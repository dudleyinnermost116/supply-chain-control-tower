# mcp_server/memory_mcp_server.py
#
# PURPOSE:
#   This MCP server gives Claude the ability to read and write the
#   project memory file (memory\project_memory.json).
#
#   Without this server, Claude has no way to access files on your
#   hard drive — it can only see what you paste into the chat.
#   With this server running, Claude can call these tools just like
#   it calls get_delayed_shipments() or get_inventory_summary().
#
# TOOLS IN THIS SERVER:
#   read_project_memory   — reads the full memory file at session start
#   update_project_memory — writes decisions, notes, summaries at session end
#   get_memory_status     — returns a plain-English summary paragraph
#
# HOW IT FITS INTO THE PROJECT:
#   This is the 9th MCP server. It follows the exact same FastMCP
#   pattern as all 8 existing servers. It does not touch any data
#   files (no CSV, no SQLite) — it only reads and writes memory JSON.
#
# TO RUN STANDALONE (for testing):
#   cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
#   python mcp_server\memory_mcp_server.py

import sys
import os

# ─── PATH SETUP ──────────────────────────────────────────────────────────────
# WHY THIS IS NEEDED:
#   Claude Desktop launches MCP servers from an unpredictable working directory.
#   Without this block, Python cannot find our memory_manager module.
#
# WHAT EACH LINE DOES:
#   __file__                    → full path to THIS file (memory_mcp_server.py)
#   os.path.abspath(__file__)   → converts to absolute path (no relative dots)
#   os.path.dirname(...)        → gives the folder containing this file (mcp_server\)
#   os.path.dirname(...again)   → goes up one level to the project root
#   sys.path.insert(0, ...)     → adds the project root to Python's search path
#                                 so "from memory.memory_manager import ..." works

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ─── IMPORTS ─────────────────────────────────────────────────────────────────
# FastMCP is the framework that turns Python functions into MCP tools.
# memory_manager is our own module — the safe interface to the JSON file.

from mcp.server.fastmcp import FastMCP
from memory.memory_manager import (
    load_memory,
    save_memory,
    add_decision,
    add_session_summary,
    add_note,
    add_escalation,
    clear_escalation,
    update_last_scan,
    update_last_briefing,
    update_phase_status,
    update_agent_health,
    get_status_summary,
)

# ─── CREATE THE MCP SERVER ────────────────────────────────────────────────────
# "memory-agent" is the name Claude Desktop will show for this server.
# It must be unique — no other server should use this name.

mcp = FastMCP("memory-agent")


# ─── TOOL 1: READ PROJECT MEMORY ─────────────────────────────────────────────

@mcp.tool()
def read_project_memory() -> dict:
    """
    Use this tool at the START of every session to load the project memory
    and understand the current state of the Supply Chain Control Tower.

    Returns the full memory including:
    - Phase completion status for all 10 phases
    - Last CI scan result (date, signals, recommendations, top pattern)
    - Last briefing result (date, risk level, order counts)
    - Active escalations (orders that still need manager attention)
    - Key decisions made in previous sessions
    - Session summaries from previous conversations
    - Agent health status
    - Standing notes

    Use this when the session starts, or when the user asks:
    - "What do you know about this project?"
    - "Read my project memory"
    - "What is the current project state?"
    - "What phase are we on?"
    - "What did we decide last time?"
    """
    memory = load_memory()

    # If memory is empty (file missing or corrupted), return a helpful message
    # instead of an empty dict that would confuse Claude
    if not memory:
        return {
            "error": "Memory file could not be loaded.",
            "suggestion": (
                "Check that memory\\project_memory.json exists in the project root. "
                "Run: python memory\\memory_manager.py to verify the file."
            )
        }

    return memory


# ─── TOOL 2: GET MEMORY STATUS ────────────────────────────────────────────────

@mcp.tool()
def get_memory_status() -> str:
    """
    Use this tool when you want a quick plain-English summary of the
    project state — without returning the full raw JSON.

    Returns a readable paragraph covering:
    - Current phase and what is in progress
    - Last CI scan and briefing results
    - Active escalations
    - Most recent decision and session summary

    Use this when the user asks:
    - "Give me a quick project status"
    - "What is the current state of the project?"
    - "Summarise what you know"
    - "Quick memory check"
    """
    return get_status_summary()


# ─── TOOL 3: UPDATE PROJECT MEMORY ───────────────────────────────────────────

