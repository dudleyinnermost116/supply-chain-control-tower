# mcp_server/investigation_mcp_server.py
#
# Owner: Vishal
# Investigation Agent — Phase 5 of the Supply Chain Control Tower.
#
# This is the meta-agent. It does NOT have its own data file.
# Instead, it loads data from all four existing tables/CSVs and combines
# the signals into one unified root cause report.
#
# Answers the question:
#   "Why is this order delayed, and what exactly should I do about it?"
#
# Works by calling logic from:
#   shipping   — delay status and reason code
#   inventory  — stock availability for the item on the order
#   freight    — carrier pickup status and hold flags
#   warehouse  — pick status and operational issues
#
# Tools in this server:
#   investigate_order       — full cross-agent root cause report for one order
#   find_orders_at_risk     — scans all orders for multi-domain problems
#   get_root_cause_summary  — aggregate breakdown of root causes across all orders
#   get_daily_risk_report   — morning briefing combining all four agents
#
# SECURITY FIXES ADDED (Phase 10):
#   - sanitise_input on investigate_order which accepts sales_order_no
#   - shield_row / shield_rows on all return values containing database text
#   - sys.path fix so imports work regardless of Claude Desktop launch location
#   - get_database_path() replaces all four hardcoded file paths

import sys
import os

# PHASE 10 CHANGE: sys.path fix
# Ensures Python can find supply_chain and config modules
# regardless of where Claude Desktop launches the server from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from mcp.server.fastmcp import FastMCP

# ── Data loaders ──────────────────────────────────────────────────────────────
from supply_chain.data_loader import load_shipments
from supply_chain.inventory_data_loader import load_inventory
from supply_chain.freight_data_loader import load_freight
from supply_chain.warehouse_data_loader import load_warehouse_picks

# ── Rules engines ─────────────────────────────────────────────────────────────
from supply_chain.rules import (
    assign_delay_status,
    assign_reason_code,
    calculate_delay_days,
)
from supply_chain.inventory_rules import assign_inventory_status
from supply_chain.freight_rules import (
    assign_freight_status,
    assign_carrier_tier,
    calculate_pickup_delay_days,
)
from supply_chain.warehouse_rules import assign_pick_health

# ── Investigation logic ───────────────────────────────────────────────────────
from supply_chain.investigation_rules import build_investigation_report

# SECURITY FIX:
# sanitise_input — validates string inputs before use
# shield_row     — scans a single result dict for injection text
# shield_rows    — scans a list of result dicts for injection text
from supply_chain.input_validation import sanitise_input
from supply_chain.prompt_injection_shield import shield_rows, shield_row

# PHASE 10 CHANGE: Central Settings
# get_database_path() reads from config/settings.yaml
# Replaces all four hardcoded file path lines:
#   SHIPMENTS_FILE = r"C:\Users\preet\...\shipments_sample.csv"
#   INVENTORY_FILE = r"C:\Users\preet\...\inventory_sample.csv"
#   FREIGHT_FILE   = r"C:\Users\preet\...\freight_sample.csv"
#   WAREHOUSE_FILE = r"C:\Users\preet\...\warehouse_sample.csv"
# All four agents now read from the same single SQLite database
from config.settings_loader import get_database_path
DB_FILE = get_database_path()

mcp = FastMCP("investigation-agent")

TODAY = date.today()


# ─── HELPER: build index dicts for fast lookup ───────────────────────────────
# Rather than looping through all rows four times per order, we build
# a dict keyed by the join field once per tool call.
# Example: inventory_index["ITEM-001"] gives us the inventory row for ITEM-001
# instantly instead of looping through all inventory rows every time.

def _index_by(rows: list, key: str) -> dict:
    """Returns a dict mapping key -> first matching row."""
    result = {}
    for row in rows:
        k = str(row.get(key, "")).strip()
        if k and k not in result:
            result[k] = row
    return result


# ─── HELPER: extract cross-agent signals for one shipment row ────────────────

