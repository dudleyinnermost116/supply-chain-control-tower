# supply_chain/recommendation_engine.py
#
# Recommendation engine for Phase 6 of the Supply Chain Control Tower.
#
# This module takes investigation signals (already gathered by Phase 5 logic)
# and turns them into a prioritised, team-assigned action plan.
#
# Key responsibilities:
#   1. Score every delayed order from 0-100 by urgency
#   2. Assign each order to the team responsible for fixing it
#   3. Flag orders that need manager escalation
#   4. Generate one clear action sentence per order
#
# Priority score breakdown (max 100):
#   - Delay days:       up to 40 points  (2 pts per day, capped at 20 days)
#   - Severity:         up to 30 points  (CRITICAL=30, HIGH=20, MEDIUM=10, LOW=5)
#   - Freight hold:     15 points        (physical block — always urgent)
#   - Inventory issue:  15 points        (OUT_OF_STOCK or ON_BACKORDER)
#
# Escalation threshold: score >= 70 OR status is NEED_ACTION OR freight hold active


# ─── TEAM ASSIGNMENTS ────────────────────────────────────────────────────────
# Maps root cause to the team that owns the resolution.
# Keep this in one place so it is easy to update.

TEAM_BY_ROOT_CAUSE = {
    "FREIGHT_HOLD":            "Freight / Carrier Team",
    "BACKORDER":               "Procurement / Supplier Team",
    "INVENTORY_SHORTAGE":      "Warehouse / Inventory Team",
    "TRUCK_NOT_AVAILABLE":     "Transportation Team",
    "CARRIER_DELAY":           "Carrier Relations Team",
    "WAREHOUSE_PICK_DELAY":    "Warehouse Operations Team",
    "UNKNOWN_NEEDS_REVIEW":    "Supply Chain Coordinator",
    "NOT_APPLICABLE":          "No Team Required",
}


# ─── ACTION SENTENCES ────────────────────────────────────────────────────────
# One plain-English sentence per root cause.
# Short enough to put in a work queue, specific enough to act on immediately.

ACTION_BY_ROOT_CAUSE = {
    "FREIGHT_HOLD": (
        "Contact freight team to identify hold reason and get release ETA. "
        "Escalate to logistics manager if not resolved within 24 hours."
    ),
    "BACKORDER": (
        "Call supplier for firm delivery date. "
        "If date is unacceptable, source from alternate supplier today."
    ),
    "INVENTORY_SHORTAGE": (
        "Check if stock can be reallocated from a lower-priority order. "
        "If not, raise emergency purchase order immediately."
    ),
    "TRUCK_NOT_AVAILABLE": (
        "Contact transportation team for emergency truck assignment. "
        "If unavailable, consolidate with another outbound shipment."
    ),
    "CARRIER_DELAY": (
        "Call carrier dispatcher for revised pickup commitment. "
        "If no response in 4 hours, reassign to alternate carrier."
    ),
    "WAREHOUSE_PICK_DELAY": (
        "Escalate to warehouse supervisor to prioritise this pick immediately. "
        "Confirm pick starts within 2 hours."
    ),
    "UNKNOWN_NEEDS_REVIEW": (
        "Assign to supply chain coordinator for manual investigation. "
        "Review shipment, warehouse, inventory, and carrier records before acting."
    ),
    "NOT_APPLICABLE": (
        "No action required."
    ),
}


# ─── PRIORITY SCORER ─────────────────────────────────────────────────────────

