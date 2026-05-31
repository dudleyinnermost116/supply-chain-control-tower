# supply_chain/inventory_data_loader.py
#
# Loads and cleans inventory data from CSV.
# Handles type conversion so rules.py always gets clean integers.

import csv


def load_inventory(filepath: str) -> list:
    """
    Loads inventory rows from a CSV file.
    Converts numeric fields to integers so rules can do math on them.
    Returns a list of dictionaries, one per row.
    """
    rows = []

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Convert numeric fields — default to 0 if blank or invalid
            for field in ["qty_on_hand", "qty_allocated",
                          "qty_available", "reorder_point", "safety_stock"]:
                try:
                    row[field] = int(row.get(field, 0) or 0)
                except ValueError:
                    row[field] = 0

            rows.append(row)

    return rows