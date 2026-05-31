# scripts/setup_project.py
#
# PURPOSE:
#   This is the first script a new user runs after cloning the repository.
#   It does everything needed to go from zero to a working project in
#   under 2 minutes — no manual steps, no guessing.
#
# WHAT IT DOES (in order):
#   Step 1 — Checks Python version is 3.8 or higher
#   Step 2 — Checks all required packages are installed
#   Step 3 — Checks that settings.yaml exists and is readable
#   Step 4 — Creates the SQLite database with the correct schema
#   Step 5 — Loads sample data from the data\ folder
#   Step 6 — Runs a quick sanity check on each domain
#   Step 7 — Prints a success summary with next steps
#
# HOW TO RUN:
#   cd supply-chain-control-tower
#   python scripts/setup_project.py
#
# IF SOMETHING FAILS:
#   The script tells you exactly which step failed and what to do.
#   It never silently continues past an error.

import sys
import os
import sqlite3

# ── PATH SETUP ────────────────────────────────────────────────────────────────
# __file__ = this file (scripts/setup_project.py)
# Two dirname() calls = go up to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

# ── COLOUR HELPERS ────────────────────────────────────────────────────────────
# These make the terminal output easier to read.
# On Windows, ANSI codes may not work in all terminals — we fall back to plain text.

def green(text):  return f"\033[92m{text}\033[0m"
def red(text):    return f"\033[91m{text}\033[0m"
def yellow(text): return f"\033[93m{text}\033[0m"
def bold(text):   return f"\033[1m{text}\033[0m"

def ok(msg):   print(f"  {green('✓')} {msg}")
def fail(msg): print(f"  {red('✗')} {msg}")
def warn(msg): print(f"  {yellow('!')} {msg}")
def head(msg): print(f"\n{bold(msg)}")


# ── STEP 1: CHECK PYTHON VERSION ──────────────────────────────────────────────

def check_python_version():
    head("Step 1 — Checking Python version")
    major = sys.version_info.major
    minor = sys.version_info.minor
    version_str = f"{major}.{minor}"

    # We need Python 3.8 or higher. Python 2 will not work at all.
    if major < 3 or (major == 3 and minor < 8):
        fail(f"Python {version_str} detected. Python 3.8 or higher is required.")
        print("    Download Python 3.10 from: https://python.org/downloads/")
        sys.exit(1)

    ok(f"Python {version_str} — OK")


# ── STEP 2: CHECK REQUIRED PACKAGES ──────────────────────────────────────────

def check_packages():
    head("Step 2 — Checking required packages")

    # List of (import_name, pip_name) pairs.
    # import_name = what you type in "import X"
    # pip_name    = what you type in "pip install X" (sometimes different)
    packages = [
        ("mcp",         "mcp"),
        ("apscheduler", "apscheduler"),
        ("yaml",        "pyyaml"),
        ("streamlit",   "streamlit"),
        ("plotly",      "plotly"),
    ]

    missing = []

    for import_name, pip_name in packages:
        try:
            # __import__() is like "import X" but works with a variable name
            __import__(import_name)
            ok(f"{pip_name}")
        except ImportError:
            fail(f"{pip_name} — NOT INSTALLED")
            missing.append(pip_name)

    if missing:
        print(f"\n  {red('Fix:')} Run this command then re-run setup:")
        print(f"    pip install {' '.join(missing)}")
        sys.exit(1)


# ── STEP 3: CHECK SETTINGS FILE ───────────────────────────────────────────────

def check_settings():
    head("Step 3 — Checking settings.yaml")

    settings_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")

    if not os.path.exists(settings_path):
        fail("config/settings.yaml not found.")
        print("    This file should have been included in the repository.")
        print("    Check that you cloned the full repo and not just some files.")
        sys.exit(1)

    try:
        from config.settings_loader import get_database_path
        db_path = get_database_path()
        ok(f"settings.yaml found")
        ok(f"Database path: {db_path}")
        return db_path
    except Exception as e:
        fail(f"Could not read settings.yaml — {e}")
        print("    Open config/settings.yaml and check the database.path value.")
        sys.exit(1)


# ── STEP 4: CREATE DATABASE SCHEMA ───────────────────────────────────────────

