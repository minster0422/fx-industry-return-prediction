from __future__ import annotations

import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from fx_research.v2_1_archive import (
    ARCHIVE_PURPOSE,
    ArchiveError,
    ArchiveQuotaExhausted,
    ArchiveRunLock,
    ArchiveState,
    build_archive_requests,
    fetch_archive_request,
    make_archive_request,
    run_archive_collect,
    run_archive_probe,
    write_public_archive_summary,
)


ROOT = Path(__file__).resolve().parents[1]
COLLECTION_CONFIG = ROOT / "configs" / "v2_1_collection.yaml"
PROTOCOL_CONFIG = ROOT / "configs" / "v2_1_protocol.yaml"
MAPPING = ROOT / "data" / "metadata" / "v2_1_ticker_mapping.csv"


class ArchiveFixture:
    @staticmethod
    def copy(directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        (root / "configs").mkdir(parents=True)
        (root / "data" / "metadata").mkdir(parents=True)
        config_path = root / "configs" / "v2_1_collection.yaml"
        protocol_path = root / "configs" / "v2_1_protocol.yaml"
        mapping_path = root / "data" / "metadata" / "v2_1_ticker_mapping.csv"
        shutil.copy2(COLLECTION_CONFIG, config_path)
        shutil.copy2(PROTOCOL_CONFIG, protocol_path)
        shutil.copy2(MAPPING, mapping_path)
        return root, config_path, protocol_path


class ArchivePlanTests(unittest.TestCase):
    def test_archive_request_plan_matches_frozen_upper_bound(self) -> None:
        requests = build_archive_requests(COLLECTION_CONFIG, PROTOCOL_CONFIG)
        self.assertEqual(len(requests), 12908)
        self.assertEqual(len({item.request_id for item in requests}), 12908)
        self.assertEqual(requests[0].bas_dd, "20100104")
        self.assertEqual(requests[-1].bas_dd, "20260630")
        self.assertEqual(
            {item.endpoint_name for item in requests},
            {
                "kospi_stock_basic",
                "kosdaq_stock_basic",
                "kospi_stock_daily",
                "kosdaq_stock_daily",
                "kospi_index_daily",
            },
        )

    def test_archive_endpoint_allowlist_is_not_expandable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, config_path, protocol_path = ArchiveFixture.copy(directory)
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload["archive_only"]["allowed_endpoints"].append("krx_index_daily")
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchiveError, "ARCHIVE_ENDPOINT_ALLOWLIST_CHANGED"):
                build_archive_requests(config_path, protocol_path)

    def test_research_derivation_guard_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, config_path, protocol_path = ArchiveFixture.copy(directory)
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload["archive_only"]["calculate_returns"] = True
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ArchiveError, "ARCHIVE_RESEARCH_DERIVATION_GUARD_CHANGED"
            ):
                build_archive_requests(config_path, protocol_path)


class ArchiveExecutionGateTests(unittest.TestCase):
    def test_probe_needs_explicit_execute_flag(self) -> None:
        with patch(
            "fx_research.v2_1_archive._request_raw",
            side_effect=AssertionError("probe must not call network"),
        ):
            result = run_archive_probe(
                COLLECTION_CONFIG,
                PROTOCOL_CONFIG,
                execute=False,
            )
        self.assertEqual(result["status"], "READY_NOT_EXECUTED")
        self.assertEqual(result["planned_requests"], 15)
        self.assertEqual(result["io"]["network_requests_performed"], 0)

    def test_collect_needs_explicit_execute_flag(self) -> None:
        with patch(
            "fx_research.v2_1_archive._request_raw",
            side_effect=AssertionError("archive must not call network"),
        ):
            result = run_archive_collect(
                COLLECTION_CONFIG,
                PROTOCOL_CONFIG,
                execute=False,
            )
        self.assertEqual(result["status"], "READY_NOT_EXECUTED")
        self.assertEqual(result["io"]["network_requests_performed"], 0)

    def test_public_summary_rejects_partial_archive(self) -> None:
        with patch(
            "fx_research.v2_1_archive.build_archive_status",
            return_value={"status": "PARTIAL"},
        ):
            with self.assertRaisesRegex(
                ArchiveError, "ARCHIVE_PUBLIC_SUMMARY_REQUIRES_COMPLETE_ARCHIVE"
            ):
                write_public_archive_summary(COLLECTION_CONFIG, PROTOCOL_CONFIG)


