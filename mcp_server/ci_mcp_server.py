# mcp_server/ci_mcp_server.py
#
# PURPOSE:
#   The MCP server for the Continuous Improvement Agent.
#   This is what Claude Desktop connects to.
#   Each @mcp.tool() function becomes a tool Claude can call.
#
# TOOLS IN THIS SERVER (8 tools):
#   1. run_improvement_scan         — collect signals and generate recommendations
#   2. get_pending_recommendations  — see recommendations waiting for your decision
#   3. approve_recommendation       — approve a recommendation (creates action item)
#   4. reject_recommendation        — reject a recommendation (saves lesson)
#   5. log_outcome                  — record what happened after implementation
#   6. get_improvement_summary      — high-level dashboard of CI Agent performance
#   7. get_lessons_learned          — see what the agent has learned so far
#   8. get_weekly_report            — full weekly improvement briefing
#
# HOW TO RUN:
#   cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
#   python mcp_server\ci_mcp_server.py
#
# HOW TO ADD TO CLAUDE DESKTOP:
#   Add this to claude_desktop_config.json alongside your other agents:
#
#   "ci-agent": {
#     "command": "C:\\Users\\preet\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
#     "args": ["C:\\Users\\preet\\Documents\\AI Work\\supply_chain_mcp_project\\mcp_server\\ci_mcp_server.py"],
#     "env": {
#       "PYTHONPATH": "C:\\Users\\preet\\Documents\\AI Work\\supply_chain_mcp_project\\src"
#     }
#   }

import sqlite3
import json
from datetime import datetime, date
from mcp.server.fastmcp import FastMCP

from supply_chain.ci_signal_detector import run_full_signal_scan, DB_PATH
from supply_chain.ci_recommendation_generator import generate_all_recommendations
from supply_chain.ci_learning_engine import (
    log_outcome as _log_outcome,
    record_approval_decision,
    create_action_item_from_recommendation,
    get_improvement_summary as _get_improvement_summary,
    get_pattern_learning_report,
    _connect,
)

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))
from ci_project_config import PROJECT_CONFIG

mcp = FastMCP("ci-agent")

TODAY = date.today()


# ─── HELPER: save signals to database ────────────────────────────────────────

def _save_signals_to_db(signals: list, db_path: str = DB_PATH) -> int:
    """
    Saves a list of signal dicts to the ci_signals table.
    Returns the count of signals saved.

    We use INSERT OR IGNORE to avoid duplicate errors if a signal_id
    already exists (which shouldn't happen with UUIDs, but is safe practice).
    """
    if not signals:
        return 0

    conn = _connect(db_path)
    cursor = conn.cursor()
    saved = 0

    for sig in signals:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO ci_signals (
                    signal_id, project_name, signal_type, domain,
                    title, description, evidence_json, frequency,
                    affected_records, severity, detected_at, last_seen_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sig["signal_id"],
                sig["project_name"],
                sig["signal_type"],
                sig["domain"],
                sig["title"],
                sig["description"],
                sig.get("evidence_json", "[]"),
                sig["frequency"],
                sig["affected_records"],
                sig["severity"],
                sig["detected_at"],
                sig["last_seen_at"],
                sig["status"],
            ))
            saved += 1
        except Exception as e:
            print(f"[ci_mcp_server] Warning: Could not save signal {sig.get('signal_id', 'unknown')}: {e}")

    conn.commit()
    conn.close()
    return saved


def _save_recommendations_to_db(recs: list, db_path: str = DB_PATH) -> int:
    """
    Saves a list of recommendation dicts to the ci_recommendations table.
    Returns the count saved.
    """
    if not recs:
        return 0

    conn = _connect(db_path)
    cursor = conn.cursor()
    saved = 0

    for rec in recs:
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
                rec["recommendation_id"],
                rec["project_name"],
                rec.get("signal_id", ""),
                rec["title"],
                rec.get("summary", ""),
                rec.get("evidence_json", "[]"),
                rec.get("root_cause_hypothesis", ""),
                rec["recommended_action"],
                rec.get("expected_benefit", ""),
                rec.get("impact_score", 5),
                rec.get("effort_score", 5),
                rec.get("risk_score", 5),
                rec.get("priority", "medium"),
                rec.get("confidence", 0.65),
                rec.get("requires_human_approval", 1),
                rec.get("approval_reason", ""),
                rec.get("suggested_owner", ""),
                rec.get("next_steps_json", "[]"),
                rec.get("rollback_notes", ""),
                rec.get("status", "new"),
                rec.get("created_at", datetime.now().isoformat()),
                rec.get("updated_at", datetime.now().isoformat()),
            ))
            saved += 1
        except Exception as e:
            print(f"[ci_mcp_server] Warning: Could not save recommendation: {e}")

    conn.commit()
    conn.close()
    return saved


