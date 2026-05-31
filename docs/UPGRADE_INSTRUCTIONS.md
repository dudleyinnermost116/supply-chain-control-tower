# UPGRADE INSTRUCTIONS — CI Agent v2
# Adds: Exact spec scoring formula + 8 quantitative learning rules
# =====================================================================

## WHAT CHANGED AND WHY

### Change 1 — Scoring formula replaced
The old formula used a 1–10 scale and did not include urgency.
The new formula exactly matches the spec:

  priority = (impact × 0.35) + (urgency × 0.25) + (confidence×5 × 0.20)
           - (effort × 0.10) - (risk × 0.10)

All inputs are now on a 1–5 scale.
Weights live in ci_project_config.py and are configurable.

Raw score maps to labels:
  0.0–1.9 → low
  2.0–2.9 → medium
  3.0–3.9 → high
  4.0–5.0 → critical

### Change 2 — 8 quantitative learning rules added
The learning engine now tracks per-pattern-type statistics and
automatically adjusts confidence, priority, and impact based on
real outcomes. No manual tuning needed.

  LR-01: 5 consecutive rejections    → confidence -15%
  LR-02: 3 successful implementations → confidence +10%
  LR-03: 20%+ false positive rate    → (tracked, future auto-raise)
  LR-04: Owner repeatedly changed    → (tracked in pattern_stats)
  LR-05: 5+ deferrals                → priority_delta -1
  LR-06: Metric improves 10%+        → impact_delta +1, marks HIGH_VALUE
  LR-07: No improvement after impl   → impact_delta -1
  LR-08: Repeated manual requests    → (tracked for future automation signals)

Two new database tables store all of this:
  ci_learning_rules  — every time a rule fired, what it did
  ci_pattern_stats   — running counters and net adjustments per pattern type

### Change 3 — get_lessons_learned tool upgraded
Now returns quantitative per-pattern stats instead of plain text.
Shows SUPPRESSED / NEUTRAL / HIGH_VALUE status per pattern.


## FILES CHANGED — COMPLETE LIST

  FILE                                    WHAT CHANGED
  ──────────────────────────────────────────────────────────────────────────
  ci_recommendation_generator.py         New 5-input scoring formula
                                          All template scores on 1–5 scale
                                          Urgency added as 5th dimension
                                          Calls learning engine for adjustments

  ci_learning_engine.py                  Completely rebuilt
                                          8 quantitative learning rules
                                          ci_pattern_stats tracking
                                          ci_learning_rules saving
                                          get_pattern_learning_report()

  ci_mcp_server.py                        Updated imports
                                          get_lessons_learned now shows
                                          quantitative pattern stats

  ci_project_config.py                   Scoring weights updated to spec
                                          New risk threshold key added

  scripts/upgrade_ci_database.py         NEW — run once to add:
                                          - urgency_score column
                                          - options/deadline/approver_role
                                            to ci_approval_requests
                                          - ci_learning_rules table
                                          - ci_pattern_stats table


## STEP-BY-STEP INSTALLATION

Follow these steps in exact order.

─────────────────────────────────────────────────────────────────────────────
STEP 1 — Copy the new/updated files into your project
─────────────────────────────────────────────────────────────────────────────

Copy each file to the exact destination path shown:

  FROM (this delivery)                    TO (your project)
  ──────────────────────────────────────────────────────────────────────────
  UPGRADE_INSTRUCTIONS.md                → keep for reference

  scripts/upgrade_ci_database.py         → scripts\upgrade_ci_database.py

  config/ci_project_config.py            → config\ci_project_config.py
                                           REPLACES the previous version

  src/supply_chain/
    ci_recommendation_generator.py      → src\supply_chain\ci_recommendation_generator.py
                                           REPLACES the previous version

    ci_learning_engine.py               → src\supply_chain\ci_learning_engine.py
                                           REPLACES the previous version

  mcp_server/ci_mcp_server.py            → mcp_server\ci_mcp_server.py
                                           REPLACES the previous version

  NOTE: ci_signal_detector.py, ci_dashboard_tab.py, and
        setup_ci_database.py do NOT change. Keep your existing copies.

─────────────────────────────────────────────────────────────────────────────
STEP 2 — Run the database upgrade script
─────────────────────────────────────────────────────────────────────────────

Open a terminal and run:

  cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
  $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
  python scripts\upgrade_ci_database.py

Expected output:
  Connecting to: ...supply_chain.db
  Applying upgrades...
    ✓ Added urgency_score to ci_recommendations
    ✓ Added options_json to ci_approval_requests
    ✓ Added recommended_option to ci_approval_requests
    ✓ Added deadline to ci_approval_requests
    ✓ Added approver_role to ci_approval_requests
    ✓ Created ci_learning_rules table
    ✓ Created ci_pattern_stats table
  ✅ Database upgrade complete.

If any line says "~ ... already exists, skipping" that is fine.
It means you already had that column — safe to continue.

─────────────────────────────────────────────────────────────────────────────
STEP 3 — Test the MCP server starts cleanly
─────────────────────────────────────────────────────────────────────────────

  cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
  $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
  python mcp_server\ci_mcp_server.py

