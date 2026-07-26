# Data contract

## 공개된 파일

`reference/`에는 2025 발표자료에 사용된 소형 파생표만 UTF-8 CSV로 보존한다.

- `sector_binary_2025.csv`: 24개월 × 10산업 상승 여부
- `association_rules_reported.csv`: 당시 보고된 10개 연관규칙
- `published_metrics.csv`: 최종 PPT의 최근 6개월 RMSE·Hit Rate

이 파일들은 과거 결과를 재현하기 위한 기준자료이며, 정확한 값이라고 보증하는 수정본이 아니다.

`metadata/`에는 V2.1의 공개 가능한 출처·schema·식별 metadata만 둔다. `v2_1_ticker_mapping.csv`는 U0 Legacy-50의 KRX 단축코드와 ISIN을 기록하고, `v2_1_ticker_identity_provenance.csv`는 HDC/IPARK현대산업개발 명칭 변경을 동일 코드·ISIN으로 확인한 근거만 기록한다. 종목명 유사도는 자동 매칭 근거로 사용하지 않는다.

KRX 종목기본정보에서 단축코드는 `ISU_SRT_CD`, ISIN은 `ISU_CD`다. KRX 일별 시세에서는 6자리 단축코드가 `ISU_CD`로 반환되므로 API별 schema를 구분한다. 공개 metadata에는 일별 시세 원시행이나 인증키 값이 포함되지 않는다.

## 로컬 원시 데이터

`raw/merged_50stocks_fx_multi.csv`는 Git에서 제외된다. 필요한 열은 다음과 같다.

| 열 | 의미 |
|---|---|
| `종목` | 종목명 |
| `일자` | 거래일 |
| `ret` | 일간 종목 수익률 |
| `fore_chg` | 외국인 지분율 변화 |
| `USD_ret` | 원/달러 환율 변화율 |
| `EUR_ret` | 원/유로 환율 변화율 |
| `JPY100_ret` | 원/100엔 환율 변화율 |
| `CNY_ret` | 원/위안 환율 변화율 |

프로그램은 UTF-8, UTF-8 BOM, CP949를 순서대로 시도하고 종목명 앞뒤 공백을 제거한다. 원시 데이터의 출처와 재배포 권한이 확인되기 전에는 공개 커밋하지 않는다.

## V2.1 로컬 수집 구조

V2.1 수집기 골격은 아래 경로를 사용하도록 고정했으며 전체 경로가 Git에서 제외된다.

```text
data/raw/v2_1/
├── krx/
│   ├── stock_basic/
│   ├── stock_daily/
│   └── index_daily/
├── ecos/
│   └── fx_daily/
├── manifests/
└── checkpoints/
```

원시 응답은 endpoint·시장·기준일 단위로 분리하고, 임시 파일을 완전히 쓴 뒤 원자적으로 최종 파일명으로 이동한다. manifest에는 SHA-256, schema hash, 행 수, 수집시각과 정제된 상태만 기록한다. checkpoint에는 인증키·URL·header·원시값을 넣지 않는다. 현재 프로토콜이 `DRAFT_NOT_FROZEN`이므로 전체 수집은 코드에서 차단된다.
