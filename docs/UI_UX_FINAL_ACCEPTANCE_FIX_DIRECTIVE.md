# OOTP Milestone Tracker UI/UX 최종 인수 차단 결함 수정 지시서

## 0. 문서 지위

이 문서는 `codex/ui-ux-audit-improvements` 브랜치의 W1~W8 구현을 다시 검수한 결과 발견된 **최종 인수 차단 결함만 수정하기 위한 최상위 지시서**다.

- 대상 브랜치: `codex/ui-ux-audit-improvements`
- 선행 지시서: `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`
- 구현 보고서: `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- 검증 문서: `docs/ux/finalization/FINAL_VERIFICATION.md`
- 이 문서는 기존 UI 구조를 다시 설계하기 위한 문서가 아니다.
- 기존 W1~W3과 W6의 통과된 구현은 유지한다.
- 선행 문서와 충돌할 경우 **이 문서의 인수 기준과 수정 방법이 우선한다.**

현재 구현은 이전보다 크게 개선됐으며 다음 항목은 용인 가능한 수준이다.

- 가져오기 작업 상태와 처리 메시지 상태의 기본 commit 경계
- 박스스코어 완료·부분 성공·실패·취소 구조화 payload
- 날짜 누락 메시지의 날짜 지정 후 재분석
- 메시지별 생성·중복·오류 결과
- 기록 출처 저장 및 화면 필터
- 기본 결과 라우팅과 오류 보고서 저장
- 공통 typed editor의 기반 컴포넌트

그러나 아래 결함은 실제 데이터 정확성 또는 핵심 작업 흐름에 영향을 주므로, 현재 브랜치를 최종 완료·병합 가능 상태로 판정하지 않는다.

1. 시즌 최종 판정의 분석 시즌과 저장 시즌이 달라질 수 있다.
2. 시즌 최종 판정에서 실제 후보 목록을 확인하는 검토 화면이 없다.
3. 완료된 뉴스 작업 뒤 신규·변경 메시지가 생겨도 대시보드가 완료로 남을 수 있다.
4. 정책상 자동 제외된 메시지가 처리 상태에 저장되지 않아 재스캔 때 계속 신규로 나타날 수 있다.
5. 메시지 수정 편집기에 앱의 선수·팀·마일스톤 문맥이 전달되지 않는다.
6. CSV 내보내기가 명시적 출처를 다시 `수동/자동` 두 값으로 축약한다.
7. CI 성공 실행과 실제 Windows 125% 검증 증거가 아직 확정되지 않았다.

이번 작업은 아래 A1~A5만 수행한다. 오케스트레이터는 저장소 전체를 다시 분석하거나 새로운 대규모 UI 계획을 작성하지 않는다.

---

# 1. 오케스트레이터 실행 규칙

## 1.1 해야 할 일

1. A1~A5 담당자를 지정한다.
2. 파일 소유권과 선행 관계를 확정한다.
3. 각 담당자에게 이 문서와 지정 참조 파일만 전달한다.
4. 공통 파일인 `gui/app.py`는 한 명만 수정하거나 오케스트레이터가 순차 통합한다.
5. 각 작업의 필수 테스트와 사용자 시나리오를 직접 검수한다.
6. A1~A4가 완료된 뒤 A5 독립 검수를 수행한다.
7. 모든 인수 조건을 통과하기 전에는 `UI/UX 전면 개선 완료`라고 보고하지 않는다.

## 1.2 하지 말아야 할 일

- 기존 대시보드·달성 기록·가져오기 센터를 다시 전면 설계하지 않는다.
- 테스트의 기대값만 바꿔 현재 동작을 정당화하지 않는다.
- private UI 메서드를 계속 핵심 서비스 진입점으로 사용하지 않는다.
- offscreen PNG 생성만으로 실제 Windows 배율 검증을 완료 처리하지 않는다.
- CI 워크플로 파일 존재만으로 CI 성공이라고 보고하지 않는다.
- 문서상의 완료 선언을 코드 검증보다 우선하지 않는다.

## 1.3 필수 작업 배정표

| 작업 | 담당 | 소유 파일 | 공통 파일 | 선행 작업 | 제출 증거 |
|---|---|---|---|---|---|
| A1 시즌 최종 판정 |  | 시즌 판정 core·review UI·전용 테스트 | `gui/app.py` | 없음 | 후보 검토·시즌 일치 테스트 |
| A2 메시지 정합성 |  | processed/scan/dashboard·전용 테스트 | `gui/app.py` | 없음 | 신규·변경·제외 재실행 테스트 |
| A3 편집기 문맥 |  | message review·guided editor·전용 테스트 | `gui/app.py` | 없음 | 자동완성·ID 변환 테스트 |
| A4 출처·결과 복원 |  | export·result summary·전용 테스트 | `gui/app.py` | A1, A2 | 출처 CSV·재시작 라우팅 테스트 |
| A5 독립 인수 검수 | 독립 작업자 | 테스트·검증 문서·CI | 제품 코드 수정 금지 | A1~A4 | 정확한 SHA·CI·화면 증거 |

같은 파일을 둘 이상의 작업자가 동시에 수정하지 않는다.

---

# 2. 하위 작업자 공통 참조 자료

모든 작업자가 읽을 문서:

- `docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`
- `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`
- `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- `docs/ux/finalization/FINAL_VERIFICATION.md`

