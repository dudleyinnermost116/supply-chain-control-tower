import csv
from pathlib import Path


def load_shipments(csv_path: str):
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        cleaned_rows = []

        for row in reader:
            cleaned_row = {}

            for key, value in row.items():
                clean_key = key.strip().lower() if key else key
                clean_value = value.strip() if isinstance(value, str) else value
                cleaned_row[clean_key] = clean_value

            cleaned_rows.append(cleaned_row)

        return cleaned_rows