# /warehouse
# Supply Chain Control Tower — Warehouse Operations Command
# ==========================================================
#
# WHAT THIS COMMAND DOES:
#   Gives a complete picture of warehouse pick operations —
#   what is on track, what is delayed, and what is causing problems.
#
# TOOLS CALLED (in this order):
#   1. get_warehouse_summary    — from warehouse-agent
#      Returns high-level pick health counts across all orders:
#        - Total picks: on track, at risk, delayed
#        - List of all DELAYED and AT_RISK picks with root cause
#          (staffing shortage, equipment breakdown, system error, blocked)
#
#   2. get_delayed_picks        — from warehouse-agent
#      Returns only the picks that are overdue — orders that should
#      have been picked but haven't been started or completed.
#      Sorted worst delay first, with specific recommendations per pick.
#
# WHY TWO TOOLS:
#   get_warehouse_summary gives the health overview — how many are ok vs problem.
#   get_delayed_picks gives the actionable detail — exactly which orders
#   need the warehouse supervisor's attention and why.
#   Together they answer: "How is the warehouse performing and what needs fixing?"
#
# WHEN TO USE:
#   Morning warehouse standup.
#   When multiple orders show WAREHOUSE_PICK_DELAY reason code.
#   When you suspect a staffing or equipment issue is causing a backlog.
#   Any time someone asks "what is happening in the warehouse?"

Run the warehouse operations check for the Supply Chain Control Tower.

Step 1: Call get_warehouse_summary from the warehouse-agent.
Step 2: Call get_delayed_picks from the warehouse-agent.
Step 3: Present the combined results using this format:

---
## 🏭 Warehouse Operations Report — [today's date]

### Pick Health Overview
- Total picks: [total_picks]
- ✓ On track: [on_track]
- ⚠️ At risk: [at_risk]
- ✗ Delayed: [delayed]

### Problem Picks
[For each problem pick in get_warehouse_summary show:]
  - [sales_order_no] | Status: [pick_status] | Health: [pick_health]
  - Delay reason: [pick_delay_reason]
  - Staffing issue: [staffing_flag] | Equipment issue: [equipment_issue]

[If no problem picks, say "✓ All picks are on track. No warehouse issues detected."]

### Delayed Picks — Needs Immediate Action
[For each delayed pick in get_delayed_picks show:]
  - [sales_order_no] | Warehouse: [warehouse_name] | Item: [item_no]
  - Overdue by: [pick_delay_days] days | Priority: [pick_priority]
  - Reason: [pick_delay_reason]
  - Action: [recommendation]

[If no delayed picks, say "✓ No delayed picks found."]

### Summary
- Pick completion rate: [on_track count] of [total_picks] on track
[If delayed > 0, say:]
"⚠️ [delayed] pick(s) are overdue. Escalate to warehouse supervisor immediately."
---
