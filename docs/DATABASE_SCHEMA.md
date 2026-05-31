# Database Schema
## supply_chain.db — Complete Reference

---

The project uses a single SQLite database file located at:
```
data/supply_chain.db
```

It contains 12 tables — 5 operational tables used by the supply chain
agents, and 7 CI Agent tables used by the continuous improvement system.

---

## Operational Tables

### 1. shipments

The core table. One row per order line. Used by the Shipping Delay Agent,
Investigation Agent, and Recommendation Agent.

| Column | Type | Description | Example |
|---|---|---|---|
| `sales_order_no` | TEXT | Order number (primary identifier) | SO10001 |
| `line_no` | INTEGER | Line number within the order | 10 |
| `customer_name` | TEXT | Customer name | ABC Corp |
| `item_no` | TEXT | Item or SKU number | ITEM-1001 |
| `warehouse` | TEXT | Warehouse code | WH-01 |
| `scheduled_pick_date` | TEXT | Date order should be picked (YYYY-MM-DD) | 2026-05-20 |
| `ship_confirm_date` | TEXT | Date actually shipped — blank if not yet | 2026-05-21 |
| `order_status` | TEXT | Status from source system | OPEN |
| `qty_ordered` | INTEGER | Units ordered | 100 |
| `qty_allocated` | INTEGER | Units reserved | 100 |
| `qty_shipped` | INTEGER | Units actually shipped | 0 |
| `available_inventory` | INTEGER | Units available right now | 50 |
| `backorder_qty` | INTEGER | Units on backorder | 0 |
| `carrier_status` | TEXT | What the carrier reports | ON_TIME |
| `truck_available` | TEXT | Is a truck assigned? | YES |
| `pick_status` | TEXT | Has the order been picked? | READY |
| `freight_hold_flag` | TEXT | Is there a freight hold? | NO |

**Valid values:**
- `order_status`: OPEN, SHIPPED, CLOSED, CANCELLED
- `truck_available`: YES, NO
- `pick_status`: READY, IN_PROGRESS, COMPLETE, NOT_STARTED, BLOCKED
- `freight_hold_flag`: YES, NO
- `carrier_status`: ON_TIME, DELAYED

---

### 2. inventory

One row per item per warehouse. Used by the Inventory Agent.

| Column | Type | Description | Example |
|---|---|---|---|
| `item_no` | TEXT | Item number (links to shipments) | ITEM-1001 |
| `item_description` | TEXT | Human-readable name | Surgical Gloves Box 100 |
| `warehouse_id` | TEXT | Warehouse code | WH-01 |
| `warehouse_name` | TEXT | Warehouse full name | Main Warehouse |
| `qty_on_hand` | INTEGER | Physical units in warehouse | 500 |
| `qty_allocated` | INTEGER | Units reserved for orders | 480 |
| `qty_available` | INTEGER | On hand minus allocated | 20 |
| `reorder_point` | INTEGER | Trigger level for ordering | 100 |
| `safety_stock` | INTEGER | Minimum acceptable level | 50 |
| `backorder_flag` | TEXT | On backorder from supplier? | N |
| `supplier_id` | TEXT | Supplier code | SUP-001 |
| `expected_receipt_date` | TEXT | When supplier delivers (YYYY-MM-DD) | 2026-06-01 |

**Status logic (assigned by rules engine — not stored):**
- HEALTHY: qty_available ≥ reorder_point
- LOW: qty_available < reorder_point but ≥ safety_stock
- CRITICAL: qty_available < safety_stock
- OUT_OF_STOCK: qty_available = 0
- ON_BACKORDER: backorder_flag = Y

---

### 3. purchase_orders

One row per PO line. Used by the PO Agent.

| Column | Type | Description | Example |
|---|---|---|---|
| `po_no` | TEXT | PO number | PO-5001 |
| `po_line` | INTEGER | Line number within the PO | 10 |
| `supplier_id` | TEXT | Supplier code | SUP-001 |
| `supplier_name` | TEXT | Supplier name | MedSupply Inc |
| `item_no` | TEXT | Item being ordered | ITEM-1001 |
| `item_description` | TEXT | Item name | Surgical Gloves |
| `qty_ordered` | INTEGER | Units ordered from supplier | 500 |
| `qty_received` | INTEGER | Units received so far | 0 |
| `qty_outstanding` | INTEGER | Units still expected | 500 |
| `order_date` | TEXT | When PO was raised (YYYY-MM-DD) | 2026-05-01 |
| `expected_delivery_date` | TEXT | When supplier should deliver | 2026-06-01 |
| `actual_delivery_date` | TEXT | When supplier actually delivered | |
| `po_status` | TEXT | Current PO status | OPEN |
| `unit_cost` | REAL | Cost per unit | 12.50 |
| `sales_order_no` | TEXT | Linked sales order (if applicable) | SO10001 |
| `notes` | TEXT | Free text notes | |

