# V2.1 데이터 가능성 시험

## 1. 목적과 금지 범위

이 문서는 V2.1 사전등록 프로토콜을 동결하기 전에 데이터 정의·관측 가능 시점·기업행사·산업지수 매핑을 검증한 기록이다. 최초 확인일은 2026-07-17이고, KRX 인증 기반 3차 확인일은 2026-07-20이다. 성능과 무관한 공식 schema 및 이용조건만 조사했다.

이번 시험에서는 V2.1 target 전체기간, Walk-forward prediction, MAE, RMSE, Rank IC, Hit Rate, OOS R² 및 백테스트를 생성하지 않았다. `results/v2_1/`도 생성하지 않았다. 키와 원자료는 저장하거나 출력하지 않았다.

## 2. 판정 요약

| 항목 | 상태 | 이번에 확인한 사실 | 남은 종료 증거 |
|---|---|---|---|
| UNRESOLVED-01 | `BLOCKED` | KRX `TDD_CLSPRC`, `FLUC_RT` schema와 타입 변환은 검증했으나 기업행사 조정 여부는 공식 근거가 없다 | KRX 가격 schema와 날짜순 최초 10건 이상의 공식 분할·병합·감자 대조에서 실패 0건 |
| UNRESOLVED-02 | `BLOCKED` | KRX Open API 약관의 24시간 이용 원칙은 일별 자료의 최초 공개시각을 뜻하지 않는다 | 공식 명세 또는 3거래일의 실제 timestamp 관측 |
| UNRESOLVED-03 | `OPEN` | ECOS 통계표 `731Y001`과 4개 항목의 코드·명칭·단위·방향·기간은 확인했다 | 공개시각과 수정 가능성에 대한 공식 근거 또는 timestamp 관측 |
| UNRESOLVED-04 | `BLOCKED` | 6개 legacy 산업에 대해 공식 문서에서 후보 지수명 존재만 확인했다 | 10개 지수코드와 공식 구성 정의를 포함한 사전 매핑 |
| UNRESOLVED-06 | `OPEN` | KRX 수신정보의 제3자 제공 제한을 확인했다 | KRX·ECOS 행 단위 파생 결과의 공개 허용 범위에 대한 기관별 명시 근거 |

이번 시험으로 완전히 `CLOSED`된 UNRESOLVED 항목은 없다. 따라서 프로토콜은 동결할 수 없다.

## 3. 인증 및 저장 통제

| 환경변수 | 상태 | 값 기록 |
|---|---|---|
| `KRX_API_KEY` | `SET` | 값은 기록하지 않음 |
| `ECOS_API_KEY` | `NOT_SET` | 없음 |

KRX와 ECOS의 운영용 키는 환경변수에서만 읽는다. KRX 키는 요청 header에 넣고, ECOS 키가 URL 경로에 들어가는 경우 로그에는 해당 segment를 `[REDACTED]`로 치환한다. 오류 로그에는 endpoint 식별자, HTTP 상태, 기관 result code, 요청시각, 응답 schema hash만 남긴다. 전체 URL, request header 및 응답 원문은 공개 로그에 쓰지 않는다.

원자료 저장 후보인 `data/feasibility_raw/`, `data/metadata/private/`, `data/metadata/api_logs/`와 `.env*`는 `.gitignore`에 추가했다. 공개 metadata에는 키 값이나 원자료 행이 없다.

### 3.1 데이터 가능성 시험 2차 실행

2026-07-17에 프로세스·사용자·시스템 환경을 다시 검사했으며 두 키 모두 `NOT_SET`이었다. 따라서 운영 API를 호출하지 않고 각 mode가 즉시 차단되는지만 검증했다.

| mode | 결과 | 네트워크·대기 |
|---|---|---|
| `metadata` | KRX·ECOS 모두 `BLOCKED_CREDENTIAL` | 없음 |
| `schema_sample` | `BLOCKED_CREDENTIAL` | 없음 |
| `corporate_actions` | 사건 0건, `BLOCKED_CREDENTIAL` | 없음 |
| `timestamp_once --source both` | 관측 0건, 양 기관 `BLOCKED_CREDENTIAL` | 없음, sleep 없음 |
| `audit` | `PASS` | 읽기 전용 |

