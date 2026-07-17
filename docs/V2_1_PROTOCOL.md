# V2.1 사전등록형 연구 프로토콜

## 0. 문서 상태

| 항목 | 값 |
|---|---|
| 프로토콜 버전 | `0.1.0-draft` |
| 작성일 | 2026-07-17 |
| 상태 | `DRAFT — NOT FROZEN` |
| V2.1 결과 열람 | 금지 |
| V2.1 학습 실행 | 금지 |
| 기준 난수 시드 | `20250717` |
| 예정 데이터 종료일 | 2026-06-30 |

이 문서는 V2.1 결과를 생성하기 전에 분석의 선택 자유도를 고정한다. `UNRESOLVED` 항목은 데이터 가능성 시험에서 결과변수를 만들지 않은 채 해소해야 한다. 모든 항목이 닫히고 문서와 `configs/v2_1_protocol.yaml`의 SHA-256이 기록되기 전까지 프로토콜은 동결된 것으로 간주하지 않는다.

2025 결과는 수업 팀 프로젝트의 공동 산출물이다. V2.1은 그 결과를 소급해 수정하는 작업이 아니라 별도의 후속 재구성 연구다.

## 1. 연구 목적과 범위

핵심 연구 질문은 다음과 같다.

> 과거 정보만으로 추정한 종목·산업의 환율 노출 상태와 산업 간 시차 네트워크가 단순 기준모형보다 다음 달 산업 초과수익률 예측을 개선하는가?

V2.1은 다음을 주 분석으로 고정한다.

- 기존 10개 산업·50종목의 시점별 가용 표본
- USD/KRW 환율
- 동일가중 산업 가격수익률의 KOSPI 대비 초과수익률
- 60개월 rolling 학습창
- pooled sector-month 모형
- 연속형 초과수익률 기반 방향성 시차 네트워크
- Ridge 계열의 `M4R vs M3R` paired MAE 차이를 주 검정

`results/summary.json`과 `results/v2/`는 2025 구조의 문제와 짧은 표본의 한계를 확인하는 감사 자료로만 사용했다. 그 수치로 V2.1 기간·threshold·모델·성공 기준을 고르지 않았으며 V2.1 판정 표본에 합치지 않는다.

다음은 민감도 분석으로만 사용하며 주 결론을 대체하지 않는다.

- 시가총액 가중 산업수익률
- EUR/KRW, JPY/KRW, CNY/KRW
- 504거래일 환율 β
- expanding 학습창
- Random Forest 결과
- Binary Lift 네트워크
- 매핑 가능한 KRX 산업지수 비교
- 공식 장기 외국인 수급 자료가 검증된 경우의 수급 변수

## 2. 연구가설과 판정 지표

### H1 — 환율 노출 상태의 증분가치

`M3R`은 동일 예측행에서 `M1`보다 절대오차가 작다.

- 지표: `ΔMAE_exposure = MAE(M3R) - MAE(M1)`
- 확인 기준: `ΔMAE_exposure < 0`, 95% month-block bootstrap 신뢰구간 상한 `< 0`, 세 시기 중 두 시기 이상에서 `ΔMAE_exposure < 0`
- 표본 기준: OOS 적격월 `>=36`이고 H1 paired 산업-월 `>=300`; 둘 중 하나라도 미달하면 H1은 `표본 부족으로 판단보류`

### H2 — 방향성 산업 네트워크의 존재와 안정성

과거 산업 초과수익률에는 반복 관측되는 `A_t → B_{t+1}` 관계가 존재한다.

- 지표: FDR 통과 edge의 월별 수, edge 지속률, edge 부호 일치율
- 확인 기준: 하나 이상의 방향성 edge가 전체 적격 예측월의 20% 이상에서 선택되고, 선택월 중 같은 부호의 비율이 75% 이상
- 표본 기준: 네트워크 산출이 가능한 OOS 적격월 `>=36`; 미달하면 H2는 `표본 부족으로 판단보류`

ordered edge `e=(A→B)`와 네트워크 산출 가능 OOS 월 집합 `T`에 대해 다음처럼 계산한다.

```text
edge_persistence(e) = count_t(selected(e,t)=1) / |T|
edge_sign_consistency(e)
  = max(count_t(selected(e,t)=1 and w(e,t)>0),
        count_t(selected(e,t)=1 and w(e,t)<0))
    / count_t(selected(e,t)=1)
```

한 번도 선택되지 않은 edge의 부호 일치율은 `NA`다. H2는 동일 edge 하나 이상이 두 threshold를 모두 통과할 때만 확인한다. edge 활성월이 적다는 사실은 충분한 OOS 월이 존재하는 한 표본 부족이 아니라 H2 미확인 근거다.

### H3 — 네트워크 신호의 예측 증분가치

`M4R`은 동일 예측행에서 `M3R`보다 절대오차가 작다.

- 주 지표: `ΔMAE_network = MAE(M4R) - MAE(M3R)`
- 확인 기준: `ΔMAE_network < 0`, 95% month-block bootstrap 신뢰구간 상한 `< 0`, 세 시기 중 두 시기 이상에서 `ΔMAE_network < 0`
- 보조 확인: `M4F vs M3F`의 `ΔMAE_network < 0`
- 표본 기준: OOS 적격월 `>=36`이고 H3 paired 산업-월 `>=300`; 둘 중 하나라도 미달하면 H3는 `표본 부족으로 판단보류`

## 3. 표기, 분석 단위와 예측 시점

