import logging
from datetime import datetime, date, timezone
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


def get_todays_events() -> list[dict] | None:
    try:
        service = build("calendar", "v3", credentials=_get_credentials())
        today = date.today()
        time_min = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()
        time_max = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for e in result.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            events.append({"summary": e.get("summary", "Sem título"), "start": start})
        return events
    except RuntimeError:
        raise
    except Exception as e:
        log.error("calendar_service error: %s", e)
        return None
