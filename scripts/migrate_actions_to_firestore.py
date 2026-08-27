import json
from pathlib import Path

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


COLLECTION_NAME = "financial_actions"

ACTION_LOG_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "action_log.json"
)


def load_json_actions() -> list[dict]:
    """
    Load financial actions from the existing JSON log.
    """
    if not ACTION_LOG_PATH.exists():
        raise FileNotFoundError(
            f"Action log was not found: {ACTION_LOG_PATH}"
        )

    with open(
        ACTION_LOG_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        actions = json.load(file)

    if not isinstance(actions, list):
        raise ValueError(
            "action_log.json must contain a JSON list."
        )

    return actions


def migrate_actions() -> dict:
    """
    Copy actions from JSON to Firestore.

    The source JSON file is preserved. The migration is
    idempotent because action_id is used as document ID.
    """
    actions = load_json_actions()
    migrated_ids = []

    for action in actions:
        action_id = action.get("action_id")

        if not action_id:
            raise ValueError(
                "Every action must have an action_id."
            )

        set_document(
            COLLECTION_NAME,
            action_id,
            action,
        )

        stored = get_document(
            COLLECTION_NAME,
            action_id,
        )

        if stored is None:
            raise RuntimeError(
                f"Firestore verification failed for {action_id}."
            )

        migrated_ids.append(action_id)

    return {
        "success": True,
        "source_count": len(actions),
        "migrated_count": len(migrated_ids),
        "migrated_ids": migrated_ids,
        "source_file_preserved": ACTION_LOG_PATH.exists(),
    }


if __name__ == "__main__":
    result = migrate_actions()
    print(json.dumps(result, indent=2))