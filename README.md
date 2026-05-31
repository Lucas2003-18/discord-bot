# Glitch Hub Bot

Personal Discord bot for productivity automation — daily briefing, quick capture to Obsidian vault, and smart slash commands.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

### 🌅 Morning Digest (`/digest`)
Automated daily briefing posted at 07:00 (Campinas, BR). Aggregates:

| Source | Data |
|---|---|
| ☁️ OpenWeatherMap | Current weather + feels like + humidity |
| 📅 Google Calendar | Today's events |
| 💻 GitHub API | Commits and PRs from the last 24h |
| 📧 Gmail | Unread important emails from the last 24h |
| 📰 Hacker News | Top 5 links |
| 🐍 dev.to | Top 3 articles tagged Python/FastAPI |

Resilient by design — if one integration fails, the digest still posts with the remaining sections.

### 🧠 Quick Capture
Slash commands to capture thoughts directly to Obsidian vault without leaving Discord:

| Command | Action |
|---|---|
| `/memo [text]` | Appends to `00-Inbox/discord-capture.md` with timestamp |
| `/todo [task]` | Appends a `- [ ] task` to today's daily note (`00-Inbox/YYYY-MM-DD.md`) |

All responses are ephemeral (only visible to you). Vault sync uses the Gitea REST API — no SSH, no exposed ports.

---

## Architecture

```
Discord Server
  └─ Bot (discord.py 2.x)
       ├─ Cog: MorningDigest
       │    ├─ APScheduler (07:00 America/Sao_Paulo)
       │    ├─ OpenWeatherMap API  (httpx async)
       │    ├─ Google Calendar API (OAuth 2.0)
       │    ├─ Gmail API           (OAuth 2.0)
       │    ├─ GitHub API          (PyGithub)
       │    └─ RSS feeds           (feedparser)
       │
       └─ Cog: BrainSync
            ├─ /memo  →  Gitea REST API  →  Obsidian vault
            └─ /todo  →  Gitea REST API  →  Daily note
```

**Vault sync strategy:** the bot talks directly to the Gitea REST API (`GET`/`POST`/`PUT /contents`). No local clone, no subprocess, no SSH dependency — works cleanly behind a Cloudflare Tunnel.

---

## Stack

- **Runtime:** Python 3.12
- **Discord:** discord.py 2.3.2
- **Scheduling:** APScheduler 3.x (timezone-aware, independent of discord event loop)
- **HTTP:** httpx (async) for Weather; aiohttp (discord.py internal, custom DNS connector)
- **Google APIs:** google-api-python-client + OAuth 2.0
- **GitHub:** PyGithub
- **RSS:** feedparser
- **Infra:** Docker + Docker Compose

---

## Setup

### 1. Clone & configure

```bash
git clone https://github.com/Lucas2003-18/discord-bot.git
cd discord-bot
cp .env.example .env
# Fill in .env with your tokens
```

### 2. Google OAuth (one-time)

Create an OAuth 2.0 **Desktop app** credential at [Google Cloud Console](https://console.cloud.google.com), enable Calendar API and Gmail API, download the JSON as `credentials.json`, then run:

```bash
python auth_google.py
# Opens browser → authorize → generates token.json
```

Required scopes: `calendar.readonly`, `gmail.readonly`

### 3. Run with Docker

```bash
docker compose up -d --build
```

### 4. Run locally (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

---

## Environment Variables

See `.env.example` for the full list. Required:

```env
DISCORD_TOKEN=
GUILD_ID=
CHANNEL_MORNING_DIGEST=
CHANNEL_INBOX=

GOOGLE_CREDENTIALS_JSON=./credentials.json
GOOGLE_TOKEN_JSON=./token.json

GITHUB_TOKEN=
GITHUB_USERNAME=

OPENWEATHER_API_KEY=
OPENWEATHER_CITY=Campinas,BR

VAULT_REPO_URL=https://your-gitea-instance
VAULT_GITEA_TOKEN=
VAULT_GITEA_USER=
VAULT_GITEA_REPO=

DIGEST_HOUR=7
DIGEST_MINUTE=0
TIMEZONE=America/Sao_Paulo
```

---

## Project Structure

```
discord-bot/
├── bot/
│   ├── main.py              # Bot setup, Cog loading, APScheduler
│   ├── config.py            # Typed config from .env
│   ├── cogs/
│   │   ├── morning_digest.py
│   │   └── brain_sync.py
│   └── services/
│       ├── calendar_service.py
│       ├── github_service.py
│       ├── gmail_service.py
│       ├── weather_service.py
│       ├── rss_service.py
│       └── vault_service.py
├── auth_google.py           # One-time OAuth setup
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Roadmap

- [ ] `/todo` with optional `date` parameter (today / tomorrow / YYYY-MM-DD)
- [ ] `/agenda` — create Google Calendar events from Discord
- [ ] Cog: PushAlerts — proactive reminders from vault tasks
- [ ] Image upload in `/memo` → saves to `Attachments/`

---

## License

MIT
