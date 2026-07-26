from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from fx_research.v2_1_collection import (
    ENDPOINT_SCHEMAS,
    CheckpointStore,
    CollectionError,
    atomic_write_bytes,
    build_collection_plan,
    filter_u0_daily_rows,
    load_u0_mapping,
    request_id,
    retry_backoff_seconds,
    run_collect,
    run_dry_run,
    run_schema_sample_mode,
    sha256_bytes,
    sha256_file,
    should_retry_http,
    should_retry_result_code,
)


ROOT = Path(__file__).resolve().parents[1]
COLLECTION_CONFIG = ROOT / "configs" / "v2_1_collection.yaml"
PROTOCOL_CONFIG = ROOT / "configs" / "v2_1_protocol.yaml"
MAPPING = ROOT / "data" / "metadata" / "v2_1_ticker_mapping.csv"


class CollectionFixture:
    @staticmethod
    def copy(directory: str) -> tuple[Path, Path, Path, Path]:
        root = Path(directory)
        (root / "configs").mkdir(parents=True)
        (root / "data" / "metadata").mkdir(parents=True)
        config = root / "configs" / "v2_1_collection.yaml"
        protocol = root / "configs" / "v2_1_protocol.yaml"
        mapping = root / "data" / "metadata" / "v2_1_ticker_mapping.csv"
        shutil.copyfile(COLLECTION_CONFIG, config)
        shutil.copyfile(PROTOCOL_CONFIG, protocol)
        shutil.copyfile(MAPPING, mapping)
        return root, config, protocol, mapping


class EndpointSchemaTests(unittest.TestCase):
    def test_isu_cd_meaning_is_endpoint_specific(self) -> None:
        basic = ENDPOINT_SCHEMAS["kospi_stock_basic"]
        daily = ENDPOINT_SCHEMAS["kospi_stock_daily"]
        self.assertEqual(basic.ticker_code_field, "ISU_SRT_CD")
        self.assertEqual(basic.isin_field, "ISU_CD")
        self.assertEqual(daily.ticker_code_field, "ISU_CD")
        self.assertIsNone(daily.isin_field)

    def test_daily_filter_rejects_basic_info_short_code_field(self) -> None:
        mapping = load_u0_mapping(MAPPING)
        rows = [
            {"BAS_DD": "20260401", "ISU_CD": "000660"},
            {"BAS_DD": "20260401", "ISU_CD": "KR7000660001", "ISU_SRT_CD": "000660"},
            {"BAS_DD": "20260401", "ISU_SRT_CD": "000660"},
        ]
        self.assertEqual(filter_u0_daily_rows(rows, mapping), [rows[0]])


