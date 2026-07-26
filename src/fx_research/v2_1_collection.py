"""V2.1 U0 collection scaffold with hard preregistration guards.

The module can plan and validate collection, but full collection is disabled
while the protocol remains a draft.  It deliberately has no target, return,
model, prediction, evaluation, or backtest imports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .constants import SECTOR_STOCKS
from .v2_1_feasibility import FIXED_SAMPLE, run_schema_sample


class CollectionError(RuntimeError):
    """A collection control failure whose message never contains a secret."""


@dataclass(frozen=True)
class EndpointSchema:
    endpoint_id: str
    category: str
    ticker_code_field: str | None
    ticker_code_meaning: str | None
    isin_field: str | None
    primary_key: tuple[str, ...]


ENDPOINT_SCHEMAS = {
    "kospi_stock_basic": EndpointSchema(
        endpoint_id="stk_isu_base_info",
        category="stock_basic",
        ticker_code_field="ISU_SRT_CD",
        ticker_code_meaning="6_digit_short_code",
        isin_field="ISU_CD",
        primary_key=("ISU_SRT_CD", "ISU_CD"),
    ),
    "kosdaq_stock_basic": EndpointSchema(
        endpoint_id="ksq_isu_base_info",
        category="stock_basic",
        ticker_code_field="ISU_SRT_CD",
        ticker_code_meaning="6_digit_short_code",
        isin_field="ISU_CD",
        primary_key=("ISU_SRT_CD", "ISU_CD"),
    ),
    "kospi_stock_daily": EndpointSchema(
        endpoint_id="stk_bydd_trd",
        category="stock_daily",
        ticker_code_field="ISU_CD",
        ticker_code_meaning="6_digit_short_code",
        isin_field=None,
        primary_key=("BAS_DD", "ISU_CD"),
    ),
    "kosdaq_stock_daily": EndpointSchema(
        endpoint_id="ksq_bydd_trd",
        category="stock_daily",
        ticker_code_field="ISU_CD",
        ticker_code_meaning="6_digit_short_code",
        isin_field=None,
        primary_key=("BAS_DD", "ISU_CD"),
    ),
    "kospi_index_daily": EndpointSchema(
        endpoint_id="kospi_dd_trd",
        category="index_daily",
        ticker_code_field=None,
        ticker_code_meaning=None,
        isin_field=None,
        primary_key=("BAS_DD", "IDX_CLSS", "IDX_NM"),
    ),
}

CHECKPOINT_ALLOWED_FIELDS = {
    "request_id",
    "endpoint_id",
    "bas_dd",
    "market",
    "status",
    "sha256",
    "schema_hash",
    "row_count",
    "retry_count",
    "completed_at_utc",
}

FIXED_REQUEST_POLICY = {
    "timeout_seconds": 30,
    "maximum_retries": 3,
    "backoff_initial_seconds": 1,
    "backoff_multiplier": 2,
    "backoff_maximum_seconds": 8,
    "maximum_parallel_connections": 4,
    "krx_daily_hard_limit": 10000,
    "configured_daily_request_budget": 9000,
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CollectionError("CONFIG_NOT_FOUND")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise CollectionError("CONFIG_YAML_INVALID") from None
    if not isinstance(loaded, dict):
        raise CollectionError("CONFIG_ROOT_MUST_BE_MAPPING")
    return loaded


def _project_root(config_path: Path) -> Path:
    resolved = config_path.resolve()
    if resolved.parent.name != "configs":
        raise CollectionError("COLLECTION_CONFIG_MUST_BE_IN_CONFIGS_DIRECTORY")
    return resolved.parent.parent


def _resolve_from_root(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CollectionError("CONFIG_PATH_VALUE_INVALID")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise CollectionError("CONFIG_PATH_OUTSIDE_PROJECT") from None
    return candidate


def _legacy_order() -> list[tuple[str, str]]:
    return [
        (sector, ticker)
        for sector, tickers in SECTOR_STOCKS.items()
        for ticker in tickers
    ]


def load_u0_mapping(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 50:
        raise CollectionError("U0_MAPPING_MUST_HAVE_50_ROWS")
    actual = [(row.get("legacy_sector", ""), row.get("legacy_ticker_name", "")) for row in rows]
    if actual != _legacy_order():
        raise CollectionError("U0_MAPPING_MEMBERSHIP_OR_ORDER_CHANGED")
    codes = [row.get("ticker_code", "").strip() for row in rows]
    if any(not re.fullmatch(r"\d{6}", code) for code in codes):
        raise CollectionError("U0_TICKER_CODE_INVALID")
    if len(codes) != len(set(codes)):
        raise CollectionError("U0_TICKER_CODE_DUPLICATE")
    if any(row.get("market") not in {"KOSPI", "KOSDAQ"} for row in rows):
        raise CollectionError("U0_MARKET_INVALID")
    if any(not row.get("mapping_status", "").startswith("MAPPED_OFFICIAL") for row in rows):
        raise CollectionError("U0_MAPPING_NOT_OFFICIALLY_VERIFIED")
    return rows


def filter_u0_daily_rows(
    rows: Iterable[Mapping[str, Any]],
    mapping: Iterable[Mapping[str, str]],
) -> list[dict[str, Any]]:
    allowed = {row["ticker_code"] for row in mapping}
    selected: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("ISU_CD", "")).strip()
        if re.fullmatch(r"\d{6}", code) and code in allowed:
            selected.append(dict(row))
    return selected


def _weekday_dates(start: date, end: date) -> list[date]:
    if start > end:
        raise CollectionError("COLLECTION_DATE_RANGE_INVALID")
    output: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            output.append(current)
        current += timedelta(days=1)
    return output


def _as_date(value: object, error_code: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise CollectionError(error_code) from None


def _required_mapping_fields(rows: Iterable[Mapping[str, str]]) -> None:
    for row in rows:
        if not row.get("listing_date") or not re.fullmatch(r"\d{8}", row["listing_date"]):
            raise CollectionError("U0_LISTING_DATE_INVALID")
        if row.get("delisting_date") and not re.fullmatch(r"\d{8}", row["delisting_date"]):
            raise CollectionError("U0_DELISTING_DATE_INVALID")


def _validate_request_policy(policy: Mapping[str, Any]) -> None:
    for key, expected in FIXED_REQUEST_POLICY.items():
        if policy.get(key) != expected:
            raise CollectionError(f"REQUEST_POLICY_CHANGED:{key}")
    if policy.get("retryable_http_statuses") != [408, 429, 500, 502, 503, 504]:
        raise CollectionError("RETRYABLE_HTTP_STATUSES_CHANGED")
    if policy.get("retryable_institution_result_codes") != []:
        raise CollectionError("INSTITUTION_RETRY_CODES_REQUIRE_SEPARATE_REGISTRATION")
    if policy.get("force_default") is not False:
        raise CollectionError("FORCE_DEFAULT_MUST_BE_FALSE")


def _estimate_storage_bytes(
    weekdays: int,
    requests: int,
    assumptions: Mapping[str, Any],
    u0_rows: int,
) -> dict[str, int]:
    response_rows = assumptions["estimated_rows_per_response"]
    bytes_per_row = assumptions["estimated_uncompressed_bytes_per_row"]
    gzip_ratio = float(assumptions["estimated_gzip_ratio"])
    uncompressed = (
        weekdays * int(response_rows["kospi_stock_daily"]) * int(bytes_per_row["stock_daily"])
        + weekdays * int(response_rows["kosdaq_stock_daily"]) * int(bytes_per_row["stock_daily"])
        + weekdays * int(response_rows["kospi_index_daily"]) * int(bytes_per_row["index_daily"])
        + int(response_rows["kospi_stock_basic"]) * int(bytes_per_row["stock_basic"])
        + int(response_rows["kosdaq_stock_basic"]) * int(bytes_per_row["stock_basic"])
    )
    manifests = requests * int(assumptions["estimated_manifest_bytes_per_request"])
    filtered = u0_rows * int(assumptions["estimated_filtered_u0_bytes_per_row"])
    return {
        "raw_uncompressed_upper_bound_bytes": uncompressed,
        "raw_gzip_estimate_bytes": math.ceil(uncompressed * gzip_ratio),
        "request_manifest_estimate_bytes": manifests,
        "filtered_u0_normalized_estimate_bytes": filtered,
        "combined_local_estimate_bytes": math.ceil(uncompressed * gzip_ratio) + manifests + filtered,
    }


def build_collection_plan(
    config_path: Path,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_results_absent(root)
    config = _load_yaml(config_path)
    collection = config.get("collection")
    request_policy = config.get("request_policy")
    assumptions = config.get("planning_assumptions")
    guards = config.get("research_guards")
    if not all(isinstance(value, dict) for value in (collection, request_policy, assumptions, guards)):
        raise CollectionError("COLLECTION_CONFIG_SECTION_MISSING")
    _validate_request_policy(request_policy)
    if collection["universe_label"] != "U0_LEGACY_50" or guards["u1_collection_allowed"] is not False:
        raise CollectionError("ONLY_U0_COLLECTION_IS_ALLOWED")
    forbidden_guard_keys = (
        "calculate_returns",
        "generate_targets",
        "train_models",
        "generate_predictions",
        "calculate_performance",
        "create_results_v2_1",
        "sect_tp_nm_industry_use_allowed",
    )
    if any(guards.get(key) is not False for key in forbidden_guard_keys):
        raise CollectionError("RESEARCH_GUARD_MUST_REMAIN_FALSE")
    if guards.get("fluc_rt_research_return_status") != "UNRESOLVED_01":
        raise CollectionError("FLUC_RT_MUST_REMAIN_UNRESOLVED_01")
    protocol_path = protocol_path or _resolve_from_root(root, collection["protocol_path"])
    protocol = _load_yaml(protocol_path)
    mapping = load_u0_mapping(_resolve_from_root(root, collection["ticker_mapping_path"]))
    _required_mapping_fields(mapping)

    start = _as_date(collection["collection_start"], "COLLECTION_START_INVALID")
    end = _as_date(collection["collection_end"], "COLLECTION_END_INVALID")
    protocol_data = protocol.get("data", {})
    if str(protocol_data.get("collection_start")) != start.isoformat():
        raise CollectionError("COLLECTION_START_PROTOCOL_MISMATCH")
    if str(protocol_data.get("collection_end")) != end.isoformat():
        raise CollectionError("COLLECTION_END_PROTOCOL_MISMATCH")

    weekdays = _weekday_dates(start, end)
    weekday_count = len(weekdays)
    endpoint_calls = {
        "kospi_stock_basic": 1,
        "kosdaq_stock_basic": 1,
        "kospi_stock_daily": weekday_count,
        "kosdaq_stock_daily": weekday_count,
        "kospi_index_daily": weekday_count,
    }
    endpoint_plan = [
        {
            "endpoint": "kospi_stock_basic",
            "api_id": ENDPOINT_SCHEMAS["kospi_stock_basic"].endpoint_id,
            "market": "KOSPI",
            "date_start": end.isoformat(),
            "date_end": end.isoformat(),
            "calls": 1,
            "ticker_code_field": "ISU_SRT_CD",
            "isin_field": "ISU_CD",
        },
        {
            "endpoint": "kosdaq_stock_basic",
            "api_id": ENDPOINT_SCHEMAS["kosdaq_stock_basic"].endpoint_id,
            "market": "KOSDAQ",
            "date_start": end.isoformat(),
            "date_end": end.isoformat(),
            "calls": 1,
            "ticker_code_field": "ISU_SRT_CD",
            "isin_field": "ISU_CD",
        },
        {
            "endpoint": "kospi_stock_daily",
            "api_id": ENDPOINT_SCHEMAS["kospi_stock_daily"].endpoint_id,
            "market": "KOSPI",
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "calls": weekday_count,
            "ticker_code_field": "ISU_CD",
            "isin_field": None,
        },
        {
            "endpoint": "kosdaq_stock_daily",
            "api_id": ENDPOINT_SCHEMAS["kosdaq_stock_daily"].endpoint_id,
            "market": "KOSDAQ",
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "calls": weekday_count,
            "ticker_code_field": "ISU_CD",
            "isin_field": None,
        },
        {
            "endpoint": "kospi_index_daily",
            "api_id": ENDPOINT_SCHEMAS["kospi_index_daily"].endpoint_id,
            "market": "KOSPI_INDEX",
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "calls": weekday_count,
            "ticker_code_field": None,
            "isin_field": None,
        },
    ]
    total_requests = sum(endpoint_calls.values())
    fx_config = protocol.get("fx", {})
    fx_item_codes = fx_config.get("official_item_codes", {})
    if set(fx_item_codes) != {"USD_KRW", "EUR_KRW", "JPY_KRW", "CNY_KRW"}:
        raise CollectionError("FX_ITEM_CODE_SET_CHANGED")
    market_counts = {
        market: sum(row["market"] == market for row in mapping)
        for market in ("KOSPI", "KOSDAQ")
    }
    u0_row_upper_bound = 0
    ticker_plan: list[dict[str, Any]] = []
    for row in mapping:
        listed = date(
            int(row["listing_date"][:4]),
            int(row["listing_date"][4:6]),
            int(row["listing_date"][6:8]),
        )
        first = max(start, listed)
        delisting = row.get("delisting_date", "")
        last = end
        if delisting:
            parsed_delisting = date(
                int(delisting[:4]), int(delisting[4:6]), int(delisting[6:8])
            )
            last = min(last, parsed_delisting)
        rows_max = len(_weekday_dates(first, last)) if first <= last else 0
        u0_row_upper_bound += rows_max
        ticker_plan.append(
            {
                "legacy_ticker_name": row["legacy_ticker_name"],
                "market": row["market"],
                "ticker_code": row["ticker_code"],
                "first_possible_date": first.isoformat(),
                "last_possible_date": last.isoformat(),
                "weekday_row_upper_bound": rows_max,
            }
        )

    hard_limit = int(request_policy["krx_daily_hard_limit"])
    budget = int(request_policy["configured_daily_request_budget"])
    if not 1 <= budget < hard_limit:
        raise CollectionError("DAILY_REQUEST_BUDGET_MUST_BE_BELOW_HARD_LIMIT")
    estimated_execution_days = math.ceil(total_requests / budget)
    storage = _estimate_storage_bytes(
        weekday_count,
        total_requests,
        assumptions,
        u0_row_upper_bound,
    )
    return {
        "mode": "plan",
        "status": "PLANNED_NO_NETWORK_NO_WRITE",
        "protocol_status": protocol.get("protocol", {}).get("status"),
        "universe": {
            "label": "U0_LEGACY_50",
            "stock_count": len(mapping),
            "stocks_by_market": market_counts,
            "ticker_plan": ticker_plan,
        },
        "date_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "weekday_candidate_dates": weekday_count,
            "rule": assumptions["date_count_rule"],
        },
        "request_plan": {
            "endpoints": endpoint_plan,
            "endpoint_calls": endpoint_calls,
            "total_request_upper_bound": total_requests,
            "market_date_level_requests": True,
            "daily_hard_limit": hard_limit,
            "configured_daily_budget": budget,
            "maximum_daily_limit_usage_percent": round(budget / hard_limit * 100, 2),
            "minimum_execution_days_at_budget": estimated_execution_days,
            "batch_order": "basDd_ascending_then_endpoint_id",
            "resume_key": "sha256(endpoint_id|basDd|market)",
        },
        "row_plan": {
            "u0_filtered_stock_weekday_upper_bound": u0_row_upper_bound,
            "kospi_primary_index_weekday_upper_bound": weekday_count,
            "ecos_four_series_weekday_row_upper_bound": weekday_count * len(fx_item_codes),
            "not_a_trading_day_or_data_availability_forecast": True,
        },
        "storage_plan": storage,
        "storage_estimate_scope": "KRX_ONLY_EXCLUDES_ECOS_UNTIL_UNRESOLVED_03",
        "fx_plan": {
            "source": "BOK_ECOS_OPEN_API",
            "table_code": fx_config.get("official_series_code"),
            "item_codes": dict(fx_item_codes),
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "weekday_row_upper_bound_all_four": weekday_count * len(fx_item_codes),
            "api_request_count": "UNRESOLVED_03_PAGINATION_AND_AVAILABILITY",
            "raw_storage_estimate": "UNRESOLVED_03",
            "included_in_primary": ["USD_KRW"],
            "sensitivity_only": ["EUR_KRW", "JPY_KRW", "CNY_KRW"],
        },
        "storage_paths": dict(config.get("storage", {})),
        "io": {"network_requests_performed": 0, "files_written": 0},
        "forbidden_outputs": {
            "returns": False,
            "targets": False,
            "models": False,
            "predictions": False,
            "performance": False,
            "results_v2_1": False,
        },
    }


def _guard_results_absent(root: Path) -> None:
    if (root / "results" / "v2_1").exists():
        raise CollectionError("RESULTS_V2_1_MUST_BE_ABSENT")


def _validate_schema_sample_scope(config: Mapping[str, Any], protocol: Mapping[str, Any]) -> None:
    sample = config.get("schema_sample", {})
    feasibility = protocol.get("data_feasibility", {}).get("krx_schema_sample", {})
    if sample.get("date_start") != feasibility.get("date_start"):
        raise CollectionError("SCHEMA_SAMPLE_START_CHANGED")
    if sample.get("date_end") != feasibility.get("date_end"):
        raise CollectionError("SCHEMA_SAMPLE_END_CHANGED")
    if set(sample.get("fixed_ticker_names", [])) != FIXED_SAMPLE:
        raise CollectionError("SCHEMA_SAMPLE_TICKERS_CHANGED")
    if int(sample.get("maximum_calendar_months", 0)) != 3:
        raise CollectionError("SCHEMA_SAMPLE_MAXIMUM_MONTHS_CHANGED")


def run_dry_run(config_path: Path, protocol_path: Path | None = None) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_results_absent(root)
    plan = build_collection_plan(config_path, protocol_path)
    return {
        "mode": "dry-run",
        "status": "VALIDATED_NO_NETWORK_NO_WRITE",
        "plan_summary": {
            "stock_count": plan["universe"]["stock_count"],
            "request_upper_bound": plan["request_plan"]["total_request_upper_bound"],
            "weekday_candidate_dates": plan["date_range"]["weekday_candidate_dates"],
        },
        "io": {"network_requests_performed": 0, "files_written": 0},
    }


def run_schema_sample_mode(
    config_path: Path,
    protocol_path: Path | None = None,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_results_absent(root)
    config = _load_yaml(config_path)
    collection = config["collection"]
    protocol_path = protocol_path or _resolve_from_root(root, collection["protocol_path"])
    protocol = _load_yaml(protocol_path)
    _validate_schema_sample_scope(config, protocol)
    load_u0_mapping(_resolve_from_root(root, collection["ticker_mapping_path"]))
    if not execute:
        return {
            "mode": "schema-sample",
            "status": "READY_NOT_EXECUTED",
            "reason": "EXPLICIT_EXECUTE_SCHEMA_SAMPLE_FLAG_REQUIRED",
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    result = run_schema_sample(protocol_path)
    return {"mode": "schema-sample", "delegated_feasibility_result": result, "status": result["status"]}


def run_collect(
    config_path: Path,
    protocol_path: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_results_absent(root)
    config = _load_yaml(config_path)
    collection = config["collection"]
    protocol_path = protocol_path or _resolve_from_root(root, collection["protocol_path"])
    protocol = _load_yaml(protocol_path)
    plan = build_collection_plan(config_path, protocol_path)
    if protocol.get("protocol", {}).get("status") != "FROZEN":
        return {
            "mode": "collect",
            "status": "BLOCKED_PROTOCOL_NOT_FROZEN",
            "planned_requests": plan["request_plan"]["total_request_upper_bound"],
            "force_requested": force,
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    if collection.get("full_collect_enabled") is not True:
        return {
            "mode": "collect",
            "status": "BLOCKED_FULL_COLLECT_DISABLED",
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    manifest = _resolve_from_root(root, collection["frozen_manifest_path"])
    if not manifest.is_file():
        return {
            "mode": "collect",
            "status": "BLOCKED_FROZEN_MANIFEST_MISSING",
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    manifest_payload = _load_yaml(manifest)
    expected_hashes = {
        "protocol_sha256": sha256_file(protocol_path),
        "collection_config_sha256": sha256_file(config_path),
        "ticker_mapping_sha256": sha256_file(
            _resolve_from_root(root, collection["ticker_mapping_path"])
        ),
    }
    if manifest_payload.get("status") != "FROZEN" or any(
        manifest_payload.get(key) != value for key, value in expected_hashes.items()
    ):
        return {
            "mode": "collect",
            "status": "BLOCKED_FROZEN_MANIFEST_HASH_MISMATCH",
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    return {
        "mode": "collect",
        "status": "BLOCKED_EXECUTION_NOT_AUTHORIZED_IN_SCAFFOLD",
        "io": {"network_requests_performed": 0, "files_written": 0},
    }


def request_id(endpoint_id: str, bas_dd: str, market: str) -> str:
    canonical = f"{endpoint_id}|{bas_dd}|{market}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class CheckpointStore:
    """Sanitized idempotency records; raw API values and credentials are forbidden."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise CollectionError("CHECKPOINT_INVALID_JSON") from None
        if not isinstance(payload, dict):
            raise CollectionError("CHECKPOINT_ROOT_INVALID")
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def is_complete(self, request_key: str) -> bool:
        return self._read().get(request_key, {}).get("status") == "COMPLETED"

    def should_fetch(self, request_key: str, *, force: bool = False) -> bool:
        return force or not self.is_complete(request_key)

    def record_completed(self, record: Mapping[str, Any]) -> bool:
        extra = set(record) - CHECKPOINT_ALLOWED_FIELDS
        if extra:
            raise CollectionError("CHECKPOINT_FIELD_NOT_ALLOWED")
        request_key = str(record.get("request_id", ""))
        sha256 = str(record.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", request_key):
            raise CollectionError("CHECKPOINT_REQUEST_ID_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise CollectionError("CHECKPOINT_SHA256_INVALID")
        existing = self._read()
        if request_key in existing:
            if existing[request_key].get("sha256") == sha256:
                return False
            raise CollectionError("CHECKPOINT_CONFLICT")
        sanitized = dict(record)
        sanitized["status"] = "COMPLETED"
        sanitized.setdefault("completed_at_utc", datetime.now(timezone.utc).isoformat())
        existing[request_key] = sanitized
        atomic_write_bytes(
            self.path,
            (json.dumps(existing, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        )
        return True


def should_retry_http(status: int, configured: Iterable[int]) -> bool:
    return status in {int(value) for value in configured}


def should_retry_result_code(code: str, configured: Iterable[str]) -> bool:
    return code in {str(value) for value in configured}


def retry_backoff_seconds(attempt: int) -> int:
    if attempt < 1 or attempt > FIXED_REQUEST_POLICY["maximum_retries"]:
        raise CollectionError("RETRY_ATTEMPT_OUT_OF_RANGE")
    value = FIXED_REQUEST_POLICY["backoff_initial_seconds"] * (
        FIXED_REQUEST_POLICY["backoff_multiplier"] ** (attempt - 1)
    )
    return min(value, FIXED_REQUEST_POLICY["backoff_maximum_seconds"])


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Plan or validate V2.1 U0 collection only.")
    parser.add_argument("--config", default=root / "configs" / "v2_1_collection.yaml")
    parser.add_argument("--protocol", default=None)
    parser.add_argument("--mode", required=True, choices=("plan", "dry-run", "schema-sample", "collect"))
    parser.add_argument("--execute-schema-sample", action="store_true")
    parser.add_argument("--force", action="store_true", help="Future collect override; no effect while blocked")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path = Path(args.config).resolve()
    protocol_path = Path(args.protocol).resolve() if args.protocol else None
    try:
        if args.mode == "plan":
            _guard_results_absent(_project_root(config_path))
            result = build_collection_plan(config_path, protocol_path)
        elif args.mode == "dry-run":
            result = run_dry_run(config_path, protocol_path)
        elif args.mode == "schema-sample":
            result = run_schema_sample_mode(
                config_path,
                protocol_path,
                execute=args.execute_schema_sample,
            )
        else:
            result = run_collect(config_path, protocol_path, force=args.force)
    except CollectionError as exc:
        result = {"mode": args.mode, "status": "ERROR", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] == "ERROR":
        raise SystemExit(1)
    if result["status"].startswith("BLOCKED"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
