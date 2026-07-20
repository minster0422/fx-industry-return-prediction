# V2.1 데이터 사전

## 표기 원칙

- 모든 수익률은 소수가 단위다. 예: 1%는 `0.01`.
- `t`는 feature month, `t+1`은 target month다.
- `forecast_as_of(t)`는 원칙적으로 `t`월 마지막 KRX 거래일 18:30 KST다.
- `EOD t`는 `t`월 마지막 유효 거래일 종가 이후를 뜻한다.
- `UNRESOLVED` 필드는 데이터 가능성 시험에서 공식 schema와 공개시점을 확인한 뒤 동결한다.
- 원자료는 Git에 커밋하지 않는다. 파생 산출물에는 source identifier와 SHA-256을 연결한다.

## 식별·계보 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `ticker_code` | 6자리 문자열 | KRX 종목기본정보 `ISU_SRT_CD` | 상장 공시 이후 | 종목기본정보의 단축코드. 일별 시세에서는 같은 의미의 필드가 `ISU_CD`로 반환된다. 영구 식별자로 가정하지 않음 |
| `isin_code` | 문자열 | KRX 종목기본정보 `ISU_CD` | 상장 공시 이후 | ISIN. 일별 시세의 `ISU_CD`와 이름은 같지만 의미가 다르므로 API별 schema로 구분 |
| `ticker_name` | 문자열 | KRX 종목기본정보 | 해당 시점 | 표시용 종목명; 분석 join에는 사용하지 않음 |
| `identity_provenance_status` | 범주 | 공개 provenance 표 | 검증일 이후 | 명칭 변경 연결은 동일 6자리 코드와 동일 ISIN을 모두 공식 응답에서 확인한 경우만 `VERIFIED_CODE_AND_ISIN`; 문자열 유사도 자동확정 금지 |
| `listing_date` | 날짜 | KRX 종목기본정보 | 상장 공시 이후 | 이 날짜 전 종목 관측은 구조적 결측 |
| `delisting_date` | 날짜/NA | KRX 종목기본정보 | 상장폐지 공시 이후 | 이 날짜 후 종목 관측은 구조적 결측 |
| `sector` | 범주 10개 | `constants.py` | 고정 | 2025 연구의 산업 매핑 |
| `date` | `YYYY-MM-DD` | 각 공식 API | 해당 자료 공개 후 | 원자료 기준일 |
| `feature_month` | `YYYY-MM` | 파생 | EOD t | predictor가 속한 월 |
| `target_month` | `YYYY-MM` | 파생 | t+1 종료 후 | `feature_month + 1 calendar month` |
| `forecast_as_of` | timestamp KST | 파생 | 예측 생성 전 | 해당 예측에 허용된 정보의 최종 시각 |
| `source_id` | 문자열 | manifest | 수집 시 | 기관·API·서비스·schema 버전 식별자 |
| `source_retrieved_at` | timestamp UTC | 수집기 | 수집 시 | API 응답 저장 시각 |
| `source_sha256` | 64자리 hex | 수집기 | 수집 시 | 원응답 또는 원파일 SHA-256 |

