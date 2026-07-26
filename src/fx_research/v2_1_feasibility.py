"""Credential-safe V2.1 data-feasibility checks.

This module deliberately cannot train a model, construct a V2.1 target, or
write under ``results/v2_1``.  It only inspects official source metadata,
small schema samples, and publication timestamps needed to freeze the
preregistered protocol.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .constants import SECTOR_STOCKS

KST = ZoneInfo("Asia/Seoul")
KRX_BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"
ECOS_BASE_URL = "https://ecos.bok.or.kr/api"

KRX_ENDPOINTS = {
    "kospi_stock_daily": ("sto", "stk_bydd_trd"),
    "kosdaq_stock_daily": ("sto", "ksq_bydd_trd"),
    "kospi_stock_basic": ("sto", "stk_isu_base_info"),
    "kosdaq_stock_basic": ("sto", "ksq_isu_base_info"),
    "kospi_index_daily": ("idx", "kospi_dd_trd"),
    "krx_index_daily": ("idx", "krx_dd_trd"),
}

FIXED_SAMPLE = {
    "현대건설",
    "KB금융",
    "CJ ENM",
    "셀트리온",
    "SK하이닉스",
}
ECOS_ITEMS = {
    "USD_KRW": "0000001",
    "EUR_KRW": "0000003",
    "JPY_KRW": "0000002",
    "CNY_KRW": "0000053",
}
ECOS_CHECK_DATES = (
    "20260701",
    "20260702",
    "20260703",
    "20260706",
    "20260707",
)

TICKER_COLUMNS = (
    "legacy_sector",
    "legacy_ticker_name",
    "ticker_code",
    "isin_code",
    "market",
    "listing_date",
    "delisting_date",
    "mapping_status",
    "official_source_id",
    "checked_at",
    "failure_reason",
    "fixed_sample_5",
)

IDENTITY_PROVENANCE_COLUMNS = (
    "legacy_ticker_name",
    "official_name_before",
    "official_name_after",
    "ticker_code",
    "isin_code",
    "market",
    "listing_date",
    "evidence_date_before",
    "evidence_date_after",
    "source_endpoint",
    "matching_rule",
    "status",
    "checked_at",
)

DAILY_TICKER_CODE_FIELD = "ISU_CD"
BASIC_TICKER_CODE_FIELD = "ISU_SRT_CD"
DAILY_NUMERIC_FIELDS = {
    "TDD_CLSPRC": "float",
    "FLUC_RT": "float",
    "ACC_TRDVOL": "integer",
    "ACC_TRDVAL": "integer",
    "MKTCAP": "integer",
}


class FeasibilityError(RuntimeError):
    """An error whose message is guaranteed not to include a credential."""


@dataclass(frozen=True)
class ApiResponse:
    payload: Any
    http_status: int
    headers: Mapping[str, str]
    requested_at_utc: datetime


def credential_status(name: str) -> str:
    """Return only SET/NOT_SET; never return the environment variable value."""

    return "SET" if os.environ.get(name, "").strip() else "NOT_SET"


def _legacy_rows() -> list[tuple[str, str]]:
    return [
        (sector, ticker)
        for sector, tickers in SECTOR_STOCKS.items()
        for ticker in tickers
    ]


def _normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def _read_identity_provenance(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    missing_columns = set(IDENTITY_PROVENANCE_COLUMNS) - set(rows[0])
    if missing_columns:
        raise FeasibilityError("IDENTITY_PROVENANCE_SCHEMA_MISMATCH")
    verified: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("status") != "VERIFIED_CODE_AND_ISIN":
            continue
        legacy_name = row.get("legacy_ticker_name", "").strip()
        ticker_code = row.get("ticker_code", "").strip()
        isin_code = row.get("isin_code", "").strip()
        if not legacy_name or not re.fullmatch(r"\d{6}", ticker_code) or not isin_code:
            raise FeasibilityError("IDENTITY_PROVENANCE_INVALID_VERIFIED_ROW")
        if legacy_name in verified:
            raise FeasibilityError("IDENTITY_PROVENANCE_DUPLICATE_LEGACY_NAME")
        verified[legacy_name] = dict(row)
    return verified


def _fixed_daily_rows(
    rows: Iterable[Mapping[str, Any]],
    fixed_codes: Mapping[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for source_row in rows:
        code = str(source_row.get(DAILY_TICKER_CODE_FIELD, "")).strip()
        if re.fullmatch(r"\d{6}", code) and code in fixed_codes:
            selected.append(dict(source_row))
    return selected


def _daily_stock_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("BAS_DD", "")).strip(),
        str(row.get(DAILY_TICKER_CODE_FIELD, "")).strip(),
    )


def _coerce_daily_numeric_fields(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    converted_rows: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {
        field: {
            "conversion_failures": 0,
            "missing_count": 0,
            "output_type": output_type,
            "source_types": set(),
        }
        for field, output_type in DAILY_NUMERIC_FIELDS.items()
    }
    for source_row in rows:
        converted = dict(source_row)
        for field, output_type in DAILY_NUMERIC_FIELDS.items():
            raw = source_row.get(field)
            if raw is not None:
                summary[field]["source_types"].add(type(raw).__name__)
            if _value_missing(raw):
                converted[field] = math.nan
                summary[field]["missing_count"] += 1
                continue
            text = str(raw).replace(",", "").strip()
            try:
                if output_type == "integer":
                    if not re.fullmatch(r"[+-]?\d+", text):
                        raise ValueError
                    value: int | float = int(text)
                else:
                    value = float(text)
                    if not math.isfinite(value):
                        raise ValueError
                converted[field] = value
            except (TypeError, ValueError, OverflowError):
                converted[field] = math.nan
                summary[field]["conversion_failures"] += 1
        converted_rows.append(converted)
    serializable_summary: dict[str, dict[str, Any]] = {}
    for field, values in summary.items():
        serializable_summary[field] = {
            **values,
            "source_types": sorted(values["source_types"]),
        }
    return converted_rows, serializable_summary


def _is_primary_kospi_row(row: Mapping[str, Any]) -> bool:
    return (
        _normalize_name(row.get("IDX_CLSS")) == "kospi"
        and _normalize_name(row.get("IDX_NM")) == _normalize_name("코스피")
    )


def _schema_hash(payload: Any) -> str:
    fields: list[str] = []
    if isinstance(payload, dict):
        rows = payload.get("OutBlock_1")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            fields = sorted(str(key) for key in rows[0])
        else:
            for value in payload.values():
                if isinstance(value, dict):
                    nested = value.get("row")
                    if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                        fields = sorted(str(key) for key in nested[0])
                        break
    return hashlib.sha256("\n".join(fields).encode("utf-8")).hexdigest()


def _result_code(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "UNAVAILABLE"
    for key in ("RESULT", "Result", "result"):
        result = payload.get(key)
        if isinstance(result, dict):
            return str(result.get("CODE", result.get("code", "UNAVAILABLE")))
    for key in ("OutResult", "OUT_RESULT", "outResult"):
        result = payload.get(key)
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return str(result[0].get("CODE", result[0].get("code", "UNAVAILABLE")))
    return "HTTP_OK_NO_RESULT_CODE"


def _latest_date(payload: Any) -> str | None:
    candidates: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.upper() in {"BAS_DD", "TIME", "BASE_DATE", "BASDT"}:
                    text = re.sub(r"[^0-9]", "", str(nested))
                    if len(text) >= 8:
                        candidates.append(text[:8])
                else:
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return max(candidates) if candidates else None


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


class SafeApiClient:
    """Small JSON client that never logs a URL, header, body, or secret."""

    def __init__(self, log_path: Path, timeout_seconds: int = 30) -> None:
        self.log_path = log_path
        self.timeout_seconds = timeout_seconds

    def request_json(
        self,
        *,
        endpoint_id: str,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> ApiResponse:
        requested_at = datetime.now(timezone.utc)
        data = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = int(response.status)
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            self._log_failure(endpoint_id, requested_at, int(exc.code), "HTTP_ERROR")
            raise FeasibilityError(f"{endpoint_id}: HTTP_{int(exc.code)}") from None
        except (URLError, TimeoutError, OSError):
            self._log_failure(endpoint_id, requested_at, None, "NETWORK_ERROR")
            raise FeasibilityError(f"{endpoint_id}: NETWORK_ERROR") from None
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._log_failure(endpoint_id, requested_at, status, "INVALID_JSON")
            raise FeasibilityError(f"{endpoint_id}: INVALID_JSON") from None
        latest = _latest_date(payload)
        self._log(
            endpoint_id=endpoint_id,
            requested_at=requested_at,
            http_status=status,
            result_code=_result_code(payload),
            latest_data_date=latest,
            response_date_header_present=bool(response_headers.get("Date")),
            schema_hash=_schema_hash(payload),
        )
        return ApiResponse(payload, status, response_headers, requested_at)

    def _log_failure(
        self,
        endpoint_id: str,
        requested_at: datetime,
        http_status: int | None,
        result_code: str,
    ) -> None:
        self._log(
            endpoint_id=endpoint_id,
            requested_at=requested_at,
            http_status=http_status,
            result_code=result_code,
            latest_data_date=None,
            response_date_header_present=False,
            schema_hash=None,
        )

    def _log(
        self,
        *,
        endpoint_id: str,
        requested_at: datetime,
        http_status: int | None,
        result_code: str,
        latest_data_date: str | None,
        response_date_header_present: bool,
        schema_hash: str | None,
    ) -> None:
        kst = requested_at.astimezone(KST)
        _append_jsonl(
            self.log_path,
            {
                "credential_redacted": True,
                "endpoint_id": endpoint_id,
                "http_status": http_status,
                "latest_data_date": latest_data_date,
                "request_at_kst": kst.isoformat(timespec="seconds"),
                "request_at_utc": requested_at.isoformat(timespec="seconds"),
                "response_date_header_present": response_date_header_present,
                "result_code": result_code,
                "schema_hash": schema_hash,
            },
        )


def _project_root(config_path: str | Path) -> Path:
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FeasibilityError("CONFIG_NOT_FOUND")
    return path.parent.parent


def _config_scalar(config_path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s+{re.escape(key)}:\s*[\"']?([^\"'#\n]+)", re.MULTILINE)
    match = pattern.search(config_path.read_text(encoding="utf-8"))
    if not match:
        raise FeasibilityError(f"CONFIG_KEY_NOT_FOUND:{key}")
    return match.group(1).strip()


def _guard_protocol(config_path: Path) -> None:
    text = config_path.read_text(encoding="utf-8")
    if 'status: "DRAFT_NOT_FROZEN"' not in text:
        raise FeasibilityError("PROTOCOL_NOT_DRAFT")
    if "results_may_run: false" not in text:
        raise FeasibilityError("RESULTS_GUARD_NOT_FALSE")
    if (config_path.parent.parent / "results" / "v2_1").exists():
        raise FeasibilityError("RESULTS_V2_1_MUST_BE_ABSENT_FOR_FEASIBILITY")


def _krx_url(endpoint_id: str) -> str:
    path, api_id = KRX_ENDPOINTS[endpoint_id]
    return f"{KRX_BASE_URL}/{path}/{api_id}"


def _krx_rows(response: ApiResponse) -> list[dict[str, Any]]:
    if not isinstance(response.payload, dict):
        return []
    rows = response.payload.get("OutBlock_1", [])
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_ticker_mapping(
    path: Path,
    kospi_rows: Iterable[Mapping[str, Any]],
    kosdaq_rows: Iterable[Mapping[str, Any]],
    identity_provenance_path: Path | None = None,
) -> dict[str, int]:
    official = [dict(row) for row in (*tuple(kospi_rows), *tuple(kosdaq_rows))]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in official:
        for field in ("ISU_NM", "ISU_ABBRV"):
            normalized = _normalize_name(row.get(field))
            if normalized:
                by_name.setdefault(normalized, []).append(row)

    provenance = _read_identity_provenance(identity_provenance_path)
    output: list[dict[str, str]] = []
    counts = {"mapped": 0, "failed": 0, "ambiguous": 0}
    for sector, ticker in _legacy_rows():
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for candidate in by_name.get(_normalize_name(ticker), []):
            key = (str(candidate.get("ISU_SRT_CD", "")), str(candidate.get("ISU_CD", "")))
            unique[key] = candidate
        candidates = list(unique.values())
        match_method = "CURRENT_OFFICIAL_NAME"
        if not candidates and ticker in provenance:
            identity = provenance[ticker]
            for candidate in official:
                if (
                    str(candidate.get(BASIC_TICKER_CODE_FIELD, "")).strip()
                    == identity["ticker_code"]
                    and str(candidate.get("ISU_CD", "")).strip() == identity["isin_code"]
                ):
                    key = (
                        str(candidate.get(BASIC_TICKER_CODE_FIELD, "")),
                        str(candidate.get("ISU_CD", "")),
                    )
                    unique[key] = candidate
            candidates = list(unique.values())
            match_method = "VERIFIED_CODE_AND_ISIN_PROVENANCE"
        row = {column: "" for column in TICKER_COLUMNS}
        row.update(
            legacy_sector=sector,
            legacy_ticker_name=ticker,
            official_source_id="KRX_STOCK_BASIC_INFORMATION",
            checked_at=date.today().isoformat(),
            fixed_sample_5=str(ticker in FIXED_SAMPLE).lower(),
        )
        if len(candidates) == 1:
            candidate = candidates[0]
            required = {
                "ticker_code": str(candidate.get(BASIC_TICKER_CODE_FIELD, "")).strip(),
                "isin_code": str(candidate.get("ISU_CD", "")).strip(),
                "market": str(candidate.get("MKT_TP_NM", "")).strip(),
                "listing_date": str(candidate.get("LIST_DD", "")).strip(),
            }
            if all(required.values()):
                row.update(required)
                row["mapping_status"] = (
                    "MAPPED_OFFICIAL_IDENTITY_PROVENANCE"
                    if match_method == "VERIFIED_CODE_AND_ISIN_PROVENANCE"
                    else "MAPPED_OFFICIAL_CURRENT"
                )
                if match_method == "VERIFIED_CODE_AND_ISIN_PROVENANCE":
                    row["official_source_id"] = (
                        "KRX_STOCK_BASIC_INFORMATION+V2_1_IDENTITY_PROVENANCE"
                    )
                counts["mapped"] += 1
            else:
                row["mapping_status"] = "UNMAPPED_INCOMPLETE_OFFICIAL_METADATA"
                row["failure_reason"] = "CODE_ISIN_MARKET_OR_LISTING_DATE_MISSING"
                counts["failed"] += 1
        elif len(candidates) > 1:
            row["mapping_status"] = "AMBIGUOUS"
            row["failure_reason"] = "MULTIPLE_OFFICIAL_NAME_MATCHES"
            counts["ambiguous"] += 1
        else:
            row["mapping_status"] = "UNMAPPED"
            row["failure_reason"] = "NO_EXACT_OFFICIAL_NAME_MATCH"
            counts["failed"] += 1
        output.append(row)

    codes = [row["ticker_code"] for row in output if row["ticker_code"]]
    duplicates = len(codes) - len(set(codes))
    if duplicates:
        raise FeasibilityError("DUPLICATE_NONBLANK_TICKER_CODES")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TICKER_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)
    counts["duplicate_nonblank_codes"] = duplicates
    return counts


def _update_index_candidates(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    with path.open(encoding="utf-8", newline="") as handle:
        mapping = list(csv.DictReader(handle))
    official_by_name: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        name = _normalize_name(row.get("IDX_NM"))
        if name:
            official_by_name.setdefault(name, []).append(row)
    codes_found = 0
    for entry in mapping:
        candidate_name = entry.get("krx_index_name", "")
        matches = official_by_name.get(_normalize_name(candidate_name), [])
        codes = {
            str(match.get("IDX_ID", match.get("IDX_CD", ""))).strip()
            for match in matches
            if str(match.get("IDX_ID", match.get("IDX_CD", ""))).strip()
        }
        if len(codes) == 1:
            entry["krx_index_code"] = next(iter(codes))
            note = "공식 KRX 시리즈 응답에서 지수명·코드 확인, 구성 정의는 미확인"
            if note not in entry["mapping_basis"]:
                entry["mapping_basis"] = entry["mapping_basis"] + "; " + note
            entry["checked_at"] = date.today().isoformat()
            codes_found += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mapping[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(mapping)
    return {"candidate_codes_found": codes_found, "exact_or_partial": 0}


def _ecos_rows(payload: Any, block: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    section = payload.get(block)
    if not isinstance(section, dict):
        return []
    rows = section.get("row", [])
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _verify_ecos(client: SafeApiClient, api_key: str) -> dict[str, Any]:
    item_url = f"{ECOS_BASE_URL}/StatisticItemList/{api_key}/json/kr/1/100/731Y001/"
    response = client.request_json(endpoint_id="ECOS_STATISTIC_ITEM_LIST", url=item_url)
    items = _ecos_rows(response.payload, "StatisticItemList")
    observed = {str(item.get("ITEM_CODE1", "")): item for item in items}
    missing_codes = sorted(set(ECOS_ITEMS.values()) - set(observed))
    date_matches = 0
    expected_checks = len(ECOS_ITEMS) * len(ECOS_CHECK_DATES)
    for item_code in ECOS_ITEMS.values():
        for day in ECOS_CHECK_DATES:
            url = (
                f"{ECOS_BASE_URL}/StatisticSearch/{api_key}/json/kr/1/10/"
                f"731Y001/D/{day}/{day}/{item_code}/"
            )
            checked = client.request_json(
                endpoint_id=f"ECOS_STATISTIC_SEARCH_731Y001_{item_code}_{day}",
                url=url,
            )
            rows = _ecos_rows(checked.payload, "StatisticSearch")
            if len(rows) == 1 and str(rows[0].get("TIME", "")) == day:
                date_matches += 1
    return {
        "date_checks_expected": expected_checks,
        "date_checks_matched": date_matches,
        "item_codes_missing": missing_codes,
        "item_definition_status": (
            "VERIFIED" if not missing_codes and date_matches == expected_checks else "MISMATCH"
        ),
        "publication_time": "UNRESOLVED_03",
        "revision_policy": "UNRESOLVED_03",
        "values_persisted": False,
    }


def run_metadata(config_path: Path) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_protocol(config_path)
    statuses = {
        "KRX_API_KEY": credential_status("KRX_API_KEY"),
        "ECOS_API_KEY": credential_status("ECOS_API_KEY"),
    }
    output: dict[str, Any] = {"credentials": statuses, "mode": "metadata"}
    client = SafeApiClient(root / "data" / "metadata" / "api_logs" / "requests.jsonl")
    bas_dd = re.sub(r"[^0-9]", "", _config_scalar(config_path, "collection_end"))
    if statuses["KRX_API_KEY"] == "SET":
        key = os.environ["KRX_API_KEY"]
        try:
            kospi = client.request_json(
                endpoint_id="KRX_KOSPI_STOCK_BASIC",
                url=_krx_url("kospi_stock_basic"),
                method="POST",
                headers={"AUTH_KEY": key},
                body={"basDd": bas_dd},
            )
            kosdaq = client.request_json(
                endpoint_id="KRX_KOSDAQ_STOCK_BASIC",
                url=_krx_url("kosdaq_stock_basic"),
                method="POST",
                headers={"AUTH_KEY": key},
                body={"basDd": bas_dd},
            )
            kospi_rows = _krx_rows(kospi)
            kosdaq_rows = _krx_rows(kosdaq)
            if not kospi_rows or not kosdaq_rows:
                raise FeasibilityError("KRX_BASIC_INFO_EMPTY_RESPONSE")
            output["ticker_mapping"] = _write_ticker_mapping(
                root / "data" / "metadata" / "v2_1_ticker_mapping.csv",
                kospi_rows,
                kosdaq_rows,
                root / "data" / "metadata" / "v2_1_ticker_identity_provenance.csv",
            )
            krx_index = client.request_json(
                endpoint_id="KRX_INDEX_DAILY",
                url=_krx_url("krx_index_daily"),
                method="POST",
                headers={"AUTH_KEY": key},
                body={"basDd": bas_dd},
            )
            output["index_candidates"] = _update_index_candidates(
                root / "data" / "metadata" / "v2_1_krx_index_mapping.csv",
                _krx_rows(krx_index),
            )
            output["krx_status"] = "COMPLETED"
        except FeasibilityError as exc:
            output["krx_status"] = "BLOCKED_SERVICE_OR_SCHEMA"
            output["krx_error"] = str(exc)
    else:
        output["krx_status"] = "BLOCKED_CREDENTIAL"
    if statuses["ECOS_API_KEY"] == "SET":
        try:
            output["ecos"] = _verify_ecos(client, os.environ["ECOS_API_KEY"])
            output["ecos_status"] = "COMPLETED"
        except FeasibilityError as exc:
            output["ecos_status"] = "BLOCKED_SERVICE_OR_SCHEMA"
            output["ecos_error"] = str(exc)
    else:
        output["ecos_status"] = "BLOCKED_CREDENTIAL"
    return output


def _month_start_two_months_before(end: date) -> date:
    month_index = end.year * 12 + (end.month - 1) - 2
    return date(month_index // 12, month_index % 12 + 1, 1)


def _read_fixed_codes(path: Path) -> dict[str, tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row.get("fixed_sample_5", "").lower() == "true"]
    if {row["legacy_ticker_name"] for row in selected} != FIXED_SAMPLE:
        raise FeasibilityError("FIXED_SAMPLE_CHANGED")
    if any(not row.get("ticker_code") or not row.get("market") for row in selected):
        raise FeasibilityError("FIXED_SAMPLE_MAPPING_INCOMPLETE")
    codes = [row["ticker_code"].strip() for row in selected]
    if any(not re.fullmatch(r"\d{6}", code) for code in codes):
        raise FeasibilityError("FIXED_SAMPLE_CODE_INVALID")
    if len(codes) != len(set(codes)):
        raise FeasibilityError("FIXED_SAMPLE_CODE_DUPLICATE")
    return {
        row["ticker_code"]: (row["legacy_ticker_name"], row["market"])
        for row in selected
    }


def _value_missing(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "-"}


def run_schema_sample(config_path: Path) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_protocol(config_path)
    if credential_status("KRX_API_KEY") != "SET":
        return {"mode": "schema_sample", "status": "BLOCKED_CREDENTIAL"}
    try:
        fixed = _read_fixed_codes(root / "data" / "metadata" / "v2_1_ticker_mapping.csv")
    except FeasibilityError as exc:
        return {"mode": "schema_sample", "status": "BLOCKED_MAPPING", "reason": str(exc)}
    end = date.fromisoformat(_config_scalar(config_path, "collection_end"))
    start = _month_start_two_months_before(end)
    client = SafeApiClient(root / "data" / "metadata" / "api_logs" / "requests.jsonl")
    key = os.environ["KRX_API_KEY"]
    observations: list[dict[str, Any]] = []
    index_observations: list[dict[str, Any]] = []
    day = start
    try:
        while day <= end:
            if day.weekday() < 5:
                bas_dd = day.strftime("%Y%m%d")
                for endpoint in ("kospi_stock_daily", "kosdaq_stock_daily"):
                    response = client.request_json(
                        endpoint_id=f"KRX_{endpoint.upper()}_{bas_dd}",
                        url=_krx_url(endpoint),
                        method="POST",
                        headers={"AUTH_KEY": key},
                        body={"basDd": bas_dd},
                    )
                    observations.extend(_fixed_daily_rows(_krx_rows(response), fixed))
                response = client.request_json(
                    endpoint_id=f"KRX_KOSPI_INDEX_DAILY_{bas_dd}",
                    url=_krx_url("kospi_index_daily"),
                    method="POST",
                    headers={"AUTH_KEY": key},
                    body={"basDd": bas_dd},
                )
                matches = [
                    row
                    for row in _krx_rows(response)
                    if _is_primary_kospi_row(row)
                ]
                index_observations.extend(matches)
            day += timedelta(days=1)
    except FeasibilityError as exc:
        return {"mode": "schema_sample", "status": "BLOCKED_SERVICE_OR_SCHEMA", "reason": str(exc)}

    _, conversion_summary = _coerce_daily_numeric_fields(observations)
    candidate_fields = tuple(DAILY_NUMERIC_FIELDS)
    field_summary: dict[str, Any] = {}
    for field in candidate_fields:
        details = conversion_summary[field]
        field_summary[field] = {
            "corporate_action_adjustment": "UNRESOLVED_01",
            "conversion_failures": details["conversion_failures"],
            "data_types_observed": details["source_types"],
            "missing_rate": details["missing_count"] / len(observations) if observations else None,
            "numeric_output_type": details["output_type"],
            "official_unit": {
                "TDD_CLSPRC": "KRW",
                "FLUC_RT": "percent",
                "ACC_TRDVOL": "shares",
                "ACC_TRDVAL": "KRW",
                "MKTCAP": "KRW",
            }[field],
        }
    keys = [_daily_stock_key(row) for row in observations]
    rows_by_ticker = {
        code: sum(str(row.get(DAILY_TICKER_CODE_FIELD, "")) == code for row in observations)
        for code in fixed
    }
    summary = {
        "date_end": end.isoformat(),
        "date_start": start.isoformat(),
        "duplicate_stock_date_keys": len(keys) - len(set(keys)),
        "field_summary": field_summary,
        "fixed_sample_count": len(fixed),
        "forecast_as_of_availability": "NOT_INFERABLE_FROM_RETROSPECTIVE_QUERY",
        "index_rows": len(index_observations),
        "mode": "schema_sample",
        "raw_values_persisted_publicly": False,
        "rows_by_ticker": rows_by_ticker,
        "status": "COMPLETED_SCHEMA_ONLY",
        "stock_rows": len(observations),
    }
    # Re-check immediately before the only write in this mode.  This prevents a
    # concurrent or accidental results run from coexisting with feasibility output.
    _guard_protocol(config_path)
    private_path = root / "data" / "metadata" / "private" / "schema_sample_summary.json"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def run_corporate_actions(config_path: Path) -> dict[str, Any]:
    _project_root(config_path)
    _guard_protocol(config_path)
    if credential_status("KRX_API_KEY") != "SET":
        return {
            "events_passed": 0,
            "events_failed": 0,
            "events_verified": 0,
            "mode": "corporate_actions",
            "status": "BLOCKED_CREDENTIAL",
        }
    return {
        "events_passed": 0,
        "events_failed": 0,
        "events_verified": 0,
        "mode": "corporate_actions",
        "reason": "NO_OFFICIAL_CORPORATE_ACTION_ENDPOINT_REGISTERED",
        "status": "BLOCKED_OFFICIAL_SOURCE_ENDPOINT",
    }


def _scheduled_slot(source: str, now_kst: datetime) -> bool:
    krx_slots = {(15, 40), (16, 0), (16, 30), (17, 0), (17, 30), (18, 0), (18, 30), (20, 0), (23, 30)}
    ecos_slots = {(9, 0), (16, 0), (17, 0), (18, 0), (18, 30), (20, 0), (23, 30)}
    slots = krx_slots if source == "KRX" else ecos_slots
    return (now_kst.hour, now_kst.minute) in slots


def _timestamp_record(source: str, endpoint: str, response: ApiResponse) -> dict[str, Any]:
    now_kst = response.requested_at_utc.astimezone(KST)
    latest = _latest_date(response.payload)
    return {
        "credential_redacted": True,
        "current_day_data_present": latest == now_kst.strftime("%Y%m%d"),
        "endpoint_id": endpoint,
        "http_status": response.http_status,
        "latest_data_date": latest,
        "request_at_kst": now_kst.isoformat(timespec="seconds"),
        "request_at_utc": response.requested_at_utc.isoformat(timespec="seconds"),
        "response_date_header_present": bool(response.headers.get("Date")),
        "result_code": _result_code(response.payload),
        "scheduled_slot": _scheduled_slot(source, now_kst),
        "schema_hash": _schema_hash(response.payload),
        "source": source,
    }


def run_timestamp_once(config_path: Path, source: str) -> dict[str, Any]:
    root = _project_root(config_path)
    _guard_protocol(config_path)
    client = SafeApiClient(root / "data" / "metadata" / "api_logs" / "requests.jsonl")
    observation_path = root / "data" / "metadata" / "api_logs" / "timestamp_observations.jsonl"
    records: list[dict[str, Any]] = []
    blocked: dict[str, str] = {}
    now_kst = datetime.now(timezone.utc).astimezone(KST)
    today = now_kst.strftime("%Y%m%d")
    if source in {"krx", "both"}:
        if credential_status("KRX_API_KEY") != "SET":
            blocked["KRX"] = "BLOCKED_CREDENTIAL"
        else:
            key = os.environ["KRX_API_KEY"]
            for endpoint in ("kospi_stock_daily", "kospi_index_daily"):
                try:
                    response = client.request_json(
                        endpoint_id=f"KRX_{endpoint.upper()}_TIMESTAMP",
                        url=_krx_url(endpoint),
                        method="POST",
                        headers={"AUTH_KEY": key},
                        body={"basDd": today},
                    )
                    record = _timestamp_record("KRX", endpoint, response)
                    _append_jsonl(observation_path, record)
                    records.append(record)
                except FeasibilityError as exc:
                    blocked[f"KRX:{endpoint}"] = str(exc)
    if source in {"ecos", "both"}:
        if credential_status("ECOS_API_KEY") != "SET":
            blocked["ECOS"] = "BLOCKED_CREDENTIAL"
        else:
            key = os.environ["ECOS_API_KEY"]
            url = (
                f"{ECOS_BASE_URL}/StatisticSearch/{key}/json/kr/1/10/"
                f"731Y001/D/{today}/{today}/0000001/"
            )
            try:
                response = client.request_json(endpoint_id="ECOS_USDKRW_TIMESTAMP", url=url)
                record = _timestamp_record("ECOS", "StatisticSearch_731Y001_0000001", response)
                _append_jsonl(observation_path, record)
                records.append(record)
            except FeasibilityError as exc:
                blocked["ECOS"] = str(exc)
    return {
        "blocked": blocked,
        "mode": "timestamp_once",
        "observation_count": len(records),
        "records": records,
        "slept_or_waited": False,
    }


def _yaml_parse_status(paths: Iterable[Path]) -> tuple[bool, str]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return False, "PYYAML_NOT_INSTALLED"
    try:
        for path in paths:
            yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return False, "YAML_PARSE_ERROR"
    return True, "PASS"


def _credential_scan(paths: Iterable[Path]) -> int:
    pattern = re.compile(
        r"(?:KRX_API_KEY|ECOS_API_KEY|AUTH_KEY|serviceKey)\s*[:=]\s*[\"']?"
        r"(?!NOT_SET|SET|\[REDACTED\]|KRX_API_KEY|ECOS_API_KEY)([A-Za-z0-9_-]{16,})",
        re.IGNORECASE,
    )
    count = 0
    for path in paths:
        try:
            count += len(pattern.findall(path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return count


def run_audit(config_path: Path) -> dict[str, Any]:
    root = _project_root(config_path)
    checks: dict[str, Any] = {}
    protocol_text = config_path.read_text(encoding="utf-8")
    checks["protocol_draft"] = 'status: "DRAFT_NOT_FROZEN"' in protocol_text
    checks["results_may_run_false"] = "results_may_run: false" in protocol_text
    checks["results_v2_1_absent"] = not (root / "results" / "v2_1").exists()

    ticker_path = root / "data" / "metadata" / "v2_1_ticker_mapping.csv"
    with ticker_path.open(encoding="utf-8", newline="") as handle:
        ticker_rows = list(csv.DictReader(handle))
    checks["ticker_rows_50"] = len(ticker_rows) == 50
    actual_order = [(row["legacy_sector"], row["legacy_ticker_name"]) for row in ticker_rows]
    checks["constants_order_preserved"] = actual_order == _legacy_rows()
    fixed = {row["legacy_ticker_name"] for row in ticker_rows if row["fixed_sample_5"].lower() == "true"}
    checks["fixed_sample_unchanged"] = fixed == FIXED_SAMPLE
    codes = [row["ticker_code"] for row in ticker_rows if row["ticker_code"]]
    checks["duplicate_nonblank_ticker_codes"] = len(codes) - len(set(codes))

    index_path = root / "data" / "metadata" / "v2_1_krx_index_mapping.csv"
    with index_path.open(encoding="utf-8", newline="") as handle:
        index_rows = list(csv.DictReader(handle))
    checks["index_rows_10"] = len(index_rows) == 10
    checks["index_labels_allowed"] = all(
        row["mapping_label"] in {"exact", "partial", "unavailable"} for row in index_rows
    )

    yaml_paths = [config_path, root / "data" / "metadata" / "v2_1_source_registry.yaml"]
    collection_config_path = root / "configs" / "v2_1_collection.yaml"
    if collection_config_path.is_file():
        yaml_paths.append(collection_config_path)
    yaml_ok, yaml_detail = _yaml_parse_status(yaml_paths)
    checks["yaml_parse"] = yaml_ok
    checks["yaml_parse_detail"] = yaml_detail
    if collection_config_path.is_file():
        collection_config = collection_config_path.read_text(encoding="utf-8")
        checks["collection_full_collect_disabled"] = "full_collect_enabled: false" in collection_config
        checks["collection_u1_disabled"] = "u1_collection_allowed: false" in collection_config
        checks["collection_results_guard_false"] = "create_results_v2_1: false" in collection_config
        checks["collection_raw_root_absent"] = not (root / "data" / "raw" / "v2_1").exists()
    else:
        checks["collection_full_collect_disabled"] = True
        checks["collection_u1_disabled"] = True
        checks["collection_results_guard_false"] = True
        checks["collection_raw_root_absent"] = True

    public_paths = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and "__pycache__" not in path.parts
    ]
    checks["suspicious_credential_assignments"] = _credential_scan(public_paths)
    try:
        git = shutil.which("git") or "git"
        git_prefix = [git, "-c", f"safe.directory={root.as_posix()}"]
        tracked = subprocess.run(
            [*git_prefix, "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.splitlines()
        forbidden_prefixes = (
            "data/raw/v2_1/",
            "data/feasibility_raw/",
            "data/metadata/private/",
            "data/metadata/api_logs/",
            "results/v2_1/",
        )
        checks["tracked_forbidden_files"] = [
            path for path in tracked if path.replace("\\", "/").startswith(forbidden_prefixes)
        ]
        diff_check = subprocess.run(
            [*git_prefix, "diff", "--check"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        checks["git_diff_check"] = diff_check.returncode == 0
    except (OSError, subprocess.SubprocessError):
        checks["tracked_forbidden_files"] = "GIT_UNAVAILABLE"
        checks["git_diff_check"] = False

    pass_conditions = [
        checks["protocol_draft"],
        checks["results_may_run_false"],
        checks["results_v2_1_absent"],
        checks["ticker_rows_50"],
        checks["constants_order_preserved"],
        checks["fixed_sample_unchanged"],
        checks["duplicate_nonblank_ticker_codes"] == 0,
        checks["index_rows_10"],
        checks["index_labels_allowed"],
        checks["yaml_parse"],
        checks["collection_full_collect_disabled"],
        checks["collection_u1_disabled"],
        checks["collection_results_guard_false"],
        checks["collection_raw_root_absent"],
        checks["suspicious_credential_assignments"] == 0,
        checks["tracked_forbidden_files"] == [],
        checks["git_diff_check"],
    ]
    return {"checks": checks, "mode": "audit", "status": "PASS" if all(pass_conditions) else "FAIL"}


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run V2.1 data-feasibility checks only.")
    parser.add_argument(
        "--config",
        default=root / "configs" / "v2_1_protocol.yaml",
        help="Draft V2.1 protocol config",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("metadata", "schema_sample", "corporate_actions", "timestamp_once", "audit"),
    )
    parser.add_argument(
        "--source",
        choices=("krx", "ecos", "both"),
        default="both",
        help="Source for timestamp_once",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path = Path(args.config).resolve()
    runners = {
        "metadata": lambda: run_metadata(config_path),
        "schema_sample": lambda: run_schema_sample(config_path),
        "corporate_actions": lambda: run_corporate_actions(config_path),
        "timestamp_once": lambda: run_timestamp_once(config_path, args.source),
        "audit": lambda: run_audit(config_path),
    }
    try:
        result = runners[args.mode]()
    except FeasibilityError as exc:
        result = {"mode": args.mode, "status": "ERROR", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("status") in {"ERROR", "FAIL"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