def _gather_signals(ship_row: dict,
                    inventory_index: dict,
                    freight_index: dict,
                    warehouse_index: dict) -> dict:
    """
    Given one shipment row and three lookup dicts, returns a flat dict
    of all the signals needed to call build_investigation_report.

    This helper is called by every tool that loops over all shipments.
    Centralising the signal-gathering here means if we add a new agent,
    we only update this one function instead of every tool.
    """
    sales_order_no = ship_row.get("sales_order_no", "")
    item_no        = ship_row.get("item_no", "")

    # ── Shipping signals ──────────────────────────────────────────────────────
    delay_status    = assign_delay_status(ship_row, TODAY)
    delay_days      = calculate_delay_days(ship_row, TODAY)
    shipping_reason = assign_reason_code(ship_row, TODAY)

    # ── Inventory signals ─────────────────────────────────────────────────────
    inv_row          = inventory_index.get(item_no, {})
    inventory_status = assign_inventory_status(inv_row) if inv_row else "UNKNOWN"

    # ── Freight signals ───────────────────────────────────────────────────────
    frt_row             = freight_index.get(sales_order_no, {})
    freight_status      = assign_freight_status(frt_row, TODAY) if frt_row else "UNKNOWN"
    freight_hold        = str(frt_row.get("freight_hold_flag", "NO")).strip().upper() == "YES"
    freight_hold_reason = frt_row.get("freight_hold_reason", "") if frt_row else ""
    carrier_name        = frt_row.get("carrier_name", "Unknown") if frt_row else "Unknown"
    carrier_tier        = assign_carrier_tier(
        frt_row.get("carrier_performance_score", "")
    ) if frt_row else "UNKNOWN"

    # ── Warehouse signals ─────────────────────────────────────────────────────
    wh_row      = warehouse_index.get(sales_order_no, {})
    pick_health = assign_pick_health(wh_row, TODAY) if wh_row else "UNKNOWN"

    return {
        "sales_order_no":      sales_order_no,
        "customer_name":       ship_row.get("customer_name", ""),
        "scheduled_pick_date": ship_row.get("scheduled_pick_date", ""),
        "delay_days":          delay_days,
        "delay_status":        delay_status,
        "shipping_reason":     shipping_reason,
        "inventory_status":    inventory_status,
        "freight_status":      freight_status,
        "freight_hold":        freight_hold,
        "freight_hold_reason": freight_hold_reason,
        "pick_health":         pick_health,
        "carrier_tier":        carrier_tier,
        "carrier_name":        carrier_name,
    }


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - Has input parameter (sales_order_no) → sanitise_input at TOP
#   - Returns a single dict — build_investigation_report includes
#     customer_name, carrier_name, contributing_factors (text) → shield_row on return

