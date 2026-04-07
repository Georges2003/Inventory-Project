# Simulates real inventory consumption by randomly decrementing stock levels.
# It updates 3-6 random items every ~20 sec.

import pandas as pd
import random
import time
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import INVENTORY_FILE, SIMULATOR_INTERVAL_SECONDS


def simulate_consumption():
    """Decrement stock for a random selection of items."""
    if not os.path.exists(INVENTORY_FILE):
        print("❌ inventory.xlsx not found. Run data/create_inventory.py first.")
        return False

    df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")

    # Pick 3-6 random items to consume
    num_items = random.randint(3, 6)
    indices = random.sample(range(len(df)), num_items)

    updated = []
    for idx in indices:
        item = df.iloc[idx]

        # Consume between 5% and 25% of the reorder threshold
        consume_min = max(1, int(item["reorder_threshold"] * 0.05))
        consume_max = max(2, int(item["reorder_threshold"] * 0.25))
        consume = random.randint(consume_min, consume_max)

        # Don't go below 0
        new_stock = max(0, item["current_stock"] - consume)
        df.at[idx, "current_stock"] = new_stock
        df.at[idx, "last_updated"] = datetime.now()

        status = ""
        if new_stock < item["reorder_threshold"]:
            status = " ⚠️  BELOW THRESHOLD"
        updated.append(
            f"  {item['item_id']:8s} {item['item_name']:<30s} "
            f"{int(item['current_stock']):>5d} → {new_stock:>5d}  "
            f"(threshold: {int(item['reorder_threshold'])}){status}"
        )

    df.to_excel(INVENTORY_FILE, index=False, engine="openpyxl")

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Simulated consumption for {num_items} items:")
    for line in updated:
        print(line)

    return True


def run():
    print("=" * 60)
    print("  Inventory Simulator Running")
    print(f"  Updates every {SIMULATOR_INTERVAL_SECONDS}s (~{SIMULATOR_INTERVAL_SECONDS//60} min)")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    # Run once immediately on start
    simulate_consumption()

    while True:
        time.sleep(SIMULATOR_INTERVAL_SECONDS)
        simulate_consumption()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nSimulator stopped.")
