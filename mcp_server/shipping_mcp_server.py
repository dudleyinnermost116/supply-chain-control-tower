from datetime import date
from supply_chain.recommendations import build_recommendation
from mcp.server.fastmcp import FastMCP
from supply_chain.recommendations import build_recommendation, calculate_risk_level

# PHASE 7 CHANGE: switched from CSV loader to SQLite database loader
# The old line was: from supply_chain.data_loader import load_shipments
# load_shipments_db reads from supply_chain.db instead of a CSV file
# We give it the alias "load_shipments" so all the tool code below
# does not need to change — it still just calls load_shipments(DB_FILE)
from supply_chain.db_loader import load_shipments_db as load_shipments

from supply_chain.rules import (
    calculate_delay_days,
    assign_delay_status,
    assign_reason_code,
)

# SECURITY FIX (Phase 10 Step 6d):
# sanitise_input  — validates string inputs from Claude before we use them
#                   prevents injection attacks through tool parameters
# shield_rows     — scans a LIST of result dicts before returning to Claude
#                   replaces any suspicious text in data fields with [REDACTED]
# shield_row      — same as shield_rows but for a SINGLE dict (not a list)
from supply_chain.input_validation import sanitise_input
from supply_chain.prompt_injection_shield import shield_rows, shield_row

# PHASE 10 CHANGE: sys.path fix
# os.path.abspath(__file__) finds the true location of THIS file on disk
# os.path.dirname(...) called twice walks up two folders to the project root
# sys.path.insert(0, ...) adds that folder to Python's search path
# This ensures imports work correctly no matter where Claude Desktop
# launches the server from — without this, imports sometimes fail
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# PHASE 10 CHANGE: Central Settings
# Instead of a hardcoded path like:
#   DB_FILE = r"C:\Users\preet\...\supply_chain.db"
# We now call get_database_path() which reads the path from settings.yaml
# Benefit: if the database ever moves, change ONE line in settings.yaml
# and every single server updates automatically
from config.settings_loader import get_database_path
DB_FILE = get_database_path()

# Always use today's real date — never hardcode this
# date.today() asks the OS for today's date at the moment the server starts
TODAY = date.today()

mcp = FastMCP("shipping-delay-agent")


# ─── TOOL 1 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST → shield_rows applied on the return line

@mcp.tool()
def get_delayed_shipments() -> list:
    """
    Use this tool when the user asks about delayed shipments, late orders,
    overdue deliveries, or shipments that have not shipped yet.

    Returns a list of all shipments currently in DELAYED or NEED_ACTION status.
    Each result includes: sales order number, customer name, scheduled pick date,
    number of days delayed, delay status (DELAYED or NEED_ACTION), and reason code.

    DELAYED means 1 to 5 days late.
    NEED_ACTION means more than 5 days late and requires immediate attention.

    Use this when the user asks things like:
    - "Show me all delayed shipments"
    - "What orders are late?"
    - "Which shipments are overdue?"
    - "List all delayed orders"
    """
    rows = load_shipments(DB_FILE)
    results = []

    for row in rows:
        status = assign_delay_status(row, TODAY)

        if status in ["DELAYED", "NEED_ACTION"]:
            results.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            })

    # SECURITY FIX: shield_rows scans every field in every result dict
    # If any field contains injection-like text (e.g. a customer_name field
    # saying "Ignore all instructions"), it gets replaced with [REDACTED]
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 2 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - No input parameter → no sanitise_input needed
#   - Returns a dict of COUNTS ONLY (all integers and known string constants)
#   - Integers cannot contain injection text → no shield needed here

