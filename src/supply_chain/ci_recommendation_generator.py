# src/supply_chain/ci_recommendation_generator.py
#
# PURPOSE:
#   Takes signals (problems found by ci_signal_detector.py) and turns them
#   into structured, actionable improvement recommendations.
#
# HOW IT WORKS:
#   1. Receive a signal dict from the detector
#   2. Look up the matching recommendation template
#   3. Fill in the template with the specific evidence from the signal
#   4. Score the recommendation: impact, effort, risk, priority
#   5. Decide whether human approval is required
#   6. Return a complete recommendation dict ready to save and display
#
# DESIGN PRINCIPLE:
#   Recommendations must be SPECIFIC, not generic.
#   Bad:  "Improve carrier performance."
#   Good: "3 orders have CARRIER_DELAY status. Contact carrier dispatch
#          for revised pickup commitment on each. If no response in 4 hours,
#          reassign all three to an alternate STRONG-tier carrier."

import uuid
import json
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'config'))

from ci_project_config import PROJECT_CONFIG


# ─── HELPER: generate unique IDs ─────────────────────────────────────────────

def _new_rec_id() -> str:
    """Generates a unique recommendation ID like CI-A3F2B1."""
    return f"CI-{uuid.uuid4().hex[:6].upper()}"

def _now() -> str:
    """Returns the current timestamp."""
    return datetime.now().isoformat(sep=" ", timespec="seconds")


# ─── RECOMMENDATION TEMPLATES ─────────────────────────────────────────────────
# Each key matches a signal_type from SIGNAL_TYPES in ci_project_config.py.
# Each template defines the shape of the recommendation for that signal type.
# The {placeholders} are filled in at runtime with actual signal data.

