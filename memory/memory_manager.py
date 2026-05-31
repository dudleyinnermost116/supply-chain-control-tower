# memory/memory_manager.py
#
# PURPOSE:
#   This file is the safe interface to project_memory.json.
#   Nothing should ever read or write the JSON file directly.
#   All reads and writes go through the functions in this file.
#
# WHY A SEPARATE FILE?
#   JSON files are fragile. If two things write to the same file at the
#   same time, the file can become corrupted (invalid JSON). This module
#   handles file loading and saving carefully, with error handling,
#   so the rest of the project never has to worry about it.
#
# WHAT THIS FILE DOES:
#   load_memory()           — reads the JSON file and returns it as a dict
#   save_memory(data)       — writes a dict back to the JSON file
#   update_last_scan(...)   — records the result of a CI agent scan
#   update_last_briefing(.) — records the result of a morning briefing
#   add_decision(text)      — stores a key decision made during a session
#   add_session_summary(.)  — stores a summary of what happened today
#   add_escalation(order)   — adds an order to the active escalation list
#   clear_escalation(order) — removes an order once it is resolved
#   add_note(text)          — stores a freeform note for Claude to remember
#   get_status_summary()    — returns a plain-English summary of project state
#
# HOW TO USE FROM COMMAND LINE:
#   python memory/memory_manager.py
#   This runs the self-test at the bottom and prints the project status.

import json
import os
from datetime import datetime


# ─── PATH TO THE MEMORY FILE ─────────────────────────────────────────────────
# __file__ is the path to THIS file (memory_manager.py).
# os.path.dirname(__file__) is the folder containing this file (memory\).
# os.path.join(..., "project_memory.json") gives the full path to the JSON.
# This means the path always works no matter where Python is launched from.

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_memory.json")


# ─── LOAD MEMORY ─────────────────────────────────────────────────────────────

def load_memory() -> dict:
    """
    Reads project_memory.json and returns its contents as a Python dict.

    A dict is Python's way of storing key-value pairs, like:
      {"name": "Vishal", "phase": "Phase 10"}

    If the file does not exist or is corrupted, returns an empty dict {}
    instead of crashing — this is called "safe fallback".
    """
    if not os.path.exists(MEMORY_FILE):
        # File doesn't exist yet — return empty dict, caller handles it
        print(f"[memory_manager] Memory file not found at: {MEMORY_FILE}")
        return {}

    try:
        # "with open(...)" opens the file and automatically closes it afterward
        # "r" means read-only — we are not changing the file, just reading it
        # "encoding='utf-8'" ensures special characters are handled correctly
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            # json.load(f) converts the JSON text in the file into a Python dict
            return json.load(f)

    except json.JSONDecodeError as e:
        # JSONDecodeError means the file exists but the content is not valid JSON
        # This can happen if the file was manually edited incorrectly
        print(f"[memory_manager] ERROR: Memory file is corrupted — {e}")
        return {}

    except Exception as e:
        # Catch any other unexpected error so we never crash the caller
        print(f"[memory_manager] ERROR loading memory: {e}")
        return {}


# ─── SAVE MEMORY ─────────────────────────────────────────────────────────────

def save_memory(data: dict) -> bool:
    """
    Writes a Python dict back to project_memory.json.

    Returns True if saved successfully, False if something went wrong.

    WHY WE PASS THE WHOLE DICT:
      Rather than saving individual fields, we always load the full file,
      make changes to the dict in Python, then save the whole thing back.
      This ensures we never accidentally overwrite fields we didn't touch.
    """
    try:
        # Update the last_updated timestamp so we can always see when
        # the memory was last written to
        data["project"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            # json.dump() converts the Python dict back into JSON text
            # indent=2 makes the file human-readable (each field on its own line)
            # ensure_ascii=False allows non-English characters to be stored correctly
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print(f"[memory_manager] ERROR saving memory: {e}")
        return False


# ─── UPDATE LAST CI SCAN ─────────────────────────────────────────────────────

def update_last_scan(signals: int, recommendations: int,
                     top_pattern: str, summary: str) -> bool:
    """
    Records the results of the most recent CI agent scan.

    Call this after running /sc-scan so the results persist across sessions.

    Parameters:
      signals         — number of signals detected
      recommendations — number of recommendations generated
      top_pattern     — the most common pattern found (e.g. REPEATED_DELAY_BY_CARRIER)
      summary         — a one-sentence plain-English summary
    """
    data = load_memory()
    if not data:
        return False

    # Update the last_ci_scan section of the dict
    data["last_ci_scan"] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "signals_detected": signals,
        "recommendations_generated": recommendations,
        "top_pattern": top_pattern,
        "summary": summary,
    }

    return save_memory(data)


# ─── UPDATE LAST BRIEFING ─────────────────────────────────────────────────────

