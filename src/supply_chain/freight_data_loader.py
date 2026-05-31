# supply_chain/freight_data_loader.py
#
# Reads freight_sample.csv and returns a list of dicts.
# Follows the same pattern as all other data loaders in this project.

import csv


def load_freight(filepath: str) -> list:
    """
    Reads the freight CSV and returns a list of row dicts.
    No numeric columns in freight data — all fields are strings or dates.
    Returns an empty list if the file cannot be read.
    """
    rows = []

    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

    except FileNotFoundError:
        print(f"[freight_data_loader] ERROR: File not found: {filepath}")
    except Exception as e:
        print(f"[freight_data_loader] ERROR: {e}")

    return rows
