# The central decision-maker of the system.
# It decides which agents to activate, when, and with what instructions.

import os
import sys
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import POLL_INTERVAL_SECONDS
from agents.monitor_agent import MonitorAgent


class Orchestrator:
    """
    Coordinates the four specialized agents.
    Handles three situations:
      - Path A: A new stock breach is detected during polling
      - Path B: The Monday 8am scheduled trigger fires
      - Path C: RAG chat runs independently
    """

    def __init__(self):
        self.monitor = MonitorAgent()

        # Lazy-load the other agents only when needed
        # (avoids importing LangChain/Ollama until they are built)
        self._analysis_agent = None
        self._report_writer = None
        self._delivery_agent = None

        self.run_count = 0
        self.alert_count = 0

    # ------------------------------------------------------------------
    # Agent loader helpers 
    # ------------------------------------------------------------------

    def _get_analysis_agent(self):
        if self._analysis_agent is None:
            from agents.analysis_agent import AnalysisAgent
            self._analysis_agent = AnalysisAgent()
        return self._analysis_agent

    def _get_report_writer(self):
        if self._report_writer is None:
            from agents.report_writer import ReportWriter
            self._report_writer = ReportWriter()
        return self._report_writer

    def _get_delivery_agent(self):
        if self._delivery_agent is None:
            from agents.delivery_agent import DeliveryAgent
            self._delivery_agent = DeliveryAgent()
        return self._delivery_agent

    # ------------------------------------------------------------------
    # Path A — Event-driven: single item breach
    # ------------------------------------------------------------------

    def handle_breach(self, flagged_items: list) -> dict:
        """
        Called when the polling loop detects new breaches.
        Prioritises items by severity, then runs the full pipeline
        for each one: Analysis → Report → Delivery.
        """
        if not flagged_items:
            return {"success": True, "message": "No items to process"}

        # Sort: CRITICAL first, then HIGH, then MEDIUM
        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        sorted_items = sorted(
            flagged_items,
            key=lambda x: priority_order.get(x.get("urgency", "MEDIUM"), 2)
        )

        results = []
        for item in sorted_items:
            print(f"\n  → Processing {item['item_id']} ({item['item_name']}) [{item['urgency']}]")
            result = self._run_alert_pipeline(item)
            results.append(result)
            self.alert_count += 1

        return {
            "success": True,
            "mode": "event_driven",
            "items_processed": len(results),
            "results": results
        }

    def _run_alert_pipeline(self, item: dict) -> dict:
        """
        Runs Analysis → Report Writer → Delivery for a single flagged item.
        Retries once on failure before giving up.
        """
        item_id = item["item_id"]

        for attempt in range(1, 3):  # max 2 attempts
            try:
                # Step 1: Analyse
                print(f"     [1/3] Analysis Agent...")
                analysis = self._get_analysis_agent().analyse_single_item(item)
                if not analysis.get("success"):
                    raise Exception(f"Analysis failed: {analysis.get('error')}")

                # Step 2: Write report
                print(f"     [2/3] Report Writer Agent...")
                report = self._get_report_writer().write_alert_report(item, analysis)
                if not report.get("success"):
                    raise Exception(f"Report writing failed: {report.get('error')}")

                # Step 3: Deliver
                print(f"     [3/3] Delivery Agent...")
                delivery = self._get_delivery_agent().send_alert(item, report)

                return {
                    "item_id": item_id,
                    "success": True,
                    "analysis": analysis,
                    "report_path": report.get("report_path"),
                    "delivery": delivery
                }

            except Exception as e:
                print(f"     ⚠️  Attempt {attempt} failed for {item_id}: {e}")
                if attempt == 2:
                    print(f"     ❌ Both attempts failed for {item_id}. Logging failure.")
                    return {
                        "item_id": item_id,
                        "success": False,
                        "error": str(e)
                    }
                time.sleep(2)

    # ------------------------------------------------------------------
    # Path B — Scheduled: full weekly run
    # ------------------------------------------------------------------

    def handle_weekly_run(self) -> dict:
        """
        Triggered every Monday at 8am (via Power Automate HTTP POST,
        or via the schedule library below for local testing).
        Runs full pipeline across all inventory.
        """
        print(f"\n{'='*55}")
        print(f"  WEEKLY RUN — {datetime.now().strftime('%A %d %B %Y, %H:%M')}")
        print(f"{'='*55}")

        try:
            # Step 1: Full inventory read
            print("\n  [1/4] Monitor Agent — full read...")
            snapshot = self.monitor.check_all()
            if not snapshot["success"]:
                raise Exception(snapshot.get("error"))
            print(f"         {snapshot['total_items']} items read, {snapshot['flagged_count']} flagged")

            # Step 2: Full analysis
            print("\n  [2/4] Analysis Agent — full analysis...")
            analysis = self._get_analysis_agent().analyse_full_inventory(snapshot)
            if not analysis.get("success"):
                raise Exception(analysis.get("error"))

            # Step 3: Weekly report
            print("\n  [3/4] Report Writer — weekly summary...")
            report = self._get_report_writer().write_weekly_report(snapshot, analysis)
            if not report.get("success"):
                raise Exception(report.get("error"))
            print(f"         Report saved: {report.get('report_path')}")

            # Step 4: Deliver
            print("\n  [4/4] Delivery Agent — sending report...")
            delivery = self._get_delivery_agent().send_weekly_report(report)

            print(f"\n  ✅ Weekly run complete.")
            return {
                "success": True,
                "mode": "weekly",
                "flagged_count": snapshot["flagged_count"],
                "report_path": report.get("report_path"),
                "delivery": delivery
            }

        except Exception as e:
            print(f"\n  ❌ Weekly run failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Polling loop — runs continuously for Path A
    # ------------------------------------------------------------------

    def start_polling(self):
        """
        Main loop. Polls the Monitor Agent every POLL_INTERVAL_SECONDS.
        When new breaches are found, triggers handle_breach().
        Also registers the Monday 8am weekly job.
        """
        print("=" * 55)
        print("  Orchestrator started")
        print(f"  Polling every {POLL_INTERVAL_SECONDS}s")
        print(f"  Weekly report: Monday 08:00")
        print("  Press Ctrl+C to stop")
        print("=" * 55)

        while True:
            self.run_count += 1
            ts = datetime.now().strftime("%H:%M:%S")

            result = self.monitor.check_for_new_breaches()

            if not result["success"]:
                print(f"[{ts}] ❌ Monitor error: {result.get('error')}")
            elif result["new_breach_count"] > 0:
                print(f"[{ts}] 🚨 {result['new_breach_count']} new breach(es) detected!")
                self.handle_breach(result["new_breaches"])
            else:
                print(
                    f"[{ts}] ✅ Poll #{self.run_count} — "
                    f"no new breaches (total flagged: {result['total_flagged']})"
                )

            time.sleep(POLL_INTERVAL_SECONDS)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    orchestrator = Orchestrator()

    # If passed "weekly" as argument, trigger a manual weekly run
    if len(sys.argv) > 1 and sys.argv[1] == "weekly":
        print("Manual weekly run triggered.")
        orchestrator.handle_weekly_run()
    else:
        orchestrator.start_polling()