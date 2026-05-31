# config/ci_project_config.py
#
# PURPOSE:
#   This is the project configuration for the Continuous Improvement Agent.
#   It tells the agent everything it needs to know about YOUR specific project.
#
# REUSABILITY NOTE:
#   The core agent logic never changes. Only THIS file changes between projects.
#   To use this agent on a different project, copy this file and update the values.
#
# WHAT THIS FILE CONTROLS:
#   - Project name and goals
#   - Which signals the agent should look for
#   - When the agent must ask for human approval
#   - How to score impact vs effort vs risk
#   - Which teams own which types of problems
#   - Thresholds for escalation, alerts, and priority

# ─── PROJECT IDENTITY ─────────────────────────────────────────────────────────

PROJECT_CONFIG = {

    # The name of your project. Used in all reports and recommendations.
    "project_name": "Supply Chain Control Tower",

    # A short description of what this project does.
    "project_domain": "Supply Chain / Logistics / Shipping Visibility",

    # What you are trying to achieve with this project.
    # The agent uses these goals when deciding what to prioritize.
    "business_goals": [
        "Reduce average shipment delay from current levels",
        "Eliminate NEED_ACTION escalations by catching delays at DELAYED stage",
        "Reduce UNKNOWN_NEEDS_REVIEW root cause below 10% of all delays",
        "Improve carrier WEAK/CRITICAL tier rate — move toward STRONG/AVERAGE",
        "Reduce freight hold frequency and resolution time",
        "Improve inventory health — reduce OUT_OF_STOCK and ON_BACKORDER",
        "Reduce manual investigation time per delayed order",
    ],

    # Metrics the agent should monitor and try to improve over time.
    # These are the numbers that tell you if the project is working.
    "key_metrics": [
        "percentage_delayed_shipments",       # what % of orders are delayed
        "percentage_need_action_shipments",   # what % exceed 5-day threshold
        "average_delay_days",                 # average days overdue across all delays
        "unknown_root_cause_rate",            # % of delays with UNKNOWN_NEEDS_REVIEW
        "freight_hold_count",                 # number of active freight holds
        "carrier_weak_critical_rate",         # % of carriers in WEAK or CRITICAL tier
        "inventory_critical_out_of_stock",    # count of critical/OOS inventory items
        "escalation_rate",                    # % of orders requiring escalation
        "recommendations_implemented_rate",  # % of CI recommendations that got done
    ],

    # Which domains the agent should scan for problems.
    # These match the agents you already have built.
    "data_sources": [
        {"name": "shipments",       "table": "shipments",       "agent": "shipping-delay-agent"},
        {"name": "inventory",       "table": "inventory",       "agent": "inventory-agent"},
        {"name": "freight",         "table": "freight",         "agent": "freight-agent"},
        {"name": "warehouse_picks", "table": "warehouse_picks", "agent": "warehouse-agent"},
    ],

    # The teams in your organization who own different types of problems.
    # The agent uses this to assign recommendations to the right person.
    "teams": {
        "FREIGHT_HOLD":          "Freight / Carrier Team",
        "BACKORDER":             "Procurement / Supplier Team",
        "INVENTORY_SHORTAGE":    "Warehouse / Inventory Team",
        "TRUCK_NOT_AVAILABLE":   "Transportation Team",
        "CARRIER_DELAY":         "Carrier Relations Team",
        "WAREHOUSE_PICK_DELAY":  "Warehouse Operations Team",
        "SYSTEM_IMPROVEMENT":    "Supply Chain Technology Team",
        "PROCESS_IMPROVEMENT":   "Supply Chain Operations Lead",
        "DATA_QUALITY":          "Supply Chain Data Team",
        "UNKNOWN_NEEDS_REVIEW":  "Supply Chain Coordinator",
    },

    # ─── APPROVAL RULES ───────────────────────────────────────────────────────
    # These rules define WHEN the agent must stop and ask you for a decision.
    # The agent will NEVER take autonomous action on these categories.
    "approval_rules": {

        # Always require human approval for these action types.
        # These are things that could affect customers, costs, or system behavior.
        "always_require_approval": [
            "changes_to_business_rules",     # editing scoring weights, thresholds, etc.
            "changes_to_escalation_logic",   # changing when orders escalate
            "carrier_scorecard_adjustment",  # changing carrier tier thresholds
            "customer_communication",        # anything that reaches a customer
            "code_changes",                  # any suggested code modifications
            "database_schema_changes",       # adding columns, tables, etc.
            "workflow_changes",              # changing who gets notified and when
            "new_automation",                # creating any new automated process
        ],

        # Require approval when agent confidence is below this number.
        # 0.75 means: if the agent is less than 75% confident, it asks you.
        "confidence_threshold_for_auto_log": 0.75,

        # Require approval when the risk score is at or above this value.
        # Scale is NOW 1–5 (matching the scoring formula).
        # 4 means: anything rated 4 or 5 out of 5 requires approval.
        "risk_threshold_for_approval": 7,          # kept for legacy reference
        "risk_threshold_for_approval_1_5": 4,      # used by new scoring engine

        # Require approval when the estimated effort is very high.
        # Scale is 1-10. 8 means: very large efforts require approval.
        "effort_threshold_for_approval": 8,
    },

    # ─── DETECTION THRESHOLDS ─────────────────────────────────────────────────
    # These numbers control when the agent flags something as a problem.
    # You can tune these over time as you learn what's normal for your operation.
    "detection_thresholds": {

        # Flag a carrier as a pattern problem if it causes this many delays.
        "carrier_delay_repeat_threshold": 2,

        # Flag an inventory item if it goes out of stock this many times.
        "inventory_oos_repeat_threshold": 2,

        # Flag UNKNOWN_NEEDS_REVIEW as a systemic issue if this % of delays use it.
        "unknown_root_cause_pct_threshold": 0.20,  # 20%

        # Flag a root cause as dominant if it appears in this % of delays.
        "dominant_root_cause_pct_threshold": 0.35,  # 35%

        # Minimum number of records needed before flagging a pattern.
        # Prevents false alarms from single data points.
        "minimum_sample_size": 2,

        # Flag a warehouse as having systemic issues if this many picks are delayed.
        "warehouse_delayed_picks_threshold": 2,

        # Flag freight holds as systemic if this many are active at once.
        "freight_hold_count_threshold": 2,
    },

    # ─── SCORING WEIGHTS ──────────────────────────────────────────────────────
    # These weights implement the exact formula from the spec:
    #
    #   priority = (impact × weight_impact)
    #            + (urgency × weight_urgency)
    #            + (confidence × 5 × weight_confidence)
    #            - (effort × weight_effort)
    #            - (risk × weight_risk)
    #
    # All five dimensions are on a 1–5 scale (confidence is 0–1, multiplied by 5).
    # Weights are configurable per project — change them here, not in the code.
    "scoring_weights": {
        "impact":      0.35,  # spec default
        "urgency":     0.25,  # spec default
        "confidence":  0.20,  # spec default (applied to confidence×5)
        "effort":      0.10,  # subtracted — higher effort lowers score
        "risk":        0.10,  # subtracted — higher risk lowers score
    },

    # ─── REPORTING ────────────────────────────────────────────────────────────
    "reporting_frequency": "weekly",

    # How many top recommendations to include in the weekly summary report.
    "report_top_n_recommendations": 5,
}


