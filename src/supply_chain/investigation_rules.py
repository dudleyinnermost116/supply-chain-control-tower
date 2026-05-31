# supply_chain/investigation_rules.py
#
# Investigation rules for the Phase 5 Root Cause Agent.
#
# This module does NOT load any CSV files.
# It receives pre-assembled data from the other agents and
# synthesises it into a unified root cause verdict.
#
# Key function: build_investigation_report()
# Takes findings from shipping, inventory, freight, and warehouse agents.
# Returns a structured dict with confirmed root cause, contributing
# factors, severity verdict, and the single most important next action.
#
# Root cause priority order (highest to lowest):
#   1. FREIGHT_HOLD      — order is physically blocked, nothing else matters
#   2. INVENTORY_SHORTAGE / BACKORDER — can't ship what you don't have
#   3. WAREHOUSE_PICK_DELAY — stock exists but hasn't been picked yet
#   4. CARRIER_DELAY / TRUCK_NOT_AVAILABLE — ready to go but no carrier
#   5. UNKNOWN — something is wrong but root cause is unclear


# ─── SEVERITY SCORER ────────────────────────────────────────────────────────

def score_severity(delay_days: int, has_freight_hold: bool,
                   inventory_status: str, pick_health: str) -> str:
    """
    Returns an overall investigation severity: CRITICAL, HIGH, MEDIUM, or LOW.

    CRITICAL — freight hold active OR delay is more than 7 days
    HIGH     — inventory is OUT_OF_STOCK or CRITICAL, or delay is 4–7 days
    MEDIUM   — warehouse pick is DELAYED or inventory is LOW
    LOW      — minor delay, everything else looks fine
    """
    if has_freight_hold or delay_days > 7:
        return "CRITICAL"

    if inventory_status in ("OUT_OF_STOCK", "CRITICAL") or delay_days >= 4:
        return "HIGH"

    if pick_health == "DELAYED" or inventory_status == "LOW":
        return "MEDIUM"

    return "LOW"


# ─── ROOT CAUSE RESOLVER ─────────────────────────────────────────────────────

def resolve_root_cause(shipping_reason: str, freight_status: str,
                       inventory_status: str, pick_health: str) -> str:
    """
    Determines the single most likely root cause by combining signals
    from all four agents. Uses priority ordering so the most severe
    and most actionable cause wins.

    Returns one of:
      FREIGHT_HOLD, INVENTORY_SHORTAGE, BACKORDER,
      WAREHOUSE_PICK_DELAY, CARRIER_DELAY,
      TRUCK_NOT_AVAILABLE, UNKNOWN_NEEDS_REVIEW, NOT_APPLICABLE
    """
    # Freight hold blocks everything — always the primary cause
    if freight_status == "ON_HOLD":
        return "FREIGHT_HOLD"

    # No stock or backordered — can't pick what isn't there
    if inventory_status in ("OUT_OF_STOCK", "ON_BACKORDER"):
        return "BACKORDER" if inventory_status == "ON_BACKORDER" else "INVENTORY_SHORTAGE"

    # Shipping agent already identified a specific reason — trust it
    # (but freight_hold already handled above)
    if shipping_reason not in ("NOT_APPLICABLE", "UNKNOWN_NEEDS_REVIEW", ""):
        return shipping_reason

    # Warehouse hasn't picked yet — internal execution problem
    if pick_health == "DELAYED":
        return "WAREHOUSE_PICK_DELAY"

    # Carrier missed pickup or is delayed
    if freight_status in ("PICKUP_MISSED", "CARRIER_DELAYED"):
        return "CARRIER_DELAY"

    return "UNKNOWN_NEEDS_REVIEW"


# ─── CONTRIBUTING FACTORS ────────────────────────────────────────────────────

