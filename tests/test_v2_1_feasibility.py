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
    FeasibilityError,
    FIXED_SAMPLE,
    SafeApiClient,
    _coerce_daily_numeric_fields,
    _daily_stock_key,
    _fixed_daily_rows,
    _guard_protocol,
    _legacy_rows,
    _read_fixed_codes,
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

    @staticmethod
    def _official_rows_with_renamed_hdc(*, isin: str = "KR7294870001") -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for index, (_, ticker) in enumerate(_legacy_rows(), start=1):
            if ticker == "HDC현대산업개발":
                rows.append(
                    {
                        "ISU_NM": "IPARK현대산업개발",
                        "ISU_ABBRV": "IPARK현대산업개발",
                        "ISU_SRT_CD": "294870",
                        "ISU_CD": isin,
                        "MKT_TP_NM": "KOSPI",
                        "LIST_DD": "20180612",
                    }
                )
                continue
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
        return rows

    @staticmethod
    def _write_hdc_provenance(path: Path) -> None:
        path.write_text(
            "legacy_ticker_name,official_name_before,official_name_after,ticker_code,"
            "isin_code,market,listing_date,evidence_date_before,evidence_date_after,"
            "source_endpoint,matching_rule,status,checked_at\n"
            "HDC현대산업개발,HDC현대산업개발,IPARK현대산업개발,294870,"
            "KR7294870001,KOSPI,20180612,2025-12-30,2026-06-30,"
            "KRX_STOCK_BASIC_INFORMATION,EXACT_SAME_TICKER_CODE_AND_ISIN,"
            "VERIFIED_CODE_AND_ISIN,2026-07-20\n",
            encoding="utf-8",
        )

    def test_renamed_hdc_maps_only_by_verified_code_and_isin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_path = root / "mapping.csv"
            provenance_path = root / "provenance.csv"
            self._write_hdc_provenance(provenance_path)
            counts = _write_ticker_mapping(
                mapping_path,
                self._official_rows_with_renamed_hdc(),
                [],
                provenance_path,
            )
            with mapping_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        hdc = next(row for row in rows if row["legacy_ticker_name"] == "HDC현대산업개발")
        self.assertEqual(counts["mapped"], 50)
        self.assertEqual(hdc["ticker_code"], "294870")
        self.assertEqual(hdc["isin_code"], "KR7294870001")
        self.assertEqual(hdc["mapping_status"], "MAPPED_OFFICIAL_IDENTITY_PROVENANCE")

    def test_renamed_hdc_does_not_map_when_isin_differs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_path = root / "mapping.csv"
            provenance_path = root / "provenance.csv"
            self._write_hdc_provenance(provenance_path)
            counts = _write_ticker_mapping(
                mapping_path,
                self._official_rows_with_renamed_hdc(isin="KR7294879999"),
                [],
                provenance_path,
            )
            with mapping_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        hdc = next(row for row in rows if row["legacy_ticker_name"] == "HDC현대산업개발")
        self.assertEqual(counts["mapped"], 49)
        self.assertEqual(hdc["mapping_status"], "UNMAPPED")
        self.assertEqual(hdc["ticker_code"], "")

    def test_renamed_hdc_does_not_map_when_short_code_differs(self) -> None:
        rows = self._official_rows_with_renamed_hdc()
        renamed = next(row for row in rows if row["ISU_NM"] == "IPARK현대산업개발")
        renamed["ISU_SRT_CD"] = "294871"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping_path = root / "mapping.csv"
            provenance_path = root / "provenance.csv"
            self._write_hdc_provenance(provenance_path)
            counts = _write_ticker_mapping(mapping_path, rows, [], provenance_path)
            with mapping_path.open(encoding="utf-8", newline="") as handle:
                mapped_rows = list(csv.DictReader(handle))
        hdc = next(
            row for row in mapped_rows if row["legacy_ticker_name"] == "HDC현대산업개발"
        )
        self.assertEqual(counts["mapped"], 49)
        self.assertEqual(hdc["mapping_status"], "UNMAPPED")
        self.assertEqual(hdc["ticker_code"], "")


class DailySchemaTests(unittest.TestCase):
    def test_daily_rows_use_isu_cd_not_basic_info_short_code_field(self) -> None:
        fixed = {"000660": ("SK하이닉스", "KOSPI")}
        rows = [
            {"BAS_DD": "20260401", "ISU_CD": "000660"},
            {"BAS_DD": "20260401", "ISU_CD": "KR7000660001", "ISU_SRT_CD": "000660"},
            {"BAS_DD": "20260401", "ISU_SRT_CD": "000660"},
        ]
        selected = _fixed_daily_rows(rows, fixed)
        self.assertEqual(selected, [rows[0]])
        self.assertEqual(_daily_stock_key(selected[0]), ("20260401", "000660"))

    def test_numeric_conversion_handles_commas_missing_and_failures(self) -> None:
        converted, summary = _coerce_daily_numeric_fields(
            [
                {
                    "TDD_CLSPRC": "1,234.5",
                    "FLUC_RT": "-0.75",
                    "ACC_TRDVOL": "1,000",
                    "ACC_TRDVAL": "2000",
                    "MKTCAP": "3000",
                },
                {
                    "TDD_CLSPRC": "bad",
                    "FLUC_RT": "-",
                    "ACC_TRDVOL": "",
                    "ACC_TRDVAL": "2.5",
                    "MKTCAP": None,
                },
            ]
        )
        self.assertEqual(converted[0]["TDD_CLSPRC"], 1234.5)
        self.assertEqual(converted[0]["FLUC_RT"], -0.75)
        self.assertEqual(converted[0]["ACC_TRDVOL"], 1000)
        self.assertIsInstance(converted[0]["ACC_TRDVAL"], int)
        self.assertTrue(summary["TDD_CLSPRC"]["conversion_failures"] == 1)
        self.assertEqual(summary["FLUC_RT"]["missing_count"], 1)
        self.assertEqual(summary["ACC_TRDVOL"]["missing_count"], 1)
        self.assertEqual(summary["ACC_TRDVAL"]["conversion_failures"], 1)
        self.assertEqual(summary["MKTCAP"]["missing_count"], 1)
        self.assertNotIn("raw_values", summary["TDD_CLSPRC"])

    def test_fixed_sample_codes_must_be_unique_six_digit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapping.csv"
            rows = []
            for ticker in sorted(FIXED_SAMPLE):
                rows.append(
                    {
                        "legacy_ticker_name": ticker,
                        "ticker_code": "000001",
                        "market": "KOSPI",
                        "fixed_sample_5": "true",
                    }
                )
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(FeasibilityError, "FIXED_SAMPLE_CODE_DUPLICATE"):
                _read_fixed_codes(path)


class ProtocolGuardTests(unittest.TestCase):
    def test_results_directory_blocks_feasibility_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "configs"
            config_dir.mkdir()
            config_path = config_dir / "v2_1_protocol.yaml"
            config_path.write_text(
                'status: "DRAFT_NOT_FROZEN"\nresults_may_run: false\n',
                encoding="utf-8",
            )
            (root / "results" / "v2_1").mkdir(parents=True)
            with self.assertRaisesRegex(
                FeasibilityError, "RESULTS_V2_1_MUST_BE_ABSENT_FOR_FEASIBILITY"
            ):
                _guard_protocol(config_path)


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
