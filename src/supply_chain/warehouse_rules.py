# supply_chain/warehouse_rules.py
#
# Business rules for the Warehouse Agent.
# Determines pick status, delay root cause, and recommended action.
#
# Pick status definitions (from source system):
#   COMPLETE     — all units picked
#   IN_PROGRESS  — picking started but not finished
#   READY        — pick list generated, not yet started
#   NOT_STARTED  — no pick activity at all
#   BLOCKED      — pick cannot proceed (freight hold, system issue, etc.)
#
# Pick health (assigned by this module):
#   ON_TRACK     — COMPLETE or READY with no delay flag
#   AT_RISK      — IN_PROGRESS but equipment or staffing issue flagged
#   DELAYED      — NOT_STARTED past scheduled date, or BLOCKED


from datetime import date, datetime


def parse_date(value: str):
    """Converts YYYY-MM-DD string to a Python date. Returns None if empty."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def assign_pick_health(row: dict, today: date) -> str:
    """
    Assigns a health label to a warehouse pick row.
    Used to quickly surface which picks need attention.
    """
    pick_status = str(row.get("pick_status", "")).strip().upper()
    equipment_issue = str(row.get("equipment_issue", "NO")).strip().upper()
    staffing_flag = str(row.get("staffing_flag", "NO")).strip().upper()
    scheduled_pick_date = parse_date(row.get("scheduled_pick_date"))

    if pick_status == "COMPLETE":
        return "ON_TRACK"

    if pick_status == "BLOCKED":
        return "DELAYED"

    if pick_status == "NOT_STARTED":
        # If scheduled date is past, it is delayed
        if scheduled_pick_date and scheduled_pick_date < today:
            return "DELAYED"
        return "AT_RISK"

    if pick_status == "IN_PROGRESS":
        if equipment_issue == "YES" or staffing_flag == "YES":
            return "AT_RISK"
        return "ON_TRACK"

    if pick_status == "READY":
        return "ON_TRACK"

    return "UNKNOWN"


def calculate_pick_delay_days(row: dict, today: date) -> int:
    """
    Returns how many days overdue the pick is.
    Returns 0 if pick is complete or not yet due.
    """
    pick_status = str(row.get("pick_status", "")).strip().upper()
    if pick_status == "COMPLETE":
        return 0

    scheduled = parse_date(row.get("scheduled_pick_date"))
    if scheduled is None:
        return 0

    return max((today - scheduled).days, 0)


def get_pick_recommendation(row: dict, today: date) -> str:
    """
    Returns a plain-English recommendation based on pick status and root cause flags.
    """
    pick_status = str(row.get("pick_status", "")).strip().upper()
    delay_reason = str(row.get("pick_delay_reason", "")).strip()
    equipment_issue = str(row.get("equipment_issue", "NO")).strip().upper()
    staffing_flag = str(row.get("staffing_flag", "NO")).strip().upper()
    warehouse = row.get("warehouse_name", "the warehouse")
    order = row.get("sales_order_no", "this order")
    delay_days = calculate_pick_delay_days(row, today)

    if pick_status == "COMPLETE":
        return f"Pick for {order} is complete. No action required."

    if pick_status == "BLOCKED":
        return (
            f"Pick for {order} is blocked ({delay_reason or 'reason unspecified'}). "
            "Resolve the blocking issue before pick can proceed. "
            "If freight hold is the cause, coordinate with the freight team first."
        )

    if pick_status == "NOT_STARTED":
        if staffing_flag == "YES":
            return (
                f"Pick for {order} at {warehouse} has not started — staffing shortage. "
                f"Order is {delay_days} day(s) overdue. "
                "Escalate to warehouse supervisor to reassign from another zone or bring in temp staff."
            )
        if delay_reason == "SYSTEM_ERROR":
            return (
                f"Pick for {order} has not started — WMS system error prevented pick list generation. "
                "Contact warehouse IT to regenerate the pick list immediately. "
                "Manual pick may be needed if system is still down."
            )
        return (
            f"Pick for {order} has not started and is {delay_days} day(s) overdue. "
            "Escalate to warehouse supervisor to prioritize in the pick queue immediately."
        )

    if pick_status == "IN_PROGRESS":
        if equipment_issue == "YES":
            return (
                f"Pick for {order} is in progress but a equipment breakdown has stalled it. "
                "Arrange alternate equipment or reassign to a manual pick process."
            )
        return f"Pick for {order} is in progress. Monitor for completion."

    if pick_status == "READY":
        return (
            f"Pick list for {order} is ready but picking has not started. "
            "Confirm picker assignment and begin immediately."
        )

    return f"Pick status for {order} is unknown. Manual review required."


def get_warehouse_summary_stats(rows: list, today: date) -> dict:
    """
    Aggregates pick health counts across all rows.
    Used by the summary tool.
    """
    stats = {
        "total_picks": len(rows),
        "ON_TRACK": 0,
        "AT_RISK": 0,
        "DELAYED": 0,
        "UNKNOWN": 0,
    }

    for row in rows:
        health = assign_pick_health(row, today)
        stats[health] = stats.get(health, 0) + 1

    return stats
