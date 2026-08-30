from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from my_agent.services.firestore_service import get_document
from my_agent.services.commitment_service import (
    get_commitment,
    list_commitments,
    update_commitment_expectation,
)
from my_agent.tools.notification_tools import (
    get_unread_notifications,
    respond_to_notification,
)
from my_agent.tools.action_tools import (
    COLLECTION_NAME as ACTION_COLLECTION_NAME,
    approve_financial_action,
    execute_financial_action,
    list_pending_actions,
    prepare_financial_action,
)


app = FastAPI(
    title="Safe Signal Dashboard API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MONITOR_STATE_COLLECTION = "background_monitor_state"
MONITOR_STATE_DOCUMENT_ID = "current"

MONITOR_INTERVAL_MINUTES = 15
MONITOR_STALE_AFTER_MINUTES = 30


@app.get("/health")
def health():
    return {
        "success": True,
        "service": "safesignal-dashboard-api",
    }


@app.get("/api/monitor/status")
def get_monitor_status():
    state = get_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
    )

    if not state:
        return {
            "success": True,
            "active": False,
            "status": "inactive",
            "check_interval_minutes":
                MONITOR_INTERVAL_MINUTES,
        }

    last_checked_at = state.get(
        "last_checked_at"
    )

    if not last_checked_at:
        return {
            "success": True,
            "active": False,
            "status": "inactive",
            "check_interval_minutes":
                MONITOR_INTERVAL_MINUTES,
        }

    try:
        checked_at = datetime.fromisoformat(
            last_checked_at
        )

        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(
                tzinfo=timezone.utc
            )

        now = datetime.now(timezone.utc)

        age_seconds = max(
            0,
            (
                now
                - checked_at.astimezone(
                    timezone.utc
                )
            ).total_seconds(),
        )

        age_minutes = round(
            age_seconds / 60,
            2,
        )

        active = (
            age_minutes
            <= MONITOR_STALE_AFTER_MINUTES
        )

    except (TypeError, ValueError):
        return {
            "success": False,
            "active": False,
            "status": "unknown",
            "error":
                "Invalid monitor timestamp",
        }

    return {
        "success": True,
        "active": active,
        "status":
            "active"
            if active
            else "stale",
        "last_checked_at":
            last_checked_at,
        "age_minutes":
            age_minutes,
        "check_interval_minutes":
            MONITOR_INTERVAL_MINUTES,
        "stale_after_minutes":
            MONITOR_STALE_AFTER_MINUTES,
    }


@app.get("/api/commitments")
def get_commitments():
    """
    Return persistent financial commitments
    from Safe Signal memory.
    """
    commitments = list_commitments()

    return {
        "success": True,
        "count": len(commitments),
        "commitments": commitments,
    }


@app.get("/api/notifications")
def get_notifications():
    """
    Return active financial alerts still waiting
    for the user's decision.
    """
    notifications = get_unread_notifications()

    return {
        "success": True,
        "count": len(notifications),
        "notifications": notifications,
    }


@app.get("/api/actions")
def get_actions():
    """
    Return financial actions waiting for user approval.
    """
    actions = list_pending_actions()

    return {
        "success": True,
        "count": len(actions),
        "actions": actions,
    }


@app.post("/api/commitments/{commitment_id}/keep")
def keep_commitment(
    commitment_id: str,
    notification_id: str | None = None,
):
    """
    Accept the latest observed amount as the new
    expected financial baseline.

    Resolve only the specific alert supplied by the UI,
    and only after the baseline update succeeds.
    """
    commitment = get_commitment(
        commitment_id
    )

    if commitment is None:
        return {
            "success": False,
            "reason": "commitment_not_found",
        }

    observed_amount = commitment.get(
        "last_observed_amount"
    )

    if observed_amount is None:
        return {
            "success": False,
            "reason": "observed_amount_missing",
        }

    result = update_commitment_expectation(
        commitment_id=commitment_id,
        expected_amount=observed_amount,
        user_decision="keep",
    )

    if (
        result.get("success")
        and notification_id
    ):
        result["notification_resolution"] = (
            respond_to_notification(
                notification_id,
                "approve",
            )
        )

    return result


