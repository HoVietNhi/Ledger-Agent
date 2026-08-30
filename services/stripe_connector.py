import os
from datetime import datetime, timezone
from typing import Any

import stripe


def _configure_stripe() -> None:
    """
    Configure Stripe using TEST MODE credentials only.
    """
    api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not configured."
        )

    if not api_key.startswith("sk_test_"):
        raise RuntimeError(
            "Safe Signal only allows Stripe TEST MODE "
            "for this hackathon integration."
        )

    stripe.api_key = api_key
    stripe.max_network_retries = 2


def _unix_to_iso(
    timestamp: int | None,
) -> str | None:
    if not timestamp:
        return None

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def _get_period_end(
    subscription: Any,
) -> int | None:
    """
    Return the latest current_period_end from a Stripe
    subscription response.

    Stripe SDK v15 StripeObject is not a normal dict,
    so convert it before using dict methods.
    """
    direct = getattr(
        subscription,
        "current_period_end",
        None,
    )

    if direct:
        return int(direct)

    data = subscription.to_dict()

    items = data.get("items") or {}
    item_data = items.get("data") or []

    period_ends = [
        item.get("current_period_end")
        for item in item_data
        if item.get("current_period_end")
    ]

    if period_ends:
        return int(max(period_ends))

    return None


def get_subscription_status(
    subscription_id: str,
) -> dict[str, Any]:
    """
    Read current Stripe TEST subscription state.
    """
    try:
        _configure_stripe()

        subscription = stripe.Subscription.retrieve(
            subscription_id
        )

        period_end = _get_period_end(
            subscription
        )

        return {
            "success": True,
            "provider_connector": "stripe",
            "execution_mode": "provider_api_test",
            "simulated": False,
            "subscription_id": subscription.id,
            "provider_status": subscription.status,
            "cancel_at_period_end": bool(
                subscription.cancel_at_period_end
            ),
            "current_period_end": (
                _unix_to_iso(period_end)
            ),
            "canceled_at": _unix_to_iso(
                subscription.canceled_at
            ),
            "ended_at": _unix_to_iso(
                subscription.ended_at
            ),
            "livemode": bool(
                subscription.livemode
            ),
        }

    except stripe.StripeError as exc:
        return {
            "success": False,
            "provider_connector": "stripe",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def schedule_cancel_at_period_end(
    subscription_id: str,
) -> dict[str, Any]:
    """
    Schedule a Stripe TEST subscription to cancel at
    the end of its current billing period.
    """
    try:
        _configure_stripe()

        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        )

        period_end = _get_period_end(
            subscription
        )

        return {
            "success": True,
            "provider_connector": "stripe",
            "execution_mode": "provider_api_test",
            "simulated": False,
            "subscription_id": subscription.id,
            "provider_status": subscription.status,
            "cancel_at_period_end": bool(
                subscription.cancel_at_period_end
            ),
            "cancellation_effective_at": (
                _unix_to_iso(period_end)
            ),
            "livemode": bool(
                subscription.livemode
            ),
        }

    except stripe.StripeError as exc:
        return {
            "success": False,
            "provider_connector": "stripe",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }