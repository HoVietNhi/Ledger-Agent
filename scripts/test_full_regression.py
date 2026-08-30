from my_agent.background_monitor import (
    create_notifications_for_decisions,
)

from my_agent.services.commitment_change_detector import (
    build_commitment_event_key,
)

from my_agent.services.commitment_service import (
    COMMITMENT_COLLECTION,
    get_commitment,
    update_commitment_expectation,
)

from my_agent.services.financial_classifier import (
    classify_financial_email,
)

from my_agent.services.firestore_service import (
    get_document,
    get_firestore_client,
    set_document,
    update_document,
)

from my_agent.services.meaningful_change_service import (
    decide_commitment_attention,
)

from my_agent.tools import (
    action_tools,
    notification_tools,
)


NETFLIX_ID = "subscription:j-regression-netflix"
NETFLIX_PROVIDER = "J Regression Netflix"

AS_OF_DATE = "2026-08-29"

results = {}
notification_ids = set()
action_id = None


def close_enough(
    value,
    expected,
    tolerance=0.001,
):
    if value is None:
        return False

    return abs(
        float(value) - float(expected)
    ) <= tolerance


def remember_notification_ids(
    notification_result: dict,
):
    for result in notification_result.get(
        "results",
        [],
    ):
        notification = (
            result.get("notification")
            or {}
        )

        notification_id = notification.get(
            "notification_id"
        )

        if notification_id:
            notification_ids.add(
                notification_id
            )


