# UI/UX 최종 인수 재검수 보고서

## 범위

- 브랜치: `codex/ui-ux-audit-improvements`
- 구현 기준: `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`
- 후속 수정 기준: `docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`
- 작업 소유권: `docs/ux/finalization/LAST_MILE_ASSIGNMENTS.md`

## 최종 판정

**병합 보류 — 주요 구조는 구현됐으나 최종 인수 차단 결함 수정 필요**

W1~W8 작업은 단순 문서나 외형 변경이 아니라 실제 코드로 대부분 구현됐다. 상태 commit, 구조화 import 결과, 날짜 누락 복구, 시즌 카드, 메시지 결과, typed editor와 테스트가 추가된 점은 확인됐다.

그러나 구현 보고서가 주장한 전체 완료 수준에는 도달하지 못했다.

## 용인 가능한 구현

| 영역 | 판정 | 확인 내용 |
|---|---|---|
| W1 상태 영속성 | 통과 | workflow와 processed message가 기본 commit을 사용하며 별도 연결 복원 테스트가 존재함 |
| W2 박스스코어 결과 | 통과 | completed/partial_success/failed/cancelled 구조화 payload와 중앙 저장 경로 구현 |
| W3 날짜 누락 복구 | 통과 | `message_date_required`가 date_needed로 분류되고 날짜 지정 후 실제 재분석됨 |
| W6 기본 결과 라우팅 | 대체로 통과 | workflow_id를 유지해 기록·검토·오류 목적지를 분리함 |
| 출처 DB·화면 | 통과 | boxscore_auto/message_auto/manual/season_final 등 명시적 출처 저장·필터 구현 |

## 최종 인수 차단 결함

### 1. 시즌 최종 판정 시즌 불일치 가능성

가져오기 센터의 분석은 `settings.current_season`을 사용하지만 실제 저장은 `MilestoneView._record_season_ratio_milestones()`가 다시 `season_spin.value() or current_season`을 읽는다. 분석한 시즌과 저장 시즌이 달라질 수 있다.

### 2. 실제 시즌 후보 검토 화면 부재

분석 단계는 후보 수만 상태에 저장하고 기존 달성 기록 화면으로 이동한다. 저장 전에 선수·기록·달성값을 확인하는 후보 목록이 없다.

### 3. 신규 메시지가 과거 완료 상태에 가려질 수 있음

대시보드는 pending 파일 수를 계산하지만 마지막 workflow가 completed면 pending이 있어도 완료를 반환할 수 있다.

### 4. 정책 제외 메시지의 영구 처리 누락

사용자 직접 제외는 processed 상태로 저장하지만 parser가 자동으로 제외한 신규 메시지는 스캔 과정에서 영구 저장되지 않을 수 있다. 동일 파일이 재실행 때 다시 신규로 나타날 수 있다.

### 5. processed 갱신 시 기록 연결 보존 위험

`upsert_processed_message()`의 record ID 목록 인수가 생략돼도 빈 배열로 갱신될 수 있다. 변경 파일을 재검토 상태로 저장할 때 과거 created/duplicate ID를 보존하는 계약이 필요하다.

### 6. 메시지 수정 편집기 문맥 부족

공통 typed editor는 구현됐지만 메시지 수정 다이얼로그가 aggregator/settings/milestones를 전달하지 않는다. 실제 선수 자동완성·ID 변환·팀 및 마일스톤 목록이 수동 입력과 동일하지 않다.

### 7. CSV 출처 축약

달성 기록 화면은 명시적 출처를 사용하지만 CSV 내보내기는 `milestone_is_manual()`의 bool을 사용해 출처를 다시 수동/자동 두 값으로 축약한다.

### 8. 최종 검증 미확정

- 로컬 보고: `576 passed, 2 skipped`
- 집중 테스트 보고: `56 passed`
- scaled offscreen capture: `18 / 18`
- 정확한 제품 SHA의 GitHub Actions 성공: 미확정
- 실제 Windows 125% 데스크톱 검수: 미완료

## 다음 작업

다음 최상위 문서의 A1~A5를 수행한다.

- `docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`

해당 문서는 시즌 판정 core 서비스·후보 검토, 메시지 스캔 정합성, 편집기 문맥 전달, CSV 출처와 결과 복원, 독립 CI·Windows 검증을 구체적으로 지시한다.

모든 인수 조건이 통과되기 전에는 이 문서를 `최종 완료 보고서`로 변경하지 않는다.