통과된 기반 구현:

- `core/import_workflow.py`
- `core/milestone/message_automation/processed.py`
- `gui/workers/import_worker.py`
- `tests/test_state_persistence_boundaries.py`
- `tests/test_boxscore_workflow_outcomes.py`
- `tests/test_message_date_recovery.py`

작업자는 자신의 패키지에 지정된 파일만 추가로 읽는다.

---

# 3. A1 — 시즌 최종 판정의 분석·검토·저장 일관성

## 3.1 확인된 문제

현재 가져오기 센터의 분석 단계는 `settings.current_season`을 기준으로 후보를 계산한다. 그러나 저장 단계는 `MilestoneView._record_season_ratio_milestones()`를 호출하고, 이 메서드는 `season_spin.value() or settings.current_season`을 다시 사용한다.

따라서 사용자가 달성 기록 화면의 시즌 필터를 다른 연도로 설정해 둔 경우 다음 문제가 가능하다.

1. 가져오기 센터에서 2026시즌을 분석한다.
2. 달성 기록 화면의 `season_spin`은 2025로 남아 있다.
3. 저장 단계는 2025시즌을 다시 읽고 기록한다.

또한 분석 단계는 후보 수만 워크플로 상태에 저장하며, 사용자가 실제 선수·기록·값을 확인할 수 있는 후보 목록을 표시하지 않는다. `review_results` 단계가 존재하지만 실제 검토 화면이 아니다.

## 3.2 구현 목표

시즌 최종 판정은 다음 하나의 명시적 요청 객체를 분석부터 저장까지 사용해야 한다.

```python
@dataclass(frozen=True)
class SeasonFinalizationRequest:
    season: int
    achieved_date: date
    batting_path: Path
    pitching_path: Path
```

분석 결과는 다음 정보를 가진다.

```python
@dataclass(frozen=True)
class SeasonFinalizationCandidate:
    player_id: int
    player_name: str
    team: str
    milestone_key: str
    milestone_label: str
    achieved_value: float

@dataclass(frozen=True)
class SeasonFinalizationPreview:
    request: SeasonFinalizationRequest
    batting_fingerprint: str
    pitching_fingerprint: str
    candidates: tuple[SeasonFinalizationCandidate, ...]
    validation_errors: tuple[str, ...]
```

저장 결과는 기존 `SeasonFinalizeResult`와 호환되거나 이를 core 계층으로 이동해 사용한다.

## 3.3 구현 방법

### 3.3.1 core 서비스 분리

신규 권장 파일:

- `core/milestone/season_finalization.py`

제공 함수:

```python
def analyze_season_finalization(
    aggregator,
    definitions,
    settings,
    request: SeasonFinalizationRequest,
) -> SeasonFinalizationPreview:
    ...

def apply_season_finalization(
    aggregator,
    definitions,
    settings,
    preview: SeasonFinalizationPreview,
) -> SeasonFinalizeResult:
    ...
```

서비스 함수는 다음을 해서는 안 된다.

- `QMessageBox`, `QInputDialog` 호출
- `MilestoneView.season_spin` 조회
- 다른 화면의 private 메서드 호출
- 분석 시 사용하지 않은 다른 시즌으로 저장

### 3.3.2 파일 변경 감지

