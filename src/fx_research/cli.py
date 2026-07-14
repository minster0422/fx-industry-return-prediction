"""Command-line entry point for the reconstruction and V2 comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .association import ordered_association_rules, reconcile_reported_rules
from .io import load_binary_matrix, load_market_data, read_csv_flexible
from .legacy import (
    build_legacy_monthly_panel,
    cluster_legacy,
    compute_fx_features,
    legacy_mean_corr,
    prediction_metrics,
    prepare_legacy_clean,
    walk_forward_legacy,
)
from .v2 import add_dynamic_lead_signal, build_monthly_panel, v2_metrics, walk_forward_v2


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output)
    reconstruction = output / "reconstruction"
    v2_output = output / "v2"
    reconstruction.mkdir(parents=True, exist_ok=True)
    v2_output.mkdir(parents=True, exist_ok=True)

    market = load_market_data(args.input)
    clean = prepare_legacy_clean(market)

    features = compute_fx_features(market)
    clusters, diagnostics = cluster_legacy(features)
    cluster_summary = (
        clusters.groupby("cluster")[["avg_return", "foreign_flow", "fx_sensitivity"]]
        .agg(["count", "mean", "min", "max"])
    )
    cluster_summary.columns = ["_".join(column) for column in cluster_summary.columns]
    cluster_summary = cluster_summary.reset_index()
    _write_csv(clusters, reconstruction / "cluster_assignments.csv")
    _write_csv(diagnostics, reconstruction / "cluster_diagnostics.csv")
    _write_csv(cluster_summary, reconstruction / "cluster_summary.csv")

    binary = load_binary_matrix(args.binary)
    reported = read_csv_flexible(args.reported_rules)
    calculated_rules = ordered_association_rules(binary)
    reconciliation = reconcile_reported_rules(binary, reported)
    _write_csv(calculated_rules, reconstruction / "association_rules_recomputed.csv")
    _write_csv(reconciliation, reconstruction / "association_rules_reconciliation.csv")

    mean_corr, lift = legacy_mean_corr(clean)
    _write_csv(mean_corr, reconstruction / "legacy_mean_corr.csv")
    lift_export = lift.reset_index().rename(columns={"종목": "ticker", "index": "ticker"})
    _write_csv(lift_export, reconstruction / "legacy_stock_lift_matrix.csv")

    legacy_panel = build_legacy_monthly_panel(clean, mean_corr)
    legacy_predictions = walk_forward_legacy(legacy_panel, trees=args.trees)
    legacy_metrics = prediction_metrics(legacy_predictions, last_n=6)
    _write_csv(legacy_panel, reconstruction / "legacy_monthly_panel.csv")
    _write_csv(legacy_predictions, reconstruction / "legacy_predictions.csv")
    _write_csv(legacy_metrics, reconstruction / "legacy_metrics_latest6.csv")

    published_metrics = read_csv_flexible(args.published_metrics)
    reconstructed_metrics = legacy_metrics.assign(
        reconstructed_rmse_percent_points=legacy_metrics["rmse"] * 100
    ).rename(
        columns={
            "sector": "sector",
            "hit_rate": "reconstructed_hit_rate",
            "n_months": "reconstructed_n_months",
        }
    )
    metric_comparison = published_metrics.rename(
        columns={
            "rmse_percent_points": "reported_rmse_percent_points",
            "hit_rate": "reported_hit_rate",
            "n_months": "reported_n_months",
        }
    ).merge(
        reconstructed_metrics[
            [
                "sector",
                "reconstructed_rmse_percent_points",
                "reconstructed_hit_rate",
                "reconstructed_n_months",
            ]
        ],
        on="sector",
        how="outer",
    )
    metric_comparison["rmse_delta_percent_points"] = (
        metric_comparison["reconstructed_rmse_percent_points"]
        - metric_comparison["reported_rmse_percent_points"]
    )
    metric_comparison["hit_rate_delta"] = (
        metric_comparison["reconstructed_hit_rate"] - metric_comparison["reported_hit_rate"]
    )
    _write_csv(metric_comparison, reconstruction / "published_vs_python_metrics.csv")

    monthly = build_monthly_panel(clean)
    monthly = add_dynamic_lead_signal(
        monthly,
        min_history=args.min_history,
        min_support=args.min_support,
        min_lift=args.min_lift,
    )
    v2_predictions = walk_forward_v2(monthly, trees=args.trees)
    latest_metrics = v2_metrics(v2_predictions, last_n=6)
    all_metrics = v2_metrics(v2_predictions, last_n=None)
    _write_csv(monthly, v2_output / "monthly_panel_with_network_signal.csv")
    _write_csv(v2_predictions, v2_output / "predictions.csv")
    _write_csv(latest_metrics, v2_output / "metrics_latest6.csv")
    _write_csv(all_metrics, v2_output / "metrics_all_walk_forward.csv")

    silhouette_rows = diagnostics.dropna(subset=["silhouette"])
    best_k = int(silhouette_rows.loc[silhouette_rows["silhouette"].idxmax(), "k"])
    finite_lift = lift.to_numpy(dtype=float)

    def aggregate_rmse(frame: pd.DataFrame, model: str) -> float:
        selected = frame.loc[frame["model"] == model]
        return float(np.sqrt(np.mean((selected["prediction"] - selected["actual"]) ** 2)))

    latest_predictions = (
        v2_predictions.sort_values(["model", "sector", "target_month"])
        .groupby(["model", "sector"], group_keys=False)
        .tail(6)
    )
    base_all = aggregate_rmse(v2_predictions, "rf_base")
    network_all = aggregate_rmse(v2_predictions, "rf_network")
    summary: dict[str, object] = {
        "input": {
            "rows": len(market),
            "stocks": int(market["종목"].nunique()),
            "industries": int(market["산업"].nunique()),
            "trading_days": int(market["일자"].nunique()),
            "start": market["일자"].min().date().isoformat(),
            "end": market["일자"].max().date().isoformat(),
        },
        "clustering": {
            "chosen_k_2025": 4,
            "best_silhouette_k_in_python_port": best_k,
            "k4_silhouette": float(diagnostics.loc[diagnostics["k"] == 4, "silhouette"].iloc[0]),
        },
        "association": {
            "reported_rules": len(reported),
            "rules_with_any_metric_delta_over_1e_6": int(
                (
                    reconciliation[["support_delta", "confidence_delta", "lift_delta"]]
                    .abs()
                    .max(axis=1)
                    > 1e-6
                ).sum()
            ),
        },
        "legacy_mean_corr": {
            "max_stock_lift": float(np.nanmax(finite_lift)),
            "pairs_at_or_above_1_4": int(np.nansum(finite_lift >= 1.4)),
            "nonzero_stocks": int((mean_corr["mean_corr"].abs() > 0).sum()),
        },
        "prediction": {
            "feature_month_start": legacy_predictions["feature_month"].min().date().isoformat(),
            "feature_month_end": legacy_predictions["feature_month"].max().date().isoformat(),
            "target_month_start": legacy_predictions["target_month"].min().date().isoformat(),
            "target_month_end": legacy_predictions["target_month"].max().date().isoformat(),
            "walk_forward_predictions": len(legacy_predictions),
        },
        "v2_proof_of_concept": {
            "rf_base_rmse_all": base_all,
            "rf_network_rmse_all": network_all,
            "network_relative_rmse_change_all": (network_all / base_all) - 1.0,
            "rf_base_rmse_latest6": aggregate_rmse(latest_predictions, "rf_base"),
            "rf_network_rmse_latest6": aggregate_rmse(latest_predictions, "rf_network"),
            "zero_rmse_all": aggregate_rmse(v2_predictions, "zero"),
            "conclusion": "No material incremental value is established in the 24-month sample.",
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Reconstruct the 2025 study and run the leakage-aware V2 comparison."
    )
    parser.add_argument("--input", required=True, help="Path to merged_50stocks_fx_multi.csv")
    parser.add_argument(
        "--binary",
        default=project_root / "data" / "reference" / "sector_binary_2025.csv",
        help="Reported 24-month sector up/down matrix",
    )
    parser.add_argument(
        "--reported-rules",
        default=project_root / "data" / "reference" / "association_rules_reported.csv",
        help="Association-rule table shown in the 2025 materials",
    )
    parser.add_argument(
        "--published-metrics",
        default=project_root / "data" / "reference" / "published_metrics.csv",
        help="RMSE and hit-rate table shown in the final presentation",
    )
    parser.add_argument("--output", default=project_root / "results" / "generated")
    parser.add_argument("--trees", type=int, default=300)
    parser.add_argument("--min-history", type=int, default=12)
    parser.add_argument("--min-support", type=float, default=0.10)
    parser.add_argument("--min-lift", type=float, default=1.20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