@app.post("/api/commitments/{commitment_id}/cancel")
def prepare_cancel_commitment(
    commitment_id: str,
    notification_id: str | None = None,
):
    """
    Prepare a cancellation action for user approval.

    The source notification remains unresolved until
    execution succeeds.
    """
    commitment = get_commitment(
        commitment_id
    )

    if commitment is None:
        return {
            "success": False,
            "created": False,
            "reason": "commitment_not_found",
        }

    from my_agent.services.firestore_service import (
        update_document,
    )

    for existing_action in list_pending_actions():
        if (
            existing_action.get("commitment_id")
            == commitment_id
            and existing_action.get("action_type")
            == "cancel_subscription"
        ):
            if notification_id:
                update_document(
                    ACTION_COLLECTION_NAME,
                    existing_action["action_id"],
                    {
                        "notification_id": (
                            notification_id
                        ),
                    },
                )

                existing_action = get_document(
                    ACTION_COLLECTION_NAME,
                    existing_action["action_id"],
                )

            return {
                "success": True,
                "created": False,
                "action": existing_action,
            }

    merchant = (
        commitment.get("provider")
        or commitment.get("merchant")
        or commitment_id
    )

    action = prepare_financial_action(
        merchant=merchant,
        action_type="cancel_subscription",
        reason=(
            "User requested cancellation for "
            f"{merchant}."
        ),
    )

    action_id = action.get("action_id")

    if not action_id:
        return {
            "success": False,
            "created": False,
            "reason": "action_creation_failed",
        }

    relationship = {
        "commitment_id": commitment_id,
    }

    if notification_id:
        relationship["notification_id"] = (
            notification_id
        )

    update_document(
        ACTION_COLLECTION_NAME,
        action_id,
        relationship,
    )

    persisted_action = get_document(
        ACTION_COLLECTION_NAME,
        action_id,
    )

    return {
        "success": True,
        "created": True,
        "action": persisted_action,
    }


@app.post("/api/notifications/{notification_id}/remind")
def remind_notification(notification_id: str):
    """
    Defer a financial alert without resolving it.
    """
    return respond_to_notification(
        notification_id,
        "remind later",
    )


@app.post("/api/actions/{action_id}/approve")
def approve_action(action_id: str):
    """
    Approve a prepared financial action.

    Approval does not execute the action.
    """
    return approve_financial_action(
        action_id
    )


@app.post("/api/actions/{action_id}/execute")
def execute_action(action_id: str):
    """
    Execute an approved action.

    The linked notification is resolved only after
    backend execution succeeds.
    """
    result = execute_financial_action(
        action_id
    )

    if not result.get("success"):
        return result

    action = (
        result.get("action")
        or get_document(
            ACTION_COLLECTION_NAME,
            action_id,
        )
    )

    if not action:
        return result

    if action.get("status") != "executed":
        return result

    notification_id = action.get(
        "notification_id"
    )

    if not notification_id:
        return result

    if action.get("notification_resolved_at"):
        result["notification_resolution"] = {
            "success": True,
            "already_resolved": True,
        }
        return result

    resolution = respond_to_notification(
        notification_id,
        "approve",
    )

    result["notification_resolution"] = (
        resolution
    )

    if resolution.get("success"):
        resolved_notification = (
            resolution.get("notification")
            or {}
        )

        resolved_at = (
            resolved_notification.get(
                "resolved_at"
            )
        )

        from my_agent.services.firestore_service import (
            update_document,
        )

        update_document(
            ACTION_COLLECTION_NAME,
            action_id,
            {
                "notification_resolved_at": (
                    resolved_at
                ),
            },
        )

        result["action"] = get_document(
            ACTION_COLLECTION_NAME,
            action_id,
        )

    return result
