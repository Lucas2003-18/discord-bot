import logging
from datetime import datetime, date, timezone
import discord
from discord.ext import commands
from discord import app_commands
from bot.services import vault_service
from bot.services.calendar_service import create_event, create_task, parse_date_str, parse_time_str

log = logging.getLogger(__name__)


class BrainSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="memo", description="Captura uma ideia no vault (discord-capture.md)")
    @app_commands.describe(texto="O que você quer capturar")
    async def memo(self, interaction: discord.Interaction, texto: str) -> None:
        age = (datetime.now(timezone.utc) - interaction.created_at).total_seconds()
        log.info("/memo recebido: age=%.2fs id=%s", age, interaction.id)
        await interaction.response.defer(ephemeral=True)
        try:
            await vault_service.append_to_capture(texto)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            await interaction.followup.send(
                f"✅ **Memo salvo**\n"
                f"```\n[{timestamp}] {texto}\n```\n"
                f"📁 `00-Inbox/discord-capture.md`",
                ephemeral=True,
            )
        except Exception as e:
            log.error("brain_sync /memo error: %s", e)
            await interaction.followup.send("❌ Erro inesperado.", ephemeral=True)

    @app_commands.command(name="todo", description="Adiciona uma task na Daily Note e opcionalmente no Google Calendar")
    @app_commands.describe(
        task="A task a registrar",
        data="Quando? hoje / amanhã / sexta / YYYY-MM-DD",
        tipo="Criar como tarefa ou evento no Calendar (padrão: tarefa)",
        horario="Horário do evento: 15h, 9h30 ou 15:00 (só para tipo=evento)",
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="tarefa", value="tarefa"),
        app_commands.Choice(name="evento", value="evento"),
    ])
    async def todo(self, interaction: discord.Interaction, task: str, data: str | None = None, tipo: str = "tarefa", horario: str | None = None) -> None:
        age = (datetime.now(timezone.utc) - interaction.created_at).total_seconds()
        log.info("/todo recebido: age=%.2fs id=%s tipo=%s data=%s", age, interaction.id, tipo, data)
        await interaction.response.defer(ephemeral=True)

        # Validação antecipada — falha rápido antes de qualquer I/O
        event_date: date | None = None
        if data is not None:
            try:
                event_date = parse_date_str(data)
            except ValueError as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
                return

        hora: int | None = None
        minuto: int = 0
        if tipo == "evento":
            if event_date is None:
                await interaction.followup.send(
                    "❌ Para tipo `evento`, o argumento `data` é obrigatório.", ephemeral=True
                )
                return
            if horario is not None:
                try:
                    hora, minuto = parse_time_str(horario)
                except ValueError as e:
                    await interaction.followup.send(f"❌ {e}", ephemeral=True)
                    return

        try:
            await vault_service.append_to_daily_note(task)
        except Exception as e:
            log.error("brain_sync /todo error: %s", e)
            await interaction.followup.send("❌ Erro inesperado.", ephemeral=True)
            return

        today_str = date.today().strftime("%Y-%m-%d")
        msg = f"✅ Task adicionada em `00-Inbox/{today_str}.md`"

        if event_date is not None:
            try:
                if tipo == "evento":
                    created = await interaction.client.loop.run_in_executor(
                        None, create_event, task, event_date, hora, minuto
                    )
                    if created:
                        time_suffix = f" às {hora:02d}:{minuto:02d}" if hora is not None else ""
                        msg += f"\n📅 Evento criado no Calendar para `{event_date.isoformat()}`{time_suffix}"
                    else:
                        msg += "\n⚠️ Task salva no vault, mas falha ao criar evento no Calendar — veja os logs."
                else:
                    created = await interaction.client.loop.run_in_executor(
                        None, create_task, task, event_date
                    )
                    if created:
                        msg += f"\n✔️ Tarefa criada no Google Tasks para `{event_date.isoformat()}`"
                    else:
                        msg += "\n⚠️ Task salva no vault, mas falha ao criar tarefa no Google Tasks — veja os logs."
            except RuntimeError:
                msg += "\n⚠️ Task salva no vault, mas token do Google inválido. Reautorize com `auth_google.py`."

        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BrainSync(bot))