- `i`: 종목
- `j`: 산업
- `d`: KRX 거래일
- `t`: feature month
- `t+1`: target month
- 분석 단위: 산업 `j` × feature month `t`
- 예측 대상: `j`의 `t+1`월 초과수익률
- 데이터 수집 범위: 2010-01-04~2026-06-30
- 마지막 feature month: 2026-05
- 마지막 target month: 2026-06

예측 시점 `forecast_as_of(t)`은 원칙적으로 `t`월 마지막 KRX 거래일 18:30 KST다. 해당 시각까지 공식적으로 공개되지 않은 변수는 `t`월 feature로 사용할 수 없고 한 달 lag를 적용한다. KRX Open API와 ECOS의 실제 공개 시각이 이 원칙을 만족하는지는 `UNRESOLVED-02`, `UNRESOLVED-03`에서 확인한다. 공개 시각이 원칙과 다르면 결과 생성 전에 프로토콜을 수정하고 다시 동결해야 한다.

## 4. 공식 데이터 출처와 이용 조건

### 4.1 주 출처

| 데이터 | 주 출처 | 사용 범위 |
|---|---|---|
| 종목 일별 매매정보 | KRX Open API | 50종목 가격수익률, 거래량, 거래대금, 시가총액 후보 |
| KOSPI 일별 지수 | KRX Open API | 시장수익률과 시장변동성 |
| 종목 기본정보 | KRX Open API | 종목코드, 상장·폐지 상태 확인 |
| USD/KRW 및 보조 환율 | 한국은행 ECOS Open API `731Y001` | 일별 환율수익률; USD `0000001`, EUR `0000003`, JPY `0000002`, CNY `0000053` |
| KRX 산업지수 | KRX Data Marketplace/Open API | 민감도 분석 |

KRX Open API는 2010년 이후 자료를 제공하고 인증키와 서비스별 활용승인을 요구한다. 2025-12-26 시행 약관 기준 비상업적 이용, 키당 1일 10,000회, 결과의 제3자 제공 금지와 출처표시 의무가 있다. 따라서 인증키와 KRX 원자료는 Git에 커밋하지 않는다. 공개 저장소에는 수집 코드, 필드 명세, 요청일, 응답 SHA-256, 파생 데이터의 재생성 절차만 둔다.

위 이용조건과 아래 공식 링크의 확인일은 2026-07-17이다. Open API 인증키 유효기간은 발급일로부터 1년으로 기록하고 만료 전 자동 갱신을 가정하지 않는다. 파생 결과 파일의 공개 허용 범위는 약관 문구만으로 추정하지 않고 `UNRESOLVED-06`에서 별도로 닫는다.

### 4.2 대체 출처

KRX 승인 실패 시 금융위원회 공공데이터포털 `주식시세정보` API를 대체 후보로 시험한다. 이 API는 무료·자동승인·이용허락 제한 없음으로 표시되지만 영업일 다음 날 13:00 이후 갱신된다. 따라서 대체 출처를 채택하면 `forecast_as_of`와 target 시작시점을 결과 확인 전에 다시 동결해야 한다. KRX와 공공데이터포털 중 어느 출처를 사용할지는 데이터 가능성 시험 종료 시 한 번만 결정한다.

### 4.3 출처 금지

- 화면 HTML을 비공식적으로 크롤링하지 않는다.
- 공식 약관이 확인되지 않은 포털·블로그·재배포 CSV를 주 분석에 사용하지 않는다.
- 서로 다른 출처의 가격을 성능에 유리하도록 사후 교체하지 않는다.

## 5. 표본 구성 규칙

주 표본의 산업·종목 매핑은 `src/fx_research/constants.py`의 10개 산업·50종목을 사용한다. 종목명은 데이터 조회 전에 영구 종목코드로 치환하고, 코드 매핑표의 출처와 확인일을 기록한다.

### 5.1 월별 종목 적격성

종목 `i`의 월 `t` 수익률은 다음 조건을 모두 만족할 때 유효하다.

1. `t-1`월 말과 `t`월 말 기준가격이 존재한다.
2. `t`월에 해당 시장 거래일의 80% 이상 일별 관측이 존재한다.
3. 월말 가격은 해당 월 마지막 시장 거래일 또는 그 이전 3거래일 이내의 마지막 유효가격이다.
4. 거래정지로 연속 5시장거래일을 초과해 가격이 없는 달은 제외한다.
5. 기업행사 조정 검증을 통과한 수익률 필드를 사용한다.

### 5.2 월별 산업 적격성

- 산업 `j`는 월 `t`에 유효 종목이 3개 이상일 때만 산업수익률을 계산한다.
- `panel_start`는 2010-01 이후 처음으로 10개 산업 모두에서 유효 종목이 3개 이상인 월이다.
- 이후 3개 미만인 산업-월은 결측으로 남기며 다른 종목으로 대체하지 않는다.
- 주 비교의 적격 예측월은 90개 후보 edge가 모두 48개 이상 유효 pair를 갖고, 실제값과 paired 예측이 존재하는 산업이 8개 이상인 월이다. 이 조건을 통과하지 못한 월은 모델 성능과 무관한 품질 제외로 기록한다.

### 5.3 첫 예측월

feature month `t`는 다음을 모두 만족하는 최초 월부터 예측한다.

- `panel_start` 이후 60개 이전 월이 존재한다.
- 각 산업에 이전 60개월 중 유효 target이 48개 이상 있다.
- rolling β에 필요한 종목별 일별 관측이 200개 이상인 종목이 산업마다 3개 이상이다.
- `t-60`~`t`의 각 feature month에서 90개 후보 edge가 모두 최소 48개 유효 pair를 가져, 최초 outer training window와 첫 예측월의 네트워크를 동일 규칙으로 계산할 수 있다.
- `t+1`이 2026-06 이하다.

