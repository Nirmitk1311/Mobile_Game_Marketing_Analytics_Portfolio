"""Weekly creative review: 14-day creative quality, 7-day new-creative cost test and traffic quality.

Runs on the daily-refreshed months (players files with a ``quality_flag`` column). Each reporting week ends on
WEEK_END_WEEKDAY in the demonstration calendar and is named by that day:

A campaign is identified by its campaign ID (a renamed campaign is the same campaign); in this demonstration data
every campaign keeps one name, so the name stands for the ID.

- creative quality (14 days ending on the week end): creatives running in the 14 days (also if they started earlier;
  only their figures inside the window count), plus the quality of the players they acquired (D1/D7 retention for
  mature players only, levels, revenue). When the week is complete each creative gets a decision; none is made under
  7,000 impressions in the 14 days ("Too early to judge"). Creatives that are new in the 7-day test are left out, and a creative moved
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
- incomplete last day: networks report a day's spend and impressions about one day late, and the latest day is still
  running in the players' time zone. Its full-day impressions, clicks, installs and spend are ESTIMATED per creative from
  its own average per day this week and shown ONLY in its own columns (est_installs / est_spend_usd, "not included"; self-learning: installs received so far / usual share
  received by the export time, mixed with the own average):
  delivery, CPI, the minimum-data rules and every decision use the original reported (complete-day) data. The estimate
  never boosts a creative: its CPI is never lower and its install rate never higher than the
  creative's real days. Player quality and ROAS use
  complete days only (spend_data_through).
- D30 ROAS: revenue in each player's first 30 days / spend for the latest 14 install days that are 30+ days old
  (an older group of installs than the 14-day window), per campaign (d30_roas.csv); empty until such days exist.
- report summaries: each report has its own plain-language summary (summary_creative_quality_14d.txt and
  summary_new_creatives_7d.txt), because the two reports answer different questions; prose, no tables.
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
QUALITY_MIN_IMPRESSIONS = 7_000  # 14-day review (7,000 from 2026-10-29): no decision for a creative under this many impressions in the window
QUALITY_MIN_IPM = 3             # ... deactivate below this many installs per 1,000 impressions
D30_MIN_AGE = 30                # D30 ROAS only for install days whose players are at least 30 days old ...
D30_INSTALL_DAYS = 14           # ... using the latest 14 such install days
NOWCAST_SHARE = 0.60            # share of a day's installs already received at the 13:00 export (learned in production)
NOWCAST_WEIGHT = 0.75           # weight of the received-so-far nowcast vs the own average (learned in production)
SPEND_LAG_DAYS = 1              # the latest day has installs but no reported spend yet: it is estimated (see estimate_rows)
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


def paused_creatives(creative: pd.DataFrame, keys: list[str], day: date) -> dict:
    """Rule 2026-11-18: a creative is 'no delivery today - paused?' when its campaign delivers on `day` (the export
    day) but the creative has no delivery that day, after delivering earlier. Returns {key: last delivery date}."""
    ts = pd.Timestamp(day)
    act = creative[(creative[["impressions", "clicks", "installs"]] > 0).any(axis=1) & (creative["date"] <= ts)]
    today = act[act["date"] == ts]
    camps = set(map(tuple, today[keys[:-1]].drop_duplicates().values))
    crea_today = set(map(tuple, today[keys].drop_duplicates().values))
    last = act[act["date"] < ts].groupby(keys)["date"].max()
    return {k: d.date() for k, d in last.items() if k not in crea_today and k[:-1] in camps}


def ended_verdict(row, camp) -> tuple[str, str]:
    """Rule 2026-11-18: verdict on a pause that lasted until the report day. WRONG decision when the creative was doing
    at least as well as its campaign on D7 ROAS (already includes the cost) and D1 retention, where each has enough data
    (>= 10 USD week-old spend / >= 20 day-old players); CPI only when there is no D7 ROAS. Too little data -> GOOD."""
    good, weak = [], []
    roas_ok = pd.notna(row["roas"]) and pd.notna(camp.get("roas")) and row["mature_spend_usd"] >= 10
    d1_ok = pd.notna(row["d1_retention"]) and pd.notna(camp.get("d1_retention")) and row["d1_eligible"] >= 20
    if roas_ok:
        (good if row["roas"] >= camp["roas"] else weak).append(f"D7 ROAS {row['roas']:.0%} vs campaign {camp['roas']:.0%}")
    if d1_ok:
        (good if row["d1_retention"] >= camp["d1_retention"] else weak).append(
            f"D1 retention {row['d1_retention']:.0%} vs campaign {camp['d1_retention']:.0%}")
    cpi_ok = pd.notna(row["cpi_usd"]) and pd.notna(camp.get("cpi_usd"))
    if not roas_ok and cpi_ok:
        (good if row["cpi_usd"] <= camp["cpi_usd"] else weak).append(f"CPI {row['cpi_usd']:.2f} vs campaign {camp['cpi_usd']:.2f}")
    if not (roas_ok or (d1_ok and cpi_ok)):
        return "Good decision", "too little data to show it was a strong creative"
    if not weak:
        return "Wrong decision", "it was doing very well: " + "; ".join(good)
    return "Good decision", "it was not doing very well: " + "; ".join(weak)


def estimate_rows(creative: pd.DataFrame, keys: list[str], last: date, upto: date, week_start: date,
                  window_start: date, skip=()) -> pd.DataFrame:
    """Full-day estimate for the days after `last` (up to `upto`), per key still live on `last` (or already delivering):
    its own average per day with impressions this week (week_start..last; the 7 days up to `last` when the week has no
    complete day), nowcast from the installs received so far. No boost: the estimated day's CPI and installs per 1,000
    impressions equal the key's own complete days in the window."""
    cols = ["impressions", "clicks", "installs", "spend_usd"]
    ts = pd.Timestamp
    days = pd.date_range(ts(last) + pd.Timedelta(days=1), ts(upto))
    if not len(days):
        return pd.DataFrame(columns=keys + cols + ["date"])
    done = creative[(creative["date"] <= ts(last)) & (creative["impressions"] > 0)]
    week = done[done["date"] >= ts(week_start)]
    recent = done[done["date"] > ts(last) - pd.Timedelta(days=7)]
    avg_w = week.groupby(keys)[cols].sum().div(week.groupby(keys)["date"].nunique(), axis=0)
    avg_r = recent.groupby(keys)[cols].sum().div(recent.groupby(keys)["date"].nunique(), axis=0)
    now = creative[creative["date"].isin(days)].groupby(keys)[cols].sum()
    live = sorted(set(done[done["date"] == ts(last)].set_index(keys).index)
                  | set(now[(now["impressions"] > 0) | (now["installs"] > 0)].index))
    live = [k for k in live if k not in skip]   # rule 2026-11-18: paused today -> no estimate
    avg = avg_w.combine_first(avg_r).reindex(live).dropna(how="all").fillna(0.0)
    real = creative[(creative["date"] >= ts(window_start)) & (creative["date"] <= ts(last))].groupby(keys)[cols].sum()
    real = real.reindex(avg.index).fillna(0.0)
    # Self-learning nowcast (rule 2026-11-17): installs received so far / the share of a day's installs that usually
    # arrives by the export time, mixed with the key's own average (weights and share are re-learned from past
    # estimate errors in the production pipeline; the start-up values are used here). Spend, impressions and clicks
    # follow from the key's own real CPI / rates, so the estimate is never better than its real days.
    partial = now.reindex(avg.index).fillna(0.0)["installs"]
    avg_inst = avg["installs"] * len(days)
    nowcast = partial / NOWCAST_SHARE
    ins = np.maximum(partial, np.where(partial > 0, NOWCAST_WEIGHT * nowcast + (1 - NOWCAST_WEIGHT) * avg_inst, avg_inst))
    est = avg * len(days)
    for col in ("impressions", "clicks", "spend_usd"):
        rate = real[col] / real["installs"].where(real["installs"] > 0, np.nan)
        est[col] = np.where(real["installs"] > 0, ins * rate.fillna(0.0), est[col])
    est["installs"] = ins
    return est.reset_index().assign(date=days[-1])


