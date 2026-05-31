# CLAUDE.MD
# Supply Chain Control Tower — Project Instructions
# ================================================================
# This file is read automatically by Claude at the start of every
# conversation. It gives Claude full context about this project
# without you needing to repeat it each time.
#
# WHERE TO PLACE THIS FILE:
#   Option A (Claude Code / local): project root folder
#     C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\CLAUDE.md
#
#   Option B (Claude Desktop Projects): paste content into the
#     Project Instructions field when creating a Claude Project.
# ================================================================

## Project Identity

**Name:** Supply Chain Control Tower
**Owner:** Vishal
**Type:** Multi-agent AI system for supply chain intelligence
**Status:** Production — Phase 10 complete. Current version: v2.0
**Location:** C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\

## Communication Rules

- I am a beginner coder. Always explain every line of code.
- Never assume I know what a function, pattern, or concept does.
- Always explain WHY a design decision was made, not just what it does.
- One step at a time. Never redesign everything at once.
- Always end responses with a terminal test checklist.
- Build on what exists. Never break working tools.
- Every new file gets a comment header explaining its purpose.

## Tech Stack

- Python 3.10 on Windows
- SQLite database: data\supply_chain.db
- MCP SDK: FastMCP (mcp Python package)
- LLM Client: Claude Desktop
- Dashboard: Streamlit + Plotly
- PYTHONPATH: src\ folder must always be set

## Agent Map — 8 MCP Servers, 46 Tools

| Agent | File | Tools | Domain |
|---|---|---|---|
| shipping-delay-agent | shipping_mcp_server.py | 9 | Outbound delay tracking |
| inventory-agent | inventory_mcp_server.py | 6 | Stock levels |
| po-agent | po_mcp_server.py | 5 | Purchase orders |
| freight-agent | freight_mcp_server.py | 5 | Carrier and pickup |
| warehouse-agent | warehouse_mcp_server.py | 5 | Pick operations |
| investigation-agent | investigation_mcp_server.py | 4 | Root cause analysis |
| recommendation-agent | recommendation_mcp_server.py | 4 | Action prioritisation |
| ci-agent | ci_mcp_server.py | 8 | Continuous improvement |

## Slash Command Shortcuts

/scan          → run_improvement_scan then get_pending_recommendations
/briefing      → get_management_summary + get_daily_risk_report
/investigate   → ask for order number then call investigate_order
/escalate      → get_escalation_list + get_need_action_shipments
/weekly        → get_weekly_report + get_improvement_summary
/carriers      → get_carrier_performance_summary + get_missed_pickups
/warehouse     → get_warehouse_summary + get_delayed_picks
/inventory     → get_inventory_summary + get_backordered_items

## Key Business Rules

Delay status thresholds:
  ON_TIME     = scheduled date is today or future
  DELAYED     = 1–5 days overdue, not shipped
  NEED_ACTION = 5+ days overdue, not shipped (escalate immediately)
  SHIPPED     = ship-confirmed
  CANCELLED   = cancelled

Priority scoring formula:
  score = (impact×0.35) + (urgency×0.25) + (confidence×5×0.20)
        - (effort×0.10) - (risk×0.10)
  All inputs 1–5 scale. Maps to: low / medium / high / critical

CI Agent learning rules:
  LR-01: 5 consecutive rejections → confidence -15%
  LR-02: 3 approvals + outcome    → confidence +10%
  LR-05: 5+ deferrals             → priority_delta -1
  LR-06: Metric improves 10%+     → impact_delta +1
  LR-07: No improvement           → impact_delta -1

## Database Tables

Operational: shipments, inventory, purchase_orders, freight, warehouse_picks
CI Agent:    ci_signals, ci_recommendations, ci_approval_requests,
             ci_action_items, ci_outcomes, ci_learning_rules, ci_pattern_stats

## Important Rules for Claude

1. Never hardcode supply-chain logic into generic engine files.
2. All project settings live in config\ci_project_config.py.
3. The src\ folder must be in PYTHONPATH for imports to work.
4. Never modify data\supply_chain.db directly — use DB Browser for SQLite.
5. Every MCP server file ends with: if __name__ == "__main__": mcp.run()
6. All ID formats: CI-XXXXXX, ACT-XXXXXX, SIG-XXXXXX, LR-XXXXXX

## Current Phase

Phase 10 — Enterprise Standardization ✅ COMPLETE
Added: CLAUDE.MD ✓, Settings ✓, Slash Commands ✓, Memory System ✓, 
Hooks ✓, GitHub deployment ✓, Security (input validation + prompt injection shield) ✓
Current version: v2.0 — released on GitHub

        ## Memory System — How Claude Uses It

At the start of every session, Claude should:
1. Read memory\project_memory.json
2. Run get_status_summary() from memory\memory_manager.py
3. Use the summary to understand current project state without Vishal
   needing to repeat it

At the end of every session (when Vishal says "wrap up" or "end session"),
Claude should:
1. Call add_session_summary() with a 2-3 sentence description of what
   was built, decided, or fixed in this session
2. Call add_decision() for any key technical decisions made
3. Call update_phase_status() if a phase or step was completed

If /sc-briefing is run, also call:
  update_last_briefing(risk_level, total_orders, delayed, need_action, top_cause, summary)

If /sc-scan is run, also call:
  update_last_scan(signals, recommendations, top_pattern, summary)

If escalated orders are found, also call:
  add_escalation(sales_order_no, reason)

Memory file location: memory\project_memory.json
Memory manager location: memory\memory_manager.py
