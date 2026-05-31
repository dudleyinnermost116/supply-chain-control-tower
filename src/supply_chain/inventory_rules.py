# supply_chain/inventory_rules.py
#
# Business rules for inventory status assessment.
# These rules are separate from the shipping delay rules
# so each agent stays focused on its own domain.


def calculate_shortage(qty_available: int, qty_needed: int) -> int:
    """
    Returns how many units we are short for a given need.
    Returns 0 if there is enough stock.
    """
    shortage = qty_needed - qty_available
    return max(0, shortage)


def assign_inventory_status(row: dict) -> str:
    """
    Assigns a status to an inventory row based on availability.

    Status definitions:
    ON_BACKORDER  — backorder flag is Y, meaning supplier hasn't delivered yet
    OUT_OF_STOCK  — qty_available is 0 and not on backorder (allocation used it all)
    CRITICAL      — qty_available is below safety stock threshold
    LOW           — qty_available is below reorder point but above safety stock
    HEALTHY       — qty_available is at or above reorder point
    """
    backorder_flag = row.get("backorder_flag", "N").strip().upper()
    qty_available = int(row.get("qty_available", 0))
    safety_stock = int(row.get("safety_stock", 0))
    reorder_point = int(row.get("reorder_point", 0))

    if backorder_flag == "Y":
        return "ON_BACKORDER"

    if qty_available <= 0:
        return "OUT_OF_STOCK"

    if qty_available < safety_stock:
        return "CRITICAL"

    if qty_available < reorder_point:
        return "LOW"

    return "HEALTHY"


def can_fulfill(qty_available: int, qty_needed: int) -> bool:
    """
    Returns True if available stock can cover the needed quantity.
    """
    return qty_available >= qty_needed


def get_inventory_recommendation(status: str, item_no: str,
                                  expected_receipt_date: str) -> str:
    """
    Returns a plain-English recommendation based on inventory status.
    This mirrors the pattern we used in recommendations.py for shipping.
    """
    recommendations = {
        "ON_BACKORDER": (
            f"Item {item_no} is on backorder. "
            f"Expected receipt: {expected_receipt_date or 'not confirmed'}. "
            "Follow up with supplier for firm delivery commitment. "
            "Consider sourcing from alternate supplier if date is unacceptable."
        ),
        "OUT_OF_STOCK": (
            f"Item {item_no} is out of stock — all available units are allocated. "
            "Check if any lower-priority orders can release stock. "
            "Raise emergency purchase order immediately."
        ),
        "CRITICAL": (
            f"Item {item_no} is below safety stock. "
            "Trigger replenishment order immediately. "
            "Monitor daily until stock is restored."
        ),
        "LOW": (
            f"Item {item_no} is below reorder point. "
            "Raise a standard purchase order. "
            "Monitor to ensure it does not drop to critical level."
        ),
        "HEALTHY": (
            f"Item {item_no} has healthy stock levels. No action required."
        ),
    }
    return recommendations.get(status, "Status unknown — manual review required.")