class PlanTests(unittest.TestCase):
    def test_plan_is_no_network_no_write_and_u0_only(self) -> None:
        raw_root = ROOT / "data" / "raw" / "v2_1"
        before = raw_root.exists()
        with patch(
            "fx_research.v2_1_feasibility.SafeApiClient.request_json",
            side_effect=AssertionError("network must not run"),
        ):
            plan = build_collection_plan(COLLECTION_CONFIG, PROTOCOL_CONFIG)
        self.assertEqual(plan["status"], "PLANNED_NO_NETWORK_NO_WRITE")
        self.assertEqual(plan["universe"]["stock_count"], 50)
        self.assertEqual(plan["universe"]["stocks_by_market"], {"KOSPI": 45, "KOSDAQ": 5})
        self.assertEqual(plan["date_range"]["weekday_candidate_dates"], 4302)
        self.assertEqual(plan["request_plan"]["total_request_upper_bound"], 12908)
        self.assertEqual(plan["fx_plan"]["api_request_count"], "UNRESOLVED_03_PAGINATION_AND_AVAILABILITY")
        self.assertEqual(plan["row_plan"]["ecos_four_series_weekday_row_upper_bound"], 17208)
        self.assertEqual(plan["storage_estimate_scope"], "KRX_ONLY_EXCLUDES_ECOS_UNTIL_UNRESOLVED_03")
        self.assertEqual(plan["io"], {"network_requests_performed": 0, "files_written": 0})
        self.assertEqual(raw_root.exists(), before)

    def test_dry_run_makes_no_network_request_or_raw_directory(self) -> None:
        raw_root = ROOT / "data" / "raw" / "v2_1"
        before = raw_root.exists()
        with patch(
            "fx_research.v2_1_feasibility.SafeApiClient.request_json",
            side_effect=AssertionError("network must not run"),
        ):
            result = run_dry_run(COLLECTION_CONFIG, PROTOCOL_CONFIG)
        self.assertEqual(result["status"], "VALIDATED_NO_NETWORK_NO_WRITE")
        self.assertEqual(result["io"]["network_requests_performed"], 0)
        self.assertEqual(raw_root.exists(), before)

    def test_u0_mapping_rejects_changed_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, mapping_path = CollectionFixture.copy(directory)
            with mapping_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["legacy_ticker_name"] = "U1임의종목"
            with mapping_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(CollectionError, "U0_MAPPING_MEMBERSHIP_OR_ORDER_CHANGED"):
                load_u0_mapping(mapping_path)

    def test_u0_mapping_rejects_duplicate_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, mapping_path = CollectionFixture.copy(directory)
            with mapping_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[1]["ticker_code"] = rows[0]["ticker_code"]
            with mapping_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(CollectionError, "U0_TICKER_CODE_DUPLICATE"):
                load_u0_mapping(mapping_path)


class GateTests(unittest.TestCase):
    def test_schema_sample_is_ready_but_not_executed_without_flag(self) -> None:
        with patch(
            "fx_research.v2_1_collection.run_schema_sample",
            side_effect=AssertionError("schema network run must be explicit"),
        ):
            result = run_schema_sample_mode(COLLECTION_CONFIG, PROTOCOL_CONFIG, execute=False)
        self.assertEqual(result["status"], "READY_NOT_EXECUTED")
        self.assertEqual(result["io"], {"network_requests_performed": 0, "files_written": 0})

    def test_schema_sample_scope_cannot_expand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, config_path, protocol_path, _ = CollectionFixture.copy(directory)
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload["schema_sample"]["date_start"] = "2026-03-01"
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(CollectionError, "SCHEMA_SAMPLE_START_CHANGED"):
                run_schema_sample_mode(config_path, protocol_path, execute=False)

    def test_collect_is_blocked_while_protocol_is_draft(self) -> None:
        with patch(
            "fx_research.v2_1_feasibility.SafeApiClient.request_json",
            side_effect=AssertionError("collect must not use network"),
        ):
            result = run_collect(COLLECTION_CONFIG, PROTOCOL_CONFIG)
        self.assertEqual(result["status"], "BLOCKED_PROTOCOL_NOT_FROZEN")
        self.assertEqual(result["io"], {"network_requests_performed": 0, "files_written": 0})

    def test_results_v2_1_directory_blocks_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, config_path, protocol_path, _ = CollectionFixture.copy(directory)
            (root / "results" / "v2_1").mkdir(parents=True)
            with self.assertRaisesRegex(CollectionError, "RESULTS_V2_1_MUST_BE_ABSENT"):
                run_dry_run(config_path, protocol_path)

    def test_research_guard_cannot_enable_returns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, config_path, protocol_path, _ = CollectionFixture.copy(directory)
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload["research_guards"]["calculate_returns"] = True
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(CollectionError, "RESEARCH_GUARD_MUST_REMAIN_FALSE"):
                build_collection_plan(config_path, protocol_path)

    def test_frozen_protocol_still_requires_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, config_path, protocol_path, _ = CollectionFixture.copy(directory)
            protocol_text = protocol_path.read_text(encoding="utf-8").replace(
                'status: "DRAFT_NOT_FROZEN"', 'status: "FROZEN"'
            )
            protocol_path.write_text(protocol_text, encoding="utf-8")
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["collection"]["full_collect_enabled"] = True
            config_path.write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            result = run_collect(config_path, protocol_path)
            self.assertEqual(result["status"], "BLOCKED_FROZEN_MANIFEST_MISSING")

    def test_valid_frozen_manifest_still_cannot_execute_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, config_path, protocol_path, mapping_path = CollectionFixture.copy(directory)
            protocol_path.write_text(
                protocol_path.read_text(encoding="utf-8").replace(
                    'status: "DRAFT_NOT_FROZEN"', 'status: "FROZEN"'
                ),
                encoding="utf-8",
            )
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["collection"]["full_collect_enabled"] = True
            config_path.write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            manifest_path = root / "data" / "metadata" / "v2_1_frozen_manifest.yaml"
            manifest = {
                "status": "FROZEN",
                "protocol_sha256": sha256_file(protocol_path),
                "collection_config_sha256": sha256_file(config_path),
                "ticker_mapping_sha256": sha256_file(mapping_path),
            }
            manifest_path.write_text(
                yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
            )
            result = run_collect(config_path, protocol_path)
            self.assertEqual(result["status"], "BLOCKED_EXECUTION_NOT_AUTHORIZED_IN_SCAFFOLD")
            self.assertEqual(result["io"], {"network_requests_performed": 0, "files_written": 0})


