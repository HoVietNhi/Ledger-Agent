import json
from pathlib import Path

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


COLLECTION_NAME = "financial_events"

EVENTS_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "events.json"
)


def load_json_events() -> list[dict]:
    """
    Load financial events from the existing JSON file.
    """
    if not EVENTS_PATH.exists():
        raise FileNotFoundError(
            f"Event file was not found: {EVENTS_PATH}"
        )

    with open(
        EVENTS_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        events = json.load(file)

    if not isinstance(events, list):
        raise ValueError(
            "events.json must contain a JSON list."
        )

    return events


def migrate_events() -> dict:
    """
    Copy events from JSON to Firestore.

    The source JSON file is preserved. This migration can be
    safely rerun because event_id is used as document ID.
    """
    events = load_json_events()
    migrated_ids = []

    for event in events:
        event_id = event.get("event_id")

        if not event_id:
            raise ValueError(
                "Every event must have an event_id."
            )

        set_document(
            COLLECTION_NAME,
            event_id,
            event,
        )

        stored = get_document(
            COLLECTION_NAME,
            event_id,
        )

        if stored is None:
            raise RuntimeError(
                f"Firestore verification failed for {event_id}."
            )

        migrated_ids.append(event_id)

    return {
        "success": True,
        "source_count": len(events),
        "migrated_count": len(migrated_ids),
        "migrated_ids": migrated_ids,
        "source_file_preserved": EVENTS_PATH.exists(),
    }


if __name__ == "__main__":
    result = migrate_events()
    print(json.dumps(result, indent=2))