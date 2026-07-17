from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fx_research.constants import SECTOR_STOCKS
from fx_research.v2_1_feasibility import (
    ApiResponse,
    FIXED_SAMPLE,
    SafeApiClient,
    _legacy_rows,
    _schema_hash,
    _timestamp_record,
    _write_ticker_mapping,
    credential_status,
)


class CredentialSafetyTests(unittest.TestCase):
    def test_status_never_returns_value(self) -> None:
        with patch.dict(os.environ, {"KRX_API_KEY": "secret-value-123456789"}, clear=False):
            self.assertEqual(credential_status("KRX_API_KEY"), "SET")

    def test_http_error_log_contains_no_url_or_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "requests.jsonl"
            client = SafeApiClient(log)
            client._log_failure(
                "ECOS_TEST",
                datetime(2026, 7, 17, tzinfo=timezone.utc),
                401,
                "HTTP_ERROR",
            )
            text = log.read_text(encoding="utf-8")
            self.assertNotIn("http://", text.lower())
            self.assertNotIn("https://", text.lower())
            self.assertNotIn("secret", text.lower())
            self.assertTrue(json.loads(text)["credential_redacted"])


class MappingTests(unittest.TestCase):
    def test_legacy_rows_follow_constants_insertion_order(self) -> None:
        expected = [
            (sector, ticker)
            for sector, tickers in SECTOR_STOCKS.items()
            for ticker in tickers
        ]
        self.assertEqual(_legacy_rows(), expected)
        self.assertEqual(len(expected), 50)

    def test_official_mapping_requires_code_isin_market_and_listing_date(self) -> None:
        rows = []
        for index, (_, ticker) in enumerate(_legacy_rows(), start=1):
            rows.append(
                {
                    "ISU_NM": ticker,
                    "ISU_ABBRV": ticker,
                    "ISU_SRT_CD": f"{index:06d}",
                    "ISU_CD": f"KR7000{index:05d}",
                    "MKT_TP_NM": "KOSPI",
                    "LIST_DD": "20000101",
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapping.csv"
            counts = _write_ticker_mapping(path, rows, [])
            with path.open(encoding="utf-8", newline="") as handle:
                mapped = list(csv.DictReader(handle))
        self.assertEqual(counts["mapped"], 50)
        self.assertEqual(counts["duplicate_nonblank_codes"], 0)
        self.assertEqual(
            {row["legacy_ticker_name"] for row in mapped if row["fixed_sample_5"] == "true"},
            FIXED_SAMPLE,
        )


class TimestampTests(unittest.TestCase):
    def test_timestamp_record_has_only_sanitized_metadata(self) -> None:
        payload = {"OutBlock_1": [{"BAS_DD": "20260717", "TDD_CLSPRC": "100"}]}
        response = ApiResponse(
            payload=payload,
            http_status=200,
            headers={"Date": "Fri, 17 Jul 2026 09:30:00 GMT"},
            requested_at_utc=datetime(2026, 7, 17, 9, 30, tzinfo=timezone.utc),
        )
        record = _timestamp_record("KRX", "kospi_stock_daily", response)
        self.assertTrue(record["credential_redacted"])
        self.assertTrue(record["current_day_data_present"])
        self.assertNotIn("payload", record)
        self.assertNotIn("url", record)
        self.assertEqual(record["schema_hash"], _schema_hash(payload))


if __name__ == "__main__":
    unittest.main()