def review_week(end: date, through: date, creative, players, first) -> dict:
    r1_start, r2_start = end - timedelta(days=13), end - timedelta(days=6)
    complete = through >= end
    last = min(end, through - timedelta(days=SPEND_LAG_DAYS))   # last day with reported spend
    ts = lambda d: pd.Timestamp(d)
    p14 = players[(players["install_timestamp"] >= ts(r1_start)) & (players["install_timestamp"] < ts(last + timedelta(days=1)))]
    keys = ["source", "campaign", "creative"]
    actual14 = creative[(creative["date"] >= ts(r1_start)) & (creative["date"] <= ts(last))]
    export_day = min(end, through)
    paused = paused_creatives(creative, keys, export_day)            # rule 2026-11-18
    est = estimate_rows(creative, keys, last, export_day, r2_start, r1_start, skip=paused)   # incomplete day(s), estimated in full
    c14 = actual14.copy()   # original data only: the estimate is shown in its own columns, never added (rule 2026-11-17)
    est_sum = (est.groupby(keys, as_index=False)[["installs", "spend_usd"]].sum()
               .rename(columns={"installs": "est_installs", "spend_usd": "est_spend_usd"}))
    act_spend = actual14.groupby(keys, as_index=False)["spend_usd"].sum().rename(columns={"spend_usd": "actual_spend_usd"})

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
    c7 = c14[c14["date"] >= ts(r2_start)]
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
    quality = (quality.merge(est_sum, on=keys, how="left").merge(act_spend, on=keys, how="left")
               .fillna({"est_installs": 0, "est_spend_usd": 0, "actual_spend_usd": 0}))
    quality = quality.sort_values("spend_usd", ascending=False)
    # D7 ROAS (rule 2026-11-17, user-maturity based): only players who have completed 7 days (install day <= data day - 8)
    # and the ad spend of those same install days; younger installs do not have their full week of revenue yet.
    mature_last = min(last, through - timedelta(days=8))
    pm = p14[p14["install_timestamp"] < ts(mature_last + timedelta(days=1))]
    rev_m = pm.groupby(keys, as_index=False)["total_revenue_usd"].sum().rename(columns={"total_revenue_usd": "mature_revenue_usd"})
    sp_m = (actual14[actual14["date"] <= ts(mature_last)].groupby(keys, as_index=False)["spend_usd"].sum()
            .rename(columns={"spend_usd": "mature_spend_usd"}))
    quality = quality.merge(rev_m, on=keys, how="left").merge(sp_m, on=keys, how="left").fillna(
        {"mature_revenue_usd": 0.0, "mature_spend_usd": 0.0})
    quality["roas"] = _safe(quality["mature_revenue_usd"], quality["mature_spend_usd"])
    avg_roas = (quality["mature_revenue_usd"].sum() / quality["mature_spend_usd"].sum()
                if quality["mature_spend_usd"].sum() else np.nan)
    quality["decision"], quality["decision_detail"] = (zip(*[decide_quality(r, avg_roas) if complete else ("", "")
                                                            for _, r in quality.iterrows()]) if len(quality) else ([], []))
    # rule 2026-11-18: paused creatives say so instead of a decision; on the report day (week complete) a pause that
    # started since the previous report gets a verdict: wrong decision if the creative was doing very well.
    qk = list(zip(*[quality[k] for k in keys])) if len(quality) else []
    quality["last_delivery_date"] = [paused.get(k) for k in qk]
    stopped = quality["last_delivery_date"].notna()
    quality.loc[stopped, "decision"] = "No delivery today - paused?"
    camp = quality.groupby(["source", "campaign"]).agg(mature_revenue_usd=("mature_revenue_usd", "sum"), mature_spend_usd=("mature_spend_usd", "sum"),
                                                        spend_usd=("spend_usd", "sum"), installs=("installs", "sum"),
                                                        d1_returned=("d1_returned", "sum"), d1_eligible=("d1_eligible", "sum"))
    camp["roas"] = _safe(camp["mature_revenue_usd"], camp["mature_spend_usd"])
    camp["cpi_usd"] = _safe(camp["spend_usd"], camp["installs"])
    camp["d1_retention"] = _safe(camp["d1_returned"], camp["d1_eligible"])
    prev_report = end - timedelta(days=7)
    ended = quality[stopped].copy() if (len(quality) and complete) else quality.iloc[0:0].copy()
    ended = ended[[d >= prev_report for d in ended["last_delivery_date"]]] if len(ended) else ended
    if len(ended):
        ended["verdict"], ended["verdict_detail"] = zip(*[ended_verdict(r, camp.loc[(r["source"], r["campaign"])].to_dict())
                                                          for _, r in ended.iterrows()])
    else:
        ended = ended.assign(verdict=pd.Series(dtype=str), verdict_detail=pd.Series(dtype=str))
    resumed = paused_resumed(actual14, r2_start, last, keys)
    others = delivery(c7.merge(new_ids[["source", "creative"]], how="left", indicator=True).query("_merge == 'left_only'"),
                      ["source", "campaign"])
    bench = {(r.source, r.campaign): (r.spend_usd / r.installs if r.installs >= MIN_BENCH_INSTALLS else np.nan)
             for r in others.itertuples()}
    day_n = max(1, min(7, (min(end, through) - r2_start).days + 1))
    new = new.merge(est_sum, on=keys, how="left").fillna({"est_installs": 0, "est_spend_usd": 0})
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
        "spend_data_through": last.isoformat(), "estimated_installs": int(round(est_sum["est_installs"].sum())), "estimated_spend_usd": round(float(est_sum["est_spend_usd"].sum()), 2),
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
    summary["paused_today"] = int(stopped.sum()) if len(quality) else 0
    summary["ended_creatives"] = int(len(ended))
    summary["ended_wrong_decisions"] = int((ended["verdict"] == "Wrong decision").sum()) if len(ended) else 0
    return {"quality": quality, "new": new, "traffic": traffic, "summary": summary, "resumed": resumed, "ended": ended}


