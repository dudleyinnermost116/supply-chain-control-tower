# Security Policy

## Project: Supply Chain Control Tower
**Owner:** Vishal  
**Repository:** https://github.com/vishal2559/supply-chain-control-tower

---

## Supported Versions

This project is actively maintained. Security fixes are applied to the
latest version on the `main` branch only.

| Version | Supported |
|---------|-----------|
| Latest (main branch) | ✅ Yes |
| Older commits | ❌ No — please update to latest |

---

## Scope — What This Project Protects

This system is a **local AI tool** that runs on your own machine.
It does not expose any public API, web server, or network endpoint.

Security boundaries this project enforces:

1. **No hardcoded secrets** — all paths and settings are in `settings.yaml`
   which is excluded from GitHub via `.gitignore`

2. **No real data on GitHub** — the SQLite database (`supply_chain.db`)
   and memory file (`project_memory.json`) are excluded from GitHub

3. **Input validation** — all MCP tool inputs are validated and sanitised
   before being processed by the rules engine

4. **Prompt injection protection** — all data loaded from CSV or database
   is sanitised before being returned to Claude, preventing instruction
   injection through data fields

5. **Deterministic rules engine** — delay status, reason codes, and priority
   scores are all computed in Python before Claude sees them, so Claude
   cannot hallucinate operational decisions

---

## How to Report a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**
Public issues are visible to everyone immediately.

Instead, report security issues privately:

1. Go to the **Security** tab on this repository
2. Click **"Report a vulnerability"** (GitHub's private reporting feature)
3. Describe what you found and how to reproduce it

I will respond within **72 hours** and aim to release a fix within **7 days**
for confirmed vulnerabilities.

---

## What to Include in Your Report

A good security report includes:

- **Description** — what the vulnerability is
- **Steps to reproduce** — how to trigger it
- **Impact** — what an attacker could do with it
- **Suggested fix** (optional but appreciated)

---

## Out of Scope

The following are **not** security vulnerabilities for this project:

- Issues that only affect your local machine and require physical access
- Denial of service against a local process
- Issues in third-party libraries (report those to the library maintainers)
- Findings from automated scanners with no demonstrated impact

---

## Acknowledgements

Security researchers who responsibly disclose valid vulnerabilities
will be credited in the project's release notes (with their permission).

---

*This security policy follows the
[GitHub coordinated disclosure model](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/about-coordinated-disclosure-of-security-vulnerabilities).*
