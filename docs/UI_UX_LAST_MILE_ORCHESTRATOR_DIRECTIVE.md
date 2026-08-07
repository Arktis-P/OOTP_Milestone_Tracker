# OOTP Milestone Tracker UI/UX 최종 잔여 작업 오케스트레이터 지시서

## 0. 문서 지위

이 문서는 `codex/ui-ux-audit-improvements` 브랜치의 UI/UX 개선을 실제 완료 상태까지 마무리하기 위한 **최종 잔여 작업 전용 지시서**다.

- 대상 브랜치: `codex/ui-ux-audit-improvements`
- 선행 지시서: `docs/UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md`
- 현재 구현 보고서: `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- 자동 검증 문서: `docs/ux/finalization/FINAL_VERIFICATION.md`
- 기준선 문서: `docs/ux/finalization/BASELINE.md`
- 이 문서는 선행 지시서의 미완료 항목을 구체화한 마지막 후속 문서다.
- 선행 문서와 충돌하면 **이 문서의 구현 방법·완료 조건·검증 기준이 우선한다.**

현재 구현은 주요 구조를 이미 갖췄다. 이번 작업에서는 화면을 다시 설계하거나 기존 구현을 폐기하지 않는다. 다음 여덟 개 잔여 작업만 완성하고, 실제 동작과 증거를 확인한 뒤 종료한다.

1. 가져오기 작업 상태와 메시지 처리 상태의 실제 영속성 보장
2. 박스스코어 완료·부분 성공·실패·취소의 상태 연결
3. 날짜 누락 메시지를 복구 가능한 검토 상태로 처리
4. 시즌 최종 판정의 실제 실행 경로 연결
5. 메시지 제외·미처리·신규·변경 상태와 완료 판정 정합성
6. 작업 유형별 결과 화면과 오류 화면 라우팅
7. 수동 입력과 메시지 수정의 실제 공통 안내형 폼 완성
8. CI·Windows 125% 검증과 최종 보고 정리

---

# 1. 오케스트레이터 역할

오케스트레이터는 이 문서를 읽고 다시 기능을 탐색하거나 장문의 새 계획서를 작성하지 않는다. 다음만 수행한다.

1. 아래 작업 패키지 W1~W8을 하위 작업자에게 배정한다.
2. 파일 소유권과 선행 관계를 지킨다.
3. 각 작업자의 결과를 지정된 테스트와 사용자 시나리오로 검수한다.
4. 공통 파일 충돌과 신호 연결만 직접 통합한다.
5. 전체 테스트·CI·실제 화면 검증 증거를 확인한다.
6. 완료 조건을 모두 만족할 때만 최종 완료로 보고한다.

오케스트레이터가 다시 조사해야 하는 범위는 다음 두 경우뿐이다.

- 문서에 명시된 함수나 파일이 최신 코드에서 이름이 변경된 경우
- 기존 시즌 최종 판정 엔진의 실제 진입점이 여러 개라 하나를 선택해야 하는 경우

그 외에는 아래 참조 파일과 구현 방법을 그대로 사용한다.

## 1.1 작업 배정표 필수 형식

작업 시작 전에 아래 형식으로 담당자를 확정한다.

| 작업 | 담당 | 소유 파일 | 수정 금지 파일 | 선행 작업 | 제출 증거 |
|---|---|---|---|---|---|
| W1 |  |  |  | 없음 | 테스트·커밋 |
| W2 |  |  |  | W1 | 테스트·커밋 |
| W3 |  |  |  | 없음 또는 W1 | 테스트·커밋 |
| W4 |  |  |  | W1 | 테스트·커밋 |
| W5 |  |  |  | W1, W3 | 테스트·커밋 |
| W6 |  |  |  | W2, W5 | 테스트·커밋 |
| W7 |  |  |  | W3 | 테스트·커밋 |
| W8 | 독립 검수자 | 검증·문서·CI | 제품 코드 원칙적 금지 | W1~W7 | 실행 증거 |

같은 파일을 둘 이상의 작업자가 동시에 수정하지 않는다. 공통 파일인 `gui/app.py`는 W2·W4·W6의 개별 결과를 받은 뒤 오케스트레이터가 순차 통합하거나 한 명에게만 전담시킨다.

## 1.2 권장 배분

- 데이터 영속성·메시지 상태: GPT-5.5 또는 동급 백엔드 작업자
- Qt 신호·화면 라우팅·공통 폼: Sonnet 5 또는 동급 GUI 작업자
- 시즌 판정 연결·교차 통합: GPT-5.6 Sol
- 최종 검수: 구현에 참여하지 않은 별도 작업자

모델 이름보다 파일 소유권과 독립 검수가 우선한다.

---

# 2. 필수 참조 자료

하위 작업자에게 저장소 전체를 다시 읽히지 말고 작업별로 아래 파일만 전달한다.

## 2.1 공통 문서

- `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`
- `docs/UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md`
- `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- `docs/ux/finalization/FINAL_VERIFICATION.md`

## 2.2 핵심 상태·DB 코드

- `core/import_workflow.py`
  - `save_import_workflow_state`
  - `start_import_workflow`
  - `advance_import_workflow`
  - `finish_import_workflow`
- `core/app_state.py`
  - `get_dashboard_import_states`
- `core/db/schema.py`
  - `_ensure_milestone_records_source`
