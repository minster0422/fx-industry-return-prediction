"""A transparent Python reconstruction of the 2025 R analysis flow."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .constants import LEGACY_CORR_SECTORS


def prepare_legacy_clean(data: pd.DataFrame) -> pd.DataFrame:
    """Apply the complete-case filter and global 1/99% flow winsorization."""

    required = ["ret", "fore_chg", "USD_ret", "EUR_ret", "JPY100_ret", "CNY_ret"]
    clean = data.dropna(subset=required).copy()
    low, high = clean["fore_chg"].quantile([0.01, 0.99])
    clean["fore_chg"] = clean["fore_chg"].clip(low, high)
    return clean


def compute_fx_features(data: pd.DataFrame) -> pd.DataFrame:
    """Recreate the three stock-level features used for K-means."""

    rows: list[dict[str, float | str]] = []
    for ticker, group in data.dropna(subset=["ret", "USD_ret", "fore_chg"]).groupby("종목"):
        x = group["USD_ret"].to_numpy(dtype=float)
        y = group["ret"].to_numpy(dtype=float)
        variance = float(np.var(x, ddof=1))
        beta = float(np.cov(x, y, ddof=1)[0, 1] / variance) if variance else np.nan
        rows.append(
            {
                "ticker": ticker,
                "avg_return": float(np.mean(y)),
                "foreign_flow": float(group["fore_chg"].mean()),
                "fx_sensitivity": beta,
            }
        )
    return pd.DataFrame(rows).dropna().sort_values("ticker").reset_index(drop=True)


def cluster_legacy(
    features: pd.DataFrame, chosen_k: int = 4, random_state: int = 123
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the scaled K-means flow and return assignments plus diagnostics."""

    feature_columns = ["avg_return", "foreign_flow", "fx_sensitivity"]
    scaled = StandardScaler().fit_transform(features[feature_columns])
    max_k = min(10, len(features) - 1)
    diagnostics: list[dict[str, float | int]] = []
    for k in range(1, max_k + 1):
        model = KMeans(n_clusters=k, n_init=25, random_state=random_state)
        labels = model.fit_predict(scaled)
        diagnostics.append(
            {
                "k": k,
                "wss": float(model.inertia_),
                "silhouette": (
                    float(silhouette_score(scaled, labels)) if 2 <= k < len(features) else np.nan
                ),
            }
        )

    model = KMeans(n_clusters=chosen_k, n_init=25, random_state=random_state)
    result = features.copy()
    result["cluster"] = model.fit_predict(scaled) + 1
    return result, pd.DataFrame(diagnostics)


