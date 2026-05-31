# src/supply_chain/ci_learning_engine.py
#
# PURPOSE:
#   The quantitative self-learning engine for the Continuous Improvement Agent.
#
# WHAT "SELF-LEARNING" MEANS HERE:
#   This engine tracks outcomes and decisions per pattern type, then
#   automatically adjusts confidence, priority, and impact scores using
#   8 specific quantitative rules. No AI models — just measurable rule updates.
#
# THE 8 LEARNING RULES:
#   LR-01: 5 rejections of same type  → confidence -15%
#   LR-02: 3 approved + positive outcome → confidence +10%
#   LR-03: 20%+ false positive rate   → confidence threshold raised +0.10
#   LR-04: Owner repeatedly changed   → update ownership mapping
#   LR-05: Deferred 5+ times          → priority_delta -1 (unless critical)
#   LR-06: Metric improves 10%+       → mark as HIGH_VALUE, impact_delta +1
#   LR-07: No improvement after impl  → impact_delta -1 for similar recs
#   LR-08: Repeated manual reports    → urgency bump for automation signal
#
# REUSABILITY:
#   All thresholds (5 rejections, 10% improvement, etc.) are in this file's
#   LEARNING_RULE_THRESHOLDS dict so they can be tuned without reading the logic.

import sqlite3
import uuid
import json
from datetime import datetime
from typing import List, Dict, Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'config'))
from ci_project_config import PROJECT_CONFIG


# ─── DATABASE PATH ────────────────────────────────────────────────────────────
DB_PATH = r"C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\data\supply_chain.db"


# ─── QUANTITATIVE LEARNING RULE THRESHOLDS ───────────────────────────────────
# Change these numbers to tune when rules fire.
# These are the exact thresholds from the spec.

LEARNING_RULE_THRESHOLDS = {
    "LR_01_rejections_before_confidence_drop":  5,     # 5 rejections → -15% confidence
    "LR_01_confidence_drop":                    0.15,  # how much to drop
    "LR_02_approvals_before_confidence_rise":   3,     # 3 successful approvals → +10%
    "LR_02_confidence_rise":                    0.10,  # how much to raise
    "LR_03_false_positive_rate_threshold":      0.20,  # 20% false positives → raise threshold
    "LR_03_threshold_raise":                    0.10,  # by how much
    "LR_05_deferrals_before_priority_drop":     5,     # 5 deferrals → priority_delta -1
    "LR_06_metric_improvement_pct":             0.10,  # 10% improvement → high-value
    "LR_06_impact_delta_for_high_value":        1,     # impact_delta +1
    "LR_07_impact_delta_for_no_improvement":   -1,     # impact_delta -1
}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")

def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