- `core/db/sqlite_config.py`
- `core/stats/aggregator.py`

## 2.3 메시지 자동화 코드

- `core/milestone/message_automation/processed.py`
  - `upsert_processed_message`
  - `get_message_rescan_status`
- `core/milestone/message_automation/parser.py`
- `core/milestone/message_automation/extract.py`
- `core/milestone/message_automation/recorder.py`
- `core/milestone/message_automation/service.py`

## 2.4 GUI 연결 코드

- `gui/app.py`
- `gui/views/dashboard_view.py`
- `gui/views/import_center_view.py`
- `gui/views/message_review_view.py`
- `gui/widgets/import_workflow_status.py`
- `gui/widgets/message_review_model.py`
- `gui/widgets/guided_milestone_form.py`
- `gui/widgets/manual_milestone_dialog.py`
- `gui/widgets/single_record_dialogs.py`
- `gui/workers/import_worker.py`

## 2.5 기존 테스트

- `tests/test_import_workflow_state.py`
- `tests/test_import_workflow_ui.py`
- `tests/test_finalization_app_workflows.py`
- `tests/test_processed_messages.py`
- `tests/test_message_review_ui.py`
- `tests/test_dynamic_ui_localization.py`
- `tests/test_milestone_record_source.py`
- `tests/test_responsive_layout.py`

---

# 3. W1 — 상태 영속성과 트랜잭션 경계 수정

## 3.1 문제

현재 `save_import_workflow_state()`와 `upsert_processed_message()`는 SQL을 실행하지만 함수 자체에서 영속 완료를 보장하지 않는다. 기존 테스트는 외부에서 직접 `commit()`한 뒤 재연결하므로 실제 앱 종료·재실행 경로를 검증하지 못한다.

결과적으로 다음이 발생할 수 있다.

- 작업 완료 상태가 앱 종료 후 사라짐
- 처리 메시지가 다시 신규 후보로 나타남
- 미커밋 쓰기 트랜잭션이 백그라운드 importer의 DB 접근을 막음
- 실패·취소 직후 상태가 화면에는 보이나 DB에는 남지 않음

## 3.2 구현 원칙

상태 저장 함수가 성공적으로 반환되면, 별도 외부 `commit()` 없이 새 SQLite 연결에서 같은 상태를 읽을 수 있어야 한다.

다음 중 하나를 선택한다.

### 권장안 A — 명시적 commit 옵션

```python
def save_import_workflow_state(conn, state, *, commit: bool = True):
    ...
    if commit:
        conn.commit()
```

`start_import_workflow`, `advance_import_workflow`, `finish_import_workflow`도 `commit`을 전달한다. 일반 GUI 호출은 기본 `True`를 사용한다.

`upsert_processed_message()`도 동일한 `commit: bool = True` 계약을 둔다.

여러 쓰기를 하나의 원자 작업으로 묶어야 하는 호출자는 `commit=False`로 호출하고 최상위 서비스에서 한 번만 `conn.commit()`한다. 예외 발생 시 `rollback()`한다.

### 허용안 B — 전용 transaction context

상태 저장소 계층에 명시적인 transaction helper를 만들고, 모든 GUI·서비스 호출이 해당 helper를 거쳐 commit/rollback하도록 한다.

단순히 테스트에서 `conn.commit()`을 추가하는 방식은 금지한다.

## 3.3 처리 메시지 저장의 원자성

`record_parsed_message_result()`는 생성 기록과 `processed_messages` 결과가 불일치하지 않도록 해야 한다.

현 구조의 `record_manual_*`가 내부 commit을 수행한다면 최소 보장 조건은 다음과 같다.

1. 기록 생성 성공 후 `processed_messages` 저장도 반드시 commit
2. 처리 상태 저장 실패 시 오류를 삼키지 않고 호출자에게 전달
3. 다음 스캔에서 생성된 기록을 중복 조회해 `already_applied` 또는 `duplicate`로 복구 가능

가능하면 수동 기록 메서드에 `commit=False` 옵션을 추가해 기록 생성과 처리 상태를 하나의 트랜잭션으로 묶는다. 범위가 과도하면 이번 작업에서는 내구성 보장과 복구 테스트를 우선한다.

## 3.4 수정 대상

주 소유 파일:

- `core/import_workflow.py`
- `core/milestone/message_automation/processed.py`
- 필요 시 `core/milestone/message_automation/recorder.py`
- 필요 시 `core/milestone/checker.py`

테스트:

- `tests/test_import_workflow_state.py`
- `tests/test_processed_messages.py`
- 신규 `tests/test_state_persistence_boundaries.py`

## 3.5 필수 테스트

1. 상태 저장 후 외부 commit 없이 기존 연결을 닫고 새 연결에서 복원
2. `completed`, `partial_success`, `failed`, `cancelled` 각각 복원
3. 네 작업 상태가 서로 덮어쓰지 않음
4. 처리 메시지 저장 후 외부 commit 없이 재연결해 `already_applied`
5. 제외 메시지 저장 후 재연결해 `excluded`
6. 원본 hash 변경 후 재연결해 `changed_review_needed`
7. 상태 저장 직후 별도 연결에서 읽을 수 있어 DB 잠금이 남지 않음
8. 저장 중 예외가 발생하면 잘못된 완료 상태를 남기지 않음

