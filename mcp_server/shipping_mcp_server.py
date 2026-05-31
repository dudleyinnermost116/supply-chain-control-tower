from datetime import date
from supply_chain.recommendations import build_recommendation
from mcp.server.fastmcp import FastMCP
from supply_chain.recommendations import build_recommendation, calculate_risk_level
## Old command to import data from CSV - from supply_chain.data_loader import load_shipments
from supply_chain.db_loader import load_shipments_db as load_shipments
from supply_chain.rules import (
    calculate_delay_days,
    assign_delay_status,
    assign_reason_code,
)


mcp = FastMCP("shipping-delay-agent")

# old command to import from csv folder 
#DATA_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\shipments_sample.csv"
# Below is the new one added to import from sqllite db
##DB_FILE = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"
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

# Always use today's real date — never hardcode this
TODAY = date.today()


# ─── EXISTING TOOL 1 ────────────────────────────────────────────────────────

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return results


# ─── EXISTING TOOL 2 ────────────────────────────────────────────────────────

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return {
        "total_orders": total_orders,
        "on_time": on_time_count,
        "delayed_shipments": delayed_count,
        "need_action_shipments": need_action_count,
        "shipped": shipped_count,
        "cancelled": cancelled_count,
        "reason_counts": reason_counts,
    }


# ─── EXISTING TOOL 3 ────────────────────────────────────────────────────────

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
    rows = load_shipments(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_delay_status(row, TODAY)

            return {
                "sales_order_no": row.get("sales_order_no", ""),
                "customer_name": row.get("customer_name", ""),
                "scheduled_pick_date": row.get("scheduled_pick_date", ""),
                "ship_confirm_date": row.get("ship_confirm_date", ""),
                "order_status": row.get("order_status", ""),
                "delay_days": calculate_delay_days(row, TODAY),
                "delay_status": status,
                "reason_code": assign_reason_code(row, TODAY),
            }

    return {"error": f"Sales order {sales_order_no} was not found."}


# ─── NEW TOOL 4 ─────────────────────────────────────────────────────────────
# Only returns NEED_ACTION orders (more than 5 days delayed).
# Sorted by delay_days descending so the worst offenders appear first.

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return results


# ─── NEW TOOL 5 ─────────────────────────────────────────────────────────────
# Filters all shipments by a specific reason code.
# Useful for investigating one root cause across all orders.

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return results


# ─── NEW TOOL 6 ─────────────────────────────────────────────────────────────
# Filters all shipments by customer name (partial match, case-insensitive).
# This lets users ask about a customer without knowing the exact name format.

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return results


# ─── NEW TOOL 7 ─────────────────────────────────────────────────────────────
# Filters all shipments by a specific delay status.
# Covers all 5 statuses: ON_TIME, DELAYED, NEED_ACTION, SHIPPED, CANCELLED

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

    return results

# ─── NEW TOOL 8 ─────────────────────────────────────────────────────────────
# The first tool that recommends action, not just reports data.
# Combines order lookup + delay rules + recommendation logic.

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
    rows = load_shipments(DB_FILE)

    for row in rows:
        if row.get("sales_order_no", "") == sales_order_no:
            status = assign_delay_status(row, TODAY)
            delay_days = calculate_delay_days(row, TODAY)
            reason = assign_reason_code(row, TODAY)

            # Build the recommendation using our rules engine
            recommendation = build_recommendation(reason, status, delay_days)

            # Return order facts + recommendation together
            return {
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
            }

    return {"error": f"Sales order {sales_order_no} was not found."}

    # ─── NEW TOOL 9 ─────────────────────────────────────────────────────────────
# Executive-level daily briefing tool.
# Combines everything into one structured summary a manager can act on.

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
    ## This is commented to migrate from SQL to DB 
    #rows = load_shipments(DATA_FILE)
    #new change is below to get the file from Database
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

        # Count statuses
        if status in status_counts:
            status_counts[status] += 1

        # Count reason codes (only for delayed orders — not shipped/cancelled)
        if status in ["DELAYED", "NEED_ACTION"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        # Collect NEED_ACTION orders for finding the most urgent one
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
        # Sort by delay days descending — worst first
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
    return {
        "date": str(TODAY),
        "risk_level": risk_level,
        "total_orders": total_orders,
        "status_breakdown": status_counts,
        "top_delay_reasons": top_reasons_formatted,
        "most_urgent_order": most_urgent,
        "most_urgent_recommendation": most_urgent_recommendation,
        "briefing": briefing,
    }
if __name__ == "__main__":
    mcp.run()