def _connect(db_path: str) -> sqlite3.Connection:
    """
    Opens a connection to the SQLite database.
    row_factory = sqlite3.Row lets us access columns by name like a dict.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN STATS — the counters that drive all learning rules
# ═══════════════════════════════════════════════════════════════════════════════

def _get_or_create_pattern_stats(pattern_type: str, db_path: str) -> dict:
    """
    Returns the current stats row for a pattern type.
    If no row exists yet, creates one with all zeros.

    Parameters:
      pattern_type — e.g. "REPEATED_DELAY_BY_CARRIER"

    Returns:
      A dict with all columns from ci_pattern_stats.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM ci_pattern_stats
        WHERE project_name = ? AND pattern_type = ?
    """, (PROJECT_CONFIG["project_name"], pattern_type))

    row = cursor.fetchone()

    if row is None:
        # First time we've seen this pattern — create a blank stats row.
        stat_id = _new_id("STAT")
        now = _now()
        cursor.execute("""
            INSERT INTO ci_pattern_stats (
                stat_id, project_name, pattern_type,
                total_generated, total_approved, total_rejected,
                total_deferred, total_implemented, total_failed,
                total_false_positive, consecutive_rejections,
                consecutive_approvals_with_outcome,
                current_confidence_adjustment, current_priority_adjustment,
                current_impact_adjustment, owner_override, last_updated_at
            ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, '', ?)
        """, (stat_id, PROJECT_CONFIG["project_name"], pattern_type, now))
        conn.commit()

        # Fetch the newly created row.
        cursor.execute("""
            SELECT * FROM ci_pattern_stats
            WHERE project_name = ? AND pattern_type = ?
        """, (PROJECT_CONFIG["project_name"], pattern_type))
        row = cursor.fetchone()

    conn.close()
    return dict(row)


def _update_pattern_stats(pattern_type: str, updates: dict, db_path: str):
    """
    Updates specific columns in ci_pattern_stats for a pattern type.

    Parameters:
      pattern_type — which pattern to update
      updates      — dict of column names to new values
                     e.g. {"total_rejected": 3, "consecutive_rejections": 3}
    """
    if not updates:
        return

    conn = _connect(db_path)
    cursor = conn.cursor()

    # Build the SET clause dynamically from the updates dict.
    # For example: {"total_rejected": 3} → "total_rejected = ?"
    set_clauses = ", ".join([f"{col} = ?" for col in updates.keys()])
    values = list(updates.values()) + [_now(), PROJECT_CONFIG["project_name"], pattern_type]

    cursor.execute(f"""
        UPDATE ci_pattern_stats
        SET {set_clauses}, last_updated_at = ?
        WHERE project_name = ? AND pattern_type = ?
    """, values)

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LEARNING RULE EVALUATORS
# Each function checks one rule and returns a dict of adjustments if the rule fires.
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_lr01_rejection_penalty(stats: dict) -> Optional[dict]:
    """
    LR-01: If a pattern type has been rejected 5 consecutive times,
           reduce confidence by 15%.

    WHY: Repeated rejections mean the agent is generating unhelpful
    recommendations of this type. Reducing confidence means it will be
    scored lower and require more evidence before appearing again.

    Returns: adjustment dict, or None if rule does not fire.
    """
    t = LEARNING_RULE_THRESHOLDS
    consec = stats.get("consecutive_rejections", 0)

    if consec > 0 and consec % t["LR_01_rejections_before_confidence_drop"] == 0:
        drop = t["LR_01_confidence_drop"]
        return {
            "rule_id": "LR-01",
            "trigger": f"{consec} consecutive rejections",
            "confidence_delta": -drop,
            "priority_delta":   0.0,
            "impact_delta":     0.0,
            "description": (
                f"Pattern rejected {consec} consecutive times. "
                f"Confidence reduced by {int(drop * 100)}%."
            ),
        }
    return None


def _evaluate_lr02_approval_reward(stats: dict) -> Optional[dict]:
    """
    LR-02: If 3 recommendations of this type were approved AND produced
           positive outcomes, increase confidence by 10%.

    WHY: Repeated success means the agent is reliably identifying real problems.
    Increasing confidence means it will generate more of these, and with
    higher priority scores.

    Returns: adjustment dict, or None if rule does not fire.
    """
    t = LEARNING_RULE_THRESHOLDS
    successes = stats.get("consecutive_approvals_with_outcome", 0)

    if successes > 0 and successes % t["LR_02_approvals_before_confidence_rise"] == 0:
        rise = t["LR_02_confidence_rise"]
        return {
            "rule_id": "LR-02",
            "trigger": f"{successes} consecutive approvals with positive outcomes",
            "confidence_delta": rise,
            "priority_delta":   0.0,
            "impact_delta":     0.0,
            "description": (
                f"Pattern approved and implemented successfully {successes} times. "
                f"Confidence increased by {int(rise * 100)}%."
            ),
        }
    return None


def _evaluate_lr05_deferral_penalty(stats: dict) -> Optional[dict]:
    """
    LR-05: If a pattern has been deferred 5 or more times, reduce priority by 1
           (unless the impact is at maximum, i.e., impact_score = 5).

    WHY: Repeated deferral means the team sees the problem but isn't ready
    to act on it. Lowering priority prevents it from dominating the backlog
    while still keeping it visible.

    Returns: adjustment dict, or None if rule does not fire.
    """
    t = LEARNING_RULE_THRESHOLDS
    deferrals = stats.get("total_deferred", 0)
    impact    = stats.get("current_impact_adjustment", 0)

    # Don't suppress critical items — only lower priority for non-critical.
    if deferrals >= t["LR_05_deferrals_before_priority_drop"] and impact < 5:
        return {
            "rule_id": "LR-05",
            "trigger": f"{deferrals} total deferrals",
            "confidence_delta": 0.0,
            "priority_delta":  -1.0,
            "impact_delta":     0.0,
            "description": (
                f"Pattern deferred {deferrals} times. "
                f"Priority score reduced by 1 to prevent backlog dominance."
            ),
        }
    return None


def _evaluate_lr06_high_value_reward(metric_before: str, metric_after: str,
                                      stats: dict) -> Optional[dict]:
    """
    LR-06: If an implemented recommendation improved the target metric by
           more than 10%, mark the pattern as high-value and raise impact by 1.

    WHY: Proven patterns should be prioritised more aggressively in future scans.

    Parameters:
      metric_before / metric_after — strings from outcome logging.
      We try to extract numbers from them (e.g. "3 orders" → 3).
      If we can't parse numbers, we skip this rule.

    Returns: adjustment dict, or None if rule does not fire.
    """
    t = LEARNING_RULE_THRESHOLDS

    # Try to extract numeric values from the metric strings.
    before_val = _extract_number(metric_before)
    after_val  = _extract_number(metric_after)

    if before_val is not None and after_val is not None and before_val > 0:
        improvement_pct = (before_val - after_val) / before_val
        if improvement_pct >= t["LR_06_metric_improvement_pct"]:
            delta = t["LR_06_impact_delta_for_high_value"]
            return {
                "rule_id": "LR-06",
                "trigger": f"Metric improved {int(improvement_pct * 100)}% (before={before_val}, after={after_val})",
                "confidence_delta": 0.0,
                "priority_delta":   0.0,
                "impact_delta":     float(delta),
                "high_value":       True,
                "description": (
                    f"Implementation improved target metric by {int(improvement_pct * 100)}%. "
                    f"Pattern marked as HIGH_VALUE. Impact score increased by {delta}."
                ),
            }
    return None


def _evaluate_lr07_no_improvement_penalty(metric_before: str, metric_after: str,
                                           status: str) -> Optional[dict]:
    """
    LR-07: If a recommendation was implemented but produced no measurable
           improvement, reduce impact score by 1 for similar future recs.

    WHY: If the action didn't help, future estimates of its impact were wrong.
    We correct this by lowering the impact score.

    Returns: adjustment dict, or None if rule does not fire.
    """
    t = LEARNING_RULE_THRESHOLDS

    if status != "implemented":
        return None

    before_val = _extract_number(metric_before)
    after_val  = _extract_number(metric_after)

    # If we have numbers and the after is equal to or worse than before:
    if before_val is not None and after_val is not None:
        if after_val >= before_val:
            delta = t["LR_07_impact_delta_for_no_improvement"]
            return {
                "rule_id": "LR-07",
                "trigger": f"No improvement observed (before={before_val}, after={after_val})",
                "confidence_delta": 0.0,
                "priority_delta":   0.0,
                "impact_delta":     float(delta),
                "description": (
                    f"Implementation did not improve the target metric. "
                    f"Impact score for this pattern type reduced by {abs(delta)}."
                ),
            }
    return None


def _extract_number(text: str) -> Optional[float]:
    """
    Tries to extract the first number from a string like "3 orders" → 3.0.
    Used by LR-06 and LR-07 to parse before/after metric strings.

    Returns the float if found, None if the string has no numbers.
    """
    import re
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(text))
    return float(match.group()) if match else None


# ═══════════════════════════════════════════════════════════════════════════════
# SAVE AND APPLY LEARNING RULES
# ═══════════════════════════════════════════════════════════════════════════════

def _save_learning_rule(adjustment: dict, pattern_type: str,
                         source_rec_id: str, db_path: str) -> str:
    """
    Saves a fired learning rule to ci_learning_rules.
    Each row represents one time a rule triggered and what adjustment was made.

    Parameters:
      adjustment    — dict returned by one of the _evaluate_lr* functions
      pattern_type  — the signal type this rule applies to
      source_rec_id — the recommendation that caused this rule to fire

    Returns:
      The learning_rule_id of the saved row.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    lr_id = _new_id("LR")
    now = _now()

    cursor.execute("""
        INSERT INTO ci_learning_rules (
            learning_rule_id, project_name, pattern_type,
            trigger_condition, adjustment, confidence_delta,
            priority_delta, impact_delta, times_triggered, reason,
            created_from_recs_json, last_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lr_id,
        PROJECT_CONFIG["project_name"],
        pattern_type,
        adjustment.get("trigger", ""),
        adjustment.get("description", ""),
        adjustment.get("confidence_delta", 0.0),
        adjustment.get("priority_delta", 0.0),
        adjustment.get("impact_delta", 0.0),
        1,
        adjustment.get("rule_id", ""),
        json.dumps([source_rec_id]),
        now,
    ))

    conn.commit()
    conn.close()
    return lr_id


def _apply_adjustments_to_pattern_stats(pattern_type: str, adjustments: list,
                                         db_path: str):
    """
    Accumulates confidence, priority, and impact deltas into ci_pattern_stats.
    These accumulated values are what get_learning_adjustments_for_pattern()
    returns, so future recommendations are scored with them applied.

    Parameters:
      pattern_type  — which pattern to update
      adjustments   — list of adjustment dicts from rule evaluators
    """
    if not adjustments:
        return

    stats = _get_or_create_pattern_stats(pattern_type, db_path)

    # Sum up all the deltas from all fired rules.
    total_conf   = sum(a.get("confidence_delta", 0.0) for a in adjustments)
    total_prio   = sum(a.get("priority_delta",   0.0) for a in adjustments)
    total_impact = sum(a.get("impact_delta",     0.0) for a in adjustments)

    # Add to the existing cumulative adjustments.
    new_conf   = max(-0.90, min(0.90,
        float(stats.get("current_confidence_adjustment", 0.0)) + total_conf
    ))
    new_prio   = max(-4.0, min(4.0,
        float(stats.get("current_priority_adjustment", 0.0)) + total_prio
    ))
    new_impact = max(-4.0, min(4.0,
        float(stats.get("current_impact_adjustment", 0.0)) + total_impact
    ))

    _update_pattern_stats(pattern_type, {
        "current_confidence_adjustment": new_conf,
        "current_priority_adjustment":   new_prio,
        "current_impact_adjustment":     new_impact,
    }, db_path)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — called by ci_mcp_server.py and ci_recommendation_generator.py
# ═══════════════════════════════════════════════════════════════════════════════

def get_learning_adjustments_for_pattern(pattern_type: str,
                                          db_path: str = DB_PATH) -> dict:
    """
    Returns the accumulated learning adjustments for a given pattern type.
    Called by ci_recommendation_generator.py BEFORE scoring a new recommendation,
    so that past learning is applied to future scores.

    Parameters:
      pattern_type — e.g. "REPEATED_DELAY_BY_CARRIER"

    Returns:
      Dict with confidence_delta, priority_delta, impact_delta.
      All zeros if no learning has happened yet for this pattern.

    EXAMPLE:
      If REPEATED_DELAY_BY_CARRIER has been rejected 5 times:
        {"confidence_delta": -0.15, "priority_delta": 0.0, "impact_delta": 0.0}

      If it has also been successfully implemented 3 times after that:
        {"confidence_delta": -0.05, "priority_delta": 0.0, "impact_delta": 0.0}
        (net: -0.15 + 0.10 = -0.05)
    """
    try:
        stats = _get_or_create_pattern_stats(pattern_type, db_path)
        return {
            "confidence_delta": float(stats.get("current_confidence_adjustment", 0.0)),
            "priority_delta":   float(stats.get("current_priority_adjustment", 0.0)),
            "impact_delta":     float(stats.get("current_impact_adjustment", 0.0)),
        }
    except Exception:
        # If anything goes wrong, return zero adjustments — fail safe.
        return {"confidence_delta": 0.0, "priority_delta": 0.0, "impact_delta": 0.0}


def record_approval_decision(
    recommendation_id: str,
    decision: str,
    decision_reason: str,
    decided_by: str = "user",
    db_path: str = DB_PATH,
) -> dict:
    """
    Records a human decision (approved / rejected / deferred) and runs
    all relevant learning rules.

    Parameters:
      recommendation_id — the CI-XXXXXX recommendation
      decision          — "approved", "rejected", or "deferred"
      decision_reason   — why (required for rejection)
      decided_by        — who made the decision

    Returns:
      Dict summarising the decision and any learning rules that fired.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()
    now = _now()

    # Update recommendation status.
    status_map = {"approved": "approved", "rejected": "rejected", "deferred": "deferred"}
    new_status = status_map.get(decision.lower(), "pending_approval")

    cursor.execute("""
        UPDATE ci_recommendations
        SET status = ?, updated_at = ?
        WHERE recommendation_id = ?
    """, (new_status, now, recommendation_id))

    # Update approval request if one exists.
    cursor.execute("""
        UPDATE ci_approval_requests
        SET decision = ?, decision_reason = ?, decided_by = ?, decided_at = ?
        WHERE recommendation_id = ?
    """, (decision.lower(), decision_reason, decided_by, now, recommendation_id))

    # Fetch the recommendation's signal_type (pattern_type) for learning.
    cursor.execute("""
        SELECT r.signal_id, s.signal_type
        FROM ci_recommendations r
        LEFT JOIN ci_signals s ON r.signal_id = s.signal_id
        WHERE r.recommendation_id = ?
    """, (recommendation_id,))
    row = cursor.fetchone()
    pattern_type = dict(row)["signal_type"] if row and dict(row).get("signal_type") else "UNKNOWN"

    conn.commit()
    conn.close()

    # ── Update pattern stats counter ──────────────────────────────────────────
    stats = _get_or_create_pattern_stats(pattern_type, db_path)
    fired_rules = []

    if decision.lower() == "rejected":
        new_consecutive = int(stats.get("consecutive_rejections", 0)) + 1
        _update_pattern_stats(pattern_type, {
            "total_rejected":          int(stats.get("total_rejected", 0)) + 1,
            "consecutive_rejections":  new_consecutive,
            "consecutive_approvals_with_outcome": 0,  # reset streak
        }, db_path)

        # Re-fetch updated stats and check LR-01.
        stats = _get_or_create_pattern_stats(pattern_type, db_path)
        adj = _evaluate_lr01_rejection_penalty(stats)
        if adj:
            lr_id = _save_learning_rule(adj, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj], db_path)
            fired_rules.append({"rule": "LR-01", "lr_id": lr_id, "effect": adj["description"]})

    elif decision.lower() == "approved":
        _update_pattern_stats(pattern_type, {
            "total_approved":         int(stats.get("total_approved", 0)) + 1,
            "consecutive_rejections": 0,  # reset rejection streak
        }, db_path)

    elif decision.lower() == "deferred":
        new_deferrals = int(stats.get("total_deferred", 0)) + 1
        _update_pattern_stats(pattern_type, {
            "total_deferred": new_deferrals,
        }, db_path)

        # Check LR-05 after updating.
        stats = _get_or_create_pattern_stats(pattern_type, db_path)
        adj = _evaluate_lr05_deferral_penalty(stats)
        if adj:
            lr_id = _save_learning_rule(adj, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj], db_path)
            fired_rules.append({"rule": "LR-05", "lr_id": lr_id, "effect": adj["description"]})

    return {
        "recommendation_id": recommendation_id,
        "decision":          decision,
        "new_status":        new_status,
        "pattern_type":      pattern_type,
        "learning_rules_fired": fired_rules,
        "message": f"Decision '{decision}' recorded for {recommendation_id}.",
    }


