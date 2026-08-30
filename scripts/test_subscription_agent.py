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


def fake_scan_financial_data() -> dict:
    """
    Controlled scan result for structured subscription testing.
    """
    return {
        "new_emails": [],
        "new_transactions": [],
        "changed_transactions": [],
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


def fake_load_transactions() -> list:
    """
    Return no raw transaction history.

    This proves that the agent must use the structured
    subscriptions field rather than independently calculating
    subscription information from raw transactions.
    """
    return []


# IMPORTANT:
# Preserve the original ADK tool names.
fake_scan_financial_data.__name__ = "scan_financial_data"
fake_load_transactions.__name__ = "load_transactions"


patched_scan = False
patched_transactions = False


# root_agent.tools contains direct Python function references.
# Replace those registered references with controlled test functions.
for index, tool in enumerate(root_agent.tools):
    tool_name = getattr(tool, "__name__", None)

    if tool_name == "scan_financial_data":
        root_agent.tools[index] = fake_scan_financial_data
        patched_scan = True

    elif tool_name == "load_transactions":
        root_agent.tools[index] = fake_load_transactions
        patched_transactions = True


print("PATCHED scan_financial_data:", patched_scan)
print("PATCHED load_transactions:", patched_transactions)


async def main():
    app_name = "subscription_agent_test"
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
                    "Call scan_financial_data. "
                    "Use the structured subscriptions field as the "
                    "source of truth. "
                    "Tell me whether Netflix is a subscription, "
                    "its billing frequency, previous amount, latest "
                    "amount, percentage change, monthly impact, "
                    "annual impact, next expected charge date, "
                    "and confidence. "
                    "Do not calculate values from raw transactions. "
                    "Do not create notifications or actions."
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


if __name__ == "__main__":
    asyncio.run(main())