Expected: cursor blinks silently, no errors printed.
Press Ctrl+C to stop.

If you see an ImportError, the most common causes are:
  - PYTHONPATH is not set (run the $env:PYTHONPATH line first)
  - A file was copied to the wrong path
  - The old ci_learning_engine.py is still in place (check the replace)

─────────────────────────────────────────────────────────────────────────────
STEP 4 — Restart Claude Desktop
─────────────────────────────────────────────────────────────────────────────

Close Claude Desktop completely and reopen it.
This forces it to pick up the updated ci_mcp_server.py.

You do NOT need to change claude_desktop_config.json.
The ci-agent entry you added in Phase 9 setup still works.

─────────────────────────────────────────────────────────────────────────────
STEP 5 — Verify everything works end-to-end
─────────────────────────────────────────────────────────────────────────────

In Claude Desktop, run these 4 tests in order:

TEST 1 — Run a scan:
  "Run the improvement scan"
  Expected: recommendations with priority labels like "high" or "critical"
  and a priority_score between 0 and 100.

TEST 2 — Check scores use the new formula:
  "Show me the pending recommendations"
  Look at any recommendation. You should now see:
  - impact_score: a number 1–5 (not 1–10 or 1–7)
  - urgency_score: a number 1–5
  - effort_score: a number 1–5
  - risk_score: a number 1–5
  - confidence: a decimal like 0.8

TEST 3 — Reject a recommendation and check learning fires:
  "Reject recommendation CI-XXXXXX because it doesn't apply right now"
  Expected response will now include:
    "learning_rules_fired: []" (no rule yet — need 5 rejections to fire LR-01)
  Reject the same pattern type 5 times total, then ask:
  "Show me the lessons learned"
  Expected: the pattern shows confidence_adjustment: -15%

TEST 4 — Log a successful outcome and check LR-06:
  Approve a recommendation first, then log:
  "Log the outcome for CI-XXXXXX — it worked.
   The metric went from 5 carrier delays to 1."
  Expected: LR-06 fires because improvement > 10%.
  Confirm: "Show me the lessons learned" → pattern shows impact_adjustment: +1


## UNDERSTANDING THE NEW SCORING — WORKED EXAMPLE

Take a FREIGHT_HOLD_PATTERN recommendation:
  impact     = 5   (critical — physically blocks deliveries)
  urgency    = 5   (very urgent — holds escalate fast)
  effort     = 3   (investigation + coordination)
  risk       = 3   (may involve compliance/legal)
  confidence = 0.9 (CRITICAL severity signal)

Formula:
  = (5 × 0.35) + (5 × 0.25) + (0.9×5 × 0.20) - (3 × 0.10) - (3 × 0.10)
  = 1.75       + 1.25       + 0.90             - 0.30       - 0.30
  = 3.30  → "high"

Now suppose this pattern was rejected 5 times (LR-01 fires):
  confidence_delta = -0.15
  adjusted confidence = 0.9 - 0.15 = 0.75

  = (5 × 0.35) + (5 × 0.25) + (0.75×5 × 0.20) - (3 × 0.10) - (3 × 0.10)
  = 1.75       + 1.25       + 0.75             - 0.30       - 0.30
  = 3.15  → still "high", but lower score

Now suppose it was then successfully implemented 3 times with 10%+ improvement
(LR-02 fires: confidence +10%, LR-06 fires: impact +1):
  adjusted confidence = 0.75 + 0.10 = 0.85
  adjusted impact     = 5 + 1 = capped at 5

  = (5 × 0.35) + (5 × 0.25) + (0.85×5 × 0.20) - (3 × 0.10) - (3 × 0.10)
  = 1.75       + 1.25       + 0.85             - 0.30       - 0.30
  = 3.25  → "high", slightly higher than the rejected version

This is the agent self-correcting based on real outcomes.


## TERMINAL TEST CHECKLIST

  □ python scripts\upgrade_ci_database.py
    → "✅ Database upgrade complete."

  □ python mcp_server\ci_mcp_server.py
    → silent cursor, no errors

  □ Claude Desktop: "Run the improvement scan"
    → recommendations with 1–5 scores and priority label

  □ Claude Desktop: "Show me the pending recommendations"
    → each rec shows urgency_score field

  □ Claude Desktop: "Show me the lessons learned"
    → returns per-pattern stats (empty until decisions are made)

All 5 checks passing = upgrade complete and fully operational.


## TROUBLESHOOTING

Problem: "table ci_learning_rules has no column named X"
Fix: Re-run upgrade_ci_database.py — it adds missing columns safely.

Problem: "AttributeError: module 'supply_chain.ci_learning_engine' has no attribute 'get_relevant_lessons'"
Fix: The old ci_learning_engine.py is still in place. Replace it with the new one.

Problem: Scores look very low (all "low" priority)
Fix: Check that ci_project_config.py was replaced. The old weights summed
     to 1.0 but were for a 1–10 scale. New weights are for 1–5 scale.

Problem: "No module named 'supply_chain.ci_learning_engine'"
Fix: PYTHONPATH is not set. Run:
     $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
