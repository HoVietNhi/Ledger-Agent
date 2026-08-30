import calendar

from datetime import datetime
from typing import Any


def normalize_transaction(
    transaction: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Normalize one transaction before recurring-subscription detection.

    Required:
    - merchant
    - amount
    - date

    Optional:
    - currency
    - type
    """

    if not isinstance(transaction, dict):
        return None

    merchant = transaction.get("merchant")
    amount = transaction.get("amount")
    date_value = transaction.get("date")

    if not merchant or amount is None or not date_value:
        return None

    merchant = str(merchant).strip()

    if not merchant:
        return None

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None

    try:
        parsed_date = datetime.strptime(
            str(date_value).strip(),
            "%Y-%m-%d",
        )
    except ValueError:
        return None

    currency = transaction.get("currency")
    transaction_type = transaction.get("type")

    return {
        "merchant": merchant,
        "amount": amount,
        "currency": (
            str(currency).strip().upper()
            if currency
            else None
        ),
        "date": parsed_date.strftime("%Y-%m-%d"),
        "type": (
            str(transaction_type).strip().lower()
            if transaction_type
            else None
        ),

        # Preserve source-specific metadata.
        # Existing local transactions simply return None
        # for fields they do not contain.
        "source": transaction.get("source"),
        "plaid_primary_category": (
            transaction.get(
                "plaid_primary_category"
            )
        ),
        "plaid_detailed_category": (
            transaction.get(
                "plaid_detailed_category"
            )
        ),
        "plaid_transaction_id": (
            transaction.get(
                "plaid_transaction_id"
            )
        ),
    }

def group_transactions_by_merchant(
    transactions: list[dict],
) -> dict[str, list[dict]]:
    """
    Normalize transactions and group them by merchant.
    Invalid transactions are skipped.
    """

    grouped: dict[str, list[dict]] = {}

    for transaction in transactions:
        normalized = normalize_transaction(transaction)

        if normalized is None:
            continue

        merchant = normalized["merchant"]

        if merchant not in grouped:
            grouped[merchant] = []

        grouped[merchant].append(normalized)
    for merchant_transactions in grouped.values():
        merchant_transactions.sort(
            key=lambda item: item["date"]
        )

    return grouped

def calculate_date_intervals(
    transactions: list[dict],
) -> list[int]:
    """
    Calculate day gaps between consecutive transactions.

    Assumes transactions are already sorted oldest to newest.
    """

    if len(transactions) < 2:
        return []

    intervals: list[int] = []

    for previous, current in zip(
        transactions,
        transactions[1:],
    ):
        previous_date = datetime.strptime(
            previous["date"],
            "%Y-%m-%d",
        )

        current_date = datetime.strptime(
            current["date"],
            "%Y-%m-%d",
        )

        intervals.append(
            (current_date - previous_date).days
        )

    return intervals

def detect_monthly_cadence(
    intervals: list[int],
) -> bool:
    """
    Detect whether transaction intervals look monthly.

    MVP rule:
    - Need at least 2 intervals
    - Most intervals must fall between 25 and 35 days
    """

    if len(intervals) < 2:
        return False

    monthly_matches = sum(
        25 <= interval <= 35
        for interval in intervals
    )

    return monthly_matches >= 2

def detect_subscription_for_merchant(
    transactions: list[dict],
) -> dict:
    """
    Decide whether one merchant's transaction history
    looks like a recurring monthly subscription.

    Plaid transactions receive an additional category
    quality gate to avoid treating ordinary repeated
    spending, transfers, or payments as subscriptions.
    """

    if len(transactions) < 3:
        return {
            "is_subscription": False,
            "billing_frequency": None,
            "confidence": 0.0,
        }

    intervals = calculate_date_intervals(
        transactions
    )

    monthly_matches = sum(
        25 <= interval <= 35
        for interval in intervals
    )

    is_monthly = detect_monthly_cadence(
        intervals
    )

    latest = transactions[-1]

    if (
        is_monthly
        and latest.get("source") == "plaid"
    ):
        excluded_primary_categories = {
            "FOOD_AND_DRINK",
            "GENERAL_MERCHANDISE",
            "LOAN_PAYMENTS",
            "TRANSFER_IN",
            "TRANSFER_OUT",
            "INCOME",
            "TRANSPORTATION",
        }

        primary_category = latest.get(
            "plaid_primary_category"
        )

        if (
            primary_category
            in excluded_primary_categories
        ):
            is_monthly = False

    if not is_monthly:
        confidence = 0.0

    else:
        match_ratio = (
            monthly_matches
            / len(intervals)
        )

        confidence = round(
            min(
                0.95,
                0.70
                + (match_ratio * 0.15)
                + (
                    min(
                        len(transactions),
                        5,
                    )
                    * 0.02
                ),
            ),
            2,
        )

    return {
        "is_subscription": is_monthly,
        "billing_frequency": (
            "monthly"
            if is_monthly
            else None
        ),
        "confidence": confidence,
    }

def get_latest_and_previous_amount(
    transactions: list[dict],
) -> dict:
    """
    Get the latest and previous transaction amounts.

    Assumes transactions are sorted oldest to newest.
    """

    if not transactions:
        return {
            "latest_amount": None,
            "previous_amount": None,
        }

    latest_amount = transactions[-1]["amount"]

    previous_amount = (
        transactions[-2]["amount"]
        if len(transactions) >= 2
        else None
    )

    return {
        "latest_amount": latest_amount,
        "previous_amount": previous_amount,
    }

def analyze_subscription_price_change(
    previous_amount: float | None,
    latest_amount: float | None,
) -> dict:
    """
    Analyze price change between the previous and latest charge.
    """

    if previous_amount is None or latest_amount is None:
        return {
            "change_type": None,
            "absolute_change": None,
            "percentage_change": None,
        }

    absolute_change = round(
        latest_amount - previous_amount,
        2,
    )

    if absolute_change > 0:
        change_type = "price_increase"
    elif absolute_change < 0:
        change_type = "price_decrease"
    else:
        change_type = "no_change"

    if previous_amount == 0:
        percentage_change = None
    else:
        percentage_change = round(
            (absolute_change / previous_amount) * 100,
            2,
        )

    return {
        "change_type": change_type,
        "absolute_change": absolute_change,
        "percentage_change": percentage_change,
    }

def calculate_recurring_impact(
    absolute_change: float | None,
    billing_frequency: str | None,
) -> dict:
    """
    Calculate recurring financial impact from a price change.
    """

    if absolute_change is None or billing_frequency is None:
        return {
            "monthly_impact": None,
            "annual_impact": None,
        }

    if billing_frequency == "monthly":
        monthly_impact = round(absolute_change, 2)
        annual_impact = round(absolute_change * 12, 2)

        return {
            "monthly_impact": monthly_impact,
            "annual_impact": annual_impact,
        }

    return {
        "monthly_impact": None,
        "annual_impact": None,
    }

def estimate_next_charge_date(
    transactions: list[dict],
    billing_frequency: str | None,
) -> str | None:
    """
    Estimate the next recurring charge date.

    For monthly subscriptions, advance by one calendar month
    while preserving the day when possible.
    """

    if not transactions or billing_frequency != "monthly":
        return None

    last_date = datetime.strptime(
        transactions[-1]["date"],
        "%Y-%m-%d",
    )

    if last_date.month == 12:
        next_year = last_date.year + 1
        next_month = 1
    else:
        next_year = last_date.year
        next_month = last_date.month + 1

    last_day_of_next_month = calendar.monthrange(
        next_year,
        next_month,
    )[1]

    next_day = min(
        last_date.day,
        last_day_of_next_month,
    )

    next_date = last_date.replace(
        year=next_year,
        month=next_month,
        day=next_day,
    )

    return next_date.strftime("%Y-%m-%d")

def analyze_subscription_for_merchant(
    merchant: str,
    transactions: list[dict],
) -> dict:
    """
    Build one structured subscription analysis
    from a merchant's sorted transaction history.
    """

    detection = detect_subscription_for_merchant(
        transactions
    )

    amounts = get_latest_and_previous_amount(
        transactions
    )

    price_change = analyze_subscription_price_change(
        amounts["previous_amount"],
        amounts["latest_amount"],
    )

    impact = calculate_recurring_impact(
        price_change["absolute_change"],
        detection["billing_frequency"],
    )

    next_expected_date = estimate_next_charge_date(
        transactions,
        detection["billing_frequency"],
    )

    currency = (
        transactions[-1].get("currency")
        if transactions
        else None
    )

    last_charge_date = (
        transactions[-1].get("date")
        if transactions
        else None
    )

    intervals = calculate_date_intervals(
        transactions
    )

    return {
        "merchant": merchant,
        "is_subscription": detection["is_subscription"],
        "billing_frequency": detection["billing_frequency"],
        "confidence": detection["confidence"],

        "currency": currency,
        "source": (
            transactions[-1].get("source")
            if transactions
            else None
        ),

        "previous_amount": amounts["previous_amount"],
        "latest_amount": amounts["latest_amount"],

        "change_type": price_change["change_type"],
        "absolute_change": price_change["absolute_change"],
        "percentage_change": price_change["percentage_change"],

        "monthly_impact": impact["monthly_impact"],
        "annual_impact": impact["annual_impact"],

        "last_charge_date": last_charge_date,
        "next_expected_date": next_expected_date,

        "transaction_count": len(transactions),
        "intervals_days": intervals,
    }
