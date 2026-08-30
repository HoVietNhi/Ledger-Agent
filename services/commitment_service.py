import re
from datetime import datetime, timezone
from typing import Any

from .firestore_service import (
    create_document,
    get_document,
    list_documents,
    update_document,
)


COMMITMENT_COLLECTION = "financial_commitments"

VALID_COMMITMENT_STATUSES = {
    "active",
    "waiting_for_user",
    "cancellation_requested",
    "inactive",
}


ALLOWED_STATUS_TRANSITIONS = {
    "active": {
        "waiting_for_user",
        "cancellation_requested",
    },
    "waiting_for_user": {
        "active",
        "cancellation_requested",
    },
    "cancellation_requested": {
        "active",
        "inactive",
    },
    "inactive": {
        "active",
    },
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()

    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    )

    return normalized.strip("-")


def build_commitment_id(
    provider: str,
    commitment_type: str,
) -> str:
    provider_key = _normalize_provider(provider)
    type_key = _normalize_provider(commitment_type)

    return f"{type_key}:{provider_key}"


def get_commitment(
    commitment_id: str,
) -> dict[str, Any] | None:
    return get_document(
        COMMITMENT_COLLECTION,
        commitment_id,
    )


def list_commitments() -> list[dict[str, Any]]:
    return list_documents(
        COMMITMENT_COLLECTION,
    )


def remember_commitment(
    provider: str,
    commitment_type: str,
    expected_amount: float | None,
    currency: str | None,
    frequency: str | None,
    last_charge_date: str | None = None,
    next_expected_date: str | None = None,
    renewal_date: str | None = None,
    due_date: str | None = None,
    previous_amount: float | None = None,
    source: str | None = None,
    observed_amount: float | None = None,
) -> dict[str, Any]:
    """
    Create or refresh a financial commitment.

    Important:
    - expected_amount becomes the baseline when the commitment
      is first created.
    - Later observations DO NOT automatically replace the
      expected baseline.
    - User decisions and lifecycle state are preserved.
    """
    commitment_id = build_commitment_id(
        provider,
        commitment_type,
    )

    timestamp = _now()

    if observed_amount is None:
        observed_amount = expected_amount

    existing = get_commitment(
        commitment_id
    )

    if existing is None:
        document = {
            "commitment_id": commitment_id,
            "provider": provider,
            "commitment_type": commitment_type,

            "status": "active",

            "expected_amount": expected_amount,
            "last_observed_amount": observed_amount,

            "currency": currency,
            "frequency": frequency,

            "previous_amount": previous_amount,
            "last_charge_date": last_charge_date,
            "next_expected_date": next_expected_date,
            "renewal_date": renewal_date,
            "due_date": due_date,

            "user_decision": None,
            "decision_at": None,
            "action_status": None,

            "source": source,

            "last_meaningful_event_key": None,

            "created_at": timestamp,
            "updated_at": timestamp,
            "last_checked_at": timestamp,
        }

        created = create_document(
            COMMITMENT_COLLECTION,
            commitment_id,
            document,
        )

        if created:
            return document

        existing = get_commitment(
            commitment_id
        )

    updates = {
        "provider": provider,
        "commitment_type": commitment_type,

        # Do NOT overwrite expected_amount here.
        "last_observed_amount": observed_amount,

        "currency": currency,
        "frequency": frequency,

        "previous_amount": previous_amount,
        "last_charge_date": last_charge_date,
        "next_expected_date": next_expected_date,

        "source": source,

        "updated_at": timestamp,
        "last_checked_at": timestamp,
    }

    if renewal_date is not None:
        updates["renewal_date"] = renewal_date

    if due_date is not None:
        updates["due_date"] = due_date

    update_document(
        COMMITMENT_COLLECTION,
        commitment_id,
        updates,
    )

    return get_commitment(
        commitment_id
    )

def find_matching_commitment(
    provider: str,
    preferred_type: str | None = None,
) -> dict[str, Any] | None:
    """
    Find an existing commitment for the same provider.

    Prefer the same commitment type. If the provider has only
    one known commitment, reuse it across observation sources.
    """
    provider_key = _normalize_provider(provider)

    matches = [
        commitment
        for commitment in list_commitments()
        if _normalize_provider(
            commitment.get("provider", "")
        ) == provider_key
    ]

    if preferred_type:
        for commitment in matches:
            if (
                commitment.get("commitment_type")
                == preferred_type
            ):
                return commitment

    if len(matches) == 1:
        return matches[0]

    return None


