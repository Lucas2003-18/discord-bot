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


def _get_file(path: str) -> tuple[str | None, str | None]:
    """Returns (content, sha) or (None, None) if not found."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{BASE}/{path}", headers=HEADERS)
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]


def _put_file(path: str, content: str, message: str, sha: str | None = None) -> None:
    body: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    with httpx.Client(timeout=15) as client:
        method = "put" if sha else "post"
        resp = getattr(client, method)(f"{BASE}/{path}", headers=HEADERS, json=body)
        resp.raise_for_status()


def append_to_capture(text: str) -> None:
    path = "00-Inbox/discord-capture.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing, sha = _get_file(path)

    if existing is None:
        new_content = f"# Discord Capture\n\n- [{timestamp}] {text}\n"
        _put_file(path, new_content, f"discord: capture - {text[:60]}")
    else:
        new_content = existing + f"- [{timestamp}] {text}\n"
        _put_file(path, new_content, f"discord: capture - {text[:60]}", sha)


def append_to_daily_note(task: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    path = f"00-Inbox/{today}.md"
    existing, sha = _get_file(path)

    if existing is None:
        new_content = f"# {today}\n\n## Tasks\n\n- [ ] {task}\n"
        _put_file(path, new_content, f"discord: todo - {task[:60]}")
    else:
        new_content = existing + f"- [ ] {task}\n"
        _put_file(path, new_content, f"discord: todo - {task[:60]}", sha)
