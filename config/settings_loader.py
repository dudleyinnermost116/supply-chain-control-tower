# =============================================================================
# config\settings_loader.py
# Supply Chain Control Tower — Settings Loader
# =============================================================================
#
# PURPOSE:
#   This file reads config\settings.yaml and makes its values available
#   to every MCP server in the project.
#
#   The MCP servers do NOT read the YAML file directly. They call this
#   loader instead, which handles all the file-reading logic in one place.
#
# HOW IT WORKS:
#   1. This file finds the settings.yaml relative to the project root.
#   2. It reads and parses the YAML into a Python dictionary.
#   3. It exposes two things:
#        - get_settings()  → returns the full settings dictionary
#        - get_data_path() → returns a fully resolved file path for a named CSV
#
# HOW TO USE IN AN MCP SERVER:
#   Replace this:
#     DATA_FILE = r"C:\Users\preet\...\shipments_sample.csv"
#
#   With this:
#     from config.settings_loader import get_data_path
#     DATA_FILE = get_data_path("shipments")
#
#   That's the entire change needed per server. One import, one line.
#
# DEPENDENCIES:
#   PyYAML — install with: pip install pyyaml
#   This is the standard Python library for reading YAML files.
#
# =============================================================================

import os       # os gives us tools for working with file paths and directories
import yaml     # yaml lets us read .yaml files into Python dictionaries


# =============================================================================
# STEP 1: FIND THE PROJECT ROOT
# =============================================================================
#
# We need to know WHERE the project folder is so we can find settings.yaml.
#
# __file__ is a special Python variable that holds the full path to THIS file.
# So if this file is at:
#   C:\...\supply_chain_mcp_project\config\settings_loader.py
# Then __file__ = "C:\...\supply_chain_mcp_project\config\settings_loader.py"
#
# os.path.dirname(__file__) strips the filename and gives us the folder:
#   "C:\...\supply_chain_mcp_project\config"
#
# os.path.dirname(...) again goes one level up to the project root:
#   "C:\...\supply_chain_mcp_project"
#
# os.path.abspath() converts it to an absolute path, resolving any ".." parts.
# This makes the path reliable regardless of where Python was launched from.

_THIS_FILE_FOLDER = os.path.dirname(os.path.abspath(__file__))
# _THIS_FILE_FOLDER is now: ...\supply_chain_mcp_project\config

PROJECT_ROOT = os.path.dirname(_THIS_FILE_FOLDER)
# PROJECT_ROOT is now: ...\supply_chain_mcp_project

# The full path to settings.yaml, built by joining the config folder + filename.
SETTINGS_FILE = os.path.join(_THIS_FILE_FOLDER, "settings.yaml")


# =============================================================================
# STEP 2: CACHE — ONLY READ THE FILE ONCE
# =============================================================================
#
# Reading a file from disk every single time a tool is called would be slow
# and wasteful. Instead, we use a "cache" pattern:
#
#   _settings_cache starts as None (meaning "not loaded yet").
#   The first time get_settings() is called, we read the file and store
#   the result in _settings_cache.
#   Every call after that just returns the cached value instantly —
#   no file reading needed.
#
# This is called "lazy loading" — we only do the work when it's first needed.

_settings_cache = None


# =============================================================================
# STEP 3: THE MAIN FUNCTION — get_settings()
# =============================================================================

def get_settings() -> dict:
    """
    Returns the full settings dictionary loaded from config/settings.yaml.

    The file is only read once — subsequent calls return the cached version.
    If the file is missing, a clear error message is shown with instructions.

    Returns:
        dict — the complete settings from settings.yaml

    Raises:
        FileNotFoundError — if settings.yaml cannot be found
        yaml.YAMLError    — if settings.yaml has a formatting error
    """
    global _settings_cache
    # `global` tells Python we're referring to the _settings_cache
    # variable defined above, not creating a new local one.

    # If we've already loaded the settings, return them immediately.
    if _settings_cache is not None:
        return _settings_cache

    # First time: check that the file actually exists before trying to open it.
    if not os.path.exists(SETTINGS_FILE):
        raise FileNotFoundError(
            f"\n\n[settings_loader] ERROR: settings.yaml not found.\n"
            f"Expected location: {SETTINGS_FILE}\n\n"
            f"To fix this:\n"
            f"  1. Make sure settings.yaml is in your config\\ folder.\n"
            f"  2. Check that PROJECT_ROOT is correct: {PROJECT_ROOT}\n"
        )

    # Open and read the YAML file.
    # "r" means read-only. "utf-8" handles international characters safely.
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        # yaml.safe_load() parses the YAML text into a Python dictionary.
        # We use safe_load (not load) because it's more secure —
        # it won't execute any code embedded in the YAML file.
        loaded = yaml.safe_load(f)

    # If the file exists but is empty, yaml.safe_load returns None.
    # We treat that the same as a missing file.
    if loaded is None:
        raise ValueError(
            f"[settings_loader] ERROR: settings.yaml is empty.\n"
            f"File location: {SETTINGS_FILE}"
        )

    # Store in cache so we never read the file again.
    _settings_cache = loaded
    return _settings_cache