따라서 `panel_start+60개월`을 기계적으로 첫 예측월로 쓰지 않는다. 위 조건을 만족하는 최초 월을 코드가 한 번 결정하며, 성능을 확인한 뒤 더 이른 월이나 더 늦은 월로 옮길 수 없다.

## 6. 상장·폐지·분할·합병·결측 처리

- 상장 전과 상장폐지 후는 구조적 결측으로 유지한다.
- 분석기간 중 실제로 관측 가능한 종목만 월별 동일가중에 포함한다.
- 상장폐지월 수익률은 공식 가격 계열이 경제적 손실을 반영하는 경우에만 포함한다. 반영 여부가 확인되지 않으면 해당 종목-월을 제외하고 사유를 기록한다.
- 분할·병합·감자·분사 등 기업행사는 공식 조정 수익률 필드 또는 검증된 조정계수를 사용한다.
- 가격수익률 검증은 알려진 기업행사일 10건 이상을 대상으로 수행한다. 경제적 가격변화가 없는데 일수익률 절댓값이 20%를 초과하는 사례가 1건이라도 있으면 해당 필드는 부적격이다.
- target 결측행은 학습·평가에서 제외한다. predictor 결측 처리는 15절 규칙을 적용한다.
- 종목 교체, 기업행사 수동 보정, 이상치 삭제는 모두 decision log에 날짜·근거·영향 행 수를 기록한다.

## 7. 수익률과 타깃 정의

기업행사 검증을 통과한 일별 가격수익률을 `r_{i,d}`라 한다.

```text
R_stock(i,t) = Π[d in t] (1 + r(i,d)) - 1
```

월별 동일가중 산업수익률은 다음과 같다.

```text
R_sector_EW(j,t) = (1 / N(j,t)) × Σ[i in eligible(j,t)] R_stock(i,t)
```

KOSPI 월수익률은 공식 일별 지수수익률을 복리 누적한다.

```text
R_market(t) = Π[d in t] (1 + r_KOSPI(d)) - 1
X(j,t) = R_sector_EW(j,t) - R_market(t)
```

주 타깃은 다음 달 초과수익률이다.

```text
y_primary(j,t+1) = R_sector_EW(j,t+1) - R_market(t+1)
```

민감도 분석의 시가총액 가중치는 target month가 시작되기 전인 `t`월 말 시가총액으로 고정한다.

```text
w(i,j,t) = market_cap(i,t) / Σ[k in eligible(j,t)] market_cap(k,t)
R_sector_VW(j,t+1) = Σ[i] w(i,j,t) × R_stock(i,t+1)
y_secondary(j,t+1) = R_sector_VW(j,t+1) - R_market(t+1)
```

`t`월 말에 가중치를 받은 종목의 `t+1`월 수익률이 공식 상장폐지 수익률을 포함해도 확정되지 않으면 해당 산업-월 `y_secondary` 전체를 결측으로 둔다. 남은 종목으로 가중치를 다시 1로 정규화하지 않는다.

target과 predictor 자체는 winsorize하지 않는다.

## 8. 환율수익률과 rolling β

환율 `F_d`는 원화/외화 표시다. USD/KRW 상승은 원화 약세를 뜻한다.

```text
fx_ret(d) = ln(F(d) / F(d-1))
```

월 `t`의 종목별 주 환율 노출은 `t`월 마지막 거래일까지의 최근 252 KRX 거래일로 추정한다.

```text
r_stock(i,d) = α(i,t) + β_fx(i,t) × fx_ret_USD(d)
               + β_mkt(i,t) × r_KOSPI(d) + ε(i,d)
```

- 최소 paired 일별 관측: 200개
- 추정법: OLS
- 표준오차: Newey-West HAC, max lag 5
- 저장값: `beta_fx_252`, `beta_fx_se_252`, `beta_fx_pvalue_252`, `beta_market_252`, `beta_r2_252`
- 504거래일 β는 민감도 분석이며 최소 400개 관측을 요구한다.
- β 계산에는 `t`월 이후 자료가 들어가지 않는다.
- `beta_fx_pvalue_252 = 2×(1-Φ(|beta_fx_252/beta_fx_se_252|))`로 계산하고, `beta_r2_252 = 1-SSE/SST`로 계산한다.

## 9. 월별 군집화와 안정성

군집화는 예측에 연결되는 상태변수를 만들기 위해 매월 다시 수행한다.

### 9.1 입력 변수

- `beta_fx_252`
- `stock_mean_return_252 = 252 × mean(r_stock)`
- `stock_volatility_252 = sqrt(252) × sd(r_stock)`

각 월의 적격 종목 횡단면에서 StandardScaler를 적합한다. 전체기간 scaler를 사용하지 않는다.

군집 적격 종목은 세 입력값이 모두 존재하는 종목이다. 적격 종목이 4개 미만이면 그 월의 군집과 모든 cluster 구성 변수는 결측이며 15절 품질 gate를 적용한다.

### 9.2 알고리즘

- K-means `k=4`
- `init=k-means++`, `algorithm=lloyd`
- `n_init=50`, `max_iter=300`, `tol=1e-4`
- `random_state=20250717`
- cluster label은 cluster별 `beta_fx_252` 중앙값 오름차순으로 1~4를 부여한다. 동률이면 변동성 중앙값, 다시 동률이면 원래 centroid index 순으로 정한다.

### 9.3 산업 노출 변수

