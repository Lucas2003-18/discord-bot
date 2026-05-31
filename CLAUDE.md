# Discord Bot — CLAUDE.md

**Stack:** Python 3.12 + discord.py 2.x + APScheduler + Docker
**Responsável:** Lucas Rafael Barbosa Ribeiro (Glitch)

---

## Leia antes de codar

- `ESCOPO.md` — o que está dentro e fora do MVP (10-Projects/Discord-Bot/ESCOPO.md, vault)
- `TASKS.md` — sprint atual e tarefas pendentes (10-Projects/Discord-Bot/TASKS.md, vault)
- `README.md` — visão geral, arquitetura, canais (10-Projects/Discord-Bot/README.md, vault)

---

## Estrutura do projeto

```
discord-bot/
├── bot/
│   ├── main.py              # Entry point — setup bot, carrega Cogs, inicia APScheduler
│   ├── config.py            # Lê .env via python-dotenv, expõe constantes tipadas
│   ├── cogs/
│   │   ├── morning_digest.py  # Cog: briefing diário automatizado
│   │   ├── brain_sync.py      # Cog: quick capture → vault via Git
│   │   └── push_alerts.py     # Cog: alertas ativos de tasks/infra (Sprint 2)
│   └── services/
│       ├── calendar_service.py   # Google Calendar API
│       ├── github_service.py     # GitHub API (PyGithub ou httpx)
│       ├── weather_service.py    # OpenWeatherMap API
│       ├── rss_service.py        # RSS feeds (feedparser)
│       └── vault_service.py      # Git clone + leitura/escrita de .md
├── .env                     # NUNCA commitar — listado no .gitignore
├── .env.example             # Template documentado — sempre manter atualizado
├── .gitignore
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Fluxo de sessão

**Ao iniciar:** leia `TASKS.md` e identifique a sprint atual antes de qualquer código.

**Ao encerrar a sessão, sempre:**
1. Atualize `TASKS.md` — marque o que foi feito, adicione pendências
2. Verifique se já existe `00-Inbox/handoff-discord-bot-YYYY-MM-DD.md` com a data de hoje no vault (olhar para 99-Meta/prompt-handoff.md (vault), para saber os dados necessários)
   - **Se existe:** edite esse arquivo — NÃO crie um novo
   - **Se não existe:** crie com a data de hoje
3. Se houve mudança arquitetural, atualize `CLAUDE.md` e `ESCOPO.md`

---

## Regras críticas

### Segurança — NUNCA violar
- `.env` **nunca** commitado — verificar `.gitignore` antes de qualquer `git add`
- Tokens Discord, Google, GitHub, OpenWeather: somente via variável de ambiente
- `VAULT_REPO_URL` pode ser SSH (preferível) ou HTTPS com token — nunca hardcoded
- Antes de qualquer `git push` no vault: confirmar que nenhum dado sensível foi escrito no `.md`

### Estrutura de Cogs
- Cada módulo = um arquivo Cog separado em `cogs/`
- Lógica de negócio vai em `services/` — Cogs só orquestram
- Slash commands registrados via `@app_commands.command`
- Respostas de quick capture sempre `ephemeral=True`

### Vault Sync (vault_service.py)
```
Fluxo obrigatório para qualquer escrita no vault:
1. git pull origin main  (garante repo atualizado)
2. pathlib.Path.write / open append  (escreve o .md)
3. git add [arquivo]
4. git commit -m "discord: [tipo] - [descrição breve]"
5. git push origin main
```
- Tratar `subprocess.CalledProcessError` — se o push falhar, logar e notificar via ephemeral
- Nunca usar `shell=True` nos subprocess calls
- Daily Note path: `00-Inbox/YYYY-MM-DD.md` (criar se não existir)
- Quick capture path: `00-Inbox/discord-capture.md` (append sempre)

### Morning Digest
- APScheduler com `timezone=America/Sao_Paulo`
- Se uma integração falhar (Calendar, GitHub, Weather, RSS), logar o erro e continuar com as demais — digest não pode ser cancelado por falha parcial
- Embed Discord: max 6000 chars total — truncar RSS se necessário
- Usar `discord.Embed` com cor `0x7289DA` (Discord blurple)

### Docker
- Container roda como usuário não-root
- Volumes para: credenciais Google (`credentials.json`), clone do vault
- `restart: unless-stopped` no docker-compose
- Logs via stdout — sem arquivo de log dentro do container

---

## Variáveis de ambiente

Ver `.env.example` para lista completa. Variáveis obrigatórias para o MVP:

```
DISCORD_TOKEN          # Token do bot (Discord Developer Portal)
GUILD_ID               # ID do servidor pessoal
CHANNEL_MORNING_DIGEST # ID do canal #morning-digest
CHANNEL_INBOX          # ID do canal #inbox
GITHUB_TOKEN           # Personal Access Token (read:user, repo)
GITHUB_USERNAME        # Lucas2003-18
OPENWEATHER_API_KEY    # Free tier — 1000 calls/dia
OPENWEATHER_CITY       # Campinas,BR
VAULT_REPO_URL         # URL SSH ou HTTPS do repo do vault
VAULT_LOCAL_PATH       # /app/vault (dentro do container)
TIMEZONE               # America/Sao_Paulo
DIGEST_HOUR            # 7
DIGEST_MINUTE          # 0
```

---

## Reportar bugs

```
Bug encontrado:
- O que eu fiz: [ação exata]
- O que esperava: [comportamento esperado]
- O que aconteceu: [comportamento real]
- Erro no log (docker logs): [cole aqui]
- Cog/service suspeito: [se souber]
```

---

## Não fazer

- ❌ Não recriar notificações do `#github` — GitHub App nativo já resolve
- ❌ Não implementar banco de dados próprio — vault Git é a fonte de verdade
- ❌ Não fazer busca semântica no vault via Discord — Claude/MCP faz isso melhor
- ❌ Não expor porta HTTP do bot para internet — Discord usa websocket de saída
- ❌ Não usar `shell=True` em subprocess
- ❌ Não commitar `.env`, `credentials.json`, ou qualquer arquivo com chave/token
- ❌ Não criar novo handoff se já existe um com a data de hoje — editar o existente

