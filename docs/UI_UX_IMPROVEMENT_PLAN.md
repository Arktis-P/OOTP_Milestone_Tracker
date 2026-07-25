# UI/UX 개선 구현 계획

> **현재 최상위 지시서:** [`UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`](UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md)  
> 선행 잔여 작업 지시서: [`UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md)  
> 최초 감사 기준: [`OOTP_Milestone_Tracker_UI_UX_Audit.md`](OOTP_Milestone_Tracker_UI_UX_Audit.md)

## 현재 판정

W1~W8 구현으로 주요 UI 구조와 대부분의 자동화 흐름은 완성됐다. 다음 항목은 용인 가능한 수준으로 구현됐다.

- 가져오기·처리 메시지 상태의 기본 영속성
- 박스스코어 구조화 결과와 네 종료 상태
- 날짜 누락 메시지 재분석
- 기본 메시지 검토·출처·결과 라우팅
- typed guided editor의 공통 기반

그러나 최신 인수 검수에서 데이터 정확성에 영향을 줄 수 있는 결함이 남아 있어 현재 브랜치를 최종 완료로 판정하지 않는다.

1. 시즌 최종 판정의 분석 시즌과 저장 시즌이 달라질 수 있음
2. 시즌 후보의 실제 검토 목록이 없음
3. 과거 뉴스 작업 완료 상태가 현재 신규·변경 파일을 가릴 수 있음
4. 정책상 자동 제외된 메시지가 처리 상태에 저장되지 않을 수 있음
5. 메시지 수정 편집기에 실제 선수·팀·마일스톤 문맥이 전달되지 않음
6. CSV 내보내기에서 명시적 출처가 수동/자동으로 축약됨
7. 최종 제품 SHA의 CI 성공과 실제 Windows 125% 증거가 확정되지 않음

## 이후 작업 기준

오케스트레이터는 범위를 다시 설계하지 않고 다음 문서의 A1~A5를 그대로 분배한다.

- `docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`

### A1 — 시즌 최종 판정

- 명시적 season/request를 사용하는 core 서비스
- 실제 후보 검토 화면
- 분석 후 export 변경 감지
- 분석·검토·저장 시즌 일치

### A2 — 메시지 정합성

- 정책 제외 상태 영속화
- 신규·변경 파일이 과거 completed보다 우선하도록 대시보드 수정
- processed 갱신 시 기존 record ID 보존
- 전체 review model 기반 완료 판정

### A3 — 메시지 수정 문맥

- MessageReviewView에 aggregator/settings/milestones 전달
- 수동 입력과 동일한 선수·팀·기록 선택 및 검증
- source provenance 읽기 전용 유지

### A4 — 출처와 결과 복원

- CSV에서 명시적 source 보존
- 앱 재시작 후 마지막 결과 summary 복원
- persisted 오류 보고서의 실제 확인 경로

### A5 — 독립 인수 검수

- 전체·집중 테스트
- 정확한 제품 SHA의 GitHub Actions 성공
- 실제 Windows 125% 검증 또는 미완료 사용자 게이트
- 구현 보고서와 검증 문서 정합성

## 오케스트레이터 규칙

- 저장소 전체를 다시 분석하는 계획서를 작성하지 않는다.
- A1~A5 담당자와 파일 소유권만 확정하고 구현한다.
- `gui/app.py`는 한 담당자 또는 오케스트레이터가 순차 통합한다.
- 테스트 기대값만 변경해 현재 동작을 정당화하지 않는다.
- 후보 수만 보여주는 화면을 후보 검토 완료로 간주하지 않는다.
- CI 파일 존재와 offscreen PNG 생성을 최종 검증으로 간주하지 않는다.

## 최종 완료 조건

세부 구현 방법, 테스트, 사용자 시나리오와 완료 금지 조건은 `UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`를 따른다. 해당 문서의 11절을 모두 통과하기 전에는 `UI/UX 전면 개선 완료` 또는 `병합 가능`으로 보고하지 않는다.
