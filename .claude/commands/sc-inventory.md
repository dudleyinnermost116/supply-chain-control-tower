# /inventory
# Supply Chain Control Tower — Inventory Health Command
# ======================================================
#
# WHAT THIS COMMAND DOES:
#   Gives a complete picture of current stock health —
#   what is healthy, what is dangerously low, and what
#   is waiting on supplier delivery.
#
# TOOLS CALLED (in this order):
#   1. get_inventory_summary    — from inventory-agent
#      Returns counts of items in each status category:
#        HEALTHY, LOW, CRITICAL, OUT_OF_STOCK, ON_BACKORDER
#      Also returns a list of all problem items (anything that is
#      not HEALTHY) with their expected receipt dates.
#
#   2. get_backordered_items    — from inventory-agent
#      Returns all items currently on backorder — items where
#      the supplier has not yet delivered and stock is depleted.
#      Sorted by expected receipt date so the most urgent gaps
#      appear first.
#
# WHY TWO TOOLS:
#   get_inventory_summary gives the full health picture across all items.
#   get_backordered_items focuses specifically on supplier gaps — the items
#   you cannot ship because stock hasn't arrived yet.
#   Together they answer: "What do we have, what are we out of,
#   and what are we waiting on?"
#
# WHEN TO USE:
#   When orders are being delayed due to BACKORDER or INVENTORY_SHORTAGE.
#   Weekly procurement review to check what needs reordering.
#   Before a customer call to know if their item is in stock.
#   Any time someone asks "how is our inventory looking?"

Run the inventory health check for the Supply Chain Control Tower.

Step 1: Call get_inventory_summary from the inventory-agent.
Step 2: Call get_backordered_items from the inventory-agent.
Step 3: Present the combined results using this format:

---
## 📦 Inventory Health Report — [today's date]

### Stock Status Overview
- Total items tracked: [total_items]
- ✓ Healthy: [HEALTHY count]
- ⚠️ Low: [LOW count]
- 🔴 Critical: [CRITICAL count]
- ✗ Out of stock: [OUT_OF_STOCK count]
- 🔄 On backorder: [ON_BACKORDER count]

### Problem Items
[For each problem item in get_inventory_summary show:]
  - [item_no] — [item_description]
  - Warehouse: [warehouse_name] | Available: [qty_available] units
  - Status: [status]
  - Expected receipt: [expected_receipt_date or "Not confirmed"]

[If no problem items, say "✓ All items are at healthy stock levels."]

### Backordered Items — Waiting on Supplier
[For each backordered item show:]
  - [item_no] — [item_description]
  - Warehouse: [warehouse_name]
  - On hand: [qty_on_hand] | Allocated: [qty_allocated] | Available: [qty_available]
  - Expected receipt: [expected_receipt_date or "Not confirmed"]
  - Status: [inventory_status]

[If no backorders, say "✓ No items currently on backorder."]

### Summary
[If any OUT_OF_STOCK or CRITICAL items exist, say:]
"⚠️ [count] item(s) are out of stock or critical. Raise purchase orders immediately."
[If any backorders exist, say:]
"🔄 [count] item(s) are on backorder. Follow up with suppliers for firm delivery dates."
[If everything is healthy, say:]
"✓ Inventory health is good. No immediate action required."
---
