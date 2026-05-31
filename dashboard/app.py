# dashboard/app.py
#
# Supply Chain Control Tower — Phase 8 Dashboard
#
# Elite-level Streamlit dashboard with three drill-down levels:
#   Level 1 — Command Center (landing page, KPIs, charts)
#   Level 2 — Domain panels (freight, inventory, warehouse, carrier)
#   Level 3 — Order detail panel (full investigation + recommendation)
#
# Data: reads from SQLite database (supply_chain.db) using the same rules
# engines as the MCP servers. Phase 7 update: switched from CSV to SQLite
# so the dashboard always shows the same data as Claude Desktop.
# No MCP servers need to be running for this dashboard to work.
#
# How to run:
#   cd "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project"
#   $env:PYTHONPATH = "C:\Users\preet\Documents\AI Work\supply_chain_mcp_project\src"
#   streamlit run dashboard\app.py
#
# Then open http://localhost:8501 in your browser.

import sys
import os
from datetime import date
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH     = PROJECT_ROOT / "src"
DATA_DIR     = PROJECT_ROOT / "data"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# ── Rules engine imports ──────────────────────────────────────────────────────
try:
    # OLD (Phase 8 — CSV loaders):
    # from supply_chain.data_loader          import load_shipments
    # from supply_chain.inventory_data_loader import load_inventory
    # from supply_chain.freight_data_loader   import load_freight
    # from supply_chain.warehouse_data_loader import load_warehouse_picks
    #
    # NEW (Phase 7 — SQLite loader):
    # We import all 4 loaders from one single file — db_loader.py
    # The "as" keyword renames them so the rest of the code below
    # doesn't need to change at all — same function names, new source.
    from supply_chain.db_loader import (
        load_shipments_db       as load_shipments,
        load_inventory_db       as load_inventory,
        load_freight_db         as load_freight,
        load_warehouse_picks_db as load_warehouse_picks,
    )
    from supply_chain.rules                 import assign_delay_status, assign_reason_code, calculate_delay_days
    from supply_chain.inventory_rules       import assign_inventory_status, get_inventory_recommendation
    from supply_chain.freight_rules         import assign_freight_status, assign_carrier_tier, calculate_pickup_delay_days, get_freight_recommendation
    from supply_chain.warehouse_rules       import assign_pick_health, calculate_pick_delay_days, get_pick_recommendation
    from supply_chain.investigation_rules   import build_investigation_report, resolve_root_cause, score_severity
    from supply_chain.recommendation_engine import build_action_record
    RULES_OK = True
except ImportError as e:
    RULES_OK = False
    IMPORT_ERROR = str(e)

TODAY = date.today()

# OLD (Phase 8 — four separate CSV file paths):
# SHIPMENTS_CSV  = str(DATA_DIR / "shipments_sample.csv")
# INVENTORY_CSV  = str(DATA_DIR / "inventory_sample.csv")
# FREIGHT_CSV    = str(DATA_DIR / "freight_sample.csv")
# WAREHOUSE_CSV  = str(DATA_DIR / "warehouse_sample.csv")
#
# NEW (Phase 7 — one single SQLite database file):
# All four tables now live inside supply_chain.db
# DATA_DIR is still used from the path setup above — it points to
# the /data/ folder in your project, so this works on any machine.
DB_FILE = str(DATA_DIR / "supply_chain.db")

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Supply Chain Control Tower",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# THEME  (light default, dark toggle)
# ─────────────────────────────────────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

LIGHT = {
    "bg":           "#F8F9FC",
    "surface":      "#FFFFFF",
    "surface2":     "#F1F3F9",
    "border":       "#E2E6EF",
    "text":         "#0F1523",
    "text2":        "#4A5568",
    "text3":        "#8A94A6",
    "accent":       "#1A56DB",
    "accent_light": "#EBF0FF",
    "red":          "#E02424",
    "red_light":    "#FDE8E8",
    "amber":        "#D97706",
    "amber_light":  "#FEF3C7",
    "green":        "#057A55",
    "green_light":  "#DEF7EC",
    "blue":         "#1C64F2",
    "blue_light":   "#E1EFFE",
    "chart_bg":     "#FFFFFF",
    "grid":         "#E8ECF4",
}
DARK = {
    "bg":           "#0B0F1A",
    "surface":      "#141929",
    "surface2":     "#1C2438",
    "border":       "#2A3350",
    "text":         "#E8EDF7",
    "text2":        "#9BA8C0",
    "text3":        "#5A6880",
    "accent":       "#4B7BF5",
    "accent_light": "#1A2540",
    "red":          "#F05252",
    "red_light":    "#2D1515",
    "amber":        "#F6A623",
    "amber_light":  "#2D2010",
    "green":        "#31C48D",
    "green_light":  "#0D2B1F",
    "blue":         "#4B7BF5",
    "blue_light":   "#151E35",
    "chart_bg":     "#141929",
    "grid":         "#1E2D45",
}

C = DARK if st.session_state.dark_mode else LIGHT

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {{
    font-family: 'DM Sans', sans-serif;
    background-color: {C['bg']};
    color: {C['text']};
}}

/* Hide Streamlit chrome */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 0 2rem 2rem 2rem; max-width: 1600px; }}
[data-testid="stAppViewContainer"] {{ background: {C['bg']}; }}
[data-testid="stSidebar"] {{ background: {C['surface']}; border-right: 1px solid {C['border']}; }}

/* Top bar */
.topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 0 1rem 0;
    border-bottom: 1px solid {C['border']};
    margin-bottom: 1.5rem;
}}
.topbar-left {{ display: flex; align-items: center; gap: 0.75rem; }}
.logo-mark {{
    width: 36px; height: 36px;
    background: {C['accent']};
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
}}
.topbar-title {{
    font-size: 1.1rem;
    font-weight: 700;
    color: {C['text']};
    letter-spacing: -0.02em;
}}
.topbar-sub {{
    font-size: 0.75rem;
    color: {C['text3']};
    font-weight: 400;
}}
.topbar-right {{ display: flex; align-items: center; gap: 1rem; }}
.date-chip {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    border-radius: 20px;
    padding: 0.3rem 0.85rem;
    font-size: 0.78rem;
    color: {C['text2']};
    font-family: 'DM Mono', monospace;
}}

