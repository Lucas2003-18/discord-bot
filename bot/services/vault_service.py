import asyncio
import base64
import logging
import re
from datetime import date, datetime
import httpx
from bot import config

log = logging.getLogger(__name__)

BASE = f"{config.VAULT_GITEA_URL}/api/v1/repos/{config.VAULT_GITEA_USER}/{config.VAULT_GITEA_REPO}/contents"
HEADERS = {
    "Authorization": f"token {config.VAULT_GITEA_TOKEN}",
    "Content-Type": "application/json",
}

# Serializa escritas no vault — evita conflito de SHA quando dois comandos chegam simultaneamente
_write_lock = asyncio.Lock()


async def _get_file(path: str) -> tuple[str | None, str | None]:
    """Returns (content, sha) or (None, None) if not found."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE}/{path}", headers=HEADERS)
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]


async def _put_file(path: str, content: str, message: str, sha: str | None = None) -> None:
    body: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    async with httpx.AsyncClient(timeout=15) as client:
        method = "put" if sha else "post"
        resp = await getattr(client, method)(f"{BASE}/{path}", headers=HEADERS, json=body)
        resp.raise_for_status()


async def append_to_capture(text: str, attachment_path: str | None = None) -> None:
    path = "00-Inbox/discord-capture.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- [{timestamp}] {text}"
    if attachment_path:
        line += f"\n  ![[{attachment_path}]]"
    line += "\n"
    async with _write_lock:
        existing, sha = await _get_file(path)
        if existing is None:
            new_content = f"# Discord Capture\n\n{line}"
            await _put_file(path, new_content, f"discord: capture - {text[:60]}")
        else:
            new_content = existing + line
            await _put_file(path, new_content, f"discord: capture - {text[:60]}", sha)


async def upload_attachment(filename: str, data: bytes) -> str:
    today = date.today().strftime("%Y-%m-%d")
    safe = re.sub(r"[^\w.\-]", "_", filename)
    path = f"00-Inbox/Attachments/{today}-{safe}"
    body = {
        "message": f"discord: attachment - {safe}",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": "main",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE}/{path}", headers=HEADERS, json=body)
        if resp.status_code == 422:
            # Arquivo já existe — adiciona timestamp para evitar colisão
            stem, _, ext = safe.rpartition(".")
            ts = int(datetime.now().timestamp())
            path = f"00-Inbox/Attachments/{today}-{stem}-{ts}.{ext}"
            body["message"] = f"discord: attachment - {stem}-{ts}"
            resp = await client.post(f"{BASE}/{path}", headers=HEADERS, json=body)
        resp.raise_for_status()
    return path


async def log_incident(incident: dict) -> None:
    """Registra um incidente de infra em 20-Areas/Infra/incidentes.md (append).

    `incident` espera as chaves: container, causa_raiz, solucao, status
    e opcionalmente timestamp, tempo_resolucao.
    """
    path = "20-Areas/Infra/incidentes.md"
    timestamp = incident.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M")
    container = incident["container"]

    entry = f"\n## {timestamp} — {container}\n\n"
    entry += f"**Causa raiz:** {incident.get('causa_raiz', '—')}\n"
    entry += f"**Solução aplicada:** {incident.get('solucao', '—')}\n"
    entry += f"**Status:** {incident.get('status', '—')}\n"
    if incident.get("tempo_resolucao"):
        entry += f"**Tempo de resolução:** {incident['tempo_resolucao']}\n"
    entry += "\n"

    commit_msg = f"discord: incidente - {container} ({incident.get('status', '')})"

    async with _write_lock:
        existing, sha = await _get_file(path)
        if existing is None:
            new_content = f"# Incidentes de Infra\n{entry}"
            await _put_file(path, new_content, commit_msg)
        else:
            new_content = existing + entry
            await _put_file(path, new_content, commit_msg, sha)


async def get_incident_history(container: str, limit: int = 5) -> str:
    """Retorna os últimos `limit` incidentes registrados para `container` em
    20-Areas/Infra/incidentes.md, formatados para injeção no prompt do Gemini.

    Retorna string vazia se o arquivo ainda não existir ou não houver
    incidentes anteriores para esse container.
    """
    path = "20-Areas/Infra/incidentes.md"
    content, _ = await _get_file(path)
    if content is None:
        return ""

    entries = []
    for block in content.split("\n## ")[1:]:
        header, _, body = block.partition("\n")
        _, _, name = header.partition(" — ")
        if name.strip() != container:
            continue
        entries.append(f"## {header}\n{body}".strip())

    return "\n\n".join(entries[-limit:])


async def append_to_daily_note(task: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    path = f"00-Inbox/{today}.md"
    async with _write_lock:
        existing, sha = await _get_file(path)
        if existing is None:
            new_content = f"# {today}\n\n## Tasks\n\n- [ ] {task}\n"
            await _put_file(path, new_content, f"discord: todo - {task[:60]}")
        else:
            new_content = existing + f"- [ ] {task}\n"
            await _put_file(path, new_content, f"discord: todo - {task[:60]}", sha)