def main():
    global action_id

    try:
        # ==================================================
        # J1 — Normal recurring
        # expected == observed -> SILENT
        # ==================================================
        set_document(
            COMMITMENT_COLLECTION,
            NETFLIX_ID,
            {
                "commitment_id": NETFLIX_ID,
                "provider": NETFLIX_PROVIDER,
                "commitment_type": "subscription",
                "status": "active",
                "expected_amount": 22.99,
                "last_observed_amount": 22.99,
                "currency": "CAD",
                "frequency": "monthly",
                "last_charge_date": "2026-08-21",
                "next_expected_date": "2026-09-21",
            },
        )

        j1 = decide_commitment_attention(
            get_commitment(NETFLIX_ID),
            AS_OF_DATE,
        )

        j1_notifications = (
            create_notifications_for_decisions(
                [j1]
            )
        )

        results["J1"] = (
            j1.get("meaningful") is False
            and j1.get("decision") != "attention"
            and j1_notifications.get("created") == 0
        )

        # ==================================================
        # J2 — First price increase
        # 15.99 -> 22.99
        # +7/month, +84/year, ATTENTION
        # ==================================================
        update_document(
            COMMITMENT_COLLECTION,
            NETFLIX_ID,
            {
                "expected_amount": 15.99,
                "previous_amount": 15.99,
                "last_observed_amount": 22.99,
            },
        )

        j2 = decide_commitment_attention(
            get_commitment(NETFLIX_ID),
            AS_OF_DATE,
        )

        j2_event_key = (
            build_commitment_event_key(j2)
        )

        j2_notifications = (
            create_notifications_for_decisions(
                [j2]
            )
        )

        remember_notification_ids(
            j2_notifications
        )

        results["J2"] = all(
            [
                j2.get("meaningful") is True,
                j2.get("decision")
                == "attention",
                j2.get("change_type")
                == "price_increase",
                close_enough(
                    j2.get("monthly_impact"),
                    7.0,
                ),
                close_enough(
                    j2.get("annual_impact"),
                    84.0,
                ),
                j2_notifications.get(
                    "created"
                )
                == 1,
            ]
        )

        # ==================================================
        # J3 — User KEEP
        # Accept 22.99 as new baseline
        # ==================================================
        update_commitment_expectation(
            NETFLIX_ID,
            22.99,
            user_decision="keep",
        )

        after_keep = get_commitment(
            NETFLIX_ID
        )

        results["J3"] = all(
            [
                close_enough(
                    after_keep.get(
                        "expected_amount"
                    ),
                    22.99,
                ),
                after_keep.get(
                    "user_decision"
                )
                == "keep",
                bool(
                    after_keep.get(
                        "decision_at"
                    )
                ),
            ]
        )

        # ==================================================
        # J4 — Same amount after Keep
        # 22.99 -> SILENT
        # ==================================================
        update_document(
            COMMITMENT_COLLECTION,
            NETFLIX_ID,
            {
                "last_observed_amount": 22.99,
            },
        )

        j4 = decide_commitment_attention(
            get_commitment(NETFLIX_ID),
            AS_OF_DATE,
        )

        j4_notifications = (
            create_notifications_for_decisions(
                [j4]
            )
        )

        results["J4"] = (
            j4.get("meaningful") is False
            and j4.get("decision") != "attention"
            and j4_notifications.get("created") == 0
        )

        # ==================================================
        # J5 — Second increase
        # 22.99 -> 29.99
        # must become NEW meaningful event
        # ==================================================
        update_document(
            COMMITMENT_COLLECTION,
            NETFLIX_ID,
            {
                "previous_amount": 22.99,
                "last_observed_amount": 29.99,
            },
        )

        j5 = decide_commitment_attention(
            get_commitment(NETFLIX_ID),
            AS_OF_DATE,
        )

        j5_event_key = (
            build_commitment_event_key(j5)
        )

        results["J5"] = all(
            [
                j5.get("meaningful") is True,
                j5.get("decision")
                == "attention",
                j5.get("change_type")
                == "price_increase",
                j5_event_key != j2_event_key,
            ]
        )

        # ==================================================
        # J9 — Duplicate notification
        # Do here before cancellation changes commitment
        # ==================================================
        j9_first = (
            create_notifications_for_decisions(
                [j5]
            )
        )

        j9_second = (
            create_notifications_for_decisions(
                [j5]
            )
        )

        remember_notification_ids(j9_first)
        remember_notification_ids(j9_second)

        results["J9"] = (
            j9_first.get("created") == 1
            and j9_second.get("created") == 0
        )

        # ==================================================
        # J6 — Cancel -> Approve -> Execute
        # Unsupported provider uses safe simulated fallback
        # but commitment MUST enter cancellation_requested.
        # ==================================================
        prepared = (
            action_tools.prepare_financial_action(
                NETFLIX_PROVIDER,
                "cancel_subscription",
                "J6 regression cancellation test",
            )
        )

        action_id = prepared.get(
            "action_id"
        )

        approved = (
            action_tools.approve_financial_action(
                action_id
            )
        )

        executed = (
            action_tools.execute_financial_action(
                action_id
            )
        )

        stored_action = get_document(
            action_tools.COLLECTION_NAME,
            action_id,
        )

        canceled_commitment = (
            get_commitment(NETFLIX_ID)
        )

        results["J6"] = all(
            [
                prepared.get("status")
                == "pending_approval",
                approved.get("success")
                is True,
                executed.get("success")
                is True,
                stored_action.get("status")
                == "executed",
                canceled_commitment.get(
                    "status"
                )
                == "cancellation_requested",
                canceled_commitment.get(
                    "user_decision"
                )
                == "cancel",
            ]
        )

        # ==================================================
        # J7 — Charge after cancellation
        # must become HIGH attention event.
        # ==================================================
        update_document(
            COMMITMENT_COLLECTION,
            NETFLIX_ID,
            {
                "last_charge_date":
                    "2026-09-21",
                "last_observed_amount":
                    29.99,
            },
        )

        j7 = decide_commitment_attention(
            get_commitment(NETFLIX_ID),
            "2026-09-21",
        )

        j7_notifications = (
            create_notifications_for_decisions(
                [j7]
            )
        )

        remember_notification_ids(
            j7_notifications
        )

        results["J7"] = all(
            [
                j7.get("meaningful") is True,
                j7.get("decision")
                == "attention",
                j7.get("change_type")
                == "charge_after_cancellation",
                j7.get("priority")
                == "HIGH",
                j7_notifications.get(
                    "created"
                )
                == 1,
            ]
        )

        # ==================================================
        # J8 — Adobe annual renewal
        # CAD 599, Sep 4 -> meaningful / HIGH
        # ==================================================
        adobe = {
            "commitment_id":
                "renewal:j-regression-adobe",
            "provider":
                "J Regression Adobe",
            "commitment_type":
                "renewal",
            "status":
                "active",
            "expected_amount":
                599.0,
            "last_observed_amount":
                599.0,
            "currency":
                "CAD",
            "frequency":
                "annual",
            "renewal_date":
                "2026-09-04",
        }

        j8 = decide_commitment_attention(
            adobe,
            AS_OF_DATE,
        )

        j8_notifications = (
            create_notifications_for_decisions(
                [j8]
            )
        )

        remember_notification_ids(
            j8_notifications
        )

        results["J8"] = all(
            [
                j8.get("meaningful") is True,
                j8.get("decision")
                == "attention",
                j8.get("change_type")
                == "upcoming_renewal",
                j8.get("priority")
                == "HIGH",
                j8_notifications.get(
                    "created"
                )
                == 1,
            ]
        )

        # ==================================================
        # J10 — Non-financial Gmail ignored
        # ==================================================
        non_financial_email = {
            "id": "j10-test-email",
            "sender":
                "Devpost <updates@devpost.com>",
            "subject":
                "Hackathon project update",
            "body": (
                "Your hackathon submission page "
                "has new judging information and "
                "project comments."
            ),
            "received_at":
                "2026-08-29",
        }

        j10 = classify_financial_email(
            non_financial_email
        )

        results["J10"] = (
            j10.get("is_financial") is False
        )

        # ==================================================
        # REPORT
        # ==================================================
        print()
        print("=== J FULL REGRESSION ===")

        for number in range(1, 11):
            name = f"J{number}"

            print(
                name,
                "PASS"
                if results.get(name)
                else "FAIL",
            )

        print()

        all_pass = all(
            results.get(
                f"J{number}",
                False,
            )
            for number in range(1, 11)
        )

        print(
            "J_REGRESSION_PASS =",
            all_pass,
        )

    finally:
        # ==================================================
        # CLEANUP — TEST DATA ONLY
        # ==================================================
        client = get_firestore_client()

        client.collection(
            COMMITMENT_COLLECTION
        ).document(
            NETFLIX_ID
        ).delete()

        if action_id:
            client.collection(
                action_tools.COLLECTION_NAME
            ).document(
                action_id
            ).delete()

        notification_collection = getattr(
            notification_tools,
            "COLLECTION_NAME",
            "financial_notifications",
        )

        for notification_id in notification_ids:
            client.collection(
                notification_collection
            ).document(
                notification_id
            ).delete()

        print("TEST cleanup=True")


if __name__ == "__main__":
    main()