월별 산업 `j`에 대해 다음을 계산한다.

- β 중앙값, IQR, 양수 비율, p-value<0.05 비율
- β 표준오차 중앙값, R² 중앙값
- cluster 1~4 비율
- 전월과 공통인 종목 중 cluster가 바뀐 비율
- `beta_median × fx_return_month_t`

Ridge에는 완전 공선성을 피하기 위해 cluster 1~3 비율만 넣고 cluster 4는 기준범주로 둔다. 군집 안정성은 전월 공통 종목의 Adjusted Rand Index와 이동률로 보고한다.

```text
C_j(t) = 산업 j의 cluster 적격 종목(t-1) ∩ 적격 종목(t)
cluster_migration_share(j,t)
  = count[i in C_j(t)](cluster(i,t) != cluster(i,t-1)) / |C_j(t)|
C_all(t) = 전체 cluster 적격 종목(t-1) ∩ 적격 종목(t)
cluster_ari(t)
  = adjusted_rand_score(cluster(C_all(t),t-1), cluster(C_all(t),t))
```

`|C_j(t)|<3`이면 해당 산업 migration은 `NA`, `|C_all(t)|<4`이면 ARI는 `NA`다. ARI는 Hubert-Arabie adjusted Rand index를 계산하는 `sklearn.metrics.adjusted_rand_score` 정의를 사용한다.

## 10. 외국인 수급 변수

외국인 수급은 주 분석에서 제외한다. 다음 조건을 모두 만족할 때만 사전 정의된 민감도 분석에 포함한다.

1. 공식 제공기관과 이용조건이 확인된다.
2. `panel_start`~2026-06의 월별 자료를 동일 정의로 확보한다.
3. 종목-월 커버리지가 95% 이상이다.
4. `forecast_as_of(t)` 이전 공개 여부가 확인된다.
5. 원자료 제3자 제공 없이 재생성 절차를 공개할 수 있다.

포함할 경우 변수는 다음 하나로 고정한다.

```text
foreign_flow_scaled(i,t)
  = monthly_foreign_net_purchase_value(i,t) / market_cap(i,t-1)
```

산업값은 적격 종목의 중앙값이다. 기존 `fore_chg`와 정의를 섞지 않는다. 위 조건 중 하나라도 실패하면 수급 민감도 분석 전체를 제외하고 실패 사유만 보고한다.

## 11. 연속형 시차 네트워크

### 11.1 edge 가중치

feature month `t`에서 산업 `A → B`의 후보 edge는 `t-1`까지 관측된 60개 lead-lag pair로 계산한다.

```text
candidate pairs: (X(A,s), X(B,s+1))
for s = t-61, ..., t-2

w(A→B,t) = PearsonCorr(X(A,s), X(B,s+1))
```

- 자기 edge `A=B`는 금지한다.
- 유효 pair가 48개 미만이면 edge를 계산하지 않는다.
- 두 입력 중 하나의 표본표준편차가 0이면 `w=0`, `p=1`, `selected=0`으로 기록한다.
- `t`월 follower 수익률과 `t+1` target은 edge 추정에 사용하지 않는다.

### 11.2 edge 선택

- 귀무분포: leader 시계열을 6개월 블록 단위로 circular permutation
- permutation 횟수: 1,000
- 양측 p-value: `(1 + count(|w_perm| >= |w_obs|)) / 1001`
- 매월 90개 방향성 edge에 Benjamini-Hochberg FDR 적용
- 선택 조건: `q <= 0.10`, `|w| >= 0.20`, 유효 pair `>=48`

구현은 60개 leader 값을 임의의 원형 시작점에서 회전한 뒤 연속한 6개월 블록 10개로 나누고, 그 10개 블록의 순서만 seed 기반으로 섞는다. follower 순서는 고정한다. edge별 RNG는 `SeedSequence([20250717, YYYYMM, leader_rank, follower_rank])`로 만들며 rank는 `constants.py` 산업 사전순의 0-based index다. 48개 미만인 edge는 `p=1`, `selected=0`으로 두어 매월 BH 보정의 family size를 항상 90으로 유지한다.

### 11.3 network signal

```text
network_signal(B,t)
  = Σ[A in selected leaders] w(A→B,t) × X(A,t)
    / Σ[A in selected leaders] |w(A→B,t)|
```

선택된 leader가 없으면 `network_signal=0`, `leader_count=0`, `network_weight_abs_sum=0`으로 둔다. edge 목록, p-value, q-value, 유효 pair 수와 선택 여부를 모두 저장한다.

## 12. Binary Lift 민감도 분석

기존 아이디어와의 연결을 위해 다음 규칙만 별도로 실행한다.

- `up(j,t)=1` if `X(j,t)>0`, 아니면 0
- 60개 과거 lead-lag pair
- 최소 support 0.15, 최소 동시 발생 9회, lift 1.20 이상
- 1,000회 6개월 블록 permutation, BH-FDR `q<=0.10`
- 연속형 네트워크와 동일한 Walk-forward row에서 비교

```text
support(A→B,t) = mean_s(up(A,s) × up(B,s+1))
confidence(A→B,t) = support(A→B,t) / mean_s(up(A,s))
lift(A→B,t) = confidence(A→B,t) / mean_s(up(B,s+1))
binary_weight(A→B,t) = lift(A→B,t) - 1
binary_network_signal(B,t)
  = Σ[selected A] binary_weight(A→B,t) × X(A,t)
    / Σ[selected A] binary_weight(A→B,t)
```

