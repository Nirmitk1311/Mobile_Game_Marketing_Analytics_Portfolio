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


class SqlLayerTests(unittest.TestCase):
    def test_sql_ghost_installs_match_python(self):
        f = ROOT / "outputs" / "sql" / "ghost_installs.csv"
        if not f.exists():
            self.skipTest("SQL layer not run")
        sql = pd.read_csv(f)
        players = pd.concat(pd.read_csv(p) for p in (ROOT / "outputs" / "analysis").glob("*/player_metrics.csv"))
        py = (1 - players.groupby(["source", "platform"])["tracked"].mean()).round(4)
        for r in sql.itertuples():
            self.assertAlmostEqual(r.ghost_share, py[(r.source, r.platform)], places=4)

    def test_sql_creative_roas_is_revenue_over_spend(self):
        f = ROOT / "outputs" / "sql" / "creative_roas.csv"
        if not f.exists():
            self.skipTest("SQL layer not run")
        d = pd.read_csv(f)
        d = d[d["spend_usd"] >= 10]   # revenue and spend are rounded to cents; tiny spends shift by rounding
        rel = (d["roas"] - d["revenue_usd"] / d["spend_usd"]).abs() / (d["revenue_usd"] / d["spend_usd"]).clip(lower=0.01)
        # roas has 4 decimals and revenue is rounded to cents, so tiny ROAS values (e.g. 0.0046 on $0.20 revenue) can differ
        # by up to 0.00005 + 0.005 / spend from rounding alone
        absdiff = (d["roas"] - d["revenue_usd"] / d["spend_usd"]).abs()
        self.assertTrue(((rel < 0.01) | (absdiff <= 0.00005 + 0.005 / d["spend_usd"] + 1e-9)).all())


class WeeklyReviewTests(unittest.TestCase):
    def test_new_creatives_start_inside_the_week(self):
        for week in WEEKS:
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            start, end = summary["new_creative_window"]
            new = pd.read_csv(week / "new_creatives_7d.csv")
            if new.empty:
                continue
            self.assertTrue(new["first_impression_date"].between(start, end).all())

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
            keys = ["source", "campaign", "creative"]
            hits = new.merge(earlier[keys].drop_duplicates(), on=keys)
            self.assertTrue(hits.empty, f"{week.name}: new creatives active in the same campaign before the week")

    def test_new_and_moved_creatives_left_out_of_quality_review(self):
        for week in WEEKS:
            new = pd.read_csv(week / "new_creatives_7d.csv")
            quality = pd.read_csv(week / "creative_quality_14d.csv")
            keys = ["source", "campaign", "creative"]
            self.assertTrue(new.merge(quality[keys], on=keys).empty, f"{week.name}: new creative in quality review")
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            q_start, _ = summary["quality_window"]
            n_start, _ = summary["new_creative_window"]
            months = sorted({q_start[:7], n_start[:7]})
            daily = pd.concat(pd.read_csv(p) for m in months
                              for p in [ROOT / "data" / "synthetic" / f"creative_daily_{m}.csv"] if p.exists())
            earlier = daily[(daily["date"] >= q_start) & (daily["date"] < n_start) & (daily["impressions"] > 0)]
            moved = new.merge(earlier[keys].drop_duplicates(), on=["source", "creative"], suffixes=("", "_before"))
            moved = moved[moved["campaign"] != moved["campaign_before"]][["source", "creative"]].drop_duplicates()
            self.assertTrue(quality.merge(moved, on=["source", "creative"]).empty, f"{week.name}: moved creative in quality review")

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

    def test_no_quality_decision_under_min_impressions(self):
        for week in WEEKS:
            q = pd.read_csv(week / "creative_quality_14d.csv", keep_default_na=False)
            if len(q) and "decision" in q:
                low = q[(q["impressions"].astype(float) < 7_000) & (q["decision"] != "")]
                self.assertTrue((low["decision"] == "Too early to judge").all())

    def test_incomplete_last_day_is_estimated_and_labelled(self):
        for week in WEEKS:
            summary = json.loads((week / "summary.json").read_text(encoding="utf-8"))
            if summary["data_through"] <= summary["week_end"]:
                self.assertLess(summary["spend_data_through"], summary["data_through"])
            else:
                self.assertEqual(summary["spend_data_through"], summary["week_end"])
                self.assertEqual(summary["estimated_installs"], 0)
            q = pd.read_csv(week / "creative_quality_14d.csv")
            if len(q):
                self.assertTrue((q["est_installs"] <= q["installs"] + 1e-9).all())
                self.assertTrue((q["actual_spend_usd"] <= q["spend_usd"] + 1e-6).all())
                # no boost: the estimate never lowers a creative's CPI below its real (complete-day) CPI
                real = q[(q["installs"] - q["est_installs"] > 0) & (q["actual_spend_usd"] > 0)]
                real_cpi = real["actual_spend_usd"] / (real["installs"] - real["est_installs"])
                self.assertTrue((real["cpi_usd"] >= real_cpi - 1e-6).all(), f"{week.name}: estimate lowered a CPI")

    def test_d30_roas_is_revenue_over_spend(self):
        for week in WEEKS:
            d = pd.read_csv(week / "d30_roas.csv")
            for r in d[d["spend_usd"] > 0].itertuples():
                self.assertAlmostEqual(r.d30_roas, r.revenue_30d_usd / r.spend_usd, places=6)
                self.assertGreaterEqual(r.revenue_30d_usd + 1e-9, r.revenue_7d_usd)


if __name__ == "__main__":
    unittest.main()
