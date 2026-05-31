# /weekly
# Supply Chain Control Tower — Weekly Report Command
# ====================================================
#
# WHAT THIS COMMAND DOES:
#   Generates the full weekly performance report combining operational
#   shipment data with CI agent learning and improvement tracking.
#
# TOOLS CALLED (in this order):
#   1. get_weekly_report        — from ci-agent
#      Returns a week-over-week performance summary including:
#        - Total signals detected this week vs last week
#        - Recommendations approved, rejected, deferred
#        - Outcomes logged and whether metrics improved
#        - Learning rule activations this week
#
#   2. get_improvement_summary  — from ci-agent
#      Returns the cumulative improvement picture:
#        - All active recommendations and their status
#        - Patterns the CI agent has learned over time
#        - Confidence scores per pattern type
#        - Which improvements have shown measurable results
#
# WHY TWO TOOLS:
#   get_weekly_report shows what happened THIS week — the short view.
#   get_improvement_summary shows the full learning history — the long view.
#   Together they answer: "How did this week go, and are we getting better?"
#
# WHEN TO USE:
#   Every Friday or Monday for the weekly review.
#   When preparing a report for management.
#   When you want to know if the CI agent's recommendations are working.
#   Any time someone asks "how have we improved this week?"

Run the weekly performance report for the Supply Chain Control Tower.

Step 1: Call get_weekly_report from the ci-agent.
Step 2: Call get_improvement_summary from the ci-agent.
Step 3: Present the combined results using this format:

---
## 📊 Weekly Performance Report — Week of [today's date]

### This Week at a Glance
- Signals detected: [signals_detected_this_week]
- Recommendations generated: [recommendations_generated]
- Approved: [approved_count] | Rejected: [rejected_count] | Deferred: [deferred_count]
- Outcomes logged: [outcomes_logged]
- Metrics improved: [metrics_improved_count]

### Learning Activity
[List any learning rules that fired this week with what they adjusted]
[If no learning rules fired, say "No learning rule adjustments this week."]

### Active Improvements
[For each active recommendation in get_improvement_summary show:]
  - [recommendation_id]: [description]
  - Status: [status] | Priority: [priority_label]
  - Team: [responsible_team]

### Patterns Learned
[For each pattern in the learning report show:]
  - Pattern: [pattern_type]
  - Confidence: [confidence]% | Adjustments made: [adjustment_count]

### Week Summary
[Write a 2-3 sentence plain-English summary of how the week went
based on the numbers above — improving, declining, or stable.]
---
