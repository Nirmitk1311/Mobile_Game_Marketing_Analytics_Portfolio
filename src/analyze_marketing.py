"""Clean synthetic inputs and produce campaign, creative and portfolio metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


RETENTION_DAYS = (1, 3, 7, 14)


def analyze_month(month: str, data_dir: Path, output_dir: Path) -> dict:
    players = pd.read_csv(data_dir / f"players_{month}.csv", parse_dates=["install_timestamp"])
    events = pd.read_csv(data_dir / f"events_{month}.csv", parse_dates=["event_timestamp", "install_timestamp"])
    delivery = pd.read_csv(data_dir / f"campaign_daily_{month}.csv", parse_dates=["date"])
    creatives = pd.read_csv(data_dir / f"creative_daily_{month}.csv", parse_dates=["date"])

    raw_counts = {"players": len(players), "events": len(events)}
    clean_players = players.loc[~players["is_test_market"].astype(bool)].copy()
    valid_devices = set(clean_players["device_id"])
    clean_events = events.loc[events["device_id"].isin(valid_devices)].copy()
    duplicate_events = int(clean_events.duplicated("event_id").sum())
    clean_events = clean_events.drop_duplicates("event_id")
    preinstall_events = int((clean_events["event_timestamp"] < clean_events["install_timestamp"]).sum())
    clean_events = clean_events.loc[clean_events["event_timestamp"] >= clean_events["install_timestamp"]].copy()
    clean_events["day_since_install"] = (
        clean_events["event_timestamp"].dt.normalize() - clean_events["install_timestamp"].dt.normalize()
    ).dt.days

    player_metrics = _player_metrics(clean_players, clean_events)
    delivery_summary = delivery.groupby(
        ["month", "source", "campaign", "platform", "lifecycle"], as_index=False
    ).agg(impressions=("impressions", "sum"), clicks=("clicks", "sum"),
          reported_installs=("reported_installs", "sum"), spend_usd=("spend_usd", "sum"))

    campaign = player_metrics.groupby(
        ["month", "source", "campaign", "platform", "lifecycle"], as_index=False
    ).agg(
        acquired_players=("device_id", "nunique"),
        tracked_players=("tracked", "sum"),
        sessions=("sessions", "sum"),
        active_days=("active_days", "sum"),
        levels_completed=("levels_completed", "sum"),
        ad_impressions=("ad_impressions", "sum"),
        ad_revenue_usd=("ad_revenue_usd", "sum"),
        iap_revenue_usd=("iap_revenue_usd", "sum"),
    )
    for day in RETENTION_DAYS:
        tmp = player_metrics.groupby(["month", "source", "campaign", "platform", "lifecycle"], as_index=False).agg(
            **{f"d{day}_eligible": (f"d{day}_eligible", "sum"), f"d{day}_returned": (f"d{day}_returned", "sum")}
        )
        campaign = campaign.merge(tmp, on=["month", "source", "campaign", "platform", "lifecycle"], how="left")

    campaign = delivery_summary.merge(campaign, on=["month", "source", "campaign", "platform", "lifecycle"], how="left")
    campaign = _derive_metrics(campaign)

    creative = creatives.groupby(["month", "source", "campaign", "creative"], as_index=False).agg(
        impressions=("impressions", "sum"), clicks=("clicks", "sum"),
        reported_installs=("installs", "sum"), spend_usd=("spend_usd", "sum"))
    creative_players = player_metrics.groupby(["month", "source", "campaign", "creative"], as_index=False).agg(
        acquired_players=("device_id", "nunique"), sessions=("sessions", "sum"),
        active_days=("active_days", "sum"), levels_completed=("levels_completed", "sum"),
        ad_impressions=("ad_impressions", "sum"), ad_revenue_usd=("ad_revenue_usd", "sum"),
        iap_revenue_usd=("iap_revenue_usd", "sum"), d7_eligible=("d7_eligible", "sum"),
        d7_returned=("d7_returned", "sum"))
    creative = creative.merge(creative_players, on=["month", "source", "campaign", "creative"], how="left")
    creative = _derive_metrics(creative, creative_level=True)

    overall = {
        "month": month,
        "acquired_players": int(player_metrics["device_id"].nunique()),
        "tracked_players": int(player_metrics["tracked"].sum()),
        "tracking_rate": float(player_metrics["tracked"].mean()),
        "spend_usd": float(delivery["spend_usd"].sum()),
        "ad_revenue_usd": float(player_metrics["ad_revenue_usd"].sum()),
        "iap_revenue_usd": float(player_metrics["iap_revenue_usd"].sum()),
        "total_revenue_usd": float(player_metrics["total_revenue_usd"].sum()),
    }
    overall["roas"] = overall["total_revenue_usd"] / overall["spend_usd"]
    for day in RETENTION_DAYS:
        eligible = int(player_metrics[f"d{day}_eligible"].sum())
        returned = int(player_metrics[f"d{day}_returned"].sum())
        overall[f"d{day}_eligible"] = eligible
        overall[f"d{day}_returned"] = returned
        overall[f"d{day}_retention"] = returned / eligible if eligible else None

    validation = {
        "month": month,
        "raw_players": raw_counts["players"],
        "clean_players": len(clean_players),
        "excluded_test_market_players": raw_counts["players"] - len(clean_players),
        "raw_events": raw_counts["events"],
        "duplicate_events_removed": duplicate_events,
        "preinstall_events_removed": preinstall_events,
        "clean_events": len(clean_events),
        "duplicate_device_ids": int(clean_players["device_id"].duplicated().sum()),
        "orphan_event_devices": int((~clean_events["device_id"].isin(clean_players["device_id"])).sum()),
        "negative_spend_rows": int((delivery["spend_usd"] < 0).sum()),
        "status": "PASS",
    }
    if any(validation[k] for k in ("duplicate_device_ids", "orphan_event_devices", "negative_spend_rows")):
        validation["status"] = "FAIL"

    month_dir = output_dir / month
    month_dir.mkdir(parents=True, exist_ok=True)
    clean_players.to_csv(month_dir / "clean_players.csv", index=False)
    clean_events.to_csv(month_dir / "clean_events.csv", index=False)
    player_metrics.to_csv(month_dir / "player_metrics.csv", index=False)
    campaign.sort_values("spend_usd", ascending=False).to_csv(month_dir / "campaign_summary.csv", index=False)
    creative.sort_values("spend_usd", ascending=False).to_csv(month_dir / "creative_summary.csv", index=False)
    (month_dir / "overall_summary.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    (month_dir / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    return {"overall": overall, "validation": validation}


def _player_metrics(players: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    base = players.copy()
    base["tracked"] = base["device_id"].isin(events["device_id"].unique()).astype(int)
    event_group = events.groupby("device_id")
    metrics = event_group.agg(
        sessions=("event_name", lambda s: int((s == "session_start").sum())),
        levels_completed=("event_name", lambda s: int((s == "level_completed").sum())),
        ad_impressions=("event_name", lambda s: int((s == "ad_impression").sum())),
        active_days=("day_since_install", "nunique"),
    ).reset_index()
    ad_rev = events.loc[events["event_name"] == "ad_impression"].groupby("device_id")["revenue_usd"].sum()
    iap_rev = events.loc[events["event_name"] == "purchase_complete"].groupby("device_id")["revenue_usd"].sum()
    metrics["ad_revenue_usd"] = metrics["device_id"].map(ad_rev).fillna(0)
    metrics["iap_revenue_usd"] = metrics["device_id"].map(iap_rev).fillna(0)
    base = base.merge(metrics, on="device_id", how="left")
    for col in ["sessions", "levels_completed", "ad_impressions", "active_days", "ad_revenue_usd", "iap_revenue_usd"]:
        base[col] = base[col].fillna(0)
    base["total_revenue_usd"] = base["ad_revenue_usd"] + base["iap_revenue_usd"]
    month_end = base["install_timestamp"].dt.to_period("M").dt.end_time.dt.normalize()
    session_days = events.loc[events["event_name"] == "session_start"].groupby("device_id")["day_since_install"].agg(set)
    observed_until = events["event_timestamp"].max() if len(events) else None
    in_progress = observed_until is not None and observed_until < month_end.max() + pd.Timedelta(days=14)
    for day in RETENTION_DAYS:
        if in_progress:
            # Month still refreshed daily: a player counts for day N only once day N is fully observed.
            base[f"d{day}_eligible"] = ((observed_until - base["install_timestamp"]) >= pd.Timedelta(days=day + 1)).astype(int)
        else:
            base[f"d{day}_eligible"] = ((month_end - base["install_timestamp"].dt.normalize()).dt.days >= day).astype(int)
        base[f"d{day}_returned"] = base["device_id"].map(lambda x: int(day in session_days.get(x, set()))) * base[f"d{day}_eligible"]
    return base


def _derive_metrics(df: pd.DataFrame, creative_level: bool = False) -> pd.DataFrame:
    safe = lambda a, b: np.where(b > 0, a / b, np.nan)
    df["ctr"] = safe(df["clicks"], df["impressions"])
    df["cvr"] = safe(df["reported_installs"], df["clicks"])
    df["cpi_usd"] = safe(df["spend_usd"], df["acquired_players"])
    df["total_revenue_usd"] = df["ad_revenue_usd"] + df["iap_revenue_usd"]
    df["roas"] = safe(df["total_revenue_usd"], df["spend_usd"])
    df["sessions_per_player"] = safe(df["sessions"], df["acquired_players"])
    df["active_days_per_player"] = safe(df["active_days"], df["acquired_players"])
    df["levels_per_player"] = safe(df["levels_completed"], df["acquired_players"])
    df["ad_impressions_per_player"] = safe(df["ad_impressions"], df["acquired_players"])
    days = (7,) if creative_level else RETENTION_DAYS
    for day in days:
        df[f"d{day}_retention"] = safe(df[f"d{day}_returned"], df[f"d{day}_eligible"])
        df[f"cost_per_d{day}_retained"] = safe(df["spend_usd"], df[f"d{day}_returned"])
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--output", type=Path, default=Path("outputs/analysis"))
    args = parser.parse_args()
    months = sorted(p.stem.split("_")[-1] for p in args.data.glob("players_*.csv"))
    results = [analyze_month(month, args.data, args.output) for month in months]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
