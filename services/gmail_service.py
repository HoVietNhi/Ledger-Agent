import base64
import re
import os
import unicodedata

from email.header import decode_header, make_header
from ftfy import fix_text
from pathlib import Path
from html import unescape
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

BASE_DIR = Path(__file__).resolve().parent.parent

CREDENTIALS_PATH = BASE_DIR / "credentials.json"

TOKEN_PATH = Path(
    os.getenv(
        "GMAIL_TOKEN_PATH",
        str(BASE_DIR / "token.json"),
    )
)
GMAIL_STATE_COLLECTION = "gmail_message_state"

def _normalize_email_text(value: str | None) -> str:
    """
    Normalize email text and repair common Unicode/mojibake issues.

    Examples:
        Mojibake text is repaired when possible.
        normal ASCII/Unicode text remains unchanged.
    """
    if not value:
        return ""

    text = str(value)

    try:
        text = str(make_header(decode_header(text)))
    except Exception:
        pass

    # Repair mojibake / broken Unicode encoding.
    text = fix_text(text)

    # Normalize Unicode representation.
    text = unicodedata.normalize("NFC", text)

    return text.strip()

def get_gmail_service():
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            TOKEN_PATH,
            SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        if os.getenv("GMAIL_TOKEN_PATH"):
            # Cloud Run secret mounts are read-only.
            # Do not attempt to write refreshed credentials back.
            pass
        else:
            TOKEN_PATH.write_text(
                creds.to_json(),
                encoding="utf-8",
            )

    return build(
        "gmail",
        "v1",
        credentials=creds,
    )


def _decode_body(data: str) -> str:
    if not data:
        return ""

    decoded = base64.urlsafe_b64decode(
        data + "=" * (-len(data) % 4)
    )

    return decoded.decode(
        "utf-8",
        errors="replace",
    )

def _html_to_text(html: str) -> str:
    if not html:
        return ""

    text = re.sub(
        r"<br\s*/?>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"</(p|div|h[1-6]|li|tr)\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"<[^>]+>",
        "",
        text,
    )

    text = unescape(text)

    text = re.sub(
        r"\n\s*\n+",
        "\n",
        text,
    )

    return text.strip()

def _extract_body(payload: dict) -> str:
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded = _decode_body(body_data)

        if payload.get("mimeType") == "text/html":
            return _html_to_text(decoded)

        return decoded

    for part in payload.get("parts", []):
        mime_type = part.get("mimeType", "")

        if mime_type == "text/plain":
            data = part.get("body", {}).get("data")

            if data:
                return _decode_body(data)

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")

            if data:
                return _html_to_text(
                    _decode_body(data)
                )

    for part in payload.get("parts", []):
        body = _extract_body(part)

        if body:
            return body

    return ""


def get_recent_emails(max_results: int = 5) -> list:
    service = get_gmail_service()

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            maxResults=max_results,
        )
        .execute()
    )

    messages = response.get("messages", [])
    emails = []

    for item in messages:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=item["id"],
                format="full",
            )
            .execute()
        )

        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        header_map = {
            header.get("name", "").lower(): header.get("value", "")
            for header in headers
        }

        emails.append(
            {
                "message_id": message.get("id"),
                "sender": _normalize_email_text(
                    header_map.get("from", "")
                ),
                "subject": _normalize_email_text(
                    header_map.get("subject", "")
                ),
                "received_at": header_map.get("date", ""),
                "body": _normalize_email_text(
                    _extract_body(payload)
                ),
            }
        )

    return emails

def is_message_processed(message_id: str) -> bool:
    if not message_id:
        return False

    document = get_document(
        GMAIL_STATE_COLLECTION,
        message_id,
    )

    return document is not None


def mark_message_processed(message: dict) -> None:
    message_id = message.get("message_id")

    if not message_id:
        return

    set_document(
        GMAIL_STATE_COLLECTION,
        message_id,
        {
            "message_id": message_id,
            "sender": message.get("sender", ""),
            "subject": message.get("subject", ""),
            "received_at": message.get("received_at", ""),
            "processed": True,
        },
    )


def get_unprocessed_emails(max_results: int = 50) -> list:
    emails = get_recent_emails(max_results=max_results)

    return [
        email
        for email in emails
        if not is_message_processed(
            email.get("message_id", "")
        )
    ]