## 일별 원천·기본 파생 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `daily_ticker_code_raw` | 6자리 문자열 | KRX 일별 시세 `ISU_CD` | `UNRESOLVED-02` | 일별 시세의 단축코드. 종목기본정보의 ISIN 필드 `ISU_CD`와 혼동 금지 |
| `stock_price_raw` | KRW, float | KRX `TDD_CLSPRC` | `UNRESOLVED-02` | 쉼표 제거 후 float 변환. 빈 문자열·`-`·비정상 문자열은 NaN, 변환 실패 수 기록. 기업행사 조정 정의는 `UNRESOLVED-01` |
| `corporate_action_flag` | 범주/NA | KRX 공식 권리·기업행사 자료 | 공시 후 | 분할·병합·감자·분사 등 검증 사건 코드 |
| `daily_change_rate_candidate` | %, float | KRX `FLUC_RT` | `UNRESOLVED-02` | 쉼표 제거 후 float 변환. 퍼센트 단위 후보이며 기업행사 검증 전에는 `stock_return_daily`로 확정하지 않음 |
| `stock_return_daily` | 소수 | KRX Open API/검증 파생 | `UNRESOLVED-02` | `UNRESOLVED-01` 종료 전 미확정. 이후 기업행사 검증을 통과한 등락률을 100으로 나누거나 조정가격의 `P_d/P_{d-1}-1` 중 사전 결정 |
| `stock_volume_daily` | 주, 정수 | KRX `ACC_TRDVOL` | `UNRESOLVED-02` | 쉼표 제거 후 integer 변환; 빈 문자열·`-`·비정상 문자열은 NaN 및 실패 집계 |
| `stock_value_daily` | KRW, 정수 | KRX `ACC_TRDVAL` | `UNRESOLVED-02` | 쉼표 제거 후 integer 변환; 빈 문자열·`-`·비정상 문자열은 NaN 및 실패 집계 |
| `market_cap_daily` | KRW, 정수 | KRX `MKTCAP` | `UNRESOLVED-02` | 쉼표 제거 후 integer 변환; 빈 문자열·`-`·비정상 문자열은 NaN 및 실패 집계 |
| `KOSPI_level` | 지수포인트 | KRX Open API | `UNRESOLVED-02` | KOSPI 공식 지수 종가 |
| `market_return_daily` | 소수 | KRX Open API/파생 | `UNRESOLVED-02` | 공식 일별 지수수익률 또는 `I_d/I_{d-1}-1` |
| `fx_USDKRW_level` | KRW/USD | BOK ECOS `731Y001/0000001` | 공개 시각 `UNRESOLVED-03` | `원/미국달러(매매기준율)`; 상승은 원화 약세 |
| `fx_return_daily` | 로그수익률 | 파생 | 환율 공개 후 | `ln(F_d/F_{d-1})` |
| `foreign_net_purchase_daily` | KRW | 공식 자료 조건부 | 공식 공개 후 | 외국인 순매수금액; 주 분석 제외 |
| `is_market_trading_day` | bool | KRX 캘린더 | 당일 | 해당 시장이 열린 날이면 1 |
| `is_valid_stock_day` | bool | 파생 | EOD d | 가격 존재, 상장기간 내, 거래일이면 1 |

## 월별 수익률·표본 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `stock_monthly_return` | 소수 | 일별 파생 | EOD t | `Π(1+stock_return_daily)-1`; 일별 coverage 80% 이상 |
| `stock_monthly_valid` | bool | 파생 | EOD t | 월말가격·coverage·거래정지·기업행사 조건을 모두 만족하면 1 |
| `stock_daily_coverage_ratio` | [0,1] | 파생 | EOD t | 유효 종목 거래일 수 / 시장 거래일 수 |
| `sector_stock_count` | 정수 | 파생 | EOD t | 산업-월 적격 종목 수 |
| `coverage_ratio` | [0,1] | 파생 | EOD t | `sector_stock_count / 5` |
| `sector_return_ew` | 소수 | 파생 | EOD t | 적격 종목 월수익률의 동일가중 평균; 종목 3개 이상 |
| `lagged_market_cap_weight` | [0,1] | 파생 | EOD t | `market_cap(i,t)/Σ market_cap(k,t)` |
| `sector_return_vw_next` | 소수 | 파생 | t+1 종료 후 | `t`월 말 시총가중치 × `t+1` 종목수익률 합; 구성종목 수익률 하나라도 미확정이면 전체 결측, 재정규화 금지 |
| `market_return_monthly` | 소수 | 파생 | EOD t | `Π(1+market_return_daily)-1` |
| `sector_excess_return` | 소수 | 파생 | EOD t | `sector_return_ew - market_return_monthly` |
| `target_primary` | 소수 | 파생 | t+1 종료 후 | `sector_excess_return(j,t+1)` |
| `target_secondary` | 소수 | 파생 | t+1 종료 후 | `sector_return_vw(j,t+1)-market_return(t+1)` |

