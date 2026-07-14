"""Same-month association audit and lagged association utilities."""

from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd


RULE_COLUMNS = ["A", "B", "support", "confidence", "lift"]


def ordered_association_rules(binary: pd.DataFrame) -> pd.DataFrame:
    """Calculate all ordered 1-to-1 rules from a 0/1 monthly matrix."""

    if binary.empty:
        return pd.DataFrame(columns=RULE_COLUMNS)
    matrix = binary.astype(int)
    rows: list[dict[str, float | str]] = []
    for antecedent, consequent in permutations(matrix.columns, 2):
        a = matrix[antecedent].astype(bool)
        b = matrix[consequent].astype(bool)
        support = float((a & b).mean())
        p_a = float(a.mean())
        p_b = float(b.mean())
        confidence = support / p_a if p_a else np.nan
        lift = confidence / p_b if p_b else np.nan
        rows.append(
            {
                "A": antecedent,
                "B": consequent,
                "support": support,
                "confidence": confidence,
                "lift": lift,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["lift", "confidence", "support"], ascending=False)
        .reset_index(drop=True)
    )


def reconcile_reported_rules(
    binary: pd.DataFrame, reported: pd.DataFrame
) -> pd.DataFrame:
    """Compare reported rule metrics with metrics recomputed from the matrix."""

    normalized = reported.rename(
        columns={"지지도": "support_reported", "신뢰도": "confidence_reported", "향상도": "lift_reported"}
    ).copy()
    calculated = ordered_association_rules(binary).rename(
        columns={"support": "support_calculated", "confidence": "confidence_calculated", "lift": "lift_calculated"}
    )
    merged = normalized.merge(calculated, on=["A", "B"], how="left")
    for metric in ("support", "confidence", "lift"):
        merged[f"{metric}_delta"] = (
            merged[f"{metric}_reported"] - merged[f"{metric}_calculated"]
        )
    return merged
