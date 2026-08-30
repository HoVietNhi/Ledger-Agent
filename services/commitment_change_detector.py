from datetime import date
from typing import Any


def calculate_commitment_impact(
    amount_difference: float,
    frequency: str | None,
) -> dict[str, float | None]:
    """
    Convert one recurring amount change into monthly
    and annual financial impact.
    """
    frequency_value = (
        frequency.strip().lower()
        if frequency
        else None
    )

    if frequency_value == "monthly":
        monthly_impact = round(
            amount_difference,
            2,
        )
        annual_impact = round(
            amount_difference * 12,
            2,
        )

    elif frequency_value in (
        "annual",
        "annually",
        "yearly",
    ):
        annual_impact = round(
            amount_difference,
            2,
        )
        monthly_impact = round(
            amount_difference / 12,
            2,
        )

    elif frequency_value == "weekly":
        annual_impact = round(
            amount_difference * 52,
            2,
        )
        monthly_impact = round(
            annual_impact / 12,
            2,
        )

    else:
        monthly_impact = None
        annual_impact = None

    return {
        "monthly_impact": monthly_impact,
        "annual_impact": annual_impact,
    }


def analyze_commitment_change(
    commitment: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare remembered expected state with the latest
    observed state.

    This function does not modify Firestore.
    """
    expected_amount = commitment.get(
        "expected_amount"
    )

    observed_amount = commitment.get(
        "last_observed_amount"
    )

    base_result = {
        "commitment_id": commitment.get(
            "commitment_id"
        ),
        "provider": commitment.get(
            "provider"
        ),
        "commitment_type": commitment.get(
            "commitment_type"
        ),
        "currency": commitment.get(
            "currency"
        ),
        "frequency": commitment.get(
            "frequency"
        ),
        "expected_amount": expected_amount,
        "observed_amount": observed_amount,
        "observed_date": commitment.get(
            "last_charge_date"
        ),
    }

    if (
        expected_amount is None
        or observed_amount is None
    ):
        return {
            **base_result,
            "meaningful": False,
            "change_type": "unknown",
            "reason": "missing_amount",
            "absolute_change": None,
            "percentage_change": None,
            "monthly_impact": None,
            "annual_impact": None,
        }

    expected_amount = float(
        expected_amount
    )
    observed_amount = float(
        observed_amount
    )

    difference = round(
        observed_amount - expected_amount,
        2,
    )

    if difference == 0:
        return {
            **base_result,
            "meaningful": False,
            "change_type": "no_change",
            "reason": "matches_expected_amount",
            "absolute_change": 0.0,
            "percentage_change": 0.0,
            "monthly_impact": 0.0,
            "annual_impact": 0.0,
        }

    if expected_amount != 0:
        percentage_change = round(
            (
                difference
                / expected_amount
            )
            * 100,
            2,
        )
    else:
        percentage_change = None

    impact = calculate_commitment_impact(
        difference,
        commitment.get("frequency"),
    )

    return {
        **base_result,
        "meaningful": True,
        "change_type": (
            "price_increase"
            if difference > 0
            else "price_decrease"
        ),
        "reason": "observed_amount_changed",
        "absolute_change": difference,
        "percentage_change": (
            percentage_change
        ),
        "monthly_impact": impact[
            "monthly_impact"
        ],
        "annual_impact": impact[
            "annual_impact"
        ],
    }

def analyze_commitment_timing(
    commitment: dict[str, Any],
    as_of_date: str,
    alert_window_days: int = 30,
) -> dict[str, Any]:
    """
    Detect an upcoming or overdue meaningful renewal/deadline.

    Date priority:
    1. renewal_date
    2. due_date
    3. next_expected_date

    Ordinary monthly recurring charges are not treated
    as renewal alerts.
    """
    renewal_date = commitment.get(
        "renewal_date"
    )

    due_date = commitment.get(
        "due_date"
    )

    next_expected_date = commitment.get(
        "next_expected_date"
    )

    if renewal_date:
        upcoming_date = renewal_date
        upcoming_date_type = "renewal_date"

    elif due_date:
        upcoming_date = due_date
        upcoming_date_type = "due_date"

    else:
        upcoming_date = next_expected_date
        upcoming_date_type = "next_expected_date"

    base_result = {
        "commitment_id": commitment.get(
            "commitment_id"
        ),
        "provider": commitment.get(
            "provider"
        ),
        "commitment_type": commitment.get(
            "commitment_type"
        ),
        "frequency": commitment.get(
            "frequency"
        ),

        "renewal_date": renewal_date,
        "due_date": due_date,
        "next_expected_date": next_expected_date,

        "upcoming_date": upcoming_date,
        "upcoming_date_type": upcoming_date_type,
    }

    if not upcoming_date:
        return {
            **base_result,
            "meaningful": False,
            "change_type": "no_upcoming_date",
            "days_until": None,
        }

    try:
        current_date = date.fromisoformat(
            as_of_date
        )

        expected_date = date.fromisoformat(
            upcoming_date
        )

    except ValueError:
        return {
            **base_result,
            "meaningful": False,
            "change_type": "invalid_date",
            "days_until": None,
        }

    days_until = (
        expected_date - current_date
    ).days

    frequency = (
        str(
            commitment.get("frequency")
            or ""
        )
        .strip()
        .lower()
    )

    commitment_type = (
        str(
            commitment.get(
                "commitment_type"
            )
            or ""
        )
        .strip()
        .lower()
    )

    is_renewal_commitment = (
        commitment_type == "renewal"
        or frequency in (
            "annual",
            "annually",
            "yearly",
        )
        or renewal_date is not None
    )

    if not is_renewal_commitment:
        return {
            **base_result,
            "meaningful": False,
            "change_type": "normal_recurring_timing",
            "days_until": days_until,
        }

    if days_until < 0:
        return {
            **base_result,
            "meaningful": True,
            "change_type": "renewal_overdue",
            "days_until": days_until,
        }

    if days_until <= alert_window_days:
        return {
            **base_result,
            "meaningful": True,
            "change_type": "upcoming_renewal",
            "days_until": days_until,
        }

    return {
        **base_result,
        "meaningful": False,
        "change_type": "renewal_not_due_yet",
        "days_until": days_until,
    }

def build_commitment_event_key(
    event: dict[str, Any],
) -> str:
    """
    Build a stable key for one meaningful commitment event.

    Repeated scans of the same financial change produce
    the same key, allowing notification deduplication.
    """
    if not event.get("meaningful"):
        return ""

    commitment_id = str(
        event.get("commitment_id")
        or ""
    ).strip()

    change_type = str(
        event.get("change_type")
        or ""
    ).strip()

    if not commitment_id or not change_type:
        return ""

    if change_type in (
        "price_increase",
        "price_decrease",
    ):
        expected = event.get(
            "expected_amount"
        )
        observed = event.get(
            "observed_amount"
        )

        return (
            f"{commitment_id}:"
            f"{change_type}:"
            f"{expected}:"
            f"{observed}"
        )

    if change_type == "charge_after_cancellation":
        last_charge_date = event.get(
            "last_charge_date"
        )

        observed_amount = event.get(
            "observed_amount"
        )

        return (
            f"{commitment_id}:"
            f"{change_type}:"
            f"{last_charge_date}:"
            f"{observed_amount}"
        )

    if change_type in (
        "upcoming_renewal",
        "renewal_overdue",
    ):
        renewal_date = (
            event.get("renewal_date")
            or event.get("due_date")
            or event.get("upcoming_date")
            or event.get("next_expected_date")
        )

        return (
            f"{commitment_id}:"
            f"{change_type}:"
            f"{renewal_date}"
        )

    return (
        f"{commitment_id}:"
        f"{change_type}"
    )