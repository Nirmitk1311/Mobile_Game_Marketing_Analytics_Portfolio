"""Weekly creative review: 14-day creative quality, 7-day new-creative cost test and traffic quality.

Runs on the daily-refreshed months (players files with a ``quality_flag`` column). Each reporting week ends on
WEEK_END_WEEKDAY in the demonstration calendar and is named by that day:

- creative quality (14 days ending on the week end): delivery and cost per creative, plus the quality of the players
  it acquired (D1/D7 retention for mature players only, levels, revenue).
- new-creative test (7 days ending on the week end): a creative is NEW when its first impression (whole history of
  that network, data/synthetic/creative_first_impressions.csv) falls inside the 7 days and it had no impressions in
  the earlier days of the 14-day window. No list of creatives is used. Assets the network reports without a name
  (for example search headline/description assets) are not listed; summary.json gives their count and totals.
  Keep/deactivate decisions are written only when the 7 days are complete; before that the row shows its progress.
- traffic quality (14 days): by network and platform, the share of acquired players that sent any in-game event
  (tracking coverage) and the share flagged as likely fraud. Flagged players stay in every metric; they are counted
  and listed separately, never removed.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

WEEK_END_WEEKDAY = 2            # Wednesday in the demonstration calendar
MIN_INSTALLS = 50               # new-creative decision needs at least this many installs ...
MIN_IMPRESSIONS = 10_000        # ... and this many impressions; otherwise the test is extended by one week
CPI_TOLERANCE = 1.30            # deactivate when CPI is more than 30% above the campaign's other creatives
MIN_BENCH_INSTALLS = 10         # a campaign benchmark needs at least this many installs behind it


def _safe(a, b):
    return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def week_ends(first: date, last: date) -> list[date]:
    end = first + timedelta(days=(WEEK_END_WEEKDAY - first.weekday()) % 7)
    out = []
    while end - timedelta(days=6) <= last:
        out.append(end)
        end += timedelta(days=7)
    return out


def load(data: Path, analysis: Path):
    months = []
    for p in sorted(data.glob("players_*.csv")):
        if "quality_flag" in pd.read_csv(p, nrows=0).columns:
            months.append(p.stem.split("_")[-1])
    if not months:
        return None
    creative = pd.concat([pd.read_csv(data / f"creative_daily_{m}.csv", parse_dates=["date"]) for m in months])
    players = pd.concat([pd.read_csv(analysis / m / "player_metrics.csv", parse_dates=["install_timestamp"],
                                     keep_default_na=False, na_values=[""]) for m in months])
    players["quality_flag"] = players["quality_flag"].fillna("").astype(str)
    first = pd.read_csv(data / "creative_first_impressions.csv", parse_dates=["first_impression_date"])
    status = json.loads((data / "live_status.json").read_text(encoding="utf-8"))
    return months, creative, players, first, status


def player_quality(players: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    p = players.assign(flagged=(players["quality_flag"] != "").astype(int))
    g = p.groupby(keys, as_index=False).agg(
        acquired_players=("device_id", "nunique"), tracked_players=("tracked", "sum"), flagged_players=("flagged", "sum"),
        d1_eligible=("d1_eligible", "sum"), d1_returned=("d1_returned", "sum"),
        d7_eligible=("d7_eligible", "sum"), d7_returned=("d7_returned", "sum"),
        levels_completed=("levels_completed", "sum"), total_revenue_usd=("total_revenue_usd", "sum"))
    g["d1_retention"] = _safe(g["d1_returned"], g["d1_eligible"])
    g["d7_retention"] = _safe(g["d7_returned"], g["d7_eligible"])
    g["levels_per_player"] = _safe(g["levels_completed"], g["acquired_players"])
    g["revenue_per_player_usd"] = _safe(g["total_revenue_usd"], g["acquired_players"])
    g["tracking_coverage"] = _safe(g["tracked_players"], g["acquired_players"])
    g["flagged_share"] = _safe(g["flagged_players"], g["acquired_players"])
    return g


def delivery(rows: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    g = rows.groupby(keys, as_index=False).agg(
        impressions=("impressions", "sum"), clicks=("clicks", "sum"), installs=("installs", "sum"),
        spend_usd=("spend_usd", "sum"), days_live=("date", lambda d: int(d[rows.loc[d.index, "impressions"] > 0].nunique())))
    g["cpi_usd"] = _safe(g["spend_usd"], g["installs"])
    g["ipm"] = _safe(1000 * g["installs"], g["impressions"])
    g["ctr"] = _safe(g["clicks"], g["impressions"])
    return g


def decide(row, bench) -> tuple[str, str]:
    if row["installs"] < MIN_INSTALLS or row["impressions"] < MIN_IMPRESSIONS:
        return "Extend 1 week", f"needs {MIN_INSTALLS} installs and {MIN_IMPRESSIONS:,} impressions"
    if bench is None or np.isnan(bench):
        return "Keep (no benchmark)", "the campaign's other creatives have too few installs to compare"
    if row["cpi_usd"] > CPI_TOLERANCE * bench:
        return "Deactivate", f"CPI {row['cpi_usd']:.2f} is more than 30% above the campaign benchmark {bench:.2f}"
    return "Keep", f"CPI {row['cpi_usd']:.2f} vs campaign benchmark {bench:.2f}"


def review_week(end: date, through: date, creative, players, first) -> dict:
    r1_start, r2_start = end - timedelta(days=13), end - timedelta(days=6)
    complete = through >= end
    ts = lambda d: pd.Timestamp(d)
    c14 = creative[(creative["date"] >= ts(r1_start)) & (creative["date"] <= ts(end))]
    p14 = players[(players["install_timestamp"] >= ts(r1_start)) & (players["install_timestamp"] < ts(end + timedelta(days=1)))]
    keys = ["source", "campaign", "creative"]

    quality = delivery(c14, keys).merge(player_quality(p14, keys), on=keys, how="left")
    quality = quality[quality["impressions"] > 0].sort_values("spend_usd", ascending=False)

    new_ids = first[(first["first_impression_date"] >= ts(r2_start)) & (first["first_impression_date"] <= ts(end))]
    before = c14[(c14["date"] < ts(r2_start)) & (c14["impressions"] > 0)][["source", "creative"]].drop_duplicates()
    new_ids = new_ids.merge(before, on=["source", "creative"], how="left", indicator=True)
    new_ids = new_ids[new_ids["_merge"] == "left_only"][["source", "creative", "first_impression_date"]]
    c7 = creative[(creative["date"] >= ts(r2_start)) & (creative["date"] <= ts(end))]
    new = delivery(c7, keys).merge(new_ids, on=["source", "creative"], how="inner")
    others = delivery(c7.merge(new_ids[["source", "creative"]], how="left", indicator=True).query("_merge == 'left_only'"),
                      ["source", "campaign"])
    bench = {(r.source, r.campaign): (r.spend_usd / r.installs if r.installs >= MIN_BENCH_INSTALLS else np.nan)
             for r in others.itertuples()}
    day_n = min(7, (through - r2_start).days + 1)
    new["campaign_cpi_benchmark"] = [bench.get((r.source, r.campaign), np.nan) for r in new.itertuples()]
    new["status"] = "final" if complete else f"in progress (day {day_n} of 7)"
    new["decision"], new["decision_detail"] = zip(*[decide(r, r["campaign_cpi_benchmark"]) if complete else ("", "")
                                                    for _, r in new.iterrows()]) if len(new) else ([], [])
    unnamed = new.merge(first[~first["has_name"].astype(bool)][["source", "creative"]], on=["source", "creative"])
    new = new.merge(first[first["has_name"].astype(bool)][["source", "creative"]], on=["source", "creative"])
    new = new.sort_values(["first_impression_date", "impressions"], ascending=[True, False])

    traffic = player_quality(p14, ["source", "platform"]).sort_values("acquired_players", ascending=False)
    summary = {
        "week_end": end.isoformat(), "quality_window": [r1_start.isoformat(), end.isoformat()],
        "new_creative_window": [r2_start.isoformat(), end.isoformat()], "data_through": through.isoformat(),
        "complete": complete, "creatives_in_quality_window": int(len(quality)), "new_creatives": int(new["creative"].nunique()),
        "unnamed_new_assets": {"count": int(unnamed["creative"].nunique()), "impressions": int(unnamed["impressions"].sum()),
                               "installs": int(unnamed["installs"].sum()), "spend_usd": round(float(unnamed["spend_usd"].sum()), 2)},
        "players": int(p14["device_id"].nunique()),
        "tracking_coverage": float(p14["tracked"].mean()) if len(p14) else None,
        "flagged_share": float((p14["quality_flag"] != "").mean()) if len(p14) else None,
        "lowest_tracking_coverage": (traffic.dropna(subset=["tracking_coverage"]).query("acquired_players >= 20")
                                     .nsmallest(1, "tracking_coverage")[["source", "platform", "tracking_coverage"]]
                                     .to_dict("records") or [None])[0],
    }
    return {"quality": quality, "new": new, "traffic": traffic, "summary": summary}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--analysis", type=Path, default=Path("outputs/analysis"))
    ap.add_argument("--output", type=Path, default=Path("outputs/weekly"))
    args = ap.parse_args()
    loaded = load(args.data, args.analysis)
    if loaded is None:
        print("Weekly review: no daily-refreshed month yet.")
        return
    months, creative, players, first, status = loaded
    through = date.fromisoformat(status["data_through_demo_date"])
    out_root = args.output
    shutil.rmtree(out_root, ignore_errors=True)
    weeks = week_ends(creative["date"].min().date(), through)
    results = []
    for end in weeks:
        res = review_week(end, through, creative, players, first)
        d = out_root / end.isoformat()
        d.mkdir(parents=True, exist_ok=True)
        res["quality"].to_csv(d / "creative_quality_14d.csv", index=False)
        res["new"].to_csv(d / "new_creatives_7d.csv", index=False)
        res["traffic"].to_csv(d / "traffic_quality.csv", index=False)
        (d / "summary.json").write_text(json.dumps(res["summary"], indent=2, default=str), encoding="utf-8")
        results.append(res["summary"])
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
