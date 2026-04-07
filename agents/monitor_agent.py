# Reads the inventory Excel file continuously.
# Detects which items have dropped below their reorder threshold.
# Reports flagged items to the Orchestrator.

import pandas as pd
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import INVENTORY_FILE


class MonitorAgent:
    """
    Responsible for ONE thing: reading the Excel file and
    returning a list of items that are below their reorder threshold.

    Two modes:
      - check_single(item_id)  → used by event-driven Path A
      - check_all()            → used by scheduled Path B (Monday report)
    """

    def __init__(self):
        self.last_flagged_ids = set()  # Tracks previously flagged items to avoid duplicate alerts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_all(self) -> dict:
        """
        Full read of the inventory file.
        Returns a snapshot dict with all items and a list of flagged items.
        Used by: Orchestrator (scheduled weekly run)
        """
        df = self._load()
        if df is None:
            return {"success": False, "error": "Could not read inventory file"}

        all_items = df.to_dict(orient="records")
        flagged = self._detect_breaches(df)

        return {
            "success": True,
            "mode": "full",
            "timestamp": datetime.now().isoformat(),
            "total_items": len(all_items),
            "all_items": all_items,
            "flagged_items": flagged,
            "flagged_count": len(flagged),
        }

    def check_for_new_breaches(self) -> dict:
        """
        Polls the file and returns ONLY items that are newly below threshold
        (i.e. not already flagged in the previous check).
        Used by: Orchestrator polling loop (event-driven Path A)
        """
        df = self._load()
        if df is None:
            return {"success": False, "error": "Could not read inventory file"}

        flagged = self._detect_breaches(df)
        flagged_ids = {item["item_id"] for item in flagged}

        # Only return items that weren't flagged last time
        new_breaches = [
            item for item in flagged
            if item["item_id"] not in self.last_flagged_ids
        ]

        # Update memory
        self.last_flagged_ids = flagged_ids

        return {
            "success": True,
            "mode": "poll",
            "timestamp": datetime.now().isoformat(),
            "new_breaches": new_breaches,
            "new_breach_count": len(new_breaches),
            "total_flagged": len(flagged),
        }

    def get_item(self, item_id: str) -> dict:
        """
        Fetch a single item by ID.
        Used by: Analysis Agent when drilling into one item.
        """
        df = self._load()
        if df is None:
            return {"success": False, "error": "Could not read inventory file"}

        row = df[df["item_id"] == item_id]
        if row.empty:
            return {"success": False, "error": f"Item {item_id} not found"}

        return {"success": True, "item": row.iloc[0].to_dict()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> pd.DataFrame | None:
        """Load the Excel file into a DataFrame."""
        if not os.path.exists(INVENTORY_FILE):
            print(f"❌ Monitor Agent: File not found at {INVENTORY_FILE}")
            return None
        try:
            df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
            return df
        except Exception as e:
            print(f"❌ Monitor Agent: Failed to read file — {e}")
            return None

    def _detect_breaches(self, df: pd.DataFrame) -> list[dict]:
        """
        Find all rows where current_stock < reorder_threshold.
        Returns a list of dicts sorted by severity (worst first).
        """
        breached = df[df["current_stock"] < df["reorder_threshold"]].copy()

        if breached.empty:
            return []

        # Calculate deficit and deficit percentage for each flagged item
        breached["deficit"] = breached["reorder_threshold"] - breached["current_stock"]
        breached["deficit_pct"] = (
            breached["deficit"] / breached["reorder_threshold"] * 100
        ).round(1)

        # Assign urgency level
        breached["urgency"] = breached["deficit_pct"].apply(self._urgency_level)

        # Sort: CRITICAL first, then HIGH, then MEDIUM, then by deficit_pct descending
        urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        breached["urgency_rank"] = breached["urgency"].map(urgency_order)
        breached = breached.sort_values(
            ["urgency_rank", "deficit_pct"], ascending=[True, False]
        )

        return breached.to_dict(orient="records")

    def _urgency_level(self, deficit_pct: float) -> str:
        """Map deficit percentage to urgency label."""
        if deficit_pct >= 50:
            return "CRITICAL"
        elif deficit_pct >= 25:
            return "HIGH"
        else:
            return "MEDIUM"


if __name__ == "__main__":
    agent = MonitorAgent()

    print("=" * 55)
    print("  Monitor Agent — Self Test")
    print("=" * 55)

    # Test full check
    result = agent.check_all()
    if not result["success"]:
        print(f"❌ Error: {result['error']}")
        sys.exit(1)

    print(f"\n✅ Read {result['total_items']} items from inventory.xlsx")
    print(f"   Flagged: {result['flagged_count']} items below threshold\n")

    if result["flagged_items"]:
        print("Flagged items (sorted by severity):")
        print(f"  {'ID':<10} {'Name':<28} {'Stock':>6} {'Threshold':>10} {'Deficit':>8} {'Urgency':<10}")
        print("  " + "-" * 76)
        for item in result["flagged_items"]:
            print(
                f"  {item['item_id']:<10} {item['item_name']:<28} "
                f"{int(item['current_stock']):>6} {int(item['reorder_threshold']):>10} "
                f"{int(item['deficit']):>8} {item['urgency']:<10}"
            )
    else:
        print("  ✅ No items below threshold right now.")

    # Test new breach detection (second call should return 0 new breaches)
    print("\n--- Polling test (2nd call, same data) ---")
    result2 = agent.check_for_new_breaches()
    print(f"  New breaches detected: {result2['new_breach_count']}  (expected: 0, already seen)")
    print(f"  Total still flagged:   {result2['total_flagged']}")
