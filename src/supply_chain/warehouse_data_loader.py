# supply_chain/warehouse_data_loader.py
#
# Reads warehouse_sample.csv and returns a list of dicts.
# Follows the same pattern as all other data loaders in this project.

import csv


def load_warehouse_picks(filepath: str) -> list:
    """
    Reads the warehouse picks CSV and returns a list of row dicts.
    Converts qty columns to int so rules engine never gets strings.
    Returns an empty list if the file cannot be read.
    """
    rows = []

    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col in ["qty_to_pick", "qty_picked"]:
                    try:
                        row[col] = int(row.get(col, 0) or 0)
                    except (ValueError, TypeError):
                        row[col] = 0
                rows.append(row)

    except FileNotFoundError:
        print(f"[warehouse_data_loader] ERROR: File not found: {filepath}")
    except Exception as e:
        print(f"[warehouse_data_loader] ERROR: {e}")

    return rows