## 3.6 완료 조건

- 테스트가 자체적으로 `conn.commit()`을 호출하지 않는다.
- 앱 종료·재실행 시 상태가 유지된다.
- 오케스트레이터가 테스트 코드를 확인해 외부 commit으로 결함을 숨기지 않았음을 검수한다.

---

# 4. W2 — 박스스코어 실행 결과를 워크플로 상태에 정확히 연결

## 4.1 문제

현재 UI는 import 완료 문자열만 MainWindow에 전달하는 경로가 있으며, 실제 payload의 오류 수·취소·실패를 중앙 상태가 알지 못할 수 있다. 완료 콜백이 무조건 `completed`를 저장해서 부분 오류가 완료로 표시될 가능성이 있다.

## 4.2 구현 구조

사람이 읽는 문자열을 파싱해서 상태를 결정하지 않는다. `ImportFinishedPayload` 또는 새 정규화 결과 객체를 그대로 전달한다.

권장 계약:

```python
@dataclass(frozen=True)
class ImportWorkflowCompletion:
    outcome: str
    processed: int
    created: int
    duplicates: int
    excluded: int
    errors: int
    unresolved: dict[str, int]
    message: str
```

기존 `ImportFinishedPayload`로 충분하면 새 객체를 만들지 말고 payload에서 직접 계산한다.

## 4.3 신호 연결

박스스코어를 실행할 수 있는 모든 화면을 확인한다.

- `DashboardView`
- `MilestoneView`
- `StatsView`
- 기타 `ImportWorker` 생성 위치

각 화면은 최소 다음 신호를 상위로 전달한다.

- 성공/부분 성공: 구조화 payload
- 실패: 오류 문자열 또는 예외 정보
- 취소: 취소 메시지

MainWindow 또는 단일 coordinator는 다음 상태를 저장한다.

### 완료

- 오류 0
- 작업 정상 종료
- `OUTCOME_COMPLETED`

### 부분 성공

- 일부 파일 또는 후속 마일스톤/연속기록 처리 오류 존재
- 성공 기록도 존재
- `OUTCOME_PARTIAL_SUCCESS`
- `unresolved.errors > 0`

### 실패

- 성공적으로 처리된 항목 없이 작업 중단
- `OUTCOME_FAILED`

### 취소

- 사용자가 취소
- 이미 반영된 수가 있더라도 outcome은 `OUTCOME_CANCELLED`
- 처리된 수는 totals에 보존

## 4.4 단계 상태

박스스코어 importer는 분석과 저장이 하나의 실행으로 묶여 있으므로 다음 축약 흐름을 사용한다.

1. `source_check`
2. `analyze_classify` 버튼 실행
3. 실행 직전 `save` 또는 실행 중 상태로 전환
4. 종료 후 `confirm_result`

화면에 존재하는 `review_results` 단계는 실행 결과 요약을 보는 단계로 사용하며, 가짜 별도 분석을 만들지 않는다.

## 4.5 결과 수치

가능한 실제 payload 필드를 사용해 최소 다음을 저장한다.

- processed: 확인한 파일 수
- created: 새 경기 또는 새 기록 수 중 사용자에게 가장 일관된 기준
- duplicates: 이미 처리된 파일 수
- errors: 오류 수
- unresolved.errors: 검토가 필요한 오류 수

`created`의 정의를 한 번 정한 뒤 대시보드·가져오기 센터·결과 배너에서 동일하게 사용한다.

## 4.6 수정 대상

- `gui/workers/import_worker.py`
- `gui/views/dashboard_view.py`
- 박스스코어 실행이 있는 다른 view
- `gui/app.py`
- `core/import_workflow.py`의 기존 계약 사용

테스트:

- 신규 `tests/test_boxscore_workflow_outcomes.py`
- `tests/test_finalization_app_workflows.py`
- `tests/test_import_workflow_ui.py`

## 4.7 필수 테스트

1. 정상 완료 → completed
2. 일부 오류와 일부 성공 → partial_success
3. 초기 단계 실패 → failed
4. 사용자 취소 → cancelled
5. 각 결과의 totals/unresolved가 DB에 저장됨
6. 재실행 후 같은 결과 표시
7. 결과 버튼이 작업 유형에 맞는 화면을 엶
8. 실패·취소가 완료 문구를 표시하지 않음

## 4.8 완료 조건

- MainWindow가 완료 문자열만 받고 outcome을 추정하는 코드가 남지 않는다.
- 오류·취소 신호가 배너 표시와 DB 상태 저장을 모두 수행한다.

---

# 5. W3 — 날짜 누락 메시지를 실제로 복구 가능한 상태로 처리

## 5.1 문제

트레이드·FA·연장·부상은 날짜가 없으면 파서가 `excluded=True`, `forms=[]`, `message_date_required`를 반환한다. 현재 검토 모델은 이를 `excluded`로 분류하므로 날짜 입력 버튼을 사용할 수 없다.

## 5.2 구현 방법

이번 범위에서는 parser와 모든 extractor를 대규모 재설계하지 않는다. **날짜 입력 후 재분석 방식**을 사용한다.

### 5.2.1 초기 상태 판정 순서 변경

`MessageReviewItem._initial_status()`는 다음 순서를 따른다.

