# supply_chain/recommendations.py
#
# This file contains all recommendation logic for the shipping delay agent.
# Each reason code maps to a specific action.
# Severity (NEED_ACTION vs DELAYED) adds an escalation layer on top.
#
# To add a new reason code recommendation, just add a new entry
# to the REASON_ACTIONS dictionary below.

REASON_ACTIONS = {
    "FREIGHT_HOLD": {
        "team": "Freight / Carrier Team",
        "action": (
            "Contact the freight team immediately to identify the reason for the hold. "
            "Request an estimated release date. "
            "If hold cannot be resolved within 24 hours, escalate to logistics manager."
        ),
        "customer_impact": "Customer delivery will be further delayed until freight hold is released.",
    },
    "BACKORDER": {
        "team": "Procurement / Supplier Team",
        "action": (
            "Check supplier ETA for backordered items. "
            "Evaluate whether a partial shipment is possible for available items. "
            "Consider sourcing from an alternate supplier if lead time is unacceptable."
        ),
        "customer_impact": "Customer is waiting on items not currently in stock. Proactive communication recommended.",
    },
    "INVENTORY_SHORTAGE": {
        "team": "Warehouse / Inventory Team",
        "action": (
            "Verify current inventory levels in the warehouse. "
            "Check if stock can be reallocated from a lower-priority order. "
            "If shortage is confirmed, escalate to procurement for emergency replenishment."
        ),
        "customer_impact": "Order cannot ship until inventory is available or reallocated.",
    },
    "TRUCK_NOT_AVAILABLE": {
        "team": "Transportation / Carrier Team",
        "action": (
            "Contact the assigned carrier for an emergency truck assignment. "
            "If unavailable, request routing through an alternate carrier "
            "or consolidate with another outbound shipment."
        ),
        "customer_impact": "Shipment is ready but cannot leave the warehouse. Resolution depends on carrier response time.",
    },
    "CARRIER_DELAY": {
        "team": "Carrier Relations Team",
        "action": (
            "Contact the carrier directly to get a revised pickup commitment date. "
            "Log the delay in the carrier scorecard. "
            "If no commitment is received within 4 hours, escalate and arrange alternate carrier."
        ),
        "customer_impact": "Carrier has not picked up the shipment as scheduled. Customer ETA will shift.",
    },
    "WAREHOUSE_PICK_DELAY": {
        "team": "Warehouse Operations Team",
        "action": (
            "Escalate to the warehouse supervisor to prioritize this order in the pick queue. "
            "Confirm whether pick has started. "
            "If not started, request same-day completion. "
            "Check for staffing or equipment issues causing backlog."
        ),
        "customer_impact": "Order has not been picked yet. Internal execution issue — not supplier or carrier related.",
    },
    "UNKNOWN_NEEDS_REVIEW": {
        "team": "Supply Chain Coordinator",
        "action": (
            "Assign this order to a supply chain coordinator for manual investigation. "
            "Review shipment history, warehouse status, and carrier records "
            "to identify the true root cause before taking action."
        ),
        "customer_impact": "Root cause is unclear. Do not communicate ETA to customer until investigation is complete.",
    },
    "NOT_APPLICABLE": {
        "team": "No action required",
        "action": "This order does not require intervention. It is either on time, already shipped, or cancelled.",
        "customer_impact": "No customer impact from delay.",
    },
}


def get_escalation_note(delay_status: str, delay_days: int) -> str:
    """
    Returns an escalation note based on how severe the delay is.
    This is added on top of the reason-based recommendation.
    """
    if delay_status == "NEED_ACTION":
        return (
            f"ESCALATION REQUIRED: This order is {delay_days} days overdue. "
            "Notify the customer with a revised ETA immediately. "
            "Escalate to supply chain manager if not resolved today."
        )
    elif delay_status == "DELAYED":
        return (
            f"MONITOR CLOSELY: This order is {delay_days} day(s) overdue. "
            "Coordinate with the responsible team to resolve before it reaches critical status."
        )
    else:
        return "No escalation required at this time."


def build_recommendation(reason_code: str, delay_status: str, delay_days: int) -> dict:
    """
    Combines reason-based action with severity-based escalation note.
    Returns a complete recommendation dictionary.
    """
    # Fall back to UNKNOWN if reason code is not in our table
    action_info = REASON_ACTIONS.get(reason_code, REASON_ACTIONS["UNKNOWN_NEEDS_REVIEW"])
    escalation = get_escalation_note(delay_status, delay_days)

    return {
        "responsible_team": action_info["team"],
        "recommended_action": action_info["action"],
        "escalation_note": escalation,
        "customer_impact": action_info["customer_impact"],
    }


def calculate_risk_level(total_orders: int, delayed: int, need_action: int) -> str:
    """
    Calculates an overall risk level for the management summary.
    Gives managers an instant signal about how serious the day looks.
    """
    if need_action > 0:
        return "CRITICAL"

    if total_orders == 0:
        return "LOW"

    delay_pct = delayed / total_orders

    if delay_pct > 0.30:
        return "HIGH"
    elif delayed > 0:
        return "MEDIUM"
    else:
        return "LOW"