분석 시 두 export 파일의 SHA-256 또는 내용 기반 지문을 저장한다.

저장 직전에 파일 지문을 다시 계산한다.

- 동일: 저장 진행
- 변경됨: 저장 중단, 워크플로를 `review_results`로 되돌리고 `exports_changed` 경고 표시
- 파일 없음: 실패 처리

분석 이후 파일이 변경됐는데 예전 후보를 저장해서는 안 된다.

### 3.3.3 실제 후보 검토 UI

신규 권장 파일:

- `gui/views/season_finalization_review.py`
  또는
- `gui/widgets/season_finalization_review_dialog.py`

최소 표시 항목:

- 대상 시즌
- 기록일
- 타격/투구 export 경로와 마지막 수정 정보
- 후보 수
- 선수명
- 팀
- 기록명
- 달성값
- 이미 존재하는 동일 기록 여부

필수 동작:

- 분석 결과가 없으면 `저장` 비활성화
- 검증 오류가 있으면 오류 목록 표시
- 후보 0건은 정상적인 완료 가능한 결과로 구분
- 사용자가 기록일을 바꾸면 재분석하거나 preview 요청 자체를 갱신
- 저장 버튼은 현재 preview 객체를 그대로 coordinator에 전달

### 3.3.4 가져오기 센터 단계 연결

시즌 최종 판정 카드:

1. `source_check`: 현재 선택 시즌과 export 파일 확인
2. `analyze_classify`: 명시적 요청으로 preview 생성
3. `review_results`: 후보 검토 화면 열기
4. `save`: 검토 중인 동일 preview 저장
5. `confirm_result`: `season_final` 출처 필터 또는 오류 보고서 열기

`analyze_classify` 후 바로 달성 기록 화면으로 이동하지 않는다.

### 3.3.5 기존 MilestoneView 버튼

기존 `최종 시즌 기록 판정` 버튼은 제거할 필요가 없다. 다만 다음 중 하나로 변경한다.

- 가져오기 센터의 시즌 최종 판정 카드로 이동
- 동일 core 서비스와 검토 UI를 여는 얇은 wrapper

기존 `_record_season_ratio_milestones()`를 앱의 핵심 진입점으로 유지하지 않는다. 호환 테스트가 필요하면 deprecated wrapper로 남기되, 내부에서 명시적 request/preview/apply 서비스를 호출한다.

## 3.4 수정 대상

주 소유:

- 신규 `core/milestone/season_finalization.py`
- 신규 season final review UI
- `gui/views/import_center_view.py`
- `gui/views/milestone_view.py`
- 전용 테스트

통합 전용:

- `gui/app.py`

참조:

- `core/stats/initial_import.py`
- `core/milestone/checker.py`
- `tests/test_season_finalize_workflow.py`

## 3.5 필수 테스트

1. 분석과 저장이 같은 명시적 시즌을 사용한다.
2. `MilestoneView.season_spin`이 다른 연도여도 결과가 바뀌지 않는다.
3. 후보 목록에 선수·기록·값이 표시된다.
4. 분석 후 export 변경 시 저장이 차단된다.
5. 후보 0건은 오류가 아닌 완료 또는 명확한 무변경 결과다.
6. 첫 저장은 생성, 같은 preview 재실행은 중복으로 계산된다.
7. 취소는 `cancelled`, 검증 실패는 `failed`, 일부 저장 오류는 `partial_success`다.
8. 저장된 기록의 source는 `season_final`이다.
9. 앱 재실행 후 마지막 시즌과 결과를 복원한다.
10. 이전 시즌 필터가 현재 시즌 완료 상태를 오염시키지 않는다.

## 3.6 완료 조건

- 분석 시즌과 저장 시즌이 달라질 코드 경로가 없다.
- 사용자가 저장 전에 실제 후보 목록을 볼 수 있다.
- `gui/app.py`가 MilestoneView private 저장 메서드를 직접 호출하지 않는다.
- 파일 변경 후 오래된 preview를 저장할 수 없다.

---

# 4. A2 — 메시지 스캔·처리 상태·대시보드 정합성

## 4.1 확인된 문제

### 문제 1: 완료 상태가 신규 파일보다 우선함

대시보드는 미처리 메시지 파일 수를 계산하지만, 이전 워크플로 결과가 `completed`이면 미처리 수가 1개 이상이어도 완료 상태를 반환할 수 있다.