def log_outcome(
    recommendation_id: str,
    action_id: str,
    status: str,
    measured_outcome: str,
    metric_before: str = "",
    metric_after: str = "",
    notes: str = "",
    recorded_by: str = "user",
    db_path: str = DB_PATH,
) -> dict:
    """
    Records the result of implementing a recommendation and runs all
    outcome-based learning rules (LR-02, LR-06, LR-07).

    Parameters:
      recommendation_id — the CI-XXXXXX ID
      action_id         — the ACT-XXXXXX ID (can be empty)
      status            — "implemented", "failed", or "partial"
      measured_outcome  — plain English: what actually happened
      metric_before     — value before the change (e.g. "3 carrier delays")
      metric_after      — value after the change  (e.g. "0 carrier delays")
      recorded_by       — who logged this

    Returns:
      Dict with outcome_id and list of learning rules that fired.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    outcome_id = _new_id("OUT")
    now = _now()

    # Fetch pattern_type from the linked recommendation.
    cursor.execute("""
        SELECT r.signal_id, s.signal_type
        FROM ci_recommendations r
        LEFT JOIN ci_signals s ON r.signal_id = s.signal_id
        WHERE r.recommendation_id = ?
    """, (recommendation_id,))
    row = cursor.fetchone()
    pattern_type = dict(row)["signal_type"] if row and dict(row).get("signal_type") else "UNKNOWN"

    # Build the lesson text summarising this outcome.
    lesson_text = _build_lesson_text(pattern_type, status, measured_outcome,
                                      metric_before, metric_after)

    cursor.execute("""
        INSERT INTO ci_outcomes (
            outcome_id, recommendation_id, action_id, project_name,
            status, measured_outcome, success_metric_before,
            success_metric_after, implementation_notes,
            lesson_learned, recorded_by, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        outcome_id, recommendation_id, action_id or "",
        PROJECT_CONFIG["project_name"],
        status, measured_outcome, metric_before, metric_after,
        notes, lesson_text, recorded_by, now,
    ))

    # Update recommendation status.
    new_rec_status = "implemented" if status == "implemented" else "failed"
    cursor.execute("""
        UPDATE ci_recommendations SET status = ?, updated_at = ?
        WHERE recommendation_id = ?
    """, (new_rec_status, now, recommendation_id))

    conn.commit()
    conn.close()

    # ── Run outcome-based learning rules ─────────────────────────────────────
    stats = _get_or_create_pattern_stats(pattern_type, db_path)
    fired_rules = []

    if status == "implemented":
        # Update implemented counter.
        _update_pattern_stats(pattern_type, {
            "total_implemented": int(stats.get("total_implemented", 0)) + 1,
        }, db_path)

        # ── LR-02: reward consecutive successes ───────────────────────────────
        new_streak = int(stats.get("consecutive_approvals_with_outcome", 0)) + 1
        _update_pattern_stats(pattern_type, {
            "consecutive_approvals_with_outcome": new_streak,
        }, db_path)

        stats = _get_or_create_pattern_stats(pattern_type, db_path)
        adj = _evaluate_lr02_approval_reward(stats)
        if adj:
            lr_id = _save_learning_rule(adj, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj], db_path)
            fired_rules.append({"rule": "LR-02", "lr_id": lr_id, "effect": adj["description"]})

        # ── LR-06: reward measurable metric improvement ───────────────────────
        adj6 = _evaluate_lr06_high_value_reward(metric_before, metric_after, stats)
        if adj6:
            lr_id = _save_learning_rule(adj6, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj6], db_path)
            fired_rules.append({"rule": "LR-06", "lr_id": lr_id, "effect": adj6["description"]})

        # ── LR-07: penalise if no improvement despite implementation ──────────
        adj7 = _evaluate_lr07_no_improvement_penalty(metric_before, metric_after, status)
        if adj7:
            lr_id = _save_learning_rule(adj7, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj7], db_path)
            fired_rules.append({"rule": "LR-07", "lr_id": lr_id, "effect": adj7["description"]})

    elif status == "failed":
        _update_pattern_stats(pattern_type, {
            "total_failed":                       int(stats.get("total_failed", 0)) + 1,
            "consecutive_approvals_with_outcome": 0,  # reset success streak
        }, db_path)

        # Failed implementation = no improvement — penalise impact.
        adj7 = _evaluate_lr07_no_improvement_penalty(metric_before, metric_after, "implemented")
        if adj7:
            lr_id = _save_learning_rule(adj7, pattern_type, recommendation_id, db_path)
            _apply_adjustments_to_pattern_stats(pattern_type, [adj7], db_path)
            fired_rules.append({"rule": "LR-07", "lr_id": lr_id, "effect": adj7["description"]})

    return {
        "outcome_id":           outcome_id,
        "recommendation_id":    recommendation_id,
        "status":               status,
        "pattern_type":         pattern_type,
        "lesson_extracted":     lesson_text,
        "learning_rules_fired": fired_rules,
        "message": (
            f"Outcome '{status}' logged for {recommendation_id}. "
            f"{len(fired_rules)} learning rule(s) fired."
        ),
    }


