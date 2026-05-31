# mcp_server/po_mcp_server.py
#
# Purchase Order Agent — Phase 3 of the Supply Chain Control Tower.
# Tracks inbound supplier orders and delivery performance.
#
# Phase 7 update: now reads from SQLite instead of CSV.
#
# Rules engine is in src/supply_chain/po_rules.py
# Functions used from that file:
#   assign_po_status(row, today)         — returns RECEIVED, CANCELLED, PARTIAL, LATE, ON_TIME
#   calculate_days_late(row, today)      — returns how many days overdue the PO is
#   get_po_recommendation(po_status, days_late, supplier_name, item_no, expected_receipt_date)
#   calculate_po_value(row)              — returns qty_outstanding * unit_cost

from datetime import date
from mcp.server.fastmcp import FastMCP

# OLD: from supply_chain.po_data_loader import load_purchase_orders
# NEW (Phase 7): reads from SQLite database instead of CSV
from supply_chain.db_loader import load_purchase_orders_db as load_purchase_orders

# These are the four functions that exist in po_rules.py
# We import only what we actually use in this file
from supply_chain.po_rules import (
    assign_po_status,
    calculate_days_late,
    get_po_recommendation,
    calculate_po_value,
)

# FastMCP is the framework that turns Python functions into MCP tools
# The string "po-agent" is the name Claude Desktop sees for this server
mcp = FastMCP("po-agent")

# OLD: DATA_FILE = r"...\purchase_orders_sample.csv"
# NEW (Phase 7): single SQLite database shared by all agents
#DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"

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

# date.today() gives us today's real date at the moment the tool is called
# We use this to calculate whether a PO is late
TODAY = date.today()


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# This tool answers: "What POs are still open and waiting to be received?"
# It skips anything already RECEIVED or CANCELLED — only shows active orders.

@mcp.tool()
def get_open_purchase_orders() -> list:
    """
    Use this tool when the user wants to see all purchase orders that
    are still open — not yet fully received or cancelled.

    Returns all POs with outstanding quantities, sorted by expected
    receipt date so the most overdue appear first.

    Use this when the user asks things like:
    - "Show me all open purchase orders"
    - "What POs are still outstanding?"
    - "Which supplier orders haven't arrived yet?"
    - "What are we still waiting on from suppliers?"
    - "List all open POs"
    """
    # Load all PO rows from the SQLite database
    rows = load_purchase_orders(DB_FILE)
    results = []

    for row in rows:
        # assign_po_status() reads the row and returns one of:
        # RECEIVED, CANCELLED, PARTIAL, LATE, ON_TIME
        status = assign_po_status(row, TODAY)

        # We only want open POs — skip anything already closed
        if status not in ("RECEIVED", "CANCELLED"):
            results.append({
                "po_number":             row.get("po_number", ""),
                "po_line":               row.get("po_line", ""),
                "item_no":               row.get("item_no", ""),
                "item_description":      row.get("item_description", ""),
                "supplier_name":         row.get("supplier_name", ""),
                "qty_ordered":           row.get("qty_ordered", 0),
                "qty_received":          row.get("qty_received", 0),
                "qty_outstanding":       row.get("qty_outstanding", 0),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "po_status":             status,
            })

    if not results:
        return [{"message": "No open purchase orders found."}]

    # Sort by expected_receipt_date ascending so the most overdue appear first.
    # The "or 9999" trick means rows with no date sort to the bottom
    # instead of crashing when Python tries to compare None to a string.
    results.sort(key=lambda x: x.get("expected_receipt_date") or "9999")
    return results


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# This tool answers: "Which POs have passed their expected delivery date?"
# A PO is late when assign_po_status() returns "LATE".

