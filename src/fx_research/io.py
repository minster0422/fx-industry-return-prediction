"""Input validation and encoding-safe readers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import REQUIRED_MARKET_COLUMNS, STOCK_TO_SECTOR


def read_csv_flexible(path: str | Path) -> pd.DataFrame:
    """Read a CSV using the encodings found in the 2025 project folder."""

    path = Path(path)
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding, skipinitialspace=True)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    joined = "\n".join(errors)
    raise ValueError(f"Could not decode {path} with a supported encoding:\n{joined}")


def load_market_data(path: str | Path) -> pd.DataFrame:
    """Load and validate the 50-stock panel used by the reconstruction."""

    data = read_csv_flexible(path)
    missing = sorted(REQUIRED_MARKET_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    data = data.copy()
    data["종목"] = data["종목"].astype(str).str.strip()
    data["일자"] = pd.to_datetime(data["일자"], errors="raise")
    numeric = sorted(REQUIRED_MARKET_COLUMNS - {"종목", "일자"})
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data["산업"] = data["종목"].map(STOCK_TO_SECTOR)
    unmapped = sorted(data.loc[data["산업"].isna(), "종목"].unique())
    if unmapped:
        raise ValueError(f"Unmapped tickers in the market file: {unmapped}")

    data["yearmon"] = data["일자"].dt.to_period("M").dt.to_timestamp()
    return data.sort_values(["종목", "일자"]).reset_index(drop=True)


def load_binary_matrix(path: str | Path) -> pd.DataFrame:
    """Load the reported 24-month industry up/down matrix."""

    data = read_csv_flexible(path)
    month_column = "년월" if "년월" in data.columns else data.columns[0]
    months = pd.to_datetime(data.pop(month_column), format="%y-%b", errors="raise")
    binary = data.apply(pd.to_numeric, errors="raise").astype(int)
    if not binary.isin([0, 1]).all().all():
        raise ValueError("The association matrix must contain only 0/1 values.")
    binary.index = months.dt.to_period("M").dt.to_timestamp()
    binary.index.name = "yearmon"
    return binary
