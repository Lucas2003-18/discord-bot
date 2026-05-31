import asyncio
import json
import logging
import httpx
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bot import config


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__ and not k.startswith("_")
        }
        if extra:
            obj.update(extra)
        return json.dumps(obj, ensure_ascii=False, default=str)


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    # silencia loggers verbosos de terceiros
    for noisy in ("discord.gateway", "discord.client", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_logging()
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


async def _uptime_heartbeat() -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(config.UPTIME_KUMA_PUSH_URL)
        log.debug("uptime_kuma: heartbeat enviado")
    except Exception as e:
        log.error("uptime_kuma: falha no heartbeat", exc_info=e)


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    if config.UPTIME_KUMA_PUSH_URL:
        scheduler.add_job(
            _uptime_heartbeat,
            IntervalTrigger(seconds=60),
            id="uptime_heartbeat",
            replace_existing=True,
        )
        log.info("uptime_kuma: heartbeat agendado a cada 60s")

    bot = GlitchBot(scheduler)
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
