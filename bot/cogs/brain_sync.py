import logging
import subprocess
from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord import app_commands
from bot.services import vault_service

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
            await interaction.client.loop.run_in_executor(
                None, vault_service.append_to_capture, texto
            )
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            await interaction.followup.send(
                f"✅ **Memo salvo**\n"
                f"```\n[{timestamp}] {texto}\n```\n"
                f"📁 `00-Inbox/discord-capture.md`",
                ephemeral=True,
            )
        except subprocess.CalledProcessError as e:
            log.error("brain_sync /memo git error: %s", e.stderr)
            await interaction.followup.send(
                "❌ Falha ao sincronizar com o vault. Verifique os logs.",
                ephemeral=True,
            )
        except Exception as e:
            log.error("brain_sync /memo error: %s", e)
            await interaction.followup.send("❌ Erro inesperado.", ephemeral=True)

    @app_commands.command(name="todo", description="Adiciona uma task na Daily Note de hoje")
    @app_commands.describe(task="A task a registrar")
    async def todo(self, interaction: discord.Interaction, task: str) -> None:
        age = (datetime.now(timezone.utc) - interaction.created_at).total_seconds()
        log.info("/todo recebido: age=%.2fs id=%s", age, interaction.id)
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.client.loop.run_in_executor(
                None, vault_service.append_to_daily_note, task
            )
            from datetime import date
            today = date.today().strftime("%Y-%m-%d")
            await interaction.followup.send(
                f"✅ Task adicionada em `00-Inbox/{today}.md`",
                ephemeral=True,
            )
        except subprocess.CalledProcessError as e:
            log.error("brain_sync /todo git error: %s", e.stderr)
            await interaction.followup.send(
                "❌ Falha ao sincronizar com o vault. Verifique os logs.",
                ephemeral=True,
            )
        except Exception as e:
            log.error("brain_sync /todo error: %s", e)
            await interaction.followup.send("❌ Erro inesperado.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BrainSync(bot))