def update_last_briefing(risk_level: str, total_orders: int,
                         delayed: int, need_action: int,
                         top_root_cause: str, summary: str) -> bool:
    """
    Records the results of the most recent morning briefing.

    Call this after running /sc-briefing so the results persist.

    Parameters:
      risk_level      — LOW / MEDIUM / HIGH / CRITICAL
      total_orders    — total number of orders in the system
      delayed         — orders in DELAYED status (1-5 days late)
      need_action     — orders in NEED_ACTION status (5+ days late)
      top_root_cause  — most common delay cause (e.g. FREIGHT_HOLD)
      summary         — one-sentence plain-English summary
    """
    data = load_memory()
    if not data:
        return False

    data["last_briefing"] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "risk_level": risk_level,
        "total_orders": total_orders,
        "delayed_count": delayed,
        "need_action_count": need_action,
        "top_root_cause": top_root_cause,
        "summary": summary,
    }

    return save_memory(data)


# ─── ADD A KEY DECISION ───────────────────────────────────────────────────────

def add_decision(decision_text: str) -> bool:
    """
    Stores a key decision made during a session.

    Example: add_decision("Decided to disable WEAK_CARRIER_OVERUSE detector
                           until carrier data is updated.")

    Decisions are stored with a timestamp so you can see when each was made.
    The list is kept to the 20 most recent decisions so the file stays small.
    """
    data = load_memory()
    if not data:
        return False

    # "data.get(..., [])" safely returns an empty list if the key doesn't exist
    # This protects against corrupted or older memory files missing this field
    decisions = data.get("key_decisions", [])

    decisions.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "decision": decision_text,
    })

    # Keep only the most recent 20 decisions — the file stays compact
    data["key_decisions"] = decisions[-20:]

    return save_memory(data)


# ─── ADD A SESSION SUMMARY ────────────────────────────────────────────────────

def add_session_summary(summary_text: str) -> bool:
    """
    Stores a brief summary of what happened in the current session.

    Claude should call this at the end of each session with a 2-3 sentence
    description of what was built, decided, or fixed.

    Kept to the 10 most recent summaries.
    """
    data = load_memory()
    if not data:
        return False

    summaries = data.get("session_summaries", [])

    summaries.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary_text,
    })

    # Keep only the most recent 10 summaries
    data["session_summaries"] = summaries[-10:]

    return save_memory(data)


# ─── ADD AN ESCALATION ────────────────────────────────────────────────────────

def add_escalation(sales_order_no: str, reason: str) -> bool:
    """
    Adds an order to the active escalation list.

    Call this when /sc-escalate identifies orders that need manager attention.
    The escalation persists across sessions until clear_escalation() is called.

    Parameters:
      sales_order_no — e.g. "SO10003"
      reason         — why it was escalated, e.g. "12 days overdue, FREIGHT_HOLD"
    """
    data = load_memory()
    if not data:
        return False

    escalations = data.get("active_escalations", [])

    # Avoid duplicates — check if this order is already in the list
    existing_orders = [e["sales_order_no"] for e in escalations]
    if sales_order_no not in existing_orders:
        escalations.append({
            "sales_order_no": sales_order_no,
            "reason": reason,
            "escalated_date": datetime.now().strftime("%Y-%m-%d"),
        })

    data["active_escalations"] = escalations
    return save_memory(data)


# ─── CLEAR AN ESCALATION ──────────────────────────────────────────────────────

def clear_escalation(sales_order_no: str) -> bool:
    """
    Removes an order from the active escalation list once it is resolved.

    Parameters:
      sales_order_no — e.g. "SO10003"
    """
    data = load_memory()
    if not data:
        return False

    # List comprehension: build a new list that excludes the resolved order
    # [item for item in list if condition] = "keep only items where condition is True"
    data["active_escalations"] = [
        e for e in data.get("active_escalations", [])
        if e["sales_order_no"] != sales_order_no
    ]

    return save_memory(data)


# ─── UPDATE AGENT HEALTH ──────────────────────────────────────────────────────

def update_agent_health(agent_name: str, status: str) -> bool:
    """
    Records whether an agent is currently working.

    Parameters:
      agent_name — e.g. "shipping_delay_agent"
      status     — "HEALTHY", "ERROR", or "UNKNOWN"
    """
    data = load_memory()
    if not data:
        return False

    if "agent_health" not in data:
        data["agent_health"] = {}

    data["agent_health"][agent_name] = status
    return save_memory(data)


# ─── ADD A NOTE ───────────────────────────────────────────────────────────────

def add_note(note_text: str) -> bool:
    """
    Stores a freeform note — anything Vishal wants Claude to remember.

    Example: add_note("Carrier FastFreight has been unreliable this month.
                       Flag all their orders for manual review.")

    Kept to the 15 most recent notes.
    """
    data = load_memory()
    if not data:
        return False

    notes = data.get("notes", [])

    notes.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "note": note_text,
    })

    data["notes"] = notes[-15:]
    return save_memory(data)


# ─── UPDATE PHASE STATUS ──────────────────────────────────────────────────────

