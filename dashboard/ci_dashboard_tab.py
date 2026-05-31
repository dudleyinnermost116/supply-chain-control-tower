# dashboard/ci_dashboard_tab.py
#
# PURPOSE:
#   This is the Streamlit UI for the Continuous Improvement Agent.
#   It is designed to be imported into your existing app.py as a new tab.
#
# HOW TO ADD TO YOUR EXISTING DASHBOARD:
#   In dashboard/app.py, find where you define tabs, and add:
#
#     from ci_dashboard_tab import render_ci_tab
#
#     tab1, tab2, tab3, tab_ci = st.tabs([
#         "Command Center", "Domains", "Investigation", "🔄 Improvements"
#     ])
#
#     with tab_ci:
#         render_ci_tab()
#
# WHAT IT SHOWS:
#   - KPI cards: total recs, pending approvals, open actions, success rate
#   - Signal scanner: click a button to run a new scan
#   - Recommendations table with approve/reject buttons
#   - Lessons learned list
#   - Weekly improvement briefing

import streamlit as st
import sqlite3
import json
import sys
import os
from datetime import date, datetime

# Add the src and config directories to the Python path.
# This lets us import our modules.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))

from supply_chain.ci_signal_detector import run_full_signal_scan
from supply_chain.ci_recommendation_generator import generate_all_recommendations
from supply_chain.ci_learning_engine import (
    record_approval_decision,
    create_action_item_from_recommendation,
    log_outcome,
    get_improvement_summary,
    _connect,
)
from ci_project_config import PROJECT_CONFIG

# ─── DATABASE PATH ────────────────────────────────────────────────────────────
DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"


# ─── HELPER: get recommendations from db ─────────────────────────────────────

def _get_recommendations_from_db(status_filter: list = None) -> list:
    """Loads recommendations from the database, optionally filtered by status."""
    conn = _connect(DB_PATH)
    cursor = conn.cursor()

    if status_filter:
        placeholders = ",".join(["?" for _ in status_filter])
        cursor.execute(f"""
            SELECT * FROM ci_recommendations
            WHERE project_name = ? AND status IN ({placeholders})
            ORDER BY impact_score DESC, created_at DESC
        """, [PROJECT_CONFIG["project_name"]] + status_filter)
    else:
        cursor.execute("""
            SELECT * FROM ci_recommendations
            WHERE project_name = ?
            ORDER BY impact_score DESC, created_at DESC
        """, (PROJECT_CONFIG["project_name"],))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _get_signals_from_db() -> list:
    """Loads recent signals from the database."""
    conn = _connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM ci_signals
        WHERE project_name = ?
        ORDER BY severity DESC, detected_at DESC
        LIMIT 20
    """, (PROJECT_CONFIG["project_name"],))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _get_lessons_from_db() -> list:
    """Loads all lessons from the database."""
    conn = _connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM ci_lessons
        WHERE project_name = ?
        ORDER BY confidence DESC, times_reinforced DESC
    """, (PROJECT_CONFIG["project_name"],))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _save_signal_and_recs(signals: list, recommendations: list):
    """Saves newly scanned signals and recommendations to the database."""
    conn = _connect(DB_PATH)
    cursor = conn.cursor()

    for sig in signals:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO ci_signals (
                    signal_id, project_name, signal_type, domain,
                    title, description, evidence_json, frequency,
                    affected_records, severity, detected_at, last_seen_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sig["signal_id"], sig["project_name"], sig["signal_type"], sig["domain"],
                sig["title"], sig["description"], sig.get("evidence_json", "[]"),
                sig["frequency"], sig["affected_records"], sig["severity"],
                sig["detected_at"], sig["last_seen_at"], sig["status"],
            ))
        except Exception:
            pass

    for rec in recommendations:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO ci_recommendations (
                    recommendation_id, project_name, signal_id, title, summary,
                    evidence_json, root_cause_hypothesis, recommended_action,
                    expected_benefit, impact_score, effort_score, risk_score,
                    priority, confidence, requires_human_approval, approval_reason,
                    suggested_owner, next_steps_json, rollback_notes, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec["recommendation_id"], rec["project_name"], rec.get("signal_id", ""),
                rec["title"], rec.get("summary", ""), rec.get("evidence_json", "[]"),
                rec.get("root_cause_hypothesis", ""), rec["recommended_action"],
                rec.get("expected_benefit", ""), rec.get("impact_score", 5),
                rec.get("effort_score", 5), rec.get("risk_score", 5),
                rec.get("priority", "medium"), rec.get("confidence", 0.65),
                rec.get("requires_human_approval", 1), rec.get("approval_reason", ""),
                rec.get("suggested_owner", ""), rec.get("next_steps_json", "[]"),
                rec.get("rollback_notes", ""), rec.get("status", "new"),
                rec.get("created_at", datetime.now().isoformat()),
                rec.get("updated_at", datetime.now().isoformat()),
            ))
        except Exception:
            pass

    conn.commit()
    conn.close()


