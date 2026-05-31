# Glitch Hub Bot

Personal Discord bot for productivity automation — daily briefing, quick capture to Obsidian vault, smart slash commands, and NUC infra monitoring.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Commands

### `/digest`
Generates the morning digest immediately (also runs automatically at 07:00 BRT).

Aggregates into a single Discord embed:

| Source | Data |
|---|---|
| ☁️ OpenWeatherMap | Current weather, feels like, humidity |
| 📅 Google Calendar | Today's events |
| 💻 GitHub API | Commits and PRs from the last 24h |
| 📧 Gmail | Unread important emails from the last 24h |
| 📰 Hacker News | Top 5 links |
| 🐍 dev.to | Top 3 Python/FastAPI articles |

Resilient by design — if one integration fails, the digest still posts with the remaining sections.

**Example:**
```
/digest
```

---

### `/memo`
Captures an idea to `00-Inbox/discord-capture.md` in the Obsidian vault, with a timestamp. Response is ephemeral.

Optionally attaches an image: it gets compressed (max 1920px wide, JPEG 85%) and saved to `00-Inbox/Attachments/YYYY-MM-DD-name.jpg`, then embedded in the capture note as `![[path]]` (Obsidian syntax).

**Parameters:**
| Parameter | Required | Description |
|---|---|---|
| `texto` | ✅ | The idea or note to capture |
| `imagem` | ❌ | Image attachment (JPG, PNG, GIF, WEBP) |

**Examples:**
```
/memo texto:Idea para o projeto X — usar cache por região

/memo texto:Foto do whiteboard da reunião de hoje imagem:<attach file>
```

**Result in vault (`00-Inbox/discord-capture.md`):**
```markdown
- [2026-05-31 14:32] Idea para o projeto X — usar cache por região

- [2026-05-31 15:10] Foto do whiteboard da reunião de hoje
  ![[00-Inbox/Attachments/2026-05-31-whiteboard.jpg]]
```

---

### `/todo`
Adds a task to today's daily note (`00-Inbox/YYYY-MM-DD.md`) and optionally creates a Google Calendar event or Google Tasks item. Response is ephemeral.

**Parameters:**
| Parameter | Required | Description |
|---|---|---|
| `task` | ✅ | What to do |
| `data` | ❌ | When — see date formats below |
| `tipo` | ❌ | `tarefa` (default) or `evento` |
| `horario` | ❌ | Time for events: `14h`, `9h30`, `14:00` |

**Accepted date formats:**

| Input | Resolves to |
|---|---|
| `hoje` | Today |
| `amanhã` | Tomorrow |
| `essa sexta` | This week's Friday (no ambiguity prompt) |
| `próxima sexta` | Next week's Friday (no ambiguity prompt) |
| `sexta` | Next Friday — shows **Select Menu** if day is today or tomorrow |
| `2026-06-15` | Specific date |

> When the date is ambiguous (e.g. `/todo data:domingo` on a Saturday), the bot shows a Select Menu so you pick between "Este domingo — 01/06 (amanhã)" and "Próximo domingo — 08/06".

**Examples:**
```
/todo task:Revisar o PR do auth module
→ Appends "- [ ] Revisar o PR do auth module" to today's daily note

/todo task:Call com o cliente data:amanhã tipo:evento horario:14h
→ Appends to daily note + creates Google Calendar event tomorrow at 14:00

/todo task:Estudar APScheduler data:próxima segunda tipo:tarefa
→ Appends to daily note + creates Google Tasks item due next Monday

/todo task:Deploy produção data:2026-06-15 tipo:evento horario:10h
→ Appends to daily note + creates Calendar event on Jun 15 at 10:00
```

---

### `/alerts`
Shows a snapshot of the NUC's infrastructure health. Response is ephemeral.

Reports:
- **Containers** — lists any stopped/exited containers (checks all containers via Docker socket)
- **Disk** — usage % and free space of the host filesystem
- **CPU Load** — 1m, 5m, 15m load averages and core count

The bot also runs this check automatically every 5 minutes and posts alerts to `#inbox` when something breaks or recovers (with deduplication — no repeated alerts for the same issue).

**Example:**
```
/alerts
```

**Example output:**
```
📊 Status da Infra — NUC
Containers   ✅ Todos rodando
Disco        ✅ 34.2% usado — 128.4GB livres / 195.3GB
CPU Load     ✅ 1m: 0.45 · 5m: 0.51 · 15m: 0.48 (8 cores, 6%)
```