# ─── SIGNAL TYPE DEFINITIONS ──────────────────────────────────────────────────
# These define what kinds of problems the agent knows how to detect.
# Each signal type has a name, which domain it belongs to, and a description.
#
# Think of these as the "categories" the agent uses to classify problems it finds.

SIGNAL_TYPES = {

    # ── Shipping domain signals ───────────────────────────────────────────────
    "REPEATED_DELAY_BY_CARRIER": {
        "domain": "SHIPPING",
        "description": "Same carrier is causing delays repeatedly across multiple orders",
        "auto_log": True,  # agent can log this without approval
    },
    "DOMINANT_ROOT_CAUSE": {
        "domain": "SHIPPING",
        "description": "One root cause type is appearing in a disproportionate share of delays",
        "auto_log": True,
    },
    "HIGH_UNKNOWN_RATE": {
        "domain": "SHIPPING",
        "description": "Too many delays are classified as UNKNOWN_NEEDS_REVIEW",
        "auto_log": True,
    },
    "NEED_ACTION_SPIKE": {
        "domain": "SHIPPING",
        "description": "Orders are reaching NEED_ACTION status instead of being caught at DELAYED",
        "auto_log": True,
    },
    "SCORING_THRESHOLD_ANOMALY": {
        "domain": "SHIPPING",
        "description": "Orders near the escalation boundary are behaving inconsistently",
        "auto_log": False,  # requires approval before logging because it suggests rule change
    },

    # ── Inventory domain signals ──────────────────────────────────────────────
    "REPEATED_STOCKOUT": {
        "domain": "INVENTORY",
        "description": "Same item is going out of stock repeatedly",
        "auto_log": True,
    },
    "BACKORDER_PATTERN": {
        "domain": "INVENTORY",
        "description": "Multiple items consistently on backorder from the same supplier",
        "auto_log": True,
    },
    "SAFETY_STOCK_INADEQUATE": {
        "domain": "INVENTORY",
        "description": "Safety stock level appears too low given actual demand patterns",
        "auto_log": False,  # suggests changing a business parameter — needs approval
    },

    # ── Freight domain signals ────────────────────────────────────────────────
    "CARRIER_PERFORMANCE_DEGRADATION": {
        "domain": "FREIGHT",
        "description": "A carrier's actual performance does not match their tier rating",
        "auto_log": True,
    },
    "FREIGHT_HOLD_PATTERN": {
        "domain": "FREIGHT",
        "description": "Freight holds are clustering around a specific reason or carrier",
        "auto_log": True,
    },
    "WEAK_CARRIER_OVERUSE": {
        "domain": "FREIGHT",
        "description": "WEAK or CRITICAL tier carriers are handling too many shipments",
        "auto_log": True,
    },

    # ── Warehouse domain signals ──────────────────────────────────────────────
    "WAREHOUSE_SYSTEMIC_DELAY": {
        "domain": "WAREHOUSE",
        "description": "A specific warehouse has multiple delayed picks — possible structural issue",
        "auto_log": True,
    },
    "STAFFING_PATTERN": {
        "domain": "WAREHOUSE",
        "description": "Staffing flag is repeatedly set, suggesting chronic understaffing",
        "auto_log": True,
    },
    "EQUIPMENT_FAILURE_PATTERN": {
        "domain": "WAREHOUSE",
        "description": "Equipment issues are causing repeated pick delays",
        "auto_log": True,
    },

    # ── Cross-domain signals ──────────────────────────────────────────────────
    "MULTI_DOMAIN_CLUSTER": {
        "domain": "CROSS_DOMAIN",
        "description": "Multiple domains are failing simultaneously for a cluster of orders",
        "auto_log": True,
    },
    "DATA_QUALITY_GAP": {
        "domain": "DATA",
        "description": "Missing, null, or inconsistent data is affecting agent accuracy",
        "auto_log": True,
    },
}
