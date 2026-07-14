# FX Sensitivity & Industry Return Prediction

[![CI](https://github.com/minster0422/fx-industry-return-prediction/actions/workflows/ci.yml/badge.svg)](https://github.com/minster0422/fx-industry-return-prediction/actions/workflows/ci.yml)

2025년 학부 데이터마이닝 팀 프로젝트와 KSCI 학술발표 논문을 **그대로 미화하지 않고 재구성한 연구 저장소**다. 당시의 좋은 아이디어를 보존하고, 논문·PPT·발표 대본·R 코드·CSV가 서로 달랐던 지점을 감사한 뒤, 미래정보 누수를 막은 V2 연구 설계와 실행 코드를 제공한다.

> 이 저장소의 목적은 과거 결과를 그대로 정답으로 선언하는 것이 아니라, 무엇을 생각했고 무엇을 실제로 구현했는지 분리한 뒤 더 좋은 연구로 발전시키는 것이다.

## 2025년에 떠올린 핵심 아이디어

환율 충격에 비슷하게 반응하는 종목을 군집화하고, 함께 움직이는 산업 관계를 수치화해 다음 달 산업 수익률 예측에 활용한다.

```mermaid
flowchart LR
    A["주가·환율·외국인 수급"] --> B["종목별 환율 민감도"]
    B --> C["K-means 군집화"]
    A --> D["산업별 상승 여부"]
    D --> E["산업 연관규칙과 Lift"]
    E --> F["동조 정보"]
    A --> G["월별 산업 변수"]
    F --> H["다음 달 수익률 예측"]
    G --> H
    H --> I["산업별 투자·위험관리 해석"]
```

좋았던 점은 세 분석을 나열하는 데서 끝나지 않고, **탐색적 분석에서 발견한 산업 관계를 예측변수로 다시 사용하려 했던 것**이다. 환율 민감도, 외국인 수급, 산업 네트워크를 하나의 이야기로 연결한 뼈대는 V2에서도 유지한다.

## 재구성 감사에서 확인한 내용

| 항목 | 2025 자료의 설명 | 코드·데이터 재검산 결과 |
|---|---|---|
| 데이터 | 2023-05~2025-04, 50종목 | 24,300행, 486거래일, 50종목 확인 |
| 군집 수 | Elbow와 Silhouette로 `k=4` | 현재 Python 포트의 최고 Silhouette는 `k=2`; `k=4`는 0.348 |
| 산업 연관규칙 | 제공된 24개월 이진행렬에서 계산 | 보고된 10개 규칙의 수치가 같은 행렬 재계산값과 모두 불일치 |
| `mean_corr` | 산업 동조를 반영하는 월별 변수 | R 코드는 종목별 월간 `하루라도 상승`을 사용해 Lift 최대 1.0, 모든 `mean_corr=0` |
| 예측 월 | 2024-05부터 다음 달 예측 | 코드의 2024-05 행은 실제로 2024-06 수익률을 목표로 하며 그래프 월이 한 달 앞섬 |
| 성능 향상 | `mean_corr`로 오차 5~17% 감소 | 해당 실행 경로에서는 변수가 전부 0이므로 이 주장을 재현할 수 없음 |

자세한 근거와 수치 비교는 [`docs/RECONSTRUCTION_AUDIT.md`](docs/RECONSTRUCTION_AUDIT.md)에 정리했다.

## 저장소가 제공하는 두 버전

### V1 — 2025 구조 재현

- 환율 수익률에 대한 종목별 회귀계수 β 계산
- 평균 수익률·외국인 지분율 변화·β의 K-means 군집화
- 제공된 산업 이진행렬에서 Support·Confidence·Lift 재계산
- 2025 `mean_corr` 생성 코드의 실제 동작 감사
- 12개월부터 시작하는 expanding-window Random Forest 포트
- `feature_month`와 실제 `target_month`를 동시에 저장

Python과 R의 Random Forest 구현 차이 때문에 예측 숫자를 완전히 동일하게 만들었다고 주장하지 않는다. 대신 변수 정의, 학습창, 타깃 이동, 평가 범위를 실행 가능한 형태로 고정한다.

### V2 — 누수 없는 업그레이드

- 같은 달 동조가 아니라 `산업 A의 t월 → 산업 B의 t+1월` 시차 관계 사용
- 각 예측 시점까지 관측된 과거만으로 관계를 다시 계산
- 선택된 선행 산업의 현재 수익률을 `network_signal`로 구성
- Zero, 직전 수익률, 기본 RF, 네트워크 RF를 같은 Walk-forward 구간에서 비교
- RMSE뿐 아니라 MAE와 방향 적중률을 함께 기록

V2는 완성된 투자모형이 아니라, 원래 아이디어를 검증 가능한 연구문제로 바꾸는 첫 기준선이다. 장기 데이터와 통계적 유의성 검정이 추가되어야 한다.

### 현재 V2 proof-of-concept 결과

24개월 표본에서 전체 110개 Walk-forward 예측을 합쳐 비교하면 기본 RF의 RMSE는 약 `0.003712`, 네트워크 RF는 약 `0.003701`이었다. 차이는 약 0.3%로 매우 작고, 0을 예측하는 기준선의 RMSE가 약 `0.003552`로 더 낮았다. 즉 현재 표본에서는 네트워크 신호의 실질적인 증분가치를 입증하지 못했다. 방향 적중률은 기본 RF 약 48.2%, 네트워크 RF 약 49.1%였다.

이 결과는 실패를 숨기지 않는 기준선이다. 장기 데이터, 변동성 대비 스케일링, 통계적 검정 없이 성능 향상을 주장하지 않는다.

## 실행 방법

원본 `merged_50stocks_fx_multi.csv`는 출처와 재배포 조건이 확정되지 않아 Git에 포함하지 않았다. 로컬의 `data/raw/`에 넣거나 `--input`으로 경로를 지정한다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .

fx-research `
  --input data/raw/merged_50stocks_fx_multi.csv `
  --output results/generated `
  --trees 300
```

테스트:

```powershell
python -m unittest discover -s tests -v
```

실행 결과는 다음처럼 생성된다.

```text
results/generated/
├─ summary.json
├─ reconstruction/
│  ├─ cluster_assignments.csv
│  ├─ association_rules_reconciliation.csv
│  ├─ legacy_mean_corr.csv
│  ├─ legacy_predictions.csv
│  ├─ legacy_metrics_latest6.csv
│  └─ published_vs_python_metrics.csv
└─ v2/
   ├─ monthly_panel_with_network_signal.csv
   ├─ predictions.csv
   ├─ metrics_latest6.csv
   └─ metrics_all_walk_forward.csv
```

## 문서 안내

- [`docs/RESEARCH_STORY.md`](docs/RESEARCH_STORY.md): 당시 아이디어와 잘했던 점
- [`docs/PRESENTATION_FLOW.md`](docs/PRESENTATION_FLOW.md): 발표 대본과 27장 PPT의 실제 흐름
- [`docs/VERSION_MAP.md`](docs/VERSION_MAP.md): 논문·PPT·대본·코드의 역할과 충돌 처리 원칙
- [`docs/RECONSTRUCTION_AUDIT.md`](docs/RECONSTRUCTION_AUDIT.md): 재현 과정에서 발견된 불일치
- [`docs/V2_RESEARCH_DESIGN.md`](docs/V2_RESEARCH_DESIGN.md): 업그레이드 연구 설계
- [`archive_2025/README.md`](archive_2025/README.md): 2025 공개 산출물의 보존 원칙

## 논문

이민성, 홍찬기, 추민주, 이석준, 우지영, **「환율 민감도 기반 클러스터링과 동조지수를 이용한 산업별 월간 수익률 예측」**, 한국컴퓨터정보학회 학술발표논문집, 33(2), 959–961, 2025.

- DBpia: <https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12337990>

## 주의사항

이 프로젝트는 교육·재현 연구용이며 투자 조언이 아니다. 표본은 24개월로 매우 짧고, 고정된 50종목을 사용하므로 생존편향·표본선택 편향·시장국면 의존성이 크다.
