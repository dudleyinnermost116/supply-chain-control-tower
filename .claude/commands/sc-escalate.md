# /escalate
# Supply Chain Control Tower — Escalation Command
# =================================================
#
# WHAT THIS COMMAND DOES:
#   Pulls every order that needs immediate manager attention right now.
#   Combines two tools to show both the scored escalation list and
#   the raw list of severely overdue shipments.
#
# TOOLS CALLED (in this order):
#   1. get_escalation_list      — from recommendation-agent
#      Returns orders that meet ANY of these escalation triggers:
#        - Priority score >= 70
#        - Delay status is NEED_ACTION (more than 5 days overdue)
#        - Active freight hold physically blocking the shipment
#      Each result includes the specific reason why it was escalated.
#      Sorted highest priority first.
#
#   2. get_need_action_shipments — from shipping-delay-agent
#      Returns only shipments in NEED_ACTION status — more than 5 days
#      overdue and not yet shipped. Sorted worst delay first.
#
# WHY TWO TOOLS:
#   get_escalation_list uses the full scoring engine — it catches freight
#   holds and high-scoring orders even if they are only 2 days late.
#   get_need_action_shipments catches purely time-based escalations.
#   Together they ensure nothing slips through either filter.
#
# WHEN TO USE:
#   First thing in the morning to know what cannot wait.
#   Before a manager meeting to know what to flag.
#   When the briefing shows CRITICAL risk level.
#   Any time someone asks "what needs attention right now?"

Run the escalation check for the Supply Chain Control Tower.

Step 1: Call get_escalation_list from the recommendation-agent.
Step 2: Call get_need_action_shipments from the shipping-delay-agent.
Step 3: Present the combined results using this format:

---
## ⚠️ Escalation Report — [today's date]

### Orders Requiring Manager Escalation
[For each order in get_escalation_list show:]
  - [sales_order_no] | [customer_name] | [delay_days] days overdue
  - Priority score: [priority_score]/100 | Team: [responsible_team]
  - Reason for escalation: [escalation_reason]
  - Action: [recommended_action]

[If no escalations, say "✓ No orders require escalation at this time."]

### Severely Overdue Shipments (5+ days)
[For each order in get_need_action_shipments show:]
  - [sales_order_no] | [customer_name] | [delay_days] days overdue
  - Reason: [reason_code]

[If no need-action shipments, say "✓ No shipments are severely overdue."]

### Summary
- Orders escalated: [count from get_escalation_list]
- Orders 5+ days overdue: [count from get_need_action_shipments]
[If both counts are 0, say "✓ All orders are within acceptable delay thresholds."]
---
