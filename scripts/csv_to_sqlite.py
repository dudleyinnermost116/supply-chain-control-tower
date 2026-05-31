# scripts/csv_to_sqlite.py
#
# Phase 7 — One-time migration script.
# Reads all 5 CSV files from the data folder and loads them
# into a single SQLite database: data/supply_chain.db
#
# Run this ONCE from the project root:
#   python scripts\csv_to_sqlite.py
#
# After running, verify the row counts printed match your CSV row counts.
# You do NOT need to run this again unless your CSV data changes.

import csv
import sqlite3
import os

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "supply_chain.db")

CSV_FILES = {
    "shipments":       os.path.join(DATA_DIR, "shipments_sample.csv"),
    "inventory":       os.path.join(DATA_DIR, "inventory_sample.csv"),
    "purchase_orders": os.path.join(DATA_DIR, "purchase_orders_sample.csv"),
    "freight":         os.path.join(DATA_DIR, "freight_sample.csv"),
    "warehouse_picks": os.path.join(DATA_DIR, "warehouse_sample.csv"),
}

# ── Helper: create table from CSV headers, then insert all rows ───────────────

def load_csv_to_table(conn, table_name: str, csv_path: str):
    """
    Reads the CSV, drops any existing table, creates a fresh one
    using the actual CSV headers as column names, then inserts all rows.
    This approach is bulletproof — the schema always matches the CSV.
    """
    if not os.path.exists(csv_path):
        print(f"  WARNING: CSV not found — skipping {csv_path}")
        return 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"  WARNING: {csv_path} is empty — nothing loaded")
        return 0

    # Get exact column names from the CSV header
    columns = list(rows[0].keys())

    cursor = conn.cursor()

    # Drop table if it exists so we always start clean
    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

    # Build CREATE TABLE using actual CSV column names — all TEXT
    col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    cursor.execute(f"CREATE TABLE {table_name} ({col_defs})")

    # Build INSERT statement
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(f'"{col}"' for col in columns)
    sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

    # Insert all rows
    for row in rows:
        cursor.execute(sql, list(row.values()))

    conn.commit()
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nPhase 7 — SQLite Migration")
    print(f"Database: {DB_PATH}\n")

    # Delete existing DB so we always start completely fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Removed existing supply_chain.db — rebuilding from scratch.\n")

    conn = sqlite3.connect(DB_PATH)

    for table_name, csv_path in CSV_FILES.items():
        print(f"Loading table: {table_name}")
        count = load_csv_to_table(conn, table_name, csv_path)
        print(f"  Loaded {count} rows from {os.path.basename(csv_path)}\n")

    conn.close()

    print("=" * 50)
    print("Migration complete. supply_chain.db is ready.")
    print("=" * 50)
    print("\nNext step: build db_loader.py")


if __name__ == "__main__":
    main()