@mcp.tool()
def get_late_purchase_orders() -> list:
    """
    Use this tool when the user wants to see purchase orders that are
    overdue — the expected receipt date has passed and they haven't
    been fully received yet.

    Returns all late POs sorted by delay days descending (worst first).

    Use this when the user asks things like:
    - "Which purchase orders are late?"
    - "What supplier deliveries are overdue?"
    - "Show me all late POs"
    - "Which suppliers are behind on deliveries?"
    - "What inbound orders are past their expected date?"
    """
    rows = load_purchase_orders(DB_FILE)
    results = []

    for row in rows:
        status = assign_po_status(row, TODAY)

        # Only include POs where the status came back as LATE
        if status == "LATE":
            # calculate_days_late() returns how many calendar days past
            # the expected receipt date we are right now
            days_late = calculate_days_late(row, TODAY)

            # get_po_recommendation() needs individual values, not the whole row
            # so we pull each value out separately before passing them in
            recommendation = get_po_recommendation(
                po_status             = status,
                days_late             = days_late,
                supplier_name         = row.get("supplier_name", ""),
                item_no               = row.get("item_no", ""),
                expected_receipt_date = row.get("expected_receipt_date", ""),
            )

            results.append({
                "po_number":             row.get("po_number", ""),
                "po_line":               row.get("po_line", ""),
                "item_no":               row.get("item_no", ""),
                "item_description":      row.get("item_description", ""),
                "supplier_name":         row.get("supplier_name", ""),
                "qty_outstanding":       row.get("qty_outstanding", 0),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "days_late":             days_late,
                "po_status":             status,
                "recommendation":        recommendation,
            })

    if not results:
        return [{"message": "No late purchase orders found. All supplier deliveries are on track."}]

    # Sort worst delays first — most days late at the top
    results.sort(key=lambda x: x["days_late"], reverse=True)
    return results


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# This tool answers: "What POs exist for a specific item?"
# Used when investigating why an item is on backorder or short.

@mcp.tool()
def get_po_by_item(item_no: str) -> list:
    """
    Use this tool when the user wants to see all purchase orders for a
    specific item. Useful for checking inbound supply for a delayed order.

    Input: item_no — the exact item number (for example: ITEM-003)

    Returns all POs for that item with status and outstanding quantities.

    Use this when the user asks things like:
    - "Are there any POs for ITEM-003?"
    - "What is inbound for ITEM-005?"
    - "Is there a PO covering the backorder on ITEM-002?"
    - "Show me all purchase orders for ITEM-007"
    - "When will we receive more of ITEM-004?"
    """
    rows = load_purchase_orders(DB_FILE)
    results = []

    for row in rows:
        # String comparison — only include rows where item_no matches exactly
        if row.get("item_no", "") == item_no:
            status = assign_po_status(row, TODAY)
            results.append({
                "po_number":             row.get("po_number", ""),
                "po_line":               row.get("po_line", ""),
                "supplier_name":         row.get("supplier_name", ""),
                "qty_ordered":           row.get("qty_ordered", 0),
                "qty_received":          row.get("qty_received", 0),
                "qty_outstanding":       row.get("qty_outstanding", 0),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "actual_receipt_date":   row.get("actual_receipt_date", ""),
                "po_status":             status,
            })

    if not results:
        return [{"message": f"No purchase orders found for item: {item_no}"}]

    return results


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# This tool answers: "How is each supplier performing overall?"
# It groups all PO rows by supplier and counts how many are late vs on time.

@mcp.tool()
def get_supplier_summary() -> list:
    """
    Use this tool when the user wants to understand how each supplier is
    performing — which suppliers are delivering on time and which are late.

    Aggregates all PO records by supplier and returns:
    - Total PO lines per supplier
    - How many are on time, late, partial, or received
    - Whether any are currently overdue

    Results are sorted so suppliers with the most late orders appear first.

    Use this when the user asks things like:
    - "Which supplier is causing the most delays?"
    - "Give me a supplier performance summary"
    - "How reliable are our suppliers?"
    - "Which suppliers have late deliveries right now?"
    - "Show me supplier on-time performance"
    """
    rows = load_purchase_orders(DB_FILE)

    # supplier_data is a dictionary where:
    #   key   = supplier name (string)
    #   value = another dictionary with counts for that supplier
    # We build this up row by row as we loop through the POs.
    supplier_data = {}

    for row in rows:
        supplier = row.get("supplier_name", "Unknown")
        status = assign_po_status(row, TODAY)

        # If we haven't seen this supplier before, create a fresh record for them
        if supplier not in supplier_data:
            supplier_data[supplier] = {
                "supplier_name":  supplier,
                "supplier_id":    row.get("supplier_id", ""),
                "total_po_lines": 0,
                "on_time":        0,
                "late":           0,
                "partial":        0,
                "received":       0,
                "cancelled":      0,
            }

        # Increment the total count for this supplier
        supplier_data[supplier]["total_po_lines"] += 1

        # Increment the right status bucket
        # This maps the status string to the matching key in the dict above
        status_key_map = {
            "ON_TIME":   "on_time",
            "LATE":      "late",
            "PARTIAL":   "partial",
            "RECEIVED":  "received",
            "CANCELLED": "cancelled",
        }
        key = status_key_map.get(status, "on_time")
        supplier_data[supplier][key] += 1

    if not supplier_data:
        return [{"message": "No purchase order records found."}]

    # Convert the dictionary of suppliers into a plain list for the response
    results = list(supplier_data.values())

    # Sort so suppliers with the most late POs appear at the top
    results.sort(key=lambda x: x["late"], reverse=True)
    return results


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────
# This is the cross-agent tool — used when another agent finds a backorder
# or inventory shortage and wants to know if a PO already covers it.

