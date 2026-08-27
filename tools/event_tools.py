import json
import os
from datetime import datetime
from functools import lru_cache
from uuid import uuid4
from zoneinfo import ZoneInfo

from google.cloud import pubsub_v1

from my_agent.services.firestore_service import (
    create_document,
    get_document,
    list_documents,
    update_document,
)


COLLECTION_NAME = "financial_events"
PUBSUB_TOPIC_NAME = "financial-events"

APP_TIMEZONE = ZoneInfo(
    os.getenv("LEDGER_TIMEZONE", "America/Toronto")
)


def _now() -> datetime:
    """
    Return the current timezone-aware time.
    """
    return datetime.now(APP_TIMEZONE)


def _remove_internal_fields(document: dict) -> dict:
    """
    Remove Firestore helper fields from returned data.
    """
    clean_document = dict(document)
    clean_document.pop("_document_id", None)
    return clean_document


@lru_cache(maxsize=1)
def _get_publisher() -> pubsub_v1.PublisherClient:
    """
    Create and reuse one Pub/Sub publisher client.
    """
    return pubsub_v1.PublisherClient()


def _get_event(event_id: str) -> dict | None:
    """
    Return one event from Firestore.
    """
    document = get_document(
        COLLECTION_NAME,
        event_id,
    )

    if document is None:
        return None

    return _remove_internal_fields(document)


def _load_events() -> list:
    """
    Load all financial events from Firestore.
    """
    documents = list_documents(COLLECTION_NAME)

    events = [
        _remove_internal_fields(document)
        for document in documents
    ]

    events.sort(
        key=lambda item: item.get("created_at", "")
    )

    return events


def _publish_event(event: dict) -> str:
    """
    Publish an event to the financial-events Pub/Sub topic.

    Returns the Pub/Sub message ID after delivery is accepted.
    """
    project_id = os.environ.get(
        "GOOGLE_CLOUD_PROJECT",
        "project-6ccd1116-fe8d-4414-91a",
    )

    publisher = _get_publisher()

    topic_path = publisher.topic_path(
        project_id,
        PUBSUB_TOPIC_NAME,
    )

    future = publisher.publish(
        topic_path,
        json.dumps(event).encode("utf-8"),
    )

    return future.result()


def emit_financial_event(
    event_type: str,
    merchant: str,
    details: str,
) -> dict:
    """
    Store a financial event in Firestore and publish it
    to Pub/Sub.

    The Firestore record is retained even when Pub/Sub
    publishing fails, allowing failed events to be retried.
    """
    now = _now()
    event_id = f"event_{uuid4().hex[:20]}"

    event = {
        "event_id": event_id,
        "event_type": event_type,
        "merchant": merchant,
        "details": details,
        "status": "new",
        "created_at": now.isoformat(),
        "publish_status": "pending",
        "pubsub_message_id": None,
        "published_at": None,
        "publish_error": None,
    }

    created = create_document(
        COLLECTION_NAME,
        event_id,
        event,
    )

    if not created:
        return {
            "success": False,
            "message": (
                f"Event {event_id} already exists."
            ),
        }

    try:
        message_id = _publish_event(event)

        update_document(
            COLLECTION_NAME,
            event_id,
            {
                "publish_status": "published",
                "pubsub_message_id": message_id,
                "published_at": _now().isoformat(),
                "publish_error": None,
            },
        )

    except Exception as error:
        update_document(
            COLLECTION_NAME,
            event_id,
            {
                "publish_status": "failed",
                "publish_error": str(error),
            },
        )

    return _get_event(event_id)


def get_new_financial_events() -> list:
    """
    Return financial events not processed by the agent.
    """
    return [
        event
        for event in _load_events()
        if event.get("status") == "new"
    ]


def mark_event_processed(event_id: str) -> dict:
    """
    Mark a Firestore event as processed by the agent.
    """
    event = _get_event(event_id)

    if event is None:
        return {
            "success": False,
            "message": f"Event {event_id} was not found.",
        }

    if event.get("status") == "processed":
        return {
            "success": True,
            "already_processed": True,
            "event": event,
        }

    update_document(
        COLLECTION_NAME,
        event_id,
        {
            "status": "processed",
            "processed_at": _now().isoformat(),
        },
    )

    return {
        "success": True,
        "already_processed": False,
        "event": _get_event(event_id),
    }