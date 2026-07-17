from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from fx_research.association import ordered_association_rules
from fx_research.legacy import legacy_mean_corr, prediction_metrics
from fx_research.v2 import add_dynamic_lead_signal


class AssociationTests(unittest.TestCase):
    def test_ordered_rule_metrics(self) -> None:
        binary = pd.DataFrame(
            {
                "A": [1, 1, 0, 0],
                "B": [1, 0, 1, 0],
            }
        )
        rules = ordered_association_rules(binary)
        row = rules[(rules["A"] == "A") & (rules["B"] == "B")].iloc[0]
        self.assertAlmostEqual(row["support"], 0.25)
        self.assertAlmostEqual(row["confidence"], 0.5)
        self.assertAlmostEqual(row["lift"], 1.0)


class LegacyAuditTests(unittest.TestCase):
    def test_any_positive_day_collapses_lift(self) -> None:
        rows = []
        for month in pd.date_range("2024-01-01", periods=14, freq="MS"):
            for ticker in ("A", "B"):
                rows.extend(
                    [
                        {"yearmon": month, "종목": ticker, "ret": -0.01},
                        {"yearmon": month, "종목": ticker, "ret": 0.01},
                    ]
                )
        mean_corr, lift = legacy_mean_corr(pd.DataFrame(rows))
        self.assertTrue((mean_corr["mean_corr"] == 0).all())
        self.assertEqual(int((lift.to_numpy() >= 1.4).sum()), 0)

    def test_prediction_metrics(self) -> None:
        predictions = pd.DataFrame(
            {
                "model": ["m"] * 2,
                "sector": ["s"] * 2,
                "target_month": pd.to_datetime(["2025-01-01", "2025-02-01"]),
                "actual": [0.01, -0.02],
                "prediction": [0.02, -0.01],
            }
        )
        metrics = prediction_metrics(predictions, last_n=None).iloc[0]
        self.assertAlmostEqual(metrics["rmse"], 0.01)
        self.assertEqual(metrics["hit_rate"], 1.0)


class V2Tests(unittest.TestCase):
    @staticmethod
    def panel() -> pd.DataFrame:
        rows = []
        months = pd.date_range("2023-01-01", periods=18, freq="MS")
        for index, month in enumerate(months):
            leader = 0.01 if index % 2 == 0 else -0.01
            follower = -0.01 if index == 0 else (0.01 if (index - 1) % 2 == 0 else -0.01)
            for sector, value in (("leader", leader), ("follower", follower)):
                rows.append(
                    {
                        "산업": sector,
                        "yearmon": month,
                        "mean_ret": value,
                        "mean_fx": 0.0,
                        "mean_flow": 0.0,
                        "next_ret": np.nan,
                    }
                )
        panel = pd.DataFrame(rows).sort_values(["산업", "yearmon"])
        panel["next_ret"] = panel.groupby("산업")["mean_ret"].shift(-1)
        return panel

    def test_dynamic_signal_does_not_use_future_months(self) -> None:
        panel = self.panel()
        first = add_dynamic_lead_signal(panel, min_history=6, min_lift=1.1)
        changed = panel.copy()
        changed.loc[changed["yearmon"] > pd.Timestamp("2024-01-01"), "mean_ret"] *= -1
        second = add_dynamic_lead_signal(changed, min_history=6, min_lift=1.1)
        key = (first["산업"] == "follower") & (first["yearmon"] == pd.Timestamp("2024-01-01"))
        self.assertAlmostEqual(
            float(first.loc[key, "network_signal"].iloc[0]),
            float(second.loc[key, "network_signal"].iloc[0]),
        )


if __name__ == "__main__":
    unittest.main()
