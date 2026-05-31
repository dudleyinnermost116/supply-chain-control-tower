# supply_chain/po_rules.py
#
# Business rules for the Purchase Order Agent.
# Follows the same structure as rules.py and inventory_rules.py.
#
# PO Status definitions:
#   RECEIVED   — all qty received, po_status = RECEIVED
#   CANCELLED  — po_status = CANCELLED
#   PARTIAL    — some qty received but not all (po_status = PARTIAL)
#   ON_TIME    — open, expected receipt date is today or in the future
#   LATE       — open, expected receipt date is in the past
#
# These statuses are assigned by assign_po_status() below.

from datetime import date, datetime


def parse_date(value: str):
    """
    Converts a date string in YYYY-MM-DD format to a Python date object.
    Returns None if the value is empty or cannot be parsed.
    Same helper used in rules.py — kept here so this module is self-contained.
    """
    if value is None or str(value).strip() == "":
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_days_late(row: dict, today: date) -> int:
    """
    Returns how many days overdue this PO is.
    Returns 0 if the PO is on time, already received, or has no date.
    """
    po_status = str(row.get("po_status", "")).strip().upper()

    # Already closed — not late
    if po_status in {"RECEIVED", "CANCELLED"}:
        return 0

    expected = parse_date(row.get("expected_receipt_date"))
    if expected is None:
        return 0

    days_late = (today - expected).days
    return max(days_late, 0)


def assign_po_status(row: dict, today: date) -> str:
    """
    Assigns a status to a PO row based on po_status field and dates.

    Priority order:
    1. CANCELLED — if po_status says so
    2. RECEIVED  — if po_status says RECEIVED and all qty is in
    3. PARTIAL   — if some qty received but not all
    4. LATE      — if open and past expected receipt date
    5. ON_TIME   — if open and receipt date is today or future
    """
    po_status = str(row.get("po_status", "")).strip().upper()
    qty_ordered = row.get("qty_ordered", 0)
    qty_received = row.get("qty_received", 0)
    expected_receipt_date = parse_date(row.get("expected_receipt_date"))

    if po_status == "CANCELLED":
        return "CANCELLED"

    if po_status == "RECEIVED" or (qty_received >= qty_ordered and qty_ordered > 0):
        return "RECEIVED"

    if po_status == "PARTIAL" or (0 < qty_received < qty_ordered):
        return "PARTIAL"

    # At this point, PO is open with outstanding qty
    if expected_receipt_date is None:
        return "ON_TIME"  # No date = assume not late yet

    if expected_receipt_date < today:
        return "LATE"

    return "ON_TIME"


def get_po_recommendation(po_status: str, days_late: int,
                           supplier_name: str, item_no: str,
                           expected_receipt_date: str) -> str:
    """
    Returns a plain-English recommendation based on PO status.
    Mirrors the pattern in inventory_rules.py and recommendations.py.
    """
    if po_status == "RECEIVED":
        return f"PO for {item_no} is fully received. No action required."

    if po_status == "CANCELLED":
        return f"PO for {item_no} is cancelled. Verify whether a replacement order is needed."

    if po_status == "PARTIAL":
        return (
            f"PO for {item_no} is partially received. "
            f"Contact {supplier_name} to confirm delivery date for the remaining qty. "
            f"Expected: {expected_receipt_date or 'not confirmed'}."
        )

    if po_status == "LATE":
        return (
            f"PO for {item_no} from {supplier_name} is {days_late} day(s) overdue. "
            "Contact supplier immediately for a revised delivery commitment. "
            "If no response within 24 hours, escalate to procurement manager. "
            "Consider emergency sourcing if delay is critical."
        )

    # ON_TIME
    return (
        f"PO for {item_no} from {supplier_name} is on track. "
        f"Expected receipt: {expected_receipt_date or 'not confirmed'}. "
        "No action required."
    )


def calculate_po_value(row: dict) -> float:
    """
    Returns the total outstanding value of a PO line.
    qty_outstanding * unit_cost — useful for financial prioritisation.
    """
    qty_outstanding = row.get("qty_outstanding", 0)
    unit_cost = row.get("unit_cost", 0.0)
    return round(qty_outstanding * unit_cost, 2)
