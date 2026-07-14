# Data contract

## 공개된 파일

`reference/`에는 2025 발표자료에 사용된 소형 파생표만 UTF-8 CSV로 보존한다.

- `sector_binary_2025.csv`: 24개월 × 10산업 상승 여부
- `association_rules_reported.csv`: 당시 보고된 10개 연관규칙
- `published_metrics.csv`: 최종 PPT의 최근 6개월 RMSE·Hit Rate

이 파일들은 과거 결과를 재현하기 위한 기준자료이며, 정확한 값이라고 보증하는 수정본이 아니다.

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