leader 또는 follower의 상승 비율이 0이면 `lift=NA`, `p=1`, `selected=0`이다. permutation은 11.2절과 동일한 leader block RNG를 사용하고 one-sided `p=(1+count(lift_perm>=lift_obs))/1001`로 고정한다. 선택 leader가 없으면 binary signal은 0이다. 이 signal과 그 leader count·weight sum이 M4의 NETWORK 3개 열을 대체한다.

Binary Lift 결과는 H2·H3의 주 판정을 바꾸지 않는다.

## 13. 예측 변수

### 기본 변수 `BASE`

- `X(j,t)`, `X(j,t-1)`, `X(j,t-2)`
- `R_sector_EW(j,t)`
- `R_market(t)`
- `fx_return_USD(t)`
- `sector_excess_vol_12m = sd(X(j,t-11:t))`
- `market_vol_21d = sqrt(252) × sd(r_KOSPI)` over last 21 trading days of `t`
- `coverage_ratio = N(j,t)/5`
- 산업 one-hot 9개 열, 한 산업은 기준범주

### 환율 노출·군집 변수 `EXPOSURE`

- `beta_median`, `beta_iqr`, `beta_positive_share`, `beta_significant_share`
- `beta_se_median`, `beta_r2_median`
- `cluster_share_1`, `cluster_share_2`, `cluster_share_3`
- `cluster_migration_share`
- `beta_fx_interaction = beta_median × fx_return_USD(t)`

### 네트워크 변수 `NETWORK`

- `network_signal`
- `leader_count`
- `network_weight_abs_sum`

## 14. 데이터 누수 방지 규칙

1. `feature_month`, `forecast_as_of`, `target_month`를 모든 예측행에 저장한다.
2. target month 자료는 predictor, imputation, scaling, winsorization, 군집화, edge 선택과 hyperparameter 선택에 사용하지 않는다.
3. outer 평가에서는 full outer training만, inner CV에서는 해당 inner training만으로 전처리기를 적합한다.
4. β는 feature month `t`까지만, edge 가중치는 follower month `t-1`까지만 사용한다.
5. 시가총액 가중치는 target 시작 전 `t`월 말 값만 사용한다.
6. inner CV는 월을 단위로 나누며 같은 월의 산업을 서로 다른 fold에 나누지 않는다.
7. 전체기간 통계량으로 결측 대치·표준화·구간 정의를 하지 않는다.
8. predictor 하나를 미래 구간에서 임의 삭제하거나 교체하지 않는다.
9. 누수 테스트는 미래 월 값을 교란해도 과거 feature가 변하지 않는지 확인한다.
10. V2.1 결과가 생성된 이후의 변경은 23절 이탈 정책을 따른다.

## 15. 전처리와 결측

- target 결측행은 제외한다.
- `core predictor`는 `M4R`의 `BASE+EXPOSURE+NETWORK` 연속형 입력 전체를 뜻하며 one-hot과 사후 생성 missing indicator는 제외한다.
- core predictor 하나라도 outer training 결측률이 5%를 초과하면 해당 outer forecast month의 M0~M4 전체를 실행 중단하고 데이터 품질 실패로 기록한다.
- 5% 이하 predictor 결측은 outer training 중앙값으로 대치하고 validation/test에 같은 값을 적용한다.
- 결측이 한 번이라도 있는 predictor에는 missing indicator를 추가한다.
- 연속형 predictor는 outer training의 1·99 percentile을 `linear` interpolation으로 계산해 clip하고 validation/test에 같은 경계를 적용한다.
- target과 현재 월 수익률 원자료는 clip하지 않는다.
- Ridge는 training에서 평균과 모집단 표준편차(`ddof=0`)를 쓰는 StandardScaler를 적합한다.
- Random Forest는 같은 대치·clip 결과를 사용하되 scaling하지 않는다.
- 산업 one-hot 범주 순서는 `constants.py` 사전순으로 고정한다.
- inner CV에서는 각 fold의 inner training만으로 대치값·clip 경계·scaler를 다시 적합한다. hyperparameter 선택 후 full outer training에 전처리기를 재적합하고 outer forecast month에는 transform만 적용한다.

## 16. Walk-forward와 내부 검증

### 16.1 Outer loop

- pooled sector-month 모형 하나를 매월 재학습한다.
- 주 학습창: 직전 60개 feature month
- 각 학습월의 적격 산업행을 모두 포함한다.
- forecast month `t`의 모든 적격 산업을 동시에 예측한다.
- expanding window는 민감도 분석이다.

### 16.2 Inner time-series CV

60개월 outer training window를 다음 세 fold로 나눈다.

1. 첫 36개월 학습, 다음 8개월 검증
2. 첫 44개월 학습, 다음 8개월 검증
3. 첫 52개월 학습, 마지막 8개월 검증

각 fold에서 같은 월의 산업은 함께 이동한다. 각 fold 안의 모든 validation 산업-월을 pooled MAE로 요약한 뒤 세 fold MAE의 단순평균이 가장 낮은 hyperparameter를 선택한다.

동률은 절대 MAE 차이 `<=1e-12`로 정의한다.

- Ridge: 더 큰 alpha 선택
- RF: 더 큰 `min_samples_leaf`, 더 작은 `max_depth`, 더 작은 `max_features` 순으로 선택

Ridge의 고정값은 `fit_intercept=true`, `solver=svd`, `tol=1e-4`다. expanding-window 민감도 분석은 hyperparameter 선택에 직전 60개월과 위 세 inner fold를 그대로 사용하고, 선택된 값으로 `panel_start` 이후의 모든 과거 적격행을 다시 학습한다.

## 17. 모델 정의