## 환율 노출·종목 상태 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `beta_fx_252` | 회귀계수 | 252일 rolling OLS | EOD t | USD/KRW 로그수익률 계수; KOSPI 일수익률 통제 |
| `beta_fx_se_252` | 회귀계수 단위 | rolling OLS | EOD t | Newey-West HAC, max lag 5 표준오차 |
| `beta_fx_pvalue_252` | [0,1] | rolling OLS | EOD t | 정규근사 양측값 `2×(1-Φ(|beta/se|))` |
| `beta_market_252` | 회귀계수 | rolling OLS | EOD t | KOSPI 일수익률 계수 |
| `beta_r2_252` | [0,1] | rolling OLS | EOD t | `1-SSE/SST`; 상수 포함 회귀 R² |
| `stock_mean_return_252` | 연율 소수 | 파생 | EOD t | `252 × mean(stock_return_daily)` |
| `stock_volatility_252` | 연율 소수 | 파생 | EOD t | `sqrt(252) × sd(stock_return_daily, ddof=1)` |
| `cluster_id` | 1~4 | 월별 K-means | EOD t | cluster β 중앙값 오름차순 canonical label |
| `cluster_changed` | bool | 파생 | EOD t | 전월 공통 종목의 canonical cluster가 바뀌면 1 |

## 산업 환율 노출·군집 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `beta_median` | 회귀계수 | 파생 | EOD t | 산업 내 적격 종목 `beta_fx_252` 중앙값 |
| `beta_iqr` | 회귀계수 | 파생 | EOD t | 75% 분위수 - 25% 분위수 |
| `beta_positive_share` | [0,1] | 파생 | EOD t | `beta_fx_252>0` 종목 비율 |
| `beta_significant_share` | [0,1] | 파생 | EOD t | `beta_fx_pvalue_252<0.05` 종목 비율 |
| `beta_se_median` | 회귀계수 단위 | 파생 | EOD t | 산업 내 β 표준오차 중앙값 |
| `beta_r2_median` | [0,1] | 파생 | EOD t | 산업 내 β 회귀 R² 중앙값 |
| `cluster_share_1` | [0,1] | 파생 | EOD t | 산업 내 cluster 1 종목 비율 |
| `cluster_share_2` | [0,1] | 파생 | EOD t | 산업 내 cluster 2 종목 비율 |
| `cluster_share_3` | [0,1] | 파생 | EOD t | 산업 내 cluster 3 종목 비율 |
| `cluster_share_4` | [0,1] | 파생 | EOD t | 산업 내 cluster 4 종목 비율; Ridge 기준범주 |
| `cluster_migration_share` | [0,1]/NA | 파생 | EOD t | 산업별 전월·현재월 cluster 적격 공통 종목 중 label 변경 비율; 공통 3종목 미만이면 NA |
| `cluster_ari` | [-1,1]/NA | 파생 | EOD t | 전체 공통 종목 label의 `adjusted_rand_score`; 공통 4종목 미만이면 NA |
| `beta_fx_interaction` | 수익률×계수 | 파생 | EOD t | `beta_median × fx_USDKRW_return_monthly` |

## 기본 predictor 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `sector_excess_return_t` | 소수 | 파생 | EOD t | `sector_excess_return(j,t)` |
| `sector_excess_return_t_minus_1` | 소수 | 파생 | t-1 종료 후 | `sector_excess_return(j,t-1)` |
| `sector_excess_return_t_minus_2` | 소수 | 파생 | t-2 종료 후 | `sector_excess_return(j,t-2)` |
| `sector_excess_vol_12m` | 소수 | 파생 | EOD t | `sd(X(j,t-11:t), ddof=1)`; 12개 모두 필요 |
| `market_vol_21d` | 연율 소수 | 파생 | EOD t | 최근 21거래일 `sd(KOSPI 일수익률, ddof=1)×sqrt(252)` |
| `fx_USDKRW_return_monthly` | 로그수익률 | 파생 | 환율 t월 자료 공개 후 | t월 `fx_return_daily` 합 |
| `sector_one_hot_*` | 0/1 | 고정 | 항상 | 사전순 기준범주 1개를 제외한 9열 |
| `missing__<field>` | 0/1 | outer/inner 전처리 | 예측 시 | 해당 predictor가 대치 전 결측이면 1; training에 결측이 한 번이라도 있었던 필드만 생성 |