재실행 인터페이스는 `python -m fx_research.v2_1_feasibility --config configs/v2_1_protocol.yaml --mode <mode>`로 구현했다. `timestamp_once`는 한 번만 조회하고 종료하며 스케줄러를 등록하지 않는다. 로그에는 endpoint ID, 시각, HTTP·기관 코드, 최신 기준일, header 존재 여부, schema hash와 `credential_redacted=true`만 허용한다.

### 3.2 데이터 가능성 시험 3차 실행 — 2026-07-20

KRX 인증키와 6개 서비스 승인을 확인한 뒤 `metadata`와 `schema_sample`만 실행했다. 키 값은 출력·문서화·커밋하지 않았다. ECOS, 기업행사, timestamp, U1 전체 종목 및 전체기간 가격 수집은 실행하지 않았다.

| 점검 | 결과 |
|---|---|
| U0 종목 식별 | 50/50, 실패 0, 비어 있지 않은 6자리 코드 중복 0 |
| HDC 명칭 변경 | 2025-12-30 `HDC현대산업개발`과 2026-06-30 `IPARK현대산업개발`이 코드 `294870`, ISIN `KR7294870001`로 동일함을 확인 |
| 고정 표본 | 2026-04-01~06-30, 5종목 각각 61행, 총 305행 |
| KOSPI | `IDX_CLSS=KOSPI`, `IDX_NM=코스피`인 주 지수 61행 |
| 중복·결측 | `(BAS_DD, ISU_CD)` 중복 0; 후보 5개 필드 결측 0 |
| 원시 자료형 | `TDD_CLSPRC`, `FLUC_RT`, `ACC_TRDVOL`, `ACC_TRDVAL`, `MKTCAP` 모두 문자열 |
| 숫자 변환 | 쉼표 제거 후 가격·등락률은 float, 거래량·거래대금·시가총액은 integer; 변환 실패 0 |

종목기본정보의 단축코드는 `ISU_SRT_CD`, ISIN은 `ISU_CD`다. 일별 시세의 6자리 단축코드는 `ISU_CD`다. 따라서 같은 필드명을 전역적으로 같은 의미로 해석하지 않고 API별 schema를 적용한다. 기존 `run_schema_sample`이 일별 시세에서 `ISU_SRT_CD`를 사용한 오류는 회귀 테스트와 함께 수정했다.

## 4. 공식 자료와 확인 범위