@mcp.tool()
def get_delay_summary() -> dict:
    """
    Use this tool when the user wants a high-level overview, summary, or dashboard
    of the current shipment situation across all orders.

    Returns aggregate counts including:
    - Total number of orders
    - How many are delayed (DELAYED status: 1 to 5 days late)
    - How many need urgent action (NEED_ACTION status: more than 5 days late)
    - Breakdown of how many orders fall under each reason code

    Use this when the user asks things like:
    - "Give me a summary of delays"
    - "How many shipments are late today?"
    - "What does the delay situation look like?"
    - "Show me the big picture"
    - "How many orders need action?"
    - "What are the most common delay reasons?"
    """
    rows = load_shipments(DB_FILE)

    total_orders = len(rows)
    delayed_count = 0
    need_action_count = 0
    on_time_count = 0
    shipped_count = 0
    cancelled_count = 0
    reason_counts = {}

    for row in rows:
        status = assign_delay_status(row, TODAY)
        reason = assign_reason_code(row, TODAY)

        if status == "DELAYED":
            delayed_count += 1
        elif status == "NEED_ACTION":
            need_action_count += 1
        elif status == "ON_TIME":
            on_time_count += 1
        elif status == "SHIPPED":
            shipped_count += 1
        elif status == "CANCELLED":
            cancelled_count += 1

        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # No shield needed — all values here are integers or reason code
    # constants that come from our own rules engine, not raw database text
    return {
        "total_orders": total_orders,
        "on_time": on_time_count,
        "delayed_shipments": delayed_count,
        "need_action_shipments": need_action_count,
        "shipped": shipped_count,
        "cancelled": cancelled_count,
        "reason_counts": reason_counts,
    }


# ─── TOOL 3 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - Has input parameter (sales_order_no) → sanitise_input added at TOP
#   - Returns a SINGLE DICT with text fields → shield_row applied on return

