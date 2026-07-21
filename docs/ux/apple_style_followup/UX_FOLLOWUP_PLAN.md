# Follow-up Plan

1. 기준: 스킬에 정량 목표·Windows 매트릭스·타입 역할·상태 복원/복구 규칙을 추가한다.
2. 기반: `gui/theme.py`의 타입 역할, 포커스, 고대비 표현을 정리한다.
3. 상태: 기존 설정 JSON에 전역 window state와 세이브별 view state를 분리해 저장·복원한다.
4. 후속 행동: 대량 편집 결과 위치 열기와 가져오기 실패 재시도를 추가한다.
5. 검증: 집중 테스트 후 전체 pytest, py_compile, diff check, offscreen 캡처를 수행한다.

## 의존 관계와 충돌

- UX-FU-01과 UX-FU-02는 파일이 겹치지 않아 병렬 수행한다.
- UX-FU-03 완료 후 `gui/app.py` 상태 계약을 기준으로 화면 접근성 작업을 검토한다.
- `gui/theme.py`, `gui/app.py`, `core/config/settings_manager.py`, `initial_import_view.py`, `bulk_rating_dialog.py`는 각각 단일 작업자만 소유한다.

## 완료 기준

- 상태가 다른 세이브에 잘못 적용되지 않는다.
- 키보드 포커스와 타입 역할이 offscreen 렌더·테스트에서 확인된다.
- 실패·저장 완료 후 사용자가 다음 행동을 화면에서 바로 선택할 수 있다.
- 전체 회귀와 문서-구현 정합성이 통과한다.