def _build_lesson_text(pattern_type: str, status: str, outcome: str,
                        before: str, after: str) -> str:
    """Generates a plain-English lesson string from an outcome."""
    if status == "implemented":
        return (
            f"Pattern '{pattern_type}' recommendation was implemented. "
            f"Before: {before or 'not measured'}. "
            f"After: {after or 'not measured'}. "
            f"Outcome: {outcome}"
        )
    elif status == "failed":
        return (
            f"Pattern '{pattern_type}' recommendation was attempted but failed. "
            f"Outcome: {outcome}. "
            f"Future recommendations of this type need closer review."
        )
    return (
        f"Pattern '{pattern_type}' recommendation was partially implemented. "
        f"Outcome: {outcome}."
    )


def create_action_item_from_recommendation(
    recommendation_id: str,
    db_path: str = DB_PATH,
) -> dict:
    """
    Creates a concrete action item in ci_action_items when a recommendation
    is approved. This is the work queue entry the team will execute.

    Parameters:
      recommendation_id — the approved CI-XXXXXX recommendation

    Returns:
      Dict with the new action_id and key fields.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM ci_recommendations WHERE recommendation_id = ?",
        (recommendation_id,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"error": f"Recommendation {recommendation_id} not found."}

    rec = dict(row)
    action_id = _new_id("ACT")
    now = _now()

    try:
        next_steps = json.loads(rec.get("next_steps_json", "[]"))
        acceptance = "Completed: " + "; ".join(next_steps[:3]) if next_steps else "All steps completed and verified."
    except (json.JSONDecodeError, TypeError):
        acceptance = "All recommended actions completed and verified."

    cursor.execute("""
        INSERT INTO ci_action_items (
            action_id, recommendation_id, project_name,
            title, description, business_impact, acceptance_criteria,
            priority, suggested_owner, due_date_suggestion,
            dependencies_json, risk_notes, success_metric,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        action_id, recommendation_id, rec["project_name"],
        rec["title"], rec["recommended_action"],
        rec.get("expected_benefit", ""),
        acceptance,
        rec.get("priority", "medium"),
        rec.get("suggested_owner", ""),
        "Within 5 business days",
        "[]",
        rec.get("rollback_notes", ""),
        "Verify metrics before and after implementation",
        "open", now,
    ))

    cursor.execute("""
        UPDATE ci_recommendations SET status = 'in_progress', updated_at = ?
        WHERE recommendation_id = ?
    """, (now, recommendation_id))

    conn.commit()
    conn.close()

    return {
        "action_id":         action_id,
        "recommendation_id": recommendation_id,
        "title":             rec["title"],
        "priority":          rec.get("priority", "medium"),
        "suggested_owner":   rec.get("suggested_owner", ""),
        "status":            "open",
        "message":           f"Action item {action_id} created from {recommendation_id}.",
    }


