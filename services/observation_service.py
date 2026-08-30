from typing import Any
from .commitment_service import (
    build_commitment_id,
    find_matching_commitment,
)

def _normalize_commitment_type(
    category: str | None,
    renewal_date: str | None = None,
) -> str | None:
    normalized = (category or "").strip().lower()

    if normalized == "subscription":
        return "subscription"

    if normalized in {"bill", "billing"}:
        return "bill"

    if normalized == "renewal":
        return "renewal"

    if renewal_date:
        return "renewal"

    return None


def normalize_gmail_observation(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert structured Gmail classifier output into
    the common financial observation format.
    """
    if not analysis.get("is_financial"):
        return {
            "success": False,
            "reason": "not_financial",
        }

    provider = analysis.get("merchant")

    if not provider:
        return {
            "success": False,
            "reason": "missing_provider",
        }

    category = str(
        analysis.get("category") or ""
    ).strip().lower()

    commitment_type = _normalize_commitment_type(
        category,
        analysis.get("renewal_date"),
    )

    # A price-change email describes an event, not necessarily
    # the underlying commitment type. Reuse memory when known.
    if (
        commitment_type is None
        and category == "price_change"
    ):
        existing = find_matching_commitment(
            provider
        )

        if existing is not None:
            commitment_type = existing.get(
                "commitment_type"
            )

    if commitment_type is None:
        return {
            "success": False,
            "reason": "not_a_commitment",
        }

    new_amount = analysis.get("new_amount")
    amount = analysis.get("amount")

    observed_amount = (
        new_amount
        if new_amount is not None
        else amount
    )

    observation = {
        "source": "gmail",
        "source_id": analysis.get("source_id"),

        "provider": provider,
        "commitment_type": commitment_type,

        "observed_amount": observed_amount,
        "previous_amount": analysis.get("old_amount"),

        "currency": analysis.get("currency"),
        "frequency": analysis.get("billing_frequency"),

        "observed_at": analysis.get("received_at"),

        "renewal_date": analysis.get("renewal_date"),
        "due_date": analysis.get("due_date"),
        "effective_date": analysis.get("effective_date"),

        "change_type": analysis.get("change_type"),
        "product": analysis.get("product"),
        "confidence": analysis.get("confidence"),
    }

    return {
        "success": True,
        "observation": observation,
    }

def normalize_transaction_observation(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert structured transaction/subscription analysis
    into the common financial observation format.
    """
    if not analysis.get("is_subscription"):
        return {
            "success": False,
            "reason": "not_a_commitment",
        }

    provider = analysis.get("merchant")

    if not provider:
        return {
            "success": False,
            "reason": "missing_provider",
        }

    observation = {
        "source": "transaction",
        "source_id": None,

        "provider": provider,
        "commitment_type": "subscription",

        "observed_amount": analysis.get(
            "latest_amount"
        ),
        "previous_amount": analysis.get(
            "previous_amount"
        ),

        "currency": analysis.get("currency"),
        "frequency": analysis.get(
            "billing_frequency"
        ),

        "observed_at": analysis.get(
            "last_charge_date"
        ),

        "last_charge_date": analysis.get(
            "last_charge_date"
        ),
        "next_expected_date": analysis.get(
            "next_expected_date"
        ),

        "renewal_date": None,
        "due_date": None,
        "effective_date": None,

        "change_type": analysis.get(
            "change_type"
        ),

        "product": None,
        "confidence": analysis.get(
            "confidence"
        ),
    }

    return {
        "success": True,
        "observation": observation,
    }

def match_observation_to_commitment(
    observation: dict[str, Any],
) -> dict[str, Any]:
    """
    Match one normalized observation to an existing
    Financial Commitment Memory record.

    This function only matches existing commitments.
    It does not create new commitments.
    """
    provider = observation.get("provider")
    commitment_type = observation.get(
        "commitment_type"
    )

    if not provider:
        return {
            "success": False,
            "matched": False,
            "reason": "missing_provider",
        }

    if not commitment_type:
        return {
            "success": False,
            "matched": False,
            "reason": "missing_commitment_type",
        }

    commitment = find_matching_commitment(
        provider,
        commitment_type,
    )

    if commitment is None:
        return {
            "success": True,
            "matched": False,
            "reason": "commitment_not_found",
            "commitment": None,
        }

    return {
        "success": True,
        "matched": True,
        "commitment_id": commitment.get(
            "commitment_id"
        ),
        "commitment": commitment,
    }

def detect_new_commitment_candidate(
    observation: dict[str, Any],
    minimum_confidence: float = 0.80,
) -> dict[str, Any]:
    """
    Detect whether a normalized observation represents
    a new financial commitment not yet known in memory.

    This function creates a candidate only.
    It does not write to Firestore.
    """
    provider = observation.get("provider")
    commitment_type = observation.get(
        "commitment_type"
    )

    if not provider:
        return {
            "success": False,
            "is_candidate": False,
            "reason": "missing_provider",
        }

    if not commitment_type:
        return {
            "success": False,
            "is_candidate": False,
            "reason": "missing_commitment_type",
        }

    existing = find_matching_commitment(
        provider,
        commitment_type,
    )

    if existing is not None:
        return {
            "success": True,
            "is_candidate": False,
            "reason": "commitment_already_exists",
            "commitment_id": existing.get(
                "commitment_id"
            ),
        }

    confidence = observation.get("confidence")

    if confidence is None:
        confidence = 0.0

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < minimum_confidence:
        return {
            "success": True,
            "is_candidate": False,
            "reason": "insufficient_confidence",
            "confidence": confidence,
        }

    observed_amount = observation.get(
        "observed_amount"
    )

    candidate = {
        "commitment_id": build_commitment_id(
            provider,
            commitment_type,
        ),
        "provider": provider,
        "commitment_type": commitment_type,

        "expected_amount": observed_amount,
        "last_observed_amount": observed_amount,

        "currency": observation.get("currency"),
        "frequency": observation.get("frequency"),

        "last_charge_date": observation.get(
            "last_charge_date"
        ),
        "next_expected_date": observation.get(
            "next_expected_date"
        ),

        "renewal_date": observation.get(
            "renewal_date"
        ),
        "due_date": observation.get(
            "due_date"
        ),

        "source": observation.get("source"),
        "confidence": confidence,
    }

    return {
        "success": True,
        "is_candidate": True,
        "reason": "new_commitment_detected",
        "candidate": candidate,
    }