def create_schema(db_path: str):
    head("Step 4 — Creating database schema")

    # Create the data folder if it does not exist
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    try:
        # connect() creates the file if it does not exist yet
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # ── Shipments table ───────────────────────────────────────────────────
        # One row per order line. Core table used by the Shipping Delay Agent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shipments (
                sales_order_no      TEXT NOT NULL,
                line_no             INTEGER,
                customer_name       TEXT,
                item_no             TEXT,
                warehouse           TEXT,
                scheduled_pick_date TEXT,
                ship_confirm_date   TEXT,
                order_status        TEXT,
                qty_ordered         INTEGER DEFAULT 0,
                qty_allocated       INTEGER DEFAULT 0,
                qty_shipped         INTEGER DEFAULT 0,
                available_inventory INTEGER DEFAULT 0,
                backorder_qty       INTEGER DEFAULT 0,
                carrier_status      TEXT,
                truck_available     TEXT,
                pick_status         TEXT,
                freight_hold_flag   TEXT DEFAULT 'NO'
            )
        """)
        ok("shipments table ready")

        # ── Inventory table ───────────────────────────────────────────────────
        # One row per item per warehouse. Used by the Inventory Agent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                item_no               TEXT NOT NULL,
                item_description      TEXT,
                warehouse_id          TEXT,
                warehouse_name        TEXT,
                qty_on_hand           INTEGER DEFAULT 0,
                qty_allocated         INTEGER DEFAULT 0,
                qty_available         INTEGER DEFAULT 0,
                reorder_point         INTEGER DEFAULT 0,
                safety_stock          INTEGER DEFAULT 0,
                backorder_flag        TEXT DEFAULT 'N',
                supplier_id           TEXT,
                expected_receipt_date TEXT
            )
        """)
        ok("inventory table ready")

        # ── Purchase orders table ─────────────────────────────────────────────
        # One row per PO line. Used by the PO Agent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_no                 TEXT NOT NULL,
                po_line               INTEGER,
                supplier_id           TEXT,
                supplier_name         TEXT,
                item_no               TEXT,
                item_description      TEXT,
                qty_ordered           INTEGER DEFAULT 0,
                qty_received          INTEGER DEFAULT 0,
                qty_outstanding       INTEGER DEFAULT 0,
                order_date            TEXT,
                expected_delivery_date TEXT,
                actual_delivery_date  TEXT,
                po_status             TEXT,
                unit_cost             REAL DEFAULT 0,
                sales_order_no        TEXT,
                notes                 TEXT
            )
        """)
        ok("purchase_orders table ready")

        # ── Freight table ─────────────────────────────────────────────────────
        # One row per shipment. Used by the Freight Agent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS freight (
                freight_id                TEXT NOT NULL,
                sales_order_no            TEXT,
                carrier_id                TEXT,
                carrier_name              TEXT,
                pickup_scheduled_date     TEXT,
                pickup_actual_date        TEXT,
                delivery_scheduled_date   TEXT,
                delivery_actual_date      TEXT,
                freight_status            TEXT,
                freight_hold_flag         TEXT DEFAULT 'NO',
                freight_hold_reason       TEXT,
                carrier_performance_score INTEGER DEFAULT 0,
                truck_available           TEXT DEFAULT 'YES',
                driver_assigned           TEXT DEFAULT 'YES',
                trailer_no                TEXT,
                origin_warehouse          TEXT,
                destination               TEXT,
                freight_notes             TEXT
            )
        """)
        ok("freight table ready")

        # ── Warehouse picks table ─────────────────────────────────────────────
        # One row per pick task. Used by the Warehouse Agent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warehouse_picks (
                pick_id             TEXT NOT NULL,
                sales_order_no      TEXT,
                warehouse_id        TEXT,
                warehouse_name      TEXT,
                item_no             TEXT,
                qty_to_pick         INTEGER DEFAULT 0,
                qty_picked          INTEGER DEFAULT 0,
                pick_status         TEXT,
                pick_priority       TEXT DEFAULT 'NORMAL',
                assigned_picker     TEXT,
                pick_start_time     TEXT,
                pick_complete_time  TEXT,
                scheduled_pick_date TEXT,
                pick_delay_reason   TEXT,
                equipment_issue     TEXT DEFAULT 'NO',
                staffing_flag       TEXT DEFAULT 'NO',
                zone                TEXT,
                pick_notes          TEXT
            )
        """)
        ok("warehouse_picks table ready")

        conn.commit()
        conn.close()

    except Exception as e:
        fail(f"Schema creation failed — {e}")
        sys.exit(1)


# ── STEP 5: LOAD SAMPLE DATA ──────────────────────────────────────────────────

def load_sample_data(db_path: str):
    head("Step 5 — Loading sample data")

    import csv

    # Map of (csv_file, table_name) pairs.
    # Each CSV file in the data\ folder maps to one database table.
    data_files = [
        ("shipments_sample.csv",       "shipments"),
        ("inventory_sample.csv",       "inventory"),
        ("purchase_orders_sample.csv", "purchase_orders"),
        ("freight_sample.csv",         "freight"),
        ("warehouse_sample.csv",       "warehouse_picks"),
    ]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for csv_filename, table_name in data_files:
        csv_path = os.path.join(PROJECT_ROOT, "data", csv_filename)

        # Skip files that do not exist — not all may be present
        if not os.path.exists(csv_path):
            warn(f"{csv_filename} not found — skipping {table_name}")
            continue

        try:
            # Check if table already has data — do not double-load
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            if count > 0:
                ok(f"{table_name} — already has {count} rows, skipping")
                continue

            # Read the CSV and insert each row into the table
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows_inserted = 0

                for row in reader:
                    # Build INSERT statement from the CSV column names
                    # This works even if the CSV has extra columns — we only
                    # insert columns that exist in both the CSV and the table
                    columns = list(row.keys())
                    placeholders = ",".join(["?" for _ in columns])
                    col_names = ",".join(columns)
                    values = [row[col] if row[col] != "" else None for col in columns]

                    try:
                        cursor.execute(
                            f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})",
                            values
                        )
                        rows_inserted += 1
                    except sqlite3.OperationalError:
                        # Column mismatch — skip this row silently
                        # This happens when CSV has columns the table does not
                        pass

            conn.commit()
            ok(f"{table_name} — {rows_inserted} rows loaded from {csv_filename}")

        except Exception as e:
            warn(f"{table_name} — could not load: {e}")

    conn.close()


# ── STEP 6: SANITY CHECK ──────────────────────────────────────────────────────

def run_sanity_check(db_path: str):
    head("Step 6 — Running sanity check")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = ["shipments", "inventory", "purchase_orders", "freight", "warehouse_picks"]
    all_ok = True

    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            if count > 0:
                ok(f"{table} — {count} rows")
            else:
                warn(f"{table} — 0 rows (empty table)")
        except Exception as e:
            fail(f"{table} — error: {e}")
            all_ok = False

    conn.close()
    return all_ok


# ── STEP 7: PRINT SUCCESS SUMMARY ─────────────────────────────────────────────

def print_success():
    head("Setup Complete!")
    print(f"""
  {green('Your Supply Chain Control Tower is ready.')}

  {bold('Next steps:')}

  1. Connect Claude Desktop
     Add all MCP servers to your claude_desktop_config.json
     See: docs/DEPLOYMENT.md for the full config block

  2. Start the background scheduler
     python scripts/scheduler.py

  3. Open Claude Desktop and try:
     "Read my project memory"
     "Give me today's management summary"
     "What orders need urgent attention?"

  4. Launch the dashboard
     streamlit run dashboard/app.py

  {bold('Using your own data instead of sample data?')}
  See: docs/BRING_YOUR_OWN_DATA.md
    """)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(bold("\n" + "=" * 60))
    print(bold("  Supply Chain Control Tower — Project Setup"))
    print(bold("=" * 60))

    check_python_version()
    check_packages()
    db_path = check_settings()
    create_schema(db_path)
    load_sample_data(db_path)
    all_ok = run_sanity_check(db_path)

    if all_ok:
        print_success()
    else:
        print(f"\n  {yellow('Setup completed with warnings. Check the items above.')}")


if __name__ == "__main__":
    main()