/* Risk badge */
.risk-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 1rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}
.risk-CRITICAL {{ background: {C['red_light']}; color: {C['red']}; border: 1px solid {C['red']}22; }}
.risk-HIGH     {{ background: {C['amber_light']}; color: {C['amber']}; border: 1px solid {C['amber']}22; }}
.risk-MEDIUM   {{ background: {C['amber_light']}; color: {C['amber']}; border: 1px solid {C['amber']}22; }}
.risk-LOW      {{ background: {C['green_light']}; color: {C['green']}; border: 1px solid {C['green']}22; }}

/* Section headers */
.section-header {{
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {C['text3']};
    margin: 1.5rem 0 0.75rem 0;
}}

/* KPI Cards */
.kpi-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; margin-bottom: 1.5rem; }}
.kpi-card {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    padding: 1.25rem 1.25rem 1rem 1.25rem;
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.2s;
    cursor: default;
}}
.kpi-card:hover {{ box-shadow: 0 4px 20px {C['accent']}18; border-color: {C['accent']}44; }}
.kpi-accent-bar {{
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}}
.kpi-label {{ font-size: 0.72rem; font-weight: 600; color: {C['text3']}; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.4rem; }}
.kpi-value {{ font-size: 2rem; font-weight: 700; color: {C['text']}; letter-spacing: -0.03em; line-height: 1; }}
.kpi-sub {{ font-size: 0.72rem; color: {C['text3']}; margin-top: 0.3rem; }}

/* Data cards / panels */
.panel {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
}}
.panel-title {{
    font-size: 0.85rem;
    font-weight: 700;
    color: {C['text']};
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}}

/* Status badges */
.badge {{
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}}
.badge-red    {{ background: {C['red_light']};   color: {C['red']};   }}
.badge-amber  {{ background: {C['amber_light']}; color: {C['amber']}; }}
.badge-green  {{ background: {C['green_light']}; color: {C['green']}; }}
.badge-blue   {{ background: {C['blue_light']};  color: {C['blue']};  }}
.badge-grey   {{ background: {C['surface2']};    color: {C['text3']}; }}

/* Order rows */
.order-row {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0;
    border-bottom: 1px solid {C['border']};
    cursor: pointer;
    transition: background 0.15s;
    border-radius: 6px;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
}}
.order-row:hover {{ background: {C['surface2']}; }}
.order-no {{
    font-family: 'DM Mono', monospace;
    font-size: 0.8rem;
    font-weight: 500;
    color: {C['accent']};
    min-width: 75px;
}}
.order-customer {{ font-size: 0.82rem; color: {C['text']}; flex: 1; }}
.order-days {{ font-size: 0.78rem; font-weight: 600; color: {C['red']}; min-width: 55px; text-align: right; }}
.order-reason {{ font-size: 0.7rem; color: {C['text3']}; min-width: 120px; text-align: right; }}

/* Detail panel */
.detail-panel {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 16px;
    padding: 1.5rem;
    margin-top: 0.5rem;
}}
.detail-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1.25rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid {C['border']};
}}
.detail-order-no {{
    font-family: 'DM Mono', monospace;
    font-size: 1.1rem;
    font-weight: 600;
    color: {C['accent']};
}}
.detail-customer {{
    font-size: 1.3rem;
    font-weight: 700;
    color: {C['text']};
    letter-spacing: -0.02em;
}}
.detail-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.25rem;
}}
.detail-field {{ }}
.detail-field-label {{ font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: {C['text3']}; margin-bottom: 0.2rem; }}
.detail-field-value {{ font-size: 0.9rem; font-weight: 600; color: {C['text']}; }}
.action-box {{
    background: {C['accent_light']};
    border: 1px solid {C['accent']}33;
    border-radius: 10px;
    padding: 1rem;
    margin-top: 1rem;
}}
.action-box-label {{ font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: {C['accent']}; margin-bottom: 0.4rem; }}
.action-box-text {{ font-size: 0.85rem; color: {C['text']}; line-height: 1.6; }}
.factor-item {{
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.4rem 0;
    font-size: 0.82rem;
    color: {C['text2']};
    border-bottom: 1px solid {C['border']};
}}
.factor-dot {{ width: 6px; height: 6px; border-radius: 50%; background: {C['amber']}; margin-top: 0.4rem; flex-shrink: 0; }}

/* Domain deep-dive */
.domain-card {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
}}
.domain-stat {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.45rem 0;
    border-bottom: 1px solid {C['border']};
    font-size: 0.82rem;
}}
.domain-stat-label {{ color: {C['text2']}; }}
.domain-stat-value {{ font-weight: 700; color: {C['text']}; font-family: 'DM Mono', monospace; }}

/* Scrollable table containers */
.scroll-table {{ max-height: 320px; overflow-y: auto; }}
.scroll-table::-webkit-scrollbar {{ width: 4px; }}
.scroll-table::-webkit-scrollbar-track {{ background: transparent; }}
.scroll-table::-webkit-scrollbar-thumb {{ background: {C['border']}; border-radius: 2px; }}

/* Divider */
.divider {{ height: 1px; background: {C['border']}; margin: 1rem 0; }}

/* Streamlit button overrides */
div[data-testid="stButton"] > button {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    color: {C['text']};
    border-radius: 8px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    font-size: 0.82rem;
    padding: 0.3rem 0.75rem;
    transition: all 0.15s;
}}
div[data-testid="stButton"] > button:hover {{
    background: {C['accent_light']};
    border-color: {C['accent']};
    color: {C['accent']};
}}
div[data-testid="stButton"] > button[kind="primary"] {{
    background: {C['accent']};
    border-color: {C['accent']};
    color: white;
}}

/* Plotly charts transparent bg */
.js-plotly-plot .plotly .bg {{ fill: transparent !important; }}

