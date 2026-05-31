# src/supply_chain/ci_signal_detector.py
#
# PURPOSE:
#   This is the "eyes" of the Continuous Improvement Agent.
#   It scans all four data domains (shipping, inventory, freight, warehouse)
#   and produces a list of signals — patterns or anomalies worth investigating.
#
# HOW IT WORKS:
#   1. Load all data from the SQLite database
#   2. Run each detector function against that data
#   3. Each detector returns a list of Signal objects if it finds a problem
#   4. All signals are collected and returned to the MCP server
#
# REUSABILITY:
#   The detector functions are generic pattern-finders.
#   The thresholds they use come from ci_project_config.py.
#   To use this in a different project, update the config — not this file.

import sqlite3
import uuid
from datetime import datetime, date
from typing import List, Dict, Any

# We import the project config to get thresholds and settings.
# sys.path manipulation is not needed because PYTHONPATH is set in your terminal.
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'config'))

from ci_project_config import PROJECT_CONFIG, SIGNAL_TYPES


# ─── DATABASE PATH ────────────────────────────────────────────────────────────
# This is the same database all your other agents use.
# DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"

# ─── DATABASE PATH ────────────────────────────────────────────────────────────
#
# WHAT WAS HERE BEFORE:
#   DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"
#
# HISTORY — WHY THIS IS IN ci_signal_detector.py AND NOT ci_mcp_server.py:
#   The CI agent was structured differently from the other agents.
#   Instead of defining DB_PATH in the MCP server file, it was defined
#   here in ci_signal_detector.py and then imported by ci_mcp_server.py
#   with this line:
#     from supply_chain.ci_signal_detector import run_full_signal_scan, DB_PATH
#   So this file is the real home of the CI agent's database path.
#
# PHASE 10 CHANGE:
#   get_database_path() reads the path from config\settings.yaml instead
#   of having it hardcoded here. This makes the CI agent consistent with
#   all 7 other agents — they all now get their database path from the
#   same single place: settings.yaml.
#
#   The sys.path manipulation already at the top of this file (the lines
#   with sys.path.insert) makes the config folder findable from here,
#   so the import below works without any extra setup.
#
# HOW TO ROLL BACK:
#   Comment out the two new lines and uncomment the original DB_PATH line.
# ─────────────────────────────────────────────────────────────────────────────
from settings_loader import get_database_path
DB_PATH = get_database_path()

# Today's date — used by delay calculators.
TODAY = date.today()


# ─── HELPER: generate unique IDs ─────────────────────────────────────────────

def _new_signal_id() -> str:
    """
    Generates a unique signal ID like SIG-A3F2B1.
    We use the first 6 characters of a UUID to keep it short but unique.
    UUID = Universally Unique Identifier — a random string Python can generate.
    """
    return f"SIG-{uuid.uuid4().hex[:6].upper()}"


def _now() -> str:
    """Returns the current timestamp as a readable string."""
    return datetime.now().isoformat(sep=" ", timespec="seconds")


# ─── HELPER: load data from the database ─────────────────────────────────────

def _load_table(db_path: str, table_name: str) -> List[Dict]:
    """
    Loads every row from a database table and returns them as a list of dicts.
    Each dict has column names as keys and row values as values.

    For example, loading 'shipments' gives you:
      [{"sales_order_no": "SO-1001", "customer_name": "Acme Corp", ...}, ...]

    Parameters:
      db_path    — path to the SQLite database file
      table_name — name of the table to load (e.g. 'shipments')
    """
    rows = []
    try:
        # Connect to the database in read-only mode.
        conn = sqlite3.connect(db_path)

        # row_factory = sqlite3.Row makes each row behave like a dict.
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # SELECT * means "give me all columns". The table name is inserted safely.
        cursor.execute(f"SELECT * FROM {table_name}")

        # fetchall() gets every row at once.
        # dict(row) converts the Row object to a plain Python dict.
        rows = [dict(row) for row in cursor.fetchall()]

        conn.close()
    except Exception as e:
        print(f"[ci_signal_detector] WARNING: Could not load table '{table_name}': {e}")
    return rows


