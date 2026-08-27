import json
from pathlib import Path

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


COLLECTION_NAME = "notifications"

NOTIFICATIONS_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "notifications.json"
)


def load_json_notifications() -> list[dict]:
    """
    Load the existing local notification data.
    """
    if not NOTIFICATIONS_PATH.exists():
        raise FileNotFoundError(
            f"Notification file was not found: {NOTIFICATIONS_PATH}"
        )

    with open(
        NOTIFICATIONS_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        notifications = json.load(file)

    if not isinstance(notifications, list):
        raise ValueError(
            "notifications.json must contain a JSON list."
        )

    return notifications


def migrate_notifications() -> dict:
    """
    Copy notifications from JSON to Firestore.

    The JSON source file is not modified or deleted.
    Existing Firestore documents with the same notification_id
    are replaced with the JSON version, making this migration
    safe to rerun.
    """
    notifications = load_json_notifications()

    migrated_ids = []

    for notification in notifications:
        notification_id = notification.get("notification_id")

        if not notification_id:
            raise ValueError(
                "Every notification must have a notification_id."
            )

        set_document(
            COLLECTION_NAME,
            notification_id,
            notification,
        )

        stored = get_document(
            COLLECTION_NAME,
            notification_id,
        )

        if stored is None:
            raise RuntimeError(
                f"Firestore verification failed for {notification_id}."
            )

        migrated_ids.append(notification_id)

    return {
        "success": True,
        "source_count": len(notifications),
        "migrated_count": len(migrated_ids),
        "migrated_ids": migrated_ids,
        "source_file_preserved": NOTIFICATIONS_PATH.exists(),
    }


if __name__ == "__main__":
    result = migrate_notifications()
    print(json.dumps(result, indent=2))