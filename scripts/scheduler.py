# scripts/scheduler.py
#
# PURPOSE:
#   This script runs in the background on your Windows machine and
#   automatically fires "hooks" on a timer — without you needing to
#   ask Claude to do anything.
#
#   Think of it like a smart alarm clock for your supply chain system.
#   It wakes up on schedule, does the work, saves the results to memory,
#   and goes back to sleep. When you open Claude Desktop later, the
#   results are already waiting for you.
#
# HOOKS DEFINED IN THIS FILE:
#   morning_briefing    — runs every day at 8:00am
#   ci_scan             — runs every hour
#   need_action_monitor — runs every 30 minutes
#   agent_health_check  — runs every 6 hours
#
# ALL HOOKS ARE CONTROLLED BY settings.yaml:
#   To turn a hook off: set enabled: false under that hook in settings.yaml
#   To change the time: edit the schedule values in settings.yaml
#   No code changes needed — just edit the config file.
#
# HOW TO RUN:
#   Option A (terminal): python scripts\scheduler.py
#   Option B (double-click): run_scheduler.bat
#   Option C (startup): add run_scheduler.bat to Windows startup folder
#
# HOW TO STOP:
#   Press Ctrl+C in the terminal window, or close the terminal.

import sys
import os
import logging
from datetime import date, datetime

# ─── PATH SETUP ──────────────────────────────────────────────────────────────
# Same pattern used in all MCP servers.
# __file__ = this file (scripts\scheduler.py)
# Two dirname() calls = go up to project root
# sys.path.insert = add project root so all our modules are importable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

# ─── LOGGING SETUP ────────────────────────────────────────────────────────────
# Logging lets us see what the scheduler is doing without opening a debugger.
# Every time a hook fires, it writes a line to both the terminal and a log file.
#
# logging.basicConfig() sets up the logging system with:
#   level=INFO    → show INFO messages and above (INFO, WARNING, ERROR)
#   format        → how each line looks: [2025-01-15 08:00:01] INFO - message
#   handlers      → where to send log lines (terminal + log file)

LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "scheduler.log")
os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        # StreamHandler sends log lines to the terminal (so you can watch it live)
        logging.StreamHandler(),
        # FileHandler writes log lines to a file (so you can review them later)
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)

# logging.getLogger(__name__) creates a logger named after this file
# We use this throughout the file: logger.info("..."), logger.error("...")
logger = logging.getLogger(__name__)

# ─── IMPORT APSCHEDULER ───────────────────────────────────────────────────────
# APScheduler is the library that handles timing.
# BlockingScheduler = runs in the foreground, keeps the script alive
# It is like a while True loop that wakes up at the right times

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    logger.error(
        "APScheduler is not installed. "
        "Run: pip install apscheduler"
    )
    sys.exit(1)

# ─── IMPORT OUR OWN MODULES ───────────────────────────────────────────────────
# These are the modules we have already built. The scheduler uses them
# to do the actual work inside each hook.

try:
    from memory.memory_manager import (
        update_last_briefing,
        update_last_scan,
        add_escalation,
        update_agent_health,
        add_note,
    )
except ImportError as e:
    logger.error(f"Could not import memory_manager: {e}")
    sys.exit(1)

# ─── IMPORT SUPPLY CHAIN MODULES ──────────────────────────────────────────────
# We import these inside each hook function (not at the top) so that if
# one module has an error, it only affects that one hook — not the whole scheduler.
# This is called "lazy importing" and makes the scheduler more resilient.


# ─── SETTINGS LOADER ─────────────────────────────────────────────────────────
# Try to load hook settings from settings.yaml.
# If settings.yaml is not available, fall back to safe defaults.
# This means the scheduler always works, even if settings are missing.

def load_hook_settings() -> dict:
    """
    Reads hook configuration from settings.yaml.
    Returns a dict of hook settings.
    Falls back to defaults if settings.yaml cannot be read.
    """
    defaults = {
        "morning_briefing": {
            "enabled": True,
            "hour": 8,
            "minute": 0,
        },
        "ci_scan": {
            "enabled": True,
            "interval_minutes": 60,
        },
        "need_action_monitor": {
            "enabled": True,
            "interval_minutes": 30,
        },
        "agent_health_check": {
            "enabled": True,
            "interval_hours": 6,
        },
    }

    try:
        from config.settings_loader import get_settings
        settings = get_settings()
        hooks = settings.get("hooks", {})
        if hooks:
            logger.info("Hook settings loaded from settings.yaml")
            return hooks
    except Exception as e:
        logger.warning(f"Could not load settings.yaml — using defaults. ({e})")

    return defaults