판정 우선순위는 반드시 다음과 같아야 한다.

1. 현재 신규·변경·날짜 누락·오류·승인 대기 존재
2. 현재 소스 접근 오류
3. 마지막 실행 실패·부분 성공
4. 현재 미처리 없음 + 마지막 완료

과거 완료 상태가 현재 신규 파일보다 우선해서는 안 된다.

### 문제 2: 정책상 제외 메시지가 영구 처리되지 않음

새 메시지를 파싱했을 때 `trade_deadline_not_a_transaction`, `player_of_week_not_recorded`, 추적 팀 무관 등 정책상 제외 결과가 나오더라도 현재 검토 목록에만 추가되고 `processed_messages`에 저장되지 않을 수 있다.

이 경우 다음 스캔에서도 같은 파일이 `new`로 판정된다.

### 문제 3: processed upsert의 None 의미

`upsert_processed_message()`는 생성·중복 ID 인수가 생략돼도 기존 값을 빈 배열로 덮어쓸 수 있다. 변경 파일을 재검토 상태로 저장할 때 과거 생성 기록 연결이 사라질 위험이 있다.

## 4.2 구현 목표

메시지 파일 하나는 스캔 직후 다음 중 하나의 명시적 상태를 가진다.

- `candidate`
- `date_needed`
- `error`
- `excluded_policy`
- `excluded_by_reviewer`
- `applied`
- `duplicate`
- `changed_review_needed`

DB 내부 상태명을 기존 값과 호환되게 정할 수 있지만, 정책 제외와 사용자 제외 이유는 구분한다.

## 4.3 스캔 서비스 분리

신규 권장 파일:

- `core/milestone/message_automation/review_service.py`

권장 결과:

```python
@dataclass(frozen=True)
class MessageScanResult:
    items: tuple[MessageReviewItemData, ...]
    totals: dict[str, int]
    unresolved: dict[str, int]
```

서비스 책임:

1. 파일 목록 수집
2. fingerprint 계산
3. 기존 processed 상태 조회
4. 변경 여부 판정
5. parser 실행
6. 정책 제외 상태 영구 저장
7. 신규 후보·날짜 필요·오류 상태 저장
8. UI용 review item 데이터 반환

GUI가 파일별 DB 정합성 로직을 직접 반복하지 않도록 한다.

## 4.4 processed 저장 API 수정

`upsert_processed_message()`의 리스트 인수는 다음 의미를 가져야 한다.

- `None`: 기존 값 유지
- `[]`: 명시적으로 비움
- `[id, ...]`: 새 값으로 교체

이를 위해 SQL에서 각 필드의 갱신 플래그를 별도로 전달하거나, 기존 레코드를 읽고 보존한 값을 명시적으로 넘긴다.

변경 재검토 상태로 전환할 때 다음 정보는 보존한다.

- 과거 `created_record_ids`
- 과거 `duplicate_record_ids`
- 과거 applied_at

현재 fingerprint와 상태는 갱신한다. 필요하다면 `previous_source_hash` 또는 별도 이력 필드를 추가한다.

## 4.5 정책 제외 영속화

스캔 결과가 정책 제외면 즉시 다음을 저장한다.

- 현재 fingerprint
- status: 정책 제외를 나타내는 값
- category
- parser exclusion_reason
- last_seen_at

다음 스캔에서 원본이 동일하면 미처리 수에 포함하지 않는다.

원본이 변경되면 `changed_review_needed`로 돌아간다.

사용자 제외는 `excluded_by_reviewer` 사유를 유지하고 동일 원본에서는 미처리 수에 포함하지 않는다.

## 4.6 대시보드 판정 수정

`DashboardView._news_messages_state()`는 다음 순서로 판정한다.

```text
소스 폴더 없음/읽기 실패
→ date_missing/errors/review_needed 있음
→ pending_file_count > 0
→ 마지막 outcome이 failed/partial_success/cancelled
→ pending 0이고 마지막 completed
→ 아직 실행하지 않음
```

특히 `pending_file_count > 0`이면 이전 outcome이 completed여도 `needed` 또는 `warning`이다.

대시보드 문구:

- 신규 N건
- 원본 변경 N건
- 날짜 필요 N건
- 오류 N건
- 승인 대기 N건

가능하면 총합뿐 아니라 가장 중요한 사유를 표시한다.