| 기관·자료 | 공식 근거 | 확인일/시행일 또는 schema 일자 | 확인 내용 |
|---|---|---|---|
| KRX Open API 서비스 목록 | [서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd) | 확인 2026-07-17 | KOSPI 지수·KOSPI/KOSDAQ 종목 일별매매·종목기본정보, 2010-01-04 이후 범위 |
| KRX Open API 이용방법 | [이용방법](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp) | 확인 2026-07-17 | 회원가입, 인증키, 서비스별 활용신청 구조 |
| KRX Open API 이용약관 | [약관](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp) | 시행 2025-12-26 | 비상업 이용, 출처표시, 수신정보 제3자 제공 제한, 키당 일 10,000회 |
| KRX KOSPI 종목 일별매매 | [서비스 페이지](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC) | 페이지 수정 2026-01-16 | `AUTH_KEY` 필요; 인증 없는 상태에서는 응답 필드표와 표본 응답 미확보 |
| KRX KOSPI 지수 일별시세 | [서비스 페이지](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN) | 페이지 수정 2026-01-16 | 공식 API ID `kospi_dd_trd`; `AUTH_KEY` 필요 |
| KRX 종가 분배상품 | [데이터 분배상품](https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp) | 확인 2026-07-17 | 종가 분배 1차 16:00·2차 18:10; Open API 공개시각으로 전용하지 않음 |
| 금융위원회 주식시세정보 | [공공데이터포털](https://www.data.go.kr/data/15094808/openapi.do) | 페이지 수정 2026-01-02 | 공식 필드와 익영업일 13:00 제공 일정 |
| 금융위원회 주식권리일정정보 | [공공데이터포털](https://www.data.go.kr/data/15059609/openapi.do) | 페이지 수정 2026-04-20 | 증자·주식교환·감자 등 후보 사건 자료, 익영업일 13:00 제공 일정 |
| 한국은행 ECOS | [Open API](https://ecos.bok.or.kr/api/) | 확인 2026-07-17 | 통계표·항목 metadata와 5개 날짜의 일별 행 확인 |
| 한국은행 저작권보호방침 | [저작권보호방침](https://www.bok.or.kr/portal/main/contents.do?menuNo=200228) | 확인 2026-07-17 | 공공데이터는 관련 절차·조건에 따라 이용; ECOS 행 단위 공개 범위를 이 문구만으로 추정하지 않음 |

## 5. A — KRX schema 가능성 시험

### 5.1 고정 표본

`constants.py`의 산업명을 사전순으로 정렬한 뒤 첫 5개 산업에서 각 산업의 첫 종목을 선택했다. 이 목록은 이후 결측률이나 응답 성공 여부로 바꾸지 않는다.

| 순서 | legacy 산업 | 고정 종목 |
|---:|---|---|
| 1 | 건설 | 현대건설 |
| 2 | 금융 | KB금융 |
| 3 | 미디어_엔터 | CJ ENM |
| 4 | 바이오_제약 | 셀트리온 |
| 5 | 반도체 | SK하이닉스 |

2026-07-20 KRX 종목기본정보 응답으로 U0 50종목의 단축코드, ISIN, 시장과 상장일을 확인했다. 49종목은 현재 공식 명칭과 정확히 대응했고, `HDC현대산업개발` 1종목은 명칭 변경 전후에 동일한 코드 `294870`과 ISIN `KR7294870001`이 유지된 공식 응답 provenance로 연결했다. 문자열 유사도는 사용하지 않았다. 최종 매핑은 50/50, 실패 0, 비어 있지 않은 단축코드 중복 0이다.

공식 서비스 목록과 상세 페이지 원문에서 KOSPI 일별매매 `stk_bydd_trd`, KOSDAQ 일별매매 `ksq_bydd_trd`, KOSPI 종목기본정보 `stk_isu_base_info`, KOSDAQ 종목기본정보 `ksq_isu_base_info`, KRX 지수 `krx_dd_trd`, KOSPI 지수 `kospi_dd_trd` API ID와 sample URL 구성을 확인했다. 기존 source registry의 종목기본정보 상세화면 경로가 `_S4`로 잘못 기록돼 있던 것을 공식 `_S2` 경로로 수정했다. 인증 없는 운영 endpoint 시험은 HTTP 401이었으며 응답 원문은 저장하지 않았다.

종목 매핑 CSV 순서는 `constants.py`의 dict 삽입 순서로 바로잡았다. 고정 5종목 표시는 변경하지 않았다.

### 5.2 KRX 일별 시세 후보 필드

KRX 실제 응답에서 아래 필드를 확인했다. 2026-04-01~06-30 고정 표본의 원시값은 모두 문자열이었고, 공개 파일에는 원시값을 복제하지 않았다. 필드의 schema·단위·숫자 변환 가능성만 확인했으며 수익률이나 기업행사 조정 여부는 확정하지 않았다.

| KRX 필드 | 변환형 | 단위 | 결측 | 변환 실패 | 기업행사 조정 |
|---|---|---:|---:|---:|---|
| `TDD_CLSPRC` | float | KRW | 0/305 | 0 | `UNRESOLVED-01` |
| `FLUC_RT` | float | % | 0/305 | 0 | `UNRESOLVED-01`; 수익률로 미확정 |
| `ACC_TRDVOL` | integer | 주 | 0/305 | 0 | 해당 없음 |
| `ACC_TRDVAL` | integer | KRW | 0/305 | 0 | 해당 없음 |
| `MKTCAP` | integer | KRW | 0/305 | 0 | 해당 없음 |

빈 문자열과 `-`는 NaN으로, 그 밖의 비정상 문자열은 NaN으로 바꾸고 변환 실패로 집계한다. 쉼표는 제거한다. 변환 전 원본값은 공개 결과 파일에 복제하지 않는다.

아래 금융위원회 필드는 KRX 주 자료를 대체하도록 채택한 것이 아니라 공식 대체 API의 과거 조사 기록이다.

| 공식 필드 | 자료형 | 단위 | 공식 의미 | 기업행사 조정 | 표본 결측률 | 중복 key | 날짜 범위 | `forecast_as_of` 이전 이용 |
|---|---|---|---|---|---|---|---|---|
| `clpr` | string | 원 | 종가 | 명세 없음 | `BLOCKED_CREDENTIAL` | `BLOCKED_CREDENTIAL` | 2020-01-01 이후 | 불가: 익영업일 13:00 |
| `fltRt` | number | % | 등락률 | 명세 없음 | `BLOCKED_CREDENTIAL` | `BLOCKED_CREDENTIAL` | 2020-01-01 이후 | 불가: 익영업일 13:00 |
| `trqu` | number | 주 | 거래량 | 해당 없음 | `BLOCKED_CREDENTIAL` | `BLOCKED_CREDENTIAL` | 2020-01-01 이후 | 불가: 익영업일 13:00 |
| `trPrc` | number | 원 | 거래대금 | 해당 없음 | `BLOCKED_CREDENTIAL` | `BLOCKED_CREDENTIAL` | 2020-01-01 이후 | 불가: 익영업일 13:00 |
| `mrktTotAmt` | number | 원 | 시가총액 | 명세 없음 | `BLOCKED_CREDENTIAL` | `BLOCKED_CREDENTIAL` | 2020-01-01 이후 | 불가: 익영업일 13:00 |

`fltRt`의 분모·반올림·기업행사 조정 정의가 공식 schema에 명시되지 않았으므로 이를 주 일수익률로 채택하지 않는다. 금융위원회 API는 현재의 동일월말 18:30 cutoff와 양립하지 않으므로, 사용하려면 프로토콜 규칙대로 한 달 lag가 필요하다.

## 6. B — 기업행사 검증

공식 주식권리일정 API와 KRX 가격 API 모두 인증이 필요한 상태라 사건을 가져오지 않았다. 날짜순 최초 10건 규칙을 지키기 위해 비공식 검색 결과나 기억으로 사건을 채우지 않았고, [기업행사 감사 파일](../data/metadata/v2_1_corporate_action_audit.csv)에는 header와 차단 사유만 기록했다.

추가로 KRX Open API 공식 서비스 목록에는 분할·병합·감자의 사건 모집단을 제공하는 기업행사 API가 확인되지 않았다. KRX 데이터 분배상품은 종목이벤트를 별도 정보상품으로 설명한다. 따라서 `KRX_API_KEY`만 설정돼도 기업행사 mode를 자동 종료하지 않으며, 공식 사건 endpoint 또는 기관 제공 파일과 그 이용조건이 source registry에 등록될 때까지 `BLOCKED_OFFICIAL_SOURCE_ENDPOINT`를 적용한다.

따라서 사건 전후 `clpr`, `fltRt`, 조정계수, 절대 일수익률 20% 초과 여부 및 후보 필드별 실패 건수는 산출할 수 없다. 실패 0건인 필드가 아직 없으므로 UNRESOLVED-01은 `BLOCKED`이다.

## 7. C — 공개 시각 검증

KRX 약관의 “24시간 이용”은 API 운영시간 원칙이며 특정 기준일 자료가 최초로 나타나는 시각의 증거가 아니다. 공개 서비스 페이지에도 일별 자료의 최초 제공시각이 없고, 현재 응답 header로 과거 공개시각을 추정하지 않았다.

인증 후 다음 절차를 고정한다.

1. 연속된 보통 KRX 거래일 3일을 선택한다. 장애·임시휴장일은 대체하되 삭제 이유를 로그에 남긴다.
2. 각 날 KOSPI 종목 일별매매와 KOSPI 지수 일별매매를 15:40, 16:00, 16:30, 17:00, 17:30, 18:00, 18:30, 20:00, 23:30 KST에 각각 한 번 조회한다.
3. 요청 UTC·KST, HTTP 상태, 기관 result code, 최신 기준일, 응답 header의 `Date` 존재 여부, 정제된 schema hash를 기록한다. 키와 원문은 기록하지 않는다.
4. 세 거래일 모두 당일 기준일 자료가 18:30까지 나타날 때만 같은 달 feature로 허용한다.
5. 한 번이라도 18:30을 넘기거나 결과가 불명확하면 월말 자료에 한 달 lag를 적용한다.

이번 실행에서는 3거래일 관측을 수행하지 않았으므로 UNRESOLVED-02는 `BLOCKED`이다.

2차 실행의 `timestamp_once`는 두 키가 없어 관측행을 만들지 않았다. 누적 유효 거래일과 관측 레코드는 모두 0이다.

## 8. D — ECOS 환율 검증

공개 `sample` metadata API로 다음 계열을 확인했다. 2026-07-17 05:59:30 UTC(14:59:30 KST)에 metadata endpoint가 HTTP 200을 반환했고 응답 `Date` header가 있었지만, 이는 각 통계값의 최초 공개시각 증거가 아니다.

| pair | 통계표 | 항목 | 공식 명칭 | 주기 | 단위·방향 | 의미 | 최초일 | 확인 당시 최종일 |
|---|---|---|---|---|---|---|---|---|
| USD/KRW | `731Y001` | `0000001` | 원/미국달러(매매기준율) | D | 1 USD당 원 | 매매기준율 | 1964-05-04 | 2026-07-16 |
| EUR/KRW | `731Y001` | `0000003` | 원/유로 | D | 1 EUR당 원 | 공식 명칭은 종가·평균을 별도 표기하지 않음 | 1994-04-11 | 2026-07-16 |
| JPY/KRW | `731Y001` | `0000002` | 원/일본엔(100엔) | D | 100 JPY당 원 | 공식 명칭은 종가·평균을 별도 표기하지 않음 | 1977-04-01 | 2026-07-16 |
| CNY/KRW | `731Y001` | `0000053` | 원/위안(매매기준율) | D | 1 CNY당 원 | 매매기준율 | 2016-01-04 | 2026-07-16 |

USD/KRW 주 계열은 공식 명칭이 정의를 명시한 `731Y001/0000001`로 추천한다. JPY는 100엔 단위이지만 로그차분은 고정 배율 100의 영향을 받지 않는다. CNY는 2016-01-04부터만 존재하므로 보조 민감도 분석의 가용기간이 짧아진다. 이를 이유로 계열을 교체하지 않는다.

2026-07-01, 02, 03, 06, 07의 서로 다른 5개 날짜를 `StatisticSearch`와 metadata에서 대조했다. 네 항목 모두 표 코드·항목 코드·명칭·단위·날짜가 5/5 일치했으며 값은 공개 파일에 저장하지 않았다.

공식 metadata만으로는 수정 가능 여부와 공개시각을 확정할 수 없다. ECOS도 연속된 KRX 거래일 3일 동안 16:00, 17:00, 18:00, 18:30, 20:00, 23:30 KST 및 익일 09:00 KST에 USD 항목의 최신 `TIME`을 기록한다. 세 날 모두 당일 값이 18:30까지 보일 때만 same-day 이용을 허용하며, 그렇지 않으면 한 달 lag를 적용한다. 일별 β에서는 휴일을 보간하지 않고 FX와 주식시장에 동시에 존재하는 날짜만 inner join한다.

따라서 계열 코드·단위·방향은 확정 가능하지만 UNRESOLVED-03 전체는 공개시각과 수정정책 때문에 `OPEN`이다.

## 9. E — KRX 산업지수 사전 매핑

수익률 상관과 예측성능은 사용하지 않았다. 공식 KRX 지수 자료와 공시에서 `KRX 건설`, `KRX 은행`, `KRX 반도체`, `KRX 에너지화학`, `KRX 헬스케어`, `KRX 미디어&엔터테인먼트`의 명칭 존재만 확인했다. 현재 구성 정의와 지수코드를 확보하지 못했으므로 이 사실만으로 `exact` 또는 `partial`을 부여하지 않았다.

[산업지수 매핑표](../data/metadata/v2_1_krx_index_mapping.csv)의 10행은 모두 `unavailable`이다. `exact + partial = 0 < 8`이므로 KRX 산업지수 민감도 분석 전체를 현재 제외한다. 이는 영구 제외가 아니라 UNRESOLVED-04가 닫히기 전의 사전 gate 판정이다.

## 10. F — 이용조건과 공개 범위

| 파일 또는 정보 | Git 허용 | 근거·조건 |
|---|---|---|
| 코드, 프로토콜, schema 설명, source URL, 확인일 | 예 | 원자료 행과 키를 포함하지 않음 |
| 이 문서의 ECOS 통계표·항목 metadata | 예 | 공식 분류 metadata와 출처만 기록 |
| legacy 종목명·공식 코드·ISIN·시장·상장일·검증 provenance | 예 | 원시 시세행이 아닌 식별 metadata만 기록; 명칭 변경은 동일 코드와 ISIN으로 검증 |
| KRX 원응답과 수신정보 행 | 아니오 | KRX 약관의 제3자 제공 제한 및 원자료 비커밋 원칙 |
| 금융위원회 API 원응답 | 아니오 | 이번 연구의 원자료 비커밋 원칙; 개별 dataset 약관도 수집 시 다시 보존 |
| ECOS 원자료 행 | 아니오 | 연구 원자료 비커밋 원칙 |
| 종목별 β, 산업별 실제수익률, V2.1 예측행 | `UNRESOLVED_06` | 원자료가 아니어도 공개 허용 범위를 추정하지 않음 |
| 허용 범위가 확인된 집계 성능표 | 조건부 | V2.1 실행·공개 gate를 통과한 이후에만 생성 |
| 인증키, `.env`, 전체 request URL·header | 아니오 | 환경변수 전용, 로그 redaction 필수 |

KRX와 ECOS의 행 단위 파생 결과 공개 허용 범위는 공식 약관 조항 또는 기관 답변 전까지 UNRESOLVED-06으로 유지한다.

## 11. 품질 점검 결과

| 점검 | 결과 |
|---|---|
| 공개 파일에 인증키 값 없음 | 통과 |
| 원자료·private mapping·request log 경로 `.gitignore` 포함 | 통과 |
| legacy 종목 행 수 | 50 |
| `constants.py` 순서 보존·고정 5종목 불변 | 통과 |
| 공식 종목코드 매핑 실패 | 0 (50/50 식별) |
| 확인된 비어 있지 않은 종목코드 중복 | 0 |
| 고정 5종목 일별 시세 | 각 61행, 총 305행 |
| KOSPI 주 지수 | 61행 |
| 후보 5필드 결측·숫자 변환 실패 | 모두 0 |
| ECOS 날짜·단위·방향 수동 대조 | 통과: 5개 날짜·4항목 |
| 공식 기업행사 10건 | 차단: 사건을 꾸미지 않음 |
| `results/v2_1/` 생성 | 없음 |
| target·prediction·성능 생성 | 없음 |
| protocol 상태 | `DRAFT_NOT_FROZEN` 유지 |
| 전체 단위 테스트 | 16개 통과(그중 feasibility 12개) |
| feasibility `audit` mode | 통과 |
| timestamp 누적 | 0거래일·0레코드 |

## 12. 결론

V2.1의 주 표본은 U0 Legacy-50으로 유지한다. U1 Expanded-10은 현재 채택하지 않으며, 과거 시점별 10개 업종 소속, 상장폐지·합병·분할·코드 변경 계보 및 기업행사 조정 수익률 경로를 공식 자료로 확보한 뒤 V2.2 후보로 다시 평가한다. `SECT_TP_NM`은 공식 산업분류로 확인되지 않았으므로 사용하지 않는다.

채택 가능한 KRX 결정은 U0 50종목 식별, API별 종목코드 필드, 다섯 후보 필드의 명시적 숫자 변환 규칙이다. `TDD_CLSPRC`와 `FLUC_RT`의 기업행사 조정 방식은 미확정이므로 일별 연구 수익률은 아직 채택할 수 없다. ECOS 주 환율 후보 `731Y001/0000001`의 코드·명칭·단위·방향은 기존 확인을 유지한다.

프로토콜은 아직 동결할 수 없다. 다음 단계로 넘어가기 위한 단 하나의 권고는 **KRX 문의 초안을 발송해 기업행사 조정·과거 구성·산업분류·영구 식별·파생 통계 공개 범위의 공식 답변을 확보하고, 별도로 정상 거래일 3일의 공개시각 관측을 완료하는 것**이다.
