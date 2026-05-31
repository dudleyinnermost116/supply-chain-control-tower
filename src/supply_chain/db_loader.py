# src/supply_chain/db_loader.py
#
# Phase 7 — SQLite data loader.
# Replaces all 5 individual CSV loaders with one file.
#
# Each function returns a list of dicts — exactly the same format
# the rules engines already expect. Nothing else in the project changes.
#
# Usage in each MCP server (replaces the old CSV loader import):
#
#   from supply_chain.db_loader import (
#       load_shipments_db,
#       load_inventory_db,
#       load_purchase_orders_db,
#       load_freight_db,
#       load_warehouse_picks_db,
#   )
#
#   DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"

import sqlite3


def _query_table(db_path: str, table_name: str) -> list:
    """
    Shared helper. Connects to the SQLite database, runs
    SELECT * on the given table, and returns a list of dicts.
    Each dict key is a column name — same structure as csv.DictReader.
    Returns an empty list if anything goes wrong.
    """
    rows = []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # makes rows behave like dicts
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

    except sqlite3.OperationalError as e:
        print(f"[db_loader] ERROR reading {table_name}: {e}")
    except FileNotFoundError:
        print(f"[db_loader] ERROR: Database not found at {db_path}")
    except Exception as e:
        print(f"[db_loader] ERROR: {e}")

    return rows


# ── Public loader functions ───────────────────────────────────────────────────
# Each one mirrors its old CSV loader but reads from SQLite instead.
# The numeric type conversions that used to happen in each CSV loader
# are handled here for inventory and warehouse so rules engines still work.


def load_shipments_db(db_path: str) -> list:
    """
    Loads all rows from the shipments table.
    Equivalent to the old load_shipments() from data_loader.py
    """
    rows = _query_table(db_path, "shipments")

    # Convert numeric columns so rules engine never gets strings
    int_cols = ["qty_ordered", "qty_allocated", "qty_shipped",
                "available_inventory", "backorder_qty"]
    for row in rows:
        for col in int_cols:
            try:
                row[col] = int(row.get(col) or 0)
            except (ValueError, TypeError):
                row[col] = 0

    return rows


def load_inventory_db(db_path: str) -> list:
    """
    Loads all rows from the inventory table.
    Equivalent to the old load_inventory() from inventory_data_loader.py
    """
    rows = _query_table(db_path, "inventory")

    int_cols = ["qty_on_hand", "qty_allocated", "qty_available",
                "reorder_point", "safety_stock"]
    for row in rows:
        for col in int_cols:
            try:
                row[col] = int(row.get(col) or 0)
            except (ValueError, TypeError):
                row[col] = 0

    return rows


def load_purchase_orders_db(db_path: str) -> list:
    """
    Loads all rows from the purchase_orders table.
    Equivalent to the old load_purchase_orders() from po_data_loader.py
    """
    rows = _query_table(db_path, "purchase_orders")

    int_cols = ["qty_ordered", "qty_received", "qty_outstanding"]
    float_cols = ["unit_cost"]

    for row in rows:
        for col in int_cols:
            try:
                row[col] = int(row.get(col) or 0)
            except (ValueError, TypeError):
                row[col] = 0
        for col in float_cols:
            try:
                row[col] = float(row.get(col) or 0.0)
            except (ValueError, TypeError):
                row[col] = 0.0

    return rows


def load_freight_db(db_path: str) -> list:
    """
    Loads all rows from the freight table.
    Equivalent to the old load_freight() from freight_data_loader.py
    """
    # Freight has no numeric columns that need conversion —
    # carrier_performance_score is handled as a string in freight_rules.py
    return _query_table(db_path, "freight")


def load_warehouse_picks_db(db_path: str) -> list:
    """
    Loads all rows from the warehouse_picks table.
    Equivalent to the old load_warehouse_picks() from warehouse_data_loader.py
    """
    rows = _query_table(db_path, "warehouse_picks")

    int_cols = ["qty_to_pick", "qty_picked"]
    for row in rows:
        for col in int_cols:
            try:
                row[col] = int(row.get(col) or 0)
            except (ValueError, TypeError):
                row[col] = 0

    return rows