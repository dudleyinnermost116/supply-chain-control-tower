# mcp_server/recommendation_mcp_server.py
#
# Owner: Vishal
# Recommendation Agent — Phase 6 of the Supply Chain Control Tower.
#
# Builds on Phase 5 (Investigation Agent) by turning root cause findings
# into a prioritised, team-assigned action plan.
#
# Answers the question:
#   "Given everything that is wrong today, what should my team do,
#    in what order, and who is responsible for each item?"
#
# This agent loads data from all four tables (same as investigation agent)
# and runs the full investigation logic internally before scoring.
#
# Tools in this server:
#   get_action_plan              — full prioritised work queue for today
#   get_team_workload            — actions grouped by responsible team
#   get_escalation_list          — orders that need manager attention now
#   get_recommendation_for_order — single order priority + action
#
# SECURITY FIXES ADDED (Phase 10):
#   - sanitise_input on get_recommendation_for_order which accepts sales_order_no
#   - shield_row / shield_rows on all return values containing database text
#   - sys.path fix so imports work regardless of Claude Desktop launch location
#   - get_database_path() replaces all four hardcoded file paths

import sys
import os

# PHASE 10 CHANGE: sys.path fix
# Ensures Python can find supply_chain and config modules
# regardless of where Claude Desktop launches the server from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from mcp.server.fastmcp import FastMCP

# ── Data loaders ──────────────────────────────────────────────────────────────
from supply_chain.data_loader import load_shipments
from supply_chain.inventory_data_loader import load_inventory
from supply_chain.freight_data_loader import load_freight
from supply_chain.warehouse_data_loader import load_warehouse_picks

# ── Rules engines ─────────────────────────────────────────────────────────────
from supply_chain.rules import (
    assign_delay_status,
    assign_reason_code,
    calculate_delay_days,
)
from supply_chain.inventory_rules import assign_inventory_status
from supply_chain.freight_rules import assign_freight_status, assign_carrier_tier
from supply_chain.warehouse_rules import assign_pick_health

# ── Investigation logic (Phase 5) ─────────────────────────────────────────────
from supply_chain.investigation_rules import (
    build_investigation_report,
    resolve_root_cause,
    score_severity,
)

# ── Recommendation logic (Phase 6) ────────────────────────────────────────────
from supply_chain.recommendation_engine import build_action_record

# SECURITY FIX:
# sanitise_input — validates string inputs before use
# shield_row     — scans a single result dict for injection text
# shield_rows    — scans a list of result dicts for injection text
from supply_chain.input_validation import sanitise_input
from supply_chain.prompt_injection_shield import shield_rows, shield_row

# PHASE 10 CHANGE: Central Settings
# get_database_path() reads from config/settings.yaml
# Replaces all four hardcoded file path lines
from config.settings_loader import get_database_path
DB_FILE = get_database_path()

mcp = FastMCP("recommendation-agent")

TODAY = date.today()


# ─── SHARED HELPER: index rows by a key field ────────────────────────────────

def _index_by(rows: list, key: str) -> dict:
    """Returns a dict mapping key -> first matching row. Same as investigation agent."""
    result = {}
    for row in rows:
        k = str(row.get(key, "")).strip()
        if k and k not in result:
            result[k] = row
    return result


# ─── SHARED HELPER: build one action record for a shipment row ───────────────