모든 학습형 모델의 예측 대상은 `y_primary(j,t+1)`이고, outer 학습창은 feature month `t-60`~`t-1`의 60개월이다. M0-mean은 산업별로 `X(j,t-59)`~`X(j,t)` 중 유효한 최근 60개 값의 평균을 사용하며 최소 48개를 요구한다.

| ID | 입력 변수 | 학습창 | 전처리 | 조정 가능한 hyperparameter | 탐색 범위 | 재학습 주기 | 예측 대상 | 비교 목적 |
|---|---|---|---|---|---|---|---|---|
| M0-mean | 산업별 과거 `X` | 최근 60 target month, 최소 48개 | 없음 | 없음 | 없음 | 매월 재계산 | `y_primary(j,t+1)` | 역사평균 기준선·OOS R² 분모 |
| M0-last | `X(j,t)` | 학습 없음 | 없음 | 없음 | 없음 | 재학습 없음 | `y_primary(j,t+1)` | 1개월 지속성 기준선 |
| M1 | `BASE` 전부 | 60개월 rolling | median 대치, missing indicator, 1/99% clip, StandardScaler | `alpha` | `{0.01,0.1,1,10,100}` | 매월 | `y_primary(j,t+1)` | 선형 기본모형 |
| M2 | `BASE` 전부 | 60개월 rolling | median 대치, missing indicator, 1/99% clip, scaling 없음 | `max_depth`, `min_samples_leaf`, `max_features` | 아래 RF grid | 매월 | `y_primary(j,t+1)` | 비선형 기본모형 |
| M1N | `BASE+NETWORK` 전부 | 60개월 rolling | M1과 동일 | `alpha` | M1과 동일 | 매월 | `y_primary(j,t+1)` | network-only ablation |
| M3R | `BASE+EXPOSURE` 전부 | 60개월 rolling | M1과 동일 | `alpha` | M1과 동일 | 매월 | `y_primary(j,t+1)` | H1 주 검정 |
| M3F | `BASE+EXPOSURE` 전부 | 60개월 rolling | M2와 동일 | RF 3개 조정값 | M2와 동일 | 매월 | `y_primary(j,t+1)` | H1 보조 검정 |
| M4R | `BASE+EXPOSURE+NETWORK` 전부 | 60개월 rolling | M1과 동일 | `alpha` | M1과 동일 | 매월 | `y_primary(j,t+1)` | H3 주 검정 |
| M4F | `BASE+EXPOSURE+NETWORK` 전부 | 60개월 rolling | M2와 동일 | RF 3개 조정값 | M2와 동일 | 매월 | `y_primary(j,t+1)` | H3 보조 검정 |

Random Forest grid:

- `n_estimators=500` 고정
- `max_depth ∈ {3, 5, null}`
- `min_samples_leaf ∈ {5, 10, 20}`
- `max_features ∈ {sqrt, 0.5, 1.0}`
- `bootstrap=true`, `criterion=squared_error`, `random_state=20250717`, `n_jobs=-1`

모든 모델은 같은 outer 예측행과 target을 사용한다. 성능이 좋은 산업만 골라 재평가하지 않는다.

## 18. 평가지표

### 18.1 주 지표

```text
absolute_error = |prediction - actual|
ΔMAE_network = mean(AE_M4R - AE_M3R)
```

음수면 네트워크가 개선한 것이다.

### 18.2 보조 지표

- `MAE = mean(|prediction-actual|)`와 `RMSE = sqrt(mean((prediction-actual)^2))`
- `OOS R² = 1 - SSE(model) / SSE(M0-mean)`
- 월별 Spearman Rank IC: 한 달에 실제·예측 산업이 8개 이상일 때 평균순위 방식으로 계산; 예측 또는 실제 횡단면 분산이 0이면 그 월은 `NA`
- 방향 Accuracy: 0 예측 제외 후 `mean(sign(prediction)=sign(actual))`
- balanced accuracy: 0 예측 제외 후 `(positive-class recall + negative-class recall)/2`; 실제값의 한 class가 없으면 `NA`
- 산업별 지표는 기술통계로만 보고하고 개별 산업 성능을 주 결론으로 삼지 않는다.

예측값이 정확히 0인 행은 방향성 평가에서 제외하고 제외 건수를 보고한다. Hit Rate는 보조지표이며 단독 성공 근거가 아니다.

## 19. Paired comparison과 bootstrap

- paired loss는 동일한 `sector, feature_month, target_month` 행만 사용한다.
- 한 달의 모든 산업을 하나의 cluster로 유지한다.
- moving block bootstrap, block length 6개월, 10,000회
- OOS 적격월 수를 `T`라 할 때 각 bootstrap 표본은 `[1..T]`에서 원형 시작점을 복원추출하고 연속 6개월 블록을 이어 붙여 정확히 `T`개월에서 자른다.
- 선택된 월의 모든 paired 산업행을 함께 복제하며, 각 표본에서 복제된 전체 행으로 `mean(AE_M4R-AE_M3R)`를 다시 계산한다.
- seed `20250717`
- percentile 95% CI 사용
- CI 끝점은 bootstrap 통계량의 0.025·0.975 분위수를 `linear` interpolation으로 계산한다.
- OOS 적격월이 36개월 미만 또는 paired 산업-월이 300개 미만이면 연구적 결론은 `표본 부족으로 판단보류`다. 이 기준을 충족한 뒤 edge가 적게 선택되거나 M4R이 M3R을 이기지 못하면 `증분가치 미확인`이다.

## 20. 사전 정의 하위기간과 시장국면

