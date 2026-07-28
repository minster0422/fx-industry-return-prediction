# Changelog

## [0.2.1] - 2026-07-28

### Added

- 연구 파생을 전부 차단한 KRX archive-only 수집기와 명시적 실행 gate
- KST 일일 quota, 250회 reserve, SQLite checkpoint, SHA-256 재검증, 단일 프로세스 lock과 원자적 저장
- 2010-01-04~2026-06-30 KRX 원응답 계획 12,908건의 로컬 보존 완료
- endpoint별 요청·행·용량과 local manifest 해시만 담은 공개 archive 요약
- archive 범위·완결성·이용조건·공개 경계를 정리한 보존 보고서
- invalid JSON 재시도, 잘못된 기존 파일 거부, 중복 실행 차단과 파생 기능 금지 회귀 테스트

### Verified

- 완료 checkpoint 12,908건과 유효 gzip 원본 12,908건 일치, 남은 요청 0건
- 총 9,301,468행, gzip 535,466,270 bytes, 비압축 2,961,927,978 bytes
- 수익률, target, 모델, 예측, 성능, 백테스트와 `results/v2_1/` 미생성
- 인증키·원자료·요청별 manifest·checkpoint는 Git 추적 대상이 아님

### Not included

- 기업행사 조정이나 공개시각을 임의 가정한 연구용 변환
- ECOS 운영 수집
- V2.1 프로토콜 동결과 실증 결과

## [0.2.0] - 2026-07-26

### Added

- 결과 확인 전에 연구 선택을 고정하는 V2.1 사전등록형 프로토콜과 기계 판독 설정
- KRX·ECOS 데이터 가능성 감사, source registry, 데이터 사전과 결정 로그
- U0 Legacy-50의 KRX 공식 코드 50/50 매핑과 명칭 변경 provenance
- 고정 5종목·KOSPI 제한 스키마 검증과 API별 종목코드 회귀 테스트
- 프로토콜 동결 전 전체수집을 차단하는 U0 수집기 plan·dry-run·checkpoint 골격
- 포트폴리오 요약과 외부 공식 근거 확보 후 재개할 V2.1 로드맵

### Changed

- U0 Legacy-50을 V2.1 기본 표본으로 유지하고 U1 Expanded-10을 V2.2 후보로 이관
- V2.1 실증 결과와 현재 완료된 재구성·연구설계 산출물을 명확히 분리

### Not included

- V2.1 전체기간 원자료 수집, target, 모델 학습, 예측, 성능평가와 백테스트
- 재배포 조건이 확정되지 않은 KRX·ECOS 원자료와 인증키

## [0.1.0] - 2026-07-14

- 2025 학부 팀 연구의 논문·PPT·발표 대본·R 코드·CSV 재구성
- 불일치 감사와 누수 없는 V2 proof-of-concept 기준선
- 실행 가능한 Python 패키지, 테스트와 GitHub Actions CI
