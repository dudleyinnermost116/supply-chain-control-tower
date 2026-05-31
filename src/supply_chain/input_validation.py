# supply_chain/input_validation.py
#
# Owner: Vishal
# Purpose: Central input validation and sanitisation for all MCP tools.
#
# WHY THIS FILE EXISTS:
#   Every MCP tool that accepts input from Claude (like a sales order number
#   or a status string) needs to check that input before using it.
#   Instead of writing the same check in every tool, we write it once here
#   and import it everywhere.
#
# WHAT IT PROTECTS AGAINST:
#   1. Inputs that are too long — no order number should be 10,000 characters
#   2. Inputs with dangerous characters — SQL injection, shell injection
#   3. Empty or missing inputs that would cause confusing errors later
#   4. Inputs that don't match the expected format for known fields
#
# HOW TO USE IT IN ANY MCP SERVER:
#   from supply_chain.input_validation import sanitise_input, ValidationError
#
#   result = sanitise_input(sales_order_no, field_name="sales_order_no", max_length=20)
#   if "error" in result:
#       return result   # Return the error dict immediately, stop processing
#
# ================================================================

import re


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

# Maximum allowed length for any string input.
# A real sales order number is something like "SO-1003" — 7 characters.
# We allow up to 100 to be generous, but 10,000 is clearly an attack.
DEFAULT_MAX_LENGTH = 100

# Characters that are safe in any input field.
# This allows: letters, numbers, spaces, hyphens, underscores, dots, slashes.
# It BLOCKS: semicolons, quotes, angle brackets, backticks, etc.
# Those characters are used in SQL injection and shell injection attacks.
SAFE_CHARACTERS_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-\_\.\/]+$")

# Known valid values for specific fields.
# If a field is in this dict, only these values are accepted.
ALLOWED_VALUES = {
    "delay_status": [
        "ON_TIME", "DELAYED", "NEED_ACTION", "SHIPPED", "CANCELLED"
    ],
    "inventory_status": [
        "HEALTHY", "LOW", "CRITICAL", "OUT_OF_STOCK", "ON_BACKORDER"
    ],
    "reason_code": [
        "FREIGHT_HOLD", "BACKORDER", "INVENTORY_SHORTAGE",
        "TRUCK_NOT_AVAILABLE", "CARRIER_DELAY", "WAREHOUSE_PICK_DELAY",
        "UNKNOWN_NEEDS_REVIEW", "NOT_APPLICABLE"
    ],
    "freight_status": [
        "SCHEDULED", "IN_TRANSIT", "DELIVERED", "ON_HOLD",
        "PICKUP_MISSED", "CARRIER_DELAYED"
    ],
    "pick_health": [
        "ON_TRACK", "AT_RISK", "DELAYED", "UNKNOWN"
    ],
}


# ── VALIDATION ERROR FORMAT ───────────────────────────────────────────────────

def _error(field_name: str, message: str) -> dict:
    """
    Returns a standardised error dict.

    All MCP tools return dicts. When validation fails, we return this
    structured error dict so Claude can read a clear error message
    instead of seeing a Python crash.

    Example output:
      {"error": "Invalid input for 'sales_order_no': Input cannot be empty."}
    """
    return {"error": f"Invalid input for '{field_name}': {message}"}


# ── MAIN VALIDATION FUNCTION ──────────────────────────────────────────────────

