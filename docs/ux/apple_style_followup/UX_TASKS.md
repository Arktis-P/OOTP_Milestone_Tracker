# UX Follow-up Tasks

## UX-FU-01 — 프로젝트 UX 기준 보강

- 상태: completed
- 구현: GPT-5.5
- 파일: `.skills/ootp-milestone-ux/SKILL.md`, `UX_VERIFICATION.md`
- 결과: 반응성 수치, Windows 배율·고대비·키보드 매트릭스, 전역/세이브별 상태 규칙, 복구 원칙과 타입 역할을 추가했다.
- 검증: frontmatter에 `name`/`description`만 존재, 138줄, placeholder 없음.

## UX-FU-02 — 공통 테마와 고대비

- 상태: completed
- 구현: GPT-5.5
- 파일: `gui/theme.py`, `tests/test_theme_accessibility.py`
- 결과: 타입 역할 selector, focus/hover/selected/disabled 상태, 색상 외 선택·경고 단서, 선택적 고대비 override를 추가했다.
- 검증: 테마·offscreen 테스트 4 passed.

## UX-FU-03 — 전역/세이브별 상태 복원

- 상태: completed
- 구현: GPT-5.5
- 파일: `core/config/settings_manager.py`, `gui/app.py`, `gui/views/stats_view.py`, `tests/test_ui_state_restore.py`
- 결과: 창 geometry·마지막 화면은 전역으로, Stats splitter·모드·시즌은 해시된 세이브 키별로 저장한다. 화면 밖 geometry와 없는 시즌에는 안전한 fallback을 적용한다.
- 검증: 상태 복원 테스트 11 passed.

## UX-FU-04 — 핵심 화면 접근성

- 상태: completed
- 구현: GPT-5.5
- 파일: `gui/sidebar_nav.py`, `gui/views/predict_view.py`, `gui/widgets/player_detail_summary.py`, `tests/test_accessibility_followup.py`
- 결과: 주요 컨트롤의 accessible name/description, StrongFocus, 고배율 wrapping/minimum sizing, 타입 역할을 보강했다. Near 상태는 Status 열과 tooltip로 색상 외 단서를 유지한다.
- 검증: 접근성 offscreen 테스트 3 passed.

## UX-FU-05 — 대량 편집 저장 결과 액션

- 상태: completed
- 구현: GPT-5.5
- 파일: `gui/widgets/bulk_rating_dialog.py`, `core/i18n/translator.py`, `tests/test_bulk_rating_preview_ux.py`
- 결과: 변경 수, 출력·백업 전체 경로, 복원 안내, 출력/백업 폴더 열기 액션을 제공한다. 폴더 열기 실패 시에도 경로를 보존한다.
- 검증: 관련 집중 테스트를 포함한 통합 집중 테스트 30 passed.

## UX-FU-06 — 초기 가져오기 취소·재시도·부분 실패

- 상태: completed
- 구현: GPT-5.5
- 파일: `gui/views/initial_import_view.py`, `gui/workers/initial_import_worker.py`, `core/i18n/translator.py`, `tests/test_initial_import.py`
- 결과: 파일 경계 cooperative cancel, 즉시 취소 요청 피드백, 입력·모드 보존 Retry, preview 무변경과 persist 부분 저장 가능성의 구분 안내를 구현했다.
- 검증: 초기 가져오기 테스트 11 passed.
