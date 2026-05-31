# scripts/setup_ci_database.py
#
# PURPOSE:
#   Creates all database tables needed for the Continuous Improvement Agent.
#   Run this ONCE to set up the tables inside your existing supply_chain.db
#
# HOW TO RUN:
#   cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
#   python scripts\setup_ci_database.py
#
# WHAT IT CREATES:
#   6 new tables inside data\supply_chain.db:
#     - ci_signals            : raw observations the agent collects
#     - ci_recommendations    : improvement suggestions the agent generates
#     - ci_approval_requests  : items waiting for your human decision
#     - ci_action_items       : approved work items for the team to action
#     - ci_outcomes           : results after an action was implemented
#     - ci_lessons            : things the agent learned from past decisions

import sqlite3
import os

# ─── PATH CONFIGURATION ──────────────────────────────────────────────────────
# This points to your existing database.
# Change this path if your project folder is in a different location.

DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"


def setup_ci_tables(db_path: str):
    """
    Connects to the database and creates all 6 CI Agent tables.
    If a table already exists, it is left untouched (safe to re-run).
    """
    print(f"Connecting to database: {db_path}")

    # Connect to the SQLite database file.
    # If the file doesn't exist yet, SQLite creates it automatically.
    conn = sqlite3.connect(db_path)

    # A cursor is what we use to send SQL commands to the database.
    cursor = conn.cursor()

    print("Creating CI Agent tables...")

    # ── TABLE 1: ci_signals ───────────────────────────────────────────────────
    # This is where the agent stores every observation it collects.
    # Think of it as a notepad where the agent writes down anything unusual it sees.
    # "IF NOT EXISTS" means: create the table ONLY if it doesn't already exist.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_signals (
            signal_id        TEXT PRIMARY KEY,   -- unique ID like SIG-0001
            project_name     TEXT NOT NULL,       -- which project this belongs to
            signal_type      TEXT NOT NULL,       -- e.g. REPEATED_DELAY, DATA_QUALITY
            domain           TEXT NOT NULL,       -- e.g. SHIPPING, INVENTORY, FREIGHT
            title            TEXT NOT NULL,       -- short description
            description      TEXT,               -- detailed description
            evidence_json    TEXT,               -- raw data that triggered this signal
            frequency        INTEGER DEFAULT 1,  -- how many times this pattern appeared
            affected_records TEXT,               -- order numbers, items, etc.
            severity         TEXT DEFAULT 'LOW', -- LOW, MEDIUM, HIGH, CRITICAL
            detected_at      TEXT NOT NULL,       -- when agent first saw this
            last_seen_at     TEXT NOT NULL,       -- when agent last saw this
            status           TEXT DEFAULT 'new'  -- new, reviewed, actioned, dismissed
        )
    """)
    print("  ✓ ci_signals")

    # ── TABLE 2: ci_recommendations ──────────────────────────────────────────
    # This is where the agent stores its improvement suggestions.
    # Each row is one specific recommendation with all its supporting details.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_recommendations (
            recommendation_id     TEXT PRIMARY KEY,  -- unique ID like CI-0001
            project_name          TEXT NOT NULL,
            signal_id             TEXT,              -- which signal triggered this
            title                 TEXT NOT NULL,
            summary               TEXT,
            evidence_json         TEXT,              -- list of supporting data points
            root_cause_hypothesis TEXT,              -- why the agent thinks this is happening
            recommended_action    TEXT NOT NULL,     -- what to do about it
            expected_benefit      TEXT,
            impact_score          INTEGER DEFAULT 0, -- 1-10, how much benefit if done
            effort_score          INTEGER DEFAULT 0, -- 1-10, how hard to implement
            risk_score            INTEGER DEFAULT 0, -- 1-10, how risky the change is
            priority              TEXT DEFAULT 'medium', -- low, medium, high, critical
            confidence            REAL DEFAULT 0.5,  -- 0.0 to 1.0
            requires_human_approval INTEGER DEFAULT 1, -- 1=yes, 0=no
            approval_reason       TEXT,
            suggested_owner       TEXT,
            next_steps_json       TEXT,
            rollback_notes        TEXT,
            status                TEXT DEFAULT 'new', -- new, pending_approval, approved,
                                                      -- rejected, in_progress, implemented,
                                                      -- deferred, failed
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            FOREIGN KEY (signal_id) REFERENCES ci_signals(signal_id)
        )
    """)
    print("  ✓ ci_recommendations")

    # ── TABLE 3: ci_approval_requests ────────────────────────────────────────
    # When the agent needs your decision, it creates a row here.
    # You review these and mark them approved, rejected, or deferred.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_approval_requests (
            approval_id          TEXT PRIMARY KEY,  -- unique ID like APR-0001
            recommendation_id    TEXT NOT NULL,
            project_name         TEXT NOT NULL,
            question_for_human   TEXT NOT NULL,     -- what the agent is asking you
            context_json         TEXT,              -- background info for your decision
            risk_level           TEXT DEFAULT 'MEDIUM', -- LOW, MEDIUM, HIGH, CRITICAL
            decision             TEXT DEFAULT 'pending', -- pending, approved, rejected, deferred
            decision_reason      TEXT,              -- why you approved or rejected
            decided_by           TEXT,              -- who made the decision
            requested_at         TEXT NOT NULL,
            decided_at           TEXT,
            FOREIGN KEY (recommendation_id) REFERENCES ci_recommendations(recommendation_id)
        )
    """)
    print("  ✓ ci_approval_requests")

    # ── TABLE 4: ci_action_items ──────────────────────────────────────────────
    # Once a recommendation is approved, the agent creates an action item here.
    # This is the work queue — what needs to actually get done.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_action_items (
            action_id            TEXT PRIMARY KEY,  -- unique ID like ACT-0001
            recommendation_id    TEXT NOT NULL,
            project_name         TEXT NOT NULL,
            title                TEXT NOT NULL,
            description          TEXT,
            business_impact      TEXT,
            acceptance_criteria  TEXT,              -- how you know when it's done
            priority             TEXT DEFAULT 'medium',
            suggested_owner      TEXT,
            due_date_suggestion  TEXT,
            dependencies_json    TEXT,              -- what needs to happen first
            risk_notes           TEXT,
            success_metric       TEXT,              -- what to measure after implementation
            status               TEXT DEFAULT 'open', -- open, in_progress, done, cancelled
            created_at           TEXT NOT NULL,
            completed_at         TEXT,
            FOREIGN KEY (recommendation_id) REFERENCES ci_recommendations(recommendation_id)
        )
    """)
    print("  ✓ ci_action_items")

    # ── TABLE 5: ci_outcomes ──────────────────────────────────────────────────
    # After an action item is completed, you log the result here.
    # This is how the agent knows if its recommendations actually helped.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_outcomes (
            outcome_id              TEXT PRIMARY KEY,  -- unique ID like OUT-0001
            recommendation_id       TEXT NOT NULL,
            action_id               TEXT,
            project_name            TEXT NOT NULL,
            status                  TEXT NOT NULL,  -- implemented, failed, partial
            measured_outcome        TEXT,           -- what actually happened
            success_metric_before   TEXT,           -- value before the change
            success_metric_after    TEXT,           -- value after the change
            implementation_notes    TEXT,
            lesson_learned          TEXT,           -- what the agent should remember
            recorded_by             TEXT,
            recorded_at             TEXT NOT NULL,
            FOREIGN KEY (recommendation_id) REFERENCES ci_recommendations(recommendation_id),
            FOREIGN KEY (action_id) REFERENCES ci_action_items(action_id)
        )
    """)
    print("  ✓ ci_outcomes")

    # ── TABLE 6: ci_lessons ───────────────────────────────────────────────────
    # The agent's memory. Each row is something the agent learned.
    # This grows over time and makes future recommendations smarter.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_lessons (
            lesson_id                 TEXT PRIMARY KEY,  -- unique ID like LES-0001
            project_name              TEXT NOT NULL,
            lesson                    TEXT NOT NULL,     -- plain English description
            source_recommendation_id  TEXT,
            lesson_type               TEXT DEFAULT 'preference', -- preference, threshold,
                                                                  -- pattern, false_positive
            confidence                REAL DEFAULT 0.5,
            applies_to_domain         TEXT,              -- SHIPPING, INVENTORY, etc.
            applies_to_signal_type    TEXT,
            times_reinforced          INTEGER DEFAULT 1, -- how many times this was confirmed
            created_at                TEXT NOT NULL,
            updated_at                TEXT NOT NULL,
            FOREIGN KEY (source_recommendation_id) REFERENCES ci_recommendations(recommendation_id)
        )
    """)
    print("  ✓ ci_lessons")

    # ── TABLE 7: ci_agent_run_log ─────────────────────────────────────────────
    # Every time the agent runs a scan, it logs a record here.
    # Useful for debugging and for tracking agent activity over time.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_agent_run_log (
            run_id           TEXT PRIMARY KEY,
            project_name     TEXT NOT NULL,
            run_type         TEXT NOT NULL,  -- FULL_SCAN, SIGNAL_ONLY, REPORT
            signals_found    INTEGER DEFAULT 0,
            recommendations_generated INTEGER DEFAULT 0,
            approvals_requested INTEGER DEFAULT 0,
            started_at       TEXT NOT NULL,
            completed_at     TEXT,
            status           TEXT DEFAULT 'running',  -- running, completed, failed
            error_message    TEXT
        )
    """)
    print("  ✓ ci_agent_run_log")

    # Save all changes to the database file.
    conn.commit()

    # Close the connection cleanly.
    conn.close()

    print("\n✅ All CI Agent tables created successfully.")
    print(f"   Database: {db_path}")
    print("\nNext step: Run mcp_server\\ci_mcp_server.py to test the agent.")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
# This block runs only when you execute this file directly.
# It does NOT run when another file imports from this file.

if __name__ == "__main__":
    # Check that the database file exists before trying to add tables.
    if not os.path.exists(DB_PATH):
        print(f"WARNING: Database not found at {DB_PATH}")
        print("Creating a new database file at that location...")
        # SQLite will create the file automatically when we connect.

    setup_ci_tables(DB_PATH)
