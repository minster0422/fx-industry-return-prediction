# V2.1 U0 데이터 수집 계획

## 상태

- 작성일: 2026-07-20
- archive 완료일: 2026-07-28
- 대상: `U0_LEGACY_50`과 KOSPI
- 프로토콜: `DRAFT_NOT_FROZEN`
- 연구용 전체수집: `BLOCKED`
- 파생 없는 KRX archive-only: `COMPLETE`
- 수익률·target·model·prediction·performance: 생성 금지

이 문서는 전체 데이터를 받기 전에 API 요청량, 저장 구조, 재시작 규칙과 실행 gate를 고정했다. 숫자는 수익률이나 예측결과를 사용하지 않은 공학적 계획치다. 이후 별도의 archive-only 경로로 원응답만 보존했으며 연구용 변환과 `collect` gate는 그대로 차단했다.

## archive-only 완료 결과

| 항목 | 계획 | 완료 |
|---|---:|---:|
| KRX 요청 | 12,908 | 12,908 |
| 유효 gzip 원본 | 12,908 | 12,908 |
| 남은 요청 | 0 | 0 |
| 총 행 수 | 계획하지 않음 | 9,301,468 |
| 비압축 bytes | 6,066,748,000 추정 | 2,961,927,978 |
| gzip bytes | 2,123,361,800 추정 | 535,466,270 |

계획치와 실측치의 차이는 기간·표본·필드·연구모형 변경에 사용하지 않았다. 상세 endpoint 집계, 일별 시도 수와 무결성 해시는 [`V2_1_ARCHIVE_REPORT.md`](V2_1_ARCHIVE_REPORT.md)에 보존한다.

## 계획치

| 항목 | 고정 계획치 |
|---|---:|
| 기간 | 2010-01-04~2026-06-30 |
| U0 종목 | 50개: KOSPI 45, KOSDAQ 5 |
| 월~금 후보일 | 4,302일 |
| 종목기본정보 요청 | 2회 |
| KOSPI 일별매매 요청 상한 | 4,302회 |
| KOSDAQ 일별매매 요청 상한 | 4,302회 |
| KOSPI 지수 요청 상한 | 4,302회 |
| KRX 총 요청 상한 | 12,908회 |
| U0 필터 후 종목-평일 행 상한 | 187,250행 |
| KOSPI 주 지수 행 상한 | 4,302행 |
| ECOS 4계열 평일 행 상한 | 17,208행 |
| 원시 응답 비압축 추정 | 6,066,748,000 bytes |
| gzip 원시 응답 추정 | 2,123,361,800 bytes |
| manifest·U0 정규화 후보 포함 KRX 합계 | 2,158,485,000 bytes, 약 2.16GB |

4,302일은 공식 거래일 수가 아니라 월요일부터 금요일까지의 상한이다. 저장량은 KOSPI 1,000행, KOSDAQ 1,900행, KOSPI 지수 60행/응답과 gzip 비율 0.35를 가정한 KRX 전용 값이다. 실제 행 수와 저장량은 달라지며 이 차이를 이유로 기간·표본·모델을 바꾸지 않는다.

ECOS는 `731Y001`의 USD `0000001`, EUR `0000003`, JPY `0000002`, CNY `0000053`을 계획에 유지한다. 네 계열의 평일 행 상한은 17,208행이다. 공식 pagination, 공개시각과 수정정책이 UNRESOLVED-03이므로 ECOS API 호출 수와 원시 저장량은 임의로 정하지 않으며 위 12,908회·2.16GB에 포함하지 않는다.

KRX 일별 API는 종목별 요청이 아니라 시장·기준일별 응답이다. 따라서 U0가 50종목이어도 주식 일별 요청 수는 `종목 수 × 날짜 수`가 아니라 `2개 시장 × 날짜 수`다. 응답을 로컬 원자료로 보존한 뒤 U0 6자리 코드만 별도 처리하는 구조를 전제로 한다.

## API별 schema

| endpoint | API ID | 시장 | 단축코드 | ISIN | 요청 범위 |
|---|---|---|---|---|---|
| `kospi_stock_basic` | `stk_isu_base_info` | KOSPI | `ISU_SRT_CD` | `ISU_CD` | 종료일 snapshot 1회 |
| `kosdaq_stock_basic` | `ksq_isu_base_info` | KOSDAQ | `ISU_SRT_CD` | `ISU_CD` | 종료일 snapshot 1회 |
| `kospi_stock_daily` | `stk_bydd_trd` | KOSPI | `ISU_CD` | 없음 | 평일 후보일별 1회 |
| `kosdaq_stock_daily` | `ksq_bydd_trd` | KOSDAQ | `ISU_CD` | 없음 | 평일 후보일별 1회 |
| `kospi_index_daily` | `kospi_dd_trd` | KOSPI 지수 | 해당 없음 | 해당 없음 | 평일 후보일별 1회 |