def _count_text(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def report_summaries(res) -> dict[str, str]:
    """Each report gets its OWN plain-language summary, because the two reports answer different questions (real
    project rule 2026-11-12): the 14-day review judges the quality of the creatives already running, the 7-day test
    judges the cost of the newly activated ones. Prose with numbers in sentences, no tables."""
    s, q, n = res["summary"], res["quality"], res["new"]
    win_q, win_n = s["quality_window"], s["new_creative_window"]
    state = "complete" if s["complete"] else f"still running (data through {s['data_through']})"
    qd = q["decision"].replace("", np.nan).dropna().value_counts() if len(q) and "decision" in q else pd.Series(dtype=int)
    q_text = (f"This report checks the quality of the creatives that ran between {win_q[0]} and {win_q[1]}: "
              f"{_count_text(int(len(q)), 'creative')} delivered {int(q['impressions'].sum()) if len(q) else 0:,} impressions "
              f"and {int(q['installs'].sum()) if len(q) else 0:,} installs for ${float(q['spend_usd'].sum()) if len(q) else 0:,.0f}. "
              f"The window is {state}. ")
    if len(qd):
        q_text += "Decisions: " + ", ".join(f"{k.lower()} for {_count_text(int(v), 'creative')}" for k, v in qd.items()) + ". "
    elif not s["complete"]:
        q_text += "Decisions are made only when the window is complete. "
    if s.get("tracking_coverage") is not None:
        q_text += (f"{s['tracking_coverage']:.0%} of the {s['players']:,} acquired players sent in-game events and "
                   f"{s['flagged_share']:.1%} were flagged as likely fraud.")
    nd = n["decision"].replace("", np.nan).dropna().value_counts() if len(n) and "decision" in n else pd.Series(dtype=int)
    n_text = (f"This report tests the cost of the creatives newly activated between {win_n[0]} and {win_n[1]}: "
              f"{_count_text(s['new_creatives'], 'new creative')} delivered {int(n['impressions'].sum()) if len(n) else 0:,} "
              f"impressions and {int(n['installs'].sum()) if len(n) else 0:,} installs for "
              f"${float(n['spend_usd'].sum()) if len(n) else 0:,.0f}. The test week is {state}. ")
    if len(nd):
        n_text += "Decisions: " + ", ".join(f"{k.lower()} for {_count_text(int(v), 'creative')}" for k, v in nd.items()) + ". "
    elif not s["complete"]:
        n_text += "Keep or deactivate decisions come only when the 7 days are complete. "
    if s.get("paused_resumed_excluded"):
        n_text += f"{_count_text(s['paused_resumed_excluded'], 'paused-and-resumed creative')} were left out because they are not new."
    return {"creative_quality_14d": q_text.strip(), "new_creatives_7d": n_text.strip()}


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
        res["ended"].to_csv(d / "ended_creatives.csv", index=False)
        for name, text in report_summaries(res).items():
            (d / f"summary_{name}.txt").write_text(text + "\n", encoding="utf-8")
        (d / "summary.json").write_text(json.dumps(res["summary"], indent=2, default=str), encoding="utf-8")
        results.append(res["summary"])
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