# =============================================================================
# STEP 4: CONVENIENCE FUNCTION — get_data_path()
# =============================================================================
#
# This is what MCP servers will actually call. It takes a short name like
# "shipments" and returns the full absolute path to that CSV file.
#
# HOW IT BUILDS THE PATH:
#   base  = settings["paths"]["base"]         → "C:\...\supply_chain_mcp_project"
#   rel   = settings["paths"]["data"]["shipments"] → "data\shipments_sample.csv"
#   full  = os.path.join(base, rel)           → "C:\...\data\shipments_sample.csv"
#
# The result is a complete, usable file path string.

def get_data_path(name: str) -> str:
    """
    Returns the full absolute file path for a named data file.

    Args:
        name: the key from settings.yaml under paths.data
              Valid values: "shipments", "inventory", "purchase_orders",
                            "freight", "warehouse"

    Returns:
        str — full absolute path to the CSV file

    Raises:
        KeyError — if the name doesn't exist in settings.yaml
        FileNotFoundError — if the resolved file doesn't exist on disk

    Example:
        get_data_path("shipments")
        → "C:\\Users\\preet\\...\\data\\shipments_sample.csv"
    """
    settings = get_settings()

    # Navigate into the nested dictionary: paths → data → name
    try:
        base = settings["paths"]["base"]
        relative_path = settings["paths"]["data"][name]
    except KeyError:
        raise KeyError(
            f"[settings_loader] ERROR: '{name}' is not defined under paths.data "
            f"in settings.yaml.\n"
            f"Valid names are: {list(settings['paths']['data'].keys())}"
        )

    # os.path.join combines the base path and relative path correctly
    # on both Windows and Mac (handles slashes automatically).
    full_path = os.path.join(base, relative_path)

    # Warn clearly if the file doesn't exist — better than a cryptic CSV error later.
    if not os.path.exists(full_path):
        raise FileNotFoundError(
            f"[settings_loader] ERROR: Data file not found.\n"
            f"  Name requested: '{name}'\n"
            f"  Resolved path:  {full_path}\n\n"
            f"To fix this:\n"
            f"  1. Check that paths.base is correct in settings.yaml.\n"
            f"  2. Check that paths.data.{name} matches your actual filename.\n"
        )

    return full_path


# =============================================================================
# STEP 5: CONVENIENCE FUNCTION — get_database_path()
# =============================================================================
#
# Separate function for the SQLite database path (used in Phase 7+).
# Works the same way as get_data_path() but for the database file.

def get_database_path() -> str:
    """
    Returns the full absolute path to the SQLite database file.

    Returns:
        str — full path to supply_chain.db
    """
    settings = get_settings()
    base = settings["paths"]["base"]
    db_relative = settings["paths"]["database"]
    return os.path.join(base, db_relative)


# =============================================================================
# STEP 6: CONVENIENCE FUNCTION — get_threshold()
# =============================================================================
#
# Makes it easy to read a single threshold value by name, without
# having to navigate the full nested dictionary every time.

def get_threshold(key: str):
    """
    Returns a value from the thresholds section of settings.yaml.

    Args:
        key: a dot-separated path into the thresholds section.
             Examples:
               "delay.delayed_max_days"   → 5
               "escalation_threshold"     → 70
               "risk.high_delay_pct"      → 0.30

    Returns:
        The value (int, float, etc.)

    Example usage in a rules file:
        from config.settings_loader import get_threshold
        MAX_DELAYED = get_threshold("delay.delayed_max_days")
    """
    settings = get_settings()
    thresholds = settings.get("thresholds", {})

    # Support dot notation: "delay.delayed_max_days" → navigate nested dict
    parts = key.split(".")
    current = thresholds
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(
                f"[settings_loader] Threshold key '{key}' not found in settings.yaml.\n"
                f"Available top-level keys: {list(thresholds.keys())}"
            )
    return current