def _build_record_for_row(ship_row: dict, inventory_index: dict,
                           freight_index: dict, warehouse_index: dict) -> dict:
    """
    Runs the full investigation + recommendation pipeline for one shipment row.
    Returns a complete action record dict ready for any of the four tools.

    This helper is called by every tool in this server.
    It gathers signals from all four agents, resolves root cause,
    scores severity, and builds the final prioritised action record.
    """
    sales_order_no = str(ship_row.get("sales_order_no", "")).strip()
    item_no        = str(ship_row.get("item_no", "")).strip()

    # ── Shipping signals ──────────────────────────────────────────────────────
    delay_status    = assign_delay_status(ship_row, TODAY)
    delay_days      = calculate_delay_days(ship_row, TODAY)
    shipping_reason = assign_reason_code(ship_row, TODAY)

    # ── Inventory signals ─────────────────────────────────────────────────────
    inv_row          = inventory_index.get(item_no, {})
    inventory_status = assign_inventory_status(inv_row) if inv_row else "UNKNOWN"

    # ── Freight signals ───────────────────────────────────────────────────────
    frt_row             = freight_index.get(sales_order_no, {})
    freight_status      = assign_freight_status(frt_row, TODAY) if frt_row else "UNKNOWN"
    freight_hold        = str(frt_row.get("freight_hold_flag", "NO")).strip().upper() == "YES" if frt_row else False
    freight_hold_reason = frt_row.get("freight_hold_reason", "") if frt_row else ""
    carrier_name        = frt_row.get("carrier_name", "Unknown") if frt_row else "Unknown"
    carrier_tier        = assign_carrier_tier(frt_row.get("carrier_performance_score", "")) if frt_row else "UNKNOWN"

    # ── Warehouse signals ─────────────────────────────────────────────────────
    wh_row      = warehouse_index.get(sales_order_no, {})
    pick_health = assign_pick_health(wh_row, TODAY) if wh_row else "UNKNOWN"

    # ── Phase 5: resolve root cause and severity ──────────────────────────────
    root_cause = resolve_root_cause(
        shipping_reason, freight_status, inventory_status, pick_health
    )
    severity = score_severity(
        delay_days, freight_hold, inventory_status, pick_health
    )

    # ── Phase 6: build the scored action record ───────────────────────────────
    # build_action_record returns a dict with priority_score, responsible_team,
    # recommended_action, escalate flag, and escalation_reason
    return build_action_record(
        sales_order_no      = sales_order_no,
        customer_name       = ship_row.get("customer_name", ""),
        scheduled_pick_date = ship_row.get("scheduled_pick_date", ""),
        delay_days          = delay_days,
        delay_status        = delay_status,
        root_cause          = root_cause,
        severity            = severity,
        freight_hold        = freight_hold,
        inventory_status    = inventory_status,
    )


# ─── SHARED HELPER: load all four data sources and build indexes ──────────────

def _load_all():
    """
    Loads all four data sources and returns rows + lookup indexes.
    Called at the start of every tool in this server.

    Why one function for all four: every tool needs all four sources.
    Centralising this means if we add a fifth data source, we update
    one function instead of four tools.
    """
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    return ship_rows, inventory_index, freight_index, warehouse_index


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST — each record contains customer_name (database text)
#     and recommended_action (text string) → shield_rows on return

@mcp.tool()
def get_action_plan() -> list:
    """
    Use this tool when the user wants a complete prioritised action plan
    for today — a ranked work queue of every delayed order with the
    responsible team and recommended action clearly assigned.

    Returns all delayed or at-risk orders sorted by priority score
    from highest (most urgent) to lowest. Each record includes:
    - Priority score (0-100)
    - Root cause and severity
    - Responsible team
    - Recommended action
    - Escalation flag

    Use this when the user asks things like:
    - "What should my team work on today?"
    - "Give me today's action plan"
    - "What are the highest priority orders right now?"
    - "Show me the work queue for today"
    - "Prioritise all delayed orders for me"
    - "What do I tackle first?"
    - "Give me a ranked list of problems to fix"
    """
    ship_rows, inventory_index, freight_index, warehouse_index = _load_all()

    results = []

    for ship_row in ship_rows:
        delay_status = assign_delay_status(ship_row, TODAY)

        # Skip shipped and cancelled — nothing to action
        if delay_status in ("SHIPPED", "CANCELLED"):
            continue

        record = _build_record_for_row(
            ship_row, inventory_index, freight_index, warehouse_index
        )

        # Only include orders that actually have a problem
        if record["priority_score"] > 0:
            results.append(record)

    if not results:
        return [{"message": "No delayed or at-risk orders found. All orders are on track."}]

    # Highest priority score first
    results.sort(key=lambda x: x["priority_score"], reverse=True)

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # customer_name is raw database text
    # recommended_action and escalation_reason are text strings
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a dict containing team_buckets — lists of action records
#     with customer_name (database text) → shield_row on the final return

