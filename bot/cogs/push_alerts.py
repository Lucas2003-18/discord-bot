import logging
import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bot import config
from bot.services import infra_service

log = logging.getLogger(__name__)

BLURPLE = 0x7289DA
RED = 0xFF4444
GREEN = 0x57F287


class PushAlerts(commands.Cog):
    def __init__(self, bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
        self.bot = bot
        self._active_alerts: set[str] = set()

        if config.CHANNEL_ALERTS and config.INFRA_CHECK_INTERVAL > 0:
            scheduler.add_job(
                self._check_infra,
                IntervalTrigger(seconds=config.INFRA_CHECK_INTERVAL),
                id="push_alerts_infra",
                replace_existing=True,
            )
            log.info("push_alerts: checagem de infra a cada %ds", config.INFRA_CHECK_INTERVAL)

    @app_commands.command(name="alerts", description="Mostra o estado atual da infra do NUC")
    async def alerts_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        embed = await self._build_status_embed()
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _check_infra(self) -> None:
        channel = self.bot.get_channel(config.CHANNEL_ALERTS)
        if channel is None:
            log.error("push_alerts: canal %s não encontrado", config.CHANNEL_ALERTS)
            return

        alerts_now: dict[str, str] = await self._collect_alerts()
        new_keys = set(alerts_now) - self._active_alerts
        resolved_keys = self._active_alerts - set(alerts_now)
        self._active_alerts = set(alerts_now)

        if new_keys:
            embed = discord.Embed(title="🚨 Alerta de Infra — NUC", color=RED)
            embed.description = "\n".join(alerts_now[k] for k in sorted(new_keys))
            await channel.send(embed=embed)

        if resolved_keys:
            embed = discord.Embed(title="✅ Infra normalizada — NUC", color=GREEN)
            embed.description = f"{len(resolved_keys)} alerta(s) resolvido(s)"
            await channel.send(embed=embed)

    async def _collect_alerts(self) -> dict[str, str]:
        alerts: dict[str, str] = {}

        try:
            stopped = await infra_service.get_stopped_containers()
            for c in stopped:
                key = f"container:{c['name']}"
                alerts[key] = f"🔴 Container `{c['name']}` está **{c['state']}** ({c['status']})"
        except Exception as e:
            log.error("push_alerts: falha ao checar containers: %s", e)

        try:
            disk = infra_service.get_disk_usage()
            if disk["used_pct"] >= config.DISK_ALERT_THRESHOLD:
                alerts["disk:high"] = (
                    f"💾 Disco em **{disk['used_pct']}%** "
                    f"({disk['free_gb']}GB livres de {disk['total_gb']}GB)"
                )
        except Exception as e:
            log.error("push_alerts: falha ao checar disco: %s", e)

        try:
            _, _, load15 = infra_service.get_load_avg()
            cores = infra_service.get_cpu_cores()
            if load15 / cores >= config.CPU_ALERT_THRESHOLD / 100:
                alerts["cpu:high"] = (
                    f"⚠️ Load 15min: **{load15}** em {cores} core(s) "
                    f"({round(load15 / cores * 100)}%)"
                )
        except Exception as e:
            log.error("push_alerts: falha ao checar CPU: %s", e)

        return alerts

    async def _build_status_embed(self) -> discord.Embed:
        embed = discord.Embed(title="📊 Status da Infra — NUC", color=BLURPLE)

        # Containers
        try:
            stopped = await infra_service.get_stopped_containers()
            if stopped:
                lines = [f"🔴 `{c['name']}` — {c['state']}" for c in stopped]
                embed.add_field(name="Containers parados", value="\n".join(lines), inline=False)
            else:
                embed.add_field(name="Containers", value="✅ Todos rodando", inline=False)
        except Exception as e:
            embed.add_field(name="Containers", value=f"⚠️ Erro: {e}", inline=False)

        # Disco
        try:
            disk = infra_service.get_disk_usage()
            icon = "🟡" if disk["used_pct"] >= 80 else "✅"
            embed.add_field(
                name="Disco",
                value=f"{icon} **{disk['used_pct']}%** usado — {disk['free_gb']}GB livres / {disk['total_gb']}GB",
                inline=False,
            )
        except Exception as e:
            embed.add_field(name="Disco", value=f"⚠️ Indisponível: {e}", inline=False)

        # CPU / Load
        try:
            load1, load5, load15 = infra_service.get_load_avg()
            cores = infra_service.get_cpu_cores()
            pct = round(load15 / cores * 100)
            icon = "🟡" if pct >= 60 else "✅"
            embed.add_field(
                name="CPU Load",
                value=f"{icon} 1m: **{load1}** · 5m: **{load5}** · 15m: **{load15}** ({cores} cores, {pct}%)",
                inline=False,
            )
        except Exception as e:
            embed.add_field(name="CPU Load", value=f"⚠️ Indisponível: {e}", inline=False)

        return embed


async def setup(bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
    await bot.add_cog(PushAlerts(bot, scheduler))
