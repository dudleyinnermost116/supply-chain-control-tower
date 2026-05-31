from datetime import date, datetime
from typing import Dict, Any


EXCLUDED_STATUSES = {"CANCELLED", "CLOSED", "SHIPPED"}


def parse_date(value: str):
    if value is None or str(value).strip() == "":
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def calculate_delay_days(row: Dict[str, Any], today: date) -> int:
    scheduled_pick_date = parse_date(row.get("scheduled_pick_date"))

    if scheduled_pick_date is None:
        return 0

    return max((today - scheduled_pick_date).days, 0)


def assign_delay_status(row: Dict[str, Any], today: date) -> str:
    order_status = str(row.get("order_status", "")).upper()
    ship_confirm_date = row.get("ship_confirm_date")

    if order_status == "CANCELLED":
        return "CANCELLED"

    if order_status in {"SHIPPED", "CLOSED"} or str(ship_confirm_date).strip():
        return "SHIPPED"

    delay_days = calculate_delay_days(row, today)

    if delay_days == 0:
        return "ON_TIME"

    if 1 <= delay_days <= 5:
        return "DELAYED"

    return "NEED_ACTION"


def assign_reason_code(row: Dict[str, Any], today: date) -> str:
    delay_status = assign_delay_status(row, today)

    if delay_status in {"ON_TIME", "SHIPPED", "CANCELLED"}:
        return "NOT_APPLICABLE"

    qty_ordered = int(row.get("qty_ordered", 0))
    qty_allocated = int(row.get("qty_allocated", 0))
    available_inventory = int(row.get("available_inventory", 0))
    backorder_qty = int(row.get("backorder_qty", 0))

    truck_available = str(row.get("truck_available", "")).upper()
    carrier_status = str(row.get("carrier_status", "")).upper()
    pick_status = str(row.get("pick_status", "")).upper()
    freight_hold_flag = str(row.get("freight_hold_flag", "")).upper()

    if freight_hold_flag == "YES":
        return "FREIGHT_HOLD"

    if backorder_qty > 0:
        return "BACKORDER"

    if qty_allocated < qty_ordered and available_inventory < (qty_ordered - qty_allocated):
        return "INVENTORY_SHORTAGE"

    if truck_available == "NO":
        return "TRUCK_NOT_AVAILABLE"

    if carrier_status == "DELAYED":
        return "CARRIER_DELAY"

    if pick_status not in {"READY", "COMPLETE"}:
        return "WAREHOUSE_PICK_DELAY"

    return "UNKNOWN_NEEDS_REVIEW"


def generate_explanation(row: Dict[str, Any], today: date) -> str:
    delay_days = calculate_delay_days(row, today)
    delay_status = assign_delay_status(row, today)
    reason_code = assign_reason_code(row, today)

    if delay_status == "ON_TIME":
        return "Shipment is not delayed because the scheduled pick date is today or in the future."

    if delay_status == "SHIPPED":
        return "Shipment is already completed or ship-confirmed."

    if delay_status == "CANCELLED":
        return "Order is cancelled and should not be treated as an active shipment delay."

    return (
        f"Shipment is delayed by {delay_days} days. "
        f"Delay status is {delay_status}. "
        f"The likely reason is {reason_code}."
    )


def recommend_action(row: Dict[str, Any], today: date) -> str:
    reason_code = assign_reason_code(row, today)

    actions = {
        "INVENTORY_SHORTAGE": "Review available inventory, allocate stock, or check substitute items.",
        "BACKORDER": "Check inbound purchase orders and supplier delivery dates.",
        "TRUCK_NOT_AVAILABLE": "Contact transportation team to arrange truck capacity.",
        "CARRIER_DELAY": "Contact carrier and confirm revised pickup or delivery date.",
        "WAREHOUSE_PICK_DELAY": "Ask warehouse team to prioritize picking.",
        "FREIGHT_HOLD": "Resolve freight hold before scheduling pickup.",
        "UNKNOWN_NEEDS_REVIEW": "Manually review order, warehouse, inventory, and carrier data.",
        "NOT_APPLICABLE": "No action required.",
    }

    return actions.get(reason_code, "Manual review required.")