def _save_approval_requests_to_db(recs: list, db_path: str = DB_PATH) -> int:
    """
    Creates approval request records for any recommendations that need approval.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()
    saved = 0

    for rec in recs:
        if rec.get("requires_human_approval", 1) == 1:
            import uuid
            apr_id = f"APR-{uuid.uuid4().hex[:6].upper()}"
            now = datetime.now().isoformat(sep=" ", timespec="seconds")

            # Build a clear question for the human reviewer.
            question = (
                f"Should I proceed with this improvement recommendation?\n\n"
                f"TITLE: {rec['title']}\n\n"
                f"RECOMMENDED ACTION:\n{rec['recommended_action']}\n\n"
                f"EXPECTED BENEFIT: {rec.get('expected_benefit', 'Not specified')}\n\n"
                f"RISK LEVEL: {rec.get('risk_score', 5)}/10 — "
                f"Approval reason: {rec.get('approval_reason', 'Risk threshold met.')}"
            )

            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO ci_approval_requests (
                        approval_id, recommendation_id, project_name,
                        question_for_human, context_json, risk_level,
                        decision, requested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    apr_id,
                    rec["recommendation_id"],
                    rec["project_name"],
                    question,
                    rec.get("evidence_json", "{}"),
                    "HIGH" if rec.get("risk_score", 5) >= 7 else "MEDIUM",
                    "pending",
                    now,
                ))
                saved += 1
            except Exception as e:
                print(f"[ci_mcp_server] Warning: Could not save approval request: {e}")

    conn.commit()
    conn.close()
    return saved


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS
# Each function below is a tool Claude Desktop can call.
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_improvement_scan() -> dict:
    """
    Use this tool to run a full Continuous Improvement scan across all supply chain domains.

    The agent will:
    1. Scan all shipment, inventory, freight, and warehouse data
    2. Detect patterns, anomalies, and improvement opportunities
    3. Generate specific, actionable recommendations
    4. Save everything to the database
    5. Return a summary of what was found

    Use this when the user says:
    - "Run the improvement scan"
    - "What improvements can we make?"
    - "Scan for problems and suggest fixes"
    - "Run the CI agent"
    - "What patterns has the agent found?"
    - "Start the continuous improvement analysis"
    """
    run_id = f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    started = datetime.now().isoformat(sep=" ", timespec="seconds")

    # ── Step 1: Collect signals ───────────────────────────────────────────────
    # The signal detector scans all four data domains for patterns.
    signals = run_full_signal_scan(DB_PATH)

    # ── Step 2: Save signals ──────────────────────────────────────────────────
    saved_signals = _save_signals_to_db(signals)

    # ── Step 3: Generate recommendations ─────────────────────────────────────
    # Convert each signal into a structured recommendation.
    recommendations = generate_all_recommendations(signals)

    # ── Step 4: Save recommendations ─────────────────────────────────────────
    saved_recs = _save_recommendations_to_db(recommendations)

    # ── Step 5: Create approval requests ─────────────────────────────────────
    # For every recommendation that needs human review, create a request.
    saved_approvals = _save_approval_requests_to_db(recommendations)

    # ── Step 6: Log this run in the audit trail ───────────────────────────────
    conn = _connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO ci_agent_run_log (
            run_id, project_name, run_type,
            signals_found, recommendations_generated, approvals_requested,
            started_at, completed_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        PROJECT_CONFIG["project_name"],
        "FULL_SCAN",
        saved_signals,
        saved_recs,
        saved_approvals,
        started,
        datetime.now().isoformat(sep=" ", timespec="seconds"),
        "completed",
    ))
    conn.commit()
    conn.close()

    # ── Step 7: Build the response ────────────────────────────────────────────
    auto_logged = [r for r in recommendations if r.get("requires_human_approval", 1) == 0]
    needs_approval = [r for r in recommendations if r.get("requires_human_approval", 1) == 1]

    # Build a summary of what was found — highest priority items first.
    top_recs_summary = []
    for rec in recommendations[:3]:
        top_recs_summary.append({
            "id":       rec["recommendation_id"],
            "priority": rec["priority"],
            "title":    rec["title"],
            "owner":    rec["suggested_owner"],
            "needs_approval": rec.get("requires_human_approval", 1) == 1,
        })

    return {
        "run_id":                    run_id,
        "scan_completed_at":         datetime.now().isoformat(sep=" ", timespec="seconds"),
        "signals_found":             len(signals),
        "recommendations_generated": len(recommendations),
        "auto_logged":               len(auto_logged),
        "pending_your_approval":     len(needs_approval),
        "top_recommendations":       top_recs_summary,
        "next_step": (
            f"Review {len(needs_approval)} recommendations waiting for your approval. "
            f"Use get_pending_recommendations() to see them."
        ) if needs_approval else (
            "All recommendations have been auto-logged. Use get_improvement_summary() to see the full picture."
        ),
    }


@mcp.tool()
def get_pending_recommendations() -> list:
    """
    Use this tool to see all improvement recommendations that are waiting for your decision.

    Returns all recommendations with status 'new', 'pending_approval', or 'approved'
    that have not yet been acted on. Each recommendation includes:
    - What the agent found
    - What action it recommends
    - Why it needs your approval
    - Impact, effort, and risk scores
    - Confidence level

    Use this when the user says:
    - "Show me the pending recommendations"
    - "What does the CI agent want me to approve?"
    - "What improvements are waiting for me?"
    - "Show me the improvement backlog"
    - "What should I review today from the improvement agent?"
    """
    conn = _connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch all recommendations that need attention.
    cursor.execute("""
        SELECT
            r.recommendation_id,
            r.title,
            r.summary,
            r.recommended_action,
            r.expected_benefit,
            r.impact_score,
            r.effort_score,
            r.risk_score,
            r.priority,
            r.confidence,
            r.requires_human_approval,
            r.approval_reason,
            r.suggested_owner,
            r.status,
            r.created_at,
            a.question_for_human,
            a.decision as approval_status
        FROM ci_recommendations r
        LEFT JOIN ci_approval_requests a ON r.recommendation_id = a.recommendation_id
        WHERE r.project_name = ?
          AND r.status IN ('new', 'pending_approval')
        ORDER BY r.impact_score DESC, r.created_at DESC
    """, (PROJECT_CONFIG["project_name"],))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return [{"message": "No pending recommendations. Run run_improvement_scan() to generate new ones."}]

    results = []
    for row in rows:
        r = dict(row)
        results.append({
            "recommendation_id":    r["recommendation_id"],
            "priority":             r["priority"],
            "title":                r["title"],
            "summary":              r["summary"],
            "recommended_action":   r["recommended_action"],
            "expected_benefit":     r["expected_benefit"],
            "impact_score":         f"{r['impact_score']}/10",
            "effort_score":         f"{r['effort_score']}/10 (lower = easier)",
            "risk_score":           f"{r['risk_score']}/10 (lower = safer)",
            "confidence":           f"{int(float(r['confidence']) * 100)}%",
            "suggested_owner":      r["suggested_owner"],
            "requires_approval":    bool(r["requires_human_approval"]),
            "approval_reason":      r["approval_reason"],
            "question_for_you":     r.get("question_for_human", ""),
            "status":               r["status"],
            "detected_at":          r["created_at"],
        })

    return results


@mcp.tool()
def approve_recommendation(recommendation_id: str, reason: str = "Approved") -> dict:
    """
    Use this tool to approve a specific improvement recommendation.

    When you approve a recommendation, the agent will:
    1. Update the recommendation status to 'approved'
    2. Create a concrete action item in the work queue
    3. Assign it to the suggested owner

    Input:
      recommendation_id — the CI-XXXXXX ID from get_pending_recommendations()
      reason            — optional note about why you approved it

    Use this when the user says:
    - "Approve recommendation CI-A3F2B1"
    - "Yes, proceed with CI-XXXXXX"
    - "I approve that recommendation"
    - "Go ahead with the freight hold improvement"
    - "Mark CI-XXXXXX as approved"
    """
    # Record the approval decision.
    result = record_approval_decision(
        recommendation_id=recommendation_id,
        decision="approved",
        decision_reason=reason,
        db_path=DB_PATH,
    )

    if "error" in result:
        return result

    # Create the concrete action item.
    action_result = create_action_item_from_recommendation(recommendation_id, DB_PATH)

    return {
        "recommendation_id":  recommendation_id,
        "decision":           "approved",
        "action_item_created": action_result.get("action_id", ""),
        "action_title":       action_result.get("title", ""),
        "assigned_to":        action_result.get("suggested_owner", ""),
        "priority":           action_result.get("priority", ""),
        "message": (
            f"Recommendation {recommendation_id} approved. "
            f"Action item {action_result.get('action_id', '')} created and assigned to "
            f"{action_result.get('suggested_owner', 'the team')}."
        ),
    }


@mcp.tool()
def reject_recommendation(recommendation_id: str, reason: str) -> dict:
    """
    Use this tool to reject a specific improvement recommendation.

    When you reject a recommendation, the agent will:
    1. Update the recommendation status to 'rejected'
    2. Save a lesson explaining why it was rejected
    3. Use this lesson to avoid making similar suggestions in the future

    Input:
      recommendation_id — the CI-XXXXXX ID from get_pending_recommendations()
      reason            — REQUIRED: explain why this recommendation is being rejected.
                          This is essential for the agent to learn from.

    Use this when the user says:
    - "Reject recommendation CI-A3F2B1 because..."
    - "No, don't do CI-XXXXXX — the reason is..."
    - "Decline this recommendation — it's not applicable right now"
    - "Mark CI-XXXXXX as rejected"
    """
    if not reason or len(reason.strip()) < 5:
        return {
            "error": "A rejection reason is required. Please explain why this recommendation is not appropriate. The agent uses this to learn and avoid similar suggestions in the future."
        }

    result = record_approval_decision(
        recommendation_id=recommendation_id,
        decision="rejected",
        decision_reason=reason,
        db_path=DB_PATH,
    )

    return {
        "recommendation_id": recommendation_id,
        "decision":          "rejected",
        "lesson_saved":      result.get("lesson_saved", ""),
        "message": (
            f"Recommendation {recommendation_id} rejected. "
            f"Reason recorded: '{reason}'. "
            f"A lesson has been saved so the agent avoids similar suggestions in the future."
        ),
    }


@mcp.tool()
def log_outcome(
    recommendation_id: str,
    status: str,
    what_happened: str,
    metric_before: str = "",
    metric_after: str = "",
) -> dict:
    """
    Use this tool to record what happened after you implemented a recommendation.

    This is how the agent learns whether its recommendations are actually working.
    The more outcomes you log, the smarter the agent becomes.

    Inputs:
      recommendation_id — the CI-XXXXXX ID of the recommendation you implemented
      status            — "implemented" (worked), "failed" (didn't work), or "partial"
      what_happened     — plain English description of the result
      metric_before     — optional: the number before you made the change
      metric_after      — optional: the number after you made the change

    Examples:
      recommendation_id = "CI-A3F2B1"
      status            = "implemented"
      what_happened     = "Contacted carrier. They reassigned driver. Orders shipped same day."
      metric_before     = "3 orders with CARRIER_DELAY"
      metric_after      = "0 orders with CARRIER_DELAY"

    Use this when the user says:
    - "Log the outcome for CI-A3F2B1 — it worked"
    - "Mark CI-XXXXXX as implemented — here's what happened"
    - "Record that CI-XXXXXX failed because..."
    - "The recommendation worked — delays went from 3 to 0"
    """
    result = _log_outcome(
        recommendation_id=recommendation_id,
        action_id="",
        status=status,
        measured_outcome=what_happened,
        metric_before=metric_before,
        metric_after=metric_after,
        recorded_by="user",
        db_path=DB_PATH,
    )

    return {
        "outcome_id":       result.get("outcome_id", ""),
        "recommendation_id": recommendation_id,
        "status":           status,
        "lesson_extracted": result.get("lesson_extracted", ""),
        "message":          result.get("message", "Outcome recorded."),
    }


@mcp.tool()
def get_improvement_summary() -> dict:
    """
    Use this tool to get a high-level dashboard of the Continuous Improvement Agent's activity.

    Returns:
    - Total recommendations generated
    - How many are pending, approved, rejected, implemented
    - Implementation success rate
    - How many lessons have been learned
    - How many action items are open

    Use this when the user says:
    - "How is the CI agent performing?"
    - "Give me the improvement summary"
    - "How many recommendations have been implemented?"
    - "What is the CI agent's track record?"
    - "Show me the improvement dashboard"
    - "How many improvements are pending?"
    """
    summary = _get_improvement_summary(DB_PATH)

    # Also get the most recent scan date.
    conn = _connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT started_at FROM ci_agent_run_log
        WHERE project_name = ?
        ORDER BY started_at DESC LIMIT 1
    """, (PROJECT_CONFIG["project_name"],))
    last_run = cursor.fetchone()
    conn.close()

    summary["last_scan_at"] = dict(last_run)["started_at"] if last_run else "Never"
    summary["project"] = PROJECT_CONFIG["project_name"]
    # learning_rules_fired_total is now populated by the new learning engine.

    return summary