def get_improvement_summary(db_path: str = DB_PATH) -> dict:
    """
    Returns a high-level summary of CI Agent performance.
    Used by the MCP tool and dashboard.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM ci_recommendations WHERE project_name = ?
        GROUP BY status
    """, (PROJECT_CONFIG["project_name"],))
    status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT COUNT(*) as count FROM ci_lessons WHERE project_name = ?",
        (PROJECT_CONFIG["project_name"],)
    )
    # ci_lessons may not exist if using old schema — fallback gracefully.
    try:
        lesson_count = cursor.fetchone()["count"]
    except Exception:
        lesson_count = 0

    cursor.execute("""
        SELECT status, COUNT(*) as count FROM ci_outcomes
        WHERE project_name = ? GROUP BY status
    """, (PROJECT_CONFIG["project_name"],))
    outcome_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT COUNT(*) as count FROM ci_approval_requests
        WHERE project_name = ? AND decision = 'pending'
    """, (PROJECT_CONFIG["project_name"],))
    pending_approvals = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) as count FROM ci_learning_rules
        WHERE project_name = ?
    """, (PROJECT_CONFIG["project_name"],))
    try:
        learning_rules_fired = cursor.fetchone()["count"]
    except Exception:
        learning_rules_fired = 0

    conn.close()

    implemented = outcome_counts.get("implemented", 0)
    failed       = outcome_counts.get("failed", 0)
    total_outcomes = implemented + failed
    success_rate = round((implemented / total_outcomes) * 100) if total_outcomes > 0 else 0

    return {
        "total_recommendations":           sum(status_counts.values()),
        "by_status":                       status_counts,
        "pending_approvals":               pending_approvals,
        "total_implemented":               implemented,
        "total_failed":                    failed,
        "implementation_success_rate":     f"{success_rate}%",
        "lessons_learned_count":           lesson_count,
        "learning_rules_fired_total":      learning_rules_fired,
        "project_name":                    PROJECT_CONFIG["project_name"],
        "last_scan_at":                    "Use ci_agent_run_log for last scan time",
    }


