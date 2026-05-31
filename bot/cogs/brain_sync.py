import logging
import os
import re
from io import BytesIO
from datetime import datetime, date, timezone
import httpx
import discord
from discord.ext import commands
from discord import app_commands
from bot.services import vault_service
from bot.services.calendar_service import (
    AmbiguousDateError, create_event, create_task, parse_date_str, parse_time_str,
)

log = logging.getLogger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _compress_image(data: bytes, filename: str) -> tuple[bytes, str]:
    from PIL import Image
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".gif":
        return data, ".gif"
    try:
        img = Image.open(BytesIO(data))
        if img.width > 1920:
            ratio = 1920 / img.width
            img = img.resize((1920, int(img.height * ratio)), Image.LANCZOS)
        out = BytesIO()
        if img.mode in ("RGBA", "PA", "LA"):
            img.save(out, format="PNG", optimize=True)
            return out.getvalue(), ".png"
        img.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), ".jpg"
    except Exception:
        return data, ext


async def _finish_todo(
    interaction: discord.Interaction,
    task: str,
    event_date: date | None,
    tipo: str,
    hora: int | None,
    minuto: int,
) -> None:
    try:
        await vault_service.append_to_daily_note(task)
    except Exception as e:
        log.error("brain_sync /todo vault error: %s", e)
        await interaction.followup.send("❌ Erro ao salvar no vault.", ephemeral=True)
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


class _DateConfirmView(discord.ui.View):
    def __init__(
        self,
        options: list[tuple[str, date]],
        *,
        task: str,
        tipo: str,
        hora: int | None,
        minuto: int,
    ) -> None:
        super().__init__(timeout=60)
        self._task = task
        self._tipo = tipo
        self._hora = hora
        self._minuto = minuto

        select = discord.ui.Select(
            placeholder="Escolha a data...",
            options=[
                discord.SelectOption(label=label, value=d.isoformat())
                for label, d in options
            ],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        chosen = date.fromisoformat(interaction.data["values"][0])
        self.stop()
        await interaction.response.edit_message(content="⏳ Processando...", view=None)
        await _finish_todo(interaction, self._task, chosen, self._tipo, self._hora, self._minuto)


class BrainSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="memo", description="Captura uma ideia no vault (discord-capture.md)")
    @app_commands.describe(texto="O que você quer capturar", imagem="Imagem opcional (JPG, PNG, GIF, WEBP)")
    async def memo(
        self,
        interaction: discord.Interaction,
        texto: str,
        imagem: discord.Attachment | None = None,
    ) -> None:
        age = (datetime.now(timezone.utc) - interaction.created_at).total_seconds()
        log.info("/memo recebido: age=%.2fs id=%s imagem=%s", age, interaction.id, bool(imagem))
        await interaction.response.defer(ephemeral=True)

        attachment_path: str | None = None

        if imagem is not None:
            ext = os.path.splitext(imagem.filename)[1].lower()
            if ext not in _IMAGE_EXTS:
                await interaction.followup.send(
                    f"❌ Formato não suportado: `{ext}`. Use JPG, PNG, GIF ou WEBP.", ephemeral=True
                )
                return
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(imagem.url)
                    resp.raise_for_status()
                compressed, new_ext = _compress_image(resp.content, imagem.filename)
                stem = re.sub(r"[^\w\-]", "_", os.path.splitext(imagem.filename)[0])
                attachment_path = await vault_service.upload_attachment(f"{stem}{new_ext}", compressed)
                log.info("/memo: imagem salva em %s (%d bytes)", attachment_path, len(compressed))
            except Exception as e:
                log.error("brain_sync /memo imagem error: %s", e)
                await interaction.followup.send("❌ Erro ao fazer upload da imagem.", ephemeral=True)
                return

        try:
            await vault_service.append_to_capture(texto, attachment_path)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            reply = (
                f"✅ **Memo salvo**\n"
                f"```\n[{timestamp}] {texto}\n```\n"
                f"📁 `00-Inbox/discord-capture.md`"
            )
            if attachment_path:
                reply += f"\n🖼️ `{attachment_path}`"
            await interaction.followup.send(reply, ephemeral=True)
        except Exception as e:
            log.error("brain_sync /memo error: %s", e)
            await interaction.followup.send("❌ Erro inesperado.", ephemeral=True)

    @app_commands.command(name="todo", description="Adiciona uma task na Daily Note e opcionalmente no Google Calendar")
    @app_commands.describe(
        task="A task a registrar",
        data="Quando? hoje / amanhã / essa sexta / próxima sexta / YYYY-MM-DD",
        tipo="Criar como tarefa ou evento no Calendar (padrão: tarefa)",
        horario="Horário do evento: 15h, 9h30 ou 15:00 (só para tipo=evento)",
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="tarefa", value="tarefa"),
        app_commands.Choice(name="evento", value="evento"),
    ])
    async def todo(
        self,
        interaction: discord.Interaction,
        task: str,
        data: str | None = None,
        tipo: str = "tarefa",
        horario: str | None = None,
    ) -> None:
        age = (datetime.now(timezone.utc) - interaction.created_at).total_seconds()
        log.info("/todo recebido: age=%.2fs id=%s tipo=%s data=%s", age, interaction.id, tipo, data)
        await interaction.response.defer(ephemeral=True)

        # Valida tipo e horário antes da data — assim o Select Menu já recebe hora/minuto resolvidos
        hora: int | None = None
        minuto: int = 0
        if tipo == "evento":
            if data is None:
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

        event_date: date | None = None
        if data is not None:
            try:
                event_date = parse_date_str(data)
            except AmbiguousDateError as e:
                view = _DateConfirmView(
                    e.options, task=task, tipo=tipo, hora=hora, minuto=minuto,
                )
                await interaction.followup.send(
                    "📅 Qual data você quis dizer?", view=view, ephemeral=True,
                )
                return
            except ValueError as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
                return

        await _finish_todo(interaction, task, event_date, tipo, hora, minuto)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BrainSync(bot))