def update_phase_status(phase_key: str, status: str) -> bool:
    """
    Marks a phase or step as complete, in-progress, or not-started.

    Parameters:
      phase_key — e.g. "phase_10_step_4_memory"
      status    — "COMPLETE", "IN_PROGRESS", or "NOT_STARTED"
    """
    data = load_memory()
    if not data:
        return False

    if "phase_status" not in data:
        data["phase_status"] = {}

    data["phase_status"][phase_key] = status
    return save_memory(data)


# ─── GET STATUS SUMMARY ───────────────────────────────────────────────────────

def get_status_summary() -> str:
    """
    Returns a plain-English paragraph that Claude can read at session start
    to understand the current state of the project without needing to parse JSON.

    This is what Claude will print at the beginning of every conversation
    when it reads the memory file.
    """
    data = load_memory()
    if not data:
        return "Memory file could not be loaded. Starting fresh."

    lines = []

    # Project identity
    owner = data.get("project", {}).get("owner", "Unknown")
    last_updated = data.get("project", {}).get("last_updated", "never")
    lines.append(f"Project: Supply Chain Control Tower | Owner: {owner}")
    lines.append(f"Memory last updated: {last_updated}")

    # Current phase progress
    phases = data.get("phase_status", {})
    in_progress = [k for k, v in phases.items() if v == "IN_PROGRESS"]
    not_started = [k for k, v in phases.items() if v == "NOT_STARTED"]
    if in_progress:
        lines.append(f"Currently in progress: {', '.join(in_progress)}")
    if not_started:
        lines.append(f"Not yet started: {', '.join(not_started)}")

    # Last CI scan
    scan = data.get("last_ci_scan", {})
    if scan.get("date"):
        lines.append(
            f"Last CI scan: {scan['date']} — "
            f"{scan.get('signals_detected', 0)} signals, "
            f"{scan.get('recommendations_generated', 0)} recommendations. "
            f"{scan.get('summary', '')}"
        )

    # Last briefing
    briefing = data.get("last_briefing", {})
    if briefing.get("date"):
        lines.append(
            f"Last briefing: {briefing['date']} — "
            f"Risk: {briefing.get('risk_level', 'UNKNOWN')}, "
            f"{briefing.get('need_action_count', 0)} orders need action."
        )

    # Active escalations
    escalations = data.get("active_escalations", [])
    if escalations:
        order_list = ", ".join([e["sales_order_no"] for e in escalations])
        lines.append(f"Active escalations ({len(escalations)}): {order_list}")
    else:
        lines.append("No active escalations.")

    # Most recent decision
    decisions = data.get("key_decisions", [])
    if decisions:
        last = decisions[-1]
        lines.append(f"Last decision ({last['date']}): {last['decision']}")

    # Most recent session summary
    summaries = data.get("session_summaries", [])
    if summaries:
        last = summaries[-1]
        lines.append(f"Last session ({last['date']}): {last['summary']}")

    # Notes
    notes = data.get("notes", [])
    if notes:
        lines.append(f"Standing notes ({len(notes)} total):")
        for n in notes[-3:]:  # Show last 3 notes
            lines.append(f"  [{n['date']}] {n['note']}")

    return "\n".join(lines)


# ─── SELF-TEST ────────────────────────────────────────────────────────────────
# This block only runs when you type: python memory/memory_manager.py
# It does NOT run when other files import this module.
# "if __name__ == '__main__'" means "only run this if I am the main script"

if __name__ == "__main__":
    print("=" * 60)
    print("MEMORY MANAGER — SELF TEST")
    print("=" * 60)

    # Test 1: Load the memory file
    print("\n[TEST 1] Loading memory file...")
    memory = load_memory()
    if memory:
        print(f"  ✓ Loaded. Project owner: {memory.get('project', {}).get('owner', 'not set')}")
    else:
        print("  ✗ Failed to load memory file.")

    # Test 2: Get the status summary
    print("\n[TEST 2] Status summary:")
    print(get_status_summary())

    # Test 3: Write a test decision
    print("\n[TEST 3] Writing test decision...")
    result = add_decision("Self-test: Memory manager verified working.")
    print(f"  {'✓ Success' if result else '✗ Failed'}")

    # Test 4: Mark step 4 as complete
    print("\n[TEST 4] Marking phase_10_step_4_memory as COMPLETE...")
    result = update_phase_status("phase_10_step_4_memory", "COMPLETE")
    print(f"  {'✓ Success' if result else '✗ Failed'}")

    # Test 5: Read back to confirm
    print("\n[TEST 5] Confirming save by reading back...")
    memory = load_memory()
    step4_status = memory.get("phase_status", {}).get("phase_10_step_4_memory", "not found")
    print(f"  phase_10_step_4_memory = {step4_status}")

    print("\n" + "=" * 60)
    print("All tests complete. Check memory\\project_memory.json to see changes.")
    print("=" * 60)