@mcp.tool()
def get_lessons_learned() -> list:
    """
    Use this tool to see exactly what the CI Agent has learned from past decisions.

    For each signal/pattern type that has accumulated history, returns:
    - How many recommendations were generated, approved, rejected, deferred
    - Current confidence adjustment (e.g. -15% from 5 rejections)
    - Current impact adjustment (e.g. +1 from 10%+ metric improvement)
    - Which learning rules have fired and why
    - Overall learning status: NEUTRAL, SUPPRESSED, or HIGH_VALUE

    SUPPRESSED means: this pattern keeps getting rejected — the agent now
    scores it lower automatically until you approve one.

    HIGH_VALUE means: this pattern has produced measurable improvements —
    the agent now scores it higher to surface it more aggressively.

    Use this when the user says:
    - "What has the CI agent learned?"
    - "Show me the learning rules that have fired"
    - "Why is the agent no longer recommending X?"
    - "What patterns are marked as high value?"
    - "Show me confidence adjustments per pattern"
    - "Has the agent updated its scoring?"
    """
    report = get_pattern_learning_report(DB_PATH)

    if not report:
        return [{
            "message": (
                "No learning data yet. The agent learns when you approve, reject, "
                "or defer recommendations, and when you log outcomes. "
                "Run a scan and make some decisions to start building the agent's memory."
            )
        }]

    return report


