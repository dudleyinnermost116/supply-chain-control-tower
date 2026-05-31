# supply_chain/freight_rules.py
#
# Business rules for the Freight Agent.
# Determines freight status, hold classification, and carrier performance tier.
#
# Freight status definitions:
#   DELIVERED        — pickup and delivery both confirmed
#   IN_TRANSIT       — picked up, not yet delivered
#   ON_HOLD          — freight_hold_flag = YES, blocked from moving
#   PICKUP_MISSED    — pickup date passed, no actual pickup recorded
#   CARRIER_DELAYED  — carrier confirmed delay, not yet resolved
#   SCHEDULED        — pickup date is today or future, not yet picked up
#
# Carrier performance tiers (based on score):
#   STRONG    — score >= 85
#   AVERAGE   — score >= 70
#   WEAK      — score >= 55
#   CRITICAL  — score < 55


from datetime import date, datetime


def parse_date(value: str):
    """Converts YYYY-MM-DD string to a Python date. Returns None if empty."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def assign_freight_status(row: dict, today: date) -> str:
    """
    Assigns a status to a freight row based on hold flag, pickup, and delivery fields.
    Priority order ensures the most severe status always wins.
    """
    freight_status = str(row.get("freight_status", "")).strip().upper()

    # Trust the source system status for terminal states
    if freight_status == "DELIVERED":
        return "DELIVERED"

    if freight_status == "IN_TRANSIT":
        return "IN_TRANSIT"

    # Hold flag overrides everything else that is not yet delivered
    hold_flag = str(row.get("freight_hold_flag", "NO")).strip().upper()
    if hold_flag == "YES":
        return "ON_HOLD"

    if freight_status == "CARRIER_DELAYED":
        return "CARRIER_DELAYED"

    if freight_status == "PICKUP_MISSED":
        return "PICKUP_MISSED"

    # If pickup date is past and no actual pickup recorded — missed
    pickup_scheduled = parse_date(row.get("pickup_scheduled_date"))
    pickup_actual = row.get("pickup_actual_date", "").strip()

    if pickup_scheduled and pickup_scheduled < today and not pickup_actual:
        return "PICKUP_MISSED"

    return "SCHEDULED"


def calculate_pickup_delay_days(row: dict, today: date) -> int:
    """
    Returns how many days overdue the pickup is.
    Returns 0 if pickup is on time or already completed.
    """
    pickup_actual = row.get("pickup_actual_date", "").strip()
    if pickup_actual:
        return 0  # Already picked up

    pickup_scheduled = parse_date(row.get("pickup_scheduled_date"))
    if pickup_scheduled is None:
        return 0

    return max((today - pickup_scheduled).days, 0)


def assign_carrier_tier(score_str: str) -> str:
    """
    Converts a numeric carrier performance score into a tier label.
    """
    try:
        score = int(str(score_str).strip())
    except (ValueError, TypeError):
        return "UNKNOWN"

    if score >= 85:
        return "STRONG"
    if score >= 70:
        return "AVERAGE"
    if score >= 55:
        return "WEAK"
    return "CRITICAL"


def get_freight_recommendation(freight_status: str, hold_reason: str,
                                carrier_name: str, pickup_delay_days: int) -> str:
    """
    Returns a plain-English action recommendation based on freight status.
    """
    if freight_status == "DELIVERED":
        return "Shipment delivered. No action required."

    if freight_status == "IN_TRANSIT":
        return f"Shipment is in transit with {carrier_name}. Monitor for on-time delivery."

    if freight_status == "ON_HOLD":
        hold = hold_reason or "unspecified reason"
        return (
            f"Freight is on hold due to: {hold}. "
            "Contact the freight team to resolve the hold immediately. "
            "If not resolved within 24 hours, escalate to logistics manager."
        )

    if freight_status == "PICKUP_MISSED":
        return (
            f"{carrier_name} missed the scheduled pickup — {pickup_delay_days} day(s) ago. "
            "Call the carrier dispatcher for an emergency pickup slot. "
            "If no response within 4 hours, reassign to an alternate carrier."
        )

    if freight_status == "CARRIER_DELAYED":
        return (
            f"{carrier_name} has reported a delay. "
            "Request a revised pickup commitment date in writing. "
            "Log the delay in the carrier scorecard. "
            "If delay exceeds 48 hours, arrange alternate carrier."
        )

    # SCHEDULED
    return f"Pickup is scheduled with {carrier_name}. No action required yet."


def get_hold_severity(hold_reason: str) -> str:
    """
    Classifies how serious a freight hold is so urgent ones surface first.
    """
    high_severity = {"COMPLIANCE_ISSUE", "PAYMENT_DISPUTE"}
    medium_severity = {"DOCUMENTATION_MISSING"}

    normalized = str(hold_reason or "").strip().upper()

    if normalized in high_severity:
        return "HIGH"
    if normalized in medium_severity:
        return "MEDIUM"
    if normalized:
        return "LOW"
    return "NONE"
