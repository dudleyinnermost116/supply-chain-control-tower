# scripts/upgrade_ci_database.py
#
# PURPOSE:
#   Adds 2 new tables and modifies 2 existing tables to support:
#     1. The new scoring model (urgency + exact formula from spec)
#     2. Quantitative self-learning rules
#
# RUN THIS ONLY ONCE, after setup_ci_database.py has already been run.
#
# HOW TO RUN:
#   cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
#   python scripts\upgrade_ci_database.py

import sqlite3
import os

DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"


def upgrade(db_path: str):
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Applying upgrades...")

    # ── UPGRADE 1: add urgency_score column to ci_recommendations ────────────
    # urgency is a new 1-5 input to the scoring formula.
    # We use ALTER TABLE to add the column without destroying existing data.
    # DEFAULT 3 means existing rows get a middle value of 3 automatically.
    try:
        cursor.execute("""
            ALTER TABLE ci_recommendations
            ADD COLUMN urgency_score INTEGER DEFAULT 3
        """)
        print("  ✓ Added urgency_score to ci_recommendations")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  ~ urgency_score already exists, skipping")
        else:
            raise

    # ── UPGRADE 2: add options/deadline/approver_role to ci_approval_requests ─
    try:
        cursor.execute("""
            ALTER TABLE ci_approval_requests
            ADD COLUMN options_json TEXT DEFAULT '[]'
        """)
        print("  ✓ Added options_json to ci_approval_requests")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  ~ options_json already exists, skipping")
        else:
            raise

    try:
        cursor.execute("""
            ALTER TABLE ci_approval_requests
            ADD COLUMN recommended_option TEXT DEFAULT ''
        """)
        print("  ✓ Added recommended_option to ci_approval_requests")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  ~ recommended_option already exists, skipping")
        else:
            raise

    try:
        cursor.execute("""
            ALTER TABLE ci_approval_requests
            ADD COLUMN deadline TEXT DEFAULT ''
        """)
        print("  ✓ Added deadline to ci_approval_requests")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  ~ deadline already exists, skipping")
        else:
            raise

    try:
        cursor.execute("""
            ALTER TABLE ci_approval_requests
            ADD COLUMN approver_role TEXT DEFAULT ''
        """)
        print("  ✓ Added approver_role to ci_approval_requests")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  ~ approver_role already exists, skipping")
        else:
            raise

    # ── UPGRADE 3: new table ci_learning_rules ────────────────────────────────
    # Stores quantitative self-learning rules that the agent applies
    # automatically based on accumulated outcomes and decisions.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_learning_rules (
            learning_rule_id           TEXT PRIMARY KEY,
            project_name               TEXT NOT NULL,
            pattern_type               TEXT NOT NULL,
            trigger_condition          TEXT NOT NULL,
            adjustment                 TEXT NOT NULL,
            confidence_delta           REAL DEFAULT 0.0,
            priority_delta             REAL DEFAULT 0.0,
            impact_delta               REAL DEFAULT 0.0,
            times_triggered            INTEGER DEFAULT 0,
            reason                     TEXT,
            created_from_recs_json     TEXT DEFAULT '[]',
            last_updated_at            TEXT NOT NULL
        )
    """)
    print("  ✓ Created ci_learning_rules table")

    # ── UPGRADE 4: new table ci_pattern_stats ────────────────────────────────
    # Tracks per-pattern-type statistics used by learning rules.
    # For example: how many REPEATED_DELAY_BY_CARRIER recs were rejected?
    # These counts drive the quantitative triggers (e.g. "if 5 rejections...").
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ci_pattern_stats (
            stat_id            TEXT PRIMARY KEY,
            project_name       TEXT NOT NULL,
            pattern_type       TEXT NOT NULL,
            total_generated    INTEGER DEFAULT 0,
            total_approved     INTEGER DEFAULT 0,
            total_rejected     INTEGER DEFAULT 0,
            total_deferred     INTEGER DEFAULT 0,
            total_implemented  INTEGER DEFAULT 0,
            total_failed       INTEGER DEFAULT 0,
            total_false_positive INTEGER DEFAULT 0,
            consecutive_rejections INTEGER DEFAULT 0,
            consecutive_approvals_with_outcome INTEGER DEFAULT 0,
            current_confidence_adjustment REAL DEFAULT 0.0,
            current_priority_adjustment   REAL DEFAULT 0.0,
            current_impact_adjustment     REAL DEFAULT 0.0,
            owner_override     TEXT DEFAULT '',
            last_updated_at    TEXT NOT NULL
        )
    """)
    print("  ✓ Created ci_pattern_stats table")

    conn.commit()
    conn.close()
    print("\n✅ Database upgrade complete.")
    print("Next step: replace ci_recommendation_generator.py and ci_learning_engine.py")
    print("           with the new upgraded versions.")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run setup_ci_database.py first.")
    else:
        upgrade(DB_PATH)
