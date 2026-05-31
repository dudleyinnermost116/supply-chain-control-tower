# CONTINUOUS IMPROVEMENT AGENT — COMPLETE INSTALLATION GUIDE
# Supply Chain Control Tower — Phase 9
# =======================================================================

## WHAT YOU JUST BUILT

The Continuous Improvement (CI) Agent is a self-learning, always-on
improvement analyst embedded inside your Supply Chain Control Tower.

It works like a full-time analyst who:
  1. Scans all your data every time you run it
  2. Finds patterns, anomalies, and systemic problems
  3. Generates specific, actionable recommendations
  4. Asks you to approve or reject each recommendation
  5. Learns from every decision you make
  6. Gets smarter over time

It does NOT make autonomous changes. You are always in control.


## FILES CREATED — WHERE THEY GO

Copy each file to the exact path shown:

  SOURCE (this delivery)               → DESTINATION (your project)
  ─────────────────────────────────────────────────────────────────
  scripts/setup_ci_database.py         → scripts\setup_ci_database.py
  config/ci_project_config.py          → config\ci_project_config.py
  src/supply_chain/ci_signal_detector.py       → src\supply_chain\ci_signal_detector.py
  src/supply_chain/ci_recommendation_generator.py → src\supply_chain\ci_recommendation_generator.py
  src/supply_chain/ci_learning_engine.py       → src\supply_chain\ci_learning_engine.py
  mcp_server/ci_mcp_server.py          → mcp_server\ci_mcp_server.py
  dashboard/ci_dashboard_tab.py        → dashboard\ci_dashboard_tab.py


## STEP 1 — CREATE THE DATABASE TABLES

Run this ONCE to add the 7 new CI tables to your existing database:

  cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
  $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
  python scripts\setup_ci_database.py

Expected output:
  Connecting to database: ...supply_chain.db
  Creating CI Agent tables...
    ✓ ci_signals
    ✓ ci_recommendations
    ✓ ci_approval_requests
    ✓ ci_action_items
    ✓ ci_outcomes
    ✓ ci_lessons
    ✓ ci_agent_run_log
  ✅ All CI Agent tables created successfully.

If you see this, the database is ready.


## STEP 2 — TEST THE MCP SERVER

Run the CI Agent MCP server directly to check for errors:

  cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
  $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
  python mcp_server\ci_mcp_server.py

Expected: cursor blinks silently (no output = good)
Press Ctrl+C to stop.

If you see an ImportError, check that:
  - PYTHONPATH is set correctly
  - All 3 src files were copied to src\supply_chain\


## STEP 3 — ADD TO CLAUDE DESKTOP

Open your Claude Desktop config file:
  C:\Users\preet\AppData\Roaming\Claude\claude_desktop_config.json

Add the CI agent entry inside the "mcpServers" section:

  "ci-agent": {
    "command": "C:\\Users\\preet\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
    "args": [
      "C:\\Users\\preet\\Documents\\AI Work\\supply_chain_mcp_project\\mcp_server\\ci_mcp_server.py"
    ],
    "env": {
      "PYTHONPATH": "C:\\Users\\preet\\Documents\\AI Work\\supply_chain_mcp_project\\src"
    }
  }

Save the file and restart Claude Desktop completely.

To verify it's connected: open Claude Desktop and type:
  "Run the improvement scan"

Claude should call the run_improvement_scan tool and return results.


## STEP 4 — ADD TO STREAMLIT DASHBOARD

In dashboard\app.py, find where you define your tabs.
Add these two changes:

CHANGE 1 — Add the import at the top of app.py:

  from ci_dashboard_tab import render_ci_tab

CHANGE 2 — Add a new tab wherever you define your tabs:

  # Before (example — your tabs may be named differently):
  tab1, tab2, tab3 = st.tabs(["Command Center", "Domains", "Investigation"])

  # After:
  tab1, tab2, tab3, tab_ci = st.tabs([
      "Command Center", "Domains", "Investigation", "🔄 Improvements"
  ])

  # And add this at the bottom:
  with tab_ci:
      render_ci_tab()

Run the dashboard:
  streamlit run dashboard\app.py --server.port 8502


## HOW TO USE THE CI AGENT IN CLAUDE DESKTOP

Once connected, here are the exact phrases to use:

ACTION                        WHAT TO SAY
──────────────────────────────────────────────────────────────────
Run a scan                   "Run the improvement scan"
See pending recommendations  "Show me the pending recommendations"
Approve a recommendation     "Approve recommendation CI-XXXXXX"
Reject a recommendation      "Reject CI-XXXXXX because [reason]"
Log what happened            "Log the outcome for CI-XXXXXX — it worked.
                              Before: 3 carrier delays. After: 0."
See the summary              "Give me the improvement summary"
See lessons learned          "Show me the lessons learned"
Weekly report                "Give me the weekly CI report"


## THE 7 DATABASE TABLES — WHAT THEY STORE

