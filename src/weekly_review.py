"""Weekly creative review: 14-day creative quality, 7-day new-creative cost test and traffic quality.

Runs on the daily-refreshed months (players files with a ``quality_flag`` column). Each reporting week ends on
WEEK_END_WEEKDAY in the demonstration calendar and is named by that day:

A campaign is identified by its campaign ID (a renamed campaign is the same campaign); in this demonstration data
every campaign keeps one name, so the name stands for the ID.

- creative quality (14 days ending on the week end): creatives running in the 14 days (also if they started earlier;
  only their figures inside the window count), plus the quality of the players they acquired (D1/D7 retention for
  mature players only, levels, revenue). When the week is complete each creative gets a decision; none is made under
  10,000 impressions in the 14 days ("Too early to judge"). Creatives that are new in the 7-day test are left out, and a creative moved
  into a different campaign during the 7 days is left out completely (also its rows in the old campaign).
- new-creative test (7 days ending on the week end): a creative is NEW in a campaign when it has impressions in that
  campaign inside the 7 days and none in that campaign in the earlier days of the 14-day window. Older history and
  other campaigns do not block it, so a creative moved into a different campaign is new there, and a creative whose
  first impression comes later in the week (not on the first day) is still new. A creative that ran in the same
  campaign before the week, paused and came back is not new: it is listed in paused_resumed_7d.csv with its days
  without impressions and kept out of every new-creative figure. Only impressions inside the 7 days are used.
  No list of creatives is used. Assets the network reports without a name
  (for example search headline/description assets) are not listed; summary.json gives their count and totals.
  Keep/deactivate decisions are written only when the 7 days are complete; before that the row shows its progress.
- D30 ROAS: revenue in each player's first 30 days / spend for the latest 14 install days that are 30+ days old
  (an older group of installs than the 14-day window), per campaign (d30_roas.csv); empty until such days exist.
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
MIN_IMPRESSIONS = 5_000         # ... and this many impressions; otherwise the test is extended by one week
CPI_TOLERANCE = 1.30            # deactivate when CPI is more than 30% above the campaign's other creatives
MIN_BENCH_INSTALLS = 10         # a campaign benchmark needs at least this many installs behind it
QUALITY_MIN_IMPRESSIONS = 10_000  # 14-day review: no decision for a creative under this many impressions in the window
QUALITY_MIN_IPM = 3             # ... deactivate below this many installs per 1,000 impressions
D30_MIN_AGE = 30                # D30 ROAS only for install days whose players are at least 30 days old ...
D30_INSTALL_DAYS = 14           # ... using the latest 14 such install days
GHOST_DISPUTE_SHARE = 0.40      # 40%+ installs without any in-game telemetry -> billing dispute with the network
MIN_DISPUTE_PLAYERS = 20


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


def decide_quality(row, avg_roas) -> tuple[str, str]:
    """14-day creative decision: nothing under QUALITY_MIN_IMPRESSIONS impressions in the window."""
    if row["impressions"] < QUALITY_MIN_IMPRESSIONS:
        return "Too early to judge", f"only {int(row['impressions']):,} impressions (needs {QUALITY_MIN_IMPRESSIONS:,})"
    if not row["installs"]:
        return "Deactivate", f"no installs from {int(row['impressions']):,} impressions"
    if row["ipm"] < QUALITY_MIN_IPM:
        return "Deactivate", f"only {row['ipm']:.1f} installs per 1,000 impressions"
    if pd.notna(row["roas"]) and pd.notna(avg_roas) and row["roas"] < 0.5 * avg_roas:
        return "Deactivate", f"ROAS {row['roas']:.1%} is below half the average ({avg_roas:.1%})"
    return "Keep", "enough impressions and no deactivation signal"


def d30_roas(campaign_daily: pd.DataFrame, players: pd.DataFrame, events: pd.DataFrame, through: date) -> tuple[pd.DataFrame, dict]:
    """D30 ROAS = revenue in each player's first 30 days / spend, for the latest D30_INSTALL_DAYS install days that are
    at least D30_MIN_AGE days old (an older group of installs than the 14-day window). Empty until such days exist."""
    last = pd.Timestamp(through - timedelta(days=D30_MIN_AGE))
    days = sorted(d for d in campaign_daily["date"].unique() if d <= last)[-D30_INSTALL_DAYS:]
    cols = ["source", "campaign", "installs", "spend_usd", "revenue_7d_usd", "revenue_30d_usd", "d7_roas", "d30_roas"]
    if not days:
        return pd.DataFrame(columns=cols), {"window": None, "note": f"no install day is {D30_MIN_AGE} days old yet"}
    lo, hi = pd.Timestamp(days[0]), pd.Timestamp(days[-1]) + pd.Timedelta(days=1)
    spend = campaign_daily[campaign_daily["date"].isin(days)].groupby(["source", "campaign"], as_index=False)["spend_usd"].sum()
    p = players[(players["install_timestamp"] >= lo) & (players["install_timestamp"] < hi)]
    ev = events.merge(p[["device_id", "source", "campaign"]], on="device_id")
    age = ev["event_timestamp"] - ev["install_timestamp"]
    ev = ev.assign(r7=np.where(age < pd.Timedelta(days=7), ev["revenue_usd"], 0.0),
                   r30=np.where(age < pd.Timedelta(days=30), ev["revenue_usd"], 0.0))
    rev = ev.groupby(["source", "campaign"], as_index=False).agg(revenue_7d_usd=("r7", "sum"), revenue_30d_usd=("r30", "sum"))
    inst = p.groupby(["source", "campaign"], as_index=False).agg(installs=("device_id", "nunique"))
    out = spend.merge(inst, how="left").merge(rev, how="left").fillna({"installs": 0, "revenue_7d_usd": 0.0, "revenue_30d_usd": 0.0})
    out["d7_roas"] = _safe(out["revenue_7d_usd"], out["spend_usd"])
    out["d30_roas"] = _safe(out["revenue_30d_usd"], out["spend_usd"])
    tot = out[["spend_usd", "revenue_7d_usd", "revenue_30d_usd"]].sum()
    return out[cols].sort_values("spend_usd", ascending=False), {
        "window": [pd.Timestamp(days[0]).date().isoformat(), pd.Timestamp(days[-1]).date().isoformat()],
        "d7_roas": float(tot["revenue_7d_usd"] / tot["spend_usd"]) if tot["spend_usd"] else None,
        "d30_roas": float(tot["revenue_30d_usd"] / tot["spend_usd"]) if tot["spend_usd"] else None}


def review_week(end: date, through: date, creative, players, first) -> dict:
    r1_start, r2_start = end - timedelta(days=13), end - timedelta(days=6)
    complete = through >= end
    ts = lambda d: pd.Timestamp(d)
    c14 = creative[(creative["date"] >= ts(r1_start)) & (creative["date"] <= ts(end))]
    p14 = players[(players["install_timestamp"] >= ts(r1_start)) & (players["install_timestamp"] < ts(end + timedelta(days=1)))]
    keys = ["source", "campaign", "creative"]

    # New = impressions in that campaign inside the 7 days and none in that campaign in the earlier days of the
    # 14-day window. Older history and other campaigns do not block it.
    before = c14[(c14["date"] < ts(r2_start)) & (c14["impressions"] > 0)][keys].drop_duplicates()
    visible_from = creative["date"].min()
    if visible_from > ts(r1_start):
        # window days before the loaded data: a first impression on those days (creative_first_impressions.csv)
        # also counts as running before the week, in the campaign(s) the creative runs in
        hidden = first[(first["first_impression_date"] >= ts(r1_start))
                       & (first["first_impression_date"] < min(ts(r2_start), visible_from))][["source", "creative"]]
        before = pd.concat([before, creative[keys].drop_duplicates().merge(hidden, on=["source", "creative"])]).drop_duplicates()
    c7 =creative[(creative["date"] >= ts(r2_start)) & (creative["date"] <= ts(end))]
    live7 = c7[c7["impressions"] > 0]
    new = delivery(c7, keys).merge(live7.groupby(keys, as_index=False)["date"].min()
                                   .rename(columns={"date": "first_impression_date"}), on=keys)
    new = new.merge(before, on=keys, how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge")
    new_ids = new[["source", "creative", "first_impression_date"]].drop_duplicates()
    # moved = a new creative that ran before the 7 days in another campaign: it leaves the 14-day review entirely
    ran_before = c14[(c14["date"] < ts(r2_start)) & (c14["impressions"] > 0)][keys].drop_duplicates()
    moved = new[keys].merge(ran_before, on=["source", "creative"], suffixes=("", "_before"))
    moved = moved[moved["campaign"] != moved["campaign_before"]][["source", "creative"]].drop_duplicates()

    quality = delivery(c14, keys).merge(player_quality(p14, keys), on=keys, how="left")
    quality = quality[quality["impressions"] > 0]
    quality = quality.merge(new[keys], on=keys, how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge")
    quality = quality.merge(moved, on=["source", "creative"], how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge")
    quality = quality.sort_values("spend_usd", ascending=False)
    quality["roas"] = _safe(quality["total_revenue_usd"], quality["spend_usd"])   # creative ROAS (player revenue / ad spend)
    avg_roas = quality["total_revenue_usd"].sum() / quality["spend_usd"].sum() if quality["spend_usd"].sum() else np.nan
    quality["decision"], quality["decision_detail"] = (zip(*[decide_quality(r, avg_roas) if complete else ("", "")
                                                            for _, r in quality.iterrows()]) if len(quality) else ([], []))
    resumed = paused_resumed(c14, r2_start, min(end, through), keys)
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
    # ghost installs = attributed installs with no in-game telemetry; 40%+ (with >= 20 installs) -> billing dispute
    traffic["ghost_share"] = 1 - traffic["tracking_coverage"]
    traffic["billing_action"] = np.where((traffic["ghost_share"] >= GHOST_DISPUTE_SHARE)
                                         & (traffic["acquired_players"] >= MIN_DISPUTE_PLAYERS), "dispute with network", "")
    summary = {
        "week_end": end.isoformat(), "quality_window": [r1_start.isoformat(), end.isoformat()],
        "new_creative_window": [r2_start.isoformat(), end.isoformat()], "data_through": through.isoformat(),
        "complete": complete, "creatives_in_quality_window": int(len(quality)), "new_creatives": int(new["creative"].nunique()),
        "unnamed_new_assets": {"count": int(unnamed["creative"].nunique()), "impressions": int(unnamed["impressions"].sum()),
                               "installs": int(unnamed["installs"].sum()), "spend_usd": round(float(unnamed["spend_usd"].sum()), 2)},
        "players": int(p14["device_id"].nunique()),
        "tracking_coverage": float(p14["tracked"].mean()) if len(p14) else None,
        "flagged_share": float((p14["quality_flag"] != "").mean()) if len(p14) else None,
        "ghost_install_disputes": traffic[traffic["billing_action"] != ""][["source", "platform", "acquired_players", "ghost_share"]]
                                  .to_dict("records"),
        "lowest_tracking_coverage": (traffic.dropna(subset=["tracking_coverage"]).query("acquired_players >= 20")
                                     .nsmallest(1, "tracking_coverage")[["source", "platform", "tracking_coverage"]]
                                     .to_dict("records") or [None])[0],
    }
    summary["paused_resumed_excluded"] = int(len(resumed))
    return {"quality": quality, "new": new, "traffic": traffic, "summary": summary, "resumed": resumed}


def paused_resumed(c14: pd.DataFrame, r2_start: date, last: date, keys: list[str]) -> pd.DataFrame:
    """Creatives with impressions in the same campaign before the 7 days, at least one day without impressions,
    and impressions again inside the 7 days. Not new; listed separately."""
    live = c14[c14["impressions"] > 0]
    rows = []
    for k, g in live.groupby(keys):
        days = set(g["date"].dt.date)
        pre = sorted(d for d in days if d < r2_start)
        post = sorted(d for d in days if r2_start <= d <= last)
        if not pre or not post:
            continue
        gaps = [pre[0] + timedelta(days=i) for i in range((post[-1] - pre[0]).days + 1)]
        gaps = [d for d in gaps if d not in days]
        if gaps:
            rows.append(dict(zip(keys, k), first_impression_before_week=pre[0], last_impression_before_week=pre[-1],
                             days_without_impressions=len(gaps), first_impression_in_week=post[0],
                             week_impressions=int(g[g["date"].dt.date >= r2_start]["impressions"].sum())))
    return pd.DataFrame(rows, columns=keys + ["first_impression_before_week", "last_impression_before_week",
                                              "days_without_impressions", "first_impression_in_week", "week_impressions"])


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
    campaign_daily = pd.concat([pd.read_csv(args.data / f"campaign_daily_{m}.csv", parse_dates=["date"]) for m in months])
    events = pd.concat([pd.read_csv(args.data / f"events_{m}.csv", usecols=["device_id", "event_timestamp", "install_timestamp", "revenue_usd"],
                                    parse_dates=["event_timestamp", "install_timestamp"]) for m in months])
    out_root = args.output
    shutil.rmtree(out_root, ignore_errors=True)
    weeks = week_ends(creative["date"].min().date(), through)
    results = []
    for end in weeks:
        res = review_week(end, through, creative, players, first)
        d30, d30_sum = d30_roas(campaign_daily, players, events, min(end, through))
        res["summary"]["d30_roas"] = d30_sum
        d = out_root / end.isoformat()
        d.mkdir(parents=True, exist_ok=True)
        d30.to_csv(d / "d30_roas.csv", index=False)
        res["quality"].to_csv(d / "creative_quality_14d.csv", index=False)
        res["new"].to_csv(d / "new_creatives_7d.csv", index=False)
        res["traffic"].to_csv(d / "traffic_quality.csv", index=False)
        res["resumed"].to_csv(d / "paused_resumed_7d.csv", index=False)
        (d / "summary.json").write_text(json.dumps(res["summary"], indent=2, default=str), encoding="utf-8")
        results.append(res["summary"])
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
