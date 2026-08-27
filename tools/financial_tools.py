import json
import os
import re

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from my_agent.services.financial_classifier import (
    classify_financial_email,
)

from my_agent.services.gmail_service import (
    get_unprocessed_emails,
    mark_message_processed,
)

from my_agent.services.firestore_service import (
    get_document,
    set_document,
)


STATE_COLLECTION = "financial_state"
STATE_DOCUMENT_ID = "current"

APP_TIMEZONE = ZoneInfo(
    os.getenv("LEDGER_TIMEZONE", "America/Toronto")
)


def _now() -> datetime:
    """
    Return the same timezone-aware time locally and on Cloud Run.
    """
    return datetime.now(APP_TIMEZONE)

def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate the percentage change between two financial values.

    Args:
        old_value (float): The original value.
        new_value (float): The new value.

    Returns:
        float: The percentage change from old_value to new_value.
    """
    if old_value == 0:
        return 0.0

    return round(((new_value - old_value) / old_value) * 100, 2)

def analyze_price_change(merchant: str, old_price: float, new_price: float, currency: str = "CAD",) -> dict:
    """
    Analyze the price change of a product and provide insights.

    Args:
        merchant (str): The name of the merchant.
        old_price (float): The original price of the product.
        new_price (float): The new price of the product.
        currency (str, optional): The currency of the prices. Defaults to "CAD".

    Returns:
        dict: A dictionary containing the analysis results.
    """
    percentage_change = calculate_percentage_change(old_price, new_price)

    if percentage_change > 0:
        change_type = "increase"
    elif percentage_change < 0:
        change_type = "decrease"
    else:
        change_type = "no change"

    timestamp = _now().isoformat()

    analysis = {
        "merchant": merchant,
        "old_price": old_price,
        "new_price": new_price,
        "currency": currency,
        "percentage_change": percentage_change,
        "change_type": change_type,
        "detected_at": timestamp,
        "alert": (
            f"{merchant} changed from {currency} {old_price:.2f}"
            f" to {currency} {new_price:.2f} "
            f" ({percentage_change:.2f}% {change_type})"
        ),
    }

    return analysis

## Tools for transaction analysis

def analyze_transaction(merchant: str, amount: float, currency: str = "CAD", transaction_type: str = "purchase",) -> dict:
    """
    Analyze a financial transaction and provide insights.

    Args:
        merchant (str): The name of the merchant.
        amount (float): The amount of the transaction.
        currency (str, optional): The currency of the transaction. Defaults to "CAD".
        transaction_type (str, optional): The type of transaction (e.g., "purchase", "refund"). Defaults to "purchase".

    Returns:
        dict: A dictionary containing the analysis results.
    """
    timestamp = _now().isoformat()

    analysis = {
        "merchant": merchant,
        "amount": amount,
        "currency": currency,
        "transaction_type": transaction_type,
        "detected_at": timestamp,
        "status": "recorded",
    }

    return analysis

def load_transactions() -> list:
    """
    Load transactions from a JSON file.

    Returns:
        list: A list of transactions.
    """
    path = Path(__file__).parent.parent / "data" / "transactions.json"
    if not path.exists():
        return []

    with open(path, 'r',  encoding="utf-8") as file:
        transactions = json.load(file)

    return transactions

def load_financial_emails() -> list:
    """
    Load unprocessed Gmail messages, classify them,
    and return normalized financial events.
    """
    emails = get_unprocessed_emails(max_results=50)

    financial_events = []

    for email in emails:
        event = classify_financial_email(email)

        if not event.get("is_financial"):
            continue

        financial_events.append(event)

        # Preserve existing Gmail dedupe behavior.
        mark_message_processed(email)

    return financial_events

def scan_financial_data() -> dict:
    """
    Scan financial data for significant changes and provide insights.

    Returns:
        dict: A dictionary containing the analysis results.
    """
    transactions = load_transactions()
    emails = load_financial_emails()

    previous_state = load_state()

    current_state = {
        "emails": emails,
        "transactions": transactions,
    }

    changes = detect_changes(previous_state, current_state)
    save_state(emails, transactions)

    return changes

def load_state() -> dict:
    """
    Load the previous financial state from Firestore.

    Returns:
        dict: The previously stored financial state.
    """

    state = get_document(
        STATE_COLLECTION,
        STATE_DOCUMENT_ID,
    )

    if state is None:
        return {
            "emails": [],
            "transactions": [],
        }

    return {
        "emails": state.get("emails", []),
        "transactions": state.get(
            "transactions",
            [],
        ),
    }

def save_state(emails: list, transactions: list) -> None:
    """
    Save the current financial state to a Firestore.

    Args:
        emails (list): The list of financial emails.
        transactions (list): The list of financial transactions.
    """
    state = {
        "emails": emails,
        "transactions": transactions,
        "schema_version": 1,
        "updated_at": _now().isoformat(),
        "storage": "firestore",
    }

    set_document(
        STATE_COLLECTION,
        STATE_DOCUMENT_ID,
        state,
    )

def detect_changes(previous_state: dict, current_state: dict) -> dict:
    """
    Detect changes between the previous and current financial state.

    Args:
        previous_state (dict): The previously stored financial state.
        current_state (dict): The current financial state.

    Returns:
        dict: A dictionary containing detected changes.
    """
    previous_emails = previous_state.get("emails", [])
    current_emails = current_state.get("emails", [])

    previous_transactions = previous_state.get("transactions", [])
    current_transactions = current_state.get("transactions", [])

    changes = {
        "new_emails": [],
        "new_transactions": [],
        "changed_transactions": [],
    }

    # Detect new emails
    for email in current_emails:
        if email not in previous_emails:
            changes["new_emails"].append(email)

    # Detect new transactions
    for transaction in current_transactions:
        if transaction not in previous_transactions:
            changes["new_transactions"].append(transaction)

        # Detect recurring subscription price changes
    #
    # We compare the latest subscription price for each merchant
    # between the previous state and the current state.
    #
    # Important:
    # - Date is used for ordering, not as the identity of a transaction.
    # - If multiple transactions have the same date, the later one
    #   in the file wins.
    # - This allows price changes to be detected even when the old
    #   and new transactions have the same date.

    def get_latest_subscription_by_merchant(transactions: list) -> dict:
        latest = {}

        for index, transaction in enumerate(transactions):
            if transaction.get("type") != "subscription":
                continue

            merchant = transaction.get("merchant")
            date = transaction.get("date", "")

            if not merchant:
                continue

            candidate = (date, index, transaction)

            if merchant not in latest:
                latest[merchant] = candidate
                continue

            current = latest[merchant]

            # Compare date first.
            # If dates are identical, use file order as tie-breaker.
            if candidate[0] > current[0] or (
                candidate[0] == current[0]
                and candidate[1] > current[1]
            ):
                latest[merchant] = candidate

        return {
            merchant: transaction
            for merchant, (_, _, transaction) in latest.items()
        }

    previous_latest = get_latest_subscription_by_merchant(
        previous_transactions
    )

    current_latest = get_latest_subscription_by_merchant(
        current_transactions
    )

    # Compare latest subscription prices
    for merchant, current_transaction in current_latest.items():

        if merchant not in previous_latest:
            continue

        previous_transaction = previous_latest[merchant]

        previous_amount = previous_transaction.get("amount")
        current_amount = current_transaction.get("amount")

        if previous_amount is None or current_amount is None:
            continue

        if previous_amount == current_amount:
            continue

        difference = round(current_amount - previous_amount, 2)

        changes["changed_transactions"].append({
            "merchant": merchant,
            "old_amount": previous_amount,
            "new_amount": current_amount,
            "currency": current_transaction.get("currency"),
            "date": current_transaction.get("date"),
            "change_type": (
                "price_increase"
                if difference > 0
                else "price_decrease"
            ),
            "monthly_difference": difference,
            "annual_difference": round(difference * 12, 2),
        })

    return changes