## 네트워크 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `leader_sector` | 범주 | 파생 | t-1 종료 후 | 방향성 edge의 출발 산업 A |
| `follower_sector` | 범주 | 파생 | t-1 종료 후 | 방향성 edge의 도착 산업 B |
| `network_weight` | [-1,1] | 파생 | t-1 종료 후 | 최근 60 pair의 `corr(X_A,s, X_B,s+1)` |
| `network_valid_pairs` | 정수 | 파생 | t-1 종료 후 | edge 추정에 사용한 complete pair 수 |
| `network_pvalue` | [0,1] | permutation | t-1 종료 후 | 1,000회 6개월 circular block 양측 p-value; pair<48 또는 입력 분산 0이면 1 |
| `network_qvalue` | [0,1] | BH-FDR | t-1 종료 후 | 같은 월 90 edge의 보정 p-value |
| `network_edge_selected` | bool | 파생 | t-1 종료 후 | `q<=0.10`, `|w|>=0.20`, pair>=48 |
| `network_signal` | 소수 | 파생 | EOD t | 선택 edge의 `Σw×X_A,t / Σ|w|`; edge 없으면 0 |
| `leader_count` | 정수 | 파생 | EOD t | follower 산업에 선택된 leader 수 |
| `network_weight_abs_sum` | 비음수 | 파생 | t-1 종료 후 | 선택 edge `Σ|w|` |
| `network_active_month` | bool | 파생 | EOD t | 10개 follower 중 하나 이상에 선택 edge가 있으면 1; 보고값이며 표본 gate가 아님 |
| `network_all_edges_ready` | bool | 파생 | t-1 종료 후 | 해당 feature month의 90개 edge가 모두 pair>=48이면 1 |
| `edge_persistence` | [0,1] | OOS 집계 | OOS 평가 후 | ordered edge가 선택된 OOS 월 수 / 네트워크 산출 가능 OOS 월 수 |
| `edge_sign_consistency` | [0,1]/NA | OOS 집계 | OOS 평가 후 | 선택월의 양·음 부호 중 큰 빈도 / 선택월 수; 미선택 edge는 NA |
| `binary_lift` | 0 이상/NA | Binary Lift 민감도 | t-1 종료 후 | `P(up_B,s+1=1|up_A,s=1)/P(up_B,s+1=1)` |
| `binary_network_signal` | 소수 | Binary Lift 민감도 | EOD t | 선택 edge의 `Σ(lift-1)×X_A,t / Σ(lift-1)`; edge 없으면 0 |

## 조건부 외국인 수급 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `foreign_net_purchase_monthly` | KRW | 공식 자료 조건부 | `UNRESOLVED-05` | t월 외국인 순매수금액 합 |
| `foreign_flow_scaled_stock` | 비율 | 파생 | `UNRESOLVED-05` | `foreign_net_purchase_monthly / market_cap(t-1)` |
| `foreign_flow_scaled_sector` | 비율 | 파생 | `UNRESOLVED-05` | 산업 내 적격 종목 `foreign_flow_scaled_stock` 중앙값 |

외국인 수급 필드는 주 분석에 존재하지 않는다. 포함 조건을 모두 통과하지 못하면 schema에서도 제거하고 제외 사유를 기록한다.

