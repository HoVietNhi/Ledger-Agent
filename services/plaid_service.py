import os
from functools import lru_cache
from pathlib import Path

import plaid
from dotenv import load_dotenv
from plaid.api import plaid_api


ENV_FILE = (
    Path(__file__).resolve().parents[1]
    / ".env"
)

load_dotenv(
    dotenv_path=ENV_FILE,
)


def get_plaid_environment():
    """
    Resolve the configured Plaid environment.

    Supported:
    - sandbox
    - production
    """
    env = os.getenv(
        "PLAID_ENV",
        "sandbox",
    ).strip().lower()

    if env == "sandbox":
        return plaid.Environment.Sandbox

    if env == "production":
        return plaid.Environment.Production

    raise ValueError(
        f"Unsupported PLAID_ENV: {env}"
    )


def validate_plaid_configuration() -> dict:
    """
    Validate Plaid configuration without exposing secrets.
    """
    client_id = os.getenv(
        "PLAID_CLIENT_ID"
    )

    secret = os.getenv(
        "PLAID_SECRET"
    )

    env = os.getenv(
        "PLAID_ENV",
        "sandbox",
    ).strip().lower()

    return {
        "configured": bool(
            client_id
            and secret
            and env in {
                "sandbox",
                "production",
            }
        ),
        "client_id_set": bool(client_id),
        "secret_set": bool(secret),
        "environment": env,
    }


@lru_cache(maxsize=1)
def get_plaid_client():
    """
    Create and reuse one Plaid API client.

    Credentials remain backend-only and are never
    included in returned application data.
    """
    config = validate_plaid_configuration()

    if not config["configured"]:
        raise RuntimeError(
            "Plaid credentials are not configured."
        )

    configuration = plaid.Configuration(
        host=get_plaid_environment(),
        api_key={
            "clientId": os.environ[
                "PLAID_CLIENT_ID"
            ],
            "secret": os.environ[
                "PLAID_SECRET"
            ],
        },
    )

    api_client = plaid.ApiClient(
        configuration
    )

    return plaid_api.PlaidApi(
        api_client
    )



def fetch_plaid_transactions() -> list[dict]:
    """
    Fetch Plaid transactions and normalize them into
    Safe Signal's transaction-source format.

    Plaid credentials and access tokens remain backend-only.
    """
    from plaid.model.transactions_sync_request import (
        TransactionsSyncRequest,
    )

    access_token = os.getenv(
        "PLAID_ACCESS_TOKEN"
    )

    if not access_token:
        raise RuntimeError(
            "PLAID_ACCESS_TOKEN is not configured."
        )

    client = get_plaid_client()

    transactions = []
    cursor = None

    while True:
        request_kwargs = {
            "access_token": access_token,
        }

        if cursor:
            request_kwargs["cursor"] = cursor

        request = TransactionsSyncRequest(
            **request_kwargs
        )

        response = client.transactions_sync(
            request
        )

        data = (
            response.to_dict()
            if hasattr(response, "to_dict")
            else response
        )

        for transaction in data.get(
            "added",
            [],
        ):
            tx = (
                transaction.to_dict()
                if hasattr(transaction, "to_dict")
                else transaction
            )

            merchant = (
                tx.get("merchant_name")
                or tx.get("name")
                or "Unknown merchant"
            )

            amount = tx.get("amount")

            if amount is None:
                continue

            transaction_date = tx.get(
                "date"
            )

            if hasattr(
                transaction_date,
                "isoformat",
            ):
                transaction_date = (
                    transaction_date.isoformat()
                )

            personal_finance_category = (
                tx.get(
                    "personal_finance_category"
                )
                or {}
            )

            if hasattr(
                personal_finance_category,
                "to_dict",
            ):
                personal_finance_category = (
                    personal_finance_category.to_dict()
                )

            transactions.append(
                {
                    "merchant": str(
                        merchant
                    ).strip(),
                    "amount": float(amount),
                    "currency": (
                        tx.get(
                            "iso_currency_code"
                        )
                        or tx.get(
                            "unofficial_currency_code"
                        )
                    ),
                    "date": transaction_date,
                    "type": "bank_transaction",
                    "source": "plaid",
                    "plaid_primary_category": (
                        personal_finance_category.get(
                            "primary"
                        )
                    ),
                    "plaid_detailed_category": (
                        personal_finance_category.get(
                            "detailed"
                        )
                    ),
                    "plaid_transaction_id": (
                        tx.get(
                            "transaction_id"
                        )
                    ),
                }
            )

        if not data.get("has_more"):
            break

        cursor = data.get(
            "next_cursor"
        )

        if not cursor:
            break

    return transactions