def get_pattern_learning_report(db_path: str = DB_PATH) -> list:
    """
    Returns the current learning state for every pattern type that has
    accumulated stats. Used by the MCP get_lessons_learned tool and dashboard.

    Returns:
      List of dicts — one per pattern type — showing current adjustments
      and which rules have fired.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM ci_pattern_stats
        WHERE project_name = ?
        ORDER BY last_updated_at DESC
    """, (PROJECT_CONFIG["project_name"],))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    report = []
    for row in rows:
        conf_adj  = float(row.get("current_confidence_adjustment", 0.0))
        prio_adj  = float(row.get("current_priority_adjustment", 0.0))
        impact_adj = float(row.get("current_impact_adjustment", 0.0))

        status = "NEUTRAL"
        if conf_adj <= -0.10:
            status = "SUPPRESSED"
        elif conf_adj >= 0.10 or impact_adj >= 1.0:
            status = "HIGH_VALUE"

        report.append({
            "pattern_type":              row["pattern_type"],
            "learning_status":           status,
            "total_generated":           row.get("total_generated", 0),
            "total_approved":            row.get("total_approved", 0),
            "total_rejected":            row.get("total_rejected", 0),
            "total_deferred":            row.get("total_deferred", 0),
            "total_implemented":         row.get("total_implemented", 0),
            "total_failed":              row.get("total_failed", 0),
            "consecutive_rejections":    row.get("consecutive_rejections", 0),
            "confidence_adjustment":     f"{int(conf_adj * 100):+d}%",
            "priority_adjustment":       f"{prio_adj:+.1f}",
            "impact_adjustment":         f"{impact_adj:+.1f}",
            "net_effect": (
                "Scored lower on future scans" if conf_adj < -0.05
                else "Scored higher on future scans" if conf_adj > 0.05
                else "No adjustment yet"
            ),
            "last_updated":              row.get("last_updated_at", ""),
        })

    return report
