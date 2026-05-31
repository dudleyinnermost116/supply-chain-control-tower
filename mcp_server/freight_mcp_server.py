# mcp_server/freight_mcp_server.py
#
# Freight Agent — Phase 4 of the Supply Chain Control Tower.
# Tracks carrier performance, freight holds, and pickup status.
#
# Phase 7 update: now reads from SQLite instead of CSV.

from datetime import date
from mcp.server.fastmcp import FastMCP

# OLD: from supply_chain.freight_data_loader import load_freight
# NEW (Phase 7): reads from SQLite database
from supply_chain.db_loader import load_freight_db as load_freight

from supply_chain.freight_rules import (
    assign_freight_status,
    assign_carrier_tier,
    calculate_pickup_delay_days,
    get_freight_recommendation,
    get_hold_severity,
)

mcp = FastMCP("freight-agent")

# OLD: DATA_FILE = r"...\freight_sample.csv"
# NEW (Phase 7): single SQLite database
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
# ── PHASE 10 CHANGE: Central Settings (Step 2) ───────────────────────────────
#
# WHAT WAS HERE BEFORE:
#   DB_FILE = r"C:\Users\preet\..."
# ...
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings_loader import get_database_path
DB_FILE = get_database_path()

TODAY = date.today()


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────

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
    # OLD: rows = load_freight(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_freight(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_freight_status(row, TODAY)
            delay_days = calculate_pickup_delay_days(row, TODAY)
            carrier_tier = assign_carrier_tier(row.get("carrier_performance_score", ""))

            return {
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
            }

    return {"error": f"No freight record found for order: {sales_order_no}"}


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────

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
    # OLD: rows = load_freight(DATA_FILE)
    # NEW (Phase 7): load from SQLite
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

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
    results.sort(key=lambda x: (severity_order.get(x["hold_severity"], 9), -x["pickup_delay_days"]))
    return results


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────

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
    # OLD: rows = load_freight(DATA_FILE)
    # NEW (Phase 7): load from SQLite
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
    return results


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────

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
    # OLD: rows = load_freight(DATA_FILE)
    # NEW (Phase 7): load from SQLite
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

    def score_sort(c):
        try:
            return int(str(c["performance_score"]).strip())
        except (ValueError, TypeError):
            return 999

    results.sort(key=score_sort)
    return results


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────

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
    # OLD: rows = load_freight(DATA_FILE)
    # NEW (Phase 7): load from SQLite
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
    return results


if __name__ == "__main__":
    mcp.run()