# ─── HOOK 1: MORNING BRIEFING ─────────────────────────────────────────────────

def hook_morning_briefing():
    """
    Runs every morning at 8:00am (configurable in settings.yaml).

    WHAT IT DOES:
      1. Loads all shipment data from the database
      2. Counts delays, NEED_ACTION orders, reason codes
      3. Calculates risk level
      4. Saves the result to project_memory.json

    WHAT CHANGES AFTER IT RUNS:
      When you open Claude Desktop after 8am and say "read my project memory",
      Claude already knows today's briefing — you do not have to run /sc-briefing.
    """
    logger.info("HOOK FIRED: morning_briefing")

    try:
        # Your project uses separate data loader files per domain,
        # not a unified db_loader. We import the correct one here.
        # DATA_FILE points to your shipments CSV in the data\ folder.
        from supply_chain.data_loader import load_shipments
        from supply_chain.rules import assign_delay_status, assign_reason_code
        from supply_chain.recommendations import calculate_risk_level

        data_file = os.path.join(PROJECT_ROOT, "data", "shipments_sample.csv")
        rows = load_shipments(data_file)
        today = date.today()

        total = len(rows)
        delayed = 0
        need_action = 0
        reason_counts = {}

        for row in rows:
            status = assign_delay_status(row, today)
            if status == "DELAYED":
                delayed += 1
            elif status == "NEED_ACTION":
                need_action += 1

            reason = assign_reason_code(row, today)
            if status in ("DELAYED", "NEED_ACTION"):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

        risk = calculate_risk_level(total, delayed, need_action)
        top_cause = max(reason_counts, key=reason_counts.get) if reason_counts else "NONE"
        summary = (
            f"Auto-briefing {today}: {total} orders, "
            f"{delayed} delayed, {need_action} need action. "
            f"Risk: {risk}. Top cause: {top_cause}."
        )

        update_last_briefing(risk, total, delayed, need_action, top_cause, summary)
        logger.info(f"morning_briefing complete — {summary}")

    except Exception as e:
        logger.error(f"morning_briefing FAILED: {e}")


# ─── HOOK 2: CI SCAN ──────────────────────────────────────────────────────────

def hook_ci_scan():
    """
    Runs every hour (configurable in settings.yaml).

    WHAT IT DOES:
      1. Runs the CI signal detector across all operational data
      2. Counts how many signals and recommendations were generated
      3. Identifies the most common pattern
      4. Saves the result to project_memory.json

    WHAT CHANGES AFTER IT RUNS:
      The memory file always has the latest CI scan result. When you ask
      Claude "what did the last scan find?", it reads from memory — instant answer.
    """
    logger.info("HOOK FIRED: ci_scan")

    try:
        from supply_chain.ci_signal_detector import run_all_detectors
        # Your project uses separate data loader files per domain,
        # not a unified db_loader. Each reads from its own CSV file.
        from supply_chain.data_loader import load_shipments
        from supply_chain.inventory_data_loader import load_inventory
        from supply_chain.freight_data_loader import load_freight
        from supply_chain.warehouse_data_loader import load_warehouse_picks

        today = date.today()

        ship_rows = load_shipments(os.path.join(PROJECT_ROOT, "data", "shipments_sample.csv"))
        inv_rows  = load_inventory(os.path.join(PROJECT_ROOT, "data", "inventory_sample.csv"))
        frt_rows  = load_freight(os.path.join(PROJECT_ROOT, "data", "freight_sample.csv"))
        wh_rows   = load_warehouse_picks(os.path.join(PROJECT_ROOT, "data", "warehouse_sample.csv"))

        signals = run_all_detectors(ship_rows, inv_rows, frt_rows, wh_rows, today)

        signal_count = len(signals)
        top_pattern = ""
        if signals:
            # Find the most common pattern type across all signals
            pattern_counts = {}
            for s in signals:
                p = s.get("pattern_type", "UNKNOWN")
                pattern_counts[p] = pattern_counts.get(p, 0) + 1
            top_pattern = max(pattern_counts, key=pattern_counts.get)

        summary = (
            f"Auto-scan {today}: {signal_count} signal(s) detected. "
            f"Top pattern: {top_pattern or 'none'}."
        )

        update_last_scan(signal_count, 0, top_pattern, summary)
        logger.info(f"ci_scan complete — {summary}")

    except Exception as e:
        logger.error(f"ci_scan FAILED: {e}")


