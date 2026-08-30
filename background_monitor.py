import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from my_agent.services.commitment_service import (
    list_commitments,
    remember_email_analysis,
    remember_subscription_analysis,
)

from my_agent.services.cancellation_followup_service import (
    confirm_cancellation_if_supported,
)

from my_agent.services.financial_classifier import (
    classify_financial_email,
)

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)

from my_agent.services.gmail_service import (
    get_unprocessed_emails,
    mark_message_processed,
)

from my_agent.services.observation_service import (
    normalize_gmail_observation,
    normalize_transaction_observation,
)

from my_agent.services.subscription_detector import (
    analyze_subscription_for_merchant,
    group_transactions_by_merchant,
)

from my_agent.services.transaction_source import (
    get_transaction_source,
)

from my_agent.services.meaningful_change_service import (
    decide_commitment_attention,
)

from my_agent.services.commitment_change_detector import (
    build_commitment_event_key,
)

from my_agent.tools.notification_tools import (
    create_financial_notification,
)

from my_agent.tools.action_tools import (
    prepare_cancellation_followup_action,
)
MONITOR_STATE_COLLECTION = "background_monitor_state"
MONITOR_STATE_DOCUMENT_ID = "current"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_pending_cancellations(
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """
    Continue monitoring commitments after a cancellation
    action has been executed.

    Each cancellation_requested commitment is verified
    using the strongest evidence available:
    provider API when supported, otherwise monitoring
    evidence.
    """
    if as_of_date is None:
        as_of_date = datetime.now(
            timezone.utc
        ).date().isoformat()

    candidates = [
        commitment
        for commitment in list_commitments()
        if commitment.get("status")
        == "cancellation_requested"
    ]

    results = []

    for commitment in candidates:
        commitment_id = commitment.get(
            "commitment_id"
        )

        if not commitment_id:
            continue

        try:
            result = (
                confirm_cancellation_if_supported(
                    commitment_id,
                    as_of_date,
                )
            )

        except Exception as exc:
            result = {
                "success": False,
                "updated": False,
                "reason": "verification_error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

        results.append(
            {
                "commitment_id": commitment_id,
                **result,
            }
        )

    return {
        "checked": len(results),
        "updated": sum(
            1
            for result in results
            if result.get("updated")
        ),
        "results": results,
    }


def poll_gmail(
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """
    Fetch Gmail messages Safe Signal has not processed before.
    """
    return get_unprocessed_emails(
        max_results=max_results
    )


def poll_transactions() -> list[dict[str, Any]]:
    """
    Fetch transactions through the configured source abstraction.
    """
    source = get_transaction_source()
    return source.fetch_transactions()


def _transaction_key(
    transaction: dict[str, Any],
) -> str:
    """
    Build a deterministic key for one transaction.

    The MVP feed has no bank transaction ID, so Safe Signal
    fingerprints stable transaction fields.
    """
    identity = {
        "merchant": transaction.get("merchant"),
        "amount": transaction.get("amount"),
        "currency": transaction.get("currency"),
        "date": transaction.get("date"),
        "type": transaction.get("type"),
    }

    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()


def get_new_transactions(
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Return only transactions not seen by the background
    monitor before.

    On the first run, current data becomes the baseline
    instead of generating historical alerts.
    """
    state = get_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
    )

    current_keys = [
        _transaction_key(transaction)
        for transaction in transactions
    ]

    if state is None:
        set_document(
            MONITOR_STATE_COLLECTION,
            MONITOR_STATE_DOCUMENT_ID,
            {
                "seen_transaction_keys": current_keys,
                "last_checked_at": _now(),
            },
        )

        return {
            "bootstrapped": True,
            "new_transactions": [],
        }

    seen_keys = set(
        state.get(
            "seen_transaction_keys",
            [],
        )
    )

    new_transactions = [
        transaction
        for transaction, key in zip(
            transactions,
            current_keys,
        )
        if key not in seen_keys
    ]

    return {
        "bootstrapped": False,
        "new_transactions": new_transactions,
    }

def mark_transactions_seen(
    transactions: list[dict[str, Any]],
) -> None:
    """
    Mark transactions as seen only after processing
    completes successfully.
    """
    if not transactions:
        return

    state = get_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
    ) or {}

    existing_keys = state.get(
        "seen_transaction_keys",
        [],
    )

    new_keys = [
        _transaction_key(transaction)
        for transaction in transactions
    ]

    merged_keys = list(
        dict.fromkeys(
            [
                *existing_keys,
                *new_keys,
            ]
        )
    )

    set_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
        {
            **state,
            "seen_transaction_keys": merged_keys,
        },
    )

def process_gmail_observation(
    email: dict[str, Any],
) -> dict[str, Any]:
    """
    Classify one Gmail message and update Financial
    Commitment Memory when it represents a commitment.

    Notification and attention decisions are handled later.
    """
    analysis = classify_financial_email(
        email
    )

    normalized = normalize_gmail_observation(
        analysis
    )

    if not normalized.get("success"):
        return {
            "success": True,
            "memory_updated": False,
            "reason": normalized.get(
                "reason",
                "not_a_commitment",
            ),
            "analysis": analysis,
        }

    memory_result = remember_email_analysis(
        analysis
    )

    return {
        "success": True,
        "memory_updated": bool(
            memory_result.get(
                "created_or_updated"
            )
        ),
        "analysis": analysis,
        "observation": normalized.get(
            "observation"
        ),
        "memory_result": memory_result,
    }


def process_gmail_batch(
    emails: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Process only Gmail messages that have not been
    processed before.
    """
    processed = 0
    memory_updates = 0
    decisions = []

    for email in emails:
        try:
            result = process_gmail_observation(
                email
            )
        except Exception:
            # Leave failed messages unprocessed so
            # a later background run can retry them.
            continue

        if not result.get("success"):
            continue

        mark_message_processed(
            email
        )

        processed += 1

        if result.get("memory_updated"):
            memory_updates += 1
        decision = evaluate_memory_result(
            result.get("memory_result")
        )

        if decision is not None:
            decisions.append(decision)

    return {
        "processed": processed,
        "memory_updates": memory_updates,
        "decisions": decisions,
    }


def process_transaction_batch(
    new_transactions: list[dict[str, Any]],
    all_transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Process only merchants touched by new transactions.

    Full history for each affected merchant is used to
    detect recurring commitments.
    """
    if not new_transactions:
        return {
            "processed": 0,
            "memory_updates": 0,
            "decisions": [],
        }

    grouped = group_transactions_by_merchant(
        all_transactions
    )

    target_merchants = {
        str(
            transaction.get("merchant")
            or ""
        ).strip()
        for transaction in new_transactions
        if transaction.get("merchant")
    }

    memory_updates = 0
    decisions = []

    for merchant in target_merchants:
        history = grouped.get(
            merchant,
            [],
        )

        analysis = analyze_subscription_for_merchant(
            merchant,
            history,
        )

        normalized = normalize_transaction_observation(
            analysis
        )

        if not normalized.get("success"):
            continue

        memory_result = remember_subscription_analysis(
            analysis
        )

        if memory_result.get(
            "created_or_updated"
        ):
            memory_updates += 1

        decision = evaluate_memory_result(
            memory_result
        )

        if decision is not None:
            decisions.append(decision)

    return {
        "processed": len(new_transactions),
        "memory_updates": memory_updates,
        "decisions": decisions,
    }

def evaluate_memory_result(
    memory_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Run the meaningful-change decision for a commitment
    that was created or refreshed during this monitor run.
    """
    if not memory_result:
        return None

    commitment = memory_result.get(
        "commitment"
    )

    if not commitment:
        return None

    as_of_date = datetime.now(
        timezone.utc
    ).date().isoformat()

    return decide_commitment_attention(
        commitment,
        as_of_date,
    )

def create_notifications_for_decisions(
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Automatically create notifications for meaningful
    attention events.

    Stable event keys prevent duplicate notifications
    across repeated background runs.
    """
    created = 0
    results = []

    for decision in decisions:
        if (
            not decision.get("meaningful")
            or decision.get("decision")
            != "attention"
        ):
            continue

        event_key = build_commitment_event_key(
            decision
        )

        if not event_key:
            continue

        provider = (
            decision.get("provider")
            or decision.get("commitment_id")
            or "Financial commitment"
        )

        change_type = (
            decision.get("change_type")
            or "financial_change"
        )

        priority = (
            decision.get("priority")
            or "MEDIUM"
        )

        currency = (
            decision.get("currency")
            or ""
        )

        if change_type in {
            "price_increase",
            "price_decrease",
        }:
            expected = decision.get(
                "expected_amount"
            )
            observed = decision.get(
                "observed_amount"
            )

            direction = (
                "increase"
                if change_type == "price_increase"
                else "decrease"
            )

            title = (
                f"{provider} price {direction}"
            )

            message = (
                f"{provider} changed from "
                f"{currency} {expected} to "
                f"{currency} {observed}."
            )

            annual_impact = decision.get(
                "annual_impact"
            )

            if annual_impact is not None:
                message += (
                    f" Annual impact: "
                    f"{currency} {annual_impact}."
                )

        elif change_type == "upcoming_renewal":
            upcoming_date = (
                decision.get("upcoming_date")
                or decision.get("renewal_date")
                or decision.get("due_date")
                or decision.get(
                    "next_expected_date"
                )
            )

            title = (
                f"{provider} renewal approaching"
            )

            message = (
                f"{provider} has an upcoming "
                f"renewal on {upcoming_date}."
            )

        elif change_type == "renewal_overdue":
            title = (
                f"{provider} renewal overdue"
            )

            message = (
                f"{provider} has a renewal "
                f"that is overdue."
            )

        else:
            title = (
                f"{provider} needs attention"
            )

            message = (
                f"Safe Signal detected a meaningful "
                f"change for {provider}."
            )

        notification_result = (
            create_financial_notification(
                title,
                message,
                priority,
                change_type,
                event_key,
                commitment_id=decision.get(
                    "commitment_id"
                ),
            )
        )

        results.append(
            notification_result
        )

        if notification_result.get("created"):
            created += 1

    return {
        "created": created,
        "results": results,
    }

def prepare_followup_actions_for_decisions(
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Prepare follow-up actions for serious financial events.

    A charge after a cancellation request creates a new
    pending action for explicit user approval.
    """
    created = 0
    results = []

    for decision in decisions:
        if (
            decision.get("decision") != "attention"
            or decision.get("change_type")
            != "charge_after_cancellation"
        ):
            continue

        event_key = build_commitment_event_key(
            decision
        )

        if not event_key:
            continue

        provider = (
            decision.get("provider")
            or "Unknown provider"
        )

        result = (
            prepare_cancellation_followup_action(
                provider,
                event_key,
                (
                    f"A charge from {provider} was detected "
                    "after cancellation was requested. "
                    "Review and follow up with the provider."
                ),
            )
        )

        results.append(result)

        if result.get("created"):
            created += 1

    return {
        "created": created,
        "results": results,
    }

def save_monitor_status(
    last_checked_at: str,
) -> None:
    """
    Persist the latest successful background monitor check.
    """
    state = get_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
    ) or {}

    set_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
        {
            **state,
            "last_checked_at": last_checked_at,
        },
    )

def save_last_meaningful_event(
    event: dict[str, Any],
) -> None:
    """
    Persist the most recent meaningful financial event
    for dashboard/status display.
    """
    event_key = build_commitment_event_key(
        event
    )

    if not event_key:
        return

    state = get_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
    ) or {}

    recorded_at = _now()

    last_event = {
        "event_key": event_key,
        "commitment_id": event.get(
            "commitment_id"
        ),
        "provider": event.get("provider"),
        "change_type": event.get(
            "change_type"
        ),
        "priority": event.get("priority"),
        "expected_amount": event.get(
            "expected_amount"
        ),
        "observed_amount": event.get(
            "observed_amount"
        ),
        "annual_impact": event.get(
            "annual_impact"
        ),
        "upcoming_date": (
            event.get("upcoming_date")
            or event.get("renewal_date")
            or event.get("due_date")
            or event.get("next_expected_date")
        ),
        "recorded_at": recorded_at,
    }

    set_document(
        MONITOR_STATE_COLLECTION,
        MONITOR_STATE_DOCUMENT_ID,
        {
            **state,
            "last_meaningful_event": last_event,
            "last_meaningful_event_at": recorded_at,
        },
    )

def run_background_monitor() -> dict[str, Any]:
    """
    Main entry point for Safe Signal background monitoring.
    """
    started_at = _now()

    emails = poll_gmail()
    transactions = poll_transactions()

    gmail_processing = process_gmail_batch(
        emails
    )

    transaction_poll = get_new_transactions(
        transactions
    )

    new_transactions = transaction_poll[
        "new_transactions"
    ]

    transaction_processing = (
        process_transaction_batch(
            new_transactions,
            transactions,
        )
    )

    mark_transactions_seen(
        new_transactions
    )

    total_memory_updates = (
        gmail_processing["memory_updates"]
        + transaction_processing["memory_updates"]
    )

    decisions = (
        gmail_processing["decisions"]
        + transaction_processing["decisions"]
    )

    attention_events = [
        decision
        for decision in decisions
        if decision.get("decision")
        == "attention"
    ]

    if attention_events:
        save_last_meaningful_event(
            attention_events[-1]
        )

    notification_processing = (
        create_notifications_for_decisions(
            attention_events
        )
    )

    followup_processing = (
        prepare_followup_actions_for_decisions(
            attention_events
        )
    )

    cancellation_verification = (
        verify_pending_cancellations()
    )

    finished_at = _now()

    save_monitor_status(
        finished_at
    )

    return {
        "success": True,
        "started_at": started_at,

        "gmail": {
            "checked": True,
            "new_messages": len(emails),
            "processed": gmail_processing[
                "processed"
            ],
            "memory_updates": gmail_processing[
                "memory_updates"
            ],
        },

        "transactions": {
            "checked": True,
            "available": len(transactions),
            "bootstrapped": transaction_poll[
                "bootstrapped"
            ],
            "new_transactions": len(
                new_transactions
            ),
            "processed": transaction_processing[
                "processed"
            ],
            "memory_updates": transaction_processing[
                "memory_updates"
            ],
        },

        "decisions": {
        "evaluated": len(decisions),
        "attention": len(attention_events),
        "silent": (
            len(decisions)
            - len(attention_events)
        ),
    },

        "notifications_created": (
            notification_processing["created"]
        ),

        "followup_actions_created": (
            followup_processing["created"]
        ),

        "cancellation_verification": (
            cancellation_verification
        ),

        "memory_updates": total_memory_updates,
        "finished_at": finished_at,
    }


def main() -> None:
    result = run_background_monitor()
    print(result)


if __name__ == "__main__":
    main()