import re
from email.utils import parseaddr
from datetime import datetime

FINANCIAL_CATEGORIES = (
    "subscription",
    "renewal",
    "price_change",
    "payment",
    "invoice",
    "refund",
    "financial_deadline",
    "other_financial",
)


def _extract_money(text: str) -> list:
    """
    Extract monetary amounts such as:
    CAD 25.00
    CA$25.00
    USD 10
    $19.99
    """
    pattern = re.compile(
        r"(?:(CAD|USD|EUR|GBP)\s*|(?:CA)?\$)"
        r"(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    amounts = []

    for match in pattern.finditer(text):
        currency = match.group(1)

        if not currency:
            currency = "CAD" if "CA$" in match.group(0).upper() else None

        value = float(
            match.group(2).replace(",", "")
        )

        amounts.append({
            "amount": value,
            "currency": currency.upper() if currency else None,
        })

    return amounts


def _classify_category(text: str) -> str:
    text = text.lower()

    if any(x in text for x in (
        "price increase",
        "price increased",
        "price will increase",
        "price change",
        "new price",
    )):
        return "price_change"

    if any(x in text for x in (
        "refund",
        "refunded",
        "refund issued",
    )):
        return "refund"

    if any(x in text for x in (
        "invoice",
        "amount due",
        "invoice total",
    )):
        return "invoice"

    if any(x in text for x in (
        "successfully subscribed",
        "you've successfully subscribed",
        "you subscribed",
        "your new plan",
        "subscription started",
        "new subscription",
    )):
        return "subscription"

    if any(x in text for x in (
        "will renew",
        "renews",
        "renewal date",
        "automatic renewal",
        "automatically renew",
    )):
        return "renewal"

    if any(x in text for x in (
        "subscription",
        "subscribed",
        "membership",
        "your plan",
    )):
        return "subscription"

    if any(x in text for x in (
        "payment received",
        "payment successful",
        "payment confirmation",
        "you were charged",
        "we charged",
    )):
        return "payment"

    if any(x in text for x in (
        "due date",
        "deadline",
        "payment due",
    )):
        return "financial_deadline"

    return "other_financial"

def _extract_old_new_amounts(text: str) -> dict:
    result = {
        "old_amount": None,
        "new_amount": None,
        "currency": None,
    }

    pattern = re.compile(
        r"\bfrom\s+"
        r"((?:(?:CAD|USD|EUR|GBP)\s*|(?:CA)?\$)\s*"
        r"\d+(?:,\d{3})*(?:\.\d{1,2})?)"
        r"\s+to\s+"
        r"((?:(?:CAD|USD|EUR|GBP)\s*|(?:CA)?\$)\s*"
        r"\d+(?:,\d{3})*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return result

    old_money = _extract_money(match.group(1))
    new_money = _extract_money(match.group(2))

    if not old_money or not new_money:
        return result

    return {
        "old_amount": old_money[0]["amount"],
        "new_amount": new_money[0]["amount"],
        "currency": (
            new_money[0]["currency"]
            or old_money[0]["currency"]
        ),
    }

def _extract_financial_dates(text: str) -> dict:
    result = {
        "renewal_date": None,
        "due_date": None,
        "effective_date": None,
    }

    date_pattern = (
        r"(?P<date>"
        r"(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}"
        r"|\d{4}-\d{2}-\d{2}"
        r")"
    )

    def parse_date(raw_date: str) -> str | None:
        for date_format in (
            "%B %d, %Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(
                    raw_date,
                    date_format,
                ).date().isoformat()
            except ValueError:
                continue

        return None

    patterns = {
        "renewal_date": (
            rf"(?:renewal|renews?|automatically renew)"
            rf"[^.\n]{{0,120}}?{date_pattern}"
        ),

        "due_date": (
            rf"(?:due date|payment due|amount due|due on|pay by)"
            rf"[^.\n]{{0,80}}?{date_pattern}"
        ),

        "effective_date": (
            rf"(?:effective on|effective|takes effect)"
            rf"[^.\n]{{0,80}}?{date_pattern}"
        ),
    }

    for field, pattern in patterns.items():
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            result[field] = parse_date(
                match.group("date")
            )

    return result

def _is_financial_email(
    sender: str,
    subject: str,
    body: str,
) -> bool:
    text = f"{subject}\n{body}".lower()

    strong_financial_phrases = (
        "invoice",
        "receipt",
        "payment successful",
        "payment confirmation",
        "payment received",
        "you were charged",
        "we charged",
        "amount due",
        "billing amount",
        "successfully subscribed",
        "you've successfully subscribed",
        "subscription will renew",
        "subscription has renewed",
        "automatically renew",
        "renewal date",
        "price increase",
        "price decreased",
        "price decrease",
        "price change",
        "refund issued",
        "refunded",
    )

    weak_financial_words = (
        "subscription",
        "billing",
        "payment",
        "charge",
        "purchase",
        "membership",
        "plan",
        "order",
        "renewal",
        "refund",
    )

    non_financial_context = (
        "newsletter",
        "unsubscribe",
        "email preferences",
        "manage email preferences",
        "job alert",
        "jobs for you",
        "new jobs",
        "connection request",
        "application update",
        "career opportunities",
    )

    score = 0

    if any(
        phrase in text
        for phrase in strong_financial_phrases
    ):
        score += 3

    if _extract_money(text):
        score += 2

    if any(
        word in text
        for word in weak_financial_words
    ):
        score += 1

    if any(
        phrase in text
        for phrase in non_financial_context
    ):
        score -= 2

    return score >= 3

def _extract_subscription_amount(
    text: str,
) -> dict | None:
    pattern = re.compile(
        r"(?:subscription|membership|plan)"
        r"[^\n]{0,100}?"
        r"((?:(?:CAD|USD|EUR|GBP)\s*|(?:CA)?\$)"
        r"\s*\d+(?:,\d{3})*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    money = _extract_money(match.group(1))

    if not money:
        return None

    return money[0]

def _add_one_month(date_value: datetime) -> datetime:
    year = date_value.year
    month = date_value.month + 1

    if month == 13:
        month = 1
        year += 1

    # Handle month-end safely.
    import calendar

    last_day = calendar.monthrange(
        year,
        month,
    )[1]

    day = min(
        date_value.day,
        last_day,
    )

    return date_value.replace(
        year=year,
        month=month,
        day=day,
    )


def _extract_order_date(text: str) -> str | None:
    pattern = re.compile(
        r"order\s+date\s*:\s*"
        r"("
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\s+\d{1,2},\s+\d{4}"
        r")",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    raw_date = match.group(1)

    # Normalize Sept -> Sep for strptime.
    raw_date = re.sub(
        r"^Sept\b",
        "Sep",
        raw_date,
        flags=re.IGNORECASE,
    )

    try:
        return datetime.strptime(
            raw_date,
            "%b %d, %Y",
        ).date().isoformat()
    except ValueError:
        return None

def classify_financial_email(email: dict) -> dict:
    """
    Convert a Gmail financial email into a normalized financial event.
    """
    sender = email.get("sender", "")
    subject = email.get("subject", "")
    body = email.get("body", "")

    text = f"{subject}\n{body}"

    is_financial = _is_financial_email(
        sender,
        subject,
        body,
    )

    if not is_financial:
        return {
            "source": "gmail",
            "source_id": email.get("message_id"),

            "is_financial": False,
            "category": None,
            "change_type": None,

            "sender": sender,
            "subject": subject,

            "merchant": None,
            "product": None,

            "amount": None,
            "currency": None,

            "old_amount": None,
            "new_amount": None,
            "absolute_change": None,
            "percentage_change": None,

            "monthly_impact": None,
            "annual_impact": None,

            "billing_frequency": None,

            "renewal_date": None,
            "renewal_date_basis": None,
            "due_date": None,
            "effective_date": None,

            "received_at": email.get("received_at"),

            "confidence": 0.95,

            "evidence": {
                "sender": sender or None,
                "subject": subject or None,
                "body_excerpt": (
                    body[:300]
                    if body
                    else None
                ),
            },
        }

    # Basic classification / extraction
    money = _extract_money(text)
    category = _classify_category(text)
    price_change = _extract_old_new_amounts(text)

    merchant = _extract_merchant(sender)
    product = _extract_product(subject, body)

    # IMPORTANT: calculate these BEFORE recurring impact
    billing_frequency = _extract_billing_frequency(text)
    dates = _extract_financial_dates(text)

    order_date = _extract_order_date(text)

    renewal_date = dates["renewal_date"]
    renewal_date_basis = None

    if renewal_date is not None:
        renewal_date_basis = "explicit"

    elif (
        category == "subscription"
        and billing_frequency == "monthly"
        and order_date is not None
        and "first month free" in text.lower()
        and "automatically renew" in text.lower()
    ):
        order_datetime = datetime.strptime(
            order_date,
            "%Y-%m-%d",
        )

        renewal_date = (
            _add_one_month(order_datetime)
            .date()
            .isoformat()
        )

        renewal_date_basis = (
            "derived_from_order_date_and_first_month_free"
        )

    subscription_amount = None

    if category in (
        "subscription",
        "renewal",
    ):
        subscription_amount = _extract_subscription_amount(
            text
        )

    if subscription_amount:
        primary_amount = subscription_amount

    elif money:
        primary_amount = money[-1]

    else:
        primary_amount = {
            "amount": None,
            "currency": None,
        }

    # Price change values
    old_amount = price_change["old_amount"]
    new_amount = price_change["new_amount"]

    absolute_change = None
    percentage_change = None

    if old_amount is not None and new_amount is not None:
        absolute_change = round(
            new_amount - old_amount,
            2,
        )

        if old_amount != 0:
            percentage_change = round(
                ((new_amount - old_amount) / old_amount) * 100,
                2,
            )

    # Detect change type
    if category == "price_change":
        if old_amount is not None and new_amount is not None:
            if new_amount > old_amount:
                change_type = "price_increase"
            elif new_amount < old_amount:
                change_type = "price_decrease"
            else:
                change_type = "no_change"

        elif "increase" in text.lower():
            change_type = "price_increase"

        elif "decrease" in text.lower():
            change_type = "price_decrease"

        else:
            change_type = "price_change"

    elif category == "subscription":
        change_type = "new_subscription"

    elif category == "renewal":
        change_type = "renewal"

    elif category == "payment":
        change_type = "payment"

    elif category == "invoice":
        change_type = "invoice"

    elif category == "refund":
        change_type = "refund"

    elif category == "financial_deadline":
        change_type = "financial_deadline"

    else:
        change_type = "other_financial"

    # Recurring financial impact
    monthly_impact = None
    annual_impact = None

    if billing_frequency == "monthly":
        if absolute_change is not None:
            monthly_impact = absolute_change
            annual_impact = round(
                absolute_change * 12,
                2,
            )

        elif (
            category == "subscription"
            and primary_amount["amount"] is not None
        ):
            monthly_impact = primary_amount["amount"]
            annual_impact = round(
                primary_amount["amount"] * 12,
                2,
            )

    # Build source evidence from the original email.
    evidence = {
        "sender": sender or None,
        "subject": subject or None,
        "body_excerpt": (
            body[:300]
            if body
            else None
        ),
    }

    # Confidence is based only on fields actually extracted.
    confidence = 0.5

    if category != "other_financial":
        confidence += 0.15

    if merchant:
        confidence += 0.10

    if product:
        confidence += 0.05

    if primary_amount["amount"] is not None:
        confidence += 0.10

    if any((
        dates["renewal_date"],
        dates["due_date"],
        dates["effective_date"],
    )):
        confidence += 0.05

    if change_type not in (
        None,
        "other_financial",
    ):
        confidence += 0.05

    confidence = round(
        min(confidence, 0.95),
        2,
    )

    return {
        "source": "gmail",
        "source_id": email.get("message_id"),

        "is_financial": is_financial,
        "category": category,
        "change_type": change_type,

        "sender": sender,
        "subject": subject,

        "merchant": merchant,
        "product": product,

        "amount": primary_amount["amount"],
        "currency": (
            price_change["currency"]
            or primary_amount["currency"]
        ),

        "old_amount": old_amount,
        "new_amount": new_amount,
        "absolute_change": absolute_change,
        "percentage_change": percentage_change,

        "monthly_impact": monthly_impact,
        "annual_impact": annual_impact,

        "billing_frequency": billing_frequency,

        "renewal_date": renewal_date,
        "renewal_date_basis": renewal_date_basis,
        "due_date": dates["due_date"],
        "effective_date": dates["effective_date"],

        "received_at": email.get("received_at"),

        "confidence": confidence,
        "evidence": evidence,
    }

def _extract_merchant(sender: str) -> str | None:
    if not sender:
        return None

    name, email_address = parseaddr(sender)

    if name:
        return name.strip().strip('"')

    if "@" in email_address:
        domain = email_address.split("@", 1)[1]
        return domain.split(".")[0].replace("-", " ").title()

    return None


def _extract_product(subject: str, body: str) -> str | None:
    text = f"{subject}\n{body}"

    patterns = (
        r"(ChatGPT Plus)",
        r"(Netflix)",
        r"(Spotify)",
        r"(Adobe Creative Cloud(?: Business)?)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1)

    return None


def _extract_billing_frequency(text: str) -> str | None:
    text = text.lower()

    if any(x in text for x in (
        "/month",
        "per month",
        "monthly",
        "every month",
    )):
        return "monthly"

    if any(x in text for x in (
        "/year",
        "per year",
        "yearly",
        "annually",
        "annual",
    )):
        return "yearly"

    if any(x in text for x in (
        "weekly",
        "per week",
        "/week",
    )):
        return "weekly"

    return None


def _extract_date(text: str) -> str | None:
    patterns = (
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+"
        r"(\d{1,2}),\s+(\d{4})",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        raw_date = match.group(0)

        try:
            parsed = datetime.strptime(
                raw_date,
                "%B %d, %Y",
            )
            return parsed.date().isoformat()
        except ValueError:
            continue

    return None