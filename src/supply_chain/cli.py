from datetime import date

from supply_chain.data_loader import load_shipments
from supply_chain.rules import (
    calculate_delay_days,
    assign_delay_status,
    assign_reason_code,
)


DATA_FILE = "data/shipments_sample.csv"
TODAY = date(2026, 5, 13)


def show_summary():
    rows = load_shipments(DATA_FILE)

    total_orders = len(rows)
    delayed_count = 0
    need_action_count = 0
    reason_counts = {}

    for row in rows:
        status = assign_delay_status(row, TODAY)
        reason = assign_reason_code(row, TODAY)

        if status in ["DELAYED", "NEED_ACTION"]:
            delayed_count += 1

        if status == "NEED_ACTION":
            need_action_count += 1

        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    print("SHIPMENT DELAY SUMMARY")
    print("======================")
    print(f"Total orders: {total_orders}")
    print(f"Delayed shipments: {delayed_count}")
    print(f"Need action shipments: {need_action_count}")
    print()

    print("Reason counts:")
    for reason, count in reason_counts.items():
        print(f"- {reason}: {count}")


def show_delayed():
    rows = load_shipments(DATA_FILE)

    print()
    print("DELAYED ORDERS")
    print("==============")

    for row in rows:
        status = assign_delay_status(row, TODAY)

        if status in ["DELAYED", "NEED_ACTION"]:
            print("-" * 50)
            print(f"Sales Order: {row.get('sales_order_no', '')}")
            print(f"Customer: {row.get('customer_name', '')}")
            print(f"Scheduled Pick Date: {row.get('scheduled_pick_date', '')}")
            print(f"Delay Days: {calculate_delay_days(row, TODAY)}")
            print(f"Delay Status: {status}")
            print(f"Reason Code: {assign_reason_code(row, TODAY)}")


if __name__ == "__main__":
    show_summary()
    show_delayed()