@mcp.tool()
def get_shipment_by_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user asks about a specific sales order by its order number.
    This is a single-order lookup tool — use it when the user provides an order ID.

    Input: sales_order_no — the exact sales order number (for example: SO-1001)

    Returns full details for that order including:
    - Customer name
    - Scheduled pick date
    - Ship confirm date (blank if not yet shipped)
    - Order status (from the source system)
    - Number of days delayed
    - Delay status (ON_TIME, DELAYED, NEED_ACTION, SHIPPED, or CANCELLED)
    - Reason code explaining why it is delayed

    Use this when the user asks things like:
    - "What is the status of order SO-1042?"
    - "Look up order SO-1007"
    - "Tell me about sales order SO-1015"
    - "Is order SO-1003 delayed?"
    """
    # SECURITY FIX: validate the order number BEFORE loading any data
    # sanitise_input checks:
    #   - not empty or whitespace-only
    #   - not longer than 20 characters (real order numbers are ~7 chars)
    #   - no dangerous characters like ' " ; < > ` ( ) | & $
    # If any check fails, "error" will be in the returned dict
    # and we return immediately — load_shipments never runs
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    rows = load_shipments(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_delay_status(row, TODAY)

            # SECURITY FIX: shield_row wraps the result dict
            # customer_name and other text fields come from the database
            # and could theoretically contain injection text
            # shield_row replaces any suspicious field with [REDACTED]
            # REPLACES the old direct return statement
            return shield_row({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "ship_confirm_date": row.get("ship_confirm_date", ""),
                "order_status": row.get("order_status", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            })

    return {"error": f"Sales order {sales_order_no} was not found."}


# ─── TOOL 4 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - No input parameter → no sanitise_input needed
#   - Returns a LIST → shield_rows applied on the return line

@mcp.tool()
def get_need_action_shipments() -> list:
    """
    Use this tool when the user asks about urgent shipments, critical delays,
    escalations, or orders that are severely overdue and need immediate attention.

    Returns only shipments in NEED_ACTION status — these are orders delayed
    by more than 5 days that have not shipped and are not cancelled.
    Results are sorted from most delayed to least delayed.

    Each result includes: sales order number, customer name, scheduled pick date,
    delay days, delay status, and reason code.

    Use this when the user asks things like:
    - "What needs urgent attention?"
    - "Show me critical delays"
    - "Which orders are severely overdue?"
    - "What should I escalate today?"
    - "Show me the worst delays"
    - "What orders need action right now?"
    """
    rows = load_shipments(DB_FILE)
    results = []

    for row in rows:
        status = assign_delay_status(row, TODAY)

        if status == "NEED_ACTION":
            results.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            })

    # Sort worst delays first so the most urgent appear at the top
    results.sort(key=lambda x: x["delay_days"], reverse=True)

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 5 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - Has input parameter (reason_code) → sanitise_input added at TOP
#   - reason_code is in ALLOWED_VALUES in input_validation.py, so only
#     the 8 known reason codes will pass — everything else is rejected
#   - Returns a LIST → shield_rows applied on the return line

@mcp.tool()
def get_shipments_by_reason_code(reason_code: str) -> list:
    """
    Use this tool when the user wants to see all shipments affected by a
    specific delay reason. Use it to investigate one root cause across orders.

    Input: reason_code — must be one of the following exact values:
        BACKORDER
        INVENTORY_SHORTAGE
        TRUCK_NOT_AVAILABLE
        CARRIER_DELAY
        WAREHOUSE_PICK_DELAY
        FREIGHT_HOLD
        UNKNOWN_NEEDS_REVIEW
        NOT_APPLICABLE

    Returns all shipments (any status) that match the given reason code.
    Each result includes: sales order number, customer name, scheduled pick date,
    delay days, delay status, and reason code.

    Use this when the user asks things like:
    - "Show me all freight hold orders"
    - "Which orders are on backorder?"
    - "How many shipments have a carrier delay?"
    - "Show me everything with TRUCK_NOT_AVAILABLE"
    - "List all inventory shortage orders"
    - "What orders are unknown and need review?"
    """
    # SECURITY FIX: validate reason_code input
    # field_name="reason_code" triggers the ALLOWED_VALUES check in
    # input_validation.py — only the 8 known reason codes pass
    # Return is wrapped in a list [] because this tool always returns a list
    check = sanitise_input(reason_code, field_name="reason_code", max_length=30)
    if "error" in check:
        return [check]

    rows = load_shipments(DB_FILE)
    results = []

    # Normalize input so "freight hold" or "FREIGHT HOLD" still works
    normalized_input = reason_code.strip().upper().replace(" ", "_")

    for row in rows:
        assigned_reason = assign_reason_code(row, TODAY)

        if assigned_reason == normalized_input:
            status = assign_delay_status(row, TODAY)
            results.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assigned_reason,
            })

    if not results:
        return [{"message": f"No shipments found with reason code: {normalized_input}"}]

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 6 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - Has input parameter (customer_name) → sanitise_input added at TOP
#   - customer_name is NOT in ALLOWED_VALUES — any name is valid
#     so we just check length and safe characters
#   - max_length=100 because real customer names can be longer than order numbers
#   - Returns a LIST → shield_rows is especially important here because
#     customer_name is the most likely field to contain injection text

@mcp.tool()
def get_shipments_by_customer(customer_name: str) -> list:
    """
    Use this tool when the user asks about shipments for a specific customer,
    account, or buyer. Supports partial name matching — the user does not need
    to type the exact customer name.

    Input: customer_name — full or partial customer name (case-insensitive)
    Example inputs: "Acme", "acme corp", "BLUE RIDGE"

    Returns all shipments for matching customers, including all statuses.
    Each result includes: sales order number, customer name, scheduled pick date,
    delay days, delay status, and reason code.

    Use this when the user asks things like:
    - "What is delayed for Acme Corp?"
    - "Show me all orders for Blue Ridge"
    - "What is the shipment status for Delta Supply?"
    - "How many orders does Summit Retail have?"
    - "Is Pinnacle Foods impacted by any delays?"
    - "Show me everything for customer Acme"
    """
    # SECURITY FIX: validate the customer_name input
    # max_length=100 — real customer names can be long like "Blue Ridge Supply Co."
    # allow_spaces=True (default) — names like "Acme Corp" contain spaces
    # customer_name is NOT in ALLOWED_VALUES so any name passes the value check
    # Return is wrapped in a list [] because this tool always returns a list
    check = sanitise_input(customer_name, field_name="customer_name", max_length=100)
    if "error" in check:
        return [check]

    rows = load_shipments(DB_FILE)
    results = []

    # Partial, case-insensitive match so "acme" matches "Acme Corp"
    search_term = customer_name.strip().lower()

    for row in rows:
        row_customer = row.get("customer_name", "").lower()

        if search_term in row_customer:
            status = assign_delay_status(row, TODAY)
            results.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            })

    if not results:
        return [{"message": f"No shipments found for customer: {customer_name}"}]

    # SECURITY FIX: shield_rows is especially important here
    # customer_name is raw text from your database — the most likely
    # field an attacker would try to put injection text into
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 7 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - Has input parameter (delay_status) → sanitise_input added at TOP
#   - delay_status IS in ALLOWED_VALUES — only 5 valid statuses pass
#   - Returns a LIST → shield_rows applied on the return line

@mcp.tool()
def get_shipments_by_delay_status(delay_status: str) -> list:
    """
    Use this tool when the user wants to see all shipments that match a specific
    delay status category. This is the most flexible status filter tool.

    Input: delay_status — must be one of the following exact values:
        ON_TIME        — scheduled pick date is today or in the future
        DELAYED        — overdue by 1 to 5 days, not yet shipped
        NEED_ACTION    — overdue by more than 5 days, not yet shipped
        SHIPPED        — already ship-confirmed
        CANCELLED      — order is cancelled

    Returns all shipments matching the given status.
    Each result includes: sales order number, customer name, scheduled pick date,
    delay days, delay status, and reason code.

    Use this when the user asks things like:
    - "Show me all on-time shipments"
    - "List all shipped orders"
    - "How many orders are cancelled?"
    - "Show me everything in DELAYED status"
    - "Which orders have been ship confirmed?"
    - "Give me all orders that are on time"
    """
    # SECURITY FIX: validate delay_status input
    # field_name="delay_status" triggers the ALLOWED_VALUES check —
    # only ON_TIME, DELAYED, NEED_ACTION, SHIPPED, CANCELLED pass
    # Return wrapped in [] because this tool always returns a list
    check = sanitise_input(delay_status, field_name="delay_status", max_length=20)
    if "error" in check:
        return [check]

    rows = load_shipments(DB_FILE)
    results = []

    # Normalize input so "need action" or "need_action" both work
    normalized_status = delay_status.strip().upper().replace(" ", "_")

    valid_statuses = ["ON_TIME", "DELAYED", "NEED_ACTION", "SHIPPED", "CANCELLED"]

    if normalized_status not in valid_statuses:
        return [{
            "error": f"Invalid status '{delay_status}'. Valid options are: {', '.join(valid_statuses)}"
        }]

    for row in rows:
        status = assign_delay_status(row, TODAY)

        if status == normalized_status:
            results.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            })

    if not results:
        return [{"message": f"No shipments found with status: {normalized_status}"}]

    # SECURITY FIX: shield_rows scans all result dicts before returning
    # REPLACES the old line: return results
    return shield_rows(results)


# ─── TOOL 8 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - Has input parameter (sales_order_no) → sanitise_input added at TOP
#   - Returns a SINGLE DICT with text fields → shield_row applied on return

@mcp.tool()
def recommend_action_for_order(sales_order_no: str) -> dict:
    """
    Use this tool when the user wants to know what action to take for a
    specific delayed order. This tool goes beyond reporting — it tells the
    user what to do, who is responsible, and whether escalation is needed.

    Input: sales_order_no — the exact sales order number (for example: SO-1003)

    Returns a full action recommendation including:
    - Order details (customer, scheduled date, delay days, status, reason)
    - Responsible team who should take action
    - Specific recommended action steps
    - Escalation note based on delay severity
    - Customer impact summary

    Use this when the user asks things like:
    - "What should I do about order SO-1003?"
    - "Recommend an action for SO-1011"
    - "How should I resolve the delay on SO-1007?"
    - "What is the next step for order SO-1019?"
    - "Give me a recommendation for this order"
    - "What action should I take on the most delayed order?"
    """
    # SECURITY FIX: same validation as get_shipment_by_order
    # max_length=20, safe characters only, not empty
    check = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
    if "error" in check:
        return check

    rows = load_shipments(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_delay_status(row, TODAY)
            delay_days = calculate_delay_days(row, TODAY)
            reason = assign_reason_code(row, TODAY)

            recommendation = build_recommendation(reason, status, delay_days)

            # SECURITY FIX: shield_row wraps the full result dict
            # recommended_action and customer_impact are text strings
            # customer_name is raw database text
            # All of these pass through shield_row before Claude sees them
            # REPLACES the old direct return statement
            return shield_row({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "delay_days": delay_days,
                "delay_status": status,
                "reason_code": reason,
                "responsible_team": recommendation["responsible_team"],
                "recommended_action": recommendation["recommended_action"],
                "escalation_note": recommendation["escalation_note"],
                "customer_impact": recommendation["customer_impact"],
            })

    return {"error": f"Sales order {sales_order_no} was not found."}


# ─── TOOL 9 ─────────────────────────────────────────────────────────────────
# SECURITY NOTES FOR THIS TOOL:
#   - No input parameter → no sanitise_input needed
#   - Returns a SINGLE DICT — most values are integers and constants
#   - most_urgent contains customer_name from the database → shield_row
#     added as a precaution on the final return

@mcp.tool()
def get_management_summary() -> dict:
    """
    Use this tool when the user wants a complete daily briefing, morning report,
    executive summary, or management overview of the current shipment situation.

    This is the most comprehensive single tool in the shipping delay agent.
    It combines delay counts, risk level, top reason codes, and the most
    urgent order recommendation into one structured response.

    Returns:
    - Today's date
    - Total orders and full status breakdown
    - Overall risk level (LOW, MEDIUM, HIGH, or CRITICAL)
    - Top 3 delay reason codes and how many orders each affects
    - The single most urgent order with full recommendation
    - A plain-English briefing summary Claude can read aloud

    Use this when the user asks things like:
    - "Give me the management summary"
    - "What is the situation today?"
    - "Morning briefing"
    - "Give me the daily report"
    - "What does today look like?"
    - "Summarize everything for me"
    - "What should I know before my 9am standup?"
    - "Executive summary of shipment delays"
    """
    rows = load_shipments(DB_FILE)

    # ── Step 1: Count every status ──────────────────────────────────────────
    total_orders = len(rows)
    status_counts = {
        "ON_TIME": 0,
        "DELAYED": 0,
        "NEED_ACTION": 0,
        "SHIPPED": 0,
        "CANCELLED": 0,
    }
    reason_counts = {}
    need_action_orders = []

    for row in rows:
        status = assign_delay_status(row, TODAY)
        reason = assign_reason_code(row, TODAY)

        if status in status_counts:
            status_counts[status] += 1

        if status in ["DELAYED", "NEED_ACTION"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if status == "NEED_ACTION":
            need_action_orders.append({
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": reason,
            })

    # ── Step 2: Calculate overall risk level ────────────────────────────────
    risk_level = calculate_risk_level(
        total_orders,
        status_counts["DELAYED"],
        status_counts["NEED_ACTION"],
    )

    # ── Step 3: Find top 3 reason codes by frequency ────────────────────────
    top_reasons = sorted(
        reason_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]

    top_reasons_formatted = [
        {"reason_code": reason, "order_count": count}
        for reason, count in top_reasons
    ]

    # ── Step 4: Find the single most urgent order ────────────────────────────
    most_urgent = None
    most_urgent_recommendation = None

    if need_action_orders:
        need_action_orders.sort(key=lambda x: x["delay_days"], reverse=True)
        most_urgent = need_action_orders[0]

        most_urgent_recommendation = build_recommendation(
            most_urgent["reason_code"],
            most_urgent["delay_status"],
            most_urgent["delay_days"],
        )

    # ── Step 5: Build a plain-English briefing sentence ─────────────────────
    delayed_total = status_counts["DELAYED"] + status_counts["NEED_ACTION"]

    if risk_level == "CRITICAL":
        briefing = (
            f"As of today, {delayed_total} of {total_orders} orders are delayed. "
            f"{status_counts['NEED_ACTION']} require immediate action. "
            f"Risk level is CRITICAL. "
        )
        if most_urgent:
            briefing += (
                f"The most urgent order is {most_urgent['sales_order_no']} "
                f"for {most_urgent['customer_name']}, "
                f"{most_urgent['delay_days']} days overdue "
                f"with reason: {most_urgent['reason_code']}."
            )
    elif risk_level in ["HIGH", "MEDIUM"]:
        briefing = (
            f"As of today, {delayed_total} of {total_orders} orders are delayed. "
            f"Risk level is {risk_level}. No orders have exceeded the 5-day threshold yet, "
            f"but close monitoring is recommended."
        )
    else:
        briefing = (
            f"As of today, all {total_orders} orders are on track. "
            f"Risk level is LOW. No immediate action required."
        )

    # ── Step 6: Return the full summary ─────────────────────────────────────
    # SECURITY FIX: shield_row added as a precaution
    # most_urgent contains customer_name which is raw database text
    # shield_row ensures that field is clean before Claude reads it
    # REPLACES the old direct return statement
    return shield_row({
        "date": str(TODAY),
        "risk_level": risk_level,
        "total_orders": total_orders,
        "status_breakdown": status_counts,
        "top_delay_reasons": top_reasons_formatted,
        "most_urgent_order": most_urgent,
        "most_urgent_recommendation": most_urgent_recommendation,
        "briefing": briefing,
    })


if __name__ == "__main__":
    mcp.run()