@mcp.tool()
def update_project_memory(
    update_type: str,
    content: str,
    extra: str = ""
) -> dict:
    """
    Use this tool to write information to the project memory file.
    Call this at the END of a session, or whenever something important
    needs to be remembered for future sessions.

    Input parameters:
      update_type — what kind of update this is. Must be one of:
          decision         — a key technical or project decision was made
          session_summary  — a summary of what happened in this session
          note             — a freeform note to remember for the future
          escalation_add   — an order was escalated (use content=order_no, extra=reason)
          escalation_clear — an escalation was resolved (use content=order_no)
          phase_complete   — a phase or step was completed (use content=phase_key)
          scan_result      — CI scan was run (use content=summary, extra=signals,recs,pattern)
          briefing_result  — briefing was run (use content=summary, extra=risk,total,delayed,action,cause)
          agent_status     — agent health changed (use content=agent_name, extra=HEALTHY/ERROR)

      content — the main text for this update (see update_type notes above)
      extra   — optional additional data (see update_type notes above)

    Use this when:
    - Session is ending: "Save a session summary"
    - A decision was made: "Remember that we decided to use SQLite for memory"
    - An order needs escalation: "Add SO10003 to escalations"
    - A phase was completed: "Mark phase_10_step_4_memory as complete"
    """

    # Route to the correct memory_manager function based on update_type
    # This is a dispatcher pattern — one tool handles many update types
    # so Claude only needs to know one tool name

    update_type_normalized = update_type.strip().lower()

    # ── Decision ─────────────────────────────────────────────────────────────
    if update_type_normalized == "decision":
        success = add_decision(content)
        return {
            "status": "saved" if success else "failed",
            "update_type": "decision",
            "content": content,
        }

    # ── Session summary ───────────────────────────────────────────────────────
    elif update_type_normalized == "session_summary":
        success = add_session_summary(content)
        return {
            "status": "saved" if success else "failed",
            "update_type": "session_summary",
            "content": content,
        }

    # ── Freeform note ─────────────────────────────────────────────────────────
    elif update_type_normalized == "note":
        success = add_note(content)
        return {
            "status": "saved" if success else "failed",
            "update_type": "note",
            "content": content,
        }

    # ── Add escalation ────────────────────────────────────────────────────────
    elif update_type_normalized == "escalation_add":
        # content = order number, extra = reason
        reason = extra if extra else "No reason provided"
        success = add_escalation(content, reason)
        return {
            "status": "saved" if success else "failed",
            "update_type": "escalation_add",
            "order": content,
            "reason": reason,
        }

    # ── Clear escalation ──────────────────────────────────────────────────────
    elif update_type_normalized == "escalation_clear":
        success = clear_escalation(content)
        return {
            "status": "cleared" if success else "failed",
            "update_type": "escalation_clear",
            "order": content,
        }

    # ── Phase complete ────────────────────────────────────────────────────────
    elif update_type_normalized == "phase_complete":
        success = update_phase_status(content, "COMPLETE")
        return {
            "status": "saved" if success else "failed",
            "update_type": "phase_complete",
            "phase_key": content,
        }

    # ── Agent status ──────────────────────────────────────────────────────────
    elif update_type_normalized == "agent_status":
        # content = agent name, extra = HEALTHY / ERROR / UNKNOWN
        status = extra if extra else "UNKNOWN"
        success = update_agent_health(content, status)
        return {
            "status": "saved" if success else "failed",
            "update_type": "agent_status",
            "agent": content,
            "health": status,
        }

    # ── Scan result ───────────────────────────────────────────────────────────
    elif update_type_normalized == "scan_result":
        # extra format: "signals,recommendations,top_pattern"
        # e.g. extra = "3,2,REPEATED_DELAY_BY_CARRIER"
        try:
            parts = extra.split(",") if extra else []
            signals = int(parts[0]) if len(parts) > 0 else 0
            recs = int(parts[1]) if len(parts) > 1 else 0
            pattern = parts[2].strip() if len(parts) > 2 else ""
            success = update_last_scan(signals, recs, pattern, content)
        except Exception:
            success = update_last_scan(0, 0, "", content)

        return {
            "status": "saved" if success else "failed",
            "update_type": "scan_result",
        }

    # ── Briefing result ───────────────────────────────────────────────────────
    elif update_type_normalized == "briefing_result":
        # extra format: "risk_level,total,delayed,need_action,top_cause"
        # e.g. extra = "HIGH,10,3,1,FREIGHT_HOLD"
        try:
            parts = extra.split(",") if extra else []
            risk = parts[0].strip() if len(parts) > 0 else "UNKNOWN"
            total = int(parts[1]) if len(parts) > 1 else 0
            delayed = int(parts[2]) if len(parts) > 2 else 0
            need_action = int(parts[3]) if len(parts) > 3 else 0
            top_cause = parts[4].strip() if len(parts) > 4 else ""
            success = update_last_briefing(risk, total, delayed, need_action, top_cause, content)
        except Exception:
            success = update_last_briefing("UNKNOWN", 0, 0, 0, "", content)

        return {
            "status": "saved" if success else "failed",
            "update_type": "briefing_result",
        }

    # ── Unknown update type ───────────────────────────────────────────────────
    else:
        return {
            "status": "error",
            "message": (
                f"Unknown update_type: '{update_type}'. "
                "Valid options: decision, session_summary, note, escalation_add, "
                "escalation_clear, phase_complete, agent_status, scan_result, briefing_result"
            )
        }


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
# This line starts the MCP server when Claude Desktop launches it.
# "if __name__ == '__main__'" means this only runs when the file is
# executed directly — not when it is imported by another file.

if __name__ == "__main__":
    mcp.run()