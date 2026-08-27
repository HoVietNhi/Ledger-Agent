import hashlib
import os
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from my_agent.services.firestore_service import (
    create_document,
    get_document,
    list_documents,
    update_document,
)


COLLECTION_NAME = "notifications"

APP_TIMEZONE = ZoneInfo(
    os.getenv("LEDGER_TIMEZONE", "America/Toronto")
)


def _now() -> datetime:
    """
    Return a timezone-aware datetime.

    This keeps local Windows and Cloud Run on the same timezone.
    """
    return datetime.now(APP_TIMEZONE)


def _remove_internal_fields(document: dict) -> dict:
    """
    Remove Firestore helper fields before returning data
    to the agent or UI.
    """
    clean_document = dict(document)
    clean_document.pop("_document_id", None)
    return clean_document


def _load_notifications() -> list:
    """
    Load notifications from Firestore.
    """
    documents = list_documents(COLLECTION_NAME)

    notifications = [
        _remove_internal_fields(document)
        for document in documents
    ]

    notifications.sort(
        key=lambda item: item.get("created_at", "")
    )

    return notifications


def _get_notification(
    notification_id: str,
) -> dict | None:
    """
    Load one notification by its Firestore document ID.
    """
    document = get_document(
        COLLECTION_NAME,
        notification_id,
    )

    if document is None:
        return None

    return _remove_internal_fields(document)


def _find_by_event_key(
    event_key: str,
) -> dict | None:
    """
    Find an existing notification for a business event.

    Empty event keys are intentionally ignored so unrelated
    events without a key are not treated as duplicates.
    """
    if not event_key:
        return None

    for notification in _load_notifications():
        if notification.get("event_key") == event_key:
            return notification

    return None


def _build_notification_id(event_key: str) -> str:
    """
    Build a stable ID for keyed financial events.

    The same event_key always produces the same ID. Events
    without a key receive a random collision-resistant ID.
    """
    if event_key:
        digest = hashlib.sha256(
            event_key.encode("utf-8")
        ).hexdigest()[:20]

        return f"notification_{digest}"

    return f"notification_{uuid4().hex[:20]}"


def _parse_timestamp(value: str) -> datetime:
    """
    Parse old timezone-naive timestamps and new aware timestamps.

    Existing JSON timestamps are interpreted as Toronto time.
    """
    normalized_value = value

    if normalized_value.endswith("Z"):
        normalized_value = (
            normalized_value[:-1] + "+00:00"
        )

    parsed = datetime.fromisoformat(normalized_value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)

    return parsed.astimezone(APP_TIMEZONE)


def create_financial_notification(
    title: str,
    message: str,
    priority: str,
    event_type: str,
    event_key: str = "",
    reminder_after_hours: int = 24,
) -> dict:
    """
    Create one financial alert in Firestore.

    The same business event must not create duplicate alerts.
    """
    normalized_event_key = event_key.strip()

    existing = _find_by_event_key(
        normalized_event_key
    )

    if existing is not None:
        return {
            "success": True,
            "created": False,
            "message": (
                "This financial event has already been recorded. "
                "No duplicate notification was created."
            ),
            "notification": existing,
        }

    now = _now()
    notification_id = _build_notification_id(
        normalized_event_key
    )

    notification = {
        "notification_id": notification_id,
        "title": title,
        "message": message,
        "priority": priority.upper(),
        "event_type": event_type,
        "event_key": normalized_event_key,
        "status": "waiting_for_user",
        "created_at": now.isoformat(),
        "last_notified_at": now.isoformat(),
        "next_reminder_at": (
            now + timedelta(hours=reminder_after_hours)
        ).isoformat(),
        "reminder_after_hours": reminder_after_hours,
        "reminder_count": 0,
        "user_response": None,
        "resolved_at": None,
    }

    created = create_document(
        COLLECTION_NAME,
        notification_id,
        notification,
    )

    if not created:
        existing = _get_notification(notification_id)

        return {
            "success": True,
            "created": False,
            "message": (
                "This financial event has already been recorded. "
                "No duplicate notification was created."
            ),
            "notification": existing,
        }

    return {
        "success": True,
        "created": True,
        "notification": notification,
    }


