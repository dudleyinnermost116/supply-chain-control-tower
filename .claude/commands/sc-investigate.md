# /investigate
# Supply Chain Control Tower — Order Investigation Command
# =========================================================
#
# WHAT THIS COMMAND DOES:
#   Takes a sales order number from you, then runs the full
#   cross-agent root cause investigation for that order.
#   This is the deepest single-order analysis in the system.
#
# TOOLS CALLED (in this order):
#   1. investigate_order(sales_order_no)  — from investigation-agent
#      Loads data from all four domains simultaneously:
#        - Shipping: delay status and reason code
#        - Inventory: stock level for the item on this order
#        - Freight: carrier pickup status and hold flags
#        - Warehouse: pick status and operational issues
#      Returns: severity, confirmed root cause, contributing factors,
#               and the single most important first action to take.
#
#   2. get_recommendation_for_order(sales_order_no) — from recommendation-agent
#      Takes the investigation findings and adds:
#        - Priority score (0-100)
#        - Responsible team assignment
#        - Escalation flag and reason
#
# WHY TWO TOOLS:
#   investigate_order tells you WHY the order is delayed.
#   get_recommendation_for_order tells you WHAT TO DO about it.
#   Together they answer both questions in one command.
#
# WHEN TO USE:
#   When a customer calls asking about their order.
#   When you need to escalate a specific order to a manager.
#   When the briefing shows a critical order and you want full detail.
#   Any time you type an order number and want the complete picture.

Run a full investigation for a specific sales order.

Step 1: If the user typed "/investigate" with no order number, ask:
        "Which order would you like to investigate? Please provide the sales order number (e.g. SO-1003)."
        Then wait for their response before proceeding.

        If the user typed "/investigate SO-XXXX" with an order number already provided,
        skip the question and proceed directly to Step 2.

Step 2: Call investigate_order([sales_order_no]) from the investigation-agent.
Step 3: Call get_recommendation_for_order([sales_order_no]) from the recommendation-agent.
Step 4: Present the combined results using this format:

---
## 🔎 Investigation Report — [sales_order_no]

### Order Details
- Customer: [customer_name]
- Scheduled pick date: [scheduled_pick_date]
- Days overdue: [delay_days]
- Delay status: [delay_status]

### Severity & Root Cause
- Severity: [severity]
- Root cause: [root_cause]
- First action: [first_action]

### Contributing Factors
[List each contributing factor on its own line]

### Agent Signals
- Shipping reason: [shipping_reason]
- Inventory status: [inventory_status]
- Freight status: [freight_status]
- Freight hold active: [freight_hold_active]
- Pick health: [pick_health]
- Carrier: [carrier_name] ([carrier_tier])

### Action Plan
- Priority score: [priority_score] / 100
- Responsible team: [responsible_team]
- Recommended action: [recommended_action]

### Escalation
[If escalate is true:]
⚠️ ESCALATION REQUIRED: [escalation_reason]
[If escalate is false:]
✓ No escalation required at this time.
---
