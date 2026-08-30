import os
import time
from datetime import datetime

import requests

from my_agent.services.firestore_service import (
    get_firestore_client,
    set_document,
)
from my_agent.services.commitment_service import (
    COMMITMENT_COLLECTION,
    get_commitment,
)
from my_agent.services.stripe_connector import (
    get_subscription_status,
    schedule_cancel_at_period_end,
)
from my_agent.services.cancellation_followup_service import (
    confirm_cancellation_if_supported,
)


PRICE_ID = "price_1U9o74CvqN7hhJgojeGLvpry"

COMMITMENT_ID = (
    "subscription:h7-period-end-test-provider"
)

MERCHANT = "H7 Period End Test Provider"


def stripe_post(
    path: str,
    data: dict,
) -> dict:
    key = os.environ.get(
        "STRIPE_SECRET_KEY",
        "",
    ).strip()

    if not key.startswith("sk_test_"):
        raise RuntimeError(
            "Stripe TEST secret key is required."
        )

    response = requests.post(
        f"https://api.stripe.com{path}",
        auth=(key, ""),
        data=data,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def stripe_get(
    path: str,
) -> dict:
    key = os.environ.get(
        "STRIPE_SECRET_KEY",
        "",
    ).strip()

    response = requests.get(
        f"https://api.stripe.com{path}",
        auth=(key, ""),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def main() -> None:
    now_timestamp = int(time.time())

    # --------------------------------------------
    # 1. Create Stripe Test Clock
    # --------------------------------------------
    clock = stripe_post(
        "/v1/test_helpers/test_clocks",
        {
            "frozen_time": now_timestamp,
            "name": "Safe Signal H7 Period End Test",
        },
    )

    clock_id = clock["id"]

    print("1. test_clock_id =", clock_id)
    print("2. clock_status =", clock["status"])

    # --------------------------------------------
    # 2. Create customer attached to Test Clock
    # --------------------------------------------
    customer = stripe_post(
        "/v1/customers",
        {
            "name": "Safe Signal H7 Test User",
            "email": (
                "safesignal-h7@example.com"
            ),
            "test_clock": clock_id,
            "payment_method": "pm_card_visa",
            (
                "invoice_settings"
                "[default_payment_method]"
            ): "pm_card_visa",
        },
    )

    customer_id = customer["id"]

    print("3. customer_id =", customer_id)

    # --------------------------------------------
    # 3. Create real Stripe TEST subscription
    # --------------------------------------------
    subscription = stripe_post(
        "/v1/subscriptions",
        {
            "customer": customer_id,
            "items[0][price]": PRICE_ID,
        },
    )

    subscription_id = subscription["id"]

    print(
        "4. subscription_id =",
        subscription_id,
    )

    print(
        "5. initial_status =",
        subscription["status"],
    )

    # --------------------------------------------
    # 4. Schedule cancel at end of billing period
    #    through Safe Signal connector
    # --------------------------------------------
    cancel_result = (
        schedule_cancel_at_period_end(
            subscription_id
        )
    )

    print(
        "6. cancel_success =",
        cancel_result.get("success"),
    )

    print(
        "7. cancel_at_period_end =",
        cancel_result.get(
            "cancel_at_period_end"
        ),
    )

    effective_at = cancel_result.get(
        "cancellation_effective_at"
    )

    print(
        "8. cancellation_effective_at =",
        effective_at,
    )

    if not effective_at:
        raise RuntimeError(
            "Missing cancellation effective date."
        )

    # --------------------------------------------
    # 5. Create Safe Signal commitment
    # --------------------------------------------
    set_document(
        COMMITMENT_COLLECTION,
        COMMITMENT_ID,
        {
            "commitment_id": COMMITMENT_ID,
            "provider": MERCHANT,
            "commitment_type": "subscription",
            "status": "cancellation_requested",
            "expected_amount": 29.99,
            "last_observed_amount": 29.99,
            "currency": "CAD",
            "frequency": "monthly",
            "user_decision": "cancel",
            "decision_at": (
                datetime.now().astimezone().isoformat()
            ),
            "action_status": "executed",
            "provider_connector": "stripe",
            "provider_subscription_id": (
                subscription_id
            ),
            "provider_cancellation_scheduled": (
                True
            ),
            "cancel_at_period_end": True,
            "cancellation_effective_at": (
                effective_at
            ),
        },
    )

    # --------------------------------------------
    # 6. Verify BEFORE period end.
    #    Must NOT mark inactive.
    # --------------------------------------------
    before = (
        confirm_cancellation_if_supported(
            COMMITMENT_ID,
            datetime.now().date().isoformat(),
        )
    )

    print(
        "9. before_updated =",
        before.get("updated"),
    )

    print(
        "10. before_reason =",
        before.get(
            "evaluation",
            {},
        ).get("reason"),
    )

    # --------------------------------------------
    # 7. Advance Stripe Test Clock past
    #    cancellation effective time.
    # --------------------------------------------
    effective_timestamp = int(
        datetime.fromisoformat(
            effective_at
        ).timestamp()
    )

    target_timestamp = (
        effective_timestamp + 120
    )

    stripe_post(
        (
            f"/v1/test_helpers/test_clocks/"
            f"{clock_id}/advance"
        ),
        {
            "frozen_time": target_timestamp,
        },
    )

    print("11. clock_advance_started=True")

    # Stripe clock advances asynchronously.
    for _ in range(40):
        current_clock = stripe_get(
            (
                "/v1/test_helpers/test_clocks/"
                f"{clock_id}"
            )
        )

        if current_clock.get("status") == "ready":
            break

        time.sleep(2)
    else:
        raise RuntimeError(
            "Stripe Test Clock did not become ready."
        )

    print("12. clock_status_after=ready")

    # --------------------------------------------
    # 8. Wait briefly for subscription state
    #    propagation and read provider.
    # --------------------------------------------
    stripe_state = None

    for _ in range(15):
        stripe_state = (
            get_subscription_status(
                subscription_id
            )
        )

        if (
            stripe_state.get(
                "provider_status"
            )
            == "canceled"
            or stripe_state.get("ended_at")
        ):
            break

        time.sleep(2)

    print(
        "13. stripe_status_after =",
        stripe_state.get(
            "provider_status"
        ),
    )

    print(
        "14. stripe_ended_at =",
        stripe_state.get("ended_at"),
    )

    # --------------------------------------------
    # 9. Let Safe Signal verify provider result.
    # --------------------------------------------
    after = (
        confirm_cancellation_if_supported(
            COMMITMENT_ID,
            datetime.now().date().isoformat(),
        )
    )

    commitment = get_commitment(
        COMMITMENT_ID
    )

    print(
        "15. after_updated =",
        after.get("updated"),
    )

    print(
        "16. verification_method =",
        after.get(
            "verification_method"
        ),
    )

    print(
        "17. commitment_status =",
        commitment.get("status"),
    )

    print(
        "18. action_status =",
        commitment.get(
            "action_status"
        ),
    )

    print(
        "19. provider_confirmed =",
        commitment.get(
            "provider_cancellation_confirmed"
        ),
    )

    h7_pass = all(
        [
            before.get("updated") is False,

            before.get(
                "evaluation",
                {},
            ).get("reason")
            == "provider_cancellation_scheduled",

            stripe_state.get(
                "provider_status"
            )
            == "canceled"
            or bool(
                stripe_state.get("ended_at")
            ),

            after.get("updated") is True,

            after.get(
                "verification_method"
            )
            == "stripe_provider_api",

            commitment.get("status")
            == "inactive",

            commitment.get(
                "action_status"
            )
            == "cancellation_confirmed",

            commitment.get(
                "provider_cancellation_confirmed"
            )
            is True,
        ]
    )

    print()
    print("H7_PROVIDER_E2E_PASS =", h7_pass)

    # Keep Stripe sandbox objects so they can be
    # inspected in Stripe Dashboard as demo evidence.
    #
    # Only remove Safe Signal TEST commitment.
    get_firestore_client().collection(
        COMMITMENT_COLLECTION
    ).document(
        COMMITMENT_ID
    ).delete()

    print("firestore_cleanup=True")
    print(
        "stripe_test_clock_kept_for_demo =",
        clock_id,
    )


if __name__ == "__main__":
    main()
    