## 4.7 메시지 작업 완료 판정

전체 review model 기준으로 다음을 계산한다.

- candidate 또는 approved 미저장 존재 → partial_success 또는 진행 중
- date_needed 존재 → partial_success
- error 존재 + 저장 성공 없음 → failed
- error 존재 + 일부 저장 → partial_success
- applied/duplicate/excluded만 존재 → completed

정책 제외와 사용자 제외는 정상 처리 완료 항목이며, unresolved에 포함하지 않는다.

저장하지 않은 approved 행이 완료로 처리되지 않도록 한다.

## 4.8 수정 대상

주 소유:

- `core/milestone/message_automation/processed.py`
- 신규 review service
- `gui/views/dashboard_view.py`
- `gui/widgets/message_review_model.py`
- 관련 테스트

통합 전용:

- `gui/app.py`

참조:

- `gui/views/message_review_view.py`
- `tests/test_dashboard_message_pending_count.py`
- `tests/test_message_workflow_completion.py`
- `tests/test_processed_messages.py`

## 4.9 필수 테스트

1. 완료된 작업 뒤 새 파일 추가 → 대시보드 `필요`.
2. 완료된 작업 뒤 기존 파일 변경 → 대시보드 `필요`.
3. 정책 제외 파일만 있는 경우 첫 스캔 후 처리 저장, 재실행 시 pending 0.
4. 사용자 제외 파일은 재실행 시 pending 0.
5. 사용자 제외 파일 내용 변경 시 재검토 필요.
6. 정책 제외 사유가 DB와 UI에 유지됨.
7. changed 상태 저장이 과거 created/duplicate ID를 지우지 않음.
8. 날짜 필요·오류·후보가 남으면 completed가 되지 않음.
9. applied/duplicate/excluded만 남으면 completed.
10. 앱 종료·재실행 후 동일 상태 유지.
11. 새 파일·변경 파일·정책 제외·사용자 제외가 섞인 실제 폴더 통합 테스트.

## 4.10 완료 조건

- 과거 completed가 현재 pending을 숨기지 않는다.
- 동일한 정책 제외 파일이 매번 신규 후보로 다시 나타나지 않는다.
- processed 상태 갱신이 과거 생성 기록 연결을 잃지 않는다.
- UI와 DB가 같은 미처리 수를 표시한다.

---

# 5. A3 — 메시지 수정 편집기에 실제 앱 문맥 전달

## 5.1 확인된 문제

`GuidedRecordEditor` 자체는 typed form, 날짜 선택기, 선수·팀 helper와 공통 검증을 지원한다. 그러나 `ExtractedResultEditDialog`는 `GuidedMilestoneForm(item.parsed.forms, parent=self)`만 생성한다.

따라서 메시지 수정 경로에는 다음 문맥이 없다.

- Aggregator
- AppSettings
- MilestoneDefinitions

이 상태에서는 선수 자동완성, 선수명→ID 변환, 추적 팀 목록, 마일스톤 선택 목록이 수동 입력과 동일하게 동작하지 않는다.

## 5.2 구현 방법

### 5.2.1 생성자 계약

`MessageReviewView`에 다음 선택 인수를 추가한다.

```python
def __init__(
    self,
    items=(),
    *,
    save_callback=None,
    reanalyze_callback=None,
    aggregator=None,
    settings=None,
    milestones=None,
    parent=None,
):
    ...
```

`ExtractedResultEditDialog`도 동일 문맥을 전달받는다.

```python
GuidedMilestoneForm(
    item.parsed.forms,
    aggregator=aggregator,
    settings=settings,
    milestones=milestones,
    parent=self,
)
```

MainWindow에서 메시지 검토 화면을 만들 때 실제 객체를 전달한다.

### 5.2.2 출처 보호

다음 값은 수정 폼에서 읽기 전용 또는 숨김 상태를 유지한다.

- source ID
- source note
- 자동화 출처
- parser category

사용자가 기록 필드를 수정해도 `source:<message-id>`가 사라지지 않아야 한다.

### 5.2.3 동일 검증 보장

수동 단건 입력과 메시지 수정은 다음을 공유한다.

- `GuidedRecordEditor`
- 날짜 처리
- 선수 자동완성 및 ID 변환
- 팀 선택 helper
- milestone definition 목록
- `validate_manual_entry`
- `validate_manual_transfer`
- `validate_manual_injury`