class ArchiveStateTests(unittest.TestCase):
    def test_archive_run_lock_rejects_concurrent_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive_run.lock"
            with ArchiveRunLock(path):
                with self.assertRaisesRegex(ArchiveError, "ARCHIVE_RUN_ALREADY_ACTIVE"):
                    with ArchiveRunLock(path):
                        self.fail("nested archive lock must not be acquired")
            self.assertFalse(path.exists())

    def test_daily_quota_reserves_untracked_margin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = ArchiveState(
                Path(directory) / "state.sqlite3",
                daily_budget=3,
                untracked_reserve=1,
            )
            item = make_archive_request("kospi_stock_daily", "20260630")
            try:
                first = state.reserve_attempt(item, 1)
                second = state.reserve_attempt(item, 2)
                state.finish_attempt(first, outcome="TEST", http_status=200)
                state.finish_attempt(second, outcome="TEST", http_status=200)
                self.assertEqual(state.remaining_attempt_budget(), 0)
                with self.assertRaisesRegex(
                    ArchiveQuotaExhausted, "ARCHIVE_DAILY_BUDGET_EXHAUSTED"
                ):
                    state.reserve_attempt(item, 3)
            finally:
                state.close()

    def test_raw_response_is_gzipped_and_resumable(self) -> None:
        payload = {
            "OutBlock_1": [
                {
                    "BAS_DD": "20260630",
                    "ISU_CD": "005930",
                    "TDD_CLSPRC": "60000",
                }
            ]
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = ArchiveState(
                root / "checkpoints" / "state.sqlite3",
                daily_budget=10,
                untracked_reserve=1,
            )
            item = make_archive_request("kospi_stock_daily", "20260630")
            try:
                with patch(
                    "fx_research.v2_1_archive._request_raw",
                    return_value=(raw, 200),
                ) as request_mock:
                    first = fetch_archive_request(
                        item,
                        auth_key="not-recorded",
                        raw_root=root,
                        state=state,
                        timeout_seconds=1,
                        maximum_retries=0,
                        retryable_http_statuses=[],
                    )
                    second = fetch_archive_request(
                        item,
                        auth_key="not-recorded",
                        raw_root=root,
                        state=state,
                        timeout_seconds=1,
                        maximum_retries=0,
                        retryable_http_statuses=[],
                    )
                self.assertEqual(request_mock.call_count, 1)
                self.assertEqual(first.sha256, second.sha256)
                saved = root / item.relative_path
                self.assertEqual(gzip.decompress(saved.read_bytes()), raw)
                self.assertNotIn(
                    "not-recorded",
                    (root / "checkpoints" / "state.sqlite3").read_bytes().decode(
                        "latin-1", errors="ignore"
                    ),
                )
            finally:
                state.close()

    def test_invalid_json_is_retried_before_failure(self) -> None:
        valid = json.dumps({"OutBlock_1": []}).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = ArchiveState(
                root / "checkpoints" / "state.sqlite3",
                daily_budget=10,
                untracked_reserve=1,
            )
            item = make_archive_request("kospi_index_daily", "20260630")
            try:
                with patch(
                    "fx_research.v2_1_archive._request_raw",
                    side_effect=[(b"<html>temporary</html>", 200), (valid, 200)],
                ) as request_mock, patch(
                    "fx_research.v2_1_archive.time.sleep",
                    return_value=None,
                ):
                    result = fetch_archive_request(
                        item,
                        auth_key="not-recorded",
                        raw_root=root,
                        state=state,
                        timeout_seconds=1,
                        maximum_retries=1,
                        retryable_http_statuses=[],
                    )
                self.assertEqual(request_mock.call_count, 2)
                self.assertEqual(result.retry_count, 1)
                self.assertEqual(state.attempts_today(), 2)
            finally:
                state.close()

    def test_archive_purpose_constant_is_explicit(self) -> None:
        self.assertEqual(
            ARCHIVE_PURPOSE,
            "RAW_ARCHIVE_ONLY_NO_RESEARCH_DERIVATIONS",
        )


if __name__ == "__main__":
    unittest.main()