# ─── HELPER: build a signal dict ─────────────────────────────────────────────

def _make_signal(signal_type: str, title: str, description: str,
                 evidence: list, affected_records: list,
                 severity: str, frequency: int = 1) -> dict:
    """
    Creates a standardised signal dictionary.
    Every detector uses this to ensure all signals have the same structure.

    Parameters:
      signal_type      — key from SIGNAL_TYPES (e.g. 'REPEATED_DELAY_BY_CARRIER')
      title            — short one-line description
      description      — longer explanation of what was found
      evidence         — list of data points supporting this signal
      affected_records — list of order numbers, item IDs, etc. that are affected
      severity         — LOW, MEDIUM, HIGH, or CRITICAL
      frequency        — how many times this pattern was observed
    """
    import json

    # Look up the domain for this signal type from the config.
    domain = SIGNAL_TYPES.get(signal_type, {}).get("domain", "UNKNOWN")
    auto_log = SIGNAL_TYPES.get(signal_type, {}).get("auto_log", True)

    now = _now()
    return {
        "signal_id":        _new_signal_id(),
        "project_name":     PROJECT_CONFIG["project_name"],
        "signal_type":      signal_type,
        "domain":           domain,
        "title":            title,
        "description":      description,
        "evidence_json":    json.dumps(evidence),
        "frequency":        frequency,
        "affected_records": ", ".join(str(r) for r in affected_records),
        "severity":         severity,
        "detected_at":      now,
        "last_seen_at":     now,
        "status":           "new",
        "auto_log":         auto_log,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTOR FUNCTIONS
# Each function below is a self-contained detector.
# It receives data rows and returns a list of signals (possibly empty).
# ═══════════════════════════════════════════════════════════════════════════════

def detect_carrier_repeat_delays(shipment_rows: list) -> list:
    """
    DETECTOR: Repeated Delay By Carrier
    ------------------------------------
    Scans all delayed shipments and counts how many delays each carrier is
    responsible for. If a carrier appears more times than the threshold,
    we create a signal.

    Why this matters: A carrier that causes repeated delays should either be
    addressed directly or replaced. This detector surfaces that pattern early.

    Parameters:
      shipment_rows — all rows from the shipments table
    """
    signals = []
    threshold = PROJECT_CONFIG["detection_thresholds"]["carrier_delay_repeat_threshold"]

    # carrier_name -> list of affected order numbers
    # We build this dict by going through every row and grouping by carrier.
    carrier_delay_map = {}

    for row in shipment_rows:
        carrier_status = str(row.get("carrier_status", "")).upper()
        carrier = str(row.get("carrier_status", "")).strip()  # carrier name not in shipments

        # Check if this order is delayed and the reason involves the carrier.
        order_status = str(row.get("order_status", "")).upper()
        ship_confirm = str(row.get("ship_confirm_date", "")).strip()

        # Skip shipped and cancelled orders.
        if order_status in ("SHIPPED", "CLOSED", "CANCELLED") or ship_confirm:
            continue

        # If carrier_status is "DELAYED", that means the carrier is the problem.
        if carrier_status == "DELAYED":
            # Use "carrier_status" field as the identifier here (it holds the status string).
            # In a real system, you'd have a separate carrier_name column.
            carrier_key = f"Carrier (status=DELAYED)"
            order_no = row.get("sales_order_no", "UNKNOWN")

            if carrier_key not in carrier_delay_map:
                carrier_delay_map[carrier_key] = []
            carrier_delay_map[carrier_key].append(order_no)

    # Now check if any carrier exceeded the threshold.
    for carrier_key, affected_orders in carrier_delay_map.items():
        if len(affected_orders) >= threshold:
            signals.append(_make_signal(
                signal_type="REPEATED_DELAY_BY_CARRIER",
                title=f"Carrier delays appearing across {len(affected_orders)} orders",
                description=(
                    f"CARRIER_DELAY reason code appears in {len(affected_orders)} active orders. "
                    f"This pattern suggests a systemic carrier performance issue, "
                    f"not an isolated incident."
                ),
                evidence=[
                    f"{len(affected_orders)} orders with CARRIER_DELAY status",
                    f"Affected orders: {', '.join(affected_orders)}",
                    f"Threshold for flagging: {threshold} orders",
                ],
                affected_records=affected_orders,
                severity="HIGH" if len(affected_orders) >= threshold * 2 else "MEDIUM",
                frequency=len(affected_orders),
            ))

    return signals


def detect_dominant_root_cause(shipment_rows: list) -> list:
    """
    DETECTOR: Dominant Root Cause
    --------------------------------
    Checks if one root cause type is causing a disproportionate share of delays.
    If yes, that root cause deserves a dedicated improvement initiative.

    For example, if 60% of delays are WAREHOUSE_PICK_DELAY, the warehouse
    team has a systemic problem — not just bad luck on individual orders.

    Parameters:
      shipment_rows — all rows from the shipments table
    """
    signals = []
    threshold_pct = PROJECT_CONFIG["detection_thresholds"]["dominant_root_cause_pct_threshold"]
    min_sample = PROJECT_CONFIG["detection_thresholds"]["minimum_sample_size"]

    # Count how many delayed orders belong to each reason code.
    reason_counts = {}
    delayed_orders = []

    for row in shipment_rows:
        order_status = str(row.get("order_status", "")).upper()
        ship_confirm = str(row.get("ship_confirm_date", "")).strip()

        if order_status in ("SHIPPED", "CLOSED", "CANCELLED") or ship_confirm:
            continue

        # Get the scheduled pick date to see if it's overdue.
        scheduled = row.get("scheduled_pick_date", "")
        if not scheduled:
            continue

        try:
            from datetime import datetime
            scheduled_date = datetime.strptime(str(scheduled), "%Y-%m-%d").date()
            delay_days = max((TODAY - scheduled_date).days, 0)
        except (ValueError, TypeError):
            delay_days = 0

        if delay_days <= 0:
            continue  # Not delayed, skip.

        delayed_orders.append(row.get("sales_order_no", ""))

        # Determine the reason code using the same logic as rules.py.
        # We import the rules module to avoid duplicating logic.
        try:
            from supply_chain.rules import assign_reason_code
            from datetime import date as date_type
            reason = assign_reason_code(row, TODAY)
        except ImportError:
            # Fallback if import fails — use a simple heuristic.
            freight_hold = str(row.get("freight_hold_flag", "")).upper()
            if freight_hold == "YES":
                reason = "FREIGHT_HOLD"
            else:
                reason = "UNKNOWN_NEEDS_REVIEW"

        if reason != "NOT_APPLICABLE":
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    total_delayed = len(delayed_orders)

    # We need at least the minimum sample size before flagging.
    if total_delayed < min_sample:
        return signals

    # Check if any single reason code dominates.
    for reason, count in reason_counts.items():
        pct = count / total_delayed
        if pct >= threshold_pct:
            signals.append(_make_signal(
                signal_type="DOMINANT_ROOT_CAUSE",
                title=f"{reason} is causing {int(pct * 100)}% of all delays",
                description=(
                    f"Root cause '{reason}' appears in {count} out of {total_delayed} delayed orders "
                    f"({int(pct * 100)}%). This exceeds the {int(threshold_pct * 100)}% threshold "
                    f"for systemic issues. This root cause deserves a dedicated process improvement initiative."
                ),
                evidence=[
                    f"Root cause: {reason}",
                    f"Affected orders: {count} of {total_delayed} delayed",
                    f"Percentage: {int(pct * 100)}%",
                    f"Threshold: {int(threshold_pct * 100)}%",
                ],
                affected_records=delayed_orders[:10],  # first 10 as a sample
                severity="HIGH" if pct > 0.50 else "MEDIUM",
                frequency=count,
            ))

    return signals


def detect_high_unknown_rate(shipment_rows: list) -> list:
    """
    DETECTOR: High UNKNOWN_NEEDS_REVIEW Rate
    ------------------------------------------
    If too many delays are classified as UNKNOWN, it means the business rules
    in rules.py are not covering all real-world scenarios.
    This is a code quality / coverage signal — not a data problem.

    Why this matters: Every UNKNOWN order requires manual investigation.
    Reducing unknowns = less manual work for your team.

    Parameters:
      shipment_rows — all rows from the shipments table
    """
    signals = []
    threshold_pct = PROJECT_CONFIG["detection_thresholds"]["unknown_root_cause_pct_threshold"]

    unknown_orders = []
    total_delayed = 0

    for row in shipment_rows:
        order_status = str(row.get("order_status", "")).upper()
        ship_confirm = str(row.get("ship_confirm_date", "")).strip()

        if order_status in ("SHIPPED", "CLOSED", "CANCELLED") or ship_confirm:
            continue

        scheduled = row.get("scheduled_pick_date", "")
        if not scheduled:
            continue

        try:
            from datetime import datetime
            scheduled_date = datetime.strptime(str(scheduled), "%Y-%m-%d").date()
            delay_days = max((TODAY - scheduled_date).days, 0)
        except (ValueError, TypeError):
            delay_days = 0

        if delay_days <= 0:
            continue

        total_delayed += 1

        # Check if this order is stuck as UNKNOWN.
        try:
            from supply_chain.rules import assign_reason_code
            reason = assign_reason_code(row, TODAY)
        except ImportError:
            reason = "UNKNOWN_NEEDS_REVIEW"

        if reason == "UNKNOWN_NEEDS_REVIEW":
            unknown_orders.append(row.get("sales_order_no", ""))

    if total_delayed == 0:
        return signals

    unknown_pct = len(unknown_orders) / total_delayed

    if unknown_pct >= threshold_pct:
        signals.append(_make_signal(
            signal_type="HIGH_UNKNOWN_RATE",
            title=f"{int(unknown_pct * 100)}% of delayed orders have no identified root cause",
            description=(
                f"{len(unknown_orders)} out of {total_delayed} delayed orders "
                f"({int(unknown_pct * 100)}%) are classified as UNKNOWN_NEEDS_REVIEW. "
                f"This means the reason code logic in rules.py does not cover these scenarios. "
                f"Review these orders manually to find what new conditions should be added to the rules."
            ),
            evidence=[
                f"Unknown orders: {len(unknown_orders)} of {total_delayed}",
                f"Unknown rate: {int(unknown_pct * 100)}%",
                f"Threshold: {int(threshold_pct * 100)}%",
                f"Sample unknown orders: {', '.join(unknown_orders[:5])}",
            ],
            affected_records=unknown_orders,
            severity="HIGH" if unknown_pct > 0.30 else "MEDIUM",
            frequency=len(unknown_orders),
        ))

    return signals


def detect_freight_hold_pattern(freight_rows: list) -> list:
    """
    DETECTOR: Freight Hold Pattern
    --------------------------------
    Checks if multiple freight holds are active simultaneously.
    Multiple active holds suggests a systemic issue (e.g., a compliance
    problem with a specific carrier or origin warehouse).

    Parameters:
      freight_rows — all rows from the freight table
    """
    signals = []
    threshold = PROJECT_CONFIG["detection_thresholds"]["freight_hold_count_threshold"]

    hold_orders = []
    hold_reasons = {}

    for row in freight_rows:
        hold_flag = str(row.get("freight_hold_flag", "NO")).strip().upper()
        if hold_flag == "YES":
            order_no = row.get("sales_order_no", "UNKNOWN")
            hold_orders.append(order_no)
            reason = str(row.get("freight_hold_reason", "UNSPECIFIED")).strip()
            hold_reasons[reason] = hold_reasons.get(reason, 0) + 1

    if len(hold_orders) >= threshold:
        # Find the most common hold reason.
        top_reason = max(hold_reasons, key=hold_reasons.get) if hold_reasons else "UNSPECIFIED"
        top_count = hold_reasons.get(top_reason, 0)

        signals.append(_make_signal(
            signal_type="FREIGHT_HOLD_PATTERN",
            title=f"{len(hold_orders)} active freight holds — possible systemic issue",
            description=(
                f"{len(hold_orders)} shipments are currently on freight hold. "
                f"The most common reason is '{top_reason}' ({top_count} holds). "
                f"Multiple simultaneous holds suggest a root cause beyond individual orders — "
                f"likely a carrier compliance issue, documentation gap, or payment dispute."
            ),
            evidence=[
                f"Total active holds: {len(hold_orders)}",
                f"Top hold reason: {top_reason} ({top_count} holds)",
                f"All hold reasons: {hold_reasons}",
                f"Affected orders: {', '.join(hold_orders)}",
            ],
            affected_records=hold_orders,
            severity="CRITICAL" if len(hold_orders) >= threshold * 2 else "HIGH",
            frequency=len(hold_orders),
        ))

    return signals


def detect_weak_carrier_usage(freight_rows: list) -> list:
    """
    DETECTOR: Weak Carrier Overuse
    --------------------------------
    If WEAK or CRITICAL tier carriers are handling a lot of shipments,
    that's a structural problem — you're routing too much volume through
    unreliable carriers.

    Parameters:
      freight_rows — all rows from the freight table
    """
    signals = []

    weak_critical_orders = []
    total_active = 0

    for row in freight_rows:
        # Skip delivered shipments — we only care about active ones.
        freight_status = str(row.get("freight_status", "")).upper()
        if freight_status == "DELIVERED":
            continue

        total_active += 1

        # Calculate carrier tier from the performance score.
        try:
            score = int(str(row.get("carrier_performance_score", "0")).strip())
        except (ValueError, TypeError):
            score = 0

        # Mirror the tier logic from freight_rules.py.
        if score < 70:  # WEAK (55-69) or CRITICAL (<55)
            carrier_name = row.get("carrier_name", "Unknown")
            order_no = row.get("sales_order_no", "UNKNOWN")
            weak_critical_orders.append(f"{order_no} ({carrier_name}, score={score})")

    if total_active == 0:
        return signals

    weak_pct = len(weak_critical_orders) / total_active

    # Flag if more than 30% of active shipments are using weak carriers.
    if weak_pct >= 0.30 and len(weak_critical_orders) >= 2:
        signals.append(_make_signal(
            signal_type="WEAK_CARRIER_OVERUSE",
            title=f"{int(weak_pct * 100)}% of active shipments use WEAK/CRITICAL tier carriers",
            description=(
                f"{len(weak_critical_orders)} of {total_active} active shipments are handled by "
                f"carriers with performance scores below 70 (WEAK or CRITICAL tier). "
                f"This increases the probability of missed pickups, delays, and customer escalations. "
                f"Consider redirecting volume to STRONG or AVERAGE tier carriers."
            ),
            evidence=[
                f"Weak/Critical shipments: {len(weak_critical_orders)} of {total_active} active",
                f"Percentage: {int(weak_pct * 100)}%",
                f"Affected: {'; '.join(weak_critical_orders[:5])}",
            ],
            affected_records=[x.split(" ")[0] for x in weak_critical_orders],
            severity="HIGH",
            frequency=len(weak_critical_orders),
        ))

    return signals


def detect_warehouse_systemic_delays(warehouse_rows: list) -> list:
    """
    DETECTOR: Warehouse Systemic Delay
    -------------------------------------
    If multiple picks in the same warehouse are delayed, the problem is
    structural (staffing, equipment, WMS system) — not order-specific.

    Parameters:
      warehouse_rows — all rows from the warehouse_picks table
    """
    signals = []
    threshold = PROJECT_CONFIG["detection_thresholds"]["warehouse_delayed_picks_threshold"]

    # Group delayed picks by warehouse.
    warehouse_delays = {}

    for row in warehouse_rows:
        pick_status = str(row.get("pick_status", "")).strip().upper()
        scheduled = row.get("scheduled_pick_date", "")

        # A pick is delayed if it's NOT_STARTED or BLOCKED and the date is past.
        if pick_status in ("COMPLETE", "IN_PROGRESS", "READY"):
            continue

        if pick_status in ("NOT_STARTED", "BLOCKED") and scheduled:
            try:
                from datetime import datetime
                sched_date = datetime.strptime(str(scheduled), "%Y-%m-%d").date()
                if sched_date < TODAY:
                    wh_name = row.get("warehouse_name", "Unknown Warehouse")
                    order_no = row.get("sales_order_no", "UNKNOWN")

                    if wh_name not in warehouse_delays:
                        warehouse_delays[wh_name] = []
                    warehouse_delays[wh_name].append(order_no)
            except (ValueError, TypeError):
                pass

    for warehouse, affected_orders in warehouse_delays.items():
        if len(affected_orders) >= threshold:
            signals.append(_make_signal(
                signal_type="WAREHOUSE_SYSTEMIC_DELAY",
                title=f"{warehouse} has {len(affected_orders)} delayed picks — possible systemic issue",
                description=(
                    f"{warehouse} has {len(affected_orders)} overdue picks that have not started. "
                    f"When multiple picks in the same warehouse are delayed, the cause is usually "
                    f"structural: staffing shortage, equipment failure, or WMS system error. "
                    f"Individual order follow-up is not enough — the warehouse supervisor needs to "
                    f"investigate the root cause at the warehouse level."
                ),
                evidence=[
                    f"Warehouse: {warehouse}",
                    f"Delayed pick count: {len(affected_orders)}",
                    f"Affected orders: {', '.join(affected_orders)}",
                ],
                affected_records=affected_orders,
                severity="HIGH" if len(affected_orders) >= threshold * 2 else "MEDIUM",
                frequency=len(affected_orders),
            ))

    return signals


def detect_inventory_repeat_stockouts(inventory_rows: list) -> list:
    """
    DETECTOR: Repeated Stockout
    ----------------------------
    Finds items that are currently OUT_OF_STOCK with a backorder flag.
    In a real system with history, this would track repeated stockouts.
    Here, we flag items that are both OUT_OF_STOCK and have a backorder.

    Parameters:
      inventory_rows — all rows from the inventory table
    """
    signals = []
    threshold = PROJECT_CONFIG["detection_thresholds"]["inventory_oos_repeat_threshold"]

    problem_items = []

    for row in inventory_rows:
        backorder_flag = str(row.get("backorder_flag", "N")).strip().upper()
        qty_available = int(row.get("qty_available", 0) or 0)

        # An item is a stockout risk if it's on backorder OR already at zero.
        if backorder_flag == "Y" or qty_available <= 0:
            item_no = row.get("item_no", "UNKNOWN")
            desc = row.get("item_description", "")
            expected = row.get("expected_receipt_date", "not confirmed")
            problem_items.append({
                "item_no": item_no,
                "description": desc,
                "qty_available": qty_available,
                "backorder_flag": backorder_flag,
                "expected_receipt": expected,
            })

    if len(problem_items) >= threshold:
        item_ids = [p["item_no"] for p in problem_items]
        signals.append(_make_signal(
            signal_type="REPEATED_STOCKOUT",
            title=f"{len(problem_items)} inventory items are out of stock or on backorder",
            description=(
                f"{len(problem_items)} items are either at zero quantity or on backorder. "
                f"Multiple simultaneous stockouts suggests reorder points or safety stock levels "
                f"may need review. Supplier lead times may also be longer than expected."
            ),
            evidence=[
                f"Problem item count: {len(problem_items)}",
                f"Items: {', '.join([p['item_no'] + ' (' + p['description'] + ')' for p in problem_items[:5]])}",
            ],
            affected_records=item_ids,
            severity="HIGH" if len(problem_items) >= threshold * 2 else "MEDIUM",
            frequency=len(problem_items),
        ))

    return signals


def detect_data_quality_gaps(shipment_rows: list, freight_rows: list,
                              warehouse_rows: list) -> list:
    """
    DETECTOR: Data Quality Gaps
    ----------------------------
    Finds rows where important fields are missing or empty.
    Missing data makes it impossible for the agents to classify correctly,
    leading to more UNKNOWN_NEEDS_REVIEW classifications.

    Parameters:
      shipment_rows  — all rows from shipments
      freight_rows   — all rows from freight
      warehouse_rows — all rows from warehouse_picks
    """
    signals = []
    issues = []

    # Check shipments for missing critical fields.
    for row in shipment_rows:
        order_no = row.get("sales_order_no", "UNKNOWN")
        if not str(row.get("scheduled_pick_date", "")).strip():
            issues.append(f"shipment {order_no}: missing scheduled_pick_date")
        if not str(row.get("item_no", "")).strip():
            issues.append(f"shipment {order_no}: missing item_no")

    # Check freight for missing carrier information.
    for row in freight_rows:
        order_no = row.get("sales_order_no", "UNKNOWN")
        if not str(row.get("carrier_name", "")).strip():
            issues.append(f"freight {order_no}: missing carrier_name")
        if not str(row.get("pickup_scheduled_date", "")).strip():
            issues.append(f"freight {order_no}: missing pickup_scheduled_date")

    # Check warehouse for missing pick status.
    for row in warehouse_rows:
        order_no = row.get("sales_order_no", "UNKNOWN")
        if not str(row.get("pick_status", "")).strip():
            issues.append(f"warehouse {order_no}: missing pick_status")

    if len(issues) >= 3:  # Only flag if there are at least 3 data quality issues.
        signals.append(_make_signal(
            signal_type="DATA_QUALITY_GAP",
            title=f"{len(issues)} data quality issues found across tables",
            description=(
                f"{len(issues)} records have missing or empty fields in critical columns. "
                f"Missing data prevents agents from classifying orders correctly, "
                f"which increases the UNKNOWN_NEEDS_REVIEW rate and manual work."
            ),
            evidence=[f"Sample issues: {'; '.join(issues[:5])}",
                      f"Total issues found: {len(issues)}"],
            affected_records=[i.split(":")[0] for i in issues[:10]],
            severity="MEDIUM",
            frequency=len(issues),
        ))

    return signals


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER SCAN FUNCTION
# This is the main entry point. Call this function to run all detectors.
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_signal_scan(db_path: str = DB_PATH) -> List[dict]:
    """
    Runs all detectors across all domains and returns a combined list of signals.

    This is what the MCP server calls when it needs a fresh scan.
    Each signal in the list is ready to be saved to the ci_signals table.

    Parameters:
      db_path — path to the SQLite database. Defaults to project default.

    Returns:
      List of signal dicts, sorted by severity (CRITICAL first).
    """
    print("[ci_signal_detector] Starting full signal scan...")

    # ── Load all four data tables ─────────────────────────────────────────────
    shipment_rows  = _load_table(db_path, "shipments")
    inventory_rows = _load_table(db_path, "inventory")
    freight_rows   = _load_table(db_path, "freight")
    warehouse_rows = _load_table(db_path, "warehouse_picks")

    print(f"  Loaded: {len(shipment_rows)} shipments, {len(inventory_rows)} inventory, "
          f"{len(freight_rows)} freight, {len(warehouse_rows)} warehouse picks")

    # ── Run all detectors ─────────────────────────────────────────────────────
    all_signals = []

    all_signals += detect_carrier_repeat_delays(shipment_rows)
    all_signals += detect_dominant_root_cause(shipment_rows)
    all_signals += detect_high_unknown_rate(shipment_rows)
    all_signals += detect_freight_hold_pattern(freight_rows)
    all_signals += detect_weak_carrier_usage(freight_rows)
    all_signals += detect_warehouse_systemic_delays(warehouse_rows)
    all_signals += detect_inventory_repeat_stockouts(inventory_rows)
    all_signals += detect_data_quality_gaps(shipment_rows, freight_rows, warehouse_rows)

    print(f"  Detectors found: {len(all_signals)} signals")

    # ── Sort by severity ──────────────────────────────────────────────────────
    # CRITICAL problems appear first so the most urgent are always at the top.
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_signals.sort(key=lambda s: severity_order.get(s["severity"], 9))

    return all_signals
