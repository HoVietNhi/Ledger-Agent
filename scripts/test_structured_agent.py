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


def fake_load_financial_emails() -> list:
    return [
        {
            "source": "gmail",
            "source_id": "structured_test_1",
            "is_financial": True,
            "category": "subscription",
            "change_type": "new_subscription",
            "sender": "Test Billing <billing@example.com>",
            "subject": "Your new plan",
            "merchant": "OpenAI",
            "product": "ChatGPT Plus",
            "amount": 25.0,
            "currency": "CAD",
            "old_amount": None,
            "new_amount": None,
            "absolute_change": None,
            "percentage_change": None,
            "monthly_impact": 25.0,
            "annual_impact": 300.0,
            "billing_frequency": "monthly",
            "renewal_date": "2026-09-24",
            "renewal_date_basis":
                "derived_from_order_date_and_first_month_free",
            "due_date": None,
            "effective_date": None,
            "received_at": "2026-08-26",
            "confidence": 0.95,
            "evidence": {
                "sender": "Test Billing <billing@example.com>",
                "subject": "Your new plan",
                "body_excerpt": "TEST EVIDENCE ONLY",
            },
        }
    ]


# Keep the real ADK tool name.
fake_load_financial_emails.__name__ = "load_financial_emails"

patched_email_tool = False


# Replace the exact function already registered in root_agent.
for index, tool in enumerate(root_agent.tools):
    tool_name = getattr(tool, "__name__", None)

    if tool_name == "load_financial_emails":
        root_agent.tools[index] = fake_load_financial_emails
        patched_email_tool = True


print(
    "PATCHED load_financial_emails:",
    patched_email_tool,
)


async def main():
    app_name = "structured_agent_test"
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
                    "Check my financial emails. "
                    "Use the structured financial event returned "
                    "by the tool as the source of truth. "
                    "Tell me the merchant, product, amount, "
                    "monthly impact, annual impact, renewal date, "
                    "and whether the renewal date is explicit "
                    "or derived. "
                    "Do not recalculate or invent missing data."
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