같은 `ISU_CD`가 종목기본정보에서는 ISIN, 일별 시세에서는 6자리 단축코드를 뜻하므로 endpoint schema 밖에서 전역 의미를 부여하지 않는다.

## 요청 정책

| 설정 | 값 |
|---|---:|
| HTTP timeout | 30초 |
| 최대 재시도 | 3회 |
| backoff | 1초 → 2초 → 4초, 상한 8초 |
| 동시 연결 | 4개 |
| KRX 공식 일일 한도 | 10,000회 |
| 연구 수집 일일 예산 | 9,000회, 한도의 90% |
| archive 미추적 요청 reserve | 250회 |
| archive 실행 가능 예산 | 8,750회 |
| retry HTTP | 408, 429, 500, 502, 503, 504 |
| 기관 result code 재시도 | 없음; 공식 코드가 별도 등록되기 전 자동 재시도 금지 |

총 요청 상한은 9,000회 예산 기준 최소 2개의 실제 실행일로 나눈다. 정렬은 `basDd` 오름차순 후 endpoint ID 순서다. `sha256(endpoint_id|basDd|market)`를 resume key로 사용한다.

## 저장·재시작 구조

```text
data/raw/v2_1/
├── krx/stock_basic/
├── krx/stock_daily/
├── krx/index_daily/
├── ecos/fx_daily/
├── manifests/
└── checkpoints/
```

모든 경로는 Git에서 제외한다. 파일은 `.tmp`에 완전히 기록하고 `os.replace`로 최종 경로에 원자적으로 이동한다. checkpoint에는 request ID, endpoint ID, 기준일, 시장, SHA-256, schema hash, 행 수, 재시도 횟수와 완료시각만 허용한다. 같은 request ID와 SHA-256은 쓰지 않고 완료로 재사용하며, 같은 request ID에 다른 SHA-256이 나타나면 충돌로 중단한다.

## 실행 모드

```powershell
python -m fx_research.v2_1_collection --mode plan
python -m fx_research.v2_1_collection --mode dry-run
python -m fx_research.v2_1_collection --mode schema-sample
python -m fx_research.v2_1_collection --mode collect
python -m fx_research.v2_1_archive --mode status
```

- `plan`: 네트워크와 파일 쓰기 없이 요청·행·저장량 상한 출력
- `dry-run`: U0·기간·guard·경로를 검증하되 네트워크와 파일 쓰기 없음
- `schema-sample`: 기본적으로 `READY_NOT_EXECUTED`; 명시적 `--execute-schema-sample`에서만 기존 고정 5종목·3개월 feasibility에 위임
- `collect`: 현재 `BLOCKED_PROTOCOL_NOT_FROZEN`. 프로토콜을 임의로 FROZEN으로 바꾸더라도 설정 enable, frozen manifest 해시와 별도 실행 승인이 모두 없으면 차단
- `v2_1_archive`: 연구 파생 기능을 모두 끈 별도 local-only 보존 경로. 2026-07-28 `COMPLETE`; 이후 기본 명령은 상태·해시 확인만 수행

## 전체수집 해제 조건

현재 연구용 scaffold는 다음 조건을 모두 확인하도록 구현했으나 마지막 실행은 의도적으로 허가하지 않는다. archive-only 완료는 이 조건을 우회하거나 종료하지 않는다.

1. `results/v2_1/` 부재
2. U0 50종목 공식 매핑·순서·중복 검증 통과
3. `UNRESOLVED-01~04` 종료 후 프로토콜 `FROZEN`
4. `full_collect_enabled: true`에 대한 별도 검토
5. 프로토콜·수집설정·종목매핑 SHA-256을 담은 frozen manifest
6. 공식 기업행사 조정 규칙과 공개시각 lag 규칙 반영
7. 사용자 별도 승인과 수집 실행 코드 검토

지금 단계에서 가능한 다음 외부 작업은 KRX 문의 답변 확보, KRX·ECOS 3거래일 공개시각 관측과 ECOS 운영키 준비다. archive-only 단계에서는 KRX 원자료 파일만 로컬에 생성했다. 수익률, target, 모델, 예측, 성능 및 `results/v2_1/`은 생성하지 않았다.