1. 파일 읽기·파싱 자체 오류 → `error`
2. `exclusion_reason == "message_date_required"` → `date_needed`
3. 기존 반영 → `applied`
4. 기타 정책 제외 → `excluded`
5. 폼에 날짜가 비어 있음 → `date_needed`
6. 폼 존재 → `candidate`
7. 나머지 → `excluded`

즉, `parsed.excluded`보다 `message_date_required`를 먼저 검사한다.

### 5.2.2 날짜 지정 동작

`date_needed` 항목은 두 유형이 있다.

- 폼이 이미 있고 날짜만 비어 있음
- 폼이 없고 `message_date_required`로 제외됨

두 번째 유형은 날짜 입력 시 다음을 수행한다.

1. `item.message_date`에 날짜 저장
2. 앱에서 제공한 `reanalyze_callback(item)` 호출
3. callback이 `message_date=item.message_date`로 parser 재호출
4. 새 ParsedMessage가 폼을 생성하면 `candidate`
5. 여전히 제외되면 해당 제외 사유에 따라 `excluded` 또는 `error`
6. 재분석 오류 시 `error`

모델에 GUI callback을 직접 넣기 어렵다면 View의 `assign_date_to_selected()`에서 날짜 설정과 재분석을 수행하고, 모델에는 순수 상태 갱신 함수만 둔다.

### 5.2.3 승인 규칙

- 날짜를 지정했다고 자동 승인하지 않는다.
- 재분석 후 candidate로 전환한다.
- 사용자가 결과를 확인한 뒤 승인한다.
- 날짜 지정 전에는 저장 대상에 포함되지 않는다.

## 5.3 처리 상태 저장

단순 스캔 단계에서 날짜 누락을 `processed_messages.status=excluded`로 영구 확정하지 않는다.

허용 상태:

- `date_needed`
- 또는 아직 processed_messages에 쓰지 않고 검토 모델에서만 유지

사용자가 명시적으로 제외하거나 저장한 뒤에만 영구 상태를 갱신한다.

## 5.4 수정 대상

- `gui/widgets/message_review_model.py`
- `gui/views/message_review_view.py`
- 필요 시 `gui/app.py`의 재분석 callback
- 필요 시 `core/milestone/message_automation/processed.py`

테스트:

- `tests/test_message_review_ui.py`
- 신규 `tests/test_message_date_recovery.py`

## 5.5 필수 테스트

1. 날짜 없는 트레이드 → date_needed
2. 날짜 없는 FA → date_needed
3. 날짜 없는 연장 → date_needed
4. 날짜 없는 부상 → date_needed
5. 날짜 지정 후 재분석 → candidate와 실제 forms 생성
6. 날짜 지정 후 자동 승인되지 않음
7. 승인·저장 후 message_auto 기록 생성
8. 재스캔 시 already_applied
9. 정책상 제외 메시지는 date_needed로 오분류되지 않음
10. 날짜가 필요 없는 연말 수상 메시지는 기존 fallback 유지

## 5.6 완료 조건

실제 fixture를 사용해 `message_date_required → 날짜 지정 → candidate → 승인 → 저장 → 재스캔 already_applied` 전체 흐름이 하나의 통합 테스트에서 통과한다.

---

# 6. W4 — 시즌 최종 판정의 실제 실행 경로 연결

## 6.1 문제

대시보드에는 `season_finalize` 상태가 있지만 행동 버튼이 가져오기 센터를 열 뿐 실제 시즌 최종 판정을 실행하지 않는다. 가져오기 센터에도 해당 카드가 없다.

## 6.2 구현 전 확인

작업자는 저장소에서 이미 존재하는 시즌 최종 판정 진입점을 먼저 찾는다. 다음 검색어를 사용한다.

- `season final`
- `finalize`
- `season_final`
- `record season`
- 화면의 `시즌 최종 기록` 버튼 문자열

기존 엔진·다이얼로그·메서드가 있으면 반드시 재사용한다. 새 판정 로직을 중복 구현하지 않는다.

## 6.3 권장 UI 연결

다음 중 기존 구조와 충돌이 적은 하나를 선택한다.

### 권장안 A — 가져오기 센터에 네 번째 카드 추가

- 카드 ID: `season_finalize`
- 원본 확인: 현재 시즌·DB·필요 데이터 확인
- 분석/검토: 판정 후보 미리보기
- 저장: 기존 시즌 최종 판정 실행
- 결과: 생성·중복·오류 요약

### 허용안 B — 대시보드에서 기존 시즌 최종 기록 다이얼로그 직접 실행

이 경우에도 `season_finalize` 워크플로 상태를 source_check → review/save → confirm_result로 저장해야 한다.

단순히 기존 화면으로 이동만 하는 것은 불충분하다.

## 6.4 상태 계산

시즌 최종 판정 완료 여부는 최소 다음을 저장한다.

- 실행 시즌
- 마지막 완료 시각
- 생성 수
- 중복 수
- 오류 수
- outcome

현재 설정 시즌과 마지막 실행 시즌이 다르면 대시보드는 다시 `필요`로 표시한다.

단순히 과거 어느 시즌에서 한 번 완료됐다는 이유로 현재 시즌도 완료 처리하지 않는다.

## 6.5 중복과 안전

