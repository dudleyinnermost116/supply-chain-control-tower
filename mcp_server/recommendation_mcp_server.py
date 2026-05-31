# mcp_server/recommendation_mcp_server.py
#
# Recommendation Agent — Phase 6 of the Supply Chain Control Tower.
# Turns root cause findings into a prioritised, team-assigned action plan.
#
# Phase 7 update: now reads from SQLite instead of CSV.

from datetime import date
from mcp.server.fastmcp import FastMCP

# OLD: individual CSV loaders
# from supply_chain.data_loader import load_shipments
# from supply_chain.inventory_data_loader import load_inventory
# from supply_chain.freight_data_loader import load_freight
# from supply_chain.warehouse_data_loader import load_warehouse_picks
#
# NEW (Phase 7): single SQLite database loader
from supply_chain.db_loader import (
    load_shipments_db       as load_shipments,
    load_inventory_db       as load_inventory,
    load_freight_db         as load_freight,
    load_warehouse_picks_db as load_warehouse_picks,
)

from supply_chain.rules import (
    assign_delay_status,
    assign_reason_code,
    calculate_delay_days,
)
from supply_chain.inventory_rules import assign_inventory_status
from supply_chain.freight_rules import assign_freight_status, assign_carrier_tier
from supply_chain.warehouse_rules import assign_pick_health
from supply_chain.investigation_rules import (
    build_investigation_report,
    resolve_root_cause,
    score_severity,
)
from supply_chain.recommendation_engine import build_action_record

mcp = FastMCP("recommendation-agent")

TODAY = date.today()

# OLD: four separate CSV file paths
# SHIPMENTS_FILE = r"...\shipments_sample.csv"  etc.
#
# NEW (Phase 7): one SQLite database
# DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"

# ── PHASE 10 CHANGE: Central Settings (Step 2) ───────────────────────────────
#
# WHAT WAS HERE BEFORE:
#   DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"
#
# HISTORY — WHY THIS LINE CHANGED TWICE:
#   Phase 1–6:  Each server had a hardcoded DATA_FILE pointing to its own CSV.
#               e.g. DATA_FILE = r"...\data\shipments_sample.csv"
#
#   Phase 7:    We migrated from individual CSV files to a single SQLite
#               database (supply_chain.db). At that point, every server
#               replaced their DATA_FILE line with a DB_FILE line pointing
#               to the .db file. Still hardcoded, but now one file instead
#               of five different CSVs.
#
#   Phase 10:   Now we remove the last hardcoded path. get_database_path()
#               reads the database path from config\settings.yaml instead
#               of having it typed here. If the .db file ever moves, you
#               change one line in settings.yaml and all servers update.
#
# WHAT get_database_path() DOES:
#   It reads paths.database from settings.yaml, combines it with paths.base,
#   and returns the full absolute path to supply_chain.db.
#   It is defined in config\settings_loader.py which we built in Step 2.
#
# HOW TO ROLL BACK (if something breaks):
#   Comment out the two new lines below and uncomment the original DB_FILE
#   line above. The server will work exactly as it did before.
# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10 CHANGE: replaced relative sys.path with absolute path
# The old line used os.path.join with relative parts which could fail
# when Claude Desktop launches the server from an unknown working directory.
# os.path.abspath(__file__) always gives the true location of this file
# regardless of where Python was launched from.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings_loader import get_database_path
DB_FILE = get_database_path()

# ─── SHARED HELPER: index rows by a key field ────────────────────────────────

def _index_by(rows: list, key: str) -> dict:
    """Returns a dict mapping key -> first matching row."""
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
    """
    sales_order_no  = str(ship_row.get("sales_order_no", "")).strip()
    item_no         = str(ship_row.get("item_no", "")).strip()

    # Shipping signals
    delay_status    = assign_delay_status(ship_row, TODAY)
    delay_days      = calculate_delay_days(ship_row, TODAY)
    shipping_reason = assign_reason_code(ship_row, TODAY)

    # Inventory signals
    inv_row          = inventory_index.get(item_no, {})
    inventory_status = assign_inventory_status(inv_row) if inv_row else "UNKNOWN"

    # Freight signals
    frt_row             = freight_index.get(sales_order_no, {})
    freight_status      = assign_freight_status(frt_row, TODAY) if frt_row else "UNKNOWN"
    freight_hold        = str(frt_row.get("freight_hold_flag", "NO")).strip().upper() == "YES" if frt_row else False
    freight_hold_reason = frt_row.get("freight_hold_reason", "") if frt_row else ""
    carrier_name        = frt_row.get("carrier_name", "Unknown") if frt_row else "Unknown"
    carrier_tier        = assign_carrier_tier(frt_row.get("carrier_performance_score", "")) if frt_row else "UNKNOWN"

    # Warehouse signals
    wh_row      = warehouse_index.get(sales_order_no, {})
    pick_health = assign_pick_health(wh_row, TODAY) if wh_row else "UNKNOWN"

    # Phase 5: resolve root cause and severity
    root_cause = resolve_root_cause(
        shipping_reason, freight_status, inventory_status, pick_health
    )
    severity = score_severity(
        delay_days, freight_hold, inventory_status, pick_health
    )

    # Phase 6: build the scored action record
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


# ─── SHARED HELPER: load all four tables and build indexes ───────────────────

def _load_all():
    """Loads all four tables from SQLite and returns rows + indexes."""
    # OLD: load_shipments(SHIPMENTS_FILE), etc.
    # NEW (Phase 7): all from single DB_FILE
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    return ship_rows, inventory_index, freight_index, warehouse_index


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────

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

        if delay_status in ("SHIPPED", "CANCELLED"):
            continue

        record = _build_record_for_row(
            ship_row, inventory_index, freight_index, warehouse_index
        )

        if record["priority_score"] > 0:
            results.append(record)

    if not results:
        return [{"message": "No delayed or at-risk orders found. All orders are on track."}]

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────

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

    for team in team_buckets:
        team_buckets[team].sort(key=lambda x: x["priority_score"], reverse=True)

    summary = {team: len(orders) for team, orders in team_buckets.items()}

    return {
        "team_summary": summary,
        "workload_by_team": team_buckets,
    }


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────

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

        if record["escalate"]:
            results.append(record)

    if not results:
        return [{"message": "No orders require escalation at this time. All delays are within normal thresholds."}]

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────

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
    ship_rows, inventory_index, freight_index, warehouse_index = _load_all()

    for ship_row in ship_rows:
        if str(ship_row.get("sales_order_no", "")).strip() == sales_order_no:
            record = _build_record_for_row(
                ship_row, inventory_index, freight_index, warehouse_index
            )
            return record

    return {"error": f"Sales order {sales_order_no} was not found."}


if __name__ == "__main__":
    mcp.run()