import asyncio

from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(
    BASE_DIR / ".env"
)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from my_agent.agent import root_agent


notification_calls = []


def fake_scan_financial_data() -> dict:
    return {
        "new_emails": [],
        "new_transactions": [],
        "changed_transactions": [
            {
                "merchant": "Netflix",
                "old_amount": 15.99,
                "new_amount": 22.99,
                "currency": "CAD",
                "date": "2026-08-21",
                "change_type": "price_increase",
                "monthly_difference": 7.0,
                "annual_difference": 84.0,
            }
        ],
        "subscriptions": [
            {
                "source": "transaction_history",
                "event_type": "subscription_price_change",
                "merchant": "Netflix",
                "is_subscription": True,
                "billing_frequency": "monthly",
                "confidence": 0.91,
                "currency": "CAD",
                "previous_amount": 15.99,
                "latest_amount": 22.99,
                "change_type": "price_increase",
                "absolute_change": 7.0,
                "percentage_change": 43.78,
                "monthly_impact": 7.0,
                "annual_impact": 84.0,
                "last_charge_date": "2026-08-21",
                "next_expected_date": "2026-09-21",
                "transaction_count": 3,
                "intervals_days": [30, 31],
            }
        ],
    }


def fake_create_financial_notification(
    title: str,
    message: str,
    priority: str,
    event_type: str,
    event_key: str = "",
    reminder_after_hours: int = 24,
) -> dict:

    call = {
        "title": title,
        "message": message,
        "priority": priority,
        "event_type": event_type,
        "event_key": event_key,
        "reminder_after_hours": reminder_after_hours,
    }

    notification_calls.append(call)

    return {
        "success": True,
        "created": True,
        "notification": {
            "notification_id": "test_notification_1",
            **call,
        },
    }


# Preserve ADK tool names.
fake_scan_financial_data.__name__ = "scan_financial_data"
fake_create_financial_notification.__name__ = (
    "create_financial_notification"
)


patched_scan = False
patched_notification = False


for index, tool in enumerate(root_agent.tools):
    tool_name = getattr(tool, "__name__", None)

    if tool_name == "scan_financial_data":
        root_agent.tools[index] = fake_scan_financial_data
        patched_scan = True

    elif tool_name == "create_financial_notification":
        root_agent.tools[index] = (
            fake_create_financial_notification
        )
        patched_notification = True


print("PATCHED scan:", patched_scan)
print("PATCHED notification:", patched_notification)


async def main():
    app_name = "subscription_notification_test"
    user_id = "test-user"
    session_id = "test-session"

    session_service = InMemorySessionService()

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    "Perform a financial scan and process newly "
                    "detected meaningful changes using your normal "
                    "notification workflow. Use structured "
                    "subscription analysis as context."
                )
            )
        ],
    )

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    print(part.text)

    print()
    print("=== NOTIFICATION TEST ===")
    print("CALL COUNT:", len(notification_calls))

    for call in notification_calls:
        print("TITLE:", call["title"])
        print("PRIORITY:", call["priority"])
        print("EVENT TYPE:", call["event_type"])
        print("EVENT KEY:", call["event_key"])
        print("MESSAGE:", call["message"])


if __name__ == "__main__":
    asyncio.run(main())