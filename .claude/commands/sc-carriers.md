# /carriers
# Supply Chain Control Tower — Carrier Performance Command
# =========================================================
#
# WHAT THIS COMMAND DOES:
#   Pulls a complete carrier health check — who is performing well,
#   who has missed pickups, and which carriers are causing problems.
#
# TOOLS CALLED (in this order):
#   1. get_carrier_performance_summary  — from freight-agent
#      Aggregates all freight records by carrier and returns:
#        - Total shipments per carrier
#        - How many are on hold, missed, delayed, or delivered
#        - Performance score and tier (STRONG/AVERAGE/WEAK/CRITICAL)
#      Sorted worst performers first so problems are visible immediately.
#
#   2. get_missed_pickups               — from freight-agent
#      Returns all orders where the carrier missed the scheduled pickup
#      and has not yet collected the shipment.
#      Sorted by days overdue, worst first.
#
# WHY TWO TOOLS:
#   get_carrier_performance_summary gives the big picture per carrier.
#   get_missed_pickups shows the specific orders sitting in the warehouse
#   right now waiting for a carrier that hasn't shown up.
#   Together they answer: "Which carriers are reliable and what is stuck?"
#
# WHEN TO USE:
#   Weekly carrier review meetings.
#   When multiple shipments are delayed due to carrier issues.
#   When deciding whether to continue using a specific carrier.
#   Any time someone asks "how are our carriers performing?"

Run the carrier performance check for the Supply Chain Control Tower.

Step 1: Call get_carrier_performance_summary from the freight-agent.
Step 2: Call get_missed_pickups from the freight-agent.
Step 3: Present the combined results using this format:

---
## 🚛 Carrier Performance Report — [today's date]

### Carrier Scoreboard
[For each carrier in get_carrier_performance_summary show:]
  - [carrier_name] | Tier: [carrier_tier] | Score: [performance_score]
  - Total shipments: [total_shipments]
  - Delivered: [delivered] | In transit: [in_transit]
  - On hold: [on_hold] | Missed pickups: [pickup_missed] | Delayed: [carrier_delayed]

### Missed Pickups — Carriers Who Did Not Show Up
[For each missed pickup show:]
  - [sales_order_no] | Carrier: [carrier_name] ([carrier_tier])
  - Scheduled: [pickup_scheduled_date] | Overdue by: [pickup_delay_days] days
  - Action: [recommendation]

[If no missed pickups, say "✓ No missed pickups. All carriers have collected their shipments."]

### Summary
- Total carriers tracked: [count]
- STRONG performers: [count] | AVERAGE: [count] | WEAK: [count] | CRITICAL: [count]
- Total missed pickups: [count]
[If any WEAK or CRITICAL carriers exist, say:]
"⚠️ Consider reviewing contracts with WEAK/CRITICAL rated carriers."
---