TABLE                  PURPOSE
──────────────────────────────────────────────────────────────────
ci_signals             Raw observations the agent collects each scan
ci_recommendations     Improvement suggestions with all supporting data
ci_approval_requests   Items waiting for your approve/reject decision
ci_action_items        Concrete work items created after you approve
ci_outcomes            Results after an action was implemented
ci_lessons             The agent's growing memory of what it has learned
ci_agent_run_log       Audit trail of every time the agent ran

You can view all of these in DB Browser for SQLite.
Open: data\supply_chain.db → Browse Data → select any ci_ table.


## THE 8 DETECTION PATTERNS

The agent currently detects these 8 types of problems:

1. REPEATED_DELAY_BY_CARRIER
   Carrier delay reason code appearing across multiple orders

2. DOMINANT_ROOT_CAUSE
   One root cause type in more than 35% of all delays

3. HIGH_UNKNOWN_RATE
   More than 20% of delays classified as UNKNOWN_NEEDS_REVIEW

4. FREIGHT_HOLD_PATTERN
   2 or more simultaneous active freight holds

5. WEAK_CARRIER_OVERUSE
   More than 30% of active shipments using WEAK/CRITICAL carriers

6. WAREHOUSE_SYSTEMIC_DELAY
   2 or more delayed picks in the same warehouse

7. REPEATED_STOCKOUT
   2 or more inventory items at zero or on backorder

8. DATA_QUALITY_GAP
   Missing critical fields across shipment, freight, or warehouse records

To add more detectors, add a new function to ci_signal_detector.py
following the same pattern as the existing ones.


## APPROVAL RULES — WHAT REQUIRES YOUR DECISION

The agent will ALWAYS ask before:
  - Any change to business rules or scoring thresholds
  - Code changes (rules.py, recommendation_engine.py, etc.)
  - Workflow changes (who gets notified, when, how)
  - Carrier routing decisions (affects contracts and costs)
  - Inventory reorder point changes (affects purchasing budget)
  - Any action involving customer communication

The agent can auto-log (no approval needed):
  - Pattern observations with high confidence
  - Data quality gap reports
  - Warehouse delay pattern detection
  - Carrier repeat delay observations


## HOW LEARNING WORKS

The agent learns in 3 ways:

WAY 1 — From rejections:
  When you reject a recommendation with a reason, the agent saves:
  "Recommendation [type X] was rejected because [your reason].
   Avoid similar recommendations without addressing this concern."

WAY 2 — From successful outcomes:
  When you log a "implemented" outcome, the agent saves:
  "Recommendation [type X] was successfully implemented.
   Before: [metric]. After: [metric]."

WAY 3 — From failed outcomes:
  When you log a "failed" outcome, the agent saves:
  "Recommendation [type X] was attempted but did not achieve expected results.
   Future recommendations of this type need closer review."

All lessons are stored in ci_lessons and visible in the dashboard.
Over time, lessons allow the agent to calibrate its confidence scores.


## TUNING THE AGENT

All thresholds are in config\ci_project_config.py.
Change these to match your operation:

  # How many carrier delays before flagging a pattern?
  "carrier_delay_repeat_threshold": 2  ← change to 3 if your data is larger

  # At what % of delays is UNKNOWN rate a problem?
  "unknown_root_cause_pct_threshold": 0.20  ← change to 0.15 to be stricter

  # At what % do we flag weak carrier overuse?
  In detect_weak_carrier_usage(): weak_pct >= 0.30 ← change the 0.30

No other file needs to change. Configuration is centralised.


## ADDING THIS TO A DIFFERENT PROJECT

To reuse this agent on a completely different project:

1. Copy all 7 files to the new project.
2. Edit config\ci_project_config.py:
   - Change project_name, project_domain, business_goals
   - Update teams, data_sources, scoring_weights
3. Edit ci_signal_detector.py:
   - Replace the detector functions with ones that match your data structure
   - Keep the _make_signal() helper — it works for any project
4. Update DB_PATH in ci_signal_detector.py and ci_learning_engine.py.
5. Run setup_ci_database.py in the new project.
6. Add ci_mcp_server.py to Claude Desktop config.

The recommendation templates, approval rules, learning engine,
and dashboard are completely reusable without modification.


## TERMINAL TEST CHECKLIST

After copying all files, run these checks in order:

  □ Step 1: python scripts\setup_ci_database.py
    Expected: "✅ All CI Agent tables created successfully."

  □ Step 2: python mcp_server\ci_mcp_server.py
    Expected: cursor blinks silently, no errors

  □ Step 3: Restart Claude Desktop and ask:
    "Run the improvement scan"
    Expected: Claude calls run_improvement_scan and returns results

  □ Step 4: Ask Claude:
    "Show me the pending recommendations"
    Expected: list of recommendations with IDs like CI-XXXXXX

  □ Step 5: Ask Claude:
    "Reject recommendation CI-XXXXXX because it doesn't apply to our operation"
    Expected: Claude confirms rejection and says a lesson was saved

  □ Step 6: streamlit run dashboard\app.py --server.port 8502
    Go to http://localhost:8502 → "🔄 Improvements" tab
    Expected: KPI cards, scan button, recommendations list

All 6 checks passing = CI Agent fully operational.