/* Expander styling */
[data-testid="stExpander"] {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 12px;
}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "selected_order"  not in st.session_state: st.session_state.selected_order  = None
if "selected_domain" not in st.session_state: st.session_state.selected_domain = None
if "selected_reason" not in st.session_state: st.session_state.selected_reason = None

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING  (cached, re-runs every 5 minutes)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_all_data():
    if not RULES_OK:
        return None, None, None, None, IMPORT_ERROR

    errors = []
    ship_rows, inv_rows, frt_rows, wh_rows = [], [], [], []

    # OLD (Phase 8): each loader was called with its own CSV file path
    # NEW (Phase 7): all four loaders now get the same DB_FILE path
    # The db_loader.py functions know which table to query based on
    # their own function name — load_shipments reads "shipments" table,
    # load_inventory reads "inventory" table, and so on.
    for path, loader, target in [
        (DB_FILE, load_shipments,      "ship"),
        (DB_FILE, load_inventory,      "inv"),
        (DB_FILE, load_freight,        "frt"),
        (DB_FILE, load_warehouse_picks,"wh"),
    ]:
        # OLD: if not os.path.exists(path) checked for each CSV separately
        # NEW: path is now always DB_FILE — we check once if the database exists
        if not os.path.exists(path):
            errors.append(f"Missing: {path}")
            continue
        try:
            data = loader(path)
            if target == "ship": ship_rows = data
            elif target == "inv": inv_rows  = data
            elif target == "frt": frt_rows  = data
            elif target == "wh":  wh_rows   = data
        except Exception as e:
            errors.append(f"Error loading {path}: {e}")

    return ship_rows, inv_rows, frt_rows, wh_rows, errors

@st.cache_data(ttl=300)
def build_shipment_records(ship_rows_frozen):
    ship_rows = list(ship_rows_frozen)
    records = []
    for row in ship_rows:
        status     = assign_delay_status(row, TODAY)
        delay_days = calculate_delay_days(row, TODAY)
        reason     = assign_reason_code(row, TODAY)
        records.append({
            "sales_order_no":     row.get("sales_order_no",""),
            "customer_name":      row.get("customer_name",""),
            "scheduled_pick_date":row.get("scheduled_pick_date",""),
            "ship_confirm_date":  row.get("ship_confirm_date",""),
            "order_status":       row.get("order_status",""),
            "delay_status":       status,
            "delay_days":         delay_days,
            "reason_code":        reason,
            "item_no":            row.get("item_no",""),
        })
    return records

@st.cache_data(ttl=300)
def build_inventory_records(inv_rows_frozen):
    return [
        {**row, "inv_status": assign_inventory_status(row)}
        for row in inv_rows_frozen
    ]

@st.cache_data(ttl=300)
def build_freight_records(frt_rows_frozen):
    records = []
    for row in frt_rows_frozen:
        status     = assign_freight_status(row, TODAY)
        delay_days = calculate_pickup_delay_days(row, TODAY)
        tier       = assign_carrier_tier(row.get("carrier_performance_score",""))
        records.append({**row, "frt_status": status, "pickup_delay_days": delay_days, "carrier_tier": tier})
    return records

@st.cache_data(ttl=300)
def build_warehouse_records(wh_rows_frozen):
    records = []
    for row in wh_rows_frozen:
        health     = assign_pick_health(row, TODAY)
        delay_days = calculate_pick_delay_days(row, TODAY)
        records.append({**row, "pick_health": health, "pick_delay_days": delay_days})
    return records

# ─────────────────────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
REASON_LABELS = {
    "FREIGHT_HOLD":          "Freight Hold",
    "BACKORDER":             "Backorder",
    "INVENTORY_SHORTAGE":    "Inventory Shortage",
    "TRUCK_NOT_AVAILABLE":   "Truck Unavailable",
    "CARRIER_DELAY":         "Carrier Delay",
    "WAREHOUSE_PICK_DELAY":  "Warehouse Pick Delay",
    "UNKNOWN_NEEDS_REVIEW":  "Unknown / Review",
    "NOT_APPLICABLE":        "N/A",
}
DOMAIN_MAP = {
    "FREIGHT_HOLD":         "freight",
    "CARRIER_DELAY":        "freight",
    "TRUCK_NOT_AVAILABLE":  "freight",
    "BACKORDER":            "inventory",
    "INVENTORY_SHORTAGE":   "inventory",
    "WAREHOUSE_PICK_DELAY": "warehouse",
    "UNKNOWN_NEEDS_REVIEW": None,
}

def status_badge(status):
    mapping = {
        "NEED_ACTION": ("badge-red",   "🔴 Need Action"),
        "DELAYED":     ("badge-amber", "🟡 Delayed"),
        "ON_TIME":     ("badge-green", "🟢 On Time"),
        "SHIPPED":     ("badge-blue",  "✅ Shipped"),
        "CANCELLED":   ("badge-grey",  "— Cancelled"),
    }
    cls, label = mapping.get(status, ("badge-grey", status))
    return f'<span class="badge {cls}">{label}</span>'

def inv_badge(status):
    mapping = {
        "HEALTHY":     ("badge-green", "Healthy"),
        "LOW":         ("badge-amber", "Low"),
        "CRITICAL":    ("badge-red",   "Critical"),
        "OUT_OF_STOCK":("badge-red",   "Out of Stock"),
        "ON_BACKORDER":("badge-amber", "Backorder"),
    }
    cls, label = mapping.get(status, ("badge-grey", status))
    return f'<span class="badge {cls}">{label}</span>'

def pick_badge(health):
    mapping = {
        "ON_TRACK": ("badge-green", "On Track"),
        "AT_RISK":  ("badge-amber", "At Risk"),
        "DELAYED":  ("badge-red",   "Delayed"),
    }
    cls, label = mapping.get(health, ("badge-grey", health))
    return f'<span class="badge {cls}">{label}</span>'

def tier_badge(tier):
    mapping = {
        "STRONG":   ("badge-green", "Strong"),
        "AVERAGE":  ("badge-blue",  "Average"),
        "WEAK":     ("badge-amber", "Weak"),
        "CRITICAL": ("badge-red",   "Critical"),
    }
    cls, label = mapping.get(tier, ("badge-grey", tier))
    return f'<span class="badge {cls}">{label}</span>'

