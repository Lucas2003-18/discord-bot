import logging
import re
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from bot import config

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/tasks",
]

_WEEKDAYS_PT: dict[str, int] = {
    "segunda": 0, "segunda-feira": 0,
    "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sábado": 5, "sabado": 5,
    "domingo": 6,
}


def parse_date_str(date_str: str) -> date:
    s = date_str.strip().strip("\"'").strip().lower()
    today = date.today()

    if s in ("hoje", "today"):
        return today
    if s in ("amanhã", "amanha", "tomorrow"):
        return today + timedelta(days=1)
    if s in ("depois de amanhã", "depois de amanha"):
        return today + timedelta(days=2)

    if s in _WEEKDAYS_PT:
        target_wd = _WEEKDAYS_PT[s]
        days_ahead = (target_wd - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    try:
        return date.fromisoformat(date_str.strip())
    except ValueError:
        raise ValueError(f"Data não reconhecida: '{date_str}'. Use hoje/amanhã/sexta/YYYY-MM-DD")


def parse_time_str(time_str: str) -> tuple[int, int]:
    """Converte '15h', '9h30' ou '15:00' em (hora, minuto)."""
    s = time_str.strip().strip("\"'")
    m = re.fullmatch(r"(\d{1,2})h(\d{2})?", s)
    if m:
        return int(m.group(1)), int(m.group(2) or 0)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise ValueError(f"Horário não reconhecido: '{time_str}'. Use 15h, 9h30 ou 15:00")


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


def create_event(summary: str, event_date: date, hour: int | None = None, minute: int = 0) -> bool:
    try:
        service = build("calendar", "v3", credentials=_get_credentials())
        if hour is not None:
            start_dt = datetime(event_date.year, event_date.month, event_date.day, hour, minute)
            end_dt = start_dt + timedelta(hours=1)
            body = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
            }
        else:
            body = {
                "summary": summary,
                "start": {"date": event_date.isoformat()},
                "end": {"date": event_date.isoformat()},
            }
        service.events().insert(calendarId="primary", body=body).execute()
        return True
    except RuntimeError:
        raise
    except Exception as e:
        log.error("calendar_service create_event error: %s", e)
        return False


def create_task(summary: str, due_date: date | None = None) -> bool:
    try:
        service = build("tasks", "v1", credentials=_get_credentials())
        body: dict = {"title": summary}
        if due_date is not None:
            body["due"] = f"{due_date.isoformat()}T00:00:00.000Z"
        service.tasks().insert(tasklist="@default", body=body).execute()
        return True
    except RuntimeError:
        raise
    except Exception as e:
        log.error("calendar_service create_task error: %s", e)
        return False