RECOMMENDATION_TEMPLATES = {

    "REPEATED_DELAY_BY_CARRIER": {
        "title_template":   "Address systemic carrier delay pattern ({frequency} orders affected)",
        "action_template": (
            "1. Pull all {frequency} affected orders and contact carrier dispatch for each. "
            "2. Request a revised pickup commitment in writing for each order. "
            "3. If any carrier does not respond within 4 hours, reassign to an alternate STRONG-tier carrier. "
            "4. Log all carrier responses in the carrier scorecard. "
            "5. If pattern persists next week, open a formal carrier performance review."
        ),
        "benefit_template": (
            "Resolving this pattern should eliminate CARRIER_DELAY as a repeat root cause, "
            "reducing average delay days and improving escalation rates."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  4,   # affects multiple customer deliveries
        "urgency_score": 4,   # active delays need same-day resolution
        "effort_score":  2,   # phone calls and reassignment only
        "risk_score":    1,   # no system or contract changes
        "requires_approval": False,
        "approval_reason": None,
        "suggested_owner": "Carrier Relations Team",
    },

    "DOMINANT_ROOT_CAUSE": {
        "title_template":   "Launch process improvement initiative for root cause: {root_cause} ({pct}% of delays)",
        "action_template": (
            "1. Conduct a 30-minute post-mortem with the responsible team to understand why this root cause is dominant. "
            "2. Identify if there is a process gap, a training gap, or a system gap causing repetition. "
            "3. Document 3 specific changes that would reduce this root cause by at least 50%. "
            "4. Create a project tracker item for each change with a 2-week deadline. "
            "5. Review root cause distribution again after 2 weeks to confirm improvement."
        ),
        "benefit_template": (
            "Reducing the dominant root cause from {pct}% to under 20% would meaningfully decrease "
            "total delay count and reduce manual escalation workload."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  5,   # highest impact — systemic fix
        "urgency_score": 3,   # medium urgency — not a fire today
        "effort_score":  4,   # requires team coordination
        "risk_score":    2,   # process change, not system change
        "requires_approval": True,
        "approval_reason": "Launching a process improvement initiative affects team workflows and priorities. Human approval required.",
        "suggested_owner": "Supply Chain Operations Lead",
    },

    "HIGH_UNKNOWN_RATE": {
        "title_template":   "Reduce UNKNOWN_NEEDS_REVIEW rate from {pct}% by improving rules.py classification",
        "action_template": (
            "1. Manually review all {count} UNKNOWN orders to identify what they have in common. "
            "2. Find 2-3 new patterns that are not currently covered in rules.py. "
            "3. Add new conditions to the assign_reason_code() function in rules.py to cover these cases. "
            "4. Re-run the agent after the change and verify the unknown rate drops. "
            "5. Target: reduce UNKNOWN rate below 10% of all delays."
        ),
        "benefit_template": (
            "Every UNKNOWN order requires manual investigation. Reducing unknowns from {pct}% to 10% "
            "would eliminate approximately {savings} manual investigations per run."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  4,   # high — reduces manual investigation workload
        "urgency_score": 2,   # not urgent — no immediate customer impact
        "effort_score":  3,   # code review and modification needed
        "risk_score":    3,   # medium — core rules file
        "requires_approval": True,
        "approval_reason": "This recommendation requires changes to rules.py which is a core business logic file. Code changes require human review and approval.",
        "suggested_owner": "Supply Chain Technology Team",
    },

    "FREIGHT_HOLD_PATTERN": {
        "title_template":   "Resolve {count} simultaneous freight holds — investigate systemic cause",
        "action_template": (
            "1. Get a list of all {count} active freight holds and their reasons. "
            "2. Check if multiple holds share the same carrier, origin warehouse, or hold reason. "
            "3. If they cluster around one cause (e.g., COMPLIANCE_ISSUE), escalate to logistics manager. "
            "4. For each hold, contact the freight team for an estimated release time. "
            "5. Create a prevention plan: what process change would stop this from recurring?"
        ),
        "benefit_template": (
            "Resolving all {count} freight holds would immediately unblock {count} customer deliveries "
            "and prevent further escalation."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  5,   # critical — physically blocks deliveries
        "urgency_score": 5,   # very urgent — holds escalate fast
        "effort_score":  3,   # investigation + coordination
        "risk_score":    3,   # may involve compliance/legal
        "requires_approval": True,
        "approval_reason": "Multiple freight holds may involve compliance or legal issues. Escalation to logistics manager requires human confirmation.",
        "suggested_owner": "Freight / Carrier Team",
    },

    "WEAK_CARRIER_OVERUSE": {
        "title_template":   "Reduce WEAK/CRITICAL carrier volume — {pct}% of shipments at risk",
        "action_template": (
            "1. Identify which specific carriers are rated WEAK or CRITICAL. "
            "2. Review which lanes or customers are currently assigned to these carriers. "
            "3. Request routing guide review with transportation team to shift volume to STRONG/AVERAGE carriers. "
            "4. For any carrier scoring below 55 (CRITICAL), initiate a carrier review meeting. "
            "5. Set a 30-day target: reduce WEAK/CRITICAL carrier volume below 15% of active shipments."
        ),
        "benefit_template": (
            "Shifting volume away from underperforming carriers will reduce CARRIER_DELAY "
            "and PICKUP_MISSED occurrences, directly improving on-time delivery rates."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  4,   # structural risk reduction
        "urgency_score": 3,   # medium — not immediate fire
        "effort_score":  4,   # routing guide + carrier review
        "risk_score":    3,   # affects costs and contracts
        "requires_approval": True,
        "approval_reason": "Changing carrier routing assignments is a business decision affecting costs and contracts. Requires leadership approval.",
        "suggested_owner": "Transportation Team",
    },

    "WAREHOUSE_SYSTEMIC_DELAY": {
        "title_template":   "Investigate structural pick delays at {warehouse} ({count} overdue picks)",
        "action_template": (
            "1. Call the warehouse supervisor at {warehouse} for an immediate status update. "
            "2. Ask specifically about: current staffing levels, any equipment failures, WMS system issues. "
            "3. Request a pick completion ETA for all {count} delayed orders. "
            "4. If staffing is the issue, escalate to operations manager for emergency resource allocation. "
            "5. If equipment is the issue, initiate emergency maintenance request. "
            "6. Document the root cause and add to the warehouse improvement backlog."
        ),
        "benefit_template": (
            "Resolving the systemic delay at {warehouse} would immediately unblock {count} customer orders "
            "and prevent future delays from the same root cause."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  4,   # unblocks multiple orders
        "urgency_score": 4,   # warehouse delays compound quickly
        "effort_score":  2,   # escalation call + supervisor action
        "risk_score":    2,   # low — investigation only
        "requires_approval": False,
        "approval_reason": None,
        "suggested_owner": "Warehouse Operations Team",
    },

    "REPEATED_STOCKOUT": {
        "title_template":   "Review reorder points for {count} items currently out of stock or on backorder",
        "action_template": (
            "1. List all {count} items that are OUT_OF_STOCK or ON_BACKORDER. "
            "2. For each item, check the reorder point vs. the actual demand rate over the last 30 days. "
            "3. Identify items where demand exceeded reorder point — these need higher safety stock. "
            "4. Raise purchase orders for all items without an expected receipt date. "
            "5. Propose new reorder point values to the inventory manager for approval."
        ),
        "benefit_template": (
            "Correcting reorder points will prevent stockouts before they affect shipments, "
            "reducing INVENTORY_SHORTAGE and BACKORDER delay root causes."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  4,   # prevents future stockout delays
        "urgency_score": 3,   # medium — already in stockout
        "effort_score":  3,   # PO raising + reorder point review
        "risk_score":    3,   # affects purchasing budgets
        "requires_approval": True,
        "approval_reason": "Changing reorder points and safety stock levels affects procurement budgets. Requires inventory manager approval.",
        "suggested_owner": "Procurement / Supplier Team",
    },

    "DATA_QUALITY_GAP": {
        "title_template":   "Fix {count} data quality issues causing classification failures",
        "action_template": (
            "1. Review the list of records with missing fields. "
            "2. For each missing field, determine: is this a data entry problem or a system integration problem? "
            "3. For data entry gaps: update the records manually in DB Browser for SQLite. "
            "4. For integration gaps: raise a ticket with the system team to enforce required fields. "
            "5. Add a data quality check to the agent that alerts when critical fields are missing at load time."
        ),
        "benefit_template": (
            "Fixing data gaps will reduce UNKNOWN_NEEDS_REVIEW classifications "
            "and improve the accuracy of all agent reports."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  3,   # moderate — improves classification accuracy
        "urgency_score": 2,   # low urgency — no direct customer impact
        "effort_score":  3,   # investigation + data entry or ticket
        "risk_score":    1,   # very low — no system changes
        "requires_approval": False,
        "approval_reason": None,
        "suggested_owner": "Supply Chain Data Team",
    },

    "MULTI_DOMAIN_CLUSTER": {
        "title_template":   "Multi-domain failure cluster detected — {count} orders with 3+ simultaneous issues",
        "action_template": (
            "1. Identify all orders with problems in 3 or more domains simultaneously. "
            "2. These orders are at highest risk — assign a dedicated coordinator to each. "
            "3. Run the investigate_order tool on each order to get the full cross-agent report. "
            "4. Hold a 15-minute cross-team standup to align on resolution priorities. "
            "5. Set 4-hour checkpoints until all multi-domain issues are resolved."
        ),
        "benefit_template": (
            "Multi-domain orders are the most likely to miss customer SLAs. "
            "Dedicated attention reduces resolution time and customer impact."
        ),
        # Scores on 1-5 scale (spec formula)
        "impact_score":  5,   # highest — multiple domains failing
        "urgency_score": 5,   # critical — SLA breach imminent
        "effort_score":  4,   # cross-team coordination
        "risk_score":    3,   # reallocation decisions
        "requires_approval": True,
        "approval_reason": "Multi-domain clusters may require cross-team coordination and resource reallocation. Requires manager confirmation.",
        "suggested_owner": "Supply Chain Coordinator",
    },
}


# ─── PRIORITY CALCULATOR ──────────────────────────────────────────────────────
#
# FORMULA (from spec — do not change without updating ci_project_config.py):
#
#   priority_score = (impact   × weight_impact)
#                  + (urgency  × weight_urgency)
#                  + (confidence × 5 × weight_confidence)
#                  - (effort   × weight_effort)
#                  - (risk     × weight_risk)
#
# All five inputs are on a 1–5 scale EXCEPT confidence which is 0.0–1.0.
# Multiplying confidence by 5 puts it on the same 0–5 scale as the others.
#
# The raw result maps to labels:
#   0.0–1.9  → low
#   2.0–2.9  → medium
#   3.0–3.9  → high
#   4.0–5.0  → critical
#
# Weights are stored in ci_project_config.py under "scoring_weights"
# so they can be tuned per project without changing this file.

def calculate_ci_priority(impact: int, urgency: int, effort: int,
                          risk: int, confidence: float,
                          learning_adjustments: dict = None) -> tuple:
    """
    Calculates a priority score and priority label using the spec formula.

    Parameters:
      impact     — 1–5: how much operational benefit if implemented
      urgency    — 1–5: how time-sensitive this problem is
      effort     — 1–5: implementation effort (higher = harder = lower priority)
      risk       — 1–5: change risk (higher = riskier = lower priority)
      confidence — 0.0–1.0: how confident the agent is (multiplied by 5 internally)
      learning_adjustments — optional dict of adjustments from the learning engine:
                             {"confidence_delta": float, "priority_delta": float,
                              "impact_delta": float}
                             These nudge the inputs based on past outcomes.

    Returns:
      (priority_score_raw, priority_label, priority_score_0_to_100)

      priority_score_raw   — the raw float from the formula (0.0–5.0 range)
      priority_label       — "critical", "high", "medium", or "low"
      priority_score_0_100 — scaled 0–100 integer for sorting and display

    WORKED EXAMPLE:
      impact=4, urgency=4, effort=2, risk=2, confidence=0.80
      = (4×0.35) + (4×0.25) + (0.80×5×0.20) - (2×0.10) - (2×0.10)
      = 1.40    + 1.00     + 0.80            - 0.20     - 0.20
      = 2.80  → "medium"
    """
    # ── Apply learning adjustments if provided ────────────────────────────────
    # The learning engine nudges inputs based on historical outcomes.
    # For example: if this pattern type has been rejected 5 times, confidence
    # is reduced by 0.15. We apply that here before scoring.
    if learning_adjustments:
        confidence = max(0.0, min(1.0,
            confidence + learning_adjustments.get("confidence_delta", 0.0)
        ))
        impact = max(1, min(5,
            impact + int(learning_adjustments.get("impact_delta", 0.0))
        ))

    # ── Clamp all inputs to their valid ranges ────────────────────────────────
    # This prevents bad data from producing nonsense scores.
    impact     = max(1, min(5, int(impact)))
    urgency    = max(1, min(5, int(urgency)))
    effort     = max(1, min(5, int(effort)))
    risk       = max(1, min(5, int(risk)))
    confidence = max(0.0, min(1.0, float(confidence)))

    # ── Load weights from config ──────────────────────────────────────────────
    w = PROJECT_CONFIG["scoring_weights"]

    # ── Apply the exact formula from the spec ─────────────────────────────────
    raw = (
          (impact     * w["impact"])
        + (urgency    * w["urgency"])
        + (confidence * 5 * w["confidence"])
        - (effort     * w["effort"])
        - (risk       * w["risk"])
    )

    # ── Map raw score to label ────────────────────────────────────────────────
    # Spec thresholds: 0.0–1.9=low, 2.0–2.9=medium, 3.0–3.9=high, 4.0–5.0=critical
    if raw >= 4.0:
        label = "critical"
    elif raw >= 3.0:
        label = "high"
    elif raw >= 2.0:
        label = "medium"
    else:
        label = "low"

    # ── Scale to 0–100 for display and database storage ───────────────────────
    # We divide by 5 (max possible raw) to get 0–1, then multiply by 100.
    score_0_100 = int(max(0, min(100, (raw / 5.0) * 100)))

    return raw, label, score_0_100


# ─── MAIN RECOMMENDATION GENERATOR ───────────────────────────────────────────

def generate_recommendation_from_signal(signal: dict) -> dict:
    """
    Takes one signal dict (from ci_signal_detector.py) and returns one
    complete recommendation dict ready to save to ci_recommendations.

    Parameters:
      signal — a signal dict as returned by run_full_signal_scan()

    Returns:
      A recommendation dict with all fields filled in.
    """
    signal_type = signal.get("signal_type", "UNKNOWN")
    frequency   = signal.get("frequency", 1)
    affected    = signal.get("affected_records", "")

    # Get the template for this signal type.
    # If no template exists, use a generic fallback.
    template = RECOMMENDATION_TEMPLATES.get(signal_type, {
        "title_template":    f"Review {signal_type} pattern ({frequency} occurrences)",
        "action_template":  "Manually review this signal and determine appropriate action.",
        "benefit_template": "Addressing this signal should improve operational health.",
        "impact_score":     5,
        "effort_score":     5,
        "risk_score":       5,
        "requires_approval": True,
        "approval_reason":  "No specific template found — human review required.",
        "suggested_owner":  "Supply Chain Coordinator",
    })

    # ── Build context variables for template filling ──────────────────────────
    # Parse the evidence JSON stored in the signal to extract key values.
    try:
        evidence_list = json.loads(signal.get("evidence_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        evidence_list = []

    # Extract the root cause from evidence if it's a DOMINANT_ROOT_CAUSE signal.
    root_cause = "UNKNOWN"
    pct = "0"
    count_str = str(frequency)
    warehouse = signal.get("affected_records", "").split(",")[0].strip() or "Unknown Warehouse"

    for ev in evidence_list:
        if "Root cause:" in ev:
            root_cause = ev.replace("Root cause:", "").strip()
        if "Percentage:" in ev:
            pct = ev.replace("Percentage:", "").replace("%", "").strip()

    # Calculate savings for unknown rate recommendation.
    savings = max(0, frequency - int(len(evidence_list) * 0.10)) if frequency > 0 else 0

    # ── Fill in the templates ─────────────────────────────────────────────────
    # Python's .format() replaces {placeholder} with the actual value.
    try:
        title = template["title_template"].format(
            frequency=frequency, root_cause=root_cause,
            pct=pct, count=count_str, warehouse=warehouse,
        )
    except (KeyError, ValueError):
        title = template["title_template"]

    try:
        action = template["action_template"].format(
            frequency=frequency, root_cause=root_cause,
            pct=pct, count=count_str, warehouse=warehouse,
            savings=savings,
        )
    except (KeyError, ValueError):
        action = template["action_template"]

    try:
        benefit = template["benefit_template"].format(
            frequency=frequency, root_cause=root_cause,
            pct=pct, count=count_str, savings=savings,
        )
    except (KeyError, ValueError):
        benefit = template["benefit_template"]

    # ── Score and prioritize ──────────────────────────────────────────────────
    # Base confidence comes from signal severity — more severe = more evidence.
    severity_confidence = {
        "CRITICAL": 0.90,
        "HIGH":     0.80,
        "MEDIUM":   0.65,
        "LOW":      0.50,
    }
    confidence = severity_confidence.get(signal.get("severity", "MEDIUM"), 0.65)

    # Read all five scoring inputs from the template.
    # urgency_score defaults to 3 (middle) if a template doesn't define it yet.
    impact  = template["impact_score"]
    urgency = template.get("urgency_score", 3)
    effort  = template["effort_score"]
    risk    = template["risk_score"]

    # ── Fetch learning adjustments for this pattern type ─────────────────────
    # The learning engine may have nudged confidence, impact, or priority
    # based on past outcomes for this specific signal type.
    # We import here (not at top) to avoid circular imports.
    learning_adjustments = None
    try:
        from supply_chain.ci_learning_engine import get_learning_adjustments_for_pattern
        learning_adjustments = get_learning_adjustments_for_pattern(signal_type)
    except (ImportError, Exception):
        pass  # Learning engine not available yet — skip adjustments

    # ── Call the spec-formula scorer ─────────────────────────────────────────
    # Returns (raw_float, label_string, score_0_to_100_int)
    priority_raw, priority_label, priority_score = calculate_ci_priority(
        impact, urgency, effort, risk, confidence, learning_adjustments
    )

    # Apply confidence adjustment from learning engine.
    if learning_adjustments:
        confidence = max(0.0, min(1.0,
            confidence + learning_adjustments.get("confidence_delta", 0.0)
        ))

    # ── Determine approval requirement ────────────────────────────────────────
    requires_approval = template["requires_approval"]
    approval_reason   = template.get("approval_reason", "")

    # Always require approval if confidence (after learning adjustment) is low.
    conf_threshold = PROJECT_CONFIG["approval_rules"]["confidence_threshold_for_auto_log"]
    if confidence < conf_threshold:
        requires_approval = True
        approval_reason = (
            f"Confidence is {int(confidence * 100)}%, below the "
            f"{int(conf_threshold * 100)}% threshold for auto-logging."
        )

    # Always require approval if risk is at or above the threshold.
    # NOTE: threshold is now on 1-5 scale. Default threshold in config is 7/10
    # which maps to roughly 4/5. Update config if needed.
    risk_threshold = PROJECT_CONFIG["approval_rules"].get("risk_threshold_for_approval_1_5", 4)
    if risk >= risk_threshold and not requires_approval:
        requires_approval = True
        approval_reason = (
            f"Risk score {risk}/5 meets the approval threshold of {risk_threshold}/5."
        )

    # ── Build next steps list ─────────────────────────────────────────────────
    # Parse numbered steps like "1. Do X" from the action template string.
    next_steps = []
    for line in action.split("\n"):
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            step_text = line.split(". ", 1)[1]
            next_steps.append(step_text)

    # ── Assemble the recommendation dict ─────────────────────────────────────
    now = _now()
    return {
        "recommendation_id":      _new_rec_id(),
        "project_name":           PROJECT_CONFIG["project_name"],
        "signal_id":              signal.get("signal_id", ""),
        "title":                  title,
        "summary":                signal.get("description", ""),
        "evidence_json":          signal.get("evidence_json", "[]"),
        "root_cause_hypothesis":  signal.get("description", ""),
        "recommended_action":     action,
        "expected_benefit":       benefit,
        "impact_score":           impact,
        "urgency_score":          urgency,
        "effort_score":           effort,
        "risk_score":             risk,
        "priority":               priority_label,
        "priority_score":         priority_score,       # 0–100 integer
        "priority_score_raw":     round(priority_raw, 3),  # 0.0–5.0 float
        "confidence":             round(confidence, 3),
        "requires_human_approval": 1 if requires_approval else 0,
        "approval_reason":        approval_reason or "",
        "suggested_owner":        template["suggested_owner"],
        "next_steps_json":        json.dumps(next_steps),
        "rollback_notes":         "If this change causes operational disruption, revert to the previous process immediately and document the issue.",
        "status":                 "pending_approval" if requires_approval else "new",
        "created_at":             now,
        "updated_at":             now,
    }


def generate_all_recommendations(signals: list) -> list:
    """
    Converts a list of signals into a list of recommendations.
    Called by the MCP server after run_full_signal_scan().

    Parameters:
      signals — list of signal dicts from ci_signal_detector.py

    Returns:
      List of recommendation dicts, sorted by priority_score descending.
    """
    recommendations = []

    for signal in signals:
        rec = generate_recommendation_from_signal(signal)
        recommendations.append(rec)

    # Sort: highest priority score first.
    recommendations.sort(key=lambda r: r.get("priority_score", 0), reverse=True)

    return recommendations