class StorageControlTests(unittest.TestCase):
    def test_retry_policy_is_fixed(self) -> None:
        self.assertEqual([retry_backoff_seconds(i) for i in (1, 2, 3)], [1, 2, 4])
        self.assertTrue(should_retry_http(429, [408, 429, 500, 502, 503, 504]))
        self.assertFalse(should_retry_http(400, [408, 429, 500, 502, 503, 504]))
        self.assertFalse(should_retry_result_code("UNKNOWN", []))
        with self.assertRaisesRegex(CollectionError, "RETRY_ATTEMPT_OUT_OF_RANGE"):
            retry_backoff_seconds(4)

    def test_atomic_write_replaces_payload_without_tmp_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "sample.json.gz"
            atomic_write_bytes(path, b"first")
            atomic_write_bytes(path, b"second")
            self.assertEqual(path.read_bytes(), b"second")
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_checkpoint_is_idempotent_and_has_no_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            store = CheckpointStore(path)
            payload = b"local raw bytes"
            key = request_id("stk_bydd_trd", "20260401", "KOSPI")
            record = {
                "request_id": key,
                "endpoint_id": "stk_bydd_trd",
                "bas_dd": "20260401",
                "market": "KOSPI",
                "status": "COMPLETED",
                "sha256": sha256_bytes(payload),
                "schema_hash": "0" * 64,
                "row_count": 1,
                "retry_count": 0,
            }
            self.assertTrue(store.record_completed(record))
            self.assertFalse(store.record_completed(record))
            self.assertTrue(store.is_complete(key))
            self.assertFalse(store.should_fetch(key))
            self.assertTrue(store.should_fetch(key, force=True))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("local raw bytes", text)

    def test_checkpoint_rejects_credential_or_extra_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(Path(directory) / "checkpoint.json")
            record = {
                "request_id": "0" * 64,
                "sha256": "1" * 64,
                "AUTH_KEY": "must-not-be-stored",
            }
            with self.assertRaisesRegex(CollectionError, "CHECKPOINT_FIELD_NOT_ALLOWED"):
                store.record_completed(record)

    def test_checkpoint_conflict_is_not_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(Path(directory) / "checkpoint.json")
            base = {"request_id": "0" * 64, "sha256": "1" * 64}
            store.record_completed(base)
            with self.assertRaisesRegex(CollectionError, "CHECKPOINT_CONFLICT"):
                store.record_completed({"request_id": "0" * 64, "sha256": "2" * 64})


if __name__ == "__main__":
    unittest.main()