- 같은 시즌에 재실행해도 중복 기록을 생성하지 않는다.
- 저장 전에 생성 예정 수와 중복 예정 수를 볼 수 있어야 한다.
- 오류가 일부 있으면 partial_success
- 전체 실패면 failed

## 6.6 수정 대상

- 기존 시즌 최종 판정 엔진 파일
- `gui/app.py`
- `gui/views/dashboard_view.py`
- 필요 시 `gui/views/import_center_view.py`
- `core/import_workflow.py` 기존 상태 사용

테스트:

- 신규 `tests/test_season_finalize_workflow.py`
- `tests/test_finalization_app_workflows.py`

## 6.7 필수 테스트

1. 현재 시즌 미실행 → 필요
2. 실행 시작 → running
3. 정상 완료 → completed와 실행 시즌 저장
4. 동일 시즌 재실행 → 중복 생성 없음
5. 시즌 변경 → 다시 필요
6. 부분 오류 → partial_success
7. 전체 실패 → failed
8. 앱 재실행 후 상태와 실행 시즌 유지
9. 대시보드 버튼이 실제 실행 또는 실제 검토 화면으로 연결

---

# 7. W5 — 메시지 처리 상태와 완료 판정 정합성

## 7.1 문제

현재 다음 문제가 남을 수 있다.

- 사용자가 검토 화면에서 제외한 메시지가 영구 저장되지 않음
- 일부 승인 항목만 저장했는데 전체 작업이 completed로 표시됨
- 대시보드가 전체 파일 수만 보고 신규·처리 완료를 구분하지 않음
- 변경된 원본과 신규 원본이 완료 상태 뒤에 숨음

## 7.2 영구 상태 정책

`processed_messages.status`는 최소 다음 상태를 구분한다.

- `candidate`
- `date_needed`
- `approved`
- `applied`
- `duplicate`
- `excluded`
- `error`
- 필요 시 `changed_review_needed`

모든 상태를 반드시 DB에 저장할 필요는 없지만, 다음은 앱 재실행 후 유지돼야 한다.

- applied
- duplicate
- 사용자가 명시적으로 제외한 excluded
- error와 마지막 오류
- 변경된 원본 감지를 위한 hash/mtime

## 7.3 사용자 제외 저장

`Exclude selected`는 UI 상태만 변경하지 않는다.

- source fingerprint와 함께 `processed_messages.status=excluded`
- 제외 사유는 `excluded_by_reviewer` 같은 내부 코드 사용
- 사용자 표시에서는 자연어 변환
- 원본이 변경되면 `changed_review_needed`로 다시 검토 가능

## 7.4 작업 완료 판정

뉴스 메시지 저장 후 outcome을 계산할 때 저장 콜백 결과만 보지 않는다. 검토 모델 전체 상태를 다시 집계한다.

### completed

- 승인된 항목 저장 완료
- candidate 0
- approved 0
- date_needed 0
- error 0
- 정책 제외와 사용자 제외는 unresolved가 아님

### partial_success

- 일부 저장 완료
- candidate, approved, date_needed 또는 error 중 하나 이상 남음

### failed

- 저장된 항목 0
- 오류로 작업을 진행할 수 없음

### cancelled

- 사용자가 작업을 중단한 경우

`unresolved`에 최소 다음을 저장한다.

- review_needed
- date_missing
- errors

## 7.5 대시보드 신규 수 계산

`_count_message_files()`의 단순 전체 파일 수를 작업 필요 수로 사용하지 않는다.

각 메시지 fingerprint에 대해 `get_message_rescan_status()`를 조회해 다음만 작업 필요 수에 포함한다.

- new
- changed_review_needed
- candidate/date_needed/error 등 미완료 상태

다음은 작업 필요 수에서 제외한다.

- already_applied
- 변하지 않은 duplicate
- 변하지 않은 사용자 제외

파일이 많아 성능이 문제라면 마지막 스캔 결과를 저장하고 폴더 mtime 또는 파일 목록 변화 시 다시 계산한다. 정확성이 우선이다.

## 7.6 수정 대상

- `core/milestone/message_automation/processed.py`
- `gui/widgets/message_review_model.py`
- `gui/views/message_review_view.py`
- `gui/views/dashboard_view.py`
- `gui/app.py`

테스트:

- `tests/test_processed_messages.py`
- `tests/test_message_review_ui.py`
- 신규 `tests/test_message_workflow_completion.py`
- 신규 `tests/test_dashboard_message_pending_count.py`

## 7.7 필수 테스트

1. 사용자 제외 후 재실행해 excluded 유지
2. 제외 원본 변경 후 changed_review_needed
3. applied 파일은 pending 수에서 제외
4. duplicate 파일은 pending 수에서 제외
5. 신규 파일 2개면 pending 2
6. 신규 1·변경 1·적용 5면 pending 2
7. 날짜 누락이 남으면 partial_success
8. 후보가 남으면 partial_success
9. 오류가 남으면 partial_success 또는 failed
10. 모두 처리되면 completed

---

# 8. W6 — 작업별 결과·오류 라우팅 완성

## 8.1 문제

공통 `check_errors` 행동이 메시지 검토 화면으로만 이동할 수 있어 박스스코어 오류와 시즌 판정 오류를 정확히 열지 못한다.

## 8.2 라우팅 계약

결과 행동에는 반드시 workflow ID가 포함돼야 한다.

