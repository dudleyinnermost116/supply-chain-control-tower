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