## 5.3 수정 대상

- `gui/views/message_review_view.py`
- `gui/widgets/guided_milestone_form.py`
- 필요 시 `gui/widgets/single_record_dialogs.py`
- 전용 테스트

통합 전용:

- `gui/app.py`

## 5.4 필수 테스트

1. 메시지 MVP 후보 편집기에서 실제 선수 자동완성 사용.
2. 표시명으로 선택한 선수가 올바른 player_id로 저장됨.
3. 팀 목록에 추적 팀과 설정된 MLB 팀이 표시됨.
4. milestone key를 내부 문자열 입력이 아니라 정의 목록에서 선택 가능.
5. 수동 입력과 메시지 수정의 동일 잘못된 값이 동일 오류를 반환.
6. source note는 수정 후에도 보존.
7. Aggregator 문맥 없는 독립 테스트 모드도 기존처럼 작동.

## 5.5 완료 조건

- 메시지 수정 화면이 수동 입력과 같은 수준의 자동완성·선택기·검증을 제공한다.
- 사용자가 숫자 player_id나 내부 milestone key를 직접 입력할 필요가 없다.

---

# 6. A4 — 명시적 출처 보존과 결과 복원 마감

## 6.1 CSV 출처 손실 수정

달성 기록 CSV 내보내기에서 다음 호출을 사용하지 않는다.

```python
source_display_label(milestone_is_manual(record))
```

다음처럼 명시적 출처를 사용한다.

```python
source_display_label(milestone_source(record))
```

CSV는 최소 다음을 구분해야 한다.

- 박스스코어 자동
- 뉴스 자동
- 수동 입력
- 시즌 최종 판정
- 이전 데이터/마이그레이션
- 검증 재생

## 6.2 헤더와 행 개수 검증

현재 화면 표는 6열이지만 전체 CSV는 상세 필드를 추가할 수 있다. 다만 다음을 보장한다.

- 헤더 수와 행 수 일치
- `Type`, `Source` 위치 명확
- 한글명 등 상세 열이 사라지지 않음
- 필터와 무관하게 전체 기록 내보내기라는 기존 정책 유지

## 6.3 결과 요약 재시작 복원

앱 재실행 시 가져오기 카드 상태만 복원되고 하단 결과 요약이 비어 있지 않도록 한다.

권장 방법:

- 가져오기 센터 진입 시 가장 최근 `completed_at` 또는 `started_at`을 가진 workflow 선택
- persisted state의 outcome/totals/unresolved/message로 `ImportResultSummary` 구성
- workflow_id를 유지해 결과 버튼 라우팅

사용자가 다른 카드의 `confirm_result`를 누르면 해당 workflow의 persisted summary로 교체한다.

## 6.4 오류 보고서 UX

박스스코어 JSON 오류 보고서가 있으면 단순 경로 문자열만 보여주는 대신 최소 하나를 제공한다.

- 앱 내 오류 목록 다이얼로그로 JSON 행 표시
- 보고서 파일 열기
- 보고서 폴더 열기

보고서가 사라진 경우 이해 가능한 안내를 표시한다.

## 6.5 수정 대상

- `gui/views/milestone_view.py`
- `gui/views/import_center_view.py`
- `gui/widgets/import_workflow_status.py`
- 오류 보고서 표시 widget 또는 dialog
- 전용 테스트

통합 전용:

- `gui/app.py`

## 6.6 필수 테스트

1. 각 출처별 기록을 CSV로 내보내 정확한 표시명 확인.
2. CSV 헤더와 행 열 개수 일치.
3. 앱 재시작 후 마지막 결과 summary 복원.
4. 복원된 결과 버튼이 올바른 workflow 목적지로 이동.
5. 박스스코어 오류 JSON을 실제 목록으로 확인 가능.
6. 보고서 파일이 없을 때 앱이 예외 없이 안내.

## 6.7 완료 조건

- 내보내기에서 뉴스 자동과 시즌 최종 판정이 일반 자동으로 합쳐지지 않는다.
- 앱 재시작 후에도 마지막 결과와 해결 경로를 확인할 수 있다.

---

# 7. A5 — 독립 인수 검수와 증거 확정

## 7.1 독립성

