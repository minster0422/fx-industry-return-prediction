"""Leakage-aware upgrade that converts the original idea into a testable V2."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .legacy import _forest, prediction_metrics


def build_monthly_panel(data: pd.DataFrame) -> pd.DataFrame:
    """Build a clean monthly industry panel without creating future features."""

    monthly = (
        data.groupby(["산업", "yearmon"], as_index=False)
        .agg(
            mean_ret=("ret", "mean"),
            mean_fx=("USD_ret", "mean"),
            mean_flow=("fore_chg", "mean"),
        )
        .sort_values(["산업", "yearmon"])
    )
    monthly["next_ret"] = monthly.groupby("산업")["mean_ret"].shift(-1)
    return monthly


def add_dynamic_lead_signal(
    panel: pd.DataFrame,
    min_history: int = 12,
    min_support: float = 0.10,
    min_lift: float = 1.20,
) -> pd.DataFrame:
    """Add a time-varying, lagged industry-network signal.

    For feature month t, relationships are estimated only from pairs
    (leader at s, follower at s+1) whose follower month is no later than t.
    Current-month leader returns are then combined to predict the follower at
    t+1. No observation after t is used in the feature.
    """

    result = panel.copy()
    returns = result.pivot(index="yearmon", columns="산업", values="mean_ret").sort_index()
    sectors = list(returns.columns)
    signal_rows: list[dict[str, float | str | pd.Timestamp | int]] = []

    for position, month in enumerate(returns.index):
        current = returns.loc[month]
        if position < min_history:
            for follower in sectors:
                signal_rows.append(
                    {"yearmon": month, "산업": follower, "network_signal": 0.0, "leader_count": 0}
                )
            continue

        leader_history = (returns.iloc[:position] > 0).astype(int)
        follower_history = (returns.iloc[1 : position + 1] > 0).astype(int)
        follower_history.index = leader_history.index

        for follower in sectors:
            selected: list[tuple[str, float]] = []
            follower_up = follower_history[follower].astype(bool)
            p_follower = float(follower_up.mean())
            if p_follower:
                for leader in sectors:
                    if leader == follower:
                        continue
                    leader_up = leader_history[leader].astype(bool)
                    p_leader = float(leader_up.mean())
                    if not p_leader:
                        continue
                    support = float((leader_up & follower_up).mean())
                    confidence = support / p_leader
                    lift = confidence / p_follower
                    if support >= min_support and lift >= min_lift:
                        selected.append((leader, lift))

            if selected:
                weights = np.array([max(lift - 1.0, 1e-12) for _, lift in selected])
                values = np.array([float(current[leader]) for leader, _ in selected])
                signal = float(np.average(values, weights=weights))
            else:
                signal = 0.0
            signal_rows.append(
                {
                    "yearmon": month,
                    "산업": follower,
                    "network_signal": signal,
                    "leader_count": len(selected),
                }
            )

    signals = pd.DataFrame(signal_rows)
    return result.merge(signals, on=["산업", "yearmon"], how="left")


def walk_forward_v2(
    panel: pd.DataFrame,
    trees: int = 300,
    min_train: int = 12,
    random_state: int = 42,
) -> pd.DataFrame:
    """Compare naive baselines, a base RF, and the network-augmented RF."""

    rng = np.random.default_rng(random_state)
    rows: list[dict[str, float | str | pd.Timestamp | int]] = []
    for sector, group in panel.dropna(subset=["next_ret"]).groupby("산업", sort=True):
        group = group.sort_values("yearmon").reset_index(drop=True)
        for index in range(min_train, len(group)):
            feature_month = pd.Timestamp(group.loc[index, "yearmon"])
            actual = float(group.loc[index, "next_ret"])
            common = {
                "sector": sector,
                "feature_month": feature_month,
                "target_month": feature_month + pd.offsets.MonthBegin(1),
                "actual": actual,
                "training_months": index,
            }
            rows.append({**common, "model": "zero", "prediction": 0.0})
            rows.append(
                {**common, "model": "last_return", "prediction": float(group.loc[index, "mean_ret"])}
            )

            feature_sets = {
                "rf_base": ["mean_ret", "mean_fx", "mean_flow"],
                "rf_network": ["mean_ret", "mean_fx", "mean_flow", "network_signal", "leader_count"],
            }
            for model_name, features in feature_sets.items():
                model = _forest(trees, int(rng.integers(0, 2**31 - 1)))
                model.fit(group.loc[: index - 1, features], group.loc[: index - 1, "next_ret"])
                prediction = float(model.predict(group.loc[[index], features])[0])
                rows.append({**common, "model": model_name, "prediction": prediction})
    return pd.DataFrame(rows)


def v2_metrics(predictions: pd.DataFrame, last_n: int | None = 6) -> pd.DataFrame:
    return prediction_metrics(predictions, last_n=last_n)
