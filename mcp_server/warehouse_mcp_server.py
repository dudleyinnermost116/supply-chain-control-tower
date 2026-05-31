# mcp_server/warehouse_mcp_server.py
#
# Owner: Vishal
# Warehouse Agent — Phase 4 of the Supply Chain Control Tower.
# Tracks pick status, staffing issues, equipment problems, and throughput.
#
# Answers the question: "Why hasn't this order been picked yet?"
#
# Works alongside:
#   freight_mcp_server.py   — carrier and pickup status
#   shipping_mcp_server.py  — outbound delay status
#   inventory_mcp_server.py — stock availability
#   po_mcp_server.py        — inbound supplier orders
#
# SECURITY FIXES ADDED (Phase 10):
#   - sanitise_input on all tools that accept string parameters
#   - shield_row / shield_rows on all return values containing database text
#   - sys.path fix so imports work regardless of Claude Desktop launch location
#   - get_database_path() replaces hardcoded DATA_FILE path

import sys
import os

# PHASE 10 CHANGE: sys.path fix
# Ensures Python can find supply_chain and config modules
# regardless of where Claude Desktop launches the server from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from mcp.server.fastmcp import FastMCP

from supply_chain.warehouse_data_loader import load_warehouse_picks
from supply_chain.warehouse_rules import (
    assign_pick_health,
    calculate_pick_delay_days,
    get_pick_recommendation,
    get_warehouse_summary_stats,
)

# SECURITY FIX:
# sanitise_input — validates string inputs before use
# shield_row     — scans a single result dict for injection text
# shield_rows    — scans a list of result dicts for injection text
from supply_chain.input_validation import sanitise_input
from supply_chain.prompt_injection_shield import shield_rows, shield_row

# PHASE 10 CHANGE: Central Settings
# Replaces the old hardcoded line:
#   DATA_FILE = r"C:\Users\preet\...\data\warehouse_sample.csv"
from config.settings_loader import get_database_path
DB_FILE = get_database_path()

mcp = FastMCP("warehouse-agent")

TODAY = date.today()


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - Has input parameter (sales_order_no) → sanitise_input at TOP
#   - Returns a single dict with text fields like warehouse_name,
#     pick_delay_reason, assigned_picker, recommendation → shield_row on return

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
    # SECURITY FIX: validate sales_order_no before doing anything
    # max_length=20 — real order numbers like "SO-1003" are 7 chars
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    rows = load_warehouse_picks(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            health = assign_pick_health(row, TODAY)
            delay_days = calculate_pick_delay_days(row, TODAY)

            # SECURITY FIX: shield_row wraps the full result dict
            # warehouse_name, pick_delay_reason, assigned_picker, zone
            # are all raw database text — shield_row cleans them
            # REPLACES the old direct return statement
            return shield_row({
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
            })

    return {"error": f"No warehouse pick record found for order: {sales_order_no}"}


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a dict containing problem_picks — a list of dicts with
#     text fields like warehouse_name, pick_delay_reason → shield_row on return

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

    # SECURITY FIX: shield_row wraps the full result dict
    # problem_picks contains warehouse_name and pick_delay_reason
    # which are raw database text fields
    # REPLACES the old direct return statement
    return shield_row({
        "total_picks": stats["total_picks"],
        "on_track": stats["ON_TRACK"],
        "at_risk": stats["AT_RISK"],
        "delayed": stats["DELAYED"],
        "problem_picks": problem_picks,
    })


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with text fields → shield_rows on return

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

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # warehouse_name, pick_delay_reason are raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - Has input parameter (warehouse_id) → sanitise_input at TOP
#   - Returns a LIST with text fields → shield_rows on return

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
    # SECURITY FIX: validate warehouse_id input
    # max_length=20 — real warehouse IDs like "WH-01" are 5 chars
    check = sanitise_input(warehouse_id, field_name="warehouse_id", max_length=20)
    if "error" in check:
        return [check]

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

    # Sort: DELAYED first, then AT_RISK, then ON_TRACK
    health_order = {"DELAYED": 0, "AT_RISK": 1, "ON_TRACK": 2, "UNKNOWN": 3}
    results.sort(key=lambda x: health_order.get(x["pick_health"], 9))

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # pick_delay_reason is raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with text fields like warehouse_name,
#     pick_delay_reason, recommendation → shield_rows on return

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

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # warehouse_name, pick_delay_reason are raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


if __name__ == "__main__":
    mcp.run()