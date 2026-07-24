# UI/UX Final Verification

## 자동 검증 결과

- 기준 커밋: `437219d`
- 최종화 작업 브랜치: `codex/ui-ux-audit-improvements`
- 전체 pytest: `542 passed, 2 skipped`
- 신규 핵심 테스트:
  - `tests/test_import_workflow_state.py`
  - `tests/test_processed_messages.py`
  - `tests/test_finalization_app_workflows.py`
  - `tests/test_import_workflow_ui.py`
  - `tests/test_dynamic_ui_localization.py`
  - `tests/test_milestone_record_source.py`
- offscreen 화면 캡처: `16 / 16`
- 캡처 위치: `docs/ux/screenshots/final/`

자동 캡처가 증명하는 범위는 화면 생성, 지정 픽셀 크기 렌더링, 주요 위젯 존재, 예외 없음이다. 실제 Windows 125%에서의 글자 잘림·겹침·포커스 이동은 증명하지 않는다.

## 기능 검증 결과

- 작업별 가져오기 상태가 DB에 독립적으로 저장되고 새 연결에서 복원됨
- source 확인 전 저장 단계가 활성화되지 않으며 종료 상태는 결과 확인만 허용
- 메시지 저장 후 동일 source/hash 재스캔 시 `이미 반영됨` 판정
- 원본 hash 또는 mtime 변경 시 `변경됨·재검토 필요` 판정
- 메시지별 생성·중복·오류 ID가 해당 행에만 연결됨
- 한국어·영어에서 category, reason, status, source, field 표시명이 자연어로 변환됨
- `source:<message-id>` 기존 기록은 `message_auto`, 일반 수동 기록은 `manual`로 반복 안전하게 마이그레이션됨

## Windows 125% 최종 확인 절차

1. Windows 디스플레이 배율을 125%로 설정한다.
2. 1366×768 창에서 대시보드, 달성 기록, 가져오기 센터, 메시지 검토를 연다.
3. 최소 창에서 기본 필터, 표, 주요 행동 버튼과 세로 스크롤에 접근 가능한지 확인한다.
4. 메시지 검토에서 전체·후보·승인·날짜 필요·제외·이미 반영·오류 필터를 차례로 연다.
5. 수동 단건 입력과 메시지 추출 수정 폼에서 날짜, 선수/팀, 필수값 오류가 이해 가능한지 확인한다.
6. 한국어와 영어 각각에서 글자 잘림, 겹침, 비정상 빈 공간, 탭 포커스 이동을 확인한다.
7. 결과를 아래 체크리스트에 기록한다.

## 사용자 체크리스트

- [ ] 1650×900 / 100% / 한국어
- [ ] 1366×768 / 125% / 한국어
- [ ] 최소 창 / 125% / 한국어
- [ ] 1366×768 / 125% / 영어
- [ ] 주요 버튼과 필터 접근 가능
- [ ] 글자 잘림·겹침 없음
- [ ] 키보드 포커스 이동 정상
- [ ] 필요한 페이지에서 세로 스크롤 가능

## CI

`.github/workflows/ui-ux-regression.yml`이 Linux 전체 pytest와 Windows offscreen 핵심 UI·마이그레이션·현지화 검사를 정의한다. 아직 원격 push 전이므로 GitHub Actions 실행 결과와 실행 SHA는 미확인이다.
