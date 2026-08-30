from datetime import date, datetime, timedelta, timezone
from typing import Any

from my_agent.services.commitment_service import (
    COMMITMENT_COLLECTION,
    get_commitment,
    update_commitment_status,
)

from my_agent.services.firestore_service import (
    update_document,
)

from my_agent.services.stripe_connector import (
    get_subscription_status,
)


def _to_date(value: str | None) -> date | None:
    """
    Convert an ISO date or datetime string to a date.
    """
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _now_iso() -> str:
    """
    Return a UTC timestamp for provider verification evidence.
    """
    return datetime.now(timezone.utc).isoformat()


def detect_charge_after_cancellation(
    commitment: dict[str, Any],
) -> dict[str, Any]:
    """
    Detect a charge that happened after the user requested
    cancellation.
    """
    commitment_id = commitment.get(
        "commitment_id"
    )

    if (
        commitment.get("status")
        != "cancellation_requested"
    ):
        return {
            "commitment_id": commitment_id,
            "meaningful": False,
            "reason": "not_cancellation_requested",
        }

    decision_date = _to_date(
        commitment.get("decision_at")
    )

    last_charge_date = _to_date(
        commitment.get("last_charge_date")
    )

    if decision_date is None:
        return {
            "commitment_id": commitment_id,
            "meaningful": False,
            "reason": "missing_cancellation_decision_date",
        }

    if (
        last_charge_date is None
        or last_charge_date <= decision_date
    ):
        return {
            "commitment_id": commitment_id,
            "meaningful": False,
            "reason": "no_charge_after_cancellation",
        }

    return {
        "commitment_id": commitment_id,
        "provider": commitment.get("provider"),
        "meaningful": True,
        "change_type": "charge_after_cancellation",
        "reason": "charge_after_cancellation_request",
        "expected_amount": commitment.get(
            "expected_amount"
        ),
        "observed_amount": commitment.get(
            "last_observed_amount"
        ),
        "currency": commitment.get("currency"),
        "last_charge_date": (
            last_charge_date.isoformat()
        ),
        "decision_at": commitment.get(
            "decision_at"
        ),
    }


def evaluate_stripe_cancellation_verification(
    commitment: dict[str, Any],
) -> dict[str, Any]:
    """
    Verify cancellation directly against Stripe TEST API.

    cancel_at_period_end=True means cancellation has been
    scheduled but the subscription has not ended yet.

    A Stripe status of "canceled" or a provider ended_at
    timestamp is treated as direct provider evidence that
    the subscription has ended.
    """
    commitment_id = commitment.get(
        "commitment_id"
    )

    if (
        commitment.get("provider_connector")
        != "stripe"
    ):
        return {
            "commitment_id": commitment_id,
            "supported": False,
            "confirmed": False,
            "reason": "not_stripe_connected",
        }

    subscription_id = commitment.get(
        "provider_subscription_id"
    )

    if not subscription_id:
        return {
            "commitment_id": commitment_id,
            "supported": True,
            "confirmed": False,
            "reason": "missing_provider_subscription_id",
        }

    provider_result = get_subscription_status(
        subscription_id
    )

    if not provider_result.get("success"):
        return {
            "commitment_id": commitment_id,
            "supported": True,
            "confirmed": False,
            "reason": "provider_check_failed",
            "provider_result": provider_result,
        }

    provider_status = str(
        provider_result.get(
            "provider_status",
            "",
        )
    ).lower()

    ended_at = provider_result.get(
        "ended_at"
    )

    if (
        provider_status == "canceled"
        or ended_at
    ):
        return {
            "commitment_id": commitment_id,
            "supported": True,
            "confirmed": True,
            "reason": "provider_reports_canceled",
            "provider_result": provider_result,
        }

    if provider_result.get(
        "cancel_at_period_end"
    ):
        return {
            "commitment_id": commitment_id,
            "supported": True,
            "confirmed": False,
            "reason": "provider_cancellation_scheduled",
            "cancellation_effective_at": (
                provider_result.get(
                    "current_period_end"
                )
            ),
            "provider_result": provider_result,
        }

    return {
        "commitment_id": commitment_id,
        "supported": True,
        "confirmed": False,
        "reason": "provider_not_canceled",
        "provider_result": provider_result,
    }


