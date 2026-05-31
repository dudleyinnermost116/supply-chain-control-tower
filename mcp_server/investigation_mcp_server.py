# mcp_server/investigation_mcp_server.py
#
# Investigation Agent — Phase 5 of the Supply Chain Control Tower.
# This is the meta-agent — combines signals from all four agents
# into one unified root cause report.
#
# Phase 7 update: now reads from SQLite instead of CSV.

from datetime import date
from mcp.server.fastmcp import FastMCP

# OLD: individual CSV loaders
# from supply_chain.data_loader import load_shipments
# from supply_chain.inventory_data_loader import load_inventory
# from supply_chain.freight_data_loader import load_freight
# from supply_chain.warehouse_data_loader import load_warehouse_picks
#
# NEW (Phase 7): single SQLite database loader
from supply_chain.db_loader import (
    load_shipments_db       as load_shipments,
    load_inventory_db       as load_inventory,
    load_freight_db         as load_freight,
    load_warehouse_picks_db as load_warehouse_picks,
)

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
from supply_chain.investigation_rules import build_investigation_report

mcp = FastMCP("investigation-agent")

TODAY = date.today()

# OLD: four separate CSV file paths
# SHIPMENTS_FILE = r"...\shipments_sample.csv"
# INVENTORY_FILE = r"...\inventory_sample.csv"
# FREIGHT_FILE   = r"...\freight_sample.csv"
# WAREHOUSE_FILE = r"...\warehouse_sample.csv"
#
# NEW (Phase 7): one SQLite database
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