권장 신호:

```python
result_action_requested = pyqtSignal(str, str)
# workflow_id, action_id
```

또는 action key에 workflow를 포함한다.

```text
latest_boxscores:view_errors
news_messages:view_errors
season_finalize:view_errors
baseline_history:view_differences
```

문자열을 사람이 읽는 라벨로 분기하지 않는다.

## 8.3 작업별 목적지

### latest_boxscores

- view_records → 달성 기록 또는 가져온 경기 결과
- view_errors → `ImportErrorsDialog` 또는 저장된 마지막 오류 보고
- review_issues → 오류 요약

### news_messages

- view_records → `source=message_auto` 필터가 적용된 달성 기록
- view_errors → 메시지 검토 `error` 필터
- review_issues → candidate/date_needed/error 중 우선 상태 필터

### baseline_history

- view_records → 선수 기록 또는 달성 기록
- view_differences → 비교 결과 화면
- view_errors → 초기 기록 가져오기 오류 결과

### season_finalize

- view_records → `source=season_final` 필터
- view_errors → 시즌 최종 판정 오류 결과
- review_issues → 판정 후보/중복 화면

## 8.4 결과 보고 저장

앱 재실행 후에도 마지막 오류를 열 수 있어야 한다. `report_ref`에 다음 중 하나를 저장한다.

- DB 실행 이력 ID
- JSON 보고서 경로
- 오류 테이블 조회 키

메모리 안의 다이얼로그 payload만 목적지로 삼지 않는다.

최소한 앱 실행 중에는 정확한 목적지가 동작하고, 재실행 후에는 요약과 재실행 안내가 명확히 표시돼야 한다.

## 8.5 수정 대상

- `gui/views/import_center_view.py`
- `gui/widgets/import_workflow_status.py`
- `gui/app.py`
- 각 오류 다이얼로그/결과 뷰

테스트:

- 신규 `tests/test_import_result_routing.py`
- `tests/test_import_workflow_ui.py`

## 8.6 필수 테스트

네 workflow 각각에 대해:

- view_records 목적지
- view_errors 목적지
- review_issues 목적지
- 오류 0일 때 오류 버튼 비활성 또는 숨김
- 다른 workflow 화면으로 잘못 이동하지 않음

---

# 9. W7 — 실제 공통 안내형 폼 완성

## 9.1 문제

현재 `GuidedMilestoneForm`은 내부 필드명을 번역한 2열 문자열 표다. 수동 입력은 기존 전용 다이얼로그를 사용하므로 UI 컴포넌트가 실제로 통합되지 않았다.

## 9.2 목표

수동 단건 입력과 메시지 추출 수정이 동일한 필드 컴포넌트와 동일한 검증 함수를 사용해야 한다.

일괄 표 입력은 보조 기능으로 유지한다.

## 9.3 구현 구조

기존 `single_record_dialogs.py`와 `manual_entry_fields.py`의 검증된 입력 위젯을 재사용한다. 새롭게 모든 폼을 다시 만들지 않는다.

권장 컴포넌트:

```python
class GuidedRecordEditor(QWidget):
    def set_form(self, form): ...
    def build_form_data(self): ...
    def validate(self) -> list[str]: ...
```

유형별 내부 페이지:

- milestone/award editor
- transfer/contract editor
- injury editor

## 9.4 필드 위젯

### 공통

- 날짜: `QDateEdit`, calendar popup
- 시즌: 자동 계산 후 수정 가능
- 설명·비고: `QLineEdit` 또는 `QPlainTextEdit`
- 필수값: 라벨 옆 `*`와 오류 메시지

### 마일스톤·수상

- 대상: 선수/팀 선택
- 선수: 기존 player combo와 자동완성
- 팀: 기존 tracked/custom MLB team combo
- 기록: milestone definition combo
- 값: 숫자 위젯 또는 검증된 입력
- 상대 팀·상대 선수: 선택/자동완성

### 팀 이동·계약

- 합류 선수·이탈 선수: 기존 multipick 또는 autocomplete
- 이동 유형: enum combo
- 합류 팀·상대 팀: team combo

### 부상

- 선수: autocomplete
- 부상명
- 기간
- 팀

## 9.5 메시지 수정에서 숨길 필드

기본 화면에서 직접 편집하지 않는다.

- source ID 자체
- 내부 milestone key 원문
- dataclass 클래스명
- 내부 category 코드
- 처리 상태 코드

source ID는 읽기 전용 근거 정보로 별도 표시한다.

## 9.6 검증 공유

다음 기존 검증을 공통으로 사용한다.

- `validate_manual_entry`
- `validate_manual_transfer`
- `validate_manual_injury`
- 기존 player/team normalization helper

수동 입력과 메시지 수정이 서로 다른 독자 검증을 갖지 않는다.

## 9.7 적용 위치

- 수동 단건 입력: 새 공통 editor를 포함
- 메시지 `Edit extracted result`: 동일 editor를 포함
- 일괄 입력: 기존 표 유지

기존 단건 다이얼로그를 공통 editor의 얇은 wrapper로 바꾸는 방식이 가장 안전하다.

## 9.8 수정 대상