def evaluate_cancellation_verification(
    commitment: dict[str, Any],
    as_of_date: str,
    grace_days: int = 3,
) -> dict[str, Any]:
    """
    Fallback verification for commitments without a direct
    provider connector.

    Confirmation requires:
    - cancellation_requested
    - expected next charge date passed
    - grace period passed
    - no later charge observed
    """
    commitment_id = commitment.get(
        "commitment_id"
    )

    if (
        commitment.get("status")
        != "cancellation_requested"
    ):
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "not_cancellation_requested",
        }

    current_date = _to_date(
        as_of_date
    )

    next_expected_date = _to_date(
        commitment.get("next_expected_date")
    )

    decision_date = _to_date(
        commitment.get("decision_at")
    )

    last_charge_date = _to_date(
        commitment.get("last_charge_date")
    )

    if current_date is None:
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "invalid_as_of_date",
        }

    if next_expected_date is None:
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "missing_next_expected_date",
        }

    if decision_date is None:
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "missing_cancellation_decision_date",
        }

    if (
        last_charge_date is not None
        and last_charge_date > decision_date
    ):
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "charge_after_cancellation_request",
            "last_charge_date": (
                last_charge_date.isoformat()
            ),
        }

    verification_date = (
        next_expected_date
        + timedelta(days=grace_days)
    )

    if current_date < verification_date:
        return {
            "commitment_id": commitment_id,
            "confirmed": False,
            "reason": "waiting_for_evidence",
            "verification_date": (
                verification_date.isoformat()
            ),
        }

    return {
        "commitment_id": commitment_id,
        "confirmed": True,
        "reason": "expected_charge_did_not_arrive",
        "verification_date": (
            verification_date.isoformat()
        ),
    }


def confirm_cancellation_if_supported(
    commitment_id: str,
    as_of_date: str,
    grace_days: int = 3,
) -> dict[str, Any]:
    """
    Verify cancellation using the strongest available evidence.

    Stripe-connected commitment:
        query Stripe directly.

    Other commitment:
        use monitoring/no-later-charge evidence.
    """
    commitment = get_commitment(
        commitment_id
    )

    if commitment is None:
        return {
            "success": False,
            "updated": False,
            "reason": "commitment_not_found",
        }

    #
    # DIRECT STRIPE PROVIDER VERIFICATION
    #
    if (
        commitment.get("provider_connector")
        == "stripe"
    ):
        evaluation = (
            evaluate_stripe_cancellation_verification(
                commitment
            )
        )

        provider_result = (
            evaluation.get("provider_result")
            or {}
        )

        if provider_result.get("success"):
            sync_time = _now_iso()

            update_document(
                COMMITMENT_COLLECTION,
                commitment_id,
                {
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
                            "current_period_end"
                        )
                    ),
                    "provider_canceled_at": (
                        provider_result.get(
                            "canceled_at"
                        )
                    ),
                    "provider_ended_at": (
                        provider_result.get(
                            "ended_at"
                        )
                    ),
                    "last_provider_sync_at": (
                        sync_time
                    ),
                },
            )

        if not evaluation.get("confirmed"):
            return {
                "success": True,
                "updated": False,
                "verification_method": (
                    "stripe_provider_api"
                ),
                "evaluation": evaluation,
                "commitment": get_commitment(
                    commitment_id
                ),
            }

        confirmation_time = _now_iso()

        update_result = update_commitment_status(
            commitment_id,
            "inactive",
            action_status="cancellation_confirmed",
        )

        update_document(
            COMMITMENT_COLLECTION,
            commitment_id,
            {
                "cancellation_verification_method": (
                    "stripe_provider_api"
                ),
                "provider_confirmation_at": (
                    confirmation_time
                ),
                "provider_cancellation_confirmed": (
                    True
                ),
            },
        )

        return {
            "success": True,
            "updated": True,
            "verification_method": (
                "stripe_provider_api"
            ),
            "evaluation": evaluation,
            "commitment": get_commitment(
                commitment_id
            ),
        }

    #
    # FALLBACK MONITORING VERIFICATION
    #
    evaluation = evaluate_cancellation_verification(
        commitment,
        as_of_date,
        grace_days,
    )

    if not evaluation.get("confirmed"):
        return {
            "success": True,
            "updated": False,
            "verification_method": (
                "monitoring_evidence"
            ),
            "evaluation": evaluation,
            "commitment": commitment,
        }

    update_result = update_commitment_status(
        commitment_id,
        "inactive",
        action_status="cancellation_confirmed",
    )

    update_document(
        COMMITMENT_COLLECTION,
        commitment_id,
        {
            "cancellation_verification_method": (
                "no_later_charge"
            ),
            "provider_cancellation_confirmed": (
                False
            ),
        },
    )

    return {
        "success": True,
        "updated": True,
        "verification_method": (
            "monitoring_evidence"
        ),
        "evaluation": evaluation,
        "commitment": get_commitment(
            commitment_id
        ),
    }