@mcp.tool()
def get_team_workload() -> dict:
    """
    Use this tool when the user wants to see what each team needs to do
    today, grouped by responsible team. Each team only sees their own orders.

    Returns a dict where each key is a team name and the value is a list
    of orders assigned to that team, sorted by priority score.

    Also includes a summary count per team so managers can see at a glance
    which teams are most overloaded.

    Use this when the user asks things like:
    - "What does the warehouse team need to do today?"
    - "Show me the freight team's workload"
    - "Which team has the most work right now?"
    - "Group today's actions by team"
    - "What is the procurement team responsible for?"
    - "Show me workload by department"
    - "Who owns each delayed order?"
    """
    ship_rows, inventory_index, freight_index, warehouse_index = _load_all()

    # team_name -> list of action records for that team
    team_buckets = {}

    for ship_row in ship_rows:
        delay_status = assign_delay_status(ship_row, TODAY)

        if delay_status in ("SHIPPED", "CANCELLED"):
            continue

        record = _build_record_for_row(
            ship_row, inventory_index, freight_index, warehouse_index
        )

        if record["priority_score"] == 0:
            continue

        team = record["responsible_team"]
        if team not in team_buckets:
            team_buckets[team] = []
        team_buckets[team].append(record)

    if not team_buckets:
        return {"message": "No actions required. All orders are on track."}

    # Sort each team's orders by priority score descending
    for team in team_buckets:
        team_buckets[team].sort(key=lambda x: x["priority_score"], reverse=True)

    # Summary count so the user can see team workload at a glance
    summary = {
        team: len(orders)
        for team, orders in team_buckets.items()
    }

    # SECURITY FIX: shield_row applied to the full result dict
    # team_buckets contains records with customer_name (database text)
    # REPLACES the old direct return statement
    return shield_row({
        "team_summary": summary,
        "workload_by_team": team_buckets,
    })


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST of escalated action records with customer_name → shield_rows

@mcp.tool()
def get_escalation_list() -> list:
    """
    Use this tool when the user wants to see only the orders that need
    manager escalation right now — the most critical subset of the action plan.

    An order is escalated if ANY of these are true:
    - Priority score is 70 or above
    - Delay status is NEED_ACTION (more than 5 days overdue)
    - An active freight hold is physically blocking the shipment

    Returns escalated orders sorted by priority score with the specific
    reason why each order needs escalation.

    Use this when the user asks things like:
    - "What needs to be escalated today?"
    - "Show me the critical orders for my manager"
    - "Which orders need immediate escalation?"
    - "What should I flag in the morning meeting?"
    - "Show me everything above the escalation threshold"
    - "What are the most critical delays right now?"
    - "Which orders need senior attention?"
    """
    ship_rows, inventory_index, freight_index, warehouse_index = _load_all()

    results = []

    for ship_row in ship_rows:
        delay_status = assign_delay_status(ship_row, TODAY)

        if delay_status in ("SHIPPED", "CANCELLED"):
            continue

        record = _build_record_for_row(
            ship_row, inventory_index, freight_index, warehouse_index
        )

        # escalate is a boolean set by needs_escalation() in recommendation_engine.py
        # True when: priority_score >= 70 OR delay_status == NEED_ACTION OR freight_hold active
        if record["escalate"]:
            results.append(record)

    if not results:
        return [{"message": "No orders require escalation at this time. All delays are within normal thresholds."}]

    results.sort(key=lambda x: x["priority_score"], reverse=True)

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # customer_name is raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - Has input parameter (sales_order_no) → sanitise_input at TOP
#   - Returns a single action record dict with customer_name → shield_row on return

@mcp.tool()
def get_recommendation_for_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user asks for the recommendation or action plan
    for a specific sales order. This is the single-order version of
    get_action_plan — it combines Phase 5 investigation with Phase 6
    priority scoring into one complete response.

    Input: sales_order_no — the exact order number (for example: SO-1003)

    Returns:
    - Full delay and root cause details
    - Priority score (0-100) and severity
    - Responsible team and recommended action
    - Escalation flag and reason if applicable

    Use this when the user asks things like:
    - "What is the recommendation for SO-1003?"
    - "What should I do about order SO-1007?"
    - "Give me the action plan for SO-1005"
    - "What is the priority score for SO-1009?"
    - "Who owns the resolution for SO-1002?"
    - "Does SO-1003 need escalation?"
    - "What is the next step for this order?"
    """
    # SECURITY FIX: validate sales_order_no before loading any data
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    ship_rows, inventory_index, freight_index, warehouse_index = _load_all()

    for ship_row in ship_rows:
        if str(ship_row.get("sales_order_no", "")).strip() == sales_order_no:
            record = _build_record_for_row(
                ship_row, inventory_index, freight_index, warehouse_index
            )
            # SECURITY FIX: shield_row wraps the action record dict
            # customer_name is raw database text
            # REPLACES the old line: return record
            return shield_row(record)

    return {"error": f"Sales order {sales_order_no} was not found."}


if __name__ == "__main__":
    mcp.run()