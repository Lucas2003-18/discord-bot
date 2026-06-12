import logging
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bot import config
from bot.services import infra_service, gemini_service

log = logging.getLogger(__name__)

RED = 0xFF4444
BLURPLE = 0x7289DA

# Container com >N restarts e uptime curto é tratado como restart loop
RESTART_LOOP_THRESHOLD = 3
RESTART_LOOP_WINDOW_SECONDS = 600


class InfraAgent(commands.Cog):
    def __init__(self, bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
        self.bot = bot
        # Deduplicação — container com incidente aberto -> message_id do embed
        self._open_incidents: dict[str, int] = {}

        scheduler.add_job(
            self._check_incidents,
            IntervalTrigger(minutes=config.INCIDENT_CHECK_INTERVAL),
            id="infra_agent_check",
            replace_existing=True,
        )
        log.info("infra_agent: checagem de incidentes a cada %dmin", config.INCIDENT_CHECK_INTERVAL)

    @app_commands.command(name="status", description="Lista todos os containers do NUC e seus status")
    async def status_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            containers = await infra_service.get_containers()
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erro ao consultar Docker: {e}", ephemeral=True)
            return

        running = [c for c in containers if c["state"] == "running"]
        others = [c for c in containers if c["state"] != "running"]

        embed = discord.Embed(title="📦 Containers — NUC", color=BLURPLE)
        if running:
            lines = [f"🟢 `{c['name']}` — {c['status']}" for c in running]
            embed.add_field(name=f"Rodando ({len(running)})", value="\n".join(lines)[:1024], inline=False)
        if others:
            lines = [f"🔴 `{c['name']}` — {c['state']} ({c['status']})" for c in others]
            embed.add_field(name=f"Parados/outros ({len(others)})", value="\n".join(lines)[:1024], inline=False)
        if not containers:
            embed.description = "Nenhum container encontrado."

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="logs", description="Mostra as últimas linhas de log de um container")
    @app_commands.describe(container="Nome do container", linhas="Quantidade de linhas (padrão 50, máx 200)")
    async def logs_command(self, interaction: discord.Interaction, container: str, linhas: int = 50) -> None:
        await interaction.response.defer(ephemeral=True)
        linhas = max(1, min(linhas, 200))
        try:
            logs = await infra_service.get_logs(container, lines=linhas)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erro ao ler logs de `{container}`: {e}", ephemeral=True)
            return

        logs = logs.strip() or "(sem saída)"
        # Discord limita mensagens a 2000 chars — reserva espaço para o cabeçalho e ```
        chunk = logs[-1800:]
        await interaction.followup.send(
            f"📄 **{container}** (últimas {linhas} linhas)\n```\n{chunk}\n```",
            ephemeral=True,
        )

    async def _check_incidents(self) -> None:
        channel = self.bot.get_channel(config.CHANNEL_INBOX)
        if channel is None:
            log.error("infra_agent: canal %s não encontrado", config.CHANNEL_INBOX)
            return

        try:
            containers = await infra_service.get_containers()
        except Exception as e:
            log.error("infra_agent: falha ao listar containers", exc_info=e)
            return

        problem_containers: set[str] = set()

        for c in containers:
            name = c["name"]
            try:
                if c["state"] == "exited":
                    problem_containers.add(name)
                    continue

                stats = await infra_service.get_container_stats(name)
                if (
                    stats["restart_count"] > RESTART_LOOP_THRESHOLD
                    and stats["uptime_seconds"] < RESTART_LOOP_WINDOW_SECONDS
                ):
                    problem_containers.add(name)
            except Exception as e:
                log.error("infra_agent: falha ao checar stats de %s", name, exc_info=e)

        # Novos incidentes — só abre embed para quem ainda não está em aberto
        for name in problem_containers - set(self._open_incidents):
            await self._open_incident(channel, name)

        # Containers que voltaram ao normal — encerra deduplicação
        for name in set(self._open_incidents) - problem_containers:
            del self._open_incidents[name]
            log.info("infra_agent: %s voltou ao normal, incidente encerrado", name)

    async def _open_incident(self, channel: discord.abc.Messageable, name: str) -> None:
        try:
            logs = await infra_service.get_logs(name, lines=100)
        except Exception as e:
            log.error("infra_agent: falha ao ler logs de %s", name, exc_info=e)
            logs = ""

        diagnosis = await gemini_service.analyze_incident(name, logs)

        embed = discord.Embed(title=f"🔴 Incidente Detectado — {name}", color=RED)
        embed.add_field(name="Causa raiz", value=diagnosis["causa_raiz"][:1024], inline=False)
        embed.add_field(name="Sugestão", value=diagnosis["sugestao"][:1024], inline=False)
        embed.add_field(name="Confiança", value=diagnosis["confianca"], inline=False)
        embed.set_footer(text="✅ Executar  ·  ❌ Descartar  ·  💬 Discutir com Claude")

        message = await channel.send(embed=embed)
        for emoji in ("✅", "❌", "💬"):
            await message.add_reaction(emoji)

        self._open_incidents[name] = message.id
        log.info("infra_agent: incidente aberto para %s (msg %s)", name, message.id)


async def setup(bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
    await bot.add_cog(InfraAgent(bot, scheduler))
