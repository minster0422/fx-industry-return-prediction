"""Local-only KRX raw archive acquisition for the V2.1 research scaffold.

This module preserves official API responses without calculating returns,
targets, features, predictions, performance metrics, or backtests.  Raw
payloads and request-level manifests stay under ``data/raw/v2_1`` and are
excluded from Git.
"""

from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .v2_1_collection import (
    ENDPOINT_SCHEMAS,
    CollectionError,
    _guard_results_absent,
    _load_yaml,
    _project_root,
    _resolve_from_root,
    build_collection_plan,
    load_u0_mapping,
    request_id,
    retry_backoff_seconds,
)
from .v2_1_feasibility import (
    KRX_BASE_URL,
    KRX_ENDPOINTS,
    KST,
    _latest_date,
    _normalize_name,
    _result_code,
    _schema_hash,
)


ARCHIVE_PURPOSE = "RAW_ARCHIVE_ONLY_NO_RESEARCH_DERIVATIONS"
ARCHIVE_ALLOWED_ENDPOINTS = {
    "kospi_stock_basic",
    "kosdaq_stock_basic",
    "kospi_stock_daily",
    "kosdaq_stock_daily",
    "kospi_index_daily",
}
SUCCESS_RESULT_CODES = {"HTTP_OK_NO_RESULT_CODE", "INFO-000"}


class ArchiveError(CollectionError):
    """An archive failure whose message contains no credential or raw value."""


class ArchiveQuotaExhausted(ArchiveError):
    """Raised before a request that would exceed the configured daily budget."""


@dataclass(frozen=True)
class ArchiveRequest:
    endpoint_name: str
    endpoint_id: str
    bas_dd: str
    market: str
    category: str
    relative_path: str
    request_id: str


@dataclass(frozen=True)
class ArchiveResult:
    request_id: str
    endpoint_name: str
    endpoint_id: str
    bas_dd: str
    market: str
    relative_path: str
    sha256: str
    schema_hash: str
    row_count: int
    http_status: int
    result_code: str
    latest_data_date: str | None
    retry_count: int
    raw_bytes: int
    gzip_bytes: int
    completed_at_utc: str


