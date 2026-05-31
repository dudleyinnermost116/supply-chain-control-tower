# supply_chain/po_data_loader.py
#
# Reads purchase_orders_sample.csv and returns a list of dicts.
# Each dict is one PO line with correct data types.
# This follows the exact same pattern as data_loader.py and
# inventory_data_loader.py so the project stays consistent.

import csv


def load_purchase_orders(filepath: str) -> list:
    """
    Reads the purchase orders CSV file and returns a list of dicts.

    Numeric columns are converted to int or float so the rules engine
    never receives a string where it expects a number.

    Returns an empty list if the file cannot be read.
    """
    rows = []

    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Convert numeric columns — same defensive pattern as other loaders
                try:
                    row["qty_ordered"] = int(row.get("qty_ordered", 0) or 0)
                except (ValueError, TypeError):
                    row["qty_ordered"] = 0

                try:
                    row["qty_received"] = int(row.get("qty_received", 0) or 0)
                except (ValueError, TypeError):
                    row["qty_received"] = 0

                try:
                    row["qty_outstanding"] = int(row.get("qty_outstanding", 0) or 0)
                except (ValueError, TypeError):
                    row["qty_outstanding"] = 0

                try:
                    row["unit_cost"] = float(row.get("unit_cost", 0.0) or 0.0)
                except (ValueError, TypeError):
                    row["unit_cost"] = 0.0

                rows.append(row)

    except FileNotFoundError:
        print(f"[po_data_loader] ERROR: File not found: {filepath}")
    except Exception as e:
        print(f"[po_data_loader] ERROR reading file: {e}")

    return rows