### 20.1 하위기간

적격 OOS 월을 시간순으로 `numpy.array_split(months, 3)`과 동일하게 세 그룹으로 분할한다. 앞 그룹부터 최대 1개월 더 가질 수 있다. 날짜를 성능에 따라 재분할하지 않는다.

### 20.2 환율 국면

feature month `t`의 USD/KRW 월수익률을 `t-60:t-1`의 1/3·2/3 분위수와 비교한다.

- `<= 1/3 분위수`: 원화강세
- `>= 2/3 분위수`: 원화약세
- 그 사이: 중립

### 20.3 변동성 국면

`market_vol_21d(t)`를 이전 60개월의 같은 값 중앙값과 비교한다.

- 중앙값 초과: 고변동성
- 중앙값 이하: 저변동성

각 국면에 적격 예측월이 24개월 미만이면 CI와 성공 판정을 하지 않고 기술통계만 보고한다.

## 21. Ablation과 민감도 분석

주 ablation은 Ridge에서 수행한다.

1. `M1`: BASE
2. `M3R`: BASE + EXPOSURE
3. `M1N`: BASE + NETWORK
4. `M4R`: BASE + EXPOSURE + NETWORK

민감도 분석은 다음 순서와 정의를 바꾸지 않는다.

1. RF 계열 `M2/M3F/M4F`
2. 시가총액 가중 target
3. 504일 β
4. EUR/KRW, JPY/KRW, CNY/KRW를 각각 USD/KRW 대신 한 번에 하나씩 사용
5. expanding window
6. Binary Lift network
7. KRX 산업지수 비교
8. 조건 충족 시 외국인 수급 추가

각 민감도 분석은 주 분석에서 정확히 한 항목만 바꾸고 서로 조합하지 않는다. target이나 predictor가 바뀌면 같은 grid와 inner CV로 hyperparameter를 다시 선택한다. 외국인 수급 민감도는 `foreign_flow_scaled_sector` 하나를 EXPOSURE에 추가한다. 민감도 분석 결과가 주 분석과 다르더라도 주 결론을 교체하지 않는다. 각 민감도 분석은 별도 라벨로 보고한다.

KRX 산업지수 비교는 사전 매핑에서 `정확` 또는 `부분`으로 라벨된 산업이 8개 이상일 때만 수행한다. 매핑된 지수의 `X_KRX(k,t)=R_KRX_index(k,t)-R_KOSPI(t)`를 만들고, 같은 월의 legacy 산업 `X(j,t)`와의 추적상관·추적 MAE를 보고한다. 이어 KRX 지수 패널에서 `BASE`만 쓰는 M1과 `BASE+NETWORK`를 쓰는 M1N의 paired MAE를 동일 Walk-forward 규칙으로 비교한다. 지수에는 종목 군집 구성비가 없으므로 M3/M4를 억지로 복제하지 않으며 이 비교는 H1·H3 판정을 바꾸지 않는다.

## 22. 경제적 해석과 보조 백테스트

백테스트는 예측력의 경제적 크기를 설명하는 보조 분석이며 투자성과 주장의 근거가 아니다.

고정된 50종목은 2025 프로젝트에서 선택된 표본이므로 시장 전체를 대표하는 생존편향 없는 유니버스가 아니다. 백테스트와 연구 결론은 이 legacy 표본 밖으로 일반화하지 않는다.

Ridge의 standardized coefficient는 각 outer fit별로 저장하고, 변수별 중앙값·IQR·부호 일치 비율만 기술한다. regularized coefficient에 사후 p-value를 붙이지 않으며 환율 β, network edge, 예측계수에서 인과효과를 주장하지 않는다. `ΔMAE×10,000`을 basis point 단위 효과크기로 함께 보고한다.

- 매월 M4R 예측 상위 2개 산업에 각각 `+0.25`
- 하위 2개 산업에 각각 `-0.25`
- 나머지 산업 0
- 예측값 동률은 `constants.py` 산업 사전순으로 깨고, 적격 산업 8개 이상인 월에서만 구성한다.
- gross exposure 1.0, net exposure 0
- `turnover(t)=0.5 × Σ_j |weight(j,t)-weight(j,t-1)|`
- 첫 백테스트 월의 이전 weight는 모든 산업 0이다.
- 거래비용 `20bp × turnover`
- target month 실제 산업 원수익률로 gross·net return 계산
- 공매도 비용, 세금, 체결충격은 모델링하지 않으며 한계로 명시

실용적 성공은 평균 월별 Rank IC의 95% block-bootstrap CI 하한이 0보다 크고, 비용 차감 long-short 평균수익률의 CI 하한도 0보다 클 때만 확인한다.

두 CI는 19절과 동일한 6개월 moving month-block, 10,000회, seed `20250717` 절차로 월별 Rank IC와 월별 비용 차감 수익률을 각각 재표집한다.

## 23. 성공·미확인·판단보류

### A. 공학적 성공

다음을 모두 만족해야 한다.

1. `python -m fx_research.v2_1 --config configs/v2_1_protocol.yaml` 한 명령으로 원자료 이후 전 과정을 재생성한다.
2. source URL, 요청일, 필드, 행 수, 파일 SHA-256을 `data_manifest.json`에 기록한다.
3. 미래값 교란·월 정렬·fold 경계·기업행사 테스트가 통과한다.
4. 잠긴 환경과 seed에서 예측 최대 절대차 `<=1e-12`로 재현된다.

### B. 연구적 성공