A5 담당자는 A1~A4 제품 코드 구현에 참여하지 않은 작업자로 지정한다.

원칙:

- 제품 코드 수정 금지
- 실패 테스트를 삭제하거나 완화하지 않음
- 구현 보고서를 증거로 간주하지 않고 직접 코드·테스트·화면 확인

## 7.2 자동 검증

반드시 실행:

```text
python -m pytest -q
```

추가 집중 테스트:

- 시즌 분석·preview·저장 일관성
- 메시지 신규/변경/정책 제외/사용자 제외
- 대시보드 completed 우선순위 회귀
- 편집기 full-context 자동완성
- CSV 출처
- 결과 summary 재시작 복원

## 7.3 GitHub Actions

`.github/workflows/ui-ux-regression.yml`이 존재하는 것으로 완료하지 않는다.

최종 보고서에 다음을 기록한다.

- 제품 코드 최종 커밋 SHA
- workflow run ID
- Linux job 결과
- Windows job 결과
- 실패 후 재실행 여부
- artifact 이름과 보관 위치

문서만 수정한 후속 커밋의 성공이 아니라, A1~A4가 포함된 정확한 제품 코드 SHA 또는 그 직계 후속 커밋의 성공을 확인한다.

## 7.4 실제 Windows 125% 검증

다음 화면을 실제 Windows 디스플레이 배율 125%에서 확인한다.

- 대시보드
- 4개 가져오기 workflow
- 시즌 최종 후보 검토
- 뉴스 메시지 검토와 날짜 복구
- 메시지 추출 수정 편집기
- 수동 단건 편집기
- 달성 기록 기본/고급 필터
- 완료·부분 성공·실패·취소 결과
- 오류 보고서

해상도:

- 1366×768 / 125%
- 앱 최소 크기 / 125%
- 가능하면 1650×900 / 100% 비교

한국어와 영어에서 확인:

- 글자 잘림
- 버튼 겹침
- 세로 스크롤
- 키보드 Tab 이동
- 콤보박스 선택 가능
- 대화상자 화면 밖 이탈

실제 125% 환경을 사용할 수 없다면 최종 완료로 보고하지 않고, 사용자 확인 게이트를 명확히 남긴다.

## 7.5 문서 정합성

다음 문서를 실제 결과에 맞게 갱신한다.

- `docs/UI_UX_IMPLEMENTATION_REPORT.md`
- `docs/ux/finalization/FINAL_VERIFICATION.md`
- `docs/ux/UI_UX_VERIFICATION.md`

금지:

- `PENDING_PUSH`가 남은 채 CI 완료 선언
- 체크되지 않은 Windows 목록을 완료라고 서술
- 로컬 테스트 건수와 CI 테스트 건수를 혼용
- 실제 후보 검토 화면 없이 시즌 검토 완료 선언

---

# 8. 권장 작업 순서

1. A1과 A2를 병렬 시작한다.
2. A3는 A1/A2와 별도 파일 소유권으로 병렬 진행한다.
3. A1~A3 통합 후 A4를 수행한다.
4. 오케스트레이터가 `gui/app.py` 신호·라우팅을 한 번에 통합한다.
5. 전체 테스트 실행.
6. A5 독립 검수.
7. CI 성공 확인.
8. 실제 Windows 125% 확인 또는 명시적 사용자 게이트.
9. 최종 보고서 갱신.

---

# 9. 권장 커밋 단위

1. `refactor: move season finalization into explicit core service`
2. `feat: add season finalization candidate review`
3. `fix: reconcile message scan states and dashboard pending priority`
4. `fix: preserve processed message record links during rescan`
5. `fix: pass application context to extracted record editor`
6. `fix: preserve explicit milestone source in exports`
7. `feat: restore persisted import result summaries`
8. `test: add final UI UX acceptance regressions`
9. `docs: record final CI and native Windows verification`

기능 코드와 검증 문서를 하나의 거대한 커밋으로 합치지 않는다.

---

# 10. 최종 인수 시나리오

## 시나리오 1 — 시즌 필터 불일치 방지

1. 현재 시즌을 2026으로 설정한다.
2. 달성 기록 화면 시즌 필터를 2025로 변경한다.
3. 가져오기 센터에서 시즌 최종 판정 2026을 분석한다.
4. 후보 목록에서 2026을 확인한다.
5. 저장한다.
6. 생성 기록 시즌이 모두 2026인지 확인한다.
7. 대시보드가 2026 완료로 표시되는지 확인한다.

