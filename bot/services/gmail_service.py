import logging
import base64
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from bot import config

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _get_credentials() -> Credentials:
    token_path = Path(config.GOOGLE_TOKEN_JSON)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    if not creds or not creds.valid:
        raise RuntimeError(
            "token.json ausente ou inválido. "
            "Execute `python auth_google.py` uma vez para autorizar."
        )

    return creds


def get_important_emails(max_results: int = 5) -> list[dict] | None:
    try:
        service = build("gmail", "v1", credentials=_get_credentials())
        result = service.users().messages().list(
            userId="me",
            q="is:unread is:important newer_than:1d",
            maxResults=max_results,
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return []

        emails = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From"],
            ).execute()

            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            emails.append({
                "subject": headers.get("Subject", "(sem assunto)"),
                "from": headers.get("From", ""),
            })

        return emails
    except Exception as e:
        log.error("gmail_service error: %s", e)
        return None
