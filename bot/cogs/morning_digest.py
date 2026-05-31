import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from bot import config
from bot.services import weather_service, github_service, rss_service, calendar_service, gmail_service

log = logging.getLogger(__name__)

BLURPLE = 0x7289DA


class MorningDigest(commands.Cog):
    def __init__(self, bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
        self.bot = bot
        scheduler.add_job(
            self._post_digest,
            CronTrigger(
                hour=config.DIGEST_HOUR,
                minute=config.DIGEST_MINUTE,
                timezone=config.TIMEZONE,
            ),
            id="morning_digest",
            replace_existing=True,
        )
        scheduler.add_job(
            self._export_dashboard,
            IntervalTrigger(minutes=10),
            id="dashboard_export",
            replace_existing=True,
        )

    @app_commands.command(name="digest", description="Gera o morning digest agora")
    async def digest_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self._build_embed()
        await interaction.followup.send(embed=embed)

    async def _export_dashboard(self) -> None:
        try:
            results = await asyncio.gather(
                weather_service.get_weather(),
                asyncio.to_thread(calendar_service.get_todays_events),
                asyncio.to_thread(calendar_service.get_todays_tasks),
                return_exceptions=True,
            )
            weather = results[0] if isinstance(results[0], dict) else None
            events  = results[1] if isinstance(results[1], list) else []
            tasks   = results[2] if isinstance(results[2], list) else []

            agenda = [
                {"time": e["start"], "title": e["summary"], "type": "event"}
                for e in events
            ] + [
                {"time": t["due"], "title": t["summary"], "type": "task", "done": False}
                for t in tasks
            ]
            agenda.sort(key=lambda x: x["time"] or "")

            data = {
                "updated_at": datetime.now(ZoneInfo(config.TIMEZONE)).isoformat(),
                "weather": {
                    "temp": weather["temp"],
                    "feels_like": weather["feels_like"],
                    "humidity": weather["humidity"],
                    "description": weather["description"],
                } if weather else None,
                "agenda": agenda,
            }

            path: Path = config.DASHBOARD_DATA_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            log.info("dashboard_export ok — %d itens na agenda", len(agenda))
        except Exception as e:
            log.error("dashboard_export failed: %s", e)

    async def _post_digest(self) -> None:
        channel = self.bot.get_channel(config.CHANNEL_MORNING_DIGEST)
        if channel is None:
            log.error("morning_digest: canal %s não encontrado", config.CHANNEL_MORNING_DIGEST)
            return
        embed = await self._build_embed()
        await channel.send(embed=embed)

    async def _build_embed(self) -> discord.Embed:
        today = date.today().strftime("%A, %d/%m/%Y")
        embed = discord.Embed(
            title=f"🌅 Morning Digest — {today}",
            color=BLURPLE,
        )

        _SERVICES = ["weather", "github", "rss_hn", "rss_devto", "calendar", "tasks", "gmail"]
        _results = await asyncio.gather(
            weather_service.get_weather(),
            asyncio.to_thread(github_service.get_recent_activity),
            asyncio.to_thread(rss_service.get_hn_top),
            asyncio.to_thread(rss_service.get_devto_top),
            asyncio.to_thread(calendar_service.get_todays_events),
            asyncio.to_thread(calendar_service.get_todays_tasks),
            asyncio.to_thread(gmail_service.get_important_emails),
            return_exceptions=True,
        )
        weather, github, hn, devto, calendar, tasks, gmail = [
            (log.error("digest: falha em %s", svc, exc_info=r) or None)
            if isinstance(r, Exception) else r
            for svc, r in zip(_SERVICES, _results)
        ]

        # Clima
        if weather:
            embed.add_field(
                name="☁️ Clima — Campinas",
                value=(
                    f"**{weather['temp']}°C** — {weather['description']}\n"
                    f"Sensação: {weather['feels_like']}°C · Umidade: {weather['humidity']}%"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="☁️ Clima", value="⚠️ Indisponível", inline=False)

        # Agenda (eventos + tasks)
        lines = []
        if calendar is not None:
            lines += [f"• {e['start'][:16].replace('T', ' ')} — {e['summary']}" for e in calendar[:5]]
        if tasks is not None:
            lines += [f"☑ {t['summary']}" for t in tasks[:5]]
        if calendar is None and tasks is None:
            embed.add_field(name="📅 Agenda", value="⚠️ Indisponível", inline=False)
        elif lines:
            embed.add_field(name="📅 Agenda", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📅 Agenda", value="_Nenhum evento ou task hoje_", inline=False)

        # GitHub
        if github:
            lines = []
            for c in github["commits"][:5]:
                lines.append(f"• `{c['repo']}` — {c['message']}")
            for pr in github["prs"][:3]:
                lines.append(f"• PR [{pr['state']}] `{pr['repo']}` — {pr['title']}")
            value = "\n".join(lines) if lines else "_Sem atividade nas últimas 24h_"
            embed.add_field(name="💻 GitHub", value=value[:1024], inline=False)
        else:
            embed.add_field(name="💻 GitHub", value="⚠️ Indisponível", inline=False)

        # Hacker News
        if hn:
            value = "\n".join(f"• [{e['title']}]({e['url']})" for e in hn)
            embed.add_field(name="📰 Hacker News", value=value[:1024], inline=False)
        else:
            embed.add_field(name="📰 Hacker News", value="⚠️ Indisponível", inline=False)

        # dev.to
        if devto:
            value = "\n".join(f"• [{e['title']}]({e['url']})" for e in devto)
            embed.add_field(name="🐍 dev.to (Python/FastAPI)", value=value[:1024], inline=False)
        else:
            embed.add_field(name="🐍 dev.to", value="⚠️ Indisponível", inline=False)

        # Gmail
        if gmail is not None:
            if gmail:
                value = "\n".join(f"• **{e['subject']}**\n  `{e['from']}`" for e in gmail)
            else:
                value = "_Nenhum e-mail importante_"
            embed.add_field(name="📧 Gmail — Importantes", value=value[:1024], inline=False)
        else:
            embed.add_field(name="📧 Gmail", value="⚠️ Indisponível", inline=False)

        embed.set_footer(text="Glitch Hub Bot")
        return embed


async def setup(bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
    await bot.add_cog(MorningDigest(bot, scheduler))