def make_plotly_layout(title="", height=280):
    return dict(
        title=title,
        height=height,
        margin=dict(l=10, r=10, t=30 if title else 10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color=C["text2"], size=11),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        xaxis=dict(gridcolor=C["grid"], linecolor=C["border"], tickfont=dict(size=10)),
        yaxis=dict(gridcolor=C["grid"], linecolor=C["border"], tickfont=dict(size=10)),
    )

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
ship_rows, inv_rows, frt_rows, wh_rows, load_errors = load_all_data()

if not RULES_OK:
    st.error(f"⚠️ Could not import rules engines. Make sure PYTHONPATH is set correctly.\n\n`{IMPORT_ERROR}`")
    st.code('$env:PYTHONPATH = "C:\\Users\\preet\\Documents\\AI Work\\supply_chain_mcp_project\\src"')
    st.stop()

if load_errors:
    for e in load_errors:
        st.warning(f"⚠️ {e}")

# Build enriched records (cached)
ship_records = build_shipment_records(tuple(ship_rows)) if ship_rows else []
inv_records  = build_inventory_records(tuple(inv_rows)) if inv_rows else []
frt_records  = build_freight_records(tuple(frt_rows)) if frt_rows else []
wh_records   = build_warehouse_records(tuple(wh_rows)) if wh_rows else []

# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE KPIs
# ─────────────────────────────────────────────────────────────────────────────
total_orders    = len(ship_records)
need_action     = sum(1 for r in ship_records if r["delay_status"] == "NEED_ACTION")
delayed         = sum(1 for r in ship_records if r["delay_status"] == "DELAYED")
on_time         = sum(1 for r in ship_records if r["delay_status"] == "ON_TIME")
shipped         = sum(1 for r in ship_records if r["delay_status"] == "SHIPPED")
cancelled       = sum(1 for r in ship_records if r["delay_status"] == "CANCELLED")

inv_problems    = sum(1 for r in inv_records if r["inv_status"] in ("OUT_OF_STOCK","CRITICAL","ON_BACKORDER"))
frt_problems    = sum(1 for r in frt_records if r["frt_status"] in ("ON_HOLD","PICKUP_MISSED"))
wh_problems     = sum(1 for r in wh_records  if r["pick_health"] in ("DELAYED","AT_RISK"))

risk_level = "LOW"
if need_action > 0: risk_level = "CRITICAL"
elif (delayed / max(total_orders,1)) > 0.3: risk_level = "HIGH"
elif delayed > 0: risk_level = "MEDIUM"

reason_counts = {}
for r in ship_records:
    if r["delay_status"] in ("DELAYED","NEED_ACTION"):
        rc = r["reason_code"]
        reason_counts[rc] = reason_counts.get(rc, 0) + 1

