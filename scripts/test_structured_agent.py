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

import my_agent.tools.financial_tools as financial_tools


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


# Patch BEFORE importing the agent so the registered tool
# uses our controlled structured fixture.
financial_tools.load_financial_emails = fake_load_financial_emails

from my_agent.agent import root_agent


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
                    "by the tool and tell me the amount, monthly "
                    "impact, annual impact, renewal date, and "
                    "whether the renewal date is explicit or derived."
                )
            )
        ],
    )

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        if (
            event.content
            and event.content.parts
        ):
            for part in event.content.parts:
                if getattr(part, "text", None):
                    print(part.text)


if __name__ == "__main__":
    asyncio.run(main())