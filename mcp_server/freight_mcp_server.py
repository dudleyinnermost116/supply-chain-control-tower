# mcp_server/freight_mcp_server.py
#
# Owner: Vishal
# Freight Agent — Phase 4 of the Supply Chain Control Tower.
# Tracks carrier performance, freight holds, and pickup status.
#
# Answers the question: "Why hasn't the carrier picked this up?"
#
# Works alongside:
#   shipping_mcp_server.py  — outbound delay status
#   warehouse_mcp_server.py — internal pick operations
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
# Ensures Python can find the supply_chain and config modules
# regardless of where Claude Desktop launches the server from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from mcp.server.fastmcp import FastMCP

from supply_chain.freight_data_loader import load_freight
from supply_chain.freight_rules import (
    assign_freight_status,
    assign_carrier_tier,
    calculate_pickup_delay_days,
    get_freight_recommendation,
    get_hold_severity,
)

# SECURITY FIX:
# sanitise_input — validates string inputs before use
# shield_row     — scans a single result dict for injection text
# shield_rows    — scans a list of result dicts for injection text
from supply_chain.input_validation import sanitise_input
from supply_chain.prompt_injection_shield import shield_rows, shield_row

# PHASE 10 CHANGE: Central Settings
# Replaces the old hardcoded line:
#   DATA_FILE = r"C:\Users\preet\...\data\freight_sample.csv"
from config.settings_loader import get_database_path
DB_FILE = get_database_path()

mcp = FastMCP("freight-agent")

TODAY = date.today()


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - Has input parameter (sales_order_no) → sanitise_input at TOP
#   - Returns a single dict with text fields like carrier_name,
#     freight_hold_reason, recommendation → shield_row on return

