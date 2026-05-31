# Supply Chain Control Tower
### A Self-Learning Multi-Agent AI System Built with Claude MCP

[![Python](https://img.shields.io/badge/Python-3.10-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/Framework-FastMCP-purple.svg)](https://github.com/jlowin/fastmcp)
[![Claude](https://img.shields.io/badge/LLM-Claude_Desktop-orange.svg)](https://claude.ai)
[![Setup](https://img.shields.io/badge/Setup-One_Command-brightgreen.svg)](#quick-start)

> A production-grade, zero-cost, local AI system that monitors supply chain
> operations, investigates root causes across multiple domains simultaneously,
> and **learns from outcomes over time** — running entirely on a single machine
> without any cloud API costs.

---

## What This System Does

You ask it questions in plain English. It answers using your real operational data.

```
You:     "What orders need urgent attention today?"

System:  Queries shipping, inventory, freight, and warehouse data simultaneously.
         Returns all orders delayed more than 5 days, sorted by priority score,
         with responsible team and specific action for each one.

You:     "Why is order SO10003 delayed?"

System:  Investigates across 4 domains simultaneously:
         → Shipping: NEED_ACTION, 8 days overdue
         → Inventory: HEALTHY, 150 units available
         → Freight: ON_HOLD — COMPLIANCE_ISSUE blocking pickup
         → Warehouse: COMPLETE, pick finished 3 days ago
         Root cause: FREIGHT_HOLD (confirmed)
         First action: Contact freight team immediately for hold release.

You:     "What patterns keep causing delays?"

System:  CI Agent scans all historical data, detects recurring patterns,
         scores them by impact and confidence, and adjusts its own future
         behaviour based on whether previous recommendations worked.
```

---

## Architecture — 9 Agents, 49 Tools

```
┌─────────────────────────────────────────────────────────────────┐
│                      Claude Desktop                             │
│               (Natural Language Interface via MCP)              │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────▼───────┐  ┌────────▼───────┐  ┌────────▼───────┐
│Shipping Agent  │  │Inventory Agent │  │   PO Agent     │
│  9 tools       │  │   6 tools      │  │   5 tools      │
│Delay tracking  │  │ Stock levels   │  │Supplier orders │
└────────────────┘  └────────────────┘  └────────────────┘
         │                   │                   │
┌────────▼───────┐  ┌────────▼───────┐  ┌────────▼───────┐
│Freight Agent   │  │Warehouse Agent │  │ Memory Agent   │
│  5 tools       │  │   5 tools      │  │   3 tools      │
│Carrier status  │  │  Pick ops      │  │Cross-session   │
└────────────────┘  └────────────────┘  └────────────────┘
         │                   │
┌────────▼───────────────────▼────────────────────────────┐
│           Investigation Agent — 4 tools                 │
│  Combines all 4 operational domains into one unified    │
│  root cause report per order                            │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│           Recommendation Agent — 4 tools                │
│  Scores every delayed order 0–100 by urgency.           │
│  Assigns responsible team and recommended action.       │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│        CI Agent (Continuous Improvement) — 8 tools      │
│  Detects recurring patterns across all domains.         │
│  Generates scored improvement recommendations.          │
│  LEARNS from outcomes — adjusts its own behaviour.      │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│         Background Scheduler (APScheduler)              │
│  Morning briefing · CI scan · NEED_ACTION monitor       │
│  All automatic — no manual trigger needed               │
└─────────────────────────────────────────────────────────┘
```

---

## What Makes This Novel

Most supply chain AI tools answer one question from one data source.
This system is different across three dimensions:

### 1. True Multi-Domain Investigation
When an order is delayed, the system does not guess. It simultaneously
queries shipping status, inventory levels, freight carrier records,
and warehouse pick operations — then synthesises all four signals into
a single confirmed root cause using a deterministic priority resolver.

### 2. Priority-Scored Action Plans
Every delayed order receives a numeric priority score (0–100):

```
score = min(
    (delay_days × 2)              +   ← up to 40 points
    severity_score                +   ← CRITICAL=30, HIGH=20, MEDIUM=10
    (15 if freight_hold_active)   +   ← physical block always urgent
    (15 if inventory_problem)         ← OUT_OF_STOCK or ON_BACKORDER
    , 100
)
```

The result is a ranked work queue, not just a list of problems.

### 3. Quantitative Self-Learning
The CI Agent tracks outcomes of its own recommendations and adjusts
future behaviour using 8 codified, auditable learning rules:

| Rule | Trigger | Effect |
|---|---|---|
| LR-01 | 5 consecutive rejections of same pattern | Confidence −15% |
| LR-02 | 3 approvals with confirmed improvement | Confidence +10% |
| LR-03 | False positive rate exceeds 20% | Detection threshold raised |
| LR-04 | Owner changed repeatedly | Ownership auto-updated |
| LR-05 | Deferred 5+ times | Priority score reduced |
| LR-06 | Target metric improves 10%+ | Impact score increased |
| LR-07 | No improvement after implementation | Impact score decreased |
| LR-08 | Same issue raised manually 3+ times | Automation flagged |

These are not prompt instructions. They are deterministic, version-controlled
Python rules that change the agent's scoring based on evidence.

---

## Quick Start

### Prerequisites
- Python 3.8 or higher
- [Claude Desktop](https://claude.ai/download)

### One-Command Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/supply-chain-control-tower.git
cd supply-chain-control-tower

# Install all dependencies
pip install -r requirements.txt

# Run the setup script — creates database, loads sample data, verifies everything
python scripts/setup_project.py
```

If all steps show ✓, your system is ready.

### Connect to Claude Desktop

Add the MCP servers to your Claude Desktop configuration.
Full instructions: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

### Try It

Open Claude Desktop and ask:
- *"Read my project memory"*
- *"Give me today's management summary"*
- *"What orders need urgent attention?"*
- *"Investigate order SO10001"*

---

## Using Your Own Data

The sample data uses fictional orders. To use your real supply chain data:

1. Export your operational data as CSV from your ERP (SAP, Oracle, NetSuite, Excel)
2. Rename columns to match the expected format
3. Run `python scripts/import_data.py`

Full guide: [docs/BRING_YOUR_OWN_DATA.md](docs/BRING_YOUR_OWN_DATA.md)

Your real data never leaves your machine — `data/supply_chain.db` is
excluded from Git by `.gitignore`.

---

## Project Structure

```
supply-chain-control-tower/
├── mcp_server/                  ← 9 MCP server files (one per agent)
│   ├── shipping_mcp_server.py
│   ├── inventory_mcp_server.py
│   ├── po_mcp_server.py
│   ├── freight_mcp_server.py
│   ├── warehouse_mcp_server.py
│   ├── investigation_mcp_server.py
│   ├── recommendation_mcp_server.py
│   ├── ci_mcp_server.py
│   └── memory_mcp_server.py
├── src/supply_chain/            ← Business rules and data loaders
├── data/                        ← Sample CSV files (your DB stays private)
├── dashboard/                   ← Streamlit dashboard
├── memory/                      ← Cross-session memory system
├── config/                      ← Central settings (settings.yaml)
├── scripts/                     ← Setup, import, and scheduler utilities
├── docs/                        ← Full documentation
├── requirements.txt             ← All Python dependencies
└── CLAUDE.md                    ← Project instructions for Claude
```

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system design and data flow |
| [docs/AGENTS.md](docs/AGENTS.md) | All 9 agents, all 49 tools |
| [docs/CI_AGENT.md](docs/CI_AGENT.md) | The self-learning system explained |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Every table and column |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Claude Desktop connection guide |
| [docs/BRING_YOUR_OWN_DATA.md](docs/BRING_YOUR_OWN_DATA.md) | Connect your real data |

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Agent framework | FastMCP (MCP Python SDK) | Native Claude Desktop integration |
| LLM interface | Claude Desktop | Local, zero API cost |
| Database | SQLite | Zero infrastructure, runs anywhere |
| Dashboard | Streamlit + Plotly | Fast, interactive, no frontend code |
| Scheduler | APScheduler | Lightweight background job runner |
| Language | Python 3.10 | Readable, beginner-friendly |

---

## Known Limitations and Future Work

Being honest about what this project does not yet do:

**Not yet built:**
- LLM output validation (Claude's narration is not cross-checked against tool data)
- Prompt injection protection (data field values are not sanitised before reaching Claude)
- Data schema validation layer (bad input data is not caught before processing)
- Live database connectors (PostgreSQL, MySQL, SQL Server)
- Email and Slack notification plugins
- Coordinator agent for formal parallel execution

These are documented future work items, not hidden gaps.
Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Build History

| Phase | What Was Built |
|---|---|
| Phase 1 | Shipping Delay Agent — 9 tools, delay tracking and reason codes |
| Phase 2 | Inventory Agent — 6 tools, stock level monitoring |
| Phase 3 | Purchase Order Agent — 5 tools, supplier order tracking |
| Phase 4 | Freight + Warehouse Agents — 10 tools, carrier and pick operations |
| Phase 5 | Investigation Agent — cross-domain root cause analysis |
| Phase 6 | Recommendation Agent — priority-scored action plans |
| Phase 7 | SQLite upgrade — production database replacing CSV files |
| Phase 8 | Streamlit dashboard — visual operations overview |
| Phase 9 | CI Agent — continuous improvement with quantitative self-learning |
| Phase 10 | Enterprise standardisation — memory, scheduler, documentation, GitHub |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
Free to use, modify, and distribute with attribution.

---

## Author

Built by **Vishal** — a supply chain professional who learned AI engineering
by building a production-grade system from scratch, one phase at a time.

> *"The best way to learn multi-agent AI is to build something you actually need."*

---

*If this project helped you, please consider giving it a ⭐ — it helps others find it.*
