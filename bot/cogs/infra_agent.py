import logging
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bot import config
from bot.services import infra_service, gemini_service, vault_service

log = logging.getLogger(__name__)

RED = 0xFF4444
GREEN = 0x57F287
ORANGE = 0xFFA500
BLURPLE = 0x7289DA

# Container com >N restarts e uptime curto é tratado como restart loop
RESTART_LOOP_THRESHOLD = 3
RESTART_LOOP_WINDOW_SECONDS = 600

REACTION_EXECUTE = "✅"
REACTION_DISCARD = "❌"
REACTION_DISCUSS = "💬"


class InfraAgent(commands.Cog):
    def __init__(self, bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
        self.bot = bot
        # Deduplicação — container com incidente aberto -> {message_id, opened_at, diagnosis}
        self._open_incidents: dict[str, dict] = {}
        # message_id da segunda confirmação (rebuild) -> {"container": name, "action": "rebuild"}
        self._pending_confirmations: dict[int, dict] = {}

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

    @app_commands.command(name="restart", description="Restart manual imediato de um container")
    @app_commands.describe(container="Nome do container")
    async def restart_command(self, interaction: discord.Interaction, container: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await infra_service.restart_container(container, confirmed=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erro ao reiniciar `{container}`: {e}", ephemeral=True)
            return
        await interaction.followup.send(f"✅ `{container}` reiniciado.", ephemeral=True)

    # ------------------------------------------------------------------
    # Detecção de incidentes
    # ------------------------------------------------------------------

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
            if name in config.INFRA_IGNORE_CONTAINERS:
                continue
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

        # Timeout — incidentes abertos há mais de INCIDENT_TIMEOUT min sem resposta
        now = datetime.now(timezone.utc)
        for name, incident in list(self._open_incidents.items()):
            elapsed_minutes = (now - incident["opened_at"]).total_seconds() / 60
            if elapsed_minutes >= config.INCIDENT_TIMEOUT:
                await self._timeout_incident(channel, name, incident)

        # Novos incidentes — só abre embed para quem ainda não está em aberto
        for name in problem_containers - set(self._open_incidents):
            await self._open_incident(channel, name)

        # Containers que voltaram ao normal sem intervenção — encerra e registra
        for name in set(self._open_incidents) - problem_containers:
            incident = self._open_incidents[name]
            await self._log_and_close(
                name, incident,
                status="Resolvido (automaticamente)",
                solucao="Container voltou ao normal sem intervenção",
            )
            log.info("infra_agent: %s voltou ao normal, incidente encerrado", name)

    async def _open_incident(self, channel: discord.abc.Messageable, name: str) -> None:
        try:
            logs = await infra_service.get_logs(name, lines=100)
        except Exception as e:
            log.error("infra_agent: falha ao ler logs de %s", name, exc_info=e)
            logs = ""

        try:
            vault_history = await vault_service.get_incident_history(name)
        except Exception as e:
            log.error("infra_agent: falha ao ler histórico de incidentes de %s", name, exc_info=e)
            vault_history = ""

        diagnosis = await gemini_service.analyze_incident(name, logs, vault_history)

        embed = discord.Embed(title=f"🔴 Incidente Detectado — {name}", color=RED)
        embed.add_field(name="Causa raiz", value=diagnosis["causa_raiz"][:1024], inline=False)
        embed.add_field(name="Sugestão", value=diagnosis["sugestao"][:1024], inline=False)
        embed.add_field(name="Confiança", value=diagnosis["confianca"], inline=True)
        embed.add_field(name="Ação sugerida", value=diagnosis["acao_sugerida"], inline=True)
        embed.set_footer(text="✅ Executar  ·  ❌ Descartar  ·  💬 Discutir com Claude")

        message = await channel.send(embed=embed)
        for emoji in (REACTION_EXECUTE, REACTION_DISCARD, REACTION_DISCUSS):
            await message.add_reaction(emoji)

        self._open_incidents[name] = {
            "message_id": message.id,
            "opened_at": datetime.now(timezone.utc),
            "diagnosis": diagnosis,
        }
        log.info("infra_agent: incidente aberto para %s (msg %s)", name, message.id)

    # ------------------------------------------------------------------
    # Reações — execução / descarte / discussão
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        if emoji not in (REACTION_EXECUTE, REACTION_DISCARD, REACTION_DISCUSS):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        # Segunda confirmação (rebuild)
        pending = self._pending_confirmations.pop(payload.message_id, None)
        if pending is not None:
            await self._handle_rebuild_confirmation(channel, payload.message_id, emoji, pending)
            return

        # Embed principal do incidente
        container = next(
            (name for name, data in self._open_incidents.items() if data["message_id"] == payload.message_id),
            None,
        )
        if container is None:
            return

        incident = self._open_incidents[container]

        if emoji == REACTION_EXECUTE:
            await self._handle_execute(channel, container, incident)
        elif emoji == REACTION_DISCARD:
            await channel.send(f"❌ Incidente de `{container}` descartado.")
            await self._log_and_close(container, incident, status="Descartado")
        elif emoji == REACTION_DISCUSS:
            await self._handle_discuss(channel, container, incident)

    async def _handle_execute(self, channel: discord.abc.Messageable, container: str, incident: dict) -> None:
        action = incident["diagnosis"]["acao_sugerida"]

        if action == "restart":
            await self._run_action_and_close(channel, container, incident, "restart")
            return

        if action == "rebuild":
            warn = discord.Embed(
                title=f"⚠️ Confirmar REBUILD — {container}",
                description=(
                    f"Isso vai executar `docker compose up -d --build` para `{container}`, "
                    "reconstruindo a imagem e recriando o container (downtime breve).\n\n"
                    "Reaja ✅ para confirmar ou ❌ para cancelar."
                ),
                color=ORANGE,
            )
            msg = await channel.send(embed=warn)
            for emoji in (REACTION_EXECUTE, REACTION_DISCARD):
                await msg.add_reaction(emoji)
            self._pending_confirmations[msg.id] = {"container": container, "action": "rebuild"}
            return

        # edit_file ou nenhuma — sem execução automática disponível
        await channel.send(
            f"ℹ️ Não há ação automática disponível para `{container}` (`{action}`). "
            f"Sugestão do Gemini: {incident['diagnosis']['sugestao']}"
        )

    async def _handle_rebuild_confirmation(
        self, channel: discord.abc.Messageable, message_id: int, emoji: str, pending: dict,
    ) -> None:
        container = pending["container"]
        incident = self._open_incidents.get(container)

        if emoji == REACTION_EXECUTE:
            if incident is None:
                await channel.send(f"⚠️ Incidente de `{container}` não está mais aberto — rebuild cancelado.")
                return
            await self._run_action_and_close(channel, container, incident, "rebuild")
        elif emoji == REACTION_DISCARD:
            await channel.send(f"❌ Rebuild de `{container}` cancelado.")
            if incident is not None:
                await self._log_and_close(container, incident, status="Descartado (rebuild cancelado)")

    async def _handle_discuss(self, channel: discord.abc.Messageable, container: str, incident: dict) -> None:
        await channel.send(f"💬 Marcado para discutir com Claude: `{container}`.")
        try:
            await vault_service.append_to_daily_note(
                f"Discutir incidente de infra: {container} — {incident['diagnosis']['causa_raiz']}"
            )
        except Exception as e:
            log.error("infra_agent: falha ao registrar lembrete de %s", container, exc_info=e)
        # Não remove de _open_incidents — continua aberto até resolver/descartar/timeout

    # ------------------------------------------------------------------
    # Execução de correções + registro no vault
    # ------------------------------------------------------------------

    async def _run_action_and_close(
        self, channel: discord.abc.Messageable, container: str, incident: dict, action: str,
    ) -> None:
        try:
            await infra_service.execute_action(action, container, confirmed=True)
        except Exception as e:
            log.error("infra_agent: falha ao executar %s em %s", action, container, exc_info=e)
            await channel.send(f"⚠️ Falha ao executar `{action}` em `{container}`: {e}")
            await self._log_and_close(container, incident, status=f"Erro ao executar {action}: {e}")
            return

        await channel.send(f"✅ `{action}` executado em `{container}`.")
        await self._log_and_close(
            container, incident,
            status="Resolvido",
            solucao=f"`{action}` executado (ação sugerida pelo Gemini, confirmada por Glitch)",
        )

    async def _timeout_incident(self, channel: discord.abc.Messageable, name: str, incident: dict) -> None:
        await channel.send(
            f"⏱️ Incidente de `{name}` descartado automaticamente "
            f"(sem resposta em {config.INCIDENT_TIMEOUT}min)."
        )
        await self._log_and_close(name, incident, status="Descartado (timeout)")
        for msg_id, pending in list(self._pending_confirmations.items()):
            if pending["container"] == name:
                del self._pending_confirmations[msg_id]

    async def _log_and_close(self, container: str, incident: dict, status: str, solucao: str | None = None) -> None:
        opened_at = incident["opened_at"]
        elapsed_minutes = max(int((datetime.now(timezone.utc) - opened_at).total_seconds() // 60), 0)

        try:
            await vault_service.log_incident({
                "container": container,
                "causa_raiz": incident["diagnosis"]["causa_raiz"],
                "solucao": solucao or incident["diagnosis"]["sugestao"],
                "status": status,
                "tempo_resolucao": f"{elapsed_minutes} min",
            })
        except Exception as e:
            log.error("infra_agent: falha ao registrar incidente de %s no vault", container, exc_info=e)

        self._open_incidents.pop(container, None)


async def setup(bot: commands.Bot, scheduler: AsyncIOScheduler) -> None:
    await bot.add_cog(InfraAgent(bot, scheduler))
