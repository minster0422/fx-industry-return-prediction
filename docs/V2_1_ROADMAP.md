# V2.1 실행 로드맵

## 목적

V2.1은 24개월 proof-of-concept의 숫자를 조금 개선하는 작업이 아니다. 결과를 보기 전에 데이터·변수·모델·평가·성공 기준을 고정하고 다음 질문을 검증하는 후속 재구성 연구다.

> 과거 정보만으로 추정한 종목·산업의 환율 노출 상태와 산업 간 시차 네트워크가 단순 기준모형보다 다음 달 산업 초과수익률 예측을 개선하는가?

세부 연구 정의의 유일한 기준은 [`V2_1_PROTOCOL.md`](V2_1_PROTOCOL.md)와 [`../configs/v2_1_protocol.yaml`](../configs/v2_1_protocol.yaml)이다. 이 로드맵은 실행 순서와 gate만 설명하며 프로토콜과 충돌할 경우 프로토콜을 우선한다.

## 현재 상태 — 2026-07-17

상태는 `DRAFT_NOT_FROZEN`이다. V2.1 전체 target, 모델, Walk-forward 예측, 성능, 백테스트는 생성하지 않았다.

### 완료

- V2.1 사전등록 프로토콜과 기계 판독 YAML 초안
- 주 분석·민감도·성공·실패·판단보류 규칙 분리
- 데이터 사전과 결정 로그
- KRX·ECOS·공공데이터포털 공식 source registry
- 기존 10산업·50종목 보존 및 고정 5종목 schema 표본 규칙
- credential-safe feasibility CLI와 단위 테스트
- 원자료·인증키·private metadata·API log의 Git 제외
- ECOS 통계표 `731Y001`과 4개 환율 항목 metadata 확인
- 공식 KRX API ID 6개 확인

### 승인 대기

- `KRX_API_KEY` 발급
- 아래 KRX 서비스 활용승인
  - `stk_bydd_trd`
  - `ksq_bydd_trd`
  - `stk_isu_base_info`
  - `ksq_isu_base_info`
  - `krx_dd_trd`
  - `kospi_dd_trd`
- 운영용 `ECOS_API_KEY`
- 분할·병합·감자 사건 모집단을 제공하는 공식 endpoint 또는 기관 파일

키 값은 환경변수에서만 읽고 문서·명령행·로그·Git 파일에 기록하지 않는다.

## 동결 차단 상태

| 항목 | 현재 상태 | 종료 조건 |
|---|---|---|
| UNRESOLVED-01 | `BLOCKED` | 공식 분할·병합·감자 최초 10건에서 가격·수익률 후보 필드 실패 0건 |
| UNRESOLVED-02 | `BLOCKED` | KRX 일별 자료가 18:30 이전 이용 가능한지 정상 거래일 3일 관측 |
| UNRESOLVED-03 | `OPEN` | ECOS 공개시각·수정정책 확인; 계열 코드·단위·방향은 확인 완료 |
| UNRESOLVED-04 | `BLOCKED` | 10산업의 공식 지수 검색·코드·구성 정의와 exact/partial/unavailable 판정 |
| UNRESOLVED-05 | `OPEN, non-blocking` | 미해결이면 외국인 수급 민감도 분석 제외 |
| UNRESOLVED-06 | `OPEN, release-blocking` | 행 단위 파생 결과의 공개 허용 범위 확인 |

## 단계별 실행 계획

### Gate 1 — 인증 기반 metadata

환경변수가 Codex 프로세스에서 `SET`인지만 확인한 뒤 실행한다.

```powershell
python -m fx_research.v2_1_feasibility `
  --config configs/v2_1_protocol.yaml `
  --mode metadata
```

종료 조건:

- 50종목 공식 코드·ISIN·시장·상장일 매핑
- 비어 있지 않은 종목코드 중복 0
- 고정 5종목 불변
- ECOS 4개 항목과 고정 5개 날짜 운영 endpoint 재검증
- KRX 지수 후보 코드 확인

### Gate 2 — 제한 schema·기업행사 시험

