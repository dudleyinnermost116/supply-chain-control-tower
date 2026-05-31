# /scan
# Supply Chain Control Tower — CI Improvement Scan Command
# =========================================================
#
# WHAT THIS COMMAND DOES:
#   Runs the CI agent's full signal scan across all data, then
#   immediately retrieves the recommendations it generated.
#   This is the standard way to ask: "What should we improve?"
#
# TOOLS CALLED (in this order):
#   1. run_improvement_scan     — from ci-agent
#      Scans all operational data using 8 detectors:
#        REPEATED_DELAY_BY_CARRIER, DOMINANT_ROOT_CAUSE,
#        HIGH_UNKNOWN_RATE, FREIGHT_HOLD_PATTERN,
#        WEAK_CARRIER_OVERUSE, WAREHOUSE_SYSTEMIC_DELAY,
#        REPEATED_STOCKOUT, DATA_QUALITY_GAP
#      Saves detected signals to the database.
#      Returns: list of signals found and how many were saved.
#
#   2. get_pending_recommendations  — from ci-agent
#      Reads recommendations that are waiting for approval.
#      Returns: list of recommendations ranked by priority score,
#               each with responsible team and suggested action.
#
# WHY TWO TOOLS:
#   run_improvement_scan detects patterns and saves them.
#   get_pending_recommendations shows what needs a decision.
#   Running them together gives you the full CI loop in one command:
#   detect → surface → decide.
#
# WHEN TO USE:
#   Weekly review sessions.
#   After a period of high delays to look for systemic patterns.
#   When you want to know what process improvements to prioritise.

Run the CI improvement scan for the Supply Chain Control Tower.

Step 1: Call run_improvement_scan from the ci-agent.
Step 2: Call get_pending_recommendations from the ci-agent.
Step 3: Present the results using this format:

---
## 🔍 CI Improvement Scan — [today's date]

### Scan Results
- Signals detected: [count from run_improvement_scan]
- New signals saved: [saved count]

### Signals Found
[List each signal with: signal type, description, and severity]
[If no signals found, say "No new improvement signals detected."]

### Pending Recommendations
[For each recommendation show:]
  - Priority: [priority label] (score: [priority_score])
  - Type: [recommendation_type]
  - Description: [description]
  - Responsible team: [responsible_team]
  - Suggested action: [suggested_action]
  - Confidence: [confidence]%

[If no pending recommendations, say "No recommendations awaiting approval."]

### Next Step
[If there are pending recommendations, say:]
"Use /approve [recommendation_id] to approve or /reject [recommendation_id] to reject each one."
[If nothing pending, say "Scan complete. No action required."]
---
