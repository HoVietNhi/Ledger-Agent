from my_agent.services.firestore_service import (
    get_document,
    get_firestore_client,
    set_document,
)
from my_agent.services.commitment_service import (
    COMMITMENT_COLLECTION,
)
from my_agent.services.stripe_connector import (
    get_subscription_status,
)
from my_agent.tools.action_tools import (
    COLLECTION_NAME,
    approve_financial_action,
    execute_financial_action,
    prepare_financial_action,
)


MERCHANT = "H3 Stripe Test Provider"
COMMITMENT_ID = "subscription:h3-stripe-test-provider"
SUBSCRIPTION_ID = "sub_1U9o75CvqN7hhJgo6rVGi4XX"


def main() -> None:
    action_id = None

    try:
        # --------------------------------------------------
        # 1. Create Safe Signal commitment connected
        #    to the real Stripe TEST subscription.
        # --------------------------------------------------
        set_document(
            COMMITMENT_COLLECTION,
            COMMITMENT_ID,
            {
                "commitment_id": COMMITMENT_ID,
                "provider": MERCHANT,
                "commitment_type": "subscription",
                "status": "active",
                "expected_amount": 29.99,
                "last_observed_amount": 29.99,
                "currency": "CAD",
                "frequency": "monthly",
                "user_decision": None,
                "action_status": None,
                "provider_connector": "stripe",
                "provider_subscription_id": SUBSCRIPTION_ID,
            },
        )

        print("1. commitment_created=True")

        # --------------------------------------------------
        # 2. Prepare
        # --------------------------------------------------
        prepared = prepare_financial_action(
            MERCHANT,
            "cancel_subscription",
            "H3 Stripe end-to-end cancellation test",
        )

        action_id = prepared["action_id"]

        print(
            "2. prepared_status=",
            prepared.get("status"),
        )

        # --------------------------------------------------
        # 3. Explicit approval
        # --------------------------------------------------
        approved = approve_financial_action(
            action_id
        )

        print(
            "3. approved_status=",
            approved.get("action", {}).get("status"),
        )

        # --------------------------------------------------
        # 4. Execute through action_tools.py
        #    This must automatically route to Stripe.
        # --------------------------------------------------
        executed = execute_financial_action(
            action_id
        )

        print(
            "4. execution_success=",
            executed.get("success"),
        )

        print(
            "5. execution_message=",
            executed.get("message"),
        )

        # --------------------------------------------------
        # 5. Read persisted Firestore evidence.
        # --------------------------------------------------
        stored_action = get_document(
            COLLECTION_NAME,
            action_id,
        )

        stored_commitment = get_document(
            COMMITMENT_COLLECTION,
            COMMITMENT_ID,
        )

        print(
            "6. action_status=",
            stored_action.get("status"),
        )

        print(
            "7. execution_mode=",
            stored_action.get("execution_mode"),
        )

        execution_result = (
            stored_action.get("execution_result")
            or {}
        )

        print(
            "8. simulated=",
            execution_result.get("simulated"),
        )

        print(
            "9. action_cancel_at_period_end=",
            execution_result.get(
                "cancel_at_period_end"
            ),
        )

        print(
            "10. commitment_status=",
            stored_commitment.get("status"),
        )

        print(
            "11. commitment_user_decision=",
            stored_commitment.get("user_decision"),
        )

        print(
            "12. provider_connector=",
            stored_commitment.get(
                "provider_connector"
            ),
        )

        print(
            "13. provider_cancellation_scheduled=",
            stored_commitment.get(
                "provider_cancellation_scheduled"
            ),
        )

        print(
            "14. cancellation_effective_at=",
            stored_commitment.get(
                "cancellation_effective_at"
            ),
        )

        # --------------------------------------------------
        # 6. Independently retrieve Stripe provider state.
        # --------------------------------------------------
        stripe_state = get_subscription_status(
            SUBSCRIPTION_ID
        )

        print(
            "15. stripe_success=",
            stripe_state.get("success"),
        )

        print(
            "16. stripe_status=",
            stripe_state.get("provider_status"),
        )

        print(
            "17. stripe_cancel_at_period_end=",
            stripe_state.get(
                "cancel_at_period_end"
            ),
        )

        print(
            "18. stripe_livemode=",
            stripe_state.get("livemode"),
        )

        # --------------------------------------------------
        # 7. Final assertions.
        # --------------------------------------------------
        h3_pass = all(
            [
                executed.get("success") is True,

                stored_action.get("status")
                == "executed",

                stored_action.get("execution_mode")
                == "provider_api_test",

                execution_result.get("simulated")
                is False,

                execution_result.get(
                    "cancel_at_period_end"
                )
                is True,

                stored_commitment.get("status")
                == "cancellation_requested",

                stored_commitment.get(
                    "provider_connector"
                )
                == "stripe",

                stored_commitment.get(
                    "provider_cancellation_scheduled"
                )
                is True,

                stripe_state.get("success")
                is True,

                stripe_state.get(
                    "cancel_at_period_end"
                )
                is True,

                stripe_state.get("livemode")
                is False,
            ]
        )

        print()
        print("H3_E2E_PASS =", h3_pass)

    finally:
        # Remove only Safe Signal TEST records.
        # Stripe sandbox subscription remains available
        # as external evidence.
        client = get_firestore_client()

        client.collection(
            COMMITMENT_COLLECTION
        ).document(
            COMMITMENT_ID
        ).delete()

        if action_id:
            client.collection(
                COLLECTION_NAME
            ).document(
                action_id
            ).delete()

        print("cleanup=True")


if __name__ == "__main__":
    main()