def get_unread_notifications() -> list:
    """
    Return alerts still waiting for the user.
    """
    return [
        notification
        for notification in _load_notifications()
        if notification.get("status")
        == "waiting_for_user"
    ]


def mark_notification_read(
    notification_id: str,
) -> dict:
    """
    Mark a notification as seen without resolving it.
    """
    notification = _get_notification(notification_id)

    if notification is None:
        return {
            "success": False,
            "message": (
                f"Notification {notification_id} "
                "was not found."
            ),
        }

    update_document(
        COLLECTION_NAME,
        notification_id,
        {
            "seen_at": _now().isoformat(),
        },
    )

    return {
        "success": True,
        "notification": _get_notification(
            notification_id
        ),
        "message": (
            "Notification marked as seen. "
            "It is still waiting for a user response."
        ),
    }


def respond_to_notification(
    notification_id: str,
    response: str,
) -> dict:
    """
    Record the user's response to a notification.
    """
    normalized_response = response.strip().lower()

    approved_responses = {
        "yes",
        "approve",
        "approved",
    }

    dismissed_responses = {
        "no",
        "reject",
        "rejected",
        "dismiss",
    }

    if normalized_response in approved_responses:
        new_status = "user_approved"

    elif normalized_response in dismissed_responses:
        new_status = "dismissed"

    else:
        return {
            "success": False,
            "message": (
                "Unsupported response. Use yes, no, approve, "
                "reject, or dismiss."
            ),
        }

    notification = _get_notification(notification_id)

    if notification is None:
        return {
            "success": False,
            "message": (
                f"Notification {notification_id} "
                "was not found."
            ),
        }

    if notification.get("status") != "waiting_for_user":
        return {
            "success": False,
            "message": (
                "This notification is no longer waiting "
                "for a response."
            ),
        }

    now = _now().isoformat()

    update_document(
        COLLECTION_NAME,
        notification_id,
        {
            "user_response": normalized_response,
            "responded_at": now,
            "status": new_status,
            "resolved_at": now,
        },
    )

    return {
        "success": True,
        "notification": _get_notification(
            notification_id
        ),
    }


def get_due_reminders() -> list:
    """
    Return unresolved notifications whose reminder time
    has arrived.
    """
    now = _now()
    due = []

    for notification in _load_notifications():
        if notification.get("status") != "waiting_for_user":
            continue

        next_reminder_at = notification.get(
            "next_reminder_at"
        )

        if not next_reminder_at:
            continue

        try:
            reminder_time = _parse_timestamp(
                next_reminder_at
            )
        except (TypeError, ValueError):
            continue

        if reminder_time <= now:
            due.append(notification)

    return due


def mark_reminder_sent(
    notification_id: str,
) -> dict:
    """
    Record a successful reminder and schedule the next one.
    """
    notification = _get_notification(notification_id)

    if notification is None:
        return {
            "success": False,
            "message": (
                f"Notification {notification_id} "
                "was not found."
            ),
        }

    if notification.get("status") != "waiting_for_user":
        return {
            "success": False,
            "message": (
                "Notification is no longer waiting "
                "for the user."
            ),
        }

    now = _now()

    reminder_after_hours = notification.get(
        "reminder_after_hours",
        24,
    )

    updates = {
        "reminder_count": (
            notification.get("reminder_count", 0) + 1
        ),
        "last_notified_at": now.isoformat(),
        "next_reminder_at": (
            now + timedelta(hours=reminder_after_hours)
        ).isoformat(),
    }

    update_document(
        COLLECTION_NAME,
        notification_id,
        updates,
    )

    return {
        "success": True,
        "notification": _get_notification(
            notification_id
        ),
    }