- H1은 표본 기준을 통과하고 H1의 세 확인 조건을 모두 만족하면 `환율 노출 증분가치 확인`, 표본 기준만 통과하고 하나 이상 실패하면 `환율 노출 증분가치 미확인`, 표본 기준 미달이면 `표본 부족으로 판단보류`다.
- H2는 36개 네트워크 OOS 월을 충족하고 동일 edge 하나 이상이 persistence·sign threshold를 모두 통과하면 `방향성 네트워크 안정성 확인`, 표본 기준만 통과하고 실패하면 `방향성 네트워크 안정성 미확인`, 월 수 미달이면 `표본 부족으로 판단보류`다.
- H3는 아래 ΔMAE·CI·하위기간 조건으로 판정한다.
- 네트워크의 최종 판정은 H3를 따른다.

`증분가치 확인`:

- OOS 월 `>=36`, paired 산업-월 `>=300`
- H3의 세 확인 조건 모두 충족

`증분가치 미확인`:

- 위 표본 조건은 충족하지만 H3 확인 조건 중 하나 이상 실패

`표본 부족으로 판단보류`:

- OOS 월 `<36` 또는 paired 산업-월 `<300`

edge 활성월 수는 H2와 네트워크 작동 빈도를 설명하는 보고값이지 H3 표본 기준이 아니다. OOS·paired 표본 기준을 통과했다면 edge 활성 빈도와 무관하게 H3 조건 실패는 `증분가치 미확인`이다.

### C. 실용적 성공

22절의 Rank IC와 비용 차감 long-short CI 조건을 모두 만족할 때만 `실용적 유용성 확인`으로 쓴다. 그렇지 않으면 `실용적 유용성 미확인`이다.

## 24. V2.1 공개 산출물과 조건

아래 목록은 로컬에서 생성해야 하는 완전한 감사 산출물이다. Git 공개 여부는 파일별로 `UNRESOLVED-06` 판정을 적용한다.

```text
results/v2_1/
├─ data_manifest.json
├─ data_quality_report.json
├─ walk_forward_splits.csv
├─ beta_by_stock_month.csv
├─ cluster_state_by_month.csv
├─ network_edges_by_month.csv
├─ predictions.csv
├─ metrics_overall.csv
├─ metrics_by_regime.csv
├─ paired_tests.csv
├─ backtest.csv
└─ summary.json
```

공개 조건:

- 프로토콜과 설정의 동결 해시 기록
- `UNRESOLVED-01`~`04` 종료와 `UNRESOLVED-05` 포함/제외 라벨 확정
- `UNRESOLVED-06`의 공개 범위 확인; 허용되지 않은 원자료·파생 행 단위 결과는 로컬 생성만 하고 Git에는 코드와 허용된 집계치만 공개
- 원자료·인증키 제외
- 데이터 계보와 이용조건 기록
- 누수·정렬·재현성 테스트 통과
- 주 분석과 민감도 분석 분리
- 부정적 결과 포함 전체 결과 공개

## 25. 프로토콜 변경과 이탈 정책

### 동결 전

데이터 가능성 시험으로만 변경할 수 있다. 변경은 `V2_1_DECISION_LOG.md`에 이전값, 새값, 공식 근거, 결과 미열람 확인을 기록한다.

### 동결 후·결과 생성 전

오류 수정만 허용한다. 프로토콜 버전을 올리고 해시를 다시 기록하며 이전 버전을 보존한다.

### 결과 생성 후

주 분석 정의를 변경하지 않는다. 필요한 수정은 `DEVIATION`으로 라벨링하고 원래 사전등록 결과와 수정 결과를 함께 공개한다. 성능이 좋지 않다는 이유로 기간·타깃·산업·모델·지표를 바꾸지 않는다.

## 26. 동결 전 UNRESOLVED 게이트

1. `UNRESOLVED-01`: KRX 일별 수익률/가격 필드의 분할·합병·감자 조정 방식과 기업행사 검증
2. `UNRESOLVED-02`: KRX Open API 일별 자료의 실제 공개 시각과 `forecast_as_of` 적합성
3. `UNRESOLVED-03`: ECOS 통계표 `731Y001`의 항목코드·단위·방향은 2026-07-17 확인 완료; 일별 공개 시각과 수정정책은 미해결
4. `UNRESOLVED-04`: 기존 10개 산업과 KRX 산업지수의 사전 매핑표
5. `UNRESOLVED-05`: 공식 장기 외국인 순매수 자료의 접근·시점·재배포 조건
6. `UNRESOLVED-06`: KRX·ECOS 원자료로부터 만든 종목·산업 단위 파생 결과의 공개 허용 범위

`UNRESOLVED-05`는 주 분석 동결을 막지 않는다. 해당 항목이 닫히지 않으면 외국인 수급 민감도 분석을 제외한다. 01~04는 모두 닫혀야 프로토콜을 동결한다.

`UNRESOLVED-06`는 분석 프로토콜 동결을 막지 않지만 공개 릴리스를 막는다. 공식 확인이 없으면 원자료뿐 아니라 행 단위 파생 산출물도 Git에 커밋하지 않고 허용된 집계 지표와 재현 코드만 공개한다.

## 27. 공식 참고자료

- KRX Open API 서비스 목록: <https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd>
- KRX Open API 이용방법: <https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp>
- KRX Open API 이용약관: <https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp>
- KRX 데이터 분배상품 종가 전송시간: <https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp>
- KRX Data Marketplace: <https://data.krx.co.kr/>
- 금융위원회 주식시세정보 API: <https://www.data.go.kr/data/15094808/openapi.do>
- 한국은행 ECOS Open API: <https://ecos.bok.or.kr/api/>
