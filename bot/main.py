import asyncio
import logging
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class GlitchBot(commands.Bot):
    def __init__(self, scheduler: AsyncIOScheduler) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.scheduler = scheduler

    async def setup_hook(self) -> None:
        from bot.cogs import morning_digest, brain_sync
        await morning_digest.setup(self, self.scheduler)
        await brain_sync.setup(self)

        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Slash commands sincronizados: %s para guild %s", [c.name for c in synced], config.GUILD_ID)

        # Limpa comandos globais APÓS o guild sync (a árvore já foi copiada)
        self.tree.clear_commands(guild=None)
        await self.tree.sync(guild=None)
        log.info("Comandos globais limpos")

    async def on_ready(self) -> None:
        log.info("Bot online como %s (id=%s)", self.user, self.user.id)
        if not self.scheduler.running:
            self.scheduler.start()
            log.info("APScheduler iniciado")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    bot = GlitchBot(scheduler)
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