# ─── HELPER: build index dicts for fast lookup ───────────────────────────────

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
    """
    sales_order_no  = ship_row.get("sales_order_no", "")
    item_no         = ship_row.get("item_no", "")

    # Shipping signals
    delay_status    = assign_delay_status(ship_row, TODAY)
    delay_days      = calculate_delay_days(ship_row, TODAY)
    shipping_reason = assign_reason_code(ship_row, TODAY)

    # Inventory signals
    inv_row          = inventory_index.get(item_no, {})
    inventory_status = assign_inventory_status(inv_row) if inv_row else "UNKNOWN"

    # Freight signals
    frt_row             = freight_index.get(sales_order_no, {})
    freight_status      = assign_freight_status(frt_row, TODAY) if frt_row else "UNKNOWN"
    freight_hold        = str(frt_row.get("freight_hold_flag", "NO")).strip().upper() == "YES"
    freight_hold_reason = frt_row.get("freight_hold_reason", "") if frt_row else ""
    carrier_name        = frt_row.get("carrier_name", "Unknown") if frt_row else "Unknown"
    carrier_tier        = assign_carrier_tier(
        frt_row.get("carrier_performance_score", "")
    ) if frt_row else "UNKNOWN"

    # Warehouse signals
    wh_row      = warehouse_index.get(sales_order_no, {})
    pick_health = assign_pick_health(wh_row, TODAY) if wh_row else "UNKNOWN"

    return {
        "sales_order_no":       sales_order_no,
        "customer_name":        ship_row.get("customer_name", ""),
        "scheduled_pick_date":  ship_row.get("scheduled_pick_date", ""),
        "delay_days":           delay_days,
        "delay_status":         delay_status,
        "shipping_reason":      shipping_reason,
        "inventory_status":     inventory_status,
        "freight_status":       freight_status,
        "freight_hold":         freight_hold,
        "freight_hold_reason":  freight_hold_reason,
        "pick_health":          pick_health,
        "carrier_tier":         carrier_tier,
        "carrier_name":         carrier_name,
    }


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────

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
    # OLD: load_shipments(SHIPMENTS_FILE), load_inventory(INVENTORY_FILE), etc.
    # NEW (Phase 7): all from single SQLite database
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    ship_row = None
    for row in ship_rows:
        if str(row.get("sales_order_no", "")).strip() == sales_order_no:
            ship_row = row
            break

    if ship_row is None:
        return {"error": f"Sales order {sales_order_no} was not found in shipments data."}

    s = _gather_signals(ship_row, inventory_index, freight_index, warehouse_index)

    return build_investigation_report(
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


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────

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
    # NEW (Phase 7): all from single SQLite database
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

        if s["delay_status"] in ("SHIPPED", "CANCELLED"):
            continue

        domain_issues = []

        if s["delay_status"] in ("DELAYED", "NEED_ACTION"):
            domain_issues.append("SHIPPING_DELAY")

        if s["inventory_status"] in ("OUT_OF_STOCK", "ON_BACKORDER", "CRITICAL"):
            domain_issues.append("INVENTORY_PROBLEM")

        if s["freight_hold"] or s["freight_status"] in ("ON_HOLD", "PICKUP_MISSED", "CARRIER_DELAYED"):
            domain_issues.append("FREIGHT_PROBLEM")

        if s["pick_health"] in ("DELAYED", "AT_RISK"):
            domain_issues.append("WAREHOUSE_PROBLEM")

        risk_score = len(domain_issues)

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

    results.sort(key=lambda x: (-x["risk_score"], -x["delay_days"]))
    return results


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────

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
    # NEW (Phase 7): all from single SQLite database
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

        root_cause_counts[cause]    = root_cause_counts.get(cause, 0) + 1
        severity_counts[severity]   = severity_counts.get(severity, 0) + 1

    top_cause = max(root_cause_counts, key=root_cause_counts.get) if root_cause_counts else "NONE"

    sorted_causes = sorted(root_cause_counts.items(), key=lambda x: x[1], reverse=True)
    root_cause_breakdown = [
        {"root_cause": cause, "order_count": count}
        for cause, count in sorted_causes
    ]

    return {
        "total_orders_assessed": total_assessed,
        "total_delayed":         total_delayed,
        "top_root_cause":        top_cause,
        "root_cause_breakdown":  root_cause_breakdown,
        "severity_breakdown":    severity_counts,
    }


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────

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
    # NEW (Phase 7): all from single SQLite database
    ship_rows = load_shipments(DB_FILE)
    inv_rows  = load_inventory(DB_FILE)
    frt_rows  = load_freight(DB_FILE)
    wh_rows   = load_warehouse_picks(DB_FILE)

    inventory_index = _index_by(inv_rows, "item_no")
    freight_index   = _index_by(frt_rows, "sales_order_no")
    warehouse_index = _index_by(wh_rows,  "sales_order_no")

    # Shipment counts
    ship_counts = {
        "total": len(ship_rows),
        "ON_TIME": 0, "DELAYED": 0, "NEED_ACTION": 0,
        "SHIPPED": 0, "CANCELLED": 0,
    }
    for row in ship_rows:
        status = assign_delay_status(row, TODAY)
        ship_counts[status] = ship_counts.get(status, 0) + 1

    # Inventory counts
    inv_counts = {
        "total": len(inv_rows),
        "HEALTHY": 0, "LOW": 0, "CRITICAL": 0,
        "OUT_OF_STOCK": 0, "ON_BACKORDER": 0,
    }
    for row in inv_rows:
        status = assign_inventory_status(row)
        inv_counts[status] = inv_counts.get(status, 0) + 1

    # Freight counts
    frt_counts = {
        "total": len(frt_rows),
        "SCHEDULED": 0, "IN_TRANSIT": 0, "DELIVERED": 0,
        "ON_HOLD": 0, "PICKUP_MISSED": 0, "CARRIER_DELAYED": 0,
    }
    for row in frt_rows:
        status = assign_freight_status(row, TODAY)
        frt_counts[status] = frt_counts.get(status, 0) + 1

    # Warehouse counts
    wh_counts = {"total": len(wh_rows), "ON_TRACK": 0, "AT_RISK": 0, "DELAYED": 0, "UNKNOWN": 0}
    for row in wh_rows:
        health = assign_pick_health(row, TODAY)
        wh_counts[health] = wh_counts.get(health, 0) + 1

    # Multi-domain risk count
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

    # Plain-English briefing
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