@mcp.tool()
def get_freight_status_by_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user asks about the freight or carrier status
    for a specific sales order. Returns full freight details for that order.

    Input: sales_order_no — the exact order number (for example: SO-1003)

    Returns: carrier name, pickup scheduled date, actual pickup date,
    freight status, hold flag, hold reason, pickup delay days, and recommendation.

    Use this when the user asks things like:
    - "What is the freight status for SO-1003?"
    - "Has the carrier picked up order SO-1006?"
    - "Is there a freight hold on SO-1003?"
    - "Why hasn't SO-1002 been picked up yet?"
    - "What is the carrier doing on order SO-1005?"
    """
    # SECURITY FIX: validate sales_order_no before doing anything
    # max_length=20 — real order numbers like "SO-1003" are 7 chars
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    rows = load_freight(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_freight_status(row, TODAY)
            delay_days = calculate_pickup_delay_days(row, TODAY)
            carrier_tier = assign_carrier_tier(row.get("carrier_performance_score", ""))

            # SECURITY FIX: shield_row wraps the result dict
            # carrier_name, freight_hold_reason, destination are database text
            # recommendation is a generated string but shield_row is a safe layer
            # REPLACES the old direct return statement
            return shield_row({
                "freight_id": row.get("freight_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "carrier_name": row.get("carrier_name", ""),
                "carrier_tier": carrier_tier,
                "carrier_performance_score": row.get("carrier_performance_score", ""),
                "pickup_scheduled_date": row.get("pickup_scheduled_date", ""),
                "pickup_actual_date": row.get("pickup_actual_date", ""),
                "delivery_scheduled_date": row.get("delivery_scheduled_date", ""),
                "delivery_actual_date": row.get("delivery_actual_date", ""),
                "freight_status": status,
                "freight_hold_flag": row.get("freight_hold_flag", "NO"),
                "freight_hold_reason": row.get("freight_hold_reason", ""),
                "truck_available": row.get("truck_available", ""),
                "driver_assigned": row.get("driver_assigned", ""),
                "pickup_delay_days": delay_days,
                "recommendation": get_freight_recommendation(
                    status,
                    row.get("freight_hold_reason", ""),
                    row.get("carrier_name", ""),
                    delay_days,
                ),
            })

    return {"error": f"No freight record found for order: {sales_order_no}"}


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with text fields like carrier_name,
#     freight_hold_reason, destination → shield_rows on return

@mcp.tool()
def get_freight_holds() -> list:
    """
    Use this tool when the user wants to see all shipments currently on
    freight hold — orders that are physically blocked from moving.

    Returns all ON_HOLD freight records sorted by hold severity (HIGH first).
    Each result includes the hold reason, carrier, and recommendation.

    Use this when the user asks things like:
    - "Show me all freight holds"
    - "Which orders are blocked by a freight hold?"
    - "What shipments are on hold right now?"
    - "List all freight hold orders"
    - "What is causing the freight holds today?"
    """
    rows = load_freight(DB_FILE)
    results = []

    for row in rows:
        status = assign_freight_status(row, TODAY)

        if status == "ON_HOLD":
            hold_reason = row.get("freight_hold_reason", "")
            severity = get_hold_severity(hold_reason)
            delay_days = calculate_pickup_delay_days(row, TODAY)

            results.append({
                "freight_id": row.get("freight_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "carrier_name": row.get("carrier_name", ""),
                "freight_hold_reason": hold_reason,
                "hold_severity": severity,
                "pickup_scheduled_date": row.get("pickup_scheduled_date", ""),
                "pickup_delay_days": delay_days,
                "origin_warehouse": row.get("origin_warehouse", ""),
                "destination": row.get("destination", ""),
                "recommendation": get_freight_recommendation(
                    status, hold_reason, row.get("carrier_name", ""), delay_days
                ),
            })

    if not results:
        return [{"message": "No freight holds currently active. All shipments are clear."}]

    # Sort: HIGH severity first, then by delay days descending
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
    results.sort(key=lambda x: (severity_order.get(x["hold_severity"], 9), -x["pickup_delay_days"]))

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # carrier_name, freight_hold_reason, destination are raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with text fields → shield_rows on return

@mcp.tool()
def get_missed_pickups() -> list:
    """
    Use this tool when the user wants to see all orders where the carrier
    missed the scheduled pickup and has not yet collected the shipment.

    Returns all PICKUP_MISSED records sorted by days overdue (worst first).

    Use this when the user asks things like:
    - "Which carriers missed their pickup?"
    - "Show me all missed pickups"
    - "What orders didn't get picked up on time?"
    - "Which shipments are sitting in the warehouse waiting for a carrier?"
    - "Show me carrier no-shows"
    """
    rows = load_freight(DB_FILE)
    results = []

    for row in rows:
        status = assign_freight_status(row, TODAY)

        if status == "PICKUP_MISSED":
            delay_days = calculate_pickup_delay_days(row, TODAY)
            carrier_tier = assign_carrier_tier(row.get("carrier_performance_score", ""))

            results.append({
                "freight_id": row.get("freight_id", ""),
                "sales_order_no": row.get("sales_order_no", ""),
                "carrier_name": row.get("carrier_name", ""),
                "carrier_tier": carrier_tier,
                "pickup_scheduled_date": row.get("pickup_scheduled_date", ""),
                "pickup_delay_days": delay_days,
                "truck_available": row.get("truck_available", ""),
                "driver_assigned": row.get("driver_assigned", ""),
                "origin_warehouse": row.get("origin_warehouse", ""),
                "destination": row.get("destination", ""),
                "recommendation": get_freight_recommendation(
                    status, "", row.get("carrier_name", ""), delay_days
                ),
            })

    if not results:
        return [{"message": "No missed pickups found. All carriers have collected their shipments."}]

    results.sort(key=lambda x: x["pickup_delay_days"], reverse=True)

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # carrier_name, destination, driver_assigned are raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST — carrier_name comes from the database → shield_rows on return

@mcp.tool()
def get_carrier_performance_summary() -> list:
    """
    Use this tool when the user wants to understand how each carrier is
    performing — which carriers are reliable and which are causing problems.

    Aggregates all freight records by carrier and returns:
    - Total shipments per carrier
    - How many are on hold, missed, or delayed
    - Carrier performance score and tier (STRONG / AVERAGE / WEAK / CRITICAL)

    Results are sorted by performance score ascending so the worst performers
    appear first.

    Use this when the user asks things like:
    - "Which carrier is performing worst?"
    - "Give me a carrier performance summary"
    - "How reliable are our carriers?"
    - "Which carriers are causing the most problems?"
    - "Show me carrier scores"
    - "Who is our best and worst carrier?"
    """
    rows = load_freight(DB_FILE)

    carrier_data = {}

    for row in rows:
        carrier = row.get("carrier_name", "Unknown")
        status = assign_freight_status(row, TODAY)

        if carrier not in carrier_data:
            carrier_data[carrier] = {
                "carrier_name": carrier,
                "carrier_id": row.get("carrier_id", ""),
                "performance_score": row.get("carrier_performance_score", "N/A"),
                "carrier_tier": assign_carrier_tier(row.get("carrier_performance_score", "")),
                "total_shipments": 0,
                "delivered": 0,
                "in_transit": 0,
                "on_hold": 0,
                "pickup_missed": 0,
                "carrier_delayed": 0,
                "scheduled": 0,
            }

        carrier_data[carrier]["total_shipments"] += 1

        status_key_map = {
            "DELIVERED": "delivered",
            "IN_TRANSIT": "in_transit",
            "ON_HOLD": "on_hold",
            "PICKUP_MISSED": "pickup_missed",
            "CARRIER_DELAYED": "carrier_delayed",
            "SCHEDULED": "scheduled",
        }
        key = status_key_map.get(status, "scheduled")
        carrier_data[carrier][key] += 1

    if not carrier_data:
        return [{"message": "No freight records found."}]

    results = list(carrier_data.values())

    # Sort worst performers first (lowest score)
    def score_sort(c):
        try:
            return int(str(c["performance_score"]).strip())
        except (ValueError, TypeError):
            return 999

    results.sort(key=score_sort)

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # carrier_name comes from raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with text fields like carrier_name,
#     freight_hold_reason, destination → shield_rows on return

@mcp.tool()
def get_active_freight() -> list:
    """
    Use this tool when the user wants a full view of all freight records
    that are not yet delivered — everything currently in motion or blocked.

    Returns all non-delivered shipments with their current freight status.
    Sorted so holds and missed pickups appear before in-transit and scheduled.

    Use this when the user asks things like:
    - "What freight is currently active?"
    - "Show me all shipments that haven't been delivered yet"
    - "What is moving and what is stuck?"
    - "Give me a freight overview"
    - "Show me all in-transit and problem shipments"
    """
    rows = load_freight(DB_FILE)
    results = []

    status_priority = {
        "ON_HOLD": 0,
        "PICKUP_MISSED": 1,
        "CARRIER_DELAYED": 2,
        "SCHEDULED": 3,
        "IN_TRANSIT": 4,
    }

    for row in rows:
        status = assign_freight_status(row, TODAY)

        if status == "DELIVERED":
            continue

        delay_days = calculate_pickup_delay_days(row, TODAY)
        results.append({
            "freight_id": row.get("freight_id", ""),
            "sales_order_no": row.get("sales_order_no", ""),
            "carrier_name": row.get("carrier_name", ""),
            "freight_status": status,
            "freight_hold_flag": row.get("freight_hold_flag", "NO"),
            "freight_hold_reason": row.get("freight_hold_reason", ""),
            "pickup_scheduled_date": row.get("pickup_scheduled_date", ""),
            "pickup_delay_days": delay_days,
            "origin_warehouse": row.get("origin_warehouse", ""),
            "destination": row.get("destination", ""),
        })

    if not results:
        return [{"message": "All freight has been delivered. No active shipments."}]

    results.sort(key=lambda x: (status_priority.get(x["freight_status"], 9), -x["pickup_delay_days"]))

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # carrier_name, freight_hold_reason, destination are raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


if __name__ == "__main__":
    mcp.run()