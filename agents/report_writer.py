# Converts analysis output into professional, detailed PDF reports.
# Uses ReportLab canvas for precise design control.
# Produces two report types:
#   - Alert report  : focused single-item report (Path A)
#   - Weekly report : full multi-page inventory summary (Path B)

import os
import sys
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import REPORTS_DIR

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY        = colors.HexColor("#0d1b2a")
ACCENT      = colors.HexColor("#1565c0")
ACCENT_LITE = colors.HexColor("#e8f0fe")
CRITICAL_C  = colors.HexColor("#b71c1c")
CRITICAL_BG = colors.HexColor("#ffebee")
HIGH_C      = colors.HexColor("#e65100")
HIGH_BG     = colors.HexColor("#fff3e0")
MEDIUM_C    = colors.HexColor("#f57f17")
MEDIUM_BG   = colors.HexColor("#fffde7")
SAFE_C      = colors.HexColor("#1b5e20")
SAFE_BG     = colors.HexColor("#e8f5e9")
LIGHT_GREY  = colors.HexColor("#f8f9fa")
MID_GREY    = colors.HexColor("#dee2e6")
DARK_GREY   = colors.HexColor("#495057")
WHITE       = colors.white
BLACK       = colors.HexColor("#212529")

PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 18 * mm
T_MARGIN = B_MARGIN = 18 * mm
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN


def urgency_color(urgency: str):
    return {"CRITICAL": CRITICAL_C, "HIGH": HIGH_C, "MEDIUM": MEDIUM_C}.get(urgency, SAFE_C)

def urgency_bg(urgency: str):
    return {"CRITICAL": CRITICAL_BG, "HIGH": HIGH_BG, "MEDIUM": MEDIUM_BG}.get(urgency, SAFE_BG)


# ── Page number canvas ────────────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    """Adds 'Page X of Y' footer to every page."""
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for i, page in enumerate(self._pages, 1):
            self.__dict__.update(page)
            self._draw_footer(i, total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, page_num, total):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#adb5bd"))
        self.drawString(L_MARGIN, 11 * mm, "Inventory Monitoring System  ·  Confidential")
        self.drawRightString(PAGE_W - R_MARGIN, 11 * mm, f"Page {page_num} of {total}")
        self.setStrokeColor(MID_GREY)
        self.setLineWidth(0.4)
        self.line(L_MARGIN, 14 * mm, PAGE_W - R_MARGIN, 14 * mm)
        self.restoreState()


# ── Canvas drawing helpers ────────────────────────────────────────────────────
def draw_kpi_card(c, x, y, w, h, label, value, unit="", color=ACCENT):
    c.setFillColor(LIGHT_GREY)
    c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
    c.setFillColor(color)
    c.roundRect(x, y + h - 3, w, 3, 1, fill=1, stroke=0)
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(x + w / 2, y + h / 2 + 3, str(value))
    if unit:
        c.setFont("Helvetica", 8)
        c.setFillColor(DARK_GREY)
        c.drawCentredString(x + w / 2, y + h / 2 - 6, unit)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(DARK_GREY)
    c.drawCentredString(x + w / 2, y + 5, label)


# ── Platypus styles ───────────────────────────────────────────────────────────
def get_styles():
    return {
        "section_heading": ParagraphStyle(
            "sh", fontName="Helvetica-Bold", fontSize=10.5,
            textColor=ACCENT, spaceBefore=4, spaceAfter=3
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9.5,
            textColor=BLACK, leading=14, spaceAfter=3
        ),
        "label": ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=9, textColor=DARK_GREY
        ),
        "value": ParagraphStyle(
            "value", fontName="Helvetica", fontSize=9, textColor=BLACK
        ),
        "th": ParagraphStyle(
            "th", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE
        ),
        "td": ParagraphStyle(
            "td", fontName="Helvetica", fontSize=8.5, textColor=BLACK
        ),
        "td_center": ParagraphStyle(
            "td_c", fontName="Helvetica", fontSize=8.5,
            textColor=BLACK, alignment=TA_CENTER
        ),
        "td_right": ParagraphStyle(
            "td_r", fontName="Helvetica", fontSize=8.5,
            textColor=BLACK, alignment=TA_RIGHT
        ),
        "callout": ParagraphStyle(
            "callout", fontName="Helvetica-Oblique", fontSize=9.5,
            textColor=DARK_GREY, leading=14,
            leftIndent=8, rightIndent=8, spaceAfter=4
        ),
    }