## 시나리오 2 — 분석 후 export 변경

1. 시즌 후보를 분석한다.
2. export 파일 내용을 변경한다.
3. 저장을 시도한다.
4. 저장이 차단되고 재분석이 요구되는지 확인한다.

## 시나리오 3 — 완료 후 신규 메시지

1. 뉴스 작업을 완료한다.
2. 앱을 종료한다.
3. 새 message 파일을 추가한다.
4. 앱을 실행한다.
5. 대시보드가 완료가 아니라 신규 1건 필요로 표시되는지 확인한다.

## 시나리오 4 — 정책 제외 반복 방지

1. Player of the Week 또는 투표 시작 메시지를 스캔한다.
2. 정책 제외 상태를 확인한다.
3. 앱을 재실행하고 다시 스캔한다.
4. 동일 파일이 신규·미처리 수에 포함되지 않는지 확인한다.
5. 파일 내용을 바꾸면 재검토 필요로 돌아오는지 확인한다.

## 시나리오 5 — 메시지 수정 문맥

1. 선수 수상 메시지 후보를 연다.
2. 추출 결과 수정을 연다.
3. 선수명을 자동완성으로 선택한다.
4. 기록 유형을 목록에서 선택한다.
5. 저장 후 올바른 player_id와 message_auto 출처를 확인한다.

## 시나리오 6 — CSV 출처

1. 박스스코어 자동·뉴스 자동·수동·시즌 최종 기록을 각각 준비한다.
2. 전체 CSV를 내보낸다.
3. 네 출처가 서로 다른 값으로 보존되는지 확인한다.

## 시나리오 7 — 재시작 결과 복원

1. 부분 성공 박스스코어 작업을 수행한다.
2. 앱을 재실행한다.
3. 가져오기 센터에서 마지막 totals/unresolved와 오류 버튼을 확인한다.
4. 오류 버튼이 해당 보고서를 여는지 확인한다.

---

# 11. 최종 완료 조건

다음이 모두 충족돼야 최종 완료다.

- 시즌 분석과 저장이 동일한 명시적 season/request를 사용함
- 시즌 후보 목록을 저장 전에 실제로 확인할 수 있음
- export 변경 시 오래된 preview 저장 차단
- 신규·변경 메시지가 과거 completed 상태에 가려지지 않음
- 정책 제외와 사용자 제외가 재실행 후 유지됨
- changed 상태 저장이 과거 기록 ID를 지우지 않음
- 메시지 수정 편집기에 실제 선수·팀·마일스톤 문맥이 전달됨
- CSV가 모든 명시적 출처를 보존함
- 앱 재시작 후 마지막 결과 summary와 목적지 복원
- 전체 테스트 통과
- 최종 제품 SHA의 GitHub Actions Linux/Windows 성공
- 실제 Windows 125% 검증 완료 또는 사용자 확인 게이트를 미완료로 명시
- 구현·검증 문서가 실제 상태와 일치

# 12. 완료 금지 조건

다음 중 하나라도 남으면 최종 완료로 보고하지 않는다.

- 시즌 저장이 `season_spin` 등 별도 UI 상태를 다시 읽음
- 후보 수만 표시하고 실제 후보 목록이 없음
- 이전 completed 때문에 새 메시지가 완료로 표시됨
- 정책 제외 메시지가 매번 신규로 재등장함
- processed 상태 갱신이 기존 record ID를 삭제함
- 메시지 수정에서 숫자 player_id 또는 내부 key 직접 입력이 필요함
- CSV 출처가 수동/자동 두 값으로 축약됨
- CI가 `PENDING_PUSH` 또는 실행 미확인 상태임
- 실제 Windows 125% 미검증인데 완료라고 서술함

# 13. 최종 보고 형식

## 완료

- A1~A4별 사용자에게 보이는 결과

## 검증

- 전체 pytest 결과
- 집중 테스트 결과
- 제품 커밋 SHA
- GitHub Actions run ID와 Linux/Windows 결과
- 실제 Windows 125% 결과

## 남은 사용자 확인

- 실제로 남은 항목만 기재

## 최종 판정

- `병합 가능`
- `조건부 병합 가능`
- `병합 보류`

중 하나로 명시한다.
