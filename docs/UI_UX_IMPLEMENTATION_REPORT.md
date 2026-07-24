# UI/UX 최종화 구현 보고서

## 판정

`docs/UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md`의 기능 연결 결함을 보완했다. 영구 작업 상태, 실제 단계 라우팅, 메시지 기존 반영 감지, 행별 저장 결과, 동적 현지화, 출처 마이그레이션 및 재현 가능한 CI 구성을 구현했다.

실제 Windows 125% 시각 검수와 GitHub Actions 원격 실행은 아직 수행되지 않았으므로 `UI/UX 전면 개선 전체 완료`로 판정하지 않는다.

## 완료

- F0: 기준 커밋 `437219d`, 기준 테스트 `517 passed, 2 skipped`, 재현 결함과 작업 소유권을 `docs/ux/finalization/BASELINE.md`에 고정했다.
- F1: `latest_boxscores`, `news_messages`, `baseline_history`, `season_finalize`의 독립 DB 상태와 5단계 상태 계약, 완료·부분 성공·실패·취소 결과를 추가했다.
- F1/F2: 가져오기 센터의 단계별 동작과 버튼 활성화를 실제 상태에 연결하고, 대시보드가 DB 실행 이력·초기 기록·신규 파일·메시지·미해결 항목을 계산하도록 변경했다.
- F3: 뉴스 메시지 재분석 콜백, source ID·파일 해시·mtime 기반 기존 반영/변경 감지, 승인 항목 전용 저장, 메시지별 생성·중복·오류 결과를 구현했다.
- F4: 메시지 category·제외 사유·검토 상태·출처·추출 필드의 한국어/영어 표시 매핑을 추가하고 내부 코드 노출 회귀 테스트를 추가했다.
- F6: `notes`의 `source:<message-id>`를 우선해 기존 뉴스 자동 기록을 `message_auto`로 분류하고, 일반 수동 기록은 `manual`로 유지하는 반복 안전 마이그레이션과 요약 메타데이터를 추가했다.
- F8: Linux 전체 회귀와 Windows offscreen smoke 검사를 실행하는 `.github/workflows/ui-ux-regression.yml`을 추가했다.

## 부분 완료

- F5: 수동 입력과 메시지 수정이 `GuidedMilestoneForm`과 수동 입력 검증 함수를 공유한다. 다만 메시지 수정 폼의 선수 자동완성·팀 선택 목록은 기존 수동 단건 다이얼로그 수준으로 완전히 통합되지 않았고, 안내형 라벨 기반 편집으로 제공된다.
- 최신 박스스코어는 기존 importer가 분석과 저장을 한 작업으로 수행하므로 상태 계약에서는 원본 확인 후 실제 importer 실행, 결과 확인으로 연결된다. 뉴스 메시지는 검토와 저장이 분리되어 있다.
- `messages.dat` 날짜 자동 해석기는 이번 범위에 추가하지 않았다. 날짜가 필요한 메시지는 `날짜 필요` 상태에서 달력 입력으로 보완한다.

## 미구현

- 실제 Windows 데스크톱의 1366×768 / 125%와 최소 창 / 125%에서 한국어·영어 글꼴, 잘림, 겹침, 키보드 포커스를 수동 확인하지 못했다.
- 새 GitHub Actions 워크플로는 로컬에 추가했지만 아직 원격 push 전이므로 실행 URL과 Actions SHA가 없다.

## 검증

- 전체 회귀: `542 passed, 2 skipped` (`2026-07-24`, Python 가상환경, `QT_QPA_PLATFORM=offscreen`)
- 신규 핵심 검증: 작업별 상태 독립 저장·재시작 복원, 단계 순서, 처리 메시지 재스캔, 행별 저장 결과, 출처 반복 마이그레이션, 동적 현지화, 앱 단계 연결
- 자동 화면 검증: 한국어·영어 16개 화면 모두 생성, 지정 픽셀 크기, 주요 위젯 생성, 예외 없음
- 자동 캡처는 Windows 125%에서의 텍스트 무잘림이나 조작 가능성을 증명하지 않는다.
- CI 구성: `.github/workflows/ui-ux-regression.yml`; 원격 실행은 push 후 확인 필요

## 모델 배분

- GPT-5.6 Sol: 기준선, 작업 분해, 파일 소유권, 교차 통합, 마이그레이션, CI, 전체 검증 및 보고
- GPT-5.5: 영구 작업 상태, processed message 저장소, 행별 적용 결과, 가져오기 상태 UI, 메시지 검토·공통 폼·현지화
- Sonnet 5: 가져오기 GUI 및 현지화 범위를 두 차례씩 큰 범위와 축소 범위로 배정했으나 실행 제한 시간 내 변경을 남기지 못했다. 해당 작업은 지시서의 재배정 규칙에 따라 GPT-5.5가 수행했다.

## 사용자 확인 필요

- 실제 Windows 디스플레이 배율을 125%로 설정하고 `docs/ux/finalization/FINAL_VERIFICATION.md`의 순서대로 주요 화면의 글자 잘림·겹침·포커스·스크롤을 확인한다.
- 브랜치를 push한 뒤 `UI UX regression` GitHub Actions의 Linux 전체 회귀와 Windows UI smoke 결과를 확인한다.