---

## Architecture

```
Discord Server (Glitch Hub)
  └─ GLTCH Bot (discord.py 2.x)
       ├─ Cog: MorningDigest
       │    ├─ APScheduler (07:00 America/Sao_Paulo)
       │    ├─ OpenWeatherMap API  (httpx async)
       │    ├─ Google Calendar API (OAuth 2.0)
       │    ├─ Gmail API           (OAuth 2.0)
       │    ├─ GitHub API          (PyGithub)
       │    └─ RSS feeds           (feedparser)
       │
       ├─ Cog: BrainSync
       │    ├─ /memo  →  [compress] →  Gitea REST API  →  Obsidian vault
       │    └─ /todo  →  Gitea REST API + Google Calendar/Tasks API
       │
       └─ Cog: PushAlerts
            ├─ APScheduler (every 5 min) → Docker socket + /host/proc + /host/root
            └─ /alerts  →  ephemeral status embed

  Uptime Kuma (192.168.1.100:3003)
    └─ Push monitor ← bot heartbeat every 60s
```

**Vault sync strategy:** direct Gitea REST API (`GET`/`POST`/`PUT /contents`). No local clone, no subprocess, no SSH — works cleanly behind a Cloudflare Tunnel. Concurrent writes are serialized with `asyncio.Lock` to prevent SHA conflicts.

---

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Discord | discord.py 2.3.2 |
| Scheduling | APScheduler 3.x (timezone-aware) |
| HTTP | httpx (async) |
| Google APIs | google-api-python-client + OAuth 2.0 |
| GitHub | PyGithub |
| RSS | feedparser |
| Image compression | Pillow |
| Infra | Docker + Docker Compose |
| Monitoring | Uptime Kuma (push mode) |

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

Create an OAuth 2.0 **Desktop app** credential at [Google Cloud Console](https://console.cloud.google.com), enable Calendar, Gmail and Tasks APIs, download the JSON as `credencials.json` (note: intentional typo — that's the real filename), then run:

```bash
python auth_google.py
# Opens browser → authorize → generates token.json
```

Required scopes: `calendar.readonly`, `calendar.events`, `gmail.readonly`, `tasks`

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

See `.env.example` for the full list. Key variables:

```env
DISCORD_TOKEN=
GUILD_ID=
CHANNEL_MORNING_DIGEST=
CHANNEL_INBOX=
CHANNEL_ALERTS=          # Channel for automatic infra alerts (0 = disabled)

GOOGLE_CREDENTIALS_JSON=./credencials.json
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

UPTIME_KUMA_PUSH_URL=    # Optional — push monitor URL from Uptime Kuma
INFRA_CHECK_INTERVAL=300 # Seconds between infra checks
DISK_ALERT_THRESHOLD=90  # Disk usage % to trigger alert
CPU_ALERT_THRESHOLD=80   # Load/cores % to trigger alert
```

---

## Project Structure

```
discord-bot/
├── bot/
│   ├── main.py              # Bot setup, Cog loading, APScheduler, JSON logging
│   ├── config.py            # Typed config from .env
│   ├── cogs/
│   │   ├── morning_digest.py  # /digest + 07:00 scheduler
│   │   ├── brain_sync.py      # /memo + /todo
│   │   └── push_alerts.py     # /alerts + infra scheduler
│   └── services/
│       ├── calendar_service.py  # Google Calendar + Tasks + date/time parsing
│       ├── github_service.py    # GitHub commits + PRs
│       ├── gmail_service.py     # Gmail unread + important
│       ├── weather_service.py   # OpenWeatherMap
│       ├── rss_service.py       # Hacker News + dev.to
│       ├── vault_service.py     # Gitea REST API (read/write/upload)
│       └── infra_service.py     # Docker socket + host metrics
├── auth_google.py           # One-time OAuth setup
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Roadmap

**Sprint 4 (planned):**
- [ ] Discord Webhook notifications in Uptime Kuma (down/up alerts)
- [ ] More Kuma monitors: Gitea HTTP, NUC containers, host ping
- [ ] Netdata on NUC for real-time CPU/RAM/disk metrics
- [ ] Uptime Kuma Status Page on tablet (kiosk mode)
- [ ] Custom dashboard if Status Page isn't enough

---

## License

MIT