**Valid values for `po_status`:** OPEN, LATE, PARTIAL, RECEIVED, CANCELLED

---

### 4. freight

One row per shipment. Used by the Freight Agent.

| Column | Type | Description | Example |
|---|---|---|---|
| `freight_id` | TEXT | Freight record ID | FR-1001 |
| `sales_order_no` | TEXT | Links to shipments table | SO10001 |
| `carrier_id` | TEXT | Carrier code | CAR-01 |
| `carrier_name` | TEXT | Carrier company name | FastFreight LLC |
| `pickup_scheduled_date` | TEXT | When carrier should collect (YYYY-MM-DD) | 2026-05-20 |
| `pickup_actual_date` | TEXT | When carrier actually collected | 2026-05-20 |
| `delivery_scheduled_date` | TEXT | Expected delivery date | 2026-05-24 |
| `delivery_actual_date` | TEXT | Actual delivery date | 2026-05-24 |
| `freight_status` | TEXT | Current freight status | SCHEDULED |
| `freight_hold_flag` | TEXT | Is there a hold? | NO |
| `freight_hold_reason` | TEXT | Why is it on hold? | PAYMENT_DISPUTE |
| `carrier_performance_score` | INTEGER | 0-100 reliability score | 92 |
| `truck_available` | TEXT | Is a truck assigned? | YES |
| `driver_assigned` | TEXT | Is a driver assigned? | YES |
| `trailer_no` | TEXT | Trailer identifier | TRL-441 |
| `origin_warehouse` | TEXT | Pickup location | WH-01 |
| `destination` | TEXT | Delivery location | Chicago IL |
| `freight_notes` | TEXT | Free text notes | On time delivery |

**Valid values for `freight_status`:**
SCHEDULED, IN_TRANSIT, DELIVERED, ON_HOLD, PICKUP_MISSED, CARRIER_DELAYED

**Carrier tier thresholds:**
- STRONG: score ≥ 85
- AVERAGE: score ≥ 70
- WEAK: score ≥ 55
- CRITICAL: score < 55

---

### 5. warehouse_picks

One row per pick task. Used by the Warehouse Agent.

| Column | Type | Description | Example |
|---|---|---|---|
| `pick_id` | TEXT | Pick task ID | WP-2001 |
| `sales_order_no` | TEXT | Links to shipments table | SO10001 |
| `warehouse_id` | TEXT | Warehouse code | WH-01 |
| `warehouse_name` | TEXT | Warehouse full name | Main Warehouse |
| `item_no` | TEXT | Item being picked | ITEM-1001 |
| `qty_to_pick` | INTEGER | Units that need to be picked | 50 |
| `qty_picked` | INTEGER | Units actually picked so far | 50 |
| `pick_status` | TEXT | Current pick status | COMPLETE |
| `pick_priority` | TEXT | How urgent is this pick? | NORMAL |
| `assigned_picker` | TEXT | Who is picking this? | John S |
| `pick_start_time` | TEXT | When picking started | 2026-05-20 08:15 |
| `pick_complete_time` | TEXT | When picking finished | 2026-05-20 09:45 |
| `scheduled_pick_date` | TEXT | Date pick should happen (YYYY-MM-DD) | 2026-05-20 |
| `pick_delay_reason` | TEXT | Why is it delayed? | SYSTEM_ERROR |
| `equipment_issue` | TEXT | Equipment problem flagged? | NO |
| `staffing_flag` | TEXT | Staffing shortage flagged? | NO |
| `zone` | TEXT | Warehouse zone | A |
| `pick_notes` | TEXT | Free text notes | Completed on time |

**Valid values for `pick_status`:** READY, IN_PROGRESS, COMPLETE, NOT_STARTED, BLOCKED
**Valid values for `pick_priority`:** NORMAL, HIGH, URGENT
**Valid values for `equipment_issue` and `staffing_flag`:** YES, NO

---

## CI Agent Tables

These 7 tables are managed exclusively by the CI Agent.
Do not write to them manually — the CI Agent manages them through its tools.

| Table | What it stores |
|---|---|
| `ci_signals` | Detected patterns from each scan |
| `ci_recommendations` | Generated improvement recommendations |
| `ci_approval_requests` | Recommendations awaiting human review |
| `ci_action_items` | Approved recommendations in progress |
| `ci_outcomes` | Results logged after actions are taken |
| `ci_learning_rules` | History of learning rule firings |
| `ci_pattern_stats` | Per-pattern confidence and scoring adjustments |

---

## How Tables Link Together

```
shipments.sales_order_no
    │
    ├── freight.sales_order_no        (one shipment → one freight record)
    ├── warehouse_picks.sales_order_no (one shipment → one pick record)
    └── shipments.item_no
              │
              └── inventory.item_no   (one item → one inventory row per warehouse)
                        │
                        └── purchase_orders.item_no (one item → multiple POs)
```

The Investigation Agent uses these links to pull data from all four
domains simultaneously when investigating a single order.
