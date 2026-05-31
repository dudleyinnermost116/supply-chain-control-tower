# Bring Your Own Data
## How to Connect Your Real Supply Chain Data

---

This guide is for people who want to replace the sample data with
their own real supply chain data. You do not need to be a developer.
If you can export a CSV from your ERP system (SAP, Oracle, NetSuite,
Dynamics, Excel), you can connect it to this system.

---

## Overview — How Data Gets In

```
Your ERP / Excel
      │
      │  Export as CSV
      ▼
Rename columns to match
the expected format
      │
      │  Run the import script
      ▼
SQLite database
(data/supply_chain.db)
      │
      │  Agents read from here
      ▼
Claude Desktop answers
your questions
```

You do this once. After that, whenever your data changes, you
re-export and re-run the import script.

---

## The Five Data Files

The system uses five types of data. You only need to provide the ones
relevant to your operations. Everything else keeps working with
whatever data you do provide.

| File | What it contains | Required? |
|---|---|---|
| shipments.csv | Outbound orders and their status | Yes — core data |
| inventory.csv | Stock levels per item per warehouse | Recommended |
| purchase_orders.csv | Inbound supplier orders | Optional |
| freight.csv | Carrier and pickup records | Optional |
| warehouse_picks.csv | Pick task status per order | Optional |

---

## File 1 — Shipments (Required)

This is the most important file. Every other agent builds on top of it.

### Required columns

| Column name | What it means | Example value |
|---|---|---|
| `sales_order_no` | Your order number | SO10001 |
| `scheduled_pick_date` | Date the order should be picked | 2026-05-20 |
| `order_status` | Current status in your system | OPEN |
| `qty_ordered` | How many units were ordered | 100 |

### Optional but recommended columns

| Column name | What it means | Example value |
|---|---|---|
| `customer_name` | Who the order is for | ABC Corp |
| `item_no` | Item or SKU number | ITEM-1001 |
| `warehouse` | Which warehouse holds this order | WH-01 |
| `ship_confirm_date` | Date it actually shipped (blank if not yet) | 2026-05-21 |
| `qty_allocated` | How many units are allocated | 100 |
| `qty_shipped` | How many units have shipped | 0 |
| `available_inventory` | Units available right now | 50 |
| `backorder_qty` | Units on backorder | 0 |
| `carrier_status` | What the carrier says | ON_TIME |
| `truck_available` | Is a truck assigned? | YES or NO |
| `pick_status` | Has it been picked? | READY |
| `freight_hold_flag` | Is there a freight hold? | YES or NO |
| `line_no` | Order line number | 10 |

### Date format

All dates must be in `YYYY-MM-DD` format. For example: `2026-05-20`

If your ERP exports dates as `20/05/2026` or `May 20 2026`, you need
to reformat them first. The easiest way is in Excel:
1. Select the date column
2. Format Cells → Custom → type `YYYY-MM-DD`
3. Re-export as CSV

### Status values the system understands

For `order_status`: OPEN, SHIPPED, CLOSED, CANCELLED
For `truck_available`: YES or NO
For `pick_status`: READY, IN_PROGRESS, COMPLETE, NOT_STARTED, BLOCKED
For `freight_hold_flag`: YES or NO
For `carrier_status`: ON_TIME, DELAYED

---

## File 2 — Inventory (Recommended)

### Required columns

| Column name | What it means | Example value |
|---|---|---|
| `item_no` | Item or SKU number | ITEM-1001 |
| `qty_available` | Units available right now | 150 |

### Optional but recommended columns

| Column name | What it means | Example value |
|---|---|---|
| `item_description` | Human-readable item name | Surgical Gloves Box 100 |
| `warehouse_id` | Warehouse code | WH-01 |
| `warehouse_name` | Warehouse name | Main Warehouse |
| `qty_on_hand` | Physical units in warehouse | 200 |
| `qty_allocated` | Units reserved for orders | 50 |
| `reorder_point` | Trigger level for reordering | 100 |
| `safety_stock` | Minimum acceptable level | 50 |
| `backorder_flag` | Is this item on backorder? | Y or N |
| `supplier_id` | Your supplier code | SUP-001 |
| `expected_receipt_date` | When supplier will deliver | 2026-06-01 |

---

## File 3 — Purchase Orders (Optional)

### Required columns

