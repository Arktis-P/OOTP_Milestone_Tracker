# UI/UX 개선 구현 계획

> **현재 최상위 지시서:** [`UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md)  
> 선행 최종화 지시서: [`UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md)  
> 최초 오케스트레이션 지시서: [`UI_UX_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_ORCHESTRATOR_DIRECTIVE.md)  
> 감사 기준: [`OOTP_Milestone_Tracker_UI_UX_Audit.md`](OOTP_Milestone_Tracker_UI_UX_Audit.md)

## 현재 상태

현재 브랜치는 UI 구조 개편, 가져오기 상태 모델, 메시지 기존 반영 감지, 재분석, 동적 현지화, 출처 마이그레이션과 CI 파일까지 구현된 상태다.

다만 최신 검수에서 다음 핵심 결함이 확인됐다.

1. 가져오기 상태와 처리 메시지 상태의 commit 경계가 명확하지 않아 앱 재실행 후 영속성이 보장되지 않을 수 있음
2. 박스스코어 완료·부분 성공·실패·취소 상태가 실제 worker 결과와 모두 연결되지 않음
3. `message_date_required` 메시지가 `날짜 필요`가 아니라 `제외`로 분류돼 복구할 수 없음
4. 시즌 최종 판정 행동이 실제 실행 기능으로 연결되지 않음
5. 사용자 제외·미처리 수·신규/변경 메시지 계산과 뉴스 작업 완료 판정이 불완전함
6. 결과·오류 버튼이 작업 유형별 목적지로 완전히 분리되지 않음
7. 메시지 수정과 수동 입력의 공통 폼이 번역된 2열 문자열 표 수준에 머물러 있음
8. GitHub Actions 실제 성공 실행과 Windows 125% 실검수가 남아 있음

따라서 현재 상태를 `UI/UX 전면 개선 완료`로 판정하지 않는다.

## 이후 작업 기준

오케스트레이터는 더 이상 이 문서를 기반으로 구현 범위를 재설계하지 않는다. 다음 최상위 문서의 W1~W8을 하위 작업자에게 그대로 분배한다.

- `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`

해당 문서에는 다음이 포함돼 있다.

- 작업별 문제와 원인
- 구체적인 구현 방법
- 수정 대상 파일과 함수
- 작업 선행 관계
- 파일 소유권 원칙
- 필수 단위·통합 테스트
- 실제 사용자 검수 시나리오
- CI와 Windows 125% 검증 절차
- 최종 완료·완료 금지 조건

## 오케스트레이터 운영 규칙

- 저장소 전체를 다시 분석하는 장문의 계획을 작성하지 않는다.
- W1~W8 담당자와 파일 소유권만 확정한 뒤 바로 구현을 시작한다.
- 같은 파일을 여러 하위 작업자가 동시에 수정하지 않는다.
- `gui/app.py`는 한 담당자 또는 오케스트레이터가 순차 통합한다.
- 테스트 추가만으로 완료하지 않고 실제 앱 재실행·결과 상태·화면 이동을 확인한다.
- offscreen 캡처는 Windows 125% 실검수를 대체하지 않는다.
- GitHub Actions 파일 존재가 아니라 실제 성공 run을 확인한다.

## 최종 완료 조건

세부 완료 조건은 `UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`의 14절과 15절을 따른다. 해당 조건을 모두 통과하기 전에는 최종 완료로 보고하지 않는다.
