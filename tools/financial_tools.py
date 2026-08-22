import json
from pathlib import Path
from datetime import datetime

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

    timestamp = datetime.now().isoformat()

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
    timestamp = datetime.now().isoformat()

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
    Load financial emails from a JSON file.

    Returns:
        list: A list of financial emails.
    """
    path = Path(__file__).parent.parent / "data" / "emails.json"
    if not path.exists():
        return []

    with open(path, 'r',  encoding="utf-8") as file:
        emails = json.load(file)

    return emails

def scan_financial_data() -> dict:
    """
    Scan financial data for significant changes and provide insights.

    Returns:
        dict: A dictionary containing the analysis results.
    """
    transactions = load_transactions()
    emails = load_financial_emails()

    # Placeholder for actual scanning logic
    # This function can be expanded to analyze transactions and emails for significant changes

    return {
        "transactions": transactions,
        "emails": emails,
    }