| Column name | What it means | Example value |
|---|---|---|
| `po_no` | Your PO number | PO-5001 |
| `supplier_name` | Supplier name | MedSupply Inc |
| `item_no` | Item being ordered | ITEM-1001 |
| `expected_delivery_date` | When it should arrive | 2026-06-01 |
| `po_status` | Current PO status | OPEN |

### Status values: OPEN, LATE, PARTIAL, RECEIVED, CANCELLED

---

## File 4 — Freight (Optional)

### Required columns

| Column name | What it means | Example value |
|---|---|---|
| `freight_id` | Your freight record ID | FR-1001 |
| `sales_order_no` | Links to shipments table | SO10001 |
| `carrier_name` | Carrier company name | FastFreight LLC |
| `pickup_scheduled_date` | When carrier should collect | 2026-05-20 |
| `freight_status` | Current freight status | SCHEDULED |

### Status values: SCHEDULED, IN_TRANSIT, DELIVERED, ON_HOLD, PICKUP_MISSED, CARRIER_DELAYED

### Carrier performance score
A number from 0 to 100 representing carrier reliability.
If you do not track this, set it to 75 for all carriers.
The system will rate them: STRONG (≥85), AVERAGE (≥70), WEAK (≥55), CRITICAL (<55)

---

## File 5 — Warehouse Picks (Optional)

### Required columns

| Column name | What it means | Example value |
|---|---|---|
| `pick_id` | Your pick record ID | WP-2001 |
| `sales_order_no` | Links to shipments table | SO10001 |
| `pick_status` | Current pick status | READY |
| `scheduled_pick_date` | When pick should happen | 2026-05-20 |

### Status values: READY, IN_PROGRESS, COMPLETE, NOT_STARTED, BLOCKED

---

## How to Import Your Data — Step by Step

**Step 1 — Export your data from your ERP or Excel**
Export each dataset as a CSV file. Most ERP systems have a built-in
CSV export. In Excel, File → Save As → CSV (Comma delimited).

**Step 2 — Rename columns to match the expected names**
Open each CSV in Excel. Rename the header row so the column names
match exactly what is listed above. Column names are case-sensitive —
`sales_order_no` works, `Sales_Order_No` does not.

**Step 3 — Fix date formats**
All dates must be YYYY-MM-DD. Check each date column and reformat
if needed (see the Date format section above).

**Step 4 — Save your files into the data\ folder**
Name them exactly:
```
data/shipments.csv
data/inventory.csv
data/purchase_orders.csv
data/freight.csv
data/warehouse_picks.csv
```

Note: these are different from the sample files (`shipments_sample.csv`).
The sample files stay untouched — your real data goes in the files above.

**Step 5 — Run the import script**
```
python scripts/import_data.py
```
This script reads your CSV files, validates the required columns,
and loads the data into the SQLite database. It tells you exactly
how many rows were imported from each file.

**Step 6 — Verify the import**
```
python scripts/setup_project.py
```
The sanity check in Step 6 of the setup script will show you how
many rows are in each table. If the numbers match your CSV row counts,
the import worked correctly.

**Step 7 — Test with a real question**
Open Claude Desktop and ask:
```
"Give me today's management summary"
```
You should see your real order numbers, customer names, and data
in the response — not the sample data anymore.

---

## Refreshing Your Data

When your operational data changes (daily, weekly, or whenever),
re-run the import to update the database:

```
python scripts/import_data.py --replace
```

The `--replace` flag clears the existing data before importing.
Without it, the script skips tables that already have rows.

---

## Troubleshooting

**"Column not found" error**
The column name in your CSV does not match exactly. Check for:
- Extra spaces in the column name
- Different capitalisation (use lowercase with underscores)
- Special characters

**"Date format" error**
Your dates are not in YYYY-MM-DD format. Reformat them in Excel first.

**"0 rows imported"**
The CSV file is empty, or all rows failed validation.
Check that your CSV has a header row and at least one data row.

**Numbers look wrong**
Your quantity columns may contain commas (e.g. `1,000` instead of `1000`).
Remove the comma formatting in Excel before exporting.

---

## What Stays Private

Your operational data (`data/supply_chain.db`) is listed in `.gitignore`
and will never be committed to GitHub. Only the sample CSV files
ship with the repository. Your real data stays on your machine.
