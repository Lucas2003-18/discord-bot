import asyncio
import base64
import logging
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


async def append_to_capture(text: str) -> None:
    path = "00-Inbox/discord-capture.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with _write_lock:
        existing, sha = await _get_file(path)
        if existing is None:
            new_content = f"# Discord Capture\n\n- [{timestamp}] {text}\n"
            await _put_file(path, new_content, f"discord: capture - {text[:60]}")
        else:
            new_content = existing + f"- [{timestamp}] {text}\n"
            await _put_file(path, new_content, f"discord: capture - {text[:60]}", sha)


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