def calculate_priority_score(delay_days: int, severity: str,
                              freight_hold: bool, inventory_status: str) -> int:
    """
    Returns a priority score from 0 to 100.
    Higher score = more urgent = appears first in the action plan.

    Scoring breakdown:
      Delay days    → 2 points per day, capped at 40 (20 days max)
      Severity      → CRITICAL=30, HIGH=20, MEDIUM=10, LOW=5
      Freight hold  → +15 if active
      Inventory     → +15 if OUT_OF_STOCK or ON_BACKORDER
    """
    score = 0

    # Delay days — 2 points each, max 40
    score += min(delay_days * 2, 40)

    # Severity
    severity_points = {
        "CRITICAL": 30,
        "HIGH":     20,
        "MEDIUM":   10,
        "LOW":       5,
    }
    score += severity_points.get(severity, 0)

    # Freight hold — physical block always bumps priority
    if freight_hold:
        score += 15

    # Inventory problem
    if inventory_status in ("OUT_OF_STOCK", "ON_BACKORDER"):
        score += 15

    # Cap at 100
    return min(score, 100)


# ─── ESCALATION FLAG ─────────────────────────────────────────────────────────

def needs_escalation(priority_score: int, delay_status: str,
                     freight_hold: bool) -> bool:
    """
    Returns True if this order needs manager escalation.

    Escalation triggers:
      - Priority score is 70 or above
      - Delay status is NEED_ACTION (more than 5 days overdue)
      - Freight hold is active (physical block)
    """
    if priority_score >= 70:
        return True
    if delay_status == "NEED_ACTION":
        return True
    if freight_hold:
        return True
    return False


# ─── ESCALATION REASON ───────────────────────────────────────────────────────

def get_escalation_reason(priority_score: int, delay_status: str,
                           freight_hold: bool, delay_days: int) -> str:
    """
    Returns a plain-English reason why this order needs escalation.
    Used in the escalation list tool.
    """
    reasons = []

    if delay_status == "NEED_ACTION":
        reasons.append(f"Order is {delay_days} days overdue — past the 5-day threshold.")

    if freight_hold:
        reasons.append("Active freight hold is physically blocking this shipment.")

    if priority_score >= 70:
        reasons.append(f"Priority score is {priority_score}/100 — exceeds escalation threshold.")

    if not reasons:
        return "Escalation threshold met."

    return " ".join(reasons)


# ─── TEAM LOOKUP ─────────────────────────────────────────────────────────────

def get_responsible_team(root_cause: str) -> str:
    """Returns the team name for a given root cause."""
    return TEAM_BY_ROOT_CAUSE.get(root_cause, "Supply Chain Coordinator")


# ─── ACTION LOOKUP ───────────────────────────────────────────────────────────

def get_action_sentence(root_cause: str) -> str:
    """Returns the recommended action sentence for a given root cause."""
    return ACTION_BY_ROOT_CAUSE.get(root_cause, "Manual review required.")


# ─── MASTER RECORD BUILDER ───────────────────────────────────────────────────

def build_action_record(
    sales_order_no: str,
    customer_name: str,
    scheduled_pick_date: str,
    delay_days: int,
    delay_status: str,
    root_cause: str,
    severity: str,
    freight_hold: bool,
    inventory_status: str,
) -> dict:
    """
    Builds one complete action record for a single order.
    This is the core output unit used by all four recommendation tools.

    Returns a dict with:
      - Order identifiers and delay facts
      - Priority score (0-100)
      - Responsible team
      - Recommended action sentence
      - Escalation flag and reason
    """
    priority_score = calculate_priority_score(
        delay_days, severity, freight_hold, inventory_status
    )

    escalate = needs_escalation(priority_score, delay_status, freight_hold)

    escalation_reason = (
        get_escalation_reason(priority_score, delay_status, freight_hold, delay_days)
        if escalate else ""
    )

    return {
        "sales_order_no":     sales_order_no,
        "customer_name":      customer_name,
        "scheduled_pick_date": scheduled_pick_date,
        "delay_days":         delay_days,
        "delay_status":       delay_status,
        "root_cause":         root_cause,
        "severity":           severity,
        "priority_score":     priority_score,
        "responsible_team":   get_responsible_team(root_cause),
        "recommended_action": get_action_sentence(root_cause),
        "escalate":           escalate,
        "escalation_reason":  escalation_reason,
    }
