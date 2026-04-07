# agents/delivery_agent.py
# Sends reports directly via Gmail SMTP using Python's built-in smtplib.

import os
import sys
import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import OPERATIONS_MANAGER_EMAIL, REPORTS_DIR

# Load Gmail credentials from .env
from dotenv import load_dotenv
load_dotenv()

GMAIL_SENDER   = os.getenv("GMAIL_SENDER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


class DeliveryAgent:
    """
    Sends finished PDF reports as email attachments via Gmail SMTP.
    Falls back to a local delivery log if credentials are not configured.
    """

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 465  # SSL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_alert(self, item: dict, report: dict) -> dict:
        """
        Send a single-item alert email with the PDF attached.
        Used by: Orchestrator → Path A (event-driven breach)
        """
        metrics = item.get("metrics", item)
        urgency = item.get("urgency", metrics.get("urgency", "MEDIUM"))

        subject = (
            f"[{urgency}] Stock Alert — {item.get('item_id')} "
            f"{item.get('item_name')}  |  "
            f"{item.get('current_stock','?')} / {item.get('reorder_threshold','?')} units"
        )
        body = self._build_alert_body(item, metrics)

        return self._send(
            to=OPERATIONS_MANAGER_EMAIL,
            subject=subject,
            html_body=body,
            attachment_path=report.get("report_path", ""),
            label=f"Alert — {item.get('item_id')}"
        )

    def send_weekly_report(self, report: dict) -> dict:
        """
        Send the weekly summary report email with the PDF attached.
        Used by: Orchestrator → Path B (manual weekly run)
        """
        week_num = datetime.now().isocalendar()[1]
        year     = datetime.now().year
        subject  = f"Weekly Inventory Report — Week {week_num}, {year}"
        body     = self._build_weekly_body(week_num, year)

        return self._send(
            to=OPERATIONS_MANAGER_EMAIL,
            subject=subject,
            html_body=body,
            attachment_path=report.get("report_path", ""),
            label=f"Weekly Report — W{week_num}"
        )

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    def _send(self, to: str, subject: str, html_body: str,
              attachment_path: str, label: str) -> dict:
        """
        Build and send the email via Gmail SMTP over SSL.
        Falls back to local log if credentials are missing.
        """
        if not GMAIL_SENDER or not GMAIL_PASSWORD:
            return self._local_fallback(to, subject, attachment_path, label)

        try:
            msg = MIMEMultipart("mixed")
            msg["From"]    = GMAIL_SENDER
            msg["To"]      = to
            msg["Subject"] = subject

            # HTML body
            msg.attach(MIMEText(html_body, "html"))

            # PDF attachment
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, "rb") as f:
                    pdf_part = MIMEApplication(f.read(), _subtype="pdf")
                    pdf_part.add_header(
                        "Content-Disposition", "attachment",
                        filename=os.path.basename(attachment_path)
                    )
                    msg.attach(pdf_part)

            # Send via SSL
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT, context=context) as server:
                server.login(GMAIL_SENDER, GMAIL_PASSWORD)
                server.sendmail(GMAIL_SENDER, to, msg.as_string())

            print(f"     ✅ Email sent: {label}  →  {to}")
            return {
                "success":   True,
                "channel":   "gmail_smtp",
                "recipient": to,
                "subject":   subject,
                "label":     label,
                "timestamp": datetime.now().isoformat(),
            }

        except smtplib.SMTPAuthenticationError:
            print("     ❌ Gmail authentication failed.")
            print("        Check GMAIL_SENDER and GMAIL_APP_PASSWORD in your .env file.")
            return {"success": False, "error": "SMTP authentication failed", "label": label}

        except smtplib.SMTPException as e:
            print(f"     ❌ SMTP error for {label}: {e}")
            return {"success": False, "error": str(e), "label": label}

        except Exception as e:
            print(f"     ❌ Delivery error for {label}: {e}")
            return {"success": False, "error": str(e), "label": label}

    # ------------------------------------------------------------------
    # Local fallback
    # ------------------------------------------------------------------

    def _local_fallback(self, to: str, subject: str,
                        attachment_path: str, label: str) -> dict:
        """
        When Gmail credentials are not set, log the delivery locally.
        Keeps the system running cleanly during development.
        """
        log_dir  = os.path.join(REPORTS_DIR, "delivery_log")
        os.makedirs(log_dir, exist_ok=True)

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"delivery_{ts}.json")

        log_entry = {
            "label":              label,
            "to":                 to,
            "subject":            subject,
            "attachment":         os.path.basename(attachment_path),
            "attachment_exists":  os.path.exists(attachment_path),
            "fallback_reason":    "GMAIL_SENDER or GMAIL_APP_PASSWORD not set in .env",
            "timestamp":          datetime.now().isoformat(),
        }
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2)

        print(f"     📋 Gmail not configured — logged delivery to:")
        print(f"        {log_file}")
        print(f"        To:      {to}")
        print(f"        Subject: {subject}")
        print(f"        PDF:     {os.path.basename(attachment_path)}")

        return {
            "success":   True,
            "channel":   "local_log",
            "log_file":  log_file,
            "label":     label,
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Email body builders
    # ------------------------------------------------------------------

    def _build_alert_body(self, item: dict, metrics: dict) -> str:
        urgency   = item.get("urgency", "MEDIUM")
        bg_color  = {"CRITICAL": "#b71c1c", "HIGH": "#e65100", "MEDIUM": "#f57f17"}.get(urgency, "#1565c0")
        return f"""
<html><body style="font-family:Calibri,Arial,sans-serif;color:#212529;max-width:600px;">

<div style="background:{bg_color};color:white;padding:16px 20px;border-radius:6px;margin-bottom:20px;">
  <h2 style="margin:0;font-size:18px;">&#9888; STOCK ALERT — {item.get('item_id')} | {item.get('item_name')}</h2>
  <p style="margin:4px 0 0;font-size:13px;opacity:0.9;">Urgency: <strong>{urgency}</strong> &nbsp;·&nbsp; {datetime.now().strftime('%d %b %Y, %H:%M')}</p>
</div>

<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:20px;">
  <tr style="background:#f8f9fa;"><td style="padding:8px 12px;font-weight:bold;width:45%;">Current Stock</td><td style="padding:8px 12px;">{item.get('current_stock','—')} units</td></tr>
  <tr><td style="padding:8px 12px;font-weight:bold;">Reorder Threshold</td><td style="padding:8px 12px;">{item.get('reorder_threshold','—')} units</td></tr>
  <tr style="background:#f8f9fa;"><td style="padding:8px 12px;font-weight:bold;">Deficit</td><td style="padding:8px 12px;">{item.get('deficit','—')} units ({item.get('deficit_pct','—')}% below minimum)</td></tr>
  <tr><td style="padding:8px 12px;font-weight:bold;">Days Until Stockout</td><td style="padding:8px 12px;">~{metrics.get('days_until_stockout','—')} days</td></tr>
  <tr style="background:#f8f9fa;"><td style="padding:8px 12px;font-weight:bold;">Supplier</td><td style="padding:8px 12px;">{item.get('supplier','—')}</td></tr>
  <tr><td style="padding:8px 12px;font-weight:bold;">Recommended Order</td><td style="padding:8px 12px;">{metrics.get('recommended_order','—')} units (${metrics.get('reorder_value',0):.2f})</td></tr>
</table>

<div style="background:#e8f0fe;border-left:4px solid #1565c0;padding:12px 16px;border-radius:0 4px 4px 0;margin-bottom:20px;">
  <p style="margin:0;font-size:13px;color:#1565c0;font-weight:bold;">ACTION REQUIRED</p>
  <p style="margin:6px 0 0;font-size:14px;">Raise a purchase order for <strong>{metrics.get('recommended_order','—')} units</strong> from <strong>{item.get('supplier','the supplier')}</strong>. Full details in the attached PDF.</p>
</div>

<p style="font-size:12px;color:#adb5bd;border-top:1px solid #dee2e6;padding-top:12px;">
  Sent automatically by the Inventory Monitoring System.
</p>
</body></html>""".strip()

    def _build_weekly_body(self, week_num: int, year: int) -> str:
        return f"""
<html><body style="font-family:Calibri,Arial,sans-serif;color:#212529;max-width:600px;">

<div style="background:#0d1b2a;color:white;padding:16px 20px;border-radius:6px;margin-bottom:20px;">
  <h2 style="margin:0;font-size:18px;">Weekly Inventory Report — Week {week_num}, {year}</h2>
  <p style="margin:4px 0 0;font-size:13px;opacity:0.7;">{datetime.now().strftime('%A, %d %B %Y at %H:%M')} &nbsp;·&nbsp; ESAB Inventory Monitoring System</p>
</div>

<p style="font-size:14px;">Please find attached the weekly inventory summary report for Week {week_num}, {year}.</p>
<p style="font-size:14px;">The report includes:</p>
<ul style="font-size:14px;">
  <li>Overall inventory health scorecard (KPI cards)</li>
  <li>Category-by-category health breakdown</li>
  <li>All items below reorder threshold with urgency ratings</li>
  <li>Per-item action cards with recommended order quantities</li>
  <li>Full inventory status table</li>
</ul>

<div style="background:#e8f0fe;border-left:4px solid #1565c0;padding:12px 16px;border-radius:0 4px 4px 0;margin:20px 0;">
  <p style="margin:0;font-size:13px;color:#1565c0;font-weight:bold;">NEXT STEPS</p>
  <p style="margin:6px 0 0;font-size:14px;">Review the flagged items and raise any required purchase orders before end of day.</p>
</div>

<p style="font-size:12px;color:#adb5bd;border-top:1px solid #dee2e6;padding-top:12px;">
  Sent automatically by the Inventory Monitoring System.
</p>
</body></html>""".strip()


# ------------------------------------------------------------------
# Self test
# ------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agents.monitor_agent import MonitorAgent
    from agents.analysis_agent import AnalysisAgent
    from agents.report_writer import ReportWriter

    print("=" * 55)
    print("  Delivery Agent — Self Test")
    print("=" * 55)
    print(f"  Gmail sender : {GMAIL_SENDER or 'NOT SET'}")
    print(f"  App password : {'SET' if GMAIL_PASSWORD else 'NOT SET'}")
    print(f"  Recipient    : {OPERATIONS_MANAGER_EMAIL}")

    monitor  = MonitorAgent()
    analyser = AnalysisAgent()
    writer   = ReportWriter()
    agent    = DeliveryAgent()

    fake_item = {
        "item_id": "ITM-001", "item_name": "Steel Bolts M8",
        "category": "Raw Materials", "supplier": "FastenCo",
        "current_stock": 18, "reorder_threshold": 50,
        "max_capacity": 500, "unit_cost": 0.15,
        "deficit": 32, "deficit_pct": 64.0, "urgency": "CRITICAL",
    }

    print("\n--- Test 1: Alert delivery ---")
    analysis = analyser.analyse_single_item(fake_item)
    report   = writer.write_alert_report(fake_item, analysis)
    result   = agent.send_alert({**fake_item, **analysis.get("metrics", {})}, report)
    print(f"  Channel : {result.get('channel')}")
    print(f"  Success : {result.get('success')}")

    print("\n--- Test 2: Weekly delivery ---")
    snapshot  = monitor.check_all()
    analysis2 = analyser.analyse_full_inventory(snapshot)
    report2   = writer.write_weekly_report(snapshot, analysis2)
    result2   = agent.send_weekly_report(report2)
    print(f"  Channel : {result2.get('channel')}")
    print(f"  Success : {result2.get('success')}")

    print("\n✅ Delivery Agent ready.")
    if not GMAIL_SENDER:
        print("   Add GMAIL_SENDER and GMAIL_APP_PASSWORD to .env to send real emails.")