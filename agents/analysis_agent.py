# agents/analysis_agent.py
# Takes inventory data and produces structured insights.
# Calculates: days until stockout, trend, risk score, category health.
# Uses Ollama (LLaMA 3.1) for natural language reasoning on top of the numbers.

import os
import sys
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import OLLAMA_MODEL, OLLAMA_BASE_URL


class AnalysisAgent:
    def __init__(self):
        self.llm = self._load_llm()

    def _load_llm(self):
        try:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                temperature=0.1,  # Low temperature = consistent, factual outputs
            )
            print(f"✅ Analysis Agent: LLM loaded ({OLLAMA_MODEL})")
            return llm
        except Exception as e:
            print(f"⚠️  Analysis Agent: Could not load LLM — {e}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse_single_item(self, item: dict) -> dict:
        """
        Deep analysis of one flagged item.
        Returns structured insights ready for the Report Writer.
        Used by: Orchestrator → Path A (event-driven alert)
        """
        try:
            metrics = self._calculate_item_metrics(item)
            llm_insight = self._get_item_llm_insight(item, metrics)

            return {
                "success": True,
                "mode": "single_item",
                "item_id": item["item_id"],
                "item_name": item["item_name"],
                "metrics": metrics,
                "llm_insight": llm_insight,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyse_full_inventory(self, snapshot: dict) -> dict:
        """
        Full analysis across all inventory items.
        Returns summary stats, top risks, and category health scores.
        Used by: Orchestrator → Path B (weekly run)
        """
        try:
            all_items = snapshot["all_items"]
            flagged_items = snapshot["flagged_items"]

            # Per-item metrics for every flagged item
            flagged_with_metrics = []
            for item in flagged_items:
                metrics = self._calculate_item_metrics(item)
                flagged_with_metrics.append({**item, "metrics": metrics})

            # Aggregate stats
            summary_stats = self._calculate_summary_stats(all_items, flagged_items)

            # Category health
            category_health = self._calculate_category_health(all_items)

            # LLM weekly summary insight
            llm_insight = self._get_weekly_llm_insight(
                summary_stats, category_health, flagged_with_metrics
            )

            return {
                "success": True,
                "mode": "full_inventory",
                "summary_stats": summary_stats,
                "category_health": category_health,
                "flagged_with_metrics": flagged_with_metrics,
                "llm_insight": llm_insight,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Metric calculations
    # ------------------------------------------------------------------

    def _calculate_item_metrics(self, item: dict) -> dict:
        current = float(item.get("current_stock", 0))
        threshold = float(item.get("reorder_threshold", 1))
        max_cap = float(item.get("max_capacity", threshold * 2))
        unit_cost = float(item.get("unit_cost", 0))

        deficit = max(0, threshold - current)
        deficit_pct = round((deficit / threshold) * 100, 1) if threshold > 0 else 0

        # Recommended order: bring stock up to 80% of max capacity
        recommended_order = max(0, int(max_cap * 0.8) - int(current))

        # Reorder value
        reorder_value = round(recommended_order * unit_cost, 2)

        # Days until stockout estimate:
        # Assumes daily consumption = 5% of reorder threshold
        # In a real system this would use historical consumption data
        daily_consumption = max(1, threshold * 0.05)
        days_until_stockout = round(current / daily_consumption, 1) if current > 0 else 0

        # Stock health percentage (0-100)
        stock_health_pct = round((current / max_cap) * 100, 1) if max_cap > 0 else 0

        # Urgency level
        if deficit_pct >= 50:
            urgency = "CRITICAL"
        elif deficit_pct >= 25:
            urgency = "HIGH"
        else:
            urgency = "MEDIUM"

        return {
            "current_stock": int(current),
            "reorder_threshold": int(threshold),
            "max_capacity": int(max_cap),
            "deficit": int(deficit),
            "deficit_pct": deficit_pct,
            "recommended_order": recommended_order,
            "reorder_value": reorder_value,
            "days_until_stockout": days_until_stockout,
            "daily_consumption_estimate": round(daily_consumption, 1),
            "stock_health_pct": stock_health_pct,
            "urgency": urgency,
        }

    def _calculate_summary_stats(self, all_items: list, flagged_items: list) -> dict:
        """Aggregate stats across the full inventory."""
        total = len(all_items)
        flagged_count = len(flagged_items)
        safe_count = total - flagged_count
        health_pct = round((safe_count / total) * 100, 1) if total > 0 else 0

        critical = sum(1 for i in flagged_items if i.get("urgency") == "CRITICAL")
        high = sum(1 for i in flagged_items if i.get("urgency") == "HIGH")
        medium = sum(1 for i in flagged_items if i.get("urgency") == "MEDIUM")

        # Total reorder value across all flagged items
        total_reorder_value = 0
        for item in flagged_items:
            metrics = self._calculate_item_metrics(item)
            total_reorder_value += metrics["reorder_value"]

        # Fastest declining = highest deficit_pct
        fastest_declining = None
        if flagged_items:
            fastest_declining = max(
                flagged_items,
                key=lambda x: float(x.get("deficit_pct", 0))
            )

        return {
            "total_items": total,
            "flagged_count": flagged_count,
            "safe_count": safe_count,
            "health_pct": health_pct,
            "critical_count": critical,
            "high_count": high,
            "medium_count": medium,
            "total_reorder_value": round(total_reorder_value, 2),
            "fastest_declining": fastest_declining,
        }

    def _calculate_category_health(self, all_items: list) -> dict:
        """Health score per category (% of items within safe stock levels)."""
        categories = {}
        for item in all_items:
            cat = item.get("category", "Unknown")
            if cat not in categories:
                categories[cat] = {"total": 0, "flagged": 0}
            categories[cat]["total"] += 1
            if float(item.get("current_stock", 0)) < float(item.get("reorder_threshold", 0)):
                categories[cat]["flagged"] += 1

        health = {}
        for cat, counts in categories.items():
            safe = counts["total"] - counts["flagged"]
            health[cat] = {
                "total_items": counts["total"],
                "flagged_items": counts["flagged"],
                "safe_items": safe,
                "health_pct": round((safe / counts["total"]) * 100, 1),
            }
        return health

    # ------------------------------------------------------------------
    # LLM insight generation
    # ------------------------------------------------------------------

    def _get_item_llm_insight(self, item: dict, metrics: dict) -> str:
        """
        Ask the LLM to produce a 2-3 sentence plain-English insight
        for a single flagged item. Falls back gracefully if LLM unavailable.
        """
        if self.llm is None:
            return self._fallback_item_insight(item, metrics)

        prompt = f"""You are an inventory analyst. Given the data below, write exactly 2-3 sentences of plain-English insight for an operations manager. Be direct and actionable. Do not repeat the numbers back — interpret them.

Item: {item.get('item_name')} ({item.get('item_id')})
Category: {item.get('category')}
Supplier: {item.get('supplier')}
Current stock: {metrics['current_stock']} units
Reorder threshold: {metrics['reorder_threshold']} units
Deficit: {metrics['deficit']} units ({metrics['deficit_pct']}% below threshold)
Days until stockout: ~{metrics['days_until_stockout']} days
Urgency: {metrics['urgency']}
Recommended order: {metrics['recommended_order']} units (${metrics['reorder_value']:.2f})

Write your 2-3 sentence insight now:"""

        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"⚠️  LLM insight failed: {e}")
            return self._fallback_item_insight(item, metrics)

    def _get_weekly_llm_insight(
        self, summary: dict, category_health: dict, flagged_items: list
    ) -> str:
        """
        Ask the LLM for a weekly executive summary paragraph.
        Falls back gracefully if LLM unavailable.
        """
        if self.llm is None:
            return self._fallback_weekly_insight(summary)

        # Build category health string
        cat_lines = "\n".join(
            f"  - {cat}: {data['health_pct']}% healthy ({data['flagged_items']} flagged)"
            for cat, data in category_health.items()
        )

        # Top 3 critical items
        top_items = flagged_items[:3]
        top_lines = "\n".join(
            f"  - {i.get('item_name')} ({i.get('item_id')}): "
            f"{i['metrics']['deficit_pct']}% below threshold [{i['metrics']['urgency']}]"
            for i in top_items
        )

        prompt = f"""You are an inventory analyst writing a weekly executive summary for an operations manager. Write a single focused paragraph (4-5 sentences) summarising the inventory health, the most urgent risks, and one clear recommendation. Be direct and specific.

Overall health: {summary['health_pct']}% of items within safe levels
Total flagged: {summary['flagged_count']} items ({summary['critical_count']} CRITICAL, {summary['high_count']} HIGH, {summary['medium_count']} MEDIUM)
Total reorder value: ${summary['total_reorder_value']:.2f}

Category health:
{cat_lines}

Top priority items:
{top_lines}

Write your executive summary paragraph now:"""

        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"⚠️  LLM weekly insight failed: {e}")
            return self._fallback_weekly_insight(summary)

    # ------------------------------------------------------------------
    # Fallback insights (used when Ollama is not running)
    # ------------------------------------------------------------------

    def _fallback_item_insight(self, item: dict, metrics: dict) -> str:
        return (
            f"{item.get('item_name')} is {metrics['deficit_pct']}% below its reorder threshold "
            f"with approximately {metrics['days_until_stockout']} days of stock remaining. "
            f"A purchase order for {metrics['recommended_order']} units from "
            f"{item.get('supplier', 'the supplier')} should be raised immediately."
        )

    def _fallback_weekly_insight(self, summary: dict) -> str:
        return (
            f"Overall inventory health is at {summary['health_pct']}% with "
            f"{summary['flagged_count']} items below their reorder threshold. "
            f"There are {summary['critical_count']} critical items requiring immediate action. "
            f"Estimated total reorder value is ${summary['total_reorder_value']:.2f}."
        )


# ------------------------------------------------------------------
# Self test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agents.monitor_agent import MonitorAgent

    print("=" * 55)
    print("  Analysis Agent — Self Test")
    print("=" * 55)

    agent = AnalysisAgent()
    monitor = MonitorAgent()

    # Test 1: single item analysis
    print("\n--- Test 1: Single item analysis ---")
    fake_item = {
        "item_id": "ITM-001",
        "item_name": "Steel Bolts M8",
        "category": "Raw Materials",
        "supplier": "FastenCo",
        "current_stock": 18,
        "reorder_threshold": 50,
        "max_capacity": 500,
        "unit_cost": 0.15,
        "deficit": 32,
        "deficit_pct": 64.0,
        "urgency": "CRITICAL",
    }
    result = agent.analyse_single_item(fake_item)
    if result["success"]:
        m = result["metrics"]
        print(f"  Item:               {result['item_name']}")
        print(f"  Deficit:            {m['deficit']} units ({m['deficit_pct']}%)")
        print(f"  Days until stockout:{m['days_until_stockout']} days")
        print(f"  Recommended order:  {m['recommended_order']} units (${m['reorder_value']:.2f})")
        print(f"  Urgency:            {m['urgency']}")
        print(f"\n  LLM Insight:\n  {result['llm_insight']}")
    else:
        print(f"  ❌ {result['error']}")

    # Test 2: full inventory analysis
    print("\n--- Test 2: Full inventory analysis ---")
    snapshot = monitor.check_all()
    result2 = agent.analyse_full_inventory(snapshot)
    if result2["success"]:
        s = result2["summary_stats"]
        print(f"  Total items:        {s['total_items']}")
        print(f"  Health:             {s['health_pct']}%")
        print(f"  Flagged:            {s['flagged_count']} ({s['critical_count']} CRITICAL, {s['high_count']} HIGH, {s['medium_count']} MEDIUM)")
        print(f"  Total reorder value:${s['total_reorder_value']:.2f}")
        print(f"\n  Category health:")
        for cat, data in result2["category_health"].items():
            print(f"    {cat:<20} {data['health_pct']}%  ({data['flagged_items']} flagged)")
        print(f"\n  LLM Insight:\n  {result2['llm_insight']}")
    else:
        print(f"  ❌ {result2['error']}")