@mcp.tool()
def investigate_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user wants a complete root cause investigation
    for a specific delayed order. This is the most powerful single tool
    in the entire system — it combines data from all four agents.

    Input: sales_order_no — the exact order number (for example: SO-1003)

    Returns a full investigation report including:
    - Delay status and how many days overdue
    - Overall severity rating (CRITICAL, HIGH, MEDIUM, LOW)
    - Confirmed root cause with explanation
    - List of all contributing factors found across agents
    - The single most important first action to take right now
    - Raw signals from every agent for transparency

    Use this when the user asks things like:
    - "Investigate order SO-1003"
    - "Why is SO-1007 delayed?"
    - "Give me a full root cause report for SO-1005"
    - "What is causing the delay on SO-1002?"
    - "Do a deep dive on order SO-1009"
    - "Investigate the most delayed order"
    """
    # SECURITY FIX: validate sales_order_no before loading any data
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    # Load all four data sources
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    # Build lookup dicts for fast cross-agent joining
    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    # Find the shipment row for this order
    ship_row = None
    for row in ship_rows:
        if str(row.get("sales_order_no", "")).strip() == sales_order_no:
            ship_row = row
            break

    if ship_row is None:
        return {"error": f"Sales order {sales_order_no} was not found in shipments data."}

    # Gather all signals from all four agents
    s = _gather_signals(ship_row, inventory_index, freight_index, warehouse_index)

    # SECURITY FIX: shield_row wraps the full investigation report
    # contributing_factors is a list of plain-English strings built from
    # database values — customer_name and carrier_name are raw database text
    # REPLACES the old direct return statement
    return shield_row(build_investigation_report(
        sales_order_no      = s["sales_order_no"],
        customer_name       = s["customer_name"],
        scheduled_pick_date = s["scheduled_pick_date"],
        delay_days          = s["delay_days"],
        delay_status        = s["delay_status"],
        shipping_reason     = s["shipping_reason"],
        inventory_status    = s["inventory_status"],
        freight_status      = s["freight_status"],
        freight_hold        = s["freight_hold"],
        freight_hold_reason = s["freight_hold_reason"],
        pick_health         = s["pick_health"],
        carrier_tier        = s["carrier_tier"],
        carrier_name        = s["carrier_name"],
    ))


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST with customer_name from the database → shield_rows on return

@mcp.tool()
def find_orders_at_risk() -> list:
    """
    Use this tool when the user wants to proactively identify which orders
    are most likely to become serious problems — before they escalate further.

    Scans all shipments and flags orders that have problems in more than
    one domain (for example: inventory is low AND the warehouse pick is
    delayed). Multi-domain problems are always more dangerous than single ones.

    Returns a list of at-risk orders sorted by risk score (highest first).
    Each result shows which domains have issues and a summary risk verdict.

    Use this when the user asks things like:
    - "Which orders are most at risk right now?"
    - "Show me orders with problems in multiple areas"
    - "What should I watch before things get worse?"
    - "Find orders that might escalate today"
    - "Give me a proactive risk scan"
    - "Which delayed orders have the most compounding problems?"
    """
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    results = []

    for ship_row in ship_rows:
        s = _gather_signals(ship_row, inventory_index, freight_index, warehouse_index)

        # Only assess orders that are not yet shipped or cancelled
        if s["delay_status"] in ("SHIPPED", "CANCELLED"):
            continue

        # Score each domain as a problem (1) or not (0)
        # The more domains with problems, the higher the risk score
        domain_issues = []

        if s["delay_status"] in ("DELAYED", "NEED_ACTION"):
            domain_issues.append("SHIPPING_DELAY")

        if s["inventory_status"] in ("OUT_OF_STOCK", "ON_BACKORDER", "CRITICAL"):
            domain_issues.append("INVENTORY_PROBLEM")

        if s["freight_hold"] or s["freight_status"] in ("ON_HOLD", "PICKUP_MISSED", "CARRIER_DELAYED"):
            domain_issues.append("FREIGHT_PROBLEM")

        if s["pick_health"] in ("DELAYED", "AT_RISK"):
            domain_issues.append("WAREHOUSE_PROBLEM")

        # Risk score = number of domains with problems
        risk_score = len(domain_issues)

        # Only include orders with at least one domain problem
        if risk_score == 0:
            continue

        results.append({
            "sales_order_no":   s["sales_order_no"],
            "customer_name":    s["customer_name"],
            "delay_days":       s["delay_days"],
            "delay_status":     s["delay_status"],
            "risk_score":       risk_score,
            "problem_domains":  domain_issues,
            "root_cause":       s["shipping_reason"],
            "inventory_status": s["inventory_status"],
            "freight_status":   s["freight_status"],
            "pick_health":      s["pick_health"],
        })

    if not results:
        return [{"message": "No orders with multi-domain risk found. All orders look stable."}]

    # Sort: most problem domains first, then most delayed
    results.sort(key=lambda x: (-x["risk_score"], -x["delay_days"]))

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # customer_name is raw database text
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a dict of counts and breakdown lists — all controlled constants
#     and integers — no raw database text in the output → no shield needed

@mcp.tool()
def get_root_cause_summary() -> dict:
    """
    Use this tool when the user wants to understand the big picture —
    what categories of problems are causing the most delays across
    all orders, looking at all four agents together.

    Returns:
    - Total orders assessed
    - Count of orders by root cause category
    - Count of orders by severity level
    - The top root cause (the single biggest problem category today)

    Use this when the user asks things like:
    - "What is the most common cause of delays today?"
    - "Give me a root cause breakdown"
    - "How many orders are delayed due to freight vs inventory?"
    - "What category of problem should I focus on first?"
    - "Summarise why everything is delayed"
    - "Which root cause is hurting us most today?"
    """
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    root_cause_counts = {}
    severity_counts   = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    total_assessed    = 0
    total_delayed     = 0

    for ship_row in ship_rows:
        s = _gather_signals(ship_row, inventory_index, freight_index, warehouse_index)

        # Skip shipped and cancelled
        if s["delay_status"] in ("SHIPPED", "CANCELLED"):
            continue

        total_assessed += 1

        if s["delay_status"] in ("DELAYED", "NEED_ACTION"):
            total_delayed += 1

        report = build_investigation_report(
            sales_order_no      = s["sales_order_no"],
            customer_name       = s["customer_name"],
            scheduled_pick_date = s["scheduled_pick_date"],
            delay_days          = s["delay_days"],
            delay_status        = s["delay_status"],
            shipping_reason     = s["shipping_reason"],
            inventory_status    = s["inventory_status"],
            freight_status      = s["freight_status"],
            freight_hold        = s["freight_hold"],
            freight_hold_reason = s["freight_hold_reason"],
            pick_health         = s["pick_health"],
            carrier_tier        = s["carrier_tier"],
            carrier_name        = s["carrier_name"],
        )

        cause    = report["root_cause"]
        severity = report["severity"]

        root_cause_counts[cause] = root_cause_counts.get(cause, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    top_cause = max(root_cause_counts, key=root_cause_counts.get) if root_cause_counts else "NONE"

    sorted_causes = sorted(
        root_cause_counts.items(), key=lambda x: x[1], reverse=True
    )
    root_cause_breakdown = [
        {"root_cause": cause, "order_count": count}
        for cause, count in sorted_causes
    ]

    # No shield needed — all values are counts, known constants, or
    # root_cause strings which are controlled values from our rules engine
    return {
        "total_orders_assessed": total_assessed,
        "total_delayed":         total_delayed,
        "top_root_cause":        top_cause,
        "root_cause_breakdown":  root_cause_breakdown,
        "severity_breakdown":    severity_counts,
    }


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES:
#   - No input parameter → no sanitise_input needed
#   - Returns a dict — briefing string is built from integers and known constants
#     not raw database text → no shield needed

@mcp.tool()
def get_daily_risk_report() -> dict:
    """
    Use this tool when the user wants the complete morning briefing —
    a single structured report that combines health signals from all
    four agents into one executive-level daily snapshot.

    Returns:
    - Today's date
    - Shipment delay counts (on time, delayed, need action)
    - Inventory health counts (healthy, low, critical, out of stock, backorder)
    - Freight health counts (scheduled, in transit, on hold, missed)
    - Warehouse pick health counts (on track, at risk, delayed)
    - Number of orders with multi-domain risk
    - Top root cause across the system
    - A plain-English briefing paragraph

    Use this when the user asks things like:
    - "Give me today's risk report"
    - "Morning briefing"
    - "What does the supply chain look like today?"
    - "Daily summary across all agents"
    - "What should I know before my 9am standup?"
    - "Give me the full picture"
    - "How is the supply chain performing today?"
    """
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    # ── Shipment counts ───────────────────────────────────────────────────────
    ship_counts = {
        "total": len(ship_rows),
        "ON_TIME": 0, "DELAYED": 0, "NEED_ACTION": 0,
        "SHIPPED": 0, "CANCELLED": 0,
    }
    for row in ship_rows:
        status = assign_delay_status(row, TODAY)
        ship_counts[status] = ship_counts.get(status, 0) + 1

    # ── Inventory counts ──────────────────────────────────────────────────────
    inv_counts = {
        "total": len(inv_rows),
        "HEALTHY": 0, "LOW": 0, "CRITICAL": 0,
        "OUT_OF_STOCK": 0, "ON_BACKORDER": 0,
    }
    for row in inv_rows:
        status = assign_inventory_status(row)
        inv_counts[status] = inv_counts.get(status, 0) + 1

    # ── Freight counts ────────────────────────────────────────────────────────
    frt_counts = {
        "total": len(frt_rows),
        "SCHEDULED": 0, "IN_TRANSIT": 0, "DELIVERED": 0,
        "ON_HOLD": 0, "PICKUP_MISSED": 0, "CARRIER_DELAYED": 0,
    }
    for row in frt_rows:
        status = assign_freight_status(row, TODAY)
        frt_counts[status] = frt_counts.get(status, 0) + 1

    # ── Warehouse counts ──────────────────────────────────────────────────────
    wh_counts = {"total": len(wh_rows), "ON_TRACK": 0, "AT_RISK": 0, "DELAYED": 0, "UNKNOWN": 0}
    for row in wh_rows:
        health = assign_pick_health(row, TODAY)
        wh_counts[health] = wh_counts.get(health, 0) + 1

    # ── Multi-domain risk count ───────────────────────────────────────────────
    multi_domain_count = 0
    root_cause_counts  = {}

    for ship_row in ship_rows:
        s = _gather_signals(ship_row, inventory_index, freight_index, warehouse_index)

        if s["delay_status"] in ("SHIPPED", "CANCELLED"):
            continue

        issues = 0
        if s["delay_status"] in ("DELAYED", "NEED_ACTION"):
            issues += 1
        if s["inventory_status"] in ("OUT_OF_STOCK", "ON_BACKORDER", "CRITICAL"):
            issues += 1
        if s["freight_hold"] or s["freight_status"] in ("ON_HOLD", "PICKUP_MISSED"):
            issues += 1
        if s["pick_health"] in ("DELAYED", "AT_RISK"):
            issues += 1

        if issues >= 2:
            multi_domain_count += 1

        if s["delay_status"] in ("DELAYED", "NEED_ACTION"):
            report = build_investigation_report(
                sales_order_no      = s["sales_order_no"],
                customer_name       = s["customer_name"],
                scheduled_pick_date = s["scheduled_pick_date"],
                delay_days          = s["delay_days"],
                delay_status        = s["delay_status"],
                shipping_reason     = s["shipping_reason"],
                inventory_status    = s["inventory_status"],
                freight_status      = s["freight_status"],
                freight_hold        = s["freight_hold"],
                freight_hold_reason = s["freight_hold_reason"],
                pick_health         = s["pick_health"],
                carrier_tier        = s["carrier_tier"],
                carrier_name        = s["carrier_name"],
            )
            cause = report["root_cause"]
            root_cause_counts[cause] = root_cause_counts.get(cause, 0) + 1

    top_cause = (
        max(root_cause_counts, key=root_cause_counts.get)
        if root_cause_counts else "NONE"
    )

    # ── Build plain-English briefing ──────────────────────────────────────────
    delayed_total = ship_counts["DELAYED"] + ship_counts["NEED_ACTION"]
    need_action   = ship_counts["NEED_ACTION"]
    inv_problems  = inv_counts["CRITICAL"] + inv_counts["OUT_OF_STOCK"] + inv_counts["ON_BACKORDER"]
    frt_problems  = frt_counts["ON_HOLD"] + frt_counts["PICKUP_MISSED"]
    wh_problems   = wh_counts["DELAYED"] + wh_counts["AT_RISK"]

    briefing_parts = []

    if need_action > 0:
        briefing_parts.append(
            f"{need_action} order(s) need IMMEDIATE action — more than 5 days overdue."
        )
    if delayed_total > 0:
        briefing_parts.append(
            f"{delayed_total} of {ship_counts['total']} shipments are delayed. "
            f"Top root cause: {top_cause.replace('_', ' ')}."
        )
    if multi_domain_count > 0:
        briefing_parts.append(
            f"{multi_domain_count} order(s) have problems across multiple domains — highest priority."
        )
    if inv_problems > 0:
        briefing_parts.append(
            f"{inv_problems} inventory item(s) are critical, out of stock, or on backorder."
        )
    if frt_problems > 0:
        briefing_parts.append(
            f"{frt_problems} freight record(s) have holds or missed pickups."
        )
    if wh_problems > 0:
        briefing_parts.append(
            f"{wh_problems} warehouse pick(s) are delayed or at risk."
        )
    if not briefing_parts:
        briefing_parts.append("All systems are performing normally. No immediate action required.")

    briefing = " ".join(briefing_parts)

    # No shield needed — all values here are counts, dates, and
    # briefing text built entirely from integers and known constants
    return {
        "date": str(TODAY),
        "briefing": briefing,
        "shipment_health": ship_counts,
        "inventory_health": inv_counts,
        "freight_health": frt_counts,
        "warehouse_health": wh_counts,
        "multi_domain_risk_orders": multi_domain_count,
        "top_root_cause": top_cause,
    }


if __name__ == "__main__":
    mcp.run()