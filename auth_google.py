"""
Rode uma única vez para autorizar o acesso ao Google Calendar.
Gera token.json — não commitar.

Uso:
    python auth_google.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/tasks",
]
credentials_path = os.environ.get("GOOGLE_CREDENTIALS_JSON", "./credentials.json")
token_path = os.environ.get("GOOGLE_TOKEN_JSON", "./token.json")

flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
creds = flow.run_local_server(port=0)

Path(token_path).write_text(creds.to_json())
print(f"✅ Autorizado. Token salvo em: {token_path}")
