from typing import Any
from my_agent.services.commitment_change_detector import (
    analyze_commitment_change,
    analyze_commitment_timing,
)

from my_agent.services.cancellation_followup_service import (
    detect_charge_after_cancellation,
)

def decide_new_commitment_candidate(
    candidate_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Decide whether a newly detected commitment candidate
    deserves user review.

    Detection and decision are intentionally separated:
    D4 detects a candidate.
    E6 decides whether the candidate is meaningful.
    """
    if not candidate_result.get("success"):
        return {
            "meaningful": False,
            "decision": "silent",
            "reason": candidate_result.get(
                "reason",
                "candidate_detection_failed",
            ),
        }

    if not candidate_result.get("is_candidate"):
        return {
            "meaningful": False,
            "decision": "silent",
            "reason": candidate_result.get(
                "reason",
                "not_a_new_commitment",
            ),
        }

    candidate = (
        candidate_result.get("candidate")
        or {}
    )

    return {
        "meaningful": True,
        "decision": "review",
        "reason": "unexpected_recurring_commitment",
        "commitment_id": candidate.get(
            "commitment_id"
        ),
        "provider": candidate.get("provider"),
        "commitment_type": candidate.get(
            "commitment_type"
        ),
        "observed_amount": candidate.get(
            "last_observed_amount"
        ),
        "currency": candidate.get("currency"),
        "frequency": candidate.get("frequency"),
        "confidence": candidate.get("confidence"),
    }

def decide_priority(
    event: dict[str, Any],
) -> str:
    """
    Assign a deterministic alert priority.

    HIGH:
    - overdue renewal
    - renewal due within 7 days
    - large recurring impact >= 500/year

    MEDIUM:
    - meaningful price change
    - unexpected recurring commitment
    - upcoming renewal within alert window

    LOW:
    - informational / non-meaningful events
    """
    if not event.get("meaningful"):
        return "LOW"

    change_type = (
        str(event.get("change_type") or "")
        .strip()
        .lower()
    )

    reason = (
        str(event.get("reason") or "")
        .strip()
        .lower()
    )

    days_until = event.get("days_until")
    annual_impact = event.get("annual_impact")

    if change_type == "charge_after_cancellation":
        return "HIGH"

    if change_type == "renewal_overdue":
        return "HIGH"

    if (
        change_type == "upcoming_renewal"
        and days_until is not None
        and days_until <= 7
    ):
        return "HIGH"

    try:
        annual_impact_value = abs(
            float(annual_impact)
        )
    except (TypeError, ValueError):
        annual_impact_value = 0.0

    if annual_impact_value >= 500:
        return "HIGH"

    if reason == "unexpected_recurring_commitment":
        return "MEDIUM"

    if change_type in {
        "price_increase",
        "price_decrease",
        "upcoming_renewal",
    }:
        return "MEDIUM"

    return "MEDIUM"

def decide_commitment_attention(
    commitment: dict[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    """
    Decide whether an existing commitment needs attention.

    Amount changes take precedence over timing alerts.
    Otherwise normal observations stay silent.
    """
    cancellation_event = (
        detect_charge_after_cancellation(
            commitment
        )
    )

    if cancellation_event.get("meaningful"):
        return {
            **cancellation_event,
            "decision": "attention",
            "priority": decide_priority(
                cancellation_event
            ),
        }
    
    change = analyze_commitment_change(
        commitment
    )

    if change.get("meaningful"):
        return {
            **change,
            "decision": "attention",
            "priority": decide_priority(
                change
            ),
        }

    timing = analyze_commitment_timing(
        commitment,
        as_of_date=as_of_date,
    )

    if timing.get("meaningful"):
        return {
            **timing,
            "decision": "attention",
            "priority": decide_priority(
                timing
            ),
        }

    return {
        "commitment_id": commitment.get(
            "commitment_id"
        ),
        "meaningful": False,
        "decision": "silent",
        "change_type": change.get(
            "change_type",
            "no_change",
        ),
        "priority": "LOW",
    }