def std_table_style(header_color=ACCENT):
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  header_color),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1), 0.25, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, 0),  1, header_color),
    ])


# ── ReportWriter ──────────────────────────────────────────────────────────────
class ReportWriter:

    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def write_alert_report(self, item: dict, analysis: dict) -> dict:
        try:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ALERT_{item['item_id']}_{ts}.pdf"
            filepath = os.path.join(REPORTS_DIR, filename)
            self._build_alert_pdf(filepath, item, analysis)
            print(f"     ✅ Alert report saved: {filename}")
            return {"success": True, "report_path": filepath, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_weekly_report(self, snapshot: dict, analysis: dict) -> dict:
        try:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            week_num = datetime.now().isocalendar()[1]
            filename = f"WEEKLY_REPORT_W{week_num}_{ts}.pdf"
            filepath = os.path.join(REPORTS_DIR, filename)
            self._build_weekly_pdf(filepath, snapshot, analysis)
            print(f"     ✅ Weekly report saved: {filename}")
            return {"success": True, "report_path": filepath, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Alert PDF ──────────────────────────────────────────────────────────────

    def _build_alert_pdf(self, filepath, item, analysis):
        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            leftMargin=L_MARGIN, rightMargin=R_MARGIN,
            topMargin=T_MARGIN + 32*mm, bottomMargin=B_MARGIN + 8*mm
        )
        S       = get_styles()
        metrics = analysis.get("metrics", {})
        urgency = metrics.get("urgency", item.get("urgency", "MEDIUM"))
        uc      = urgency_color(urgency)
        uc_bg   = urgency_bg(urgency)
        story   = []

        def on_first_page(c, doc):
            c.saveState()
            # Banner
            bar_h = 28*mm
            bar_y = PAGE_H - T_MARGIN - bar_h
            c.setFillColor(uc)
            c.rect(L_MARGIN, bar_y, CONTENT_W, bar_h, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.rect(L_MARGIN, bar_y, 4, bar_h, fill=1, stroke=0)
            # Urgency pill
            pill_w = 32*mm
            c.setFillColor(colors.HexColor("#00000030"))
            c.roundRect(PAGE_W - R_MARGIN - pill_w - 2*mm, bar_y + 8, pill_w, 12, 4, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawCentredString(PAGE_W - R_MARGIN - pill_w/2 - 2*mm, bar_y + 12, f"! {urgency}")
            # Title
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(L_MARGIN + 9, bar_y + bar_h - 10*mm,
                         f"STOCK ALERT  —  {item['item_id']}")
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#ffffffcc"))
            c.drawString(L_MARGIN + 9, bar_y + 5*mm,
                         f"{item['item_name']}  ·  {item.get('category','')}  ·  {datetime.now().strftime('%d %b %Y, %H:%M')}")
            # KPI cards
            card_y  = bar_y - 23*mm
            card_h  = 20*mm
            card_gap = 4*mm
            card_w  = (CONTENT_W - 3*card_gap) / 4
            kpis = [
                ("Current Stock",    metrics.get("current_stock","—"),         "units",  uc),
                ("Deficit",          metrics.get("deficit","—"),               "units",  CRITICAL_C),
                ("Days to Stockout", metrics.get("days_until_stockout","—"),   "days",   HIGH_C),
                ("Reorder Value",    f"${metrics.get('reorder_value',0):.0f}", "",       ACCENT),
            ]
            for i, (lbl, val, unit, col) in enumerate(kpis):
                cx = L_MARGIN + i * (card_w + card_gap)
                draw_kpi_card(c, cx, card_y, card_w, card_h, lbl, val, unit, col)
            c.restoreState()

        # Body elements
        story.append(Spacer(1, 2*mm))

        # ── Section 1: Stock Status ─────────────────────────────────────────
        story.append(Paragraph("Stock Status", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        rows = [
            [Paragraph("Field",           S["th"]),   Paragraph("Value", S["th"])],
            [Paragraph("Item ID",         S["label"]), Paragraph(item.get("item_id",""),   S["value"])],
            [Paragraph("Item Name",       S["label"]), Paragraph(item.get("item_name",""), S["value"])],
            [Paragraph("Category",        S["label"]), Paragraph(item.get("category",""),  S["value"])],
            [Paragraph("Supplier",        S["label"]), Paragraph(item.get("supplier",""),  S["value"])],
            [Paragraph("Current Stock",   S["label"]), Paragraph(f"{metrics.get('current_stock','—')} units", S["value"])],
            [Paragraph("Reorder Threshold",S["label"]),Paragraph(f"{metrics.get('reorder_threshold','—')} units", S["value"])],
            [Paragraph("Max Capacity",    S["label"]), Paragraph(f"{metrics.get('max_capacity','—')} units", S["value"])],
            [Paragraph("Unit Cost",       S["label"]), Paragraph(f"${float(item.get('unit_cost',0)):.2f}", S["value"])],
            [Paragraph("Stock Health",    S["label"]), Paragraph(f"{metrics.get('stock_health_pct','—')}%", S["value"])],
        ]
        t = Table(rows, colWidths=[65*mm, CONTENT_W - 65*mm])
        t.setStyle(std_table_style())
        story.append(t)
        story.append(Spacer(1, 5*mm))

        # ── Section 2: Deficit & Stockout ──────────────────────────────────
        story.append(Paragraph("Deficit & Stockout Analysis", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        deficit_rows = [
            [Paragraph("Metric", S["th"]),    Paragraph("Value", S["th"]),         Paragraph("Detail", S["th"])],
            [Paragraph("Deficit",            S["label"]),
             Paragraph(f"{metrics.get('deficit','—')} units",  S["value"]),
             Paragraph(f"{float(metrics.get('deficit_pct',0)):.1f}% below reorder threshold", S["value"])],
            [Paragraph("Days Until Stockout",S["label"]),
             Paragraph(f"~{metrics.get('days_until_stockout','—')} days", S["value"]),
             Paragraph(f"Est. daily consumption: {metrics.get('daily_consumption_estimate','—')} units/day", S["value"])],
            [Paragraph("Urgency Level",      S["label"]),
             Paragraph(urgency, ParagraphStyle("urg", parent=S["value"], textColor=uc, fontName="Helvetica-Bold")),
             Paragraph(
                 "Immediate PO required — risk of operational stoppage" if urgency=="CRITICAL"
                 else "Order within 24-48 hours to avoid breach" if urgency=="HIGH"
                 else "Monitor closely — order within this week",
                 S["value"])],
        ]
        dt = Table(deficit_rows, colWidths=[55*mm, 45*mm, CONTENT_W - 100*mm])
        dt.setStyle(std_table_style())
        story.append(dt)
        story.append(Spacer(1, 5*mm))

        # ── Section 3: Recommended Action ──────────────────────────────────
        story.append(Paragraph("Recommended Action", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        rec_rows = [
            [Paragraph("Action Item", S["th"]),         Paragraph("Detail", S["th"])],
            [Paragraph("Recommended Order Qty", S["label"]),
             Paragraph(f"{metrics.get('recommended_order','—')} units  (to reach 80% of max capacity)", S["value"])],
            [Paragraph("Estimated Order Value", S["label"]),
             Paragraph(f"${metrics.get('reorder_value',0):.2f}", S["value"])],
            [Paragraph("Supplier",              S["label"]),
             Paragraph(item.get("supplier","N/A"), S["value"])],
            [Paragraph("Action Required By",    S["label"]),
             Paragraph(
                 "TODAY — risk of stockout within days" if urgency=="CRITICAL"
                 else "Within 48 hours" if urgency=="HIGH"
                 else "Within this week",
                 ParagraphStyle("act", parent=S["value"], textColor=uc, fontName="Helvetica-Bold"))],
        ]
        rt = Table(rec_rows, colWidths=[65*mm, CONTENT_W - 65*mm])
        ts3 = std_table_style(ACCENT)
        ts3.add("BACKGROUND", (0, 4), (-1, 4), uc_bg)
        rt.setStyle(ts3)
        story.append(rt)
        story.append(Spacer(1, 5*mm))

        # ── Section 4: AI Analysis ──────────────────────────────────────────
        if analysis.get("llm_insight"):
            story.append(Paragraph("AI Analysis", S["section_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
            insight_data = [[Paragraph(analysis["llm_insight"], S["callout"])]]
            it = Table(insight_data, colWidths=[CONTENT_W])
            it.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), ACCENT_LITE),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LINEAFTER",     (0,0), (0,-1),  2, ACCENT),
            ]))
            story.append(it)

        doc.build(story, onFirstPage=on_first_page, canvasmaker=NumberedCanvas)

    # ── Weekly PDF ─────────────────────────────────────────────────────────────

    def _build_weekly_pdf(self, filepath, snapshot, analysis):
        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            leftMargin=L_MARGIN, rightMargin=R_MARGIN,
            topMargin=T_MARGIN + 34*mm, bottomMargin=B_MARGIN + 8*mm
        )
        S        = get_styles()
        summary  = analysis.get("summary_stats", {})
        cat_h    = analysis.get("category_health", {})
        flagged  = analysis.get("flagged_with_metrics", [])
        week_num = datetime.now().isocalendar()[1]
        year     = datetime.now().year
        story    = []

        def on_first_page(c, doc):
            c.saveState()
            bar_h = 30*mm
            bar_y = PAGE_H - T_MARGIN - bar_h
            c.setFillColor(NAVY)
            c.rect(L_MARGIN, bar_y, CONTENT_W, bar_h, fill=1, stroke=0)
            c.setFillColor(ACCENT)
            c.rect(L_MARGIN, bar_y, 4, bar_h, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(L_MARGIN + 9, bar_y + bar_h - 10*mm,
                         f"Weekly Inventory Report  —  Week {week_num}, {year}")
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#90a4ae"))
            c.drawString(L_MARGIN + 9, bar_y + 5,
                         f"Generated {datetime.now().strftime('%A, %d %B %Y at %H:%M')}  ·  ESAB Inventory Monitoring System")
            # 6 KPI cards
            card_y   = bar_y - 24*mm
            card_h   = 21*mm
            card_gap = 3*mm
            card_w   = (CONTENT_W - 5*card_gap) / 6
            health   = summary.get("health_pct", 0)
            hcol     = SAFE_C if health >= 90 else (HIGH_C if health >= 70 else CRITICAL_C)
            kpis = [
                ("Total Items",   summary.get("total_items",0),    "",   ACCENT),
                ("Safe Items",    summary.get("safe_count",0),     "",   SAFE_C),
                ("Flagged",       summary.get("flagged_count",0),  "",   HIGH_C),
                ("Critical",      summary.get("critical_count",0), "",   CRITICAL_C),
                ("Health",        f"{health}",                     "%",  hcol),
                ("Reorder Value", f"${summary.get('total_reorder_value',0):.0f}", "", ACCENT),
            ]
            for i, (lbl, val, unit, col) in enumerate(kpis):
                cx = L_MARGIN + i * (card_w + card_gap)
                draw_kpi_card(c, cx, card_y, card_w, card_h, lbl, val, unit, col)
            c.restoreState()

        def on_later_pages(c, doc):
            c.saveState()
            bar_h = 9*mm
            bar_y = PAGE_H - T_MARGIN - bar_h + 22*mm
            c.setFillColor(NAVY)
            c.rect(L_MARGIN, bar_y, CONTENT_W, bar_h, fill=1, stroke=0)
            c.setFillColor(ACCENT)
            c.rect(L_MARGIN, bar_y, 4, bar_h, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(L_MARGIN + 9, bar_y + 3,
                         f"Weekly Inventory Report  —  Week {week_num}, {year}")
            c.restoreState()

        # ── Page 1: Executive Summary + Category Health + Summary Stats ─────

        story.append(Spacer(1, 2*mm))

        # Executive Summary
        if analysis.get("llm_insight"):
            story.append(Paragraph("Executive Summary", S["section_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
            insight_data = [[Paragraph(analysis["llm_insight"], S["callout"])]]
            it = Table(insight_data, colWidths=[CONTENT_W])
            it.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), ACCENT_LITE),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LINEAFTER",     (0,0), (0,-1),  2, ACCENT),
            ]))
            story.append(it)
            story.append(Spacer(1, 5*mm))

        # Category Health
        story.append(Paragraph("Category Health Overview", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        cat_header = [
            Paragraph("Category",  S["th"]),
            Paragraph("Total",     S["th"]),
            Paragraph("Safe",      S["th"]),
            Paragraph("Flagged",   S["th"]),
            Paragraph("Health %",  S["th"]),
            Paragraph("Status",    S["th"]),
        ]
        cat_rows = [cat_header]
        for cat, data in cat_h.items():
            hp     = data["health_pct"]
            hcol   = SAFE_C if hp >= 90 else (HIGH_C if hp >= 70 else CRITICAL_C)
            status = "Healthy" if hp >= 90 else ("At Risk" if hp >= 70 else "Critical")
            cat_rows.append([
                Paragraph(cat,                       S["td"]),
                Paragraph(str(data["total_items"]),  S["td_center"]),
                Paragraph(str(data["safe_items"]),   S["td_center"]),
                Paragraph(str(data["flagged_items"]),S["td_center"]),
                Paragraph(f"{hp}%", ParagraphStyle("hp", parent=S["td_center"], textColor=hcol, fontName="Helvetica-Bold")),
                Paragraph(status,   ParagraphStyle("st", parent=S["td_center"], textColor=hcol, fontName="Helvetica-Bold")),
            ])
        ct = Table(cat_rows, colWidths=[52*mm, 20*mm, 20*mm, 22*mm, 26*mm, 34*mm])
        ct.setStyle(std_table_style())
        story.append(ct)
        story.append(Spacer(1, 5*mm))

        # Inventory Summary Stats
        story.append(Paragraph("Inventory Summary", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        fastest  = summary.get("fastest_declining")
        fd_name  = fastest.get("item_name","N/A") if fastest else "None"
        sum_rows = [
            [Paragraph("Metric", S["th"]),                Paragraph("Value", S["th"])],
            [Paragraph("Total Items in Inventory",        S["label"]), Paragraph(str(summary.get("total_items",0)), S["value"])],
            [Paragraph("Items Within Safe Levels",        S["label"]), Paragraph(f"{summary.get('safe_count',0)}  ({summary.get('health_pct',0)}%)", S["value"])],
            [Paragraph("Items Below Reorder Threshold",   S["label"]), Paragraph(str(summary.get("flagged_count",0)), S["value"])],
            [Paragraph("  of which Critical",             S["label"]), Paragraph(str(summary.get("critical_count",0)), S["value"])],
            [Paragraph("  of which High",                 S["label"]), Paragraph(str(summary.get("high_count",0)), S["value"])],
            [Paragraph("  of which Medium",               S["label"]), Paragraph(str(summary.get("medium_count",0)), S["value"])],
            [Paragraph("Most Urgent Item",                S["label"]), Paragraph(fd_name, S["value"])],
            [Paragraph("Total Estimated Reorder Value",   S["label"]), Paragraph(f"${summary.get('total_reorder_value',0):.2f}", S["value"])],
        ]
        st = Table(sum_rows, colWidths=[80*mm, CONTENT_W - 80*mm])
        st.setStyle(std_table_style())
        story.append(st)

        # ── Page 2: Flagged items ───────────────────────────────────────────
        if flagged:
            story.append(PageBreak())
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph("Flagged Items — Full Detail", S["section_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
            flag_header = [
                Paragraph("ID",         S["th"]),
                Paragraph("Item Name",  S["th"]),
                Paragraph("Category",   S["th"]),
                Paragraph("Stock",      S["th"]),
                Paragraph("Threshold",  S["th"]),
                Paragraph("Deficit",    S["th"]),
                Paragraph("Days Left",  S["th"]),
                Paragraph("Rec. Order", S["th"]),
                Paragraph("Value ($)",  S["th"]),
                Paragraph("Urgency",    S["th"]),
            ]
            flag_rows = [flag_header]
            for fi in flagged:
                m   = fi.get("metrics", {})
                urg = m.get("urgency","MEDIUM")
                uc  = urgency_color(urg)
                flag_rows.append([
                    Paragraph(fi.get("item_id",""),   S["td"]),
                    Paragraph(fi.get("item_name",""), S["td"]),
                    Paragraph(fi.get("category",""),  S["td"]),
                    Paragraph(str(m.get("current_stock","")),          S["td_center"]),
                    Paragraph(str(m.get("reorder_threshold","")),      S["td_center"]),
                    Paragraph(f"{m.get('deficit','')} ({m.get('deficit_pct','')}%)", S["td_center"]),
                    Paragraph(str(m.get("days_until_stockout","")),    S["td_center"]),
                    Paragraph(str(m.get("recommended_order","")),      S["td_center"]),
                    Paragraph(f"${m.get('reorder_value',0):.0f}",      S["td_right"]),
                    Paragraph(urg, ParagraphStyle("urg2", parent=S["td_center"], textColor=uc, fontName="Helvetica-Bold")),
                ])
            ft = Table(flag_rows, colWidths=[18*mm, 38*mm, 24*mm, 14*mm, 18*mm, 22*mm, 16*mm, 17*mm, 14*mm, 17*mm])
            fts = std_table_style()
            for row_i, fi in enumerate(flagged, 1):
                fts.add("BACKGROUND", (0, row_i), (-1, row_i), urgency_bg(fi.get("metrics",{}).get("urgency","MEDIUM")))
            ft.setStyle(fts)
            story.append(ft)
            story.append(Spacer(1, 5*mm))

            # Action cards
            story.append(Paragraph("Item-by-Item Action Cards", S["section_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
            for fi in flagged:
                m      = fi.get("metrics", {})
                urg    = m.get("urgency","MEDIUM")
                uc     = urgency_color(urg)
                uc_bg  = urgency_bg(urg)
                card_d = [[Paragraph(
                    f"<b>{fi.get('item_id','')} — {fi.get('item_name','')}</b>  "
                    f"[ {urg} ]  ·  Supplier: {fi.get('supplier','N/A')}  ·  "
                    f"Stock: {m.get('current_stock','—')} / {m.get('reorder_threshold','—')} units  ·  "
                    f"~{m.get('days_until_stockout','—')} days left  ·  "
                    f"Order {m.get('recommended_order','—')} units  (${m.get('reorder_value',0):.0f})",
                    ParagraphStyle("card", parent=S["td"], textColor=BLACK, leading=13)
                )]]
                card_t = Table(card_d, colWidths=[CONTENT_W])
                card_t.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), uc_bg),
                    ("LINEAFTER",     (0,0), (0,-1),  3, uc),
                    ("TOPPADDING",    (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING",   (0,0), (-1,-1), 8),
                ]))
                story.append(card_t)
                story.append(Spacer(1, 2*mm))

        # ── Page 3+: Full inventory table ───────────────────────────────────
        story.append(PageBreak())
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph("Full Inventory Status", S["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.4, color=MID_GREY, spaceAfter=3))
        all_items   = snapshot.get("all_items", [])
        flagged_ids = {fi.get("item_id") for fi in flagged}
        inv_header  = [
            Paragraph("ID",        S["th"]),
            Paragraph("Item Name", S["th"]),
            Paragraph("Category",  S["th"]),
            Paragraph("Stock",     S["th"]),
            Paragraph("Threshold", S["th"]),
            Paragraph("Max Cap.",  S["th"]),
            Paragraph("Unit Cost", S["th"]),
            Paragraph("Supplier",  S["th"]),
            Paragraph("Status",    S["th"]),
        ]
        inv_rows = [inv_header]
        for ai in all_items:
            cs  = float(ai.get("current_stock", 0))
            rt  = float(ai.get("reorder_threshold", 1))
            ok  = cs >= rt
            scol = SAFE_C if ok else CRITICAL_C
            inv_rows.append([
                Paragraph(str(ai.get("item_id","")),   S["td"]),
                Paragraph(str(ai.get("item_name","")), S["td"]),
                Paragraph(str(ai.get("category","")),  S["td"]),
                Paragraph(str(int(cs)),                S["td_center"]),
                Paragraph(str(int(rt)),                S["td_center"]),
                Paragraph(str(int(ai.get("max_capacity",0))), S["td_center"]),
                Paragraph(f"${float(ai.get('unit_cost',0)):.2f}", S["td_right"]),
                Paragraph(str(ai.get("supplier","")),  S["td"]),
                Paragraph("OK" if ok else "LOW",
                          ParagraphStyle("st2", parent=S["td_center"], textColor=scol, fontName="Helvetica-Bold")),
            ])
        inv_t  = Table(inv_rows, colWidths=[18*mm, 42*mm, 28*mm, 14*mm, 18*mm, 16*mm, 16*mm, 24*mm, 14*mm])
        inv_ts = std_table_style()
        for row_i, ai in enumerate(all_items, 1):
            if ai.get("item_id") in flagged_ids:
                inv_ts.add("BACKGROUND", (0, row_i), (-1, row_i), CRITICAL_BG)
        inv_t.setStyle(inv_ts)
        story.append(inv_t)

        doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages,
                  canvasmaker=NumberedCanvas)


# ── Self test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agents.monitor_agent import MonitorAgent
    from agents.analysis_agent import AnalysisAgent
    import pandas as pd
    from config.settings import INVENTORY_FILE

    print("=" * 55)
    print("  Report Writer — Self Test")
    print("=" * 55)

    # Force multiple breaches for a rich test
    df = pd.read_excel(INVENTORY_FILE, engine="openpyxl")
    df.loc[df["item_id"] == "ITM-001", "current_stock"] = 18
    df.loc[df["item_id"] == "ITM-019", "current_stock"] = 12
    df.loc[df["item_id"] == "ITM-037", "current_stock"] = 5
    df["last_updated"] = datetime.now()
    df.to_excel(INVENTORY_FILE, index=False, engine="openpyxl")

    monitor  = MonitorAgent()
    analyser = AnalysisAgent()
    writer   = ReportWriter()

    print("\n--- Test 1: Alert report ---")
    fake_item = {
        "item_id": "ITM-001", "item_name": "Steel Bolts M8",
        "category": "Raw Materials", "supplier": "FastenCo",
        "current_stock": 18, "reorder_threshold": 50,
        "max_capacity": 500, "unit_cost": 0.15,
        "deficit": 32, "deficit_pct": 64.0, "urgency": "CRITICAL",
    }
    analysis = analyser.analyse_single_item(fake_item)
    result   = writer.write_alert_report(fake_item, analysis)
    print(f"  {'✅' if result['success'] else '❌'} {result.get('filename', result.get('error'))}")

    print("\n--- Test 2: Weekly report ---")
    snapshot  = monitor.check_all()
    analysis2 = analyser.analyse_full_inventory(snapshot)
    result2   = writer.write_weekly_report(snapshot, analysis2)
    print(f"  {'✅' if result2['success'] else '❌'} {result2.get('filename', result2.get('error'))}")

    print(f"\n  Reports saved to: {REPORTS_DIR}")