# ─── COLOUR MAPPINGS ──────────────────────────────────────────────────────────

PRIORITY_COLORS = {
    "critical": "#ef4444",
    "high":     "#f97316",
    "medium":   "#eab308",
    "low":      "#22c55e",
}

SEVERITY_COLORS = {
    "CRITICAL": "#ef4444",
    "HIGH":     "#f97316",
    "MEDIUM":   "#eab308",
    "LOW":      "#22c55e",
}

STATUS_COLORS = {
    "new":              "#6366f1",
    "pending_approval": "#f59e0b",
    "approved":         "#3b82f6",
    "rejected":         "#ef4444",
    "in_progress":      "#8b5cf6",
    "implemented":      "#22c55e",
    "deferred":         "#6b7280",
    "failed":           "#dc2626",
}


def _color_badge(text: str, color: str) -> str:
    """Creates an HTML badge with the given text and color."""
    return (
        f'<span style="background:{color}22; color:{color}; '
        f'padding:2px 8px; border-radius:4px; font-size:12px; '
        f'font-weight:600; letter-spacing:0.5px;">{text.upper()}</span>'
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def render_ci_tab():
    """
    Renders the entire Continuous Improvement tab in the Streamlit dashboard.
    Call this function inside a Streamlit tab block in app.py.
    """

    st.markdown("## 🔄 Continuous Improvement Agent")
    st.markdown(
        "The CI Agent continuously scans your supply chain data for patterns, "
        "generates specific improvement recommendations, and learns from your decisions."
    )

    # ── KPI Cards Row ─────────────────────────────────────────────────────────
    summary = get_improvement_summary(DB_PATH)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📋 Total Recommendations",
            value=summary.get("total_recommendations", 0),
            help="Total improvement recommendations generated by the CI Agent",
        )
    with col2:
        pending = summary.get("pending_approvals", 0)
        st.metric(
            label="⏳ Pending Your Review",
            value=pending,
            delta=f"Need decision" if pending > 0 else "All reviewed",
            delta_color="inverse",
            help="Recommendations waiting for your approve/reject decision",
        )
    with col3:
        st.metric(
            label="✅ Implemented",
            value=summary.get("total_implemented", 0),
            help="Recommendations that were implemented and outcomes were logged",
        )
    with col4:
        st.metric(
            label="🧠 Lessons Learned",
            value=summary.get("lessons_learned_count", 0),
            help="Things the CI agent has learned from your decisions",
        )

    st.divider()

    # ── Scan Controls ─────────────────────────────────────────────────────────
    col_scan, col_info = st.columns([1, 3])

    with col_scan:
        run_scan = st.button(
            "🔍 Run Improvement Scan",
            type="primary",
            use_container_width=True,
            help="Scans all supply chain data for improvement opportunities",
        )

    with col_info:
        last_scan = summary.get("last_scan_at", "Never")
        st.info(
            f"**Last scan:** {last_scan}  |  "
            f"**Success rate:** {summary.get('implementation_success_rate', 'N/A')}",
            icon="ℹ️"
        )

    if run_scan:
        with st.spinner("Scanning all domains for improvement opportunities..."):
            # Run the full signal scan.
            signals = run_full_signal_scan(DB_PATH)
            recommendations = generate_all_recommendations(signals)
            _save_signal_and_recs(signals, recommendations)

        st.success(
            f"✅ Scan complete — found **{len(signals)} signals** and generated "
            f"**{len(recommendations)} recommendations**."
        )
        st.rerun()

    # ── Tabs within the CI tab ─────────────────────────────────────────────────
    ci_tab1, ci_tab2, ci_tab3, ci_tab4 = st.tabs([
        "📋 Recommendations",
        "📡 Signals Detected",
        "🧠 Lessons Learned",
        "📊 Weekly Report",
    ])

    # ── Tab 1: Recommendations ────────────────────────────────────────────────
    with ci_tab1:
        st.markdown("### Improvement Recommendations")

        status_filter = st.multiselect(
            "Filter by status",
            options=["new", "pending_approval", "approved", "rejected", "in_progress", "implemented", "deferred"],
            default=["new", "pending_approval"],
            key="ci_status_filter",
        )

        recs = _get_recommendations_from_db(status_filter if status_filter else None)

        if not recs:
            st.info("No recommendations found with the selected filters. Run a scan or change the filter.")
        else:
            for rec in recs:
                priority = rec.get("priority", "medium")
                status = rec.get("status", "new")
                color = PRIORITY_COLORS.get(priority, "#6b7280")

                with st.expander(
                    f"[{priority.upper()}] {rec['title'][:80]}",
                    expanded=(status in ("new", "pending_approval")),
                ):
                    col_a, col_b = st.columns([3, 1])

                    with col_a:
                        st.markdown(f"**ID:** `{rec['recommendation_id']}`")
                        st.markdown(f"**Status:** {_color_badge(status, STATUS_COLORS.get(status, '#6b7280'))}", unsafe_allow_html=True)
                        st.markdown(f"**Owner:** {rec.get('suggested_owner', 'Not assigned')}")

                    with col_b:
                        impact = rec.get("impact_score", 5)
                        effort = rec.get("effort_score", 5)
                        risk   = rec.get("risk_score", 5)
                        conf   = int(float(rec.get("confidence", 0.65)) * 100)

                        st.markdown(f"**Impact:** {impact}/10")
                        st.markdown(f"**Effort:** {effort}/10")
                        st.markdown(f"**Risk:** {risk}/10")
                        st.markdown(f"**Confidence:** {conf}%")

                    st.markdown("**What was found:**")
                    st.markdown(rec.get("summary", ""))

                    st.markdown("**Recommended Action:**")
                    st.markdown(rec.get("recommended_action", ""))

                    st.markdown("**Expected Benefit:**")
                    st.markdown(rec.get("expected_benefit", ""))

                    if rec.get("approval_reason"):
                        st.warning(f"⚠️ **Requires approval:** {rec['approval_reason']}")

                    # Show approval buttons only for pending recommendations.
                    if status in ("new", "pending_approval"):
                        st.markdown("---")
                        col_approve, col_reject, col_defer = st.columns(3)

                        with col_approve:
                            if st.button(
                                "✅ Approve",
                                key=f"approve_{rec['recommendation_id']}",
                                use_container_width=True,
                            ):
                                record_approval_decision(
                                    rec["recommendation_id"], "approved",
                                    "Approved via dashboard", db_path=DB_PATH,
                                )
                                create_action_item_from_recommendation(
                                    rec["recommendation_id"], DB_PATH
                                )
                                st.success(f"Approved! Action item created.")
                                st.rerun()

                        with col_reject:
                            reject_reason = st.text_input(
                                "Rejection reason (required)",
                                key=f"reject_reason_{rec['recommendation_id']}",
                                placeholder="Why is this not applicable?",
                            )
                            if st.button(
                                "❌ Reject",
                                key=f"reject_{rec['recommendation_id']}",
                                use_container_width=True,
                            ):
                                if reject_reason:
                                    record_approval_decision(
                                        rec["recommendation_id"], "rejected",
                                        reject_reason, db_path=DB_PATH,
                                    )
                                    st.warning("Rejected. Lesson saved.")
                                    st.rerun()
                                else:
                                    st.error("Please enter a rejection reason first.")

                        with col_defer:
                            if st.button(
                                "⏸ Defer",
                                key=f"defer_{rec['recommendation_id']}",
                                use_container_width=True,
                            ):
                                record_approval_decision(
                                    rec["recommendation_id"], "deferred",
                                    "Deferred via dashboard", db_path=DB_PATH,
                                )
                                st.info("Deferred.")
                                st.rerun()

                    # Outcome logging for implemented/in_progress items.
                    if status in ("in_progress", "approved"):
                        st.markdown("---")
                        st.markdown("**Log Outcome:**")
                        col_o1, col_o2 = st.columns(2)
                        with col_o1:
                            outcome_status = st.selectbox(
                                "Result",
                                ["implemented", "partial", "failed"],
                                key=f"outcome_status_{rec['recommendation_id']}",
                            )
                            before_val = st.text_input(
                                "Metric before",
                                key=f"before_{rec['recommendation_id']}",
                                placeholder="e.g. 3 carrier delays",
                            )
                        with col_o2:
                            outcome_desc = st.text_area(
                                "What happened",
                                key=f"outcome_desc_{rec['recommendation_id']}",
                                placeholder="Describe what actually happened after implementation",
                                height=80,
                            )
                            after_val = st.text_input(
                                "Metric after",
                                key=f"after_{rec['recommendation_id']}",
                                placeholder="e.g. 0 carrier delays",
                            )

                        if st.button(
                            "📝 Log Outcome",
                            key=f"log_outcome_{rec['recommendation_id']}",
                        ):
                            if outcome_desc:
                                log_outcome(
                                    recommendation_id=rec["recommendation_id"],
                                    action_id="",
                                    status=outcome_status,
                                    measured_outcome=outcome_desc,
                                    metric_before=before_val,
                                    metric_after=after_val,
                                    db_path=DB_PATH,
                                )
                                st.success("Outcome logged! Lesson saved to agent memory.")
                                st.rerun()
                            else:
                                st.error("Please describe what happened before logging.")

    # ── Tab 2: Signals ────────────────────────────────────────────────────────
    with ci_tab2:
        st.markdown("### Signals Detected")
        st.caption("These are the raw observations the CI Agent collected before generating recommendations.")

        signals = _get_signals_from_db()

        if not signals:
            st.info("No signals yet. Run a scan to detect patterns.")
        else:
            for sig in signals:
                severity = sig.get("severity", "LOW")
                color = SEVERITY_COLORS.get(severity, "#6b7280")

                with st.expander(
                    f"[{severity}] {sig['title'][:80]}",
                    expanded=False,
                ):
                    st.markdown(f"**Signal ID:** `{sig['signal_id']}`")
                    st.markdown(f"**Type:** `{sig['signal_type']}`  |  **Domain:** `{sig['domain']}`")
                    st.markdown(f"**Frequency:** {sig['frequency']} occurrences")
                    st.markdown(f"**Detected:** {sig['detected_at']}")
                    st.markdown(f"**Description:** {sig['description']}")

                    if sig.get("affected_records"):
                        st.markdown(f"**Affected:** `{sig['affected_records']}`")

                    if sig.get("evidence_json"):
                        try:
                            evidence = json.loads(sig["evidence_json"])
                            if evidence:
                                st.markdown("**Evidence:**")
                                for e in evidence:
                                    st.markdown(f"- {e}")
                        except (json.JSONDecodeError, TypeError):
                            pass

    # ── Tab 3: Lessons Learned ────────────────────────────────────────────────
    with ci_tab3:
        st.markdown("### 🧠 Agent Memory — Lessons Learned")
        st.caption(
            "Every time you approve, reject, or log an outcome, the agent saves a lesson. "
            "These lessons shape future recommendations."
        )

        lessons = _get_lessons_from_db()

        if not lessons:
            st.info(
                "No lessons yet. The agent learns when you approve/reject recommendations "
                "and when you log outcomes."
            )
        else:
            for lesson in lessons:
                confidence = int(float(lesson.get("confidence", 0.5)) * 100)
                lesson_type = lesson.get("lesson_type", "preference")

                type_icons = {
                    "preference":    "💬",
                    "outcome":       "✅",
                    "failure":       "❌",
                    "threshold":     "📊",
                    "pattern":       "🔄",
                    "false_positive": "⚠️",
                }
                icon = type_icons.get(lesson_type, "💡")

                with st.expander(
                    f"{icon} [{lesson_type.upper()}] {lesson['lesson'][:80]}...",
                    expanded=False,
                ):
                    st.markdown(f"**Lesson ID:** `{lesson['lesson_id']}`")
                    st.markdown(f"**Full Lesson:** {lesson['lesson']}")
                    st.markdown(f"**Confidence:** {confidence}%")
                    st.markdown(f"**Reinforced:** {lesson.get('times_reinforced', 1)} time(s)")
                    st.markdown(f"**Learned:** {lesson.get('created_at', '')}")
                    if lesson.get("applies_to_signal_type"):
                        st.markdown(f"**Applies to:** `{lesson['applies_to_signal_type']}`")

    # ── Tab 4: Weekly Report ──────────────────────────────────────────────────
    with ci_tab4:
        st.markdown("### 📊 Weekly Improvement Report")

        summary = get_improvement_summary(DB_PATH)
        by_status = summary.get("by_status", {})

        st.markdown(f"**Project:** {summary.get('project', '')}")
        st.markdown(f"**Report Date:** {date.today()}")
        st.markdown(f"**Last Scan:** {summary.get('last_scan_at', 'Never')}")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Recommendation Status Breakdown:**")
            for status_key, count in by_status.items():
                color = STATUS_COLORS.get(status_key, "#6b7280")
                st.markdown(
                    f"{_color_badge(status_key, color)} **{count}**",
                    unsafe_allow_html=True,
                )

        with col2:
            st.markdown("**Performance Metrics:**")
            st.metric("Implemented", summary.get("total_implemented", 0))
            st.metric("Success Rate", summary.get("implementation_success_rate", "N/A"))
            st.metric("Lessons in Memory", summary.get("lessons_learned_count", 0))

        st.divider()

        pending = summary.get("pending_approvals", 0)
        if pending > 0:
            st.warning(
                f"⏳ **{pending} recommendations** are waiting for your review. "
                f"Go to the Recommendations tab to approve or reject them."
            )
        else:
            st.success("✅ All recommendations have been reviewed. Run a new scan for fresh insights.")
