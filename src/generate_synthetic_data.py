"""Generate deterministic, fictional mobile-game marketing data.

All names, identifiers and values produced by this module are synthetic.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


CAMPAIGNS = [
    ("Search Network", "Search Value Global", "Android", "active", 1.05, 0.16, 0.20),
    ("Search Network", "Search Value North", "Android", "active", 1.55, 0.21, 0.25),
    ("Game Network", "Playable Broad", "iOS", "active", 1.35, 0.25, 0.31),
    ("Game Network", "Playable Premium", "iOS", "active", 2.10, 0.29, 0.38),
    ("Social Network", "Social Gameplay", "iOS", "active", 1.70, 0.18, 0.19),
    ("Social Network", "Social Lifestyle", "iOS", "stopped", 2.25, 0.14, 0.13),
    ("Discovery Network", "Discovery Rewarded", "Android", "stopped", 0.95, 0.12, 0.15),
    ("Store Search", "Store Intent", "iOS", "active", 2.45, 0.31, 0.42),
]

CREATIVE_CONCEPTS = ["Playable Puzzle", "Progress Video", "Reward Story"]
REGIONS = ["North America", "Western Europe", "APAC", "LATAM", "Test Market"]
REGION_P = [0.33, 0.25, 0.27, 0.11, 0.04]


def _month_config(month: str) -> tuple[pd.Timestamp, int, int]:
    if month == "2025-08":
        return pd.Timestamp("2025-08-01"), 31, 1600
    if month == "2025-09":
        return pd.Timestamp("2025-09-01"), 30, 1850
    raise ValueError(f"Unsupported month: {month}")


def generate_month(month: str, output_dir: Path) -> None:
    start, days, target_players = _month_config(month)
    rng = np.random.default_rng(int(month.replace("-", "")))
    campaign_rows: list[dict] = []

    weights = np.array([1.15, 0.85, 1.20, 0.78, 0.90, 0.45, 0.55, 0.35])
    if month.endswith("09"):
        weights *= np.array([1.08, 1.00, 1.15, 0.92, 0.82, 0.55, 0.60, 1.10])

    for day_idx in range(days):
        date = start + pd.Timedelta(days=day_idx)
        for c_idx, (source, campaign, platform, status, base_cpi, quality, revenue_factor) in enumerate(CAMPAIGNS):
            if status == "stopped" and day_idx >= (18 if month.endswith("08") else 15):
                continue
            weekend = 1.10 if date.dayofweek >= 5 else 1.0
            impressions = int(rng.poisson(2500 * weights[c_idx] * weekend) + 300)
            ctr = np.clip(0.025 + 0.006 * c_idx + rng.normal(0, 0.004), 0.012, 0.085)
            clicks = max(1, int(impressions * ctr))
            cvr = np.clip(0.12 + quality * 0.30 + rng.normal(0, 0.015), 0.10, 0.28)
            installs = max(1, int(clicks * cvr))
            spend = installs * base_cpi * rng.uniform(0.91, 1.09)
            campaign_rows.append(
                {
                    "month": month,
                    "date": date.date().isoformat(),
                    "source": source,
                    "campaign": campaign,
                    "platform": platform,
                    "lifecycle": status,
                    "impressions": impressions,
                    "clicks": clicks,
                    "reported_installs": installs,
                    "spend_usd": round(spend, 2),
                    "synthetic_quality": quality,
                    "synthetic_revenue_factor": revenue_factor,
                }
            )

    delivery = pd.DataFrame(campaign_rows)
    probabilities = delivery["reported_installs"].to_numpy(dtype=float)
    probabilities /= probabilities.sum()
    selected = rng.choice(delivery.index.to_numpy(), size=target_players, replace=True, p=probabilities)

    player_rows: list[dict] = []
    event_rows: list[dict] = []
    creative_rows: list[dict] = []
    event_counter = 1

    for player_num, row_idx in enumerate(selected, start=1):
        d = delivery.loc[row_idx]
        c_idx = next(i for i, c in enumerate(CAMPAIGNS) if c[1] == d["campaign"])
        quality = float(d["synthetic_quality"])
        creative_num = int(rng.integers(0, len(CREATIVE_CONCEPTS)))
        creative = f"{CREATIVE_CONCEPTS[creative_num]} {chr(65 + c_idx)}"
        install_date = pd.Timestamp(d["date"]) + pd.Timedelta(minutes=int(rng.integers(0, 1440)))
        region = rng.choice(REGIONS, p=REGION_P)
        is_test = region == "Test Market"
        device_id = f"SYN-{month.replace('-', '')}-D{player_num:05d}"
        person_id = f"SYN-{month.replace('-', '')}-P{player_num:05d}"
        tracked = bool(rng.random() > (0.055 + (0.025 if d["platform"] == "Android" else 0)))

        player_rows.append(
            {
                "month": month,
                "device_id": device_id,
                "person_id": person_id,
                "install_timestamp": install_date.isoformat(),
                "source": d["source"],
                "campaign": d["campaign"],
                "creative": creative,
                "platform": d["platform"],
                "region_group": region,
                "is_test_market": is_test,
                "lifecycle": d["lifecycle"],
                "tracking_available": tracked,
            }
        )

        creative_rows.append(
            {
                "month": month,
                "date": pd.Timestamp(d["date"]).date().isoformat(),
                "source": d["source"],
                "campaign": d["campaign"],
                "creative": creative,
                "impressions": int(rng.integers(35, 110)),
                "clicks": int(rng.integers(2, 10)),
                "installs": 1,
                "spend_usd": round(float(CAMPAIGNS[c_idx][4] * rng.uniform(0.85, 1.18)), 2),
            }
        )

        if not tracked:
            continue

        base_return = quality + (0.025 if month.endswith("09") else 0)
        active_days = [0]
        for day, multiplier in [(1, 1.0), (2, 0.82), (3, 0.70), (4, 0.58), (5, 0.50), (6, 0.44), (7, 0.39), (14, 0.24)]:
            if rng.random() < min(0.78, base_return * multiplier):
                active_days.append(day)

        for day in sorted(set(active_days)):
            sessions = 1 + int(rng.poisson(0.55 + quality * 2.2))
            for session in range(sessions):
                event_time = install_date + pd.Timedelta(days=day, hours=2 + session * 3)
                event_rows.append(
                    _event(month, event_counter, device_id, person_id, event_time, install_date, "session_start", 0, 0.0)
                )
                event_counter += 1
                levels = max(1, int(rng.poisson(2.8 + quality * 8)))
                for _ in range(levels):
                    event_rows.append(
                        _event(month, event_counter, device_id, person_id, event_time + pd.Timedelta(minutes=int(rng.integers(2, 80))), install_date, "level_completed", 1, 0.0)
                    )
                    event_counter += 1
                ads = int(rng.poisson(0.8 + quality * 4.0))
                for _ in range(ads):
                    event_rows.append(
                        _event(month, event_counter, device_id, person_id, event_time + pd.Timedelta(minutes=int(rng.integers(3, 90))), install_date, "ad_impression", 0, round(float(rng.uniform(0.006, 0.035)), 4))
                    )
                    event_counter += 1
                if rng.random() < 0.018 + quality * 0.035:
                    event_rows.append(
                        _event(month, event_counter, device_id, person_id, event_time + pd.Timedelta(minutes=95), install_date, "purchase_complete", 0, float(rng.choice([0.99, 1.99, 4.99, 9.99])))
                    )
                    event_counter += 1

        # Add a small deterministic set of dirty rows to demonstrate cleaning.
        if player_num % 137 == 0 and event_rows:
            duplicate = dict(event_rows[-1])
            duplicate["event_id"] = event_rows[-1]["event_id"]
            event_rows.append(duplicate)
        if player_num % 211 == 0:
            event_rows.append(
                _event(month, event_counter, device_id, person_id, install_date - pd.Timedelta(hours=2), install_date, "session_start", 0, 0.0)
            )
            event_counter += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    delivery.drop(columns=["synthetic_quality", "synthetic_revenue_factor"]).to_csv(output_dir / f"campaign_daily_{month}.csv", index=False)
    pd.DataFrame(player_rows).to_csv(output_dir / f"players_{month}.csv", index=False)
    pd.DataFrame(event_rows).to_csv(output_dir / f"events_{month}.csv", index=False)
    pd.DataFrame(creative_rows).groupby(
        ["month", "date", "source", "campaign", "creative"], as_index=False
    ).sum(numeric_only=True).to_csv(output_dir / f"creative_daily_{month}.csv", index=False)


def _event(month: str, event_id: int, device_id: str, person_id: str, event_time: pd.Timestamp,
           install_time: pd.Timestamp, event_name: str, level_value: int, revenue_usd: float) -> dict:
    return {
        "month": month,
        "event_id": f"EVT-{month.replace('-', '')}-{event_id:08d}",
        "device_id": device_id,
        "person_id": person_id,
        "event_timestamp": event_time.isoformat(),
        "install_timestamp": install_time.isoformat(),
        "event_name": event_name,
        "level_value": level_value,
        "revenue_usd": revenue_usd,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()
    for month in ("2025-08", "2025-09"):
        generate_month(month, args.output)
    print(f"Synthetic data written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
