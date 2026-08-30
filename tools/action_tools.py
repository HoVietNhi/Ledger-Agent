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

from my_agent.services.commitment_service import (
    COMMITMENT_COLLECTION,
    find_matching_commitment,
    update_commitment_status,
)

from my_agent.services.stripe_connector import (
    schedule_cancel_at_period_end,
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
                "No duplicate approval was performed."
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
            f"Action {action_id} has been approved "
            "and is ready for execution."
        ),
    }

def execute_financial_action(
    action_id: str,
) -> dict:
    """
    Execute an approved financial action.

    Supported execution paths:

    - Stripe TEST connector:
      schedules cancellation at the end of the current
      billing period through the real Stripe API.

    - Unsupported providers:
      keep the existing simulated MVP fallback.

    A provider action must never be marked executed if the
    external provider call fails.
    """
    action = _get_action(action_id)

    if action is None:
        return {
            "success": False,
            "message": f"Action {action_id} was not found.",
        }

    if action.get("status") == "executed":
        return {
            "success": True,
            "already_executed": True,
            "action": action,
            "message": (
                f"Action {action_id} was already executed. "
                "No duplicate execution was performed."
            ),
        }

    if action.get("status") != "approved":
        return {
            "success": False,
            "message": (
                f"Action {action_id} must be approved before "
                "it can be executed."
            ),
        }

    if action.get("action_type") != "cancel_subscription":
        return {
            "success": False,
            "message": (
                f"Action type {action.get('action_type')} "
                "is not supported for execution."
            ),
        }

    merchant = action.get("merchant", "")

    commitment = find_matching_commitment(
        merchant,
        preferred_type="subscription",
    )

    commitment_id = None
    provider_connector = None
    provider_subscription_id = None

    if commitment is not None:
        commitment_id = commitment.get(
            "commitment_id"
        )

        provider_connector = (
            commitment.get("provider_connector")
        )

        provider_subscription_id = (
            commitment.get(
                "provider_subscription_id"
            )
        )

    executed_at = _now().isoformat()

    #
    # REAL STRIPE TEST PROVIDER EXECUTION
    #
    if (
        provider_connector == "stripe"
        and provider_subscription_id
    ):
        try:
            provider_result = (
                schedule_cancel_at_period_end(
                    provider_subscription_id
                )
            )
        except Exception as exc:
            provider_result = {
                "success": False,
                "provider_connector": "stripe",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

        if not provider_result.get("success"):
            update_document(
                COLLECTION_NAME,
                action_id,
                {
                    "provider_error": provider_result,
                    "last_execution_attempt_at": (
                        executed_at
                    ),
                },
            )

            return {
                "success": False,
                "already_executed": False,
                "provider_result": provider_result,
                "action": _get_action(action_id),
                "message": (
                    "Stripe provider execution failed. "
                    "The action was not marked executed."
                ),
            }

        if not provider_result.get(
            "cancel_at_period_end"
        ):
            return {
                "success": False,
                "already_executed": False,
                "provider_result": provider_result,
                "message": (
                    "Stripe did not confirm that "
                    "cancel_at_period_end is enabled. "
                    "The action was not marked executed."
                ),
            }

        update_document(
            COLLECTION_NAME,
            action_id,
            {
                "status": "executed",
                "executed_at": executed_at,
                "execution_mode": (
                    "provider_api_test"
                ),
                "commitment_id": commitment_id,
                "provider_connector": "stripe",
                "provider_subscription_id": (
                    provider_subscription_id
                ),
                "execution_result": (
                    provider_result
                ),
            },
        )

        commitment_update = None

        if commitment_id:
            commitment_update = (
                update_commitment_status(
                    commitment_id,
                    "cancellation_requested",
                    user_decision="cancel",
                    action_status="executed",
                )
            )

            update_document(
                COMMITMENT_COLLECTION,
                commitment_id,
                {
                    "provider_connector": "stripe",
                    "provider_subscription_id": (
                        provider_subscription_id
                    ),
                    "provider_status": (
                        provider_result.get(
                            "provider_status"
                        )
                    ),
                    "cancel_at_period_end": (
                        provider_result.get(
                            "cancel_at_period_end"
                        )
                    ),
                    "cancellation_effective_at": (
                        provider_result.get(
                            "cancellation_effective_at"
                        )
                    ),
                    "provider_execution_mode": (
                        provider_result.get(
                            "execution_mode"
                        )
                    ),
                    "provider_cancellation_scheduled": (
                        True
                    ),
                    "provider_acknowledged_at": (
                        executed_at
                    ),
                    "last_provider_sync_at": (
                        executed_at
                    ),
                },
            )

        return {
            "success": True,
            "already_executed": False,
            "action": _get_action(action_id),
            "commitment_update": (
                commitment_update
            ),
            "provider_result": provider_result,
            "message": (
                f"Stripe confirmed that cancellation "
                f"for {merchant} is scheduled for the "
                "end of the current billing period. "
                "Safe Signal will continue monitoring "
                "until the subscription actually ends."
            ),
        }

    #
    # SIMULATED FALLBACK FOR UNSUPPORTED PROVIDERS
    #
    update_document(
        COLLECTION_NAME,
        action_id,
        {
            "status": "executed",
            "executed_at": executed_at,
            "execution_mode": "simulated",
            "commitment_id": commitment_id,
            "execution_result": {
                "success": True,
                "simulated": True,
                "operation": (
                    "cancel_subscription"
                ),
                "merchant": merchant,
            },
        },
    )

    commitment_update = None

    if commitment_id:
        commitment_update = (
            update_commitment_status(
                commitment_id,
                "cancellation_requested",
                user_decision="cancel",
                action_status="executed",
            )
        )

    return {
        "success": True,
        "already_executed": False,
        "action": _get_action(action_id),
        "commitment_update": commitment_update,
        "message": (
            f"Simulated cancellation for "
            f"{merchant} completed successfully. "
            "No supported provider connector was "
            "available. The commitment remains under "
            "monitoring until cancellation is verified."
        ),
    }

def prepare_cancellation_followup_action(
    merchant: str,
    event_key: str,
    reason: str,
) -> dict:
    """
    Prepare one follow-up action when a charge is detected
    after a cancellation request.

    The same financial event must not create duplicate actions.
    """
    normalized_event_key = event_key.strip()

    if not normalized_event_key:
        return {
            "success": False,
            "created": False,
            "reason": "missing_event_key",
        }

    for existing in _load_action_log():
        if (
            existing.get("event_key")
            == normalized_event_key
            and existing.get("action_type")
            == "cancellation_followup"
        ):
            return {
                "success": True,
                "created": False,
                "action": existing,
            }

    action = prepare_financial_action(
        merchant,
        "cancellation_followup",
        reason,
    )

    action_id = action.get("action_id")

    if not action_id:
        return {
            "success": False,
            "created": False,
            "reason": "action_creation_failed",
        }

    update_document(
        COLLECTION_NAME,
        action_id,
        {
            "event_key": normalized_event_key,
        },
    )

    return {
        "success": True,
        "created": True,
        "action": _get_action(action_id),
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