def legacy_mean_corr(
    clean: pd.DataFrame, lift_threshold: float = 1.4
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproduce the stock-level mean_corr block exactly enough to audit it.

    The original code marks a stock as up when it has *any* positive daily
    return in a month. With ordinary daily data this is almost always true,
    which collapses the lift matrix to 1 and mean_corr to zero.
    """

    up = (
        clean.groupby(["yearmon", "종목"])["ret"]
        .apply(lambda values: bool((values > 0).any()))
        .unstack(fill_value=False)
        .astype(int)
    )
    probabilities = up.mean(axis=0)
    joint = up.T.dot(up) / len(up)
    lift = joint.div(probabilities, axis=0).div(probabilities, axis=1)
    lift = lift.replace([np.inf, -np.inf], np.nan)
    lift_values = lift.to_numpy(copy=True)
    np.fill_diagonal(lift_values, np.nan)
    lift.iloc[:, :] = lift_values

    monthly_returns = clean.groupby(["yearmon", "종목"])["ret"].mean().unstack()
    correlations = monthly_returns.corr()
    rows: list[dict[str, float | str | int]] = []
    for ticker in up.columns:
        partners = lift.columns[lift.loc[ticker] >= lift_threshold].tolist()
        value = 0.0 if not partners else float(correlations.loc[ticker, partners].mean())
        rows.append(
            {
                "ticker": ticker,
                "mean_corr": value,
                "partner_count": len(partners),
                "up_months": int(up[ticker].sum()),
            }
        )
    return pd.DataFrame(rows), lift


def build_legacy_monthly_panel(
    clean: pd.DataFrame, mean_corr: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate daily observations and create the next-month target."""

    joined = clean.merge(mean_corr[["ticker", "mean_corr"]], left_on="종목", right_on="ticker")
    monthly = (
        joined.groupby(["산업", "yearmon"], as_index=False)
        .agg(
            mean_ret=("ret", "mean"),
            mean_fx=("USD_ret", "mean"),
            mean_flow=("fore_chg", "mean"),
            avg_corr=("mean_corr", "mean"),
        )
        .sort_values(["산업", "yearmon"])
    )
    monthly["next_ret"] = monthly.groupby("산업")["mean_ret"].shift(-1)
    return monthly.dropna(subset=["next_ret"]).reset_index(drop=True)


def _forest(trees: int, seed: int) -> RandomForestRegressor:
    """Approximate R randomForest regression defaults deterministically."""

    return RandomForestRegressor(
        n_estimators=trees,
        random_state=seed,
        max_features=1,
        min_samples_leaf=5,
        n_jobs=-1,
    )


def walk_forward_legacy(
    panel: pd.DataFrame,
    trees: int = 300,
    min_train: int = 12,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run the expanding-window model used in the presentation.

    Both the feature month and the correctly aligned target month are kept.
    The 2025 chart used feature_month on the x-axis even though `actual` is
    next month's return.
    """

    rng = np.random.default_rng(random_state)
    rows: list[dict[str, float | str | pd.Timestamp | int]] = []
    for sector, group in panel.groupby("산업", sort=True):
        group = group.sort_values("yearmon").reset_index(drop=True)
        features = ["mean_ret", "mean_fx", "mean_flow"]
        if sector in LEGACY_CORR_SECTORS:
            features.append("avg_corr")
        for index in range(min_train, len(group)):
            model = _forest(trees, int(rng.integers(0, 2**31 - 1)))
            model.fit(group.loc[: index - 1, features], group.loc[: index - 1, "next_ret"])
            prediction = float(model.predict(group.loc[[index], features])[0])
            feature_month = pd.Timestamp(group.loc[index, "yearmon"])
            rows.append(
                {
                    "model": "legacy_rf",
                    "sector": sector,
                    "feature_month": feature_month,
                    "target_month": feature_month + pd.offsets.MonthBegin(1),
                    "actual": float(group.loc[index, "next_ret"]),
                    "prediction": prediction,
                    "training_months": index,
                }
            )
    return pd.DataFrame(rows)


def prediction_metrics(predictions: pd.DataFrame, last_n: int | None = 6) -> pd.DataFrame:
    """Calculate RMSE, MAE, and directional hit rate by model and sector."""

    if predictions.empty:
        return pd.DataFrame(columns=["model", "sector", "rmse", "mae", "hit_rate", "n_months"])
    ordered = predictions.sort_values(["model", "sector", "target_month"])
    if last_n is not None:
        ordered = ordered.groupby(["model", "sector"], group_keys=False).tail(last_n)
    rows: list[dict[str, float | str | int]] = []
    for (model, sector), group in ordered.groupby(["model", "sector"], sort=True):
        error = group["prediction"] - group["actual"]
        hit_rate = (
            np.nan
            if model == "zero"
            else float((np.sign(group["prediction"]) == np.sign(group["actual"])).mean())
        )
        rows.append(
            {
                "model": model,
                "sector": sector,
                "rmse": float(np.sqrt(np.mean(error**2))),
                "mae": float(np.mean(np.abs(error))),
                "hit_rate": hit_rate,
                "n_months": len(group),
            }
        )
    return pd.DataFrame(rows)