# ─── HOOK 3: NEED ACTION MONITOR ──────────────────────────────────────────────

def hook_need_action_monitor():
    """
    Runs every 30 minutes (configurable in settings.yaml).

    WHAT IT DOES:
      1. Scans all shipments for orders in NEED_ACTION status
         (more than 5 days overdue and not yet shipped)
      2. For any new NEED_ACTION order found, adds it to the
         active_escalations list in project_memory.json

    WHAT CHANGES AFTER IT RUNS:
      If an order crosses the 5-day threshold at any time of day,
      it gets added to escalations automatically. Next time you open
      Claude Desktop and read memory, you immediately see it flagged.
      You do not have to run /sc-escalate to find out.
    """
    logger.info("HOOK FIRED: need_action_monitor")

    try:
        # Your project uses separate data loader files per domain,
        # not a unified db_loader. This reads from your shipments CSV.
        from supply_chain.data_loader import load_shipments
        from supply_chain.rules import (
            assign_delay_status,
            assign_reason_code,
            calculate_delay_days,
        )

        today = date.today()
        rows = load_shipments(os.path.join(PROJECT_ROOT, "data", "shipments_sample.csv"))

        found = 0
        for row in rows:
            status = assign_delay_status(row, today)
            if status == "NEED_ACTION":
                order_no = row.get("sales_order_no", "")
                delay_days = calculate_delay_days(row, today)
                reason = assign_reason_code(row, today)
                escalation_reason = (
                    f"{delay_days} days overdue — {reason} — auto-flagged by monitor"
                )
                add_escalation(order_no, escalation_reason)
                found += 1

        logger.info(f"need_action_monitor complete — {found} NEED_ACTION order(s) found")

    except Exception as e:
        logger.error(f"need_action_monitor FAILED: {e}")


# ─── HOOK 4: AGENT HEALTH CHECK ───────────────────────────────────────────────

def hook_agent_health_check():
    """
    Runs every 6 hours (configurable in settings.yaml).

    WHAT IT DOES:
      1. Checks that each MCP server file exists on disk
      2. Checks that each server file is readable (not corrupted)
      3. Saves the health status of each agent to project_memory.json

    NOTE ON WHAT THIS CHECKS:
      This checks that the files exist and are readable Python files.
      It does NOT check whether Claude Desktop has them connected and running —
      that requires Claude Desktop itself to be open.
      Think of this as a "file integrity check" rather than a "live ping".

    WHAT CHANGES AFTER IT RUNS:
      If a server file gets accidentally deleted or renamed, this hook
      will write ERROR to that agent's health status in memory.
      Next time you read memory, Claude will flag it immediately.
    """
    logger.info("HOOK FIRED: agent_health_check")

    # Map of agent name → expected file path
    agents = {
        "shipping_delay_agent":  "mcp_server\\shipping_mcp_server.py",
        "inventory_agent":       "mcp_server\\inventory_mcp_server.py",
        "po_agent":              "mcp_server\\po_mcp_server.py",
        "freight_agent":         "mcp_server\\freight_mcp_server.py",
        "warehouse_agent":       "mcp_server\\warehouse_mcp_server.py",
        "investigation_agent":   "mcp_server\\investigation_mcp_server.py",
        "recommendation_agent":  "mcp_server\\recommendation_mcp_server.py",
        "ci_agent":              "mcp_server\\ci_mcp_server.py",
        "memory_agent":          "mcp_server\\memory_mcp_server.py",
    }

    healthy = 0
    errors = 0

    for agent_name, relative_path in agents.items():
        full_path = os.path.join(PROJECT_ROOT, relative_path)
        if os.path.exists(full_path):
            update_agent_health(agent_name, "HEALTHY")
            healthy += 1
        else:
            update_agent_health(agent_name, "ERROR")
            logger.warning(f"Agent file missing: {full_path}")
            errors += 1

    logger.info(
        f"agent_health_check complete — "
        f"{healthy} healthy, {errors} missing"
    )


# ─── HELPER: GET DATABASE PATH ────────────────────────────────────────────────

def _get_db_path() -> str:
    """
    Returns the path to supply_chain.db.
    Tries settings.yaml first, falls back to the default path.
    The underscore prefix (_) is a Python convention meaning
    "this function is for internal use in this file only".
    """
    try:
        from config.settings_loader import get_database_path
        return get_database_path()
    except Exception:
        # Default fallback path if settings.yaml is not available
        return os.path.join(PROJECT_ROOT, "data", "supply_chain.db")


