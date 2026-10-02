import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class PortfolioOutputTests(unittest.TestCase):
    def test_validation_passes(self):
        for month in ("2025-08", "2025-09"):
            path = ROOT / "outputs" / "analysis" / month / "validation.json"
            validation = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "PASS")
            self.assertEqual(validation["duplicate_device_ids"], 0)
            self.assertEqual(validation["orphan_event_devices"], 0)

    def test_retention_is_bounded(self):
        for month in ("2025-08", "2025-09"):
            df = pd.read_csv(ROOT / "outputs" / "analysis" / month / "campaign_summary.csv")
            for day in (1, 3, 7, 14):
                self.assertTrue(df[f"d{day}_retention"].dropna().between(0, 1).all())

    def test_revenue_reconciles(self):
        for month in ("2025-08", "2025-09"):
            df = pd.read_csv(ROOT / "outputs" / "analysis" / month / "campaign_summary.csv")
            diff = (df["ad_revenue_usd"] + df["iap_revenue_usd"] - df["total_revenue_usd"]).abs().max()
            self.assertLess(diff, 1e-8)


if __name__ == "__main__":
    unittest.main()
