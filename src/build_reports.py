"""Build two synthetic management reports as Word documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


BLUE = "1F4E78"
LIGHT_BLUE = "DCE6F1"
GREEN = "E2F0D9"
AMBER = "FFF2CC"


def build_report(month: str, analysis_dir: Path, chart_dir: Path, output_dir: Path) -> Path:
    month_name = pd.Timestamp(f"{month}-01").strftime("%B %Y")
    source = analysis_dir / month
    campaign = pd.read_csv(source / "campaign_summary.csv")
    creative = pd.read_csv(source / "creative_summary.csv")
    overall = json.loads((source / "overall_summary.json").read_text(encoding="utf-8"))
    validation = json.loads((source / "validation.json").read_text(encoding="utf-8"))

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)
    styles = doc.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(9)
    styles["Title"].font.name = "Arial"
    styles["Title"].font.size = Pt(23)
    styles["Title"].font.color.rgb = RGBColor(0, 0, 0)
    title_ppr = styles["Title"]._element.get_or_add_pPr()
    title_border = title_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_ppr.remove(title_border)
    for name in ("Heading 1", "Heading 2"):
        styles[name].font.name = "Arial"
        styles[name].font.color.rgb = RGBColor(31, 78, 120)

    title = doc.add_paragraph(style="Title")
    title.add_run("Mobile Game Marketing Performance")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = subtitle.add_run(f"Synthetic portfolio report for {month_name}")
    run.bold = True
    run.font.size = Pt(12)
    doc.add_paragraph(
        "This report evaluates fictional paid acquisition campaigns by cost, player quality, retention and monetization. "
        "It demonstrates the analytical method without exposing any employer, client or production data."
    )

    best = campaign.loc[campaign["d7_retention"].idxmax()]
    efficient = campaign.loc[campaign["cost_per_d7_retained"].replace([float("inf")], pd.NA).idxmin()]
    doc.add_heading("Executive summary", level=1)
    doc.add_paragraph(
        f"The synthetic portfolio acquired {overall['acquired_players']:,} players and generated {overall['roas']:.1%} return on ad spend. "
        f"D7 retention was {overall['d7_retention']:.1%}. {best['campaign']} produced the strongest D7 retention, while "
        f"{efficient['campaign']} produced the lowest cost per D7 retained player."
    )
    _kpi_table(doc, overall)

    doc.add_heading("Portfolio retention", level=1)
    doc.add_picture(str(chart_dir / month / "retention_curve.png"), width=Inches(6.7))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        "Retention uses exact return-day session activity and includes only cohorts mature enough to reach each day. "
        "Players without qualifying events remain visible in the tracking audit."
    )

    doc.add_heading("Campaign economics and player quality", level=1)
    cols = ["Campaign", "Life cycle", "Players", "CPI", "D7 retention", "D7 retained cost", "ROAS"]
    rows = []
    for _, r in campaign.sort_values("d7_retention", ascending=False).iterrows():
        rows.append([
            r["campaign"], r["lifecycle"].title(), f"{int(r['acquired_players']):,}", f"${r['cpi_usd']:.2f}",
            f"{r['d7_retention']:.1%}", f"${r['cost_per_d7_retained']:.2f}", f"{r['roas']:.1%}",
        ])
    _table(doc, cols, rows, [2.0, 0.75, 0.60, 0.65, 0.80, 0.90, 0.60])

    doc.add_heading("Campaign findings", level=2)
    top_quality = campaign.nlargest(2, "d7_retention")
    top_return = campaign.nlargest(2, "roas")
    doc.add_paragraph(
        f"Quality leaders were {', '.join(top_quality['campaign'])}. The strongest return signals came from "
        f"{', '.join(top_return['campaign'])}. Campaign decisions should combine scale, retained-user cost and return rather than optimize installs alone."
    )

    doc.add_heading("Creative performance", level=1)
    top_creative = creative.loc[creative["levels_per_player"].idxmax()]
    doc.add_picture(str(chart_dir / month / "creative_quality.png"), width=Inches(6.7))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        f"{top_creative['creative']} generated the strongest completed-level signal among the synthetic creatives. "
        "Creative results should be treated as directional when eligible cohort sizes are small."
    )

    doc.add_heading("Recommended actions", level=1)
    recommendations = [
        f"Use {best['campaign']} as the player-quality benchmark for the next controlled test.",
        f"Use {efficient['campaign']} as the efficiency comparison and monitor D7 retained-user cost.",
        "Reduce or redesign creatives with weak engagement even when their acquisition cost appears low.",
        "Investigate missing event coverage before making large budget changes.",
        "Review changes after a complete seven-day maturation window.",
    ]
    for item in recommendations:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Data quality and methodology", level=1)
    _table(doc, ["Check", "Result"], [
        ["Validation status", validation["status"]],
        ["Synthetic players after exclusions", f"{validation['clean_players']:,}"],
        ["Duplicate events removed", f"{validation['duplicate_events_removed']:,}"],
        ["Pre-install events removed", f"{validation['preinstall_events_removed']:,}"],
        ["Orphan event devices", f"{validation['orphan_event_devices']:,}"],
    ], [2.8, 1.5])
    doc.add_paragraph(
        "The pipeline joins fictional acquisition records to product events through synthetic device identifiers. "
        "It removes test-market records, duplicate event identifiers and pre-install activity before calculating engagement. "
        "ROAS equals total synthetic ad and purchase revenue divided by synthetic spend."
    )
    doc.add_paragraph("All data, names, findings and recommendations in this report are fictional and intended only for portfolio demonstration.")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"Marketing_Performance_Report_{month}.docx"
    doc.core_properties.title = f"Mobile Game Marketing Performance {month_name}"
    doc.core_properties.subject = "Synthetic portfolio analysis"
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    doc.save(path)
    return path


def _kpi_table(doc: Document, overall: dict) -> None:
    table = doc.add_table(rows=2, cols=5)
    table.autofit = False
    labels = ["Acquired players", "Tracking rate", "D1 retention", "D7 retention", "ROAS"]
    values = [f"{overall['acquired_players']:,}", f"{overall['tracking_rate']:.1%}",
              f"{overall['d1_retention']:.1%}", f"{overall['d7_retention']:.1%}", f"{overall['roas']:.1%}"]
    for i, text in enumerate(labels):
        cell = table.cell(0, i)
        cell.text = text
        _shade(cell, BLUE)
        for run in cell.paragraphs[0].runs:
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.bold = True
    for i, text in enumerate(values):
        cell = table.cell(1, i)
        cell.text = text
        _shade(cell, LIGHT_BLUE)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.paragraphs[0].runs[0].bold = True


def _table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        cell.width = Inches(widths[i])
        _shade(cell, BLUE)
        for run in cell.paragraphs[0].runs:
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.bold = True
            run.font.size = Pt(8)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
            cells[i].width = Inches(widths[i])
            cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for run in cells[i].paragraphs[0].runs:
                run.font.size = Pt(7.5)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, default=Path("outputs/analysis"))
    parser.add_argument("--charts", type=Path, default=Path("outputs/charts"))
    parser.add_argument("--output", type=Path, default=Path("outputs/reports"))
    args = parser.parse_args()
    for month in sorted(p.name for p in args.analysis.iterdir() if p.is_dir()):
        overall = json.loads((args.analysis / month / "overall_summary.json").read_text(encoding="utf-8"))
        if overall.get("d7_retention") is None:
            print(f"{month}: report skipped until the first cohort reaches Day 7 (month still refreshing daily)")
            continue
        path = build_report(month, args.analysis, args.charts, args.output)
        print(path)


if __name__ == "__main__":
    main()