# ─────────────────────────────────────────────────────────────────────────────
# TOP BAR
# ─────────────────────────────────────────────────────────────────────────────
tb_left, tb_right = st.columns([3, 1])
with tb_left:
    risk_icon = {"CRITICAL":"🚨","HIGH":"⚠️","MEDIUM":"⚡","LOW":"✅"}.get(risk_level,"")
    st.markdown(f"""
    <div class="topbar">
      <div class="topbar-left">
        <div class="logo-mark">🏭</div>
        <div>
          <div class="topbar-title">Supply Chain Control Tower</div>
          <div class="topbar-sub">Real-time operations dashboard</div>
        </div>
      </div>
      <div class="topbar-right">
        <span class="date-chip">📅 {TODAY.strftime('%a %d %b %Y')}</span>
        <span class="risk-badge risk-{risk_level}">{risk_icon} {risk_level} RISK</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

with tb_right:
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    toggle_label = "☀️ Light Mode" if st.session_state.dark_mode else "🌙 Dark Mode"
    if st.button(toggle_label, key="theme_toggle"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1 — KPI CARDS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Shipment Overview</div>', unsafe_allow_html=True)

kpi_cols = st.columns(5)
kpis = [
    ("Total Orders",   total_orders, f"{shipped} shipped · {cancelled} cancelled", C["accent"]),
    ("Need Action",    need_action,  ">5 days overdue — act now",                  C["red"]),
    ("Delayed",        delayed,      "1–5 days overdue",                            C["amber"]),
    ("On Time",        on_time,      "Scheduled pick date current",                 C["green"]),
    ("Cross-Domain ⚠", frt_problems + wh_problems, f"Freight {frt_problems} · Warehouse {wh_problems}", C["blue"]),
]
for col, (label, value, sub, color) in zip(kpi_cols, kpis):
    with col:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-accent-bar" style="background:{color}"></div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color}">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1 — CHARTS ROW
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📈 Delay Analysis</div>', unsafe_allow_html=True)
chart_col1, chart_col2, chart_col3 = st.columns([1.2, 1.5, 1.3])

# Donut chart — status breakdown
with chart_col1:
    status_data = {
        "Need Action": need_action,
        "Delayed":     delayed,
        "On Time":     on_time,
        "Shipped":     shipped,
        "Cancelled":   cancelled,
    }
    status_data = {k:v for k,v in status_data.items() if v > 0}
    colors_donut = {
        "Need Action": C["red"],
        "Delayed":     C["amber"],
        "On Time":     C["green"],
        "Shipped":     C["blue"],
        "Cancelled":   C["text3"],
    }
    fig = go.Figure(go.Pie(
        labels=list(status_data.keys()),
        values=list(status_data.values()),
        hole=0.65,
        marker_colors=[colors_donut[k] for k in status_data],
        textinfo="label+value",
        textfont=dict(family="DM Sans", size=11, color=C["text"]),
        hovertemplate="%{label}: %{value} orders<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{total_orders}</b><br><span style='font-size:10px'>orders</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family="DM Sans", size=16, color=C["text"]),
    )
    layout = make_plotly_layout("Order Status", 260)
    layout.update(showlegend=False)
    fig.update_layout(**layout)
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# Bar chart — delay reasons
with chart_col2:
    if reason_counts:
        rc_labels = [REASON_LABELS.get(k, k) for k in reason_counts]
        rc_values = list(reason_counts.values())
        rc_colors = []
        for k in reason_counts:
            if k in ("FREIGHT_HOLD","BACKORDER","INVENTORY_SHORTAGE"):
                rc_colors.append(C["red"])
            elif k in ("CARRIER_DELAY","TRUCK_NOT_AVAILABLE"):
                rc_colors.append(C["amber"])
            else:
                rc_colors.append(C["blue"])
        sorted_pairs = sorted(zip(rc_values, rc_labels, rc_colors), reverse=True)
        rc_values, rc_labels, rc_colors = zip(*sorted_pairs) if sorted_pairs else ([],[],[])

        fig2 = go.Figure(go.Bar(
            x=list(rc_values),
            y=list(rc_labels),
            orientation="h",
            marker_color=list(rc_colors),
            text=list(rc_values),
            textposition="outside",
            textfont=dict(family="DM Mono", size=11, color=C["text"]),
            hovertemplate="%{y}: %{x} orders<extra></extra>",
        ))
        layout2 = make_plotly_layout("Root Cause Breakdown", 260)
        layout2["xaxis"]["showgrid"] = False
        layout2["yaxis"]["showgrid"] = False
        fig2.update_layout(**layout2)
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="panel"><div class="panel-title">Root Cause Breakdown</div><p style="color:{C["text3"]};font-size:0.85rem">No delays found — all orders on time.</p></div>', unsafe_allow_html=True)

# Cross-domain health bars
with chart_col3:
    health_data = [
        ("Inventory Issues",  inv_problems,  len(inv_records),  C["amber"]),
        ("Freight Problems",  frt_problems,  len(frt_records),  C["red"]),
        ("Warehouse At Risk", wh_problems,   len(wh_records),   C["blue"]),
    ]
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="panel-title">🔗 Cross-Domain Health</div>', unsafe_allow_html=True)
    for label, problem, total, color in health_data:
        pct = int((problem / max(total,1)) * 100)
        st.markdown(f"""
        <div style="margin-bottom:1rem">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem">
                <span style="font-size:0.78rem;color:{C['text2']}">{label}</span>
                <span style="font-size:0.78rem;font-weight:700;color:{color};font-family:'DM Mono',monospace">{problem}/{total}</span>
            </div>
            <div style="background:{C['surface2']};border-radius:4px;height:6px;overflow:hidden">
                <div style="background:{color};width:{pct}%;height:100%;border-radius:4px;transition:width 0.5s"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1 — HOT ISSUES TABLE + DOMAIN FILTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">🔥 Active Issues — Click an Order to Investigate</div>', unsafe_allow_html=True)

main_col, side_col = st.columns([1.6, 1])

with main_col:
    # Filter row
    fc1, fc2, fc3 = st.columns([1, 1, 1])
    with fc1:
        status_filter = st.selectbox("Status", ["All", "Need Action", "Delayed", "On Time", "Shipped", "Cancelled"], key="sf")
    with fc2:
        reason_options = ["All"] + [REASON_LABELS.get(k,k) for k in reason_counts.keys()]
        reason_filter  = st.selectbox("Reason", reason_options, key="rf")
    with fc3:
        sort_by = st.selectbox("Sort", ["Delay Days ↓", "Order No.", "Customer"], key="sb")

    # Filter records — start from all records, apply filters, then sort
    status_priority = {"NEED_ACTION": 0, "DELAYED": 1, "ON_TIME": 2, "SHIPPED": 3, "CANCELLED": 4}

    if status_filter != "All":
        status_map = {"Need Action":"NEED_ACTION","Delayed":"DELAYED","On Time":"ON_TIME","Shipped":"SHIPPED","Cancelled":"CANCELLED"}
        tgt = status_map.get(status_filter)
        visible = [r for r in ship_records if r["delay_status"] == tgt]
    else:
        # Default order: problems first, then on-time, shipped, cancelled
        visible = sorted(ship_records, key=lambda x: status_priority.get(x["delay_status"], 9))

    if reason_filter != "All":
        rev_labels = {v:k for k,v in REASON_LABELS.items()}
        tgt_reason = rev_labels.get(reason_filter)
        if tgt_reason:
            visible = [r for r in visible if r["reason_code"] == tgt_reason]

    if sort_by == "Delay Days ↓":
        visible.sort(key=lambda x: x["delay_days"], reverse=True)
    elif sort_by == "Order No.":
        visible.sort(key=lambda x: x["sales_order_no"])
    elif sort_by == "Customer":
        visible.sort(key=lambda x: x["customer_name"])

    # Table header
    st.markdown(f"""
    <div style="display:flex;gap:0.75rem;padding:0.5rem 0.5rem;border-bottom:2px solid {C['border']};margin-bottom:0.25rem">
        <span style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C['text3']};min-width:75px">Order</span>
        <span style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C['text3']};flex:1">Customer</span>
        <span style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C['text3']};min-width:90px">Status</span>
        <span style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C['text3']};min-width:55px;text-align:right">Days Late</span>
        <span style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C['text3']};min-width:130px;text-align:right">Reason</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="scroll-table">', unsafe_allow_html=True)
    for r in visible[:25]:
        days_txt = f"{r['delay_days']}d" if r["delay_days"] > 0 else "—"
        days_color = C["red"] if r["delay_days"] > 5 else (C["amber"] if r["delay_days"] > 0 else C["text3"])
        reason_label = REASON_LABELS.get(r["reason_code"], r["reason_code"])
        st.markdown(f"""
        <div class="order-row">
            <span class="order-no">{r['sales_order_no']}</span>
            <span class="order-customer">{r['customer_name']}</span>
            <span style="min-width:90px">{status_badge(r['delay_status'])}</span>
            <span class="order-days" style="color:{days_color}">{days_txt}</span>
            <span class="order-reason">{reason_label}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Order selector
    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
    order_nos = [r["sales_order_no"] for r in visible[:25]]
    if order_nos:
        sel = st.selectbox("🔍 Select an order to investigate:", ["— pick an order —"] + order_nos, key="order_sel")
        if sel != "— pick an order —":
            st.session_state.selected_order = sel

with side_col:
    # Quick domain navigation
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="panel-title">🗂 Domain Deep Dive</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:0.78rem;color:{C["text3"]};margin-bottom:0.75rem">Click a domain to explore root cause details</div>', unsafe_allow_html=True)

    domains = [
        ("🚛", "Freight & Carriers", "freight",   f"{frt_problems} issue(s)",   C["red"]   if frt_problems else C["green"]),
        ("📦", "Inventory",          "inventory",  f"{inv_problems} issue(s)",   C["amber"] if inv_problems else C["green"]),
        ("🏭", "Warehouse Picks",    "warehouse",  f"{wh_problems} issue(s)",    C["blue"]  if wh_problems  else C["green"]),
        ("📋", "All Shipments",      "shipments",  f"{total_orders} orders",     C["accent"]),
    ]
    for icon, label, domain_key, sub, color in domains:
        is_selected = st.session_state.selected_domain == domain_key
        bg = C["accent_light"] if is_selected else C["surface2"]
        border = C["accent"] if is_selected else C["border"]
        if st.button(f"{icon} {label}  ·  {sub}", key=f"dom_{domain_key}"):
            if st.session_state.selected_domain == domain_key:
                st.session_state.selected_domain = None
            else:
                st.session_state.selected_domain = domain_key
                st.session_state.selected_order   = None
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # Reason code quick-links
    if reason_counts:
        st.markdown('<div class="panel" style="margin-top:0.75rem">', unsafe_allow_html=True)
        st.markdown(f'<div class="panel-title">⚡ Active Delay Reasons</div>', unsafe_allow_html=True)
        for code, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            domain = DOMAIN_MAP.get(code)
            label  = REASON_LABELS.get(code, code)
            if st.button(f"{label}  ·  {count} order{'s' if count>1 else ''}", key=f"rc_{code}"):
                st.session_state.selected_domain = domain
                st.session_state.selected_reason = code
                st.session_state.selected_order  = None
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 2 — DOMAIN DEEP DIVE PANELS
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.selected_domain and not st.session_state.selected_order:
    domain = st.session_state.selected_domain
    st.markdown(f'<div class="section-header">🔬 Domain Detail — {domain.upper()}</div>', unsafe_allow_html=True)

    close_col, _ = st.columns([1, 5])
    with close_col:
        if st.button("✕ Close panel", key="close_domain"):
            st.session_state.selected_domain = None
            st.session_state.selected_reason = None
            st.rerun()

    if domain == "freight":
        d1, d2 = st.columns(2)

        with d1:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">🚛 Freight Status Overview</div>', unsafe_allow_html=True)
            status_buckets = {}
            for r in frt_records:
                s = r["frt_status"]
                status_buckets[s] = status_buckets.get(s, 0) + 1
            for s, cnt in sorted(status_buckets.items(), key=lambda x: -x[1]):
                color = C["red"] if s in ("ON_HOLD","PICKUP_MISSED") else (C["green"] if s=="DELIVERED" else C["text2"])
                st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">{s.replace("_"," ")}</span><span class="domain-stat-value" style="color:{color}">{cnt}</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with d2:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">📊 Carrier Performance</div>', unsafe_allow_html=True)
            carrier_data = {}
            for r in frt_records:
                c = r.get("carrier_name","Unknown")
                if c not in carrier_data:
                    carrier_data[c] = {"tier": r["carrier_tier"], "total": 0, "problems": 0}
                carrier_data[c]["total"] += 1
                if r["frt_status"] in ("ON_HOLD","PICKUP_MISSED","CARRIER_DELAYED"):
                    carrier_data[c]["problems"] += 1
            for carrier, cd in sorted(carrier_data.items(), key=lambda x: -x[1]["problems"]):
                st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">{carrier}</span><span>{tier_badge(cd["tier"])}</span><span class="domain-stat-value">{cd["problems"]}/{cd["total"]} issues</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # Freight details table
        problem_freight = [r for r in frt_records if r["frt_status"] in ("ON_HOLD","PICKUP_MISSED","CARRIER_DELAYED")]
        if problem_freight:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">⚠️ Freight Issues Requiring Action ({len(problem_freight)})</div>', unsafe_allow_html=True)
            for r in problem_freight:
                hold_reason = r.get("freight_hold_reason","") or r.get("freight_notes","") or "—"
                rec = get_freight_recommendation(r["frt_status"], r.get("freight_hold_reason",""), r.get("carrier_name",""), r["pickup_delay_days"])
                st.markdown(f"""
                <div style="border:1px solid {C['border']};border-radius:8px;padding:0.75rem;margin-bottom:0.5rem">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem">
                        <span style="font-family:'DM Mono',monospace;font-size:0.85rem;color:{C['accent']}">{r.get('sales_order_no','')}</span>
                        <span class="badge badge-red">{r['frt_status'].replace('_',' ')}</span>
                    </div>
                    <div style="font-size:0.78rem;color:{C['text3']};margin-bottom:0.35rem">Carrier: <b style="color:{C['text']}">{r.get('carrier_name','')}</b> · {r['pickup_delay_days']}d delay · Hold: {hold_reason}</div>
                    <div style="font-size:0.78rem;color:{C['text2']};background:{C['surface2']};padding:0.5rem;border-radius:6px">{rec}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    elif domain == "inventory":
        d1, d2 = st.columns(2)

        with d1:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">📦 Inventory Health</div>', unsafe_allow_html=True)
            inv_buckets = {}
            for r in inv_records:
                s = r["inv_status"]
                inv_buckets[s] = inv_buckets.get(s, 0) + 1
            order_pref = ["OUT_OF_STOCK","CRITICAL","ON_BACKORDER","LOW","HEALTHY"]
            for s in order_pref:
                if s in inv_buckets:
                    color = C["red"] if s in ("OUT_OF_STOCK","CRITICAL") else (C["amber"] if s in ("ON_BACKORDER","LOW") else C["green"])
                    st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">{s.replace("_"," ")}</span><span class="domain-stat-value" style="color:{color}">{inv_buckets[s]}</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with d2:
            # Inventory bar chart
            if inv_buckets:
                fig_inv = go.Figure(go.Bar(
                    x=list(inv_buckets.keys()),
                    y=list(inv_buckets.values()),
                    marker_color=[C["red"] if k in ("OUT_OF_STOCK","CRITICAL") else (C["amber"] if k in ("ON_BACKORDER","LOW") else C["green"]) for k in inv_buckets],
                    hovertemplate="%{x}: %{y} items<extra></extra>",
                ))
                layout_inv = make_plotly_layout("", 220)
                layout_inv["showlegend"] = False
                fig_inv.update_layout(**layout_inv)
                st.markdown('<div class="domain-card">', unsafe_allow_html=True)
                st.plotly_chart(fig_inv, use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

        problem_inv = [r for r in inv_records if r["inv_status"] in ("OUT_OF_STOCK","CRITICAL","ON_BACKORDER")]
        if problem_inv:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">⚠️ Items Requiring Attention ({len(problem_inv)})</div>', unsafe_allow_html=True)
            for r in problem_inv:
                rec = get_inventory_recommendation(r["inv_status"], r.get("item_no",""), r.get("expected_receipt_date",""))
                st.markdown(f"""
                <div style="border:1px solid {C['border']};border-radius:8px;padding:0.75rem;margin-bottom:0.5rem">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem">
                        <span style="font-family:'DM Mono',monospace;font-size:0.85rem;color:{C['accent']}">{r.get('item_no','')}</span>
                        {inv_badge(r['inv_status'])}
                    </div>
                    <div style="font-size:0.78rem;color:{C['text3']};margin-bottom:0.35rem">{r.get('item_description','')} · {r.get('warehouse_name','')} · Avail: <b style="color:{C['text']}">{r.get('qty_available',0)}</b> · ETA: {r.get('expected_receipt_date','—')}</div>
                    <div style="font-size:0.78rem;color:{C['text2']};background:{C['surface2']};padding:0.5rem;border-radius:6px">{rec}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    elif domain == "warehouse":
        d1, d2 = st.columns(2)

        with d1:
            st.markdown('<div class="domain-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="panel-title">🏭 Pick Health Overview</div>', unsafe_allow_html=True)
            wh_buckets = {}
            for r in wh_records:
                h = r["pick_health"]
                wh_buckets[h] = wh_buckets.get(h, 0) + 1
            for h in ["DELAYED","AT_RISK","ON_TRACK","UNKNOWN"]:
                if h in wh_buckets:
                    color = C["red"] if h=="DELAYED" else (C["amber"] if h=="AT_RISK" else (C["green"] if h=="ON_TRACK" else C["text3"]))
                    st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">{h.replace("_"," ")}</span><span class="domain-stat-value" style="color:{color}">{wh_buckets[h]}</span></div>', unsafe_allow_html=True)
            staffing  = sum(1 for r in wh_records if str(r.get("staffing_flag","NO")).upper()=="YES")
            equipment = sum(1 for r in wh_records if str(r.get("equipment_issue","NO")).upper()=="YES")
            st.markdown(f'<div style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid {C["border"]}">', unsafe_allow_html=True)
            st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">👥 Staffing Issues</span><span class="domain-stat-value" style="color:{C["red"] if staffing else C["green"]}">{staffing}</span></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="domain-stat"><span class="domain-stat-label">🔧 Equipment Issues</span><span class="domain-stat-value" style="color:{C["red"] if equipment else C["green"]}">{equipment}</span></div>', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)

        with d2:
            problem_wh = [r for r in wh_records if r["pick_health"] in ("DELAYED","AT_RISK")]
            if problem_wh:
                st.markdown('<div class="domain-card">', unsafe_allow_html=True)
                st.markdown(f'<div class="panel-title">⚠️ Picks Requiring Attention ({len(problem_wh)})</div>', unsafe_allow_html=True)
                for r in problem_wh:
                    rec = get_pick_recommendation(r, TODAY)
                    st.markdown(f"""
                    <div style="border:1px solid {C['border']};border-radius:8px;padding:0.75rem;margin-bottom:0.5rem">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem">
                            <span style="font-family:'DM Mono',monospace;font-size:0.85rem;color:{C['accent']}">{r.get('sales_order_no','')}</span>
                            {pick_badge(r['pick_health'])}
                        </div>
                        <div style="font-size:0.78rem;color:{C['text3']};margin-bottom:0.35rem">{r.get('warehouse_name','')} · {r['pick_delay_days']}d delay · {r.get('pick_delay_reason','') or 'No reason noted'}</div>
                        <div style="font-size:0.78rem;color:{C['text2']};background:{C['surface2']};padding:0.5rem;border-radius:6px">{rec}</div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

    elif domain == "shipments":
        st.markdown('<div class="domain-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="panel-title">📋 All Shipments ({len(ship_records)})</div>', unsafe_allow_html=True)
        df = pd.DataFrame(ship_records)[["sales_order_no","customer_name","delay_status","delay_days","reason_code","scheduled_pick_date"]]
        df.columns = ["Order","Customer","Status","Days Late","Reason","Pick Date"]
        df["Reason"] = df["Reason"].map(lambda x: REASON_LABELS.get(x,x))
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 3 — ORDER INVESTIGATION PANEL
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.selected_order:
    order_id = st.session_state.selected_order

    # Find the shipment row
    ship_row  = next((r for r in ship_rows if r.get("sales_order_no") == order_id), None)
    ship_rec  = next((r for r in ship_records if r["sales_order_no"] == order_id), None)

    st.markdown(f'<div class="section-header">🔎 Order Investigation — {order_id}</div>', unsafe_allow_html=True)

    close_col2, _ = st.columns([1, 5])
    with close_col2:
        if st.button("✕ Close investigation", key="close_order"):
            st.session_state.selected_order = None
            st.rerun()

    if ship_row and ship_rec:
        # Build full investigation
        item_no = ship_row.get("item_no","")
        inv_row = next((r for r in inv_rows if r.get("item_no") == item_no), {})
        frt_row = next((r for r in frt_rows if r.get("sales_order_no") == order_id), {})
        wh_row  = next((r for r in wh_rows  if r.get("sales_order_no") == order_id), {})

        inv_status   = assign_inventory_status(inv_row) if inv_row else "UNKNOWN"
        frt_status   = assign_freight_status(frt_row, TODAY) if frt_row else "UNKNOWN"
        freight_hold = str(frt_row.get("freight_hold_flag","NO")).upper() == "YES" if frt_row else False
        pick_health  = assign_pick_health(wh_row, TODAY) if wh_row else "UNKNOWN"
        carrier_tier = assign_carrier_tier(frt_row.get("carrier_performance_score","")) if frt_row else "UNKNOWN"

        report = build_investigation_report(
            sales_order_no      = order_id,
            customer_name       = ship_rec["customer_name"],
            scheduled_pick_date = ship_rec["scheduled_pick_date"],
            delay_days          = ship_rec["delay_days"],
            delay_status        = ship_rec["delay_status"],
            shipping_reason     = ship_rec["reason_code"],
            inventory_status    = inv_status,
            freight_status      = frt_status,
            freight_hold        = freight_hold,
            freight_hold_reason = frt_row.get("freight_hold_reason","") if frt_row else "",
            pick_health         = pick_health,
            carrier_tier        = carrier_tier,
            carrier_name        = frt_row.get("carrier_name","Unknown") if frt_row else "Unknown",
        )

        action_rec = build_action_record(
            sales_order_no      = order_id,
            customer_name       = ship_rec["customer_name"],
            scheduled_pick_date = ship_rec["scheduled_pick_date"],
            delay_days          = ship_rec["delay_days"],
            delay_status        = ship_rec["delay_status"],
            root_cause          = report["root_cause"],
            severity            = report["severity"],
            freight_hold        = freight_hold,
            inventory_status    = inv_status,
        )

        severity_colors = {"CRITICAL": C["red"], "HIGH": C["amber"], "MEDIUM": C["blue"], "LOW": C["green"]}
        sev_color = severity_colors.get(report["severity"], C["text3"])
        esc_color = C["red"] if action_rec["escalate"] else C["green"]

        st.markdown(f"""
        <div class="detail-panel">
            <div class="detail-header">
                <div>
                    <div class="detail-order-no">{order_id}</div>
                    <div class="detail-customer">{ship_rec['customer_name']}</div>
                </div>
                <div style="display:flex;gap:0.5rem;flex-wrap:wrap;justify-content:flex-end">
                    {status_badge(ship_rec['delay_status'])}
                    <span class="badge" style="background:{severity_colors.get(report['severity'],C['surface2'])}22;color:{sev_color};border:1px solid {sev_color}33">{report['severity']} SEVERITY</span>
                    {'<span class="badge badge-red">🚨 ESCALATE</span>' if action_rec['escalate'] else '<span class="badge badge-green">✅ No Escalation</span>'}
                    <span class="badge" style="background:{C['surface2']};color:{C['text3']}">Priority {action_rec['priority_score']}/100</span>
                </div>
            </div>
            <div class="detail-grid">
                <div class="detail-field">
                    <div class="detail-field-label">Root Cause</div>
                    <div class="detail-field-value">{REASON_LABELS.get(report['root_cause'], report['root_cause'])}</div>
                </div>
                <div class="detail-field">
                    <div class="detail-field-label">Days Overdue</div>
                    <div class="detail-field-value" style="color:{C['red']}">{ship_rec['delay_days']} day{'s' if ship_rec['delay_days']!=1 else ''}</div>
                </div>
                <div class="detail-field">
                    <div class="detail-field-label">Scheduled Pick Date</div>
                    <div class="detail-field-value">{ship_rec['scheduled_pick_date'] or '—'}</div>
                </div>
                <div class="detail-field">
                    <div class="detail-field-label">Inventory Status</div>
                    <div class="detail-field-value">{inv_status}</div>
                </div>
                <div class="detail-field">
                    <div class="detail-field-label">Freight Status</div>
                    <div class="detail-field-value">{frt_status}</div>
                </div>
                <div class="detail-field">
                    <div class="detail-field-label">Warehouse Pick</div>
                    <div class="detail-field-value">{pick_health}</div>
                </div>
            </div>
            <div class="action-box">
                <div class="action-box-label">👥 Responsible Team: {action_rec['responsible_team']}</div>
                <div class="action-box-text"><b>Recommended Action:</b><br>{action_rec['recommended_action']}</div>
            </div>
            {"" if not action_rec['escalate'] else f'''
            <div style="background:{C["red_light"]};border:1px solid {C["red"]}33;border-radius:10px;padding:1rem;margin-top:0.75rem">
                <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:{C["red"]};margin-bottom:0.4rem">🚨 Escalation Required</div>
                <div style="font-size:0.82rem;color:{C["text"]}">{action_rec["escalation_reason"]}</div>
            </div>
            '''}
        </div>
        """, unsafe_allow_html=True)

        # Contributing factors
        if report.get("contributing_factors"):
            st.markdown(f'<div style="margin-top:0.75rem"><div class="panel-title" style="font-size:0.8rem;color:{C["text2"]}">⚡ Contributing Factors</div>', unsafe_allow_html=True)
            st.markdown('<div class="detail-panel" style="padding:1rem">', unsafe_allow_html=True)
            for factor in report["contributing_factors"]:
                st.markdown(f'<div class="factor-item"><div class="factor-dot"></div><span>{factor}</span></div>', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)

        # Agent signals (collapsible)
        with st.expander("🔬 Raw Agent Signals (for advanced users)"):
            signals = report.get("agent_signals", {})
            sig_col1, sig_col2 = st.columns(2)
            with sig_col1:
                st.markdown(f"**Shipping Reason:** `{signals.get('shipping_reason','—')}`")
                st.markdown(f"**Inventory Status:** `{signals.get('inventory_status','—')}`")
                st.markdown(f"**Freight Hold Active:** `{signals.get('freight_hold_active','—')}`")
            with sig_col2:
                st.markdown(f"**Freight Status:** `{signals.get('freight_status','—')}`")
                st.markdown(f"**Pick Health:** `{signals.get('pick_health','—')}`")
                st.markdown(f"**Carrier:** `{signals.get('carrier_name','—')}` ({signals.get('carrier_tier','—')})")

    else:
        st.warning(f"Could not find order data for {order_id}")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid {C['border']};display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:0.72rem;color:{C['text3']}">Supply Chain Control Tower · Phase 8 Dashboard · Data refreshes every 5 min</span>
    <span style="font-size:0.72rem;color:{C['text3']};font-family:'DM Mono',monospace">{TODAY.strftime('%Y-%m-%d')}</span>
</div>
""", unsafe_allow_html=True)