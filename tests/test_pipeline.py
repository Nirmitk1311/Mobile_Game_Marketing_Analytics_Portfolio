import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


MONTHS = sorted(p.name for p in (ROOT / "outputs" / "analysis").iterdir() if p.is_dir())


class PortfolioOutputTests(unittest.TestCase):
    def test_validation_passes(self):
        for month in MONTHS:
            path = ROOT / "outputs" / "analysis" / month / "validation.json"
            validation = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "PASS")
            self.assertEqual(validation["duplicate_device_ids"], 0)
            self.assertEqual(validation["orphan_event_devices"], 0)

    def test_retention_is_bounded(self):
        for month in MONTHS:
            df = pd.read_csv(ROOT / "outputs" / "analysis" / month / "campaign_summary.csv")
            for day in (1, 3, 7, 14):
                self.assertTrue(df[f"d{day}_retention"].dropna().between(0, 1).all())

    def test_revenue_reconciles(self):
        for month in MONTHS:
            df = pd.read_csv(ROOT / "outputs" / "analysis" / month / "campaign_summary.csv")
            diff = (df["ad_revenue_usd"] + df["iap_revenue_usd"] - df["total_revenue_usd"]).abs().max()
            self.assertLess(diff, 1e-8)


WEEKS = sorted(p for p in (ROOT / "outputs" / "weekly").glob("*") if p.is_dir()) if (ROOT / "outputs" / "weekly").exists() else []


class WeeklyReviewTests(unittest.TestCase):
    def test_new_creatives_start_inside_the_week(self):
        first = pd.read_csv(ROOT / "data" / "synthetic" / "creative_first_impressions.csv") if WEEKS else None
        for week in WEEKS:
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            start, end = summary["new_creative_window"]
            new = pd.read_csv(week / "new_creatives_7d.csv")
            if new.empty:
                continue
            self.assertTrue(new["first_impression_date"].between(start, end).all())
            merged = new.merge(first, on=["source", "creative"], suffixes=("", "_catalog"))
            self.assertTrue((merged["first_impression_date"] == merged["first_impression_date_catalog"]).all())

    def test_new_creatives_were_not_active_earlier_in_the_window(self):
        for week in WEEKS:
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            q_start, _ = summary["quality_window"]
            n_start, _ = summary["new_creative_window"]
            new = pd.read_csv(week / "new_creatives_7d.csv")
            if new.empty:
                continue
            months = sorted({q_start[:7], n_start[:7]})
            daily = pd.concat(pd.read_csv(p) for m in months
                              for p in [ROOT / "data" / "synthetic" / f"creative_daily_{m}.csv"] if p.exists())
            earlier = daily[(daily["date"] >= q_start) & (daily["date"] < n_start) & (daily["impressions"] > 0)]
            hits = new.merge(earlier[["source", "creative"]].drop_duplicates(), on=["source", "creative"])
            self.assertTrue(hits.empty, f"{week.name}: new creatives active before the week")

    def test_quality_shares_are_bounded(self):
        for week in WEEKS:
            df = pd.read_csv(week / "traffic_quality.csv")
            for col in ("tracking_coverage", "flagged_share", "d1_retention", "d7_retention"):
                self.assertTrue(df[col].dropna().between(0, 1).all(), f"{week.name}: {col}")

    def test_decisions_only_when_week_complete(self):
        for week in WEEKS:
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            new = pd.read_csv(week / "new_creatives_7d.csv", keep_default_na=False)
            if not summary["complete"] and len(new):
                self.assertTrue((new["decision"] == "").all())


if __name__ == "__main__":
    unittest.main()