- `gui/widgets/guided_milestone_form.py` 또는 새 `gui/widgets/guided_record_editor.py`
- `gui/widgets/single_record_dialogs.py`
- `gui/widgets/manual_entry_fields.py`
- `gui/views/message_review_view.py`
- `gui/widgets/manual_milestone_dialog.py`

테스트:

- `tests/test_manual_milestone_ux.py`
- `tests/test_message_review_ui.py`
- 신규 `tests/test_guided_record_editor.py`

## 9.9 필수 테스트

각 유형에 대해 수동 입력과 메시지 수정 양쪽에서:

1. 동일 입력값 → 동일 form data
2. 필수값 누락 → 동일 오류
3. 잘못된 날짜/숫자 → 저장 차단
4. 선수 자동완성 동작
5. 팀 선택 동작
6. 저장 후 올바른 source
7. 내부 필드명 기본 노출 없음
8. 키보드 Tab 순서 정상

## 9.10 완료 조건

단순히 `GuidedMilestoneForm` import 문장이 양쪽 파일에 있다는 이유로 완료 처리하지 않는다. 실제 렌더링 위젯과 form 생성·검증 코드가 공유돼야 한다.

---

# 10. W8 — 독립 검수, CI, Windows 125%, 최종 보고

## 10.1 독립 검수 원칙

W8 담당자는 W1~W7 제품 코드를 작성한 작업자가 아니어야 한다.

검수 실패를 숨기기 위해 제품 코드를 임의 수정하지 않는다. 결함이 있으면 해당 작업자에게 되돌린다.

## 10.2 자동 테스트

전체 테스트:

```bash
python -m pytest -q
```

추가 핵심 테스트를 별도로 실행한다.

```bash
python -m pytest -q \
  tests/test_state_persistence_boundaries.py \
  tests/test_boxscore_workflow_outcomes.py \
  tests/test_message_date_recovery.py \
  tests/test_season_finalize_workflow.py \
  tests/test_message_workflow_completion.py \
  tests/test_dashboard_message_pending_count.py \
  tests/test_import_result_routing.py \
  tests/test_guided_record_editor.py
```

실제 파일명이 달라지면 동일 범위를 증명하는 파일명을 보고서에 적는다.

## 10.3 GitHub Actions

`.github/workflows/ui-ux-regression.yml`은 다음을 포함해야 한다.

### Linux

- 전체 pytest
- 번역
- 마이그레이션
- 상태 영속성
- 메시지 전체 흐름

### Windows

- 핵심 상태·메시지·폼 테스트
- Qt offscreen smoke
- 화면 캡처 스크립트

브랜치 push 후 실제 workflow run이 성공해야 한다. 워크플로 파일 존재만으로 통과 처리하지 않는다.

최종 문서에 다음을 기록한다.

- 실행 commit SHA
- run URL 또는 run ID
- Linux 결과
- Windows 결과

## 10.4 Windows 125% 실제 검수

실제 Windows 환경에서 다음 조합을 확인한다.

- 1650×900 / 100% / 한국어
- 1366×768 / 125% / 한국어
- 최소 창 / 125% / 한국어
- 1366×768 / 125% / 영어

필수 화면:

1. 대시보드
2. 가져오기 센터 네 workflow
3. 박스스코어 완료·부분 성공·실패·취소
4. 뉴스 검토 전체 필터
5. 날짜 누락 → 날짜 입력 → 재분석
6. 메시지 추출 수정 공통 폼
7. 수동 단건 입력 공통 폼
8. 시즌 최종 판정
9. 달성 기록 source 필터
10. 오류 결과 화면

확인 항목:

- 버튼 잘림·겹침
- 가로 오버플로
- 최소 창 스크롤
- 포커스 이동
- disabled 상태 식별
- 긴 한국어·영어 문구
- 오류 메시지 접근 가능

## 10.5 사용자가 실제 Windows 검수를 해야 하는 경우

오케스트레이터 환경에서 125% 검수가 불가능하면 다음을 자동 준비한다.

- 실행 스크립트
- 고정 테스트 DB/fixture
- 화면 이동 순서
- 캡처 저장 경로
- 체크리스트

사용자에게는 위 준비가 끝난 뒤 최종 단계에서 한 번만 요청한다. 그 전에는 `완료`가 아니라 `사용자 화면 검수 대기`로 보고한다.

## 10.6 최종 문서 업데이트

다음 문서를 갱신한다.