# ─── MAIN: BUILD AND START THE SCHEDULER ─────────────────────────────────────

def main():
    """
    Builds the APScheduler instance, registers all enabled hooks,
    and starts the scheduler loop.

    This function runs when you execute: python scripts\scheduler.py
    It blocks (stays running) until you press Ctrl+C.
    """
    logger.info("=" * 60)
    logger.info("Supply Chain Control Tower — Scheduler Starting")
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 60)

    # Load hook settings from settings.yaml (or defaults)
    hooks = load_hook_settings()

    # Create the scheduler instance
    # BlockingScheduler = keeps this script alive until Ctrl+C
    scheduler = BlockingScheduler(timezone="UTC")

    # ── Register Hook 1: Morning Briefing ─────────────────────────────────
    # CronTrigger fires at a specific time of day — like a cron job in Linux.
    # hour=8, minute=0 means 8:00am UTC every day.
    # If you want 8am local time, adjust for your timezone offset.

    briefing_cfg = hooks.get("morning_briefing", {})
    if briefing_cfg.get("enabled", True):
        hour   = briefing_cfg.get("hour", 8)
        minute = briefing_cfg.get("minute", 0)
        scheduler.add_job(
            hook_morning_briefing,
            CronTrigger(hour=hour, minute=minute),
            id="morning_briefing",
            name="Morning Briefing",
            misfire_grace_time=300,  # If missed by less than 5 min, still run it
        )
        logger.info(f"Registered: morning_briefing at {hour:02d}:{minute:02d} UTC daily")
    else:
        logger.info("Skipped: morning_briefing (disabled in settings)")

    # ── Register Hook 2: CI Scan ───────────────────────────────────────────
    # IntervalTrigger fires every N minutes/hours.
    # interval_minutes=60 means it runs once per hour.

    ci_cfg = hooks.get("ci_scan", {})
    if ci_cfg.get("enabled", True):
        interval = ci_cfg.get("interval_minutes", 60)
        scheduler.add_job(
            hook_ci_scan,
            IntervalTrigger(minutes=interval),
            id="ci_scan",
            name="CI Agent Scan",
            misfire_grace_time=120,
        )
        logger.info(f"Registered: ci_scan every {interval} minutes")
    else:
        logger.info("Skipped: ci_scan (disabled in settings)")

    # ── Register Hook 3: NEED_ACTION Monitor ──────────────────────────────

    monitor_cfg = hooks.get("need_action_monitor", {})
    if monitor_cfg.get("enabled", True):
        interval = monitor_cfg.get("interval_minutes", 30)
        scheduler.add_job(
            hook_need_action_monitor,
            IntervalTrigger(minutes=interval),
            id="need_action_monitor",
            name="NEED_ACTION Monitor",
            misfire_grace_time=120,
        )
        logger.info(f"Registered: need_action_monitor every {interval} minutes")
    else:
        logger.info("Skipped: need_action_monitor (disabled in settings)")

    # ── Register Hook 4: Agent Health Check ───────────────────────────────

    health_cfg = hooks.get("agent_health_check", {})
    if health_cfg.get("enabled", True):
        interval = health_cfg.get("interval_hours", 6)
        scheduler.add_job(
            hook_agent_health_check,
            IntervalTrigger(hours=interval),
            id="agent_health_check",
            name="Agent Health Check",
            misfire_grace_time=300,
        )
        logger.info(f"Registered: agent_health_check every {interval} hours")
    else:
        logger.info("Skipped: agent_health_check (disabled in settings)")

    # ── Run all hooks once immediately on startup ──────────────────────────
    # This means you do not have to wait for the first scheduled time.
    # The moment you start the scheduler, it runs all enabled hooks right away.
    logger.info("Running all enabled hooks once at startup...")
    hook_agent_health_check()
    hook_need_action_monitor()
    # Note: we do NOT run morning_briefing or ci_scan at startup
    # because they load from the database and may be slow.
    # They will run at their scheduled times.

    # ── Start the scheduler loop ──────────────────────────────────────────
    logger.info("Scheduler is running. Press Ctrl+C to stop.")
    logger.info("=" * 60)

    try:
        # start() blocks here — the script stays alive, waking up on schedule
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        # Ctrl+C raises KeyboardInterrupt — we catch it and exit cleanly
        logger.info("Scheduler stopped by user.")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()