# =============================================================================
# STEP 7: CONVENIENCE FUNCTION — get_ci_settings()
# =============================================================================
#
# Returns the entire CI agent settings block as a dictionary.
# Used by the CI agent's learning engine and recommendation generator.

def get_ci_settings() -> dict:
    """
    Returns the CI agent settings block from settings.yaml.

    Returns:
        dict — everything under the 'ci' key in settings.yaml
    """
    settings = get_settings()
    return settings.get("ci", {})


# =============================================================================
# STEP 8: CONVENIENCE FUNCTION — is_agent_enabled()
# =============================================================================
#
# Used by the coordinator agent (Phase 10 Step 7) to decide which
# agents to route requests to.

def is_agent_enabled(agent_name: str) -> bool:
    """
    Returns True if the named agent is enabled in settings.yaml.

    Args:
        agent_name: one of the keys under 'agents' in settings.yaml
                    e.g. "shipping_delay", "inventory", "freight"

    Returns:
        bool — True if enabled, False if disabled
    """
    settings = get_settings()
    agents = settings.get("agents", {})
    return agents.get(agent_name, False)


# =============================================================================
# STEP 9: RELOAD FUNCTION — reload_settings()
# =============================================================================
#
# If you change settings.yaml while the servers are running, normally
# you'd have to restart everything. This function clears the cache so
# the next call to get_settings() re-reads the file.
#
# Usage: from config.settings_loader import reload_settings
#        reload_settings()

def reload_settings():
    """
    Clears the settings cache so the next call to get_settings() will
    re-read settings.yaml from disk.

    Use this if you edit settings.yaml while MCP servers are running
    and don't want to restart them.
    """
    global _settings_cache
    _settings_cache = None
    print("[settings_loader] Settings cache cleared. Next call will reload from disk.")


# =============================================================================
# QUICK SELF-TEST — runs only when you execute this file directly
# =============================================================================
#
# If you run:  python config\settings_loader.py
# from your project root, this block will execute and show you a summary
# of what was loaded. It will NOT run when imported by an MCP server.
#
# __name__ == "__main__" is True only when the file is run directly,
# not when it is imported by another file.

if __name__ == "__main__":
    print("=" * 60)
    print("settings_loader.py — self-test")
    print("=" * 60)

    try:
        s = get_settings()
        print(f"\n✓ Settings loaded successfully from:\n  {SETTINGS_FILE}\n")

        print(f"  Project:  {s['project']['name']} v{s['project']['version']}")
        print(f"  Owner:    {s['project']['owner']}")
        print(f"  Phase:    {s['project']['phase']}")
        print()

        print("  Data paths:")
        for name, rel in s["paths"]["data"].items():
            try:
                full = get_data_path(name)
                exists = "✓" if os.path.exists(full) else "✗ FILE NOT FOUND"
                print(f"    {name:<20} {exists}")
                print(f"    {'':20} {full}")
            except FileNotFoundError as e:
                print(f"    {name:<20} ✗ FILE NOT FOUND")
        print()

        print(f"  Delay thresholds:")
        print(f"    DELAYED_MAX_DAYS:    {get_threshold('delay.delayed_max_days')}")
        print(f"    ESCALATION_SCORE:   {s['thresholds']['escalation_threshold']}")
        print(f"    HIGH_RISK_PCT:      {get_threshold('risk.high_delay_pct')}")
        print()

        print("  Agents enabled:")
        for agent, enabled in s["agents"].items():
            status = "✓ enabled" if enabled else "✗ disabled"
            print(f"    {agent:<25} {status}")

        print()
        print("  Database path:")
        try:
            db_path = get_database_path()
            exists = "✓" if os.path.exists(db_path) else "✗ FILE NOT FOUND"
            print(f"    supply_chain.db      {exists}")
            print(f"    {'':20} {db_path}")
        except Exception as e:
            print(f"    ✗ ERROR: {e}")

        print()
        print("Self-test complete. ✓")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