def list_contributing_factors(freight_hold: bool, freight_status: str,
                               inventory_status: str, pick_health: str,
                               carrier_tier: str, delay_days: int) -> list:
    """
    Returns a plain-English list of all secondary problems found
    across the four agents, even if they are not the root cause.
    These are the 'warning signs' that may compound the delay.
    """
    factors = []

    if freight_hold:
        factors.append("Freight hold is active — order cannot move until resolved.")

    if inventory_status == "CRITICAL":
        factors.append("Inventory is critically low — replenishment needed urgently.")
    elif inventory_status == "LOW":
        factors.append("Inventory is below reorder point — monitor closely.")
    elif inventory_status == "OUT_OF_STOCK":
        factors.append("Item is out of stock — cannot allocate more units.")
    elif inventory_status == "ON_BACKORDER":
        factors.append("Item is on backorder — waiting on supplier delivery.")

    if pick_health == "DELAYED":
        factors.append("Warehouse pick is overdue — order has not been picked yet.")
    elif pick_health == "AT_RISK":
        factors.append("Warehouse pick is at risk — equipment or staffing issue flagged.")

    if freight_status == "PICKUP_MISSED":
        factors.append("Carrier missed the scheduled pickup.")
    elif freight_status == "CARRIER_DELAYED":
        factors.append("Carrier has reported a delay — revised pickup date not confirmed.")

    if carrier_tier in ("WEAK", "CRITICAL"):
        factors.append(
            f"Carrier performance is rated {carrier_tier} — "
            "consider alternate carrier for future orders."
        )

    if delay_days > 10:
        factors.append(
            f"Order is {delay_days} days overdue — "
            "customer communication should have already been sent."
        )

    if not factors:
        factors.append("No major contributing factors identified beyond the root cause.")

    return factors


# ─── FIRST ACTION RESOLVER ───────────────────────────────────────────────────

def get_first_action(root_cause: str, delay_days: int) -> str:
    """
    Returns the single most important next action for the root cause.
    Designed to be the first sentence a manager reads.
    """
    actions = {
        "FREIGHT_HOLD": (
            "Contact the freight team RIGHT NOW to identify the hold reason "
            "and get an estimated release time. Do not contact the customer "
            "until hold status is confirmed."
        ),
        "INVENTORY_SHORTAGE": (
            "Check if stock can be reallocated from a lower-priority order. "
            "If not, raise an emergency purchase order immediately."
        ),
        "BACKORDER": (
            "Call the supplier today and get a firm delivery commitment date. "
            "If date is unacceptable, source from alternate supplier."
        ),
        "WAREHOUSE_PICK_DELAY": (
            "Escalate to the warehouse supervisor to prioritise this order "
            "in the pick queue. Confirm pick starts within the next 2 hours."
        ),
        "CARRIER_DELAY": (
            "Call the carrier dispatcher directly and request a revised pickup "
            "commitment. If no response in 4 hours, reassign to alternate carrier."
        ),
        "TRUCK_NOT_AVAILABLE": (
            "Contact the transportation team for emergency truck assignment. "
            "If unavailable, consolidate with another outbound shipment today."
        ),
        "UNKNOWN_NEEDS_REVIEW": (
            "Assign this order to a supply chain coordinator for manual review. "
            "Check shipment history, warehouse records, and carrier logs "
            "before taking any action."
        ),
        "NOT_APPLICABLE": (
            "No action required — order is on time, already shipped, or cancelled."
        ),
    }

    base = actions.get(root_cause, "Manual review required.")

    # Add escalation suffix for very overdue orders
    if delay_days > 5 and root_cause != "NOT_APPLICABLE":
        base += (
            f" NOTE: This order is {delay_days} days overdue — "
            "notify customer with revised ETA immediately."
        )

    return base


# ─── MASTER REPORT BUILDER ───────────────────────────────────────────────────

def build_investigation_report(
    sales_order_no: str,
    customer_name: str,
    scheduled_pick_date: str,
    delay_days: int,
    delay_status: str,
    shipping_reason: str,
    inventory_status: str,
    freight_status: str,
    freight_hold: bool,
    freight_hold_reason: str,
    pick_health: str,
    carrier_tier: str,
    carrier_name: str,
) -> dict:
    """
    Master function. Takes one value from each agent and returns
    the complete investigation report as a structured dict.

    Called by investigate_order() in investigation_mcp_server.py.
    """
    root_cause = resolve_root_cause(
        shipping_reason, freight_status, inventory_status, pick_health
    )

    severity = score_severity(
        delay_days, freight_hold, inventory_status, pick_health
    )

    factors = list_contributing_factors(
        freight_hold, freight_status, inventory_status,
        pick_health, carrier_tier, delay_days
    )

    first_action = get_first_action(root_cause, delay_days)

    return {
        "sales_order_no": sales_order_no,
        "customer_name": customer_name,
        "scheduled_pick_date": scheduled_pick_date,
        "delay_days": delay_days,
        "delay_status": delay_status,
        "severity": severity,
        "root_cause": root_cause,
        "contributing_factors": factors,
        "first_action": first_action,
        "agent_signals": {
            "shipping_reason": shipping_reason,
            "inventory_status": inventory_status,
            "freight_status": freight_status,
            "freight_hold_active": freight_hold,
            "freight_hold_reason": freight_hold_reason,
            "pick_health": pick_health,
            "carrier_name": carrier_name,
            "carrier_tier": carrier_tier,
        },
    }
