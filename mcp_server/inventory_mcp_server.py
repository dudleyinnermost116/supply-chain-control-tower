# mcp_server/inventory_mcp_server.py
#
# Inventory Agent — second MCP server in the multi-agent architecture.
# Runs independently from shipping_mcp_server.py.
# Claude Desktop connects to both simultaneously.
#
# Phase 7 update: now reads from SQLite instead of CSV.

from mcp.server.fastmcp import FastMCP

# OLD: from supply_chain.inventory_data_loader import load_inventory
# NEW (Phase 7): reads from SQLite database
from supply_chain.db_loader import load_inventory_db as load_inventory

from supply_chain.inventory_rules import (
    assign_inventory_status,
    calculate_shortage,
    can_fulfill,
    get_inventory_recommendation,
)

mcp = FastMCP("inventory-agent")

# OLD: DATA_FILE = r"...\inventory_sample.csv"
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

# ─── TOOL 1 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_summary() -> dict:
    """
    Use this tool when the user wants a high-level overview of current
    inventory health across all items and warehouses.

    Returns counts of items in each status category and a list of
    all items that are on backorder, out of stock, or critical.

    Use this when the user asks things like:
    - "How is our inventory looking?"
    - "Give me an inventory summary"
    - "How many items are out of stock?"
    - "What is the inventory health today?"
    - "Are there any critical stock levels?"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)

    status_counts = {
        "HEALTHY": 0,
        "LOW": 0,
        "CRITICAL": 0,
        "OUT_OF_STOCK": 0,
        "ON_BACKORDER": 0,
    }
    problem_items = []

    for row in rows:
        status = assign_inventory_status(row)
        status_counts[status] = status_counts.get(status, 0) + 1

        if status in ["OUT_OF_STOCK", "CRITICAL", "ON_BACKORDER"]:
            problem_items.append({
                "item_no": row.get("item_no", ""),
                "item_description": row.get("item_description", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "qty_available": row.get("qty_available", 0),
                "status": status,
                "expected_receipt_date": row.get("expected_receipt_date", ""),
            })

    return {
        "total_items": len(rows),
        "status_counts": status_counts,
        "problem_items": problem_items,
    }


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_by_item(item_no: str) -> dict:
    """
    Use this tool when the user asks about a specific inventory item by
    its item number. Returns full stock details for that item.

    Input: item_no — the exact item number (for example: ITEM-001)

    Returns: qty on hand, qty allocated, qty available, reorder point,
    safety stock, backorder flag, inventory status, and recommendation.

    Use this when the user asks things like:
    - "What is the stock level for ITEM-002?"
    - "Is ITEM-007 available?"
    - "Show me inventory for ITEM-004"
    - "How much stock do we have for ITEM-001?"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)

    for row in rows:
        if row.get("item_no", "") == item_no:
            status = assign_inventory_status(row)
            return {
                "item_no": row.get("item_no", ""),
                "item_description": row.get("item_description", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "qty_on_hand": row.get("qty_on_hand", 0),
                "qty_allocated": row.get("qty_allocated", 0),
                "qty_available": row.get("qty_available", 0),
                "reorder_point": row.get("reorder_point", 0),
                "safety_stock": row.get("safety_stock", 0),
                "backorder_flag": row.get("backorder_flag", "N"),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "inventory_status": status,
                "recommendation": get_inventory_recommendation(
                    status,
                    item_no,
                    row.get("expected_receipt_date", "")
                ),
            }

    return {"error": f"Item {item_no} was not found."}


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_by_status(status: str) -> list:
    """
    Use this tool when the user wants to see all inventory items
    that match a specific stock status.

    Input: status — must be one of:
        HEALTHY       — stock is at or above reorder point
        LOW           — stock is below reorder point
        CRITICAL      — stock is below safety stock
        OUT_OF_STOCK  — zero units available
        ON_BACKORDER  — supplier delivery pending

    Use this when the user asks things like:
    - "Show me all out of stock items"
    - "Which items are on backorder?"
    - "List all critical inventory items"
    - "What items are running low?"
    - "Show me healthy stock items"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)
    results = []

    normalized = status.strip().upper().replace(" ", "_")
    valid = ["HEALTHY", "LOW", "CRITICAL", "OUT_OF_STOCK", "ON_BACKORDER"]

    if normalized not in valid:
        return [{"error": f"Invalid status '{status}'. Valid options: {', '.join(valid)}"}]

    for row in rows:
        if assign_inventory_status(row) == normalized:
            results.append({
                "item_no": row.get("item_no", ""),
                "item_description": row.get("item_description", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "qty_available": row.get("qty_available", 0),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "inventory_status": normalized,
            })

    if not results:
        return [{"message": f"No items found with status: {normalized}"}]

    return results


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_backordered_items() -> list:
    """
    Use this tool when the user asks about backordered items,
    items waiting on supplier delivery, or inbound supply gaps.

    Returns all items currently on backorder with their expected
    receipt dates so the user can assess supply risk.

    Use this when the user asks things like:
    - "What items are on backorder?"
    - "What are we waiting on from suppliers?"
    - "Show me all backorder items with expected dates"
    - "Which items have delayed supplier deliveries?"
    - "What is our backorder situation?"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)
    results = []

    for row in rows:
        if row.get("backorder_flag", "N").strip().upper() == "Y":
            status = assign_inventory_status(row)
            results.append({
                "item_no": row.get("item_no", ""),
                "item_description": row.get("item_description", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "qty_on_hand": row.get("qty_on_hand", 0),
                "qty_allocated": row.get("qty_allocated", 0),
                "qty_available": row.get("qty_available", 0),
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "inventory_status": status,
            })

    if not results:
        return [{"message": "No items currently on backorder."}]

    results.sort(key=lambda x: x.get("expected_receipt_date") or "9999")
    return results


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def check_inventory_for_order(item_no: str, qty_needed: int) -> dict:
    """
    Use this tool when the user wants to know if a specific item has
    enough stock to fulfill a specific order quantity. This is the
    cross-agent tool — use it when investigating whether a shipment
    delay is caused by an inventory problem.

    Inputs:
        item_no    — the item number to check (for example: ITEM-002)
        qty_needed — how many units the order requires

    Returns: whether the order can be fulfilled, how many units are
    available, how many units are short, inventory status, and
    a recommendation for resolving any shortage.

    Use this when the user asks things like:
    - "Can we fulfill 50 units of ITEM-002?"
    - "Do we have enough stock for this order?"
    - "Is the delay on SO-1003 caused by inventory?"
    - "Check if ITEM-007 can cover a qty of 30"
    - "Why can't we ship this order — is it a stock issue?"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)

    for row in rows:
        if row.get("item_no", "") == item_no:
            status = assign_inventory_status(row)
            qty_available = row.get("qty_available", 0)
            shortage = calculate_shortage(qty_available, qty_needed)
            fulfillable = can_fulfill(qty_available, qty_needed)

            return {
                "item_no": item_no,
                "item_description": row.get("item_description", ""),
                "warehouse_name": row.get("warehouse_name", ""),
                "qty_needed": qty_needed,
                "qty_available": qty_available,
                "shortage_qty": shortage,
                "can_fulfill": fulfillable,
                "inventory_status": status,
                "expected_receipt_date": row.get("expected_receipt_date", ""),
                "recommendation": get_inventory_recommendation(
                    status,
                    item_no,
                    row.get("expected_receipt_date", "")
                ),
            }

    return {"error": f"Item {item_no} was not found."}


# ─── TOOL 6 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_by_warehouse(warehouse_id: str) -> list:
    """
    Use this tool when the user asks about stock levels in a specific
    warehouse or storage location.

    Input: warehouse_id — for example: WH-01 or WH-02

    Returns all items stored in that warehouse with their
    availability and status.

    Use this when the user asks things like:
    - "What is the stock situation at WH-01?"
    - "Show me all items in cold storage"
    - "What does the main warehouse have available?"
    - "Inventory status for warehouse WH-02"
    """
    # OLD: rows = load_inventory(DATA_FILE)
    # NEW (Phase 7): load from SQLite
    rows = load_inventory(DB_FILE)
    results = []

    normalized = warehouse_id.strip().upper()

    for row in rows:
        if row.get("warehouse_id", "").strip().upper() == normalized:
            status = assign_inventory_status(row)
            results.append({
                "item_no": row.get("item_no", ""),
                "item_description": row.get("item_description", ""),
                "qty_on_hand": row.get("qty_on_hand", 0),
                "qty_available": row.get("qty_available", 0),
                "inventory_status": status,
                "expected_receipt_date": row.get("expected_receipt_date", ""),
            })

    if not results:
        return [{"message": f"No items found for warehouse: {normalized}"}]

    return results


if __name__ == "__main__":
    mcp.run()