@mcp.tool()
def check_po_for_order(item_no: str) -> dict:
    """
    Use this tool when the user wants to know if there is an inbound
    purchase order that will cover a backorder or inventory shortage
    for a specific item. This is the cross-agent tool for the PO agent.

    Input: item_no — the item number to check (for example: ITEM-004)

    Returns: whether an open PO exists, the earliest expected receipt date,
    total quantity inbound, and a recommendation.

    Use this when the user asks things like:
    - "Is there a PO that will cover the backorder on ITEM-004?"
    - "When will we get more stock for ITEM-002?"
    - "Is there inbound supply for ITEM-007?"
    - "Check if there is a PO covering the shortage on ITEM-003"
    - "Will the supplier deliver ITEM-005 soon?"
    """
    rows = load_purchase_orders(DB_FILE)

    # Collect all open POs for this item (not received, not cancelled)
    matching_pos = []

    for row in rows:
        if row.get("item_no", "") == item_no:
            status = assign_po_status(row, TODAY)

            # Only care about POs that still have outstanding qty to deliver
            if status not in ("RECEIVED", "CANCELLED"):
                days_late = calculate_days_late(row, TODAY)
                matching_pos.append({
                    "po_number":             row.get("po_number", ""),
                    "supplier_name":         row.get("supplier_name", ""),
                    "qty_outstanding":       row.get("qty_outstanding", 0),
                    "expected_receipt_date": row.get("expected_receipt_date", ""),
                    "po_status":             status,
                    "days_late":             days_late,
                })

    # If no open POs were found, tell the user to raise one immediately
    if not matching_pos:
        return {
            "item_no":        item_no,
            "open_po_exists": False,
            "message": (
                f"No open purchase orders found for item {item_no}. "
                "Consider raising an emergency PO immediately."
            ),
        }

    # Sort by expected receipt date so the soonest delivery appears first
    matching_pos.sort(key=lambda x: x.get("expected_receipt_date") or "9999")

    # Sum all outstanding qty across all open POs for this item
    total_inbound = sum(p["qty_outstanding"] for p in matching_pos)

    # The earliest date is the first item after sorting
    earliest_date = matching_pos[0]["expected_receipt_date"]

    # Check if any of the open POs are already late
    any_late = any(p["days_late"] > 0 for p in matching_pos)

    # Build a plain-English recommendation using get_po_recommendation()
    # We pass the status of the first (most urgent) PO
    first_po = matching_pos[0]
    recommendation = get_po_recommendation(
        po_status             = first_po["po_status"],
        days_late             = first_po["days_late"],
        supplier_name         = first_po["supplier_name"],
        item_no               = item_no,
        expected_receipt_date = first_po["expected_receipt_date"],
    )

    return {
        "item_no":               item_no,
        "open_po_exists":        True,
        "total_qty_inbound":     total_inbound,
        "earliest_receipt_date": earliest_date,
        "any_po_late":           any_late,
        "open_pos":              matching_pos,
        "recommendation":        recommendation,
    }


if __name__ == "__main__":
    mcp.run()