def sanitise_input(
    value,
    field_name: str = "input",
    max_length: int = DEFAULT_MAX_LENGTH,
    allow_spaces: bool = True,
) -> dict:
    """
    Validates and sanitises a single string input from a tool call.

    PARAMETERS:
      value        — the raw input from Claude (could be anything)
      field_name   — name of the field being validated (used in error messages)
      max_length   — maximum number of characters allowed (default 100)
      allow_spaces — whether to allow spaces in the value (default True)

    RETURNS:
      On success: {"value": cleaned_string}
        — the cleaned value, ready to use safely

      On failure: {"error": "explanation"}
        — the tool should return this dict immediately and stop processing

    USAGE EXAMPLE:
      result = sanitise_input(sales_order_no, field_name="sales_order_no")
      if "error" in result:
          return result      # Stop here, return the error to Claude
      clean_order = result["value"]   # Safe to use
    """

    # ── Step 1: Check it is actually a string ─────────────────────────────────
    # Inputs could be None, an integer, or something else unexpected.
    # We convert to string first, then check it is not empty.

    if value is None:
        return _error(field_name, "Input cannot be empty.")

    # Convert to string — handles cases where Claude passes an integer
    raw = str(value)

    # ── Step 2: Strip leading and trailing whitespace ─────────────────────────
    # "  SO-1003  " becomes "SO-1003"
    # This is just good hygiene — users often have accidental spaces.
    cleaned = raw.strip()

    # ── Step 3: Reject if empty after stripping ───────────────────────────────
    if not cleaned:
        return _error(field_name, "Input cannot be empty or just whitespace.")

    # ── Step 4: Reject if too long ────────────────────────────────────────────
    # A real order number is ~7 characters. 100 is very generous.
    # If someone passes 1,000 characters, it is almost certainly an attack.
    if len(cleaned) > max_length:
        return _error(
            field_name,
            f"Input is too long ({len(cleaned)} characters). Maximum allowed: {max_length}."
        )

    # ── Step 5: Check for dangerous characters ────────────────────────────────
    # We only allow safe characters: letters, numbers, spaces, hyphens,
    # underscores, dots, and forward slashes.
    #
    # Characters we block and why:
    #   '  "   — used in SQL injection: WHERE name = 'x' OR '1'='1'
    #   ;       — used to chain SQL commands: SELECT *; DROP TABLE;
    #   <  >    — used in HTML/script injection: <script>alert(1)</script>
    #   `       — used in shell injection: `rm -rf /`
    #   \       — used in path traversal: ..\..\secret.txt (we allow /)
    #   ( )     — used in function injection: sleep(10)
    #   |       — used in shell piping: cat file | mail attacker
    #   &       — used in shell background execution
    #   $       — used in shell variable expansion: $HOME

    if not allow_spaces:
        # For fields like status codes that should never have spaces
        check_pattern = re.compile(r"^[a-zA-Z0-9\-\_\.\/]+$")
    else:
        check_pattern = SAFE_CHARACTERS_PATTERN

    if not check_pattern.match(cleaned):
        # Find which characters are actually invalid for a helpful message
        bad_chars = set(
            char for char in cleaned
            if not re.match(r"[a-zA-Z0-9\s\-\_\.\/]", char)
        )
        return _error(
            field_name,
            f"Input contains invalid characters: {bad_chars}. "
            "Only letters, numbers, spaces, hyphens, underscores, dots, and slashes are allowed."
        )

    # ── Step 6: If this field has a known allowed-values list, check it ───────
    # For example, delay_status must be exactly one of 5 known values.
    # Normalise to uppercase first so "delayed" matches "DELAYED".
    normalised = cleaned.upper().replace(" ", "_")

    if field_name in ALLOWED_VALUES:
        allowed = ALLOWED_VALUES[field_name]
        if normalised not in allowed:
            return _error(
                field_name,
                f"'{cleaned}' is not a valid value. "
                f"Allowed values are: {', '.join(allowed)}"
            )
        # Return the normalised version so tools don't have to normalise themselves
        return {"value": normalised}

    # ── All checks passed ─────────────────────────────────────────────────────
    return {"value": cleaned}


# ── INTEGER VALIDATION ────────────────────────────────────────────────────────

def sanitise_integer(
    value,
    field_name: str = "input",
    min_value: int = 0,
    max_value: int = 100_000,
) -> dict:
    """
    Validates an integer input (like qty_needed in check_inventory_for_order).

    PARAMETERS:
      value      — raw input from Claude
      field_name — name of the field (for error messages)
      min_value  — minimum acceptable value (default 0)
      max_value  — maximum acceptable value (default 100,000)

    RETURNS:
      On success: {"value": integer}
      On failure: {"error": "explanation"}

    USAGE EXAMPLE:
      result = sanitise_integer(qty_needed, field_name="qty_needed", min_value=1)
      if "error" in result:
          return result
      clean_qty = result["value"]
    """

    if value is None:
        return _error(field_name, "Value cannot be empty.")

    # Try converting to integer
    try:
        as_int = int(value)
    except (ValueError, TypeError):
        return _error(field_name, f"'{value}' is not a valid number.")

    # Check range
    if as_int < min_value:
        return _error(field_name, f"Value {as_int} is below minimum allowed ({min_value}).")
    if as_int > max_value:
        return _error(field_name, f"Value {as_int} exceeds maximum allowed ({max_value}).")

    return {"value": as_int}
