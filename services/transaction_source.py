import os
from typing import Any, Protocol

from my_agent.services.plaid_service import (
    fetch_plaid_transactions,
)
from my_agent.tools.financial_tools import (
    load_transactions,
)


class TransactionSource(Protocol):
    """
    Interface for transaction data sources.
    """

    source_name: str

    def fetch_transactions(
        self,
    ) -> list[dict[str, Any]]:
        ...


class LocalFixtureTransactionSource:
    """
    Local TEST/MVP transaction feed.

    This is not a live bank connection.
    """

    source_name = "local_fixture"

    def fetch_transactions(
        self,
    ) -> list[dict[str, Any]]:
        return load_transactions()


class PlaidTransactionSource:
    """
    Fetch normalized transactions from Plaid.

    Sandbox returns Plaid test data.
    Production can use real connected bank data.
    """

    source_name = "plaid"

    def fetch_transactions(
        self,
    ) -> list[dict[str, Any]]:
        return fetch_plaid_transactions()


def get_transaction_source() -> TransactionSource:
    """
    Select the configured transaction source.

    TRANSACTION_SOURCE:
    - local
    - plaid
    """
    source = os.getenv(
        "TRANSACTION_SOURCE",
        "local",
    ).strip().lower()

    if source in {
        "local",
        "local_fixture",
    }:
        return LocalFixtureTransactionSource()

    if source == "plaid":
        return PlaidTransactionSource()

    raise ValueError(
        f"Unsupported TRANSACTION_SOURCE: {source}"
    )
