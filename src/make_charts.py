"""Create portfolio PNG charts using Pillow and synthetic analysis outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


COLORS = ["#2563EB", "#0F766E", "#D97706", "#7C3AED", "#DC2626", "#0891B2", "#65A30D", "#475569"]
INK = "#172033"
GRID = "#D8DEE9"


def _font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _canvas(title: str, width: int = 1400, height: int = 800):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 35), title, fill=INK, font=_font(34, True))
    return image, draw


def create_charts(month: str, analysis_dir: Path, chart_dir: Path) -> None:
    source = analysis_dir / month
    campaign = pd.read_csv(source / "campaign_summary.csv")
    creative = pd.read_csv(source / "creative_summary.csv")
    overall = json.loads((source / "overall_summary.json").read_text(encoding="utf-8"))
    target = chart_dir / month
    target.mkdir(parents=True, exist_ok=True)

    _retention_chart(overall, target / "retention_curve.png")
    _horizontal_bars(campaign.sort_values("d7_retention"), "campaign", "d7_retention",
                     "D7 retention by campaign", "D7 retention", target / "campaign_retention.png", percent=True)
    _scatter(campaign, target / "cpi_vs_roas.png")
    _horizontal_bars(creative.nlargest(8, "spend_usd").sort_values("levels_per_player"), "creative", "levels_per_player",
                     "Creative player quality", "Completed levels per acquired player", target / "creative_quality.png")


def _retention_chart(overall: dict, path: Path) -> None:
    image, draw = _canvas("Portfolio retention")
    left, top, right, bottom = 120, 130, 1320, 690
    days = [1, 3, 7, 14]
    values = [overall[f"d{d}_retention"] * 100 for d in days]
    ymax = max(10, max(values) * 1.25)
    for i in range(6):
        y = bottom - (bottom - top) * i / 5
        val = ymax * i / 5
        draw.line((left, y, right, y), fill=GRID, width=2)
        draw.text((25, y - 12), f"{val:.0f}%", fill=INK, font=_font(20))
    points = []
    for i, (day, val) in enumerate(zip(days, values)):
        x = left + (right - left) * i / (len(days) - 1)
        y = bottom - (bottom - top) * val / ymax
        points.append((x, y))
        draw.text((x - 16, bottom + 18), f"D{day}", fill=INK, font=_font(21))
        draw.text((x - 30, y - 42), f"{val:.1f}%", fill=INK, font=_font(20, True))
    draw.line(points, fill=COLORS[0], width=7)
    for x, y in points:
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=COLORS[0])
    image.save(path)


def _horizontal_bars(df: pd.DataFrame, label_col: str, value_col: str, title: str, axis: str,
                     path: Path, percent: bool = False) -> None:
    image, draw = _canvas(title)
    left, top, right, bottom = 490, 130, 1320, 710
    values = df[value_col].fillna(0).tolist()
    max_value = max(values) * 1.18 if values else 1
    row_h = (bottom - top) / max(1, len(df))
    for pos, (_, row) in enumerate(df.iterrows()):
        y = top + pos * row_h + row_h * 0.15
        label = str(row[label_col])[:35]
        draw.text((40, y + row_h * 0.15), label, fill=INK, font=_font(18))
        value = float(row[value_col]) if pd.notna(row[value_col]) else 0
        bar_right = left + (right - left) * value / max_value if max_value else left
        draw.rounded_rectangle((left, y, bar_right, y + row_h * 0.65), radius=7, fill=COLORS[pos % len(COLORS)])
        shown = f"{value:.1%}" if percent else f"{value:.1f}"
        draw.text((bar_right + 10, y + row_h * 0.13), shown, fill=INK, font=_font(18, True))
    draw.text((left, 745), axis, fill=INK, font=_font(19))
    image.save(path)


def _scatter(df: pd.DataFrame, path: Path) -> None:
    image, draw = _canvas("Acquisition cost and return")
    left, top, right, bottom = 120, 130, 1320, 690
    max_x = max(1, float(df["cpi_usd"].max()) * 1.2)
    max_y = max(10, float(df["roas"].max()) * 120)
    for i in range(6):
        y = bottom - (bottom - top) * i / 5
        draw.line((left, y, right, y), fill=GRID, width=2)
        draw.text((25, y - 10), f"{max_y * i / 5:.0f}%", fill=INK, font=_font(18))
    for i in range(6):
        x = left + (right - left) * i / 5
        draw.text((x - 15, bottom + 18), f"${max_x * i / 5:.1f}", fill=INK, font=_font(18))
    for i, (_, row) in enumerate(df.iterrows()):
        x = left + (right - left) * float(row["cpi_usd"]) / max_x
        y = bottom - (bottom - top) * (float(row["roas"]) * 100) / max_y
        radius = max(9, min(28, int(float(row["acquired_players"]) / 12)))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=COLORS[i % len(COLORS)])
        draw.text((x + radius + 5, y - 10), str(row["campaign"])[:24], fill=INK, font=_font(14))
    draw.text((520, 752), "Cost per acquired player (USD)", fill=INK, font=_font(19))
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, default=Path("outputs/analysis"))
    parser.add_argument("--output", type=Path, default=Path("outputs/charts"))
    args = parser.parse_args()
    for month in ("2025-08", "2025-09"):
        create_charts(month, args.analysis, args.output)
    print(f"Charts written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