def remember_email_analysis(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge a structured Gmail financial observation into
    Financial Commitment Memory.

    An email and a transaction for the same commitment should
    update one unified Firestore record.
    """
    if not analysis.get("is_financial"):
        return {
            "success": False,
            "created_or_updated": False,
            "reason": "not_financial",
        }

    provider = analysis.get("merchant")

    if not provider:
        return {
            "success": False,
            "created_or_updated": False,
            "reason": "missing_provider",
        }

    category = (
        analysis.get("category")
        or ""
    ).strip().lower()

    existing = None

    if category == "subscription":
        preferred_type = "subscription"

    elif category in {"bill", "billing"}:
        preferred_type = "bill"

    elif (
        category == "renewal"
        or analysis.get("renewal_date")
    ):
        preferred_type = "renewal"

    elif category == "price_change":
        # Price change is an event type, not a commitment type.
        # Reuse the provider's known commitment when unambiguous.
        existing = find_matching_commitment(
            provider
        )

        if existing is None:
            return {
                "success": False,
                "created_or_updated": False,
                "reason": "not_a_commitment",
            }

        preferred_type = existing.get(
            "commitment_type"
        )

    else:
        return {
            "success": False,
            "created_or_updated": False,
            "reason": "not_a_commitment",
        }

    if existing is None:
        existing = find_matching_commitment(
            provider,
            preferred_type,
        )

    if existing is not None:
        commitment_type = existing.get(
            "commitment_type",
            preferred_type,
        )
    else:
        commitment_type = preferred_type

    new_amount = analysis.get("new_amount")
    old_amount = analysis.get("old_amount")
    amount = analysis.get("amount")

    observed_amount = (
        new_amount
        if new_amount is not None
        else amount
    )

    expected_amount = (
        old_amount
        if old_amount is not None
        else amount
    )

    if existing is not None:
        if expected_amount is None:
            expected_amount = existing.get(
                "expected_amount"
            )

        if observed_amount is None:
            observed_amount = existing.get(
                "last_observed_amount"
            )

    renewal_date = analysis.get(
        "renewal_date"
    )
    due_date = analysis.get(
        "due_date"
    )

    next_expected_date = (
        renewal_date
        or due_date
        or (
            existing.get("next_expected_date")
            if existing
            else None
        )
    )

    frequency = (
        analysis.get("billing_frequency")
        or (
            existing.get("frequency")
            if existing
            else None
        )
    )

    currency = (
        analysis.get("currency")
        or (
            existing.get("currency")
            if existing
            else None
        )
    )

    last_charge_date = (
        existing.get("last_charge_date")
        if existing
        else None
    )

    commitment = remember_commitment(
        provider=provider,
        commitment_type=commitment_type,
        expected_amount=expected_amount,
        observed_amount=observed_amount,
        currency=currency,
        frequency=frequency,
        previous_amount=old_amount,
        last_charge_date=last_charge_date,
        next_expected_date=next_expected_date,
        renewal_date=renewal_date,
        due_date=due_date,
        source="gmail",
    )

    return {
        "success": True,
        "created_or_updated": True,
        "matched_existing": existing is not None,
        "commitment": commitment,
    }

def remember_subscription_analysis(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert structured subscription detector output
    into Financial Commitment Memory.
    """
    if not analysis.get("is_subscription"):
        return {
            "success": False,
            "created_or_updated": False,
            "reason": "not_a_subscription",
        }

    provider = analysis.get("merchant")

    if not provider:
        return {
            "success": False,
            "created_or_updated": False,
            "reason": "missing_provider",
        }

    latest_amount = analysis.get(
        "latest_amount"
    )

    commitment = remember_commitment(
        provider=provider,
        commitment_type="subscription",
        expected_amount=latest_amount,
        observed_amount=latest_amount,
        currency=analysis.get("currency"),
        frequency=analysis.get(
            "billing_frequency"
        ),
        previous_amount=analysis.get(
            "previous_amount"
        ),
        last_charge_date=analysis.get(
            "last_charge_date"
        ),
        next_expected_date=analysis.get(
            "next_expected_date"
        ),
        source=(
            analysis.get("source")
            or "transaction"
        ),
    )

    return {
        "success": True,
        "created_or_updated": True,
        "commitment": commitment,
    }

def update_commitment_expectation(
    commitment_id: str,
    expected_amount: float,
    user_decision: str = "keep",
) -> dict[str, Any]:
    """
    Update the expected baseline after an explicit user decision.

    Example:
        User accepts Netflix CAD 29.99
        -> expected_amount becomes 29.99
    """
    existing = get_commitment(
        commitment_id
    )

    if existing is None:
        return {
            "success": False,
            "updated": False,
            "reason": "commitment_not_found",
        }

    timestamp = _now()

    updates = {
        "expected_amount": expected_amount,
        "user_decision": user_decision,
        "decision_at": timestamp,
        "updated_at": timestamp,
        "last_meaningful_event_key": None,
    }

    update_document(
        COMMITMENT_COLLECTION,
        commitment_id,
        updates,
    )

    return {
        "success": True,
        "updated": True,
        "commitment": get_commitment(
            commitment_id
        ),
    }

def update_commitment_status(
    commitment_id: str,
    new_status: str,
    user_decision: str | None = None,
    action_status: str | None = None,
) -> dict[str, Any]:
    """
    Move a financial commitment through its lifecycle.

    Commitment lifecycle is separate from notification
    and action lifecycle.
    """
    existing = get_commitment(
        commitment_id
    )

    if existing is None:
        return {
            "success": False,
            "updated": False,
            "reason": "commitment_not_found",
        }

    normalized_status = (
        new_status.strip().lower()
    )

    if (
        normalized_status
        not in VALID_COMMITMENT_STATUSES
    ):
        return {
            "success": False,
            "updated": False,
            "reason": "invalid_status",
        }

    current_status = existing.get(
        "status",
        "active",
    )

    if normalized_status == current_status:
        return {
            "success": True,
            "updated": False,
            "already_in_status": True,
            "commitment": existing,
        }

    allowed = ALLOWED_STATUS_TRANSITIONS.get(
        current_status,
        set(),
    )

    if normalized_status not in allowed:
        return {
            "success": False,
            "updated": False,
            "reason": "invalid_transition",
            "current_status": current_status,
            "requested_status": normalized_status,
        }

    timestamp = _now()

    updates = {
        "status": normalized_status,
        "updated_at": timestamp,
    }

    if user_decision is not None:
        updates["user_decision"] = (
            user_decision
        )
        updates["decision_at"] = timestamp

    if action_status is not None:
        updates["action_status"] = (
            action_status
        )

    update_document(
        COMMITMENT_COLLECTION,
        commitment_id,
        updates,
    )

    return {
        "success": True,
        "updated": True,
        "commitment": get_commitment(
            commitment_id
        ),
    }