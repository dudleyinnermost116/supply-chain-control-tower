# mcp_server/warehouse_mcp_server.py
#
# Warehouse Agent — Phase 4 of the Supply Chain Control Tower.
# Tracks pick status, staffing issues, equipment problems, and throughput.
#
# Phase 7 update: now reads from SQLite instead of CSV.

from datetime import date
from mcp.server.fastmcp import FastMCP

# OLD: from supply_chain.warehouse_data_loader import load_warehouse_picks
# NEW (Phase 7): reads from SQLite database
from supply_chain.db_loader import load_warehouse_picks_db as load_warehouse_picks

from supply_chain.warehouse_rules import (
    assign_pick_health,
    calculate_pick_delay_days,
    get_pick_recommendation,
    get_warehouse_summary_stats,
)

mcp = FastMCP("warehouse-agent")

# OLD: DATA_FILE = r"...\warehouse_sample.csv"
# NEW (Phase 7): single SQLite database
##DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"
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

TODAY = date.today()


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_pick_status_by_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user asks about the warehouse pick status
    for a specific sales order.

    Input: sales_order_no — the exact order number (for example: SO-1003)

    Returns: warehouse, item, qty to pick, qty picked, pick status,
    pick health, delay days, delay reason, and recommendation.

    Use this when the user asks things like:
    - "Has order SO-1003 been picked yet?"
    - "What is the warehouse status for SO-1009?"
    - "Why hasn't SO-1002 been picked?"
    - "Is there a staffing issue holding up SO-1009?"
    - "What is the pick status for SO-1005?"
    """
    # OLD: rows = load_warehouse_picks(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_warehouse_picks(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            health = assign_pick_health(row, TODAY)
            delay_days = calculate_pick_delay_days(row, TODAY)

            return {
                "pick_id": row.get("pick_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "warehouse_id": row.get("warehouse_id", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "item_no": row.get("item_no", ""),
                "qty_to_pick": row.get("qty_to_pick", 0),
                "qty_picked": row.get("qty_picked", 0),
                "pick_status": row.get("pick_status", ""),
                "pick_health": health,
                "pick_priority": row.get("pick_priority", ""),
                "assigned_picker": row.get("assigned_picker", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "pick_delay_days": delay_days,
                "pick_delay_reason": row.get("pick_delay_reason", ""),
                "equipment_issue": row.get("equipment_issue", "NO"),
                "staffing_flag": row.get("staffing_flag", "NO"),
                "zone": row.get("zone", ""),
                "recommendation": get_pick_recommendation(row, TODAY),
            }

    return {"error": f"No warehouse pick record found for order: {sales_order_no}"}


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_warehouse_summary() -> dict:
    """
    Use this tool when the user wants a high-level overview of current
    warehouse pick operations across all orders and warehouses.

    Returns total pick counts by health status, plus a list of all
    picks that are DELAYED or AT_RISK with their root cause.

    Use this when the user asks things like:
    - "How is the warehouse performing today?"
    - "Give me a warehouse operations summary"
    - "How many picks are delayed?"
    - "What is the pick completion rate?"
    - "Are there any warehouse issues I should know about?"
    """
    # OLD: rows = load_warehouse_picks(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_warehouse_picks(DB_FILE)
    stats = get_warehouse_summary_stats(rows, TODAY)

    problem_picks = []
    for row in rows:
        health = assign_pick_health(row, TODAY)
        if health in ("DELAYED", "AT_RISK"):
            problem_picks.append({
                "pick_id": row.get("pick_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "pick_status": row.get("pick_status", ""),
                "pick_health": health,
                "pick_delay_reason": row.get("pick_delay_reason", ""),
                "equipment_issue": row.get("equipment_issue", "NO"),
                "staffing_flag": row.get("staffing_flag", "NO"),
                "pick_delay_days": calculate_pick_delay_days(row, TODAY),
            })

    return {
        "total_picks": stats["total_picks"],
        "on_track": stats["ON_TRACK"],
        "at_risk": stats["AT_RISK"],
        "delayed": stats["DELAYED"],
        "problem_picks": problem_picks,
    }


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_delayed_picks() -> list:
    """
    Use this tool when the user wants to see only the warehouse picks
    that are delayed — orders that should have been picked but haven't been.

    Returns picks with DELAYED health status sorted by delay days descending.
    Includes root cause (staffing, equipment, system error, blocked) and recommendation.

    Use this when the user asks things like:
    - "Show me all delayed picks"
    - "Which warehouse picks are overdue?"
    - "What orders are stuck in the warehouse?"
    - "Show me picks that haven't started on time"
    - "What is causing warehouse pick delays?"
    """
    # OLD: rows = load_warehouse_picks(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_warehouse_picks(DB_FILE)
    results = []

    for row in rows:
        health = assign_pick_health(row, TODAY)

        if health == "DELAYED":
            delay_days = calculate_pick_delay_days(row, TODAY)
            results.append({
                "pick_id": row.get("pick_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "item_no": row.get("item_no", ""),
                "pick_status": row.get("pick_status", ""),
                "pick_priority": row.get("pick_priority", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "pick_delay_days": delay_days,
                "pick_delay_reason": row.get("pick_delay_reason", ""),
                "equipment_issue": row.get("equipment_issue", "NO"),
                "staffing_flag": row.get("staffing_flag", "NO"),
                "recommendation": get_pick_recommendation(row, TODAY),
            })

    if not results:
        return [{"message": "No delayed picks found. All warehouse picks are on track."}]

    results.sort(key=lambda x: x["pick_delay_days"], reverse=True)
    return results


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_picks_by_warehouse(warehouse_id: str) -> list:
    """
    Use this tool when the user asks about pick operations in a specific
    warehouse. Returns all pick records for that warehouse with health status.

    Input: warehouse_id — for example: WH-01 or WH-02

    Use this when the user asks things like:
    - "What is the pick situation at WH-01?"
    - "Show me all picks at cold storage"
    - "How is WH-02 performing on picks today?"
    - "Are there any issues at WH-01?"
    - "Give me the pick status for warehouse WH-02"
    """
    # OLD: rows = load_warehouse_picks(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_warehouse_picks(DB_FILE)
    results = []

    normalized = warehouse_id.strip().upper()

    for row in rows:
        if row.get("warehouse_id", "").strip().upper() == normalized:
            health = assign_pick_health(row, TODAY)
            results.append({
                "pick_id": row.get("pick_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "item_no": row.get("item_no", ""),
                "pick_status": row.get("pick_status", ""),
                "pick_health": health,
                "qty_to_pick": row.get("qty_to_pick", 0),
                "qty_picked": row.get("qty_picked", 0),
                "pick_delay_days": calculate_pick_delay_days(row, TODAY),
                "pick_delay_reason": row.get("pick_delay_reason", ""),
                "staffing_flag": row.get("staffing_flag", "NO"),
                "equipment_issue": row.get("equipment_issue", "NO"),
            })

    if not results:
        return [{"message": f"No pick records found for warehouse: {normalized}"}]

    health_order = {"DELAYED": 0, "AT_RISK": 1, "ON_TRACK": 2, "UNKNOWN": 3}
    results.sort(key=lambda x: health_order.get(x["pick_health"], 9))
    return results


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_staffing_and_equipment_issues() -> list:
    """
    Use this tool when the user asks about staffing shortages or equipment
    breakdowns causing warehouse pick delays.

    Returns all picks where staffing_flag = YES or equipment_issue = YES,
    regardless of current pick status.

    Use this when the user asks things like:
    - "Are there any staffing issues in the warehouse?"
    - "Which picks are affected by equipment breakdowns?"
    - "Show me all warehouse operational issues"
    - "Is the warehouse short-staffed today?"
    - "What equipment problems are slowing down picks?"
    """
    # OLD: rows = load_warehouse_picks(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_warehouse_picks(DB_FILE)
    results = []

    for row in rows:
        staffing = str(row.get("staffing_flag", "NO")).strip().upper()
        equipment = str(row.get("equipment_issue", "NO")).strip().upper()

        if staffing == "YES" or equipment == "YES":
            health = assign_pick_health(row, TODAY)
            results.append({
                "pick_id": row.get("pick_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "pick_status": row.get("pick_status", ""),
                "pick_health": health,
                "staffing_issue": staffing == "YES",
                "equipment_issue": equipment == "YES",
                "pick_delay_reason": row.get("pick_delay_reason", ""),
                "pick_delay_days": calculate_pick_delay_days(row, TODAY),
                "recommendation": get_pick_recommendation(row, TODAY),
            })

    if not results:
        return [{"message": "No staffing or equipment issues currently flagged."}]

    results.sort(key=lambda x: x["pick_delay_days"], reverse=True)
    return results


if __name__ == "__main__":
    mcp.run()