## 민감도·비교 표본 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `fx_pair` | 범주 | ECOS `731Y001` | 공개 시각 `UNRESOLVED-03` | USD `0000001`이 주 분석; EUR `0000003`, JPY `0000002`(100엔당 원), CNY `0000053`은 각각 단독 민감도 |
| `beta_fx_504` | 회귀계수 | 504일 rolling OLS | EOD t | 주 β와 같은 회귀식, 최소 400 paired 일별 관측 |
| `krx_index_code` | 문자열 | KRX 지수정보 | 공식 공개 후 | `UNRESOLVED-04` 매핑표의 비교 지수 코드 |
| `krx_mapping_label` | 정확/부분/불가 | 사전 매핑 | 결과 열람 전 | 명칭·구성 정의만으로 판정; 정확·부분 8개 미만이면 비교 제외 |
| `krx_index_return_monthly` | 소수 | KRX 일별 지수 파생 | EOD t | 공식 일별 지수수익률의 월 복리누적 |
| `krx_index_excess_return` | 소수 | 파생 | EOD t | `krx_index_return_monthly-market_return_monthly` |
| `krx_tracking_error` | 소수 | 파생 | EOD t | `legacy sector X(j,t)-matched KRX index X(k,t)` |

## 예측·평가 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `model_id` | 범주 | 모형 | 예측 시 | M0-mean, M0-last, M1, M1N, M2, M3R, M3F, M4R, M4F |
| `prediction` | 소수 | 모형 | forecast_as_of | 다음 달 산업 초과수익률 예측 |
| `actual` | 소수 | target | t+1 종료 후 | `target_primary` |
| `absolute_error` | 소수 | 파생 | t+1 종료 후 | `abs(prediction-actual)` |
| `squared_error` | 수익률 제곱 | 파생 | t+1 종료 후 | `(prediction-actual)^2` |
| `direction_hit` | 0/1/NA | 파생 | t+1 종료 후 | prediction이 0이면 NA, 아니면 부호 일치 여부 |
| `rank_ic_month` | [-1,1] | 파생 | t+1 종료 후 | 월별 산업 예측·실제 Spearman 상관; 8산업 이상 |
| `paired_loss_diff_network` | 소수 | 파생 | t+1 종료 후 | `AE(M4R)-AE(M3R)` |
| `paired_loss_diff_exposure` | 소수 | 파생 | t+1 종료 후 | `AE(M3R)-AE(M1)` |

## 국면·백테스트 필드

| 필드 | 단위/형 | 원천 | 관측 가능 시점 | 정의·변환 |
|---|---|---|---|---|
| `fx_regime` | 강세/중립/약세 | 파생 | EOD t | t월 USD/KRW return을 이전 60개월 1/3·2/3 분위수와 비교 |
| `market_vol_regime` | 저/고 | 파생 | EOD t | t월 21일 변동성을 이전 60개월 중앙값과 비교 |
| `portfolio_weight` | [-0.25,0.25] | M4R rank | forecast_as_of | 상위 2개 +0.25, 하위 2개 -0.25, 나머지 0 |
| `portfolio_turnover` | 비음수 | 파생 | forecast_as_of | `0.5×Σ|w_t-w_{t-1}|` |
| `portfolio_cost` | 소수 | 파생 | forecast_as_of | `0.0020×turnover` |
| `portfolio_net_return` | 소수 | 파생 | t+1 종료 후 | `Σw×sector_return_ew(t+1)-portfolio_cost` |

## 데이터 품질 산출값

| 필드 | 형 | 정의 |
|---|---|---|
| `row_count` | 정수 | source·table별 행 수 |
| `duplicate_key_count` | 정수 | 기대 primary key 중복 수; 허용값 0 |
| `missing_rate` | [0,1] | 필드별 결측 비율 |
| `coverage_start` | 날짜 | 첫 유효 관측일 |
| `coverage_end` | 날짜 | 마지막 유효 관측일 |
| `corporate_action_test_failures` | 정수 | 허용값 0 |
| `future_perturbation_test_pass` | bool | 미래값 변경이 과거 feature를 바꾸지 않으면 1 |
| `target_alignment_test_pass` | bool | 모든 행에서 `target_month=feature_month+1`이면 1 |
| `primary_forecast_month_eligible` | bool | all-edge-ready이고 실제값·paired 예측이 있는 산업이 8개 이상이면 1 |
