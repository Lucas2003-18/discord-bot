import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
GUILD_ID: int = int(os.environ["GUILD_ID"])

CHANNEL_MORNING_DIGEST: int = int(os.environ["CHANNEL_MORNING_DIGEST"])
CHANNEL_INBOX: int = int(os.environ["CHANNEL_INBOX"])
CHANNEL_BRAIN: int = int(os.environ.get("CHANNEL_BRAIN") or "0")

GOOGLE_CREDENTIALS_JSON: str = os.environ["GOOGLE_CREDENTIALS_JSON"]
GOOGLE_TOKEN_JSON: str = os.environ.get("GOOGLE_TOKEN_JSON", "./token.json")

GITHUB_TOKEN: str = os.environ["GITHUB_TOKEN"]
GITHUB_USERNAME: str = os.environ["GITHUB_USERNAME"]

OPENWEATHER_API_KEY: str = os.environ["OPENWEATHER_API_KEY"]
OPENWEATHER_CITY: str = os.environ.get("OPENWEATHER_CITY", "Campinas,BR")

VAULT_GITEA_URL: str = os.environ.get("VAULT_REPO_URL", "https://vault.granzo.app")
VAULT_GITEA_TOKEN: str = os.environ["VAULT_GITEA_TOKEN"]
VAULT_GITEA_USER: str = os.environ.get("VAULT_GITEA_USER", "ribeiro")
VAULT_GITEA_REPO: str = os.environ.get("VAULT_GITEA_REPO", "obsidian-vault")

DIGEST_HOUR: int = int(os.environ.get("DIGEST_HOUR", "7"))
DIGEST_MINUTE: int = int(os.environ.get("DIGEST_MINUTE", "0"))
TIMEZONE: str = os.environ.get("TIMEZONE", "America/Sao_Paulo")

UPTIME_KUMA_PUSH_URL: str | None = os.environ.get("UPTIME_KUMA_PUSH_URL") or None

DASHBOARD_DATA_PATH: Path = Path(
    os.environ.get("DASHBOARD_DATA_PATH", "/app/dashboard_shared/agenda.json")
)

CHANNEL_ALERTS: int = int(os.environ.get("CHANNEL_ALERTS") or "0")
INFRA_CHECK_INTERVAL: int = int(os.environ.get("INFRA_CHECK_INTERVAL", "300"))
DISK_ALERT_THRESHOLD: float = float(os.environ.get("DISK_ALERT_THRESHOLD", "90"))
CPU_ALERT_THRESHOLD: float = float(os.environ.get("CPU_ALERT_THRESHOLD", "80"))