@mcp.tool()
def get_weekly_report() -> dict:
    """
    Use this tool to generate a full weekly improvement report for the project.

    The report includes:
    - What the agent found this week (top signals)
    - What recommendations were generated
    - What decisions were made (approved/rejected/deferred)
    - What was implemented and with what result
    - What the agent learned
    - What needs attention next week

    Use this when the user says:
    - "Give me the weekly CI report"
    - "What happened in continuous improvement this week?"
    - "Weekly improvement summary"
    - "What should I share with the team about improvements?"
    - "Generate the improvement report"
    - "What is the state of the improvement backlog?"
    """
    conn = _connect(DB_PATH)
    cursor = conn.cursor()

    # Get recommendations from the past 7 days.
    cursor.execute("""
        SELECT recommendation_id, title, priority, status, suggested_owner, created_at
        FROM ci_recommendations
        WHERE project_name = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (PROJECT_CONFIG["project_name"],))
    recent_recs = [dict(r) for r in cursor.fetchall()]

    # Get outcomes from the past 7 days.
    cursor.execute("""
        SELECT outcome_id, recommendation_id, status, measured_outcome, recorded_at
        FROM ci_outcomes
        WHERE project_name = ?
        ORDER BY recorded_at DESC
        LIMIT 10
    """, (PROJECT_CONFIG["project_name"],))
    recent_outcomes = [dict(r) for r in cursor.fetchall()]

    # Get pending items.
    cursor.execute("""
        SELECT COUNT(*) as count FROM ci_recommendations
        WHERE project_name = ? AND status IN ('new', 'pending_approval')
    """, (PROJECT_CONFIG["project_name"],))
    pending_count = cursor.fetchone()["count"]

    # Get open action items.
    cursor.execute("""
        SELECT COUNT(*) as count FROM ci_action_items
        WHERE project_name = ? AND status = 'open'
    """, (PROJECT_CONFIG["project_name"],))
    open_actions = cursor.fetchone()["count"]

    conn.close()

    # Build the summary text.
    summary = _get_improvement_summary(DB_PATH)
    implemented = summary.get("total_implemented", 0)
    total_recs = summary.get("total_recommendations", 0)

    briefing_parts = []
    if pending_count > 0:
        briefing_parts.append(f"{pending_count} recommendations are waiting for your review.")
    if open_actions > 0:
        briefing_parts.append(f"{open_actions} action items are open and in progress.")
    if implemented > 0:
        briefing_parts.append(f"{implemented} recommendations have been successfully implemented.")
    if not briefing_parts:
        briefing_parts.append("No active CI items this week. Run a scan to generate new recommendations.")

    return {
        "report_date":             str(date.today()),
        "project":                 PROJECT_CONFIG["project_name"],
        "weekly_briefing":         " ".join(briefing_parts),
        "total_recommendations":   total_recs,
        "pending_your_review":     pending_count,
        "open_action_items":       open_actions,
        "implemented_this_cycle":  implemented,
        "success_rate":            summary.get("implementation_success_rate", "N/A"),
        "lessons_in_memory":       summary.get("lessons_learned_count", 0),
        "recent_recommendations":  recent_recs[:5],
        "recent_outcomes":         recent_outcomes[:3],
        "focus_next_week": (
            f"Review and decide on {pending_count} pending recommendations. "
            f"Complete {open_actions} open action items."
        ) if pending_count > 0 or open_actions > 0 else (
            "Run a new scan to find the next round of improvement opportunities."
        ),
    }


if __name__ == "__main__":
    mcp.run()