def _pid_is_running(pid: int) -> bool:
    if pid < 1:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class ArchiveRunLock:
    """Cross-process lock preventing two collectors from writing the same file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._acquired = False

    def __enter__(self) -> "ArchiveRunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8"))
                    pid = int(payload.get("pid", -1))
                except (OSError, ValueError, json.JSONDecodeError):
                    raise ArchiveError("ARCHIVE_RUN_LOCK_PRESENT") from None
                if not _pid_is_running(pid):
                    try:
                        self.path.unlink()
                    except OSError:
                        raise ArchiveError("ARCHIVE_STALE_LOCK_REMOVE_FAILED") from None
                    continue
                raise ArchiveError("ARCHIVE_RUN_ALREADY_ACTIVE")
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(
                        {
                            "pid": os.getpid(),
                            "started_at_utc": datetime.now(timezone.utc).isoformat(),
                        },
                        handle,
                        sort_keys=True,
                    )
                    handle.write("\n")
                self._acquired = True
                return self
        raise ArchiveError("ARCHIVE_RUN_LOCK_ACQUIRE_FAILED")

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._acquired = False


def archive_atomic_write(path: Path, payload: bytes) -> None:
    """Write with a process/thread-specific temp file and OneDrive-safe retries."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise ArchiveError("ARCHIVE_ATOMIC_REPLACE_LOCKED") from None
                time.sleep(0.2 * (attempt + 1))
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _archive_config(config_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = _project_root(config_path)
    _guard_results_absent(root)
    config = _load_yaml(config_path)
    archive = config.get("archive_only")
    policy = config.get("request_policy")
    collection = config.get("collection")
    if not all(isinstance(value, dict) for value in (archive, policy, collection)):
        raise ArchiveError("ARCHIVE_CONFIG_SECTION_MISSING")
    if archive.get("enabled") is not True:
        raise ArchiveError("ARCHIVE_ONLY_NOT_ENABLED")
    if archive.get("purpose") != ARCHIVE_PURPOSE:
        raise ArchiveError("ARCHIVE_PURPOSE_CHANGED")
    required_false = (
        "calculate_returns",
        "generate_targets",
        "train_models",
        "generate_predictions",
        "calculate_performance",
        "create_results_v2_1",
        "normalize_u0_panel",
    )
    if any(archive.get(key) is not False for key in required_false):
        raise ArchiveError("ARCHIVE_RESEARCH_DERIVATION_GUARD_CHANGED")
    if archive.get("raw_payloads_local_only") is not True:
        raise ArchiveError("ARCHIVE_RAW_PAYLOADS_MUST_BE_LOCAL_ONLY")
    if archive.get("allowed_endpoints") != sorted(ARCHIVE_ALLOWED_ENDPOINTS):
        raise ArchiveError("ARCHIVE_ENDPOINT_ALLOWLIST_CHANGED")
    hard_limit = int(policy.get("krx_daily_hard_limit", 0))
    budget = int(policy.get("configured_daily_request_budget", 0))
    reserve = int(archive.get("untracked_request_reserve", 0))
    if hard_limit != 10000 or not 1 <= reserve < budget < hard_limit:
        raise ArchiveError("ARCHIVE_DAILY_QUOTA_POLICY_INVALID")
    if budget + 0 > hard_limit:
        raise ArchiveError("ARCHIVE_DAILY_BUDGET_EXCEEDS_HARD_LIMIT")
    return root, config, archive


def _archive_url(endpoint_name: str) -> str:
    if endpoint_name not in ARCHIVE_ALLOWED_ENDPOINTS:
        raise ArchiveError("ARCHIVE_ENDPOINT_NOT_ALLOWED")
    path, api_id = KRX_ENDPOINTS[endpoint_name]
    return f"{KRX_BASE_URL}/{path}/{api_id}"


def _archive_relative_path(endpoint_name: str, bas_dd: str) -> str:
    schema = ENDPOINT_SCHEMAS[endpoint_name]
    return f"krx/{schema.category}/{schema.endpoint_id}/{bas_dd}.json.gz"


def _market(endpoint_name: str) -> str:
    return {
        "kospi_stock_basic": "KOSPI",
        "kosdaq_stock_basic": "KOSDAQ",
        "kospi_stock_daily": "KOSPI",
        "kosdaq_stock_daily": "KOSDAQ",
        "kospi_index_daily": "KOSPI_INDEX",
    }[endpoint_name]


def make_archive_request(endpoint_name: str, bas_dd: str) -> ArchiveRequest:
    schema = ENDPOINT_SCHEMAS[endpoint_name]
    market = _market(endpoint_name)
    return ArchiveRequest(
        endpoint_name=endpoint_name,
        endpoint_id=schema.endpoint_id,
        bas_dd=bas_dd,
        market=market,
        category=schema.category,
        relative_path=_archive_relative_path(endpoint_name, bas_dd),
        request_id=request_id(schema.endpoint_id, bas_dd, market),
    )


def build_archive_requests(
    config_path: Path,
    protocol_path: Path | None = None,
) -> list[ArchiveRequest]:
    root, config, _ = _archive_config(config_path)
    plan = build_collection_plan(config_path, protocol_path)
    collection = config["collection"]
    start = str(collection["collection_start"]).replace("-", "")
    end = str(collection["collection_end"]).replace("-", "")
    if (
        plan["date_range"]["start"].replace("-", "") != start
        or plan["date_range"]["end"].replace("-", "") != end
    ):
        raise ArchiveError("ARCHIVE_PLAN_DATE_MISMATCH")
    weekdays: list[str] = []
    current = datetime.strptime(start, "%Y%m%d").date()
    final = datetime.strptime(end, "%Y%m%d").date()
    while current <= final:
        if current.weekday() < 5:
            weekdays.append(current.strftime("%Y%m%d"))
        current = current.fromordinal(current.toordinal() + 1)
    requests = [
        make_archive_request(endpoint_name, bas_dd)
        for bas_dd in weekdays
        for endpoint_name in (
            "kospi_stock_daily",
            "kosdaq_stock_daily",
            "kospi_index_daily",
        )
    ]
    requests.extend(
        (
            make_archive_request("kospi_stock_basic", end),
            make_archive_request("kosdaq_stock_basic", end),
        )
    )
    requests.sort(key=lambda item: (item.bas_dd, item.endpoint_id))
    if len(requests) != plan["request_plan"]["total_request_upper_bound"]:
        raise ArchiveError("ARCHIVE_REQUEST_COUNT_PLAN_MISMATCH")
    if len({item.request_id for item in requests}) != len(requests):
        raise ArchiveError("ARCHIVE_REQUEST_ID_DUPLICATE")
    raw_root = _resolve_from_root(root, collection["raw_root"])
    for item in requests:
        candidate = (raw_root / item.relative_path).resolve()
        try:
            candidate.relative_to(raw_root.resolve())
        except ValueError:
            raise ArchiveError("ARCHIVE_RAW_PATH_OUTSIDE_ROOT") from None
    return requests


class ArchiveState:
    """SQLite-backed quota, checkpoint, and sanitized manifest state."""

    def __init__(
        self,
        path: Path,
        *,
        daily_budget: int,
        untracked_reserve: int,
        acquire_run_lock: bool = False,
    ) -> None:
        self.path = path
        self.daily_budget = daily_budget
        self.untracked_reserve = untracked_reserve
        self._lock = threading.Lock()
        self._run_lock = (
            ArchiveRunLock(path.with_name("archive_run.lock"))
            if acquire_run_lock
            else None
        )
        if self._run_lock is not None:
            self._run_lock.__enter__()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        except Exception:
            if self._run_lock is not None:
                self._run_lock.__exit__(None, None, None)
            raise
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                endpoint_id TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                attempt_date_kst TEXT NOT NULL,
                attempted_at_utc TEXT NOT NULL,
                outcome TEXT NOT NULL,
                http_status INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_attempt_date
                ON attempts(attempt_date_kst);
            CREATE TABLE IF NOT EXISTS completed (
                request_id TEXT PRIMARY KEY,
                endpoint_name TEXT NOT NULL,
                endpoint_id TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                market TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                schema_hash TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                http_status INTEGER NOT NULL,
                result_code TEXT NOT NULL,
                latest_data_date TEXT,
                retry_count INTEGER NOT NULL,
                raw_bytes INTEGER NOT NULL,
                gzip_bytes INTEGER NOT NULL,
                completed_at_utc TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()
        if self._run_lock is not None:
            self._run_lock.__exit__(None, None, None)

    @staticmethod
    def _today_kst() -> str:
        return datetime.now(timezone.utc).astimezone(KST).date().isoformat()

    def attempts_today(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM attempts WHERE attempt_date_kst = ?",
                (self._today_kst(),),
            ).fetchone()
        return int(row[0])

    def remaining_attempt_budget(self) -> int:
        allowance = self.daily_budget - self.untracked_reserve
        return max(0, allowance - self.attempts_today())

    def reserve_attempt(self, item: ArchiveRequest, attempt_number: int) -> int:
        now = datetime.now(timezone.utc)
        day = now.astimezone(KST).date().isoformat()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            count = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM attempts WHERE attempt_date_kst = ?",
                    (day,),
                ).fetchone()[0]
            )
            if count >= self.daily_budget - self.untracked_reserve:
                self._connection.rollback()
                raise ArchiveQuotaExhausted("ARCHIVE_DAILY_BUDGET_EXHAUSTED")
            cursor = self._connection.execute(
                """
                INSERT INTO attempts (
                    request_id, endpoint_id, bas_dd, attempt_number,
                    attempt_date_kst, attempted_at_utc, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.request_id,
                    item.endpoint_id,
                    item.bas_dd,
                    attempt_number,
                    day,
                    now.isoformat(),
                    "STARTED",
                ),
            )
            attempt_id = int(cursor.lastrowid)
            self._connection.commit()
        return attempt_id

    def finish_attempt(
        self,
        attempt_id: int,
        *,
        outcome: str,
        http_status: int | None,
    ) -> None:
        if not outcome or len(outcome) > 64:
            raise ArchiveError("ARCHIVE_ATTEMPT_OUTCOME_INVALID")
        with self._lock:
            self._connection.execute(
                "UPDATE attempts SET outcome = ?, http_status = ? WHERE id = ?",
                (outcome, http_status, attempt_id),
            )
            self._connection.commit()

    def completed_record(self, request_key: str) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._connection.execute(
                "SELECT * FROM completed WHERE request_id = ?",
                (request_key,),
            )
            row = cursor.fetchone()
            columns = [entry[0] for entry in cursor.description or ()]
        return dict(zip(columns, row)) if row else None

    def record_completed(self, result: ArchiveResult) -> None:
        values = asdict(result)
        with self._lock:
            existing = self._connection.execute(
                "SELECT sha256 FROM completed WHERE request_id = ?",
                (result.request_id,),
            ).fetchone()
            if existing and existing[0] != result.sha256:
                raise ArchiveError("ARCHIVE_CHECKPOINT_HASH_CONFLICT")
            self._connection.execute(
                """
                INSERT OR REPLACE INTO completed (
                    request_id, endpoint_name, endpoint_id, bas_dd, market,
                    relative_path, sha256, schema_hash, row_count, http_status,
                    result_code, latest_data_date, retry_count, raw_bytes,
                    gzip_bytes, completed_at_utc
                ) VALUES (
                    :request_id, :endpoint_name, :endpoint_id, :bas_dd, :market,
                    :relative_path, :sha256, :schema_hash, :row_count, :http_status,
                    :result_code, :latest_data_date, :retry_count, :raw_bytes,
                    :gzip_bytes, :completed_at_utc
                )
                """,
                values,
            )
            self._connection.commit()

    def completed_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT request_id, endpoint_name, endpoint_id, bas_dd, market,
                       relative_path, sha256, schema_hash, row_count, http_status,
                       result_code, latest_data_date, retry_count, raw_bytes,
                       gzip_bytes, completed_at_utc
                FROM completed
                ORDER BY bas_dd, endpoint_id
                """
            )
            columns = [entry[0] for entry in cursor.description or ()]
            rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def attempt_day_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT attempt_date_kst, COUNT(*)
                FROM attempts
                GROUP BY attempt_date_kst
                ORDER BY attempt_date_kst
                """
            ).fetchall()
        return {str(day): int(count) for day, count in rows}


def _raw_file_valid(raw_root: Path, record: Mapping[str, Any]) -> bool:
    path = raw_root / str(record["relative_path"])
    if not path.is_file():
        return False
    try:
        raw = gzip.decompress(path.read_bytes())
    except (OSError, EOFError):
        return False
    return hashlib.sha256(raw).hexdigest() == record.get("sha256")


def _decode_payload(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ArchiveError("ARCHIVE_INVALID_JSON_RESPONSE") from None


def _row_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    rows = payload.get("OutBlock_1")
    return len(rows) if isinstance(rows, list) else 0


def _request_raw(
    item: ArchiveRequest,
    *,
    auth_key: str,
    timeout_seconds: int,
) -> tuple[bytes, int]:
    body = json.dumps({"basDd": item.bas_dd}, separators=(",", ":")).encode("utf-8")
    request = Request(
        _archive_url(item.endpoint_name),
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "AUTH_KEY": auth_key,
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read(), int(response.status)


def fetch_archive_request(
    item: ArchiveRequest,
    *,
    auth_key: str,
    raw_root: Path,
    state: ArchiveState,
    timeout_seconds: int,
    maximum_retries: int,
    retryable_http_statuses: Iterable[int],
) -> ArchiveResult:
    existing = state.completed_record(item.request_id)
    if existing and _raw_file_valid(raw_root, existing):
        return ArchiveResult(**existing)
    retryable = {int(value) for value in retryable_http_statuses}
    last_reason = "ARCHIVE_REQUEST_FAILED"
    for attempt_number in range(1, maximum_retries + 2):
        attempt_id = state.reserve_attempt(item, attempt_number)
        try:
            raw, status = _request_raw(
                item,
                auth_key=auth_key,
                timeout_seconds=timeout_seconds,
            )
            payload = _decode_payload(raw)
        except HTTPError as exc:
            status = int(exc.code)
            state.finish_attempt(attempt_id, outcome=f"HTTP_{status}", http_status=status)
            last_reason = f"ARCHIVE_HTTP_{status}"
            if status in retryable and attempt_number <= maximum_retries:
                time.sleep(retry_backoff_seconds(attempt_number))
                continue
            raise ArchiveError(last_reason) from None
        except (URLError, TimeoutError, OSError):
            state.finish_attempt(attempt_id, outcome="NETWORK_ERROR", http_status=None)
            last_reason = "ARCHIVE_NETWORK_ERROR"
            if attempt_number <= maximum_retries:
                time.sleep(retry_backoff_seconds(attempt_number))
                continue
            raise ArchiveError(last_reason) from None
        except ArchiveError:
            state.finish_attempt(attempt_id, outcome="INVALID_JSON", http_status=200)
            last_reason = "ARCHIVE_INVALID_JSON_RESPONSE"
            if attempt_number <= maximum_retries:
                time.sleep(retry_backoff_seconds(attempt_number))
                continue
            raise ArchiveError(last_reason) from None
        result_code = _result_code(payload)
        rows = _row_count(payload)
        raw_hash = hashlib.sha256(raw).hexdigest()
        compressed = gzip.compress(raw, compresslevel=6, mtime=0)
        path = raw_root / item.relative_path
        archive_atomic_write(path, compressed)
        result = ArchiveResult(
            request_id=item.request_id,
            endpoint_name=item.endpoint_name,
            endpoint_id=item.endpoint_id,
            bas_dd=item.bas_dd,
            market=item.market,
            relative_path=item.relative_path,
            sha256=raw_hash,
            schema_hash=_schema_hash(payload),
            row_count=rows,
            http_status=status,
            result_code=result_code,
            latest_data_date=_latest_date(payload),
            retry_count=attempt_number - 1,
            raw_bytes=len(raw),
            gzip_bytes=len(compressed),
            completed_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        state.record_completed(result)
        state.finish_attempt(attempt_id, outcome="COMPLETED", http_status=status)
        return result
    raise ArchiveError(last_reason)


def _write_local_manifest(
    raw_root: Path,
    state: ArchiveState,
) -> tuple[Path, str]:
    path = raw_root / "manifests" / "krx_archive_manifest.jsonl"
    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in state.completed_rows()
    ]
    payload = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    archive_atomic_write(path, payload)
    return path, hashlib.sha256(payload).hexdigest()


def _endpoint_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["endpoint_name"]), []).append(row)
    summary: dict[str, dict[str, Any]] = {}
    for endpoint, values in sorted(grouped.items()):
        dates = sorted(str(row["bas_dd"]) for row in values)
        summary[endpoint] = {
            "completed_requests": len(values),
            "first_bas_dd": dates[0],
            "last_bas_dd": dates[-1],
            "nonempty_responses": sum(int(row["row_count"]) > 0 for row in values),
            "total_rows": sum(int(row["row_count"]) for row in values),
            "raw_bytes": sum(int(row["raw_bytes"]) for row in values),
            "gzip_bytes": sum(int(row["gzip_bytes"]) for row in values),
            "schema_hash_count": len({str(row["schema_hash"]) for row in values}),
            "nonstandard_result_code_count": sum(
                str(row["result_code"]) not in SUCCESS_RESULT_CODES for row in values
            ),
        }
    return summary


def build_archive_status(
    config_path: Path,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    root, config, archive = _archive_config(config_path)
    collection = config["collection"]
    raw_root = _resolve_from_root(root, collection["raw_root"])
    state_path = raw_root / str(archive["state_database"])
    state = ArchiveState(
        state_path,
        daily_budget=int(config["request_policy"]["configured_daily_request_budget"]),
        untracked_reserve=int(archive["untracked_request_reserve"]),
    )
    try:
        requests = build_archive_requests(config_path, protocol_path)
        completed = state.completed_rows()
        valid = sum(_raw_file_valid(raw_root, row) for row in completed)
        manifest_path, manifest_hash = _write_local_manifest(raw_root, state)
        return {
            "mode": "archive-status",
            "status": "COMPLETE" if valid == len(requests) else "PARTIAL",
            "archive_purpose": ARCHIVE_PURPOSE,
            "planned_requests": len(requests),
            "completed_records": len(completed),
            "valid_raw_files": valid,
            "remaining_requests": len(requests) - valid,
            "attempt_counts_by_kst_date": state.attempt_day_counts(),
            "remaining_attempt_budget_today": state.remaining_attempt_budget(),
            "endpoint_summary": _endpoint_summary(completed),
            "local_manifest": str(manifest_path.relative_to(root)),
            "local_manifest_sha256": manifest_hash,
            "raw_payloads_committed": False,
            "research_outputs_generated": False,
        }
    finally:
        state.close()


def write_public_archive_summary(
    config_path: Path,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    root, config, archive = _archive_config(config_path)
    status = build_archive_status(config_path, protocol_path)
    if status["status"] != "COMPLETE":
        raise ArchiveError("ARCHIVE_PUBLIC_SUMMARY_REQUIRES_COMPLETE_ARCHIVE")
    output_path = _resolve_from_root(root, archive["public_summary_path"])
    payload = {
        "archive_version": str(config["collection"]["version"]),
        "status": "COMPLETE",
        "purpose": ARCHIVE_PURPOSE,
        "source": {
            "institution": "Korea Exchange",
            "service": "KRX Data Marketplace OPEN API",
            "official_service_list_url": (
                "https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd"
            ),
            "official_terms_url": str(archive["official_terms_url"]),
            "official_terms_effective_date": str(
                archive["official_terms_effective_date"]
            ),
        },
        "approval": {
            "start": str(archive["approval_start"]),
            "end": str(archive["approval_end"]),
        },
        "scope": {
            "collection_start": str(config["collection"]["collection_start"]),
            "collection_end": str(config["collection"]["collection_end"]),
            "universe": str(config["collection"]["universe_label"]),
            "allowed_endpoints": list(archive["allowed_endpoints"]),
            "weekday_candidate_rule": str(
                config["planning_assumptions"]["date_count_rule"]
            ),
        },
        "integrity": {
            "planned_requests": int(status["planned_requests"]),
            "completed_records": int(status["completed_records"]),
            "valid_raw_files": int(status["valid_raw_files"]),
            "remaining_requests": int(status["remaining_requests"]),
            "local_manifest_sha256": str(status["local_manifest_sha256"]),
            "attempt_counts_by_kst_date": dict(
                status["attempt_counts_by_kst_date"]
            ),
        },
        "endpoint_summary": dict(status["endpoint_summary"]),
        "publication_boundary": {
            "raw_payloads_committed": False,
            "request_level_manifest_committed": False,
            "credentials_committed": False,
            "returns_generated": False,
            "targets_generated": False,
            "models_trained": False,
            "predictions_generated": False,
            "performance_calculated": False,
            "results_v2_1_created": False,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    archive_atomic_write(
        output_path,
        (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    return {
        "mode": "archive-public-summary",
        "status": "WRITTEN",
        "path": str(output_path.relative_to(root)),
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }


def _probe_requests(archive: Mapping[str, Any]) -> list[ArchiveRequest]:
    dates = archive.get("probe_dates")
    if not isinstance(dates, list) or len(dates) != 5 or len(set(dates)) != 5:
        raise ArchiveError("ARCHIVE_PROBE_DATES_INVALID")
    endpoints = archive.get("probe_endpoints")
    expected = [
        "kospi_stock_daily",
        "kosdaq_stock_daily",
        "kospi_index_daily",
    ]
    if endpoints != expected:
        raise ArchiveError("ARCHIVE_PROBE_ENDPOINTS_CHANGED")
    return [
        make_archive_request(endpoint, str(day).replace("-", ""))
        for day in dates
        for endpoint in endpoints
    ]


def _probe_quality(
    config_path: Path,
    results: Iterable[ArchiveResult],
) -> dict[str, Any]:
    root, config, archive = _archive_config(config_path)
    mapping = load_u0_mapping(
        _resolve_from_root(root, config["collection"]["ticker_mapping_path"])
    )
    u0_codes = {row["ticker_code"] for row in mapping}
    raw_root = _resolve_from_root(root, config["collection"]["raw_root"])
    output: list[dict[str, Any]] = []
    for result in sorted(results, key=lambda item: (item.bas_dd, item.endpoint_id)):
        raw = gzip.decompress((raw_root / result.relative_path).read_bytes())
        payload = _decode_payload(raw)
        rows = payload.get("OutBlock_1", []) if isinstance(payload, dict) else []
        typed_rows = [row for row in rows if isinstance(row, dict)]
        requested_date_rows = [
            row for row in typed_rows if str(row.get("BAS_DD", "")) == result.bas_dd
        ]
        u0_rows = 0
        primary_kospi_rows = 0
        if result.endpoint_name in {"kospi_stock_daily", "kosdaq_stock_daily"}:
            u0_rows = sum(str(row.get("ISU_CD", "")) in u0_codes for row in typed_rows)
        elif result.endpoint_name == "kospi_index_daily":
            primary_kospi_rows = sum(
                _normalize_name(row.get("IDX_CLSS")) == "kospi"
                and _normalize_name(row.get("IDX_NM")) == _normalize_name("코스피")
                for row in typed_rows
            )
        output.append(
            {
                "bas_dd": result.bas_dd,
                "endpoint_name": result.endpoint_name,
                "http_status": result.http_status,
                "result_code": result.result_code,
                "row_count": result.row_count,
                "requested_date_row_count": len(requested_date_rows),
                "u0_row_count": u0_rows,
                "primary_kospi_row_count": primary_kospi_rows,
                "schema_hash": result.schema_hash,
            }
        )
    expected_count = len(_probe_requests(archive))
    pass_count = sum(
        row["http_status"] == 200
        and row["row_count"] > 0
        and row["requested_date_row_count"] == row["row_count"]
        and (
            row["u0_row_count"] > 0
            if row["endpoint_name"] != "kospi_index_daily"
            else row["primary_kospi_row_count"] == 1
        )
        for row in output
    )
    return {
        "status": "PASS" if pass_count == expected_count else "FAIL",
        "expected_checks": expected_count,
        "passed_checks": pass_count,
        "checks": output,
    }


def run_archive_probe(
    config_path: Path,
    protocol_path: Path | None = None,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    root, config, archive = _archive_config(config_path)
    if not execute:
        return {
            "mode": "archive-probe",
            "status": "READY_NOT_EXECUTED",
            "planned_requests": len(_probe_requests(archive)),
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    auth_key = os.environ.get("KRX_API_KEY", "").strip()
    if not auth_key:
        return {"mode": "archive-probe", "status": "BLOCKED_CREDENTIAL"}
    raw_root = _resolve_from_root(root, config["collection"]["raw_root"])
    state = ArchiveState(
        raw_root / str(archive["state_database"]),
        daily_budget=int(config["request_policy"]["configured_daily_request_budget"]),
        untracked_reserve=int(archive["untracked_request_reserve"]),
        acquire_run_lock=True,
    )
    try:
        results = [
            fetch_archive_request(
                item,
                auth_key=auth_key,
                raw_root=raw_root,
                state=state,
                timeout_seconds=int(config["request_policy"]["timeout_seconds"]),
                maximum_retries=int(config["request_policy"]["maximum_retries"]),
                retryable_http_statuses=config["request_policy"]["retryable_http_statuses"],
            )
            for item in _probe_requests(archive)
        ]
        quality = _probe_quality(config_path, results)
        status = build_archive_status(config_path, protocol_path)
        return {
            "mode": "archive-probe",
            "status": quality["status"],
            "network_requests_or_cache_hits": len(results),
            "probe_quality": quality,
            "archive_status": {
                "completed_records": status["completed_records"],
                "remaining_requests": status["remaining_requests"],
            },
        }
    finally:
        state.close()


def _run_archive_batch(
    items: list[ArchiveRequest],
    *,
    auth_key: str,
    raw_root: Path,
    state: ArchiveState,
    policy: Mapping[str, Any],
    maximum_parallel_connections: int,
    progress_every: int,
) -> tuple[list[ArchiveResult], list[dict[str, str]], bool]:
    completed: list[ArchiveResult] = []
    failures: list[dict[str, str]] = []
    quota_exhausted = False

    def submit_item(executor: ThreadPoolExecutor, item: ArchiveRequest) -> Future[ArchiveResult]:
        return executor.submit(
            fetch_archive_request,
            item,
            auth_key=auth_key,
            raw_root=raw_root,
            state=state,
            timeout_seconds=int(policy["timeout_seconds"]),
            maximum_retries=int(policy["maximum_retries"]),
            retryable_http_statuses=policy["retryable_http_statuses"],
        )

    with ThreadPoolExecutor(max_workers=maximum_parallel_connections) as executor:
        pending: dict[Future[ArchiveResult], ArchiveRequest] = {}
        iterator = iter(items)
        for _ in range(maximum_parallel_connections):
            try:
                item = next(iterator)
            except StopIteration:
                break
            pending[submit_item(executor, item)] = item
        while pending:
            future = next(as_completed(tuple(pending)))
            item = pending.pop(future)
            try:
                completed.append(future.result())
            except ArchiveQuotaExhausted:
                quota_exhausted = True
            except ArchiveError as exc:
                failures.append(
                    {
                        "request_id": item.request_id,
                        "endpoint_id": item.endpoint_id,
                        "bas_dd": item.bas_dd,
                        "reason": str(exc),
                    }
                )
            if progress_every > 0 and (len(completed) + len(failures)) % progress_every == 0:
                print(
                    json.dumps(
                        {
                            "archive_progress": len(completed),
                            "failures": len(failures),
                            "attempt_budget_remaining": state.remaining_attempt_budget(),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            if not quota_exhausted:
                try:
                    next_item = next(iterator)
                except StopIteration:
                    continue
                pending[submit_item(executor, next_item)] = next_item
    return completed, failures, quota_exhausted


def run_archive_collect(
    config_path: Path,
    protocol_path: Path | None = None,
    *,
    execute: bool = False,
    max_requests: int | None = None,
    progress_every: int = 250,
) -> dict[str, Any]:
    root, config, archive = _archive_config(config_path)
    if not execute:
        return {
            "mode": "archive-collect",
            "status": "READY_NOT_EXECUTED",
            "reason": "EXPLICIT_EXECUTE_ARCHIVE_FLAG_REQUIRED",
            "io": {"network_requests_performed": 0, "files_written": 0},
        }
    auth_key = os.environ.get("KRX_API_KEY", "").strip()
    if not auth_key:
        return {"mode": "archive-collect", "status": "BLOCKED_CREDENTIAL"}
    raw_root = _resolve_from_root(root, config["collection"]["raw_root"])
    state = ArchiveState(
        raw_root / str(archive["state_database"]),
        daily_budget=int(config["request_policy"]["configured_daily_request_budget"]),
        untracked_reserve=int(archive["untracked_request_reserve"]),
        acquire_run_lock=True,
    )
    try:
        all_requests = build_archive_requests(config_path, protocol_path)
        remaining = [
            item
            for item in all_requests
            if not (
                (record := state.completed_record(item.request_id))
                and _raw_file_valid(raw_root, record)
            )
        ]
        allowance = state.remaining_attempt_budget()
        request_cap = allowance
        if max_requests is not None:
            if max_requests < 1:
                raise ArchiveError("ARCHIVE_MAX_REQUESTS_INVALID")
            request_cap = min(request_cap, max_requests)
        selected = remaining[:request_cap]
        if not selected:
            status = build_archive_status(config_path, protocol_path)
            return {
                "mode": "archive-collect",
                "status": (
                    "COMPLETE"
                    if status["status"] == "COMPLETE"
                    else "PAUSED_DAILY_BUDGET"
                ),
                "archive_status": status,
                "batch": {"selected": 0, "completed": 0, "failures": 0},
            }
        completed, failures, quota_exhausted = _run_archive_batch(
            selected,
            auth_key=auth_key,
            raw_root=raw_root,
            state=state,
            policy=config["request_policy"],
            maximum_parallel_connections=int(
                config["request_policy"]["maximum_parallel_connections"]
            ),
            progress_every=progress_every,
        )
        status = build_archive_status(config_path, protocol_path)
        if status["status"] == "COMPLETE":
            final_status = "COMPLETE"
        elif quota_exhausted or state.remaining_attempt_budget() == 0:
            final_status = "PAUSED_DAILY_BUDGET"
        elif failures:
            final_status = "PARTIAL_WITH_FAILURES"
        else:
            final_status = "PARTIAL_BATCH_COMPLETE"
        return {
            "mode": "archive-collect",
            "status": final_status,
            "batch": {
                "selected": len(selected),
                "completed": len(completed),
                "failures": len(failures),
                "failure_sample": failures[:10],
            },
            "archive_status": status,
        }
    finally:
        state.close()


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Archive KRX V2.1 source responses locally without research derivations."
    )
    parser.add_argument("--config", default=root / "configs" / "v2_1_collection.yaml")
    parser.add_argument("--protocol", default=None)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("probe", "collect", "status"),
    )
    parser.add_argument("--execute-probe", action="store_true")
    parser.add_argument("--execute-archive", action="store_true")
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--write-public-summary", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path = Path(args.config).resolve()
    protocol_path = Path(args.protocol).resolve() if args.protocol else None
    try:
        if args.mode == "probe":
            result = run_archive_probe(
                config_path,
                protocol_path,
                execute=args.execute_probe,
            )
        elif args.mode == "collect":
            result = run_archive_collect(
                config_path,
                protocol_path,
                execute=args.execute_archive,
                max_requests=args.max_requests,
                progress_every=args.progress_every,
            )
        else:
            result = (
                write_public_archive_summary(config_path, protocol_path)
                if args.write_public_summary
                else build_archive_status(config_path, protocol_path)
            )
    except ArchiveError as exc:
        result = {"mode": f"archive-{args.mode}", "status": "ERROR", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] == "ERROR":
        raise SystemExit(1)
    if result["status"].startswith("BLOCKED"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