고정 5종목의 공식 매핑이 완료된 경우에만 최대 3개월 schema 표본을 실행한다.

```powershell
python -m fx_research.v2_1_feasibility `
  --config configs/v2_1_protocol.yaml `
  --mode schema_sample
```

공식 기업행사 source가 등록된 경우에만 기업행사 시험을 실행한다.

```powershell
python -m fx_research.v2_1_feasibility `
  --config configs/v2_1_protocol.yaml `
  --mode corporate_actions
```

종료 조건:

- 가격·등락률·거래량·거래대금·시가총액 schema와 단위 확인
- 표본의 결측률·중복 key·날짜 범위 기록
- 공식 사건을 정해진 정렬 규칙으로 선택한 최초 10건 검증
- 기업행사 설명이 안 되는 절대 일수익률 20% 초과 실패 0건인 필드만 추천

### Gate 3 — 공개시각 3거래일 관측

각 예약시각에는 한 번만 실행한다. CLI는 sleep하거나 스케줄러를 자동 등록하지 않는다.

```powershell
python -m fx_research.v2_1_feasibility `
  --config configs/v2_1_protocol.yaml `
  --mode timestamp_once `
  --source both
```

종료 조건:

- 서로 다른 정상 KRX 거래일 3일
- KRX와 ECOS의 실제 요청 UTC·KST, 최신 기준일, HTTP·기관 코드, schema hash 기록
- 세 날 모두 18:30 이전 당일 자료가 있으면 same-day 사용
- 한 날이라도 늦거나 불명확하면 프로토콜에 따라 한 달 lag

### Gate 4 — 프로토콜 동결

UNRESOLVED-01~04가 모두 닫힌 뒤에만 수행한다.

1. 문서·YAML 결론 일치 감사
2. 프로토콜과 설정 SHA-256 기록
3. 버전과 `status: FROZEN` 변경
4. 동결 commit ID를 결정 로그에 기록
5. 동결 이후 결과 생성 전에는 오류 수정만 허용

### Gate 5 — 전체 데이터 수집과 품질 보고

동결 전에는 진입하지 않는다.

- 2010-01-04부터 최신 완결 월까지 공식 원자료 수집
- 원자료는 Git 제외 로컬 경로에 저장
- source URL·요청일·schema·행 수·SHA-256 manifest 생성
- 상장 전·상장폐지 후·거래정지·기업행사·결측 처리
- 분석 시작월을 사전 규칙으로 기계 결정

이 단계에서는 아직 모델 성능으로 source·기간·필드를 바꾸지 않는다.

### Gate 6 — V2.1 파이프라인 구현

- rolling 환율 β와 HAC 표준오차
- 월별 군집 구성·안정성
- 연속형 시차 네트워크와 FDR
- M0~M4 Walk-forward
- 내부 시계열 검증과 누수 테스트
- 같은 seed·환경의 재현성 테스트

### Gate 7 — 사전등록 분석 1회 실행

- 주 분석을 먼저 실행하고 원래 결과를 보존
- 민감도 분석은 정해진 순서대로 한 번에 한 요소만 변경
- 네트워크가 기준모형을 이기지 못해도 `증분가치 미확인`으로 공개
- 표본 gate 미달은 `표본 부족으로 판단보류`로 공개

### Gate 8 — 공개 릴리스

UNRESOLVED-06에 따라 공개 가능한 파일만 Git에 포함한다. 행 단위 종목 β, 산업 실제수익률, 예측행의 권한이 불명확하면 로컬 생성으로 제한하고 코드·schema·허용된 집계 결과만 공개한다.

## 품질 명령

```powershell
python -m unittest discover -s tests -v
python -m fx_research.v2_1_feasibility `
  --config configs/v2_1_protocol.yaml `
  --mode audit
```

현재 milestone의 완료 기준은 높은 성능이 아니라 다음 세 가지다.

1. 결과를 보기 전에 연구 선택을 고정했다.
2. 공식 근거가 없는 사항을 `UNRESOLVED`로 남겼다.
3. 승인 후 같은 제한 명령으로 데이터 가능성 검증을 이어갈 수 있다.
