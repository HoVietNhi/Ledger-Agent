import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


COLLECTION_NAME = "financial_state"
DOCUMENT_ID = "current"

APP_TIMEZONE = ZoneInfo("America/Toronto")

STATE_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "state.json"
)


def load_json_state() -> dict:
    """
    Load the existing financial snapshot from JSON.
    """
    if not STATE_PATH.exists():
        raise FileNotFoundError(
            f"State file was not found: {STATE_PATH}"
        )

    with open(
        STATE_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise ValueError(
            "state.json must contain a JSON object."
        )

    if not isinstance(state.get("emails", []), list):
        raise ValueError(
            "state.emails must be a list."
        )

    if not isinstance(
        state.get("transactions", []),
        list,
    ):
        raise ValueError(
            "state.transactions must be a list."
        )

    return state


def migrate_state() -> dict:
    """
    Copy the current financial state to Firestore.

    The source JSON file is preserved.
    """
    state = load_json_state()

    firestore_state = {
        "emails": state.get("emails", []),
        "transactions": state.get(
            "transactions",
            [],
        ),
        "schema_version": 1,
        "updated_at": datetime.now(
            APP_TIMEZONE
        ).isoformat(),
        "migrated_from": "data/state.json",
    }

    set_document(
        COLLECTION_NAME,
        DOCUMENT_ID,
        firestore_state,
    )

    stored = get_document(
        COLLECTION_NAME,
        DOCUMENT_ID,
    )

    if stored is None:
        raise RuntimeError(
            "Firestore verification failed for financial state."
        )

    return {
        "success": True,
        "email_count": len(
            stored.get("emails", [])
        ),
        "transaction_count": len(
            stored.get("transactions", [])
        ),
        "document_id": DOCUMENT_ID,
        "source_file_preserved": STATE_PATH.exists(),
        "schema_version": stored.get(
            "schema_version"
        ),
    }


if __name__ == "__main__":
    result = migrate_state()
    print(json.dumps(result, indent=2))