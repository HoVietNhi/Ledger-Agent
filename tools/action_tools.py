import os
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from my_agent.services.firestore_service import (
    create_document,
    get_document,
    list_documents,
    update_document,
)


COLLECTION_NAME = "financial_actions"

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


def _get_action(action_id: str) -> dict | None:
    """
    Return one financial action from Firestore.
    """
    document = get_document(
        COLLECTION_NAME,
        action_id,
    )

    if document is None:
        return None

    return _remove_internal_fields(document)


def _load_action_log() -> list:
    """
    Load all financial actions from Firestore.
    """
    documents = list_documents(COLLECTION_NAME)

    actions = [
        _remove_internal_fields(document)
        for document in documents
    ]

    actions.sort(
        key=lambda item: item.get("created_at", "")
    )

    return actions


def prepare_financial_action(
    merchant: str,
    action_type: str,
    reason: str,
) -> dict:
    """
    Prepare a financial action for user approval.

    This function never executes a real financial action.
    """
    now = _now()
    action_id = f"action_{uuid4().hex[:20]}"

    action = {
        "action_id": action_id,
        "merchant": merchant,
        "action_type": action_type,
        "reason": reason,
        "status": "pending_approval",
        "created_at": now.isoformat(),
        "approved_at": None,
        "execution_mode": "simulated",
    }

    created = create_document(
        COLLECTION_NAME,
        action_id,
        action,
    )

    if not created:
        return {
            "success": False,
            "message": (
                f"Action {action_id} already exists."
            ),
        }

    return action


def approve_financial_action(
    action_id: str,
) -> dict:
    """
    Approve a prepared financial action.

    Approval is idempotent: approving an already-approved
    action does not execute it again.
    """
    action = _get_action(action_id)

    if action is None:
        return {
            "success": False,
            "message": f"Action {action_id} was not found.",
        }

    if action.get("status") == "approved":
        return {
            "success": True,
            "already_approved": True,
            "action": action,
            "message": (
                f"Action {action_id} was already approved. "
                "No duplicate execution was performed."
            ),
        }

    if action.get("status") != "pending_approval":
        return {
            "success": False,
            "message": (
                f"Action {action_id} cannot be approved because "
                f"its status is {action.get('status')}."
            ),
        }

    update_document(
        COLLECTION_NAME,
        action_id,
        {
            "status": "approved",
            "approved_at": _now().isoformat(),
        },
    )

    return {
        "success": True,
        "already_approved": False,
        "action": _get_action(action_id),
        "message": (
            f"Action {action_id} has been approved. "
            "Execution is simulated in this MVP."
        ),
    }


def list_pending_actions() -> list:
    """
    Return actions waiting for user approval.
    """
    return [
        action
        for action in _load_action_log()
        if action.get("status")
        == "pending_approval"
    ]