- `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- `docs/ux/finalization/FINAL_VERIFICATION.md`

최종 보고서에는 다음 표를 포함한다.

| 항목 | 코드 완료 | 자동 테스트 | CI | Windows 실검수 | 판정 |
|---|---:|---:|---:|---:|---|
| W1 영속성 |  |  |  | 해당 없음 |  |
| W2 박스스코어 결과 |  |  |  |  |  |
| W3 날짜 복구 |  |  |  |  |  |
| W4 시즌 최종 판정 |  |  |  |  |  |
| W5 메시지 정합성 |  |  |  |  |  |
| W6 결과 라우팅 |  |  |  |  |  |
| W7 공통 폼 |  |  |  |  |  |
| W8 검증 |  |  |  |  |  |

---

# 11. 권장 작업 순서

## 1차 병렬 작업

- W1 상태 영속성
- W3 날짜 누락 복구
- W7 공통 폼 기반 작업

W3와 W7이 같은 메시지 UI 파일을 수정해야 하면 W3을 먼저 완료한 뒤 W7을 수행한다.

## 2차 작업

- W2 박스스코어 outcome 연결: W1 이후
- W4 시즌 최종 판정: W1 이후
- W5 메시지 정합성: W1·W3 이후

## 3차 통합

- W6 결과 라우팅: W2·W4·W5 이후
- `gui/app.py` 최종 통합
- 전체 테스트

## 4차 독립 검수

- W8 자동 테스트
- CI
- 실제 Windows 확인
- 최종 보고서

---

# 12. 커밋 단위

권장 커밋:

1. `fix: make workflow and processed-message state durable`
2. `fix: persist boxscore completed partial failed and cancelled outcomes`
3. `fix: recover date-required messages through review reanalysis`
4. `feat: connect season finalization to persisted workflow`
5. `fix: persist reviewer exclusions and derive pending message counts`
6. `fix: route import results by workflow and issue type`
7. `refactor: share guided record editors across manual and message flows`
8. `test: add last-mile workflow integration coverage`
9. `ci: verify final UI UX workflows on Linux and Windows`
10. `docs: record final UI UX completion evidence`

한 커밋에 W1~W7을 모두 합치지 않는다.

---

# 13. 최종 사용자 시나리오

## A. 앱 재실행 상태 복원

1. 뉴스 분석 실행
2. 날짜 누락과 후보 확인
3. 앱 종료
4. 앱 재실행
5. 마지막 실행 상태와 처리 메시지 상태 유지

## B. 날짜 누락 복구

1. 날짜 없는 트레이드 메시지 스캔
2. `날짜 필요` 필터에 표시
3. 날짜 지정
4. 자동 재분석
5. candidate 확인
6. 승인·저장
7. 달성 기록의 `뉴스 자동` 확인
8. 재스캔 `이미 반영됨` 확인

## C. 사용자 제외

1. 후보 메시지 제외
2. 앱 재실행
3. 제외 상태 유지
4. 원본 수정
5. 변경됨·재검토 필요로 전환

## D. 박스스코어 결과 네 종류

- 정상 완료
- 일부 오류 부분 성공
- 시작 단계 실패
- 사용자 취소

각 결과가 DB와 화면에 동일하게 표시돼야 한다.

## E. 시즌 최종 판정

1. 현재 시즌 미실행 상태 확인
2. 대시보드에서 실행/검토 진입
3. 후보 확인
4. 저장
5. 시즌 최종 출처 기록 확인
6. 재실행 중복 없음
7. 시즌 변경 후 다시 필요 표시

## F. 결과 라우팅

각 workflow에서 기록 보기·검토 필요·오류 보기를 눌러 해당 작업의 정확한 화면이 열리는지 확인한다.

## G. 공통 폼

동일한 부상 데이터를 수동 입력과 메시지 수정에서 각각 입력해 동일한 검증과 DB 결과가 나오는지 확인한다.

---

# 14. 최종 완료 조건

다음이 모두 충족돼야 한다.

- 상태 저장 함수가 외부 commit 없이 재연결 후 복원됨
- processed message 상태가 재실행 후 유지됨
- 박스스코어 completed/partial_success/failed/cancelled 구분
- 날짜 누락 메시지가 date_needed에서 복구 가능
- 사용자 제외가 영구 유지되고 원본 변경 시 재검토 가능
- 대시보드가 신규·변경·미처리 메시지만 작업 필요로 계산
- 시즌 최종 판정 버튼이 실제 기능과 연결
- 결과·오류 버튼이 workflow별 정확한 목적지로 이동
- 수동 단건 입력과 메시지 수정이 실제 공통 editor와 검증 사용
- 전체 pytest 통과
- GitHub Actions Linux·Windows 성공
- Windows 125% 실검수 완료 또는 사용자 검수 대기라고 명확히 보고
- 최종 보고서의 주장과 코드·테스트·화면 증거가 일치

---

# 15. 완료 금지 조건

다음 중 하나라도 있으면 `UI/UX 전면 개선 완료`로 보고하지 않는다.

- 테스트가 외부 `commit()`으로 상태 영속성 결함을 숨김
- 실패·취소가 completed로 저장됨
- 날짜 누락 메시지가 excluded에서 복구되지 않음
- 시즌 최종 판정 버튼이 단순 페이지 이동만 수행
- 사용자가 제외한 메시지가 재실행 후 다시 후보로 나타남
- 전체 메시지 파일 수를 미처리 수로 표시
- 박스스코어 오류 버튼이 메시지 오류 화면을 엶
- 공통 폼이 번역된 2열 문자열 표에 그침
- GitHub Actions 파일만 있고 실제 성공 run이 없음
- offscreen 캡처만으로 Windows 125% 검수를 완료 처리

---

# 16. 오케스트레이터 최종 보고 형식

```markdown
## 완료
- W1 ...

## 검증
- 전체 테스트: n passed, n skipped
- GitHub Actions: Linux 성공 / Windows 성공 / commit SHA
- Windows 125%: 완료 또는 사용자 검수 대기

## 남은 항목
- 없음
```

남은 항목이 있으면 `완료` 대신 `부분 완료`라고 보고한다. 사용자에게 구현 과정의 장문 설명을 전달하지 말고, 변경 결과·검증·실제 확인 필요 사항만 간단히 보고한다.
