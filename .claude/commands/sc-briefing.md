# /briefing
# Supply Chain Control Tower — Morning Briefing Command
# ======================================================
#
# WHAT THIS COMMAND DOES:
#   Runs two tools back to back and presents their results together
#   as a single structured morning briefing.
#
# TOOLS CALLED (in this order):
#   1. get_management_summary   — from shipping-delay-agent
#      Returns: risk level, total orders, delay counts, top reason codes,
#               most urgent order, and a plain-English briefing sentence.
#
#   2. get_daily_risk_report    — from investigation-agent
#      Returns: cross-agent health snapshot covering shipments, inventory,
#               freight, warehouse, and multi-domain risk orders.
#
# WHY TWO TOOLS:
#   get_management_summary focuses on shipment delays only.
#   get_daily_risk_report looks across all four domains simultaneously.
#   Together they give a complete picture — one for the delay situation,
#   one for the full supply chain health.
#
# WHEN TO USE:
#   Every morning before your standup.
#   Any time you need a quick full-system status check.
#   When someone asks "what does today look like?"

Run the morning briefing for the Supply Chain Control Tower.

Step 1: Call get_management_summary from the shipping-delay-agent.
Step 2: Call get_daily_risk_report from the investigation-agent.
Step 3: Present the results together as a single briefing using this format:

---
## 🏭 Supply Chain Morning Briefing — [today's date]

### Overall Risk Level: [risk_level from get_management_summary]

### Shipment Summary
- Total orders: [total_orders]
- On time: [on_time count]
- Delayed: [delayed count]
- Need action: [need_action count]
- Shipped: [shipped count]

### Top Delay Reasons
[list the top_delay_reasons from get_management_summary]

### Most Urgent Order
[If there is a most_urgent_order, show order number, customer, delay days, and recommended action]
[If there is no urgent order, say "No orders require immediate escalation today."]

### Cross-Domain Health
- Inventory problems: [critical + out_of_stock + on_backorder count from get_daily_risk_report]
- Freight problems: [on_hold + pickup_missed count]
- Warehouse problems: [delayed + at_risk pick count]
- Multi-domain risk orders: [multi_domain_risk_orders count]

### Briefing Summary
[Print the briefing text from get_daily_risk_report]
---
