# 로컬라이제이션 기능 검증 보고서

- 검증 기준 문서: `docs/localization_features.md`
- 검증일: 2026-06-22
- 검증 방식: 요구사항-구현 추적, 정적 번역 키 검사, 관련 단위 테스트, 전체 회귀 테스트, Qt 오프스크린 스모크 테스트

## 1. 종합 판정

**부분 구현 / 조건부 통과**로 판정한다.

UI 언어 설정·첫 실행 언어 선택·이름 매핑·추천·주요 화면의 한글명 표시는 구현되어 있고 핵심 관련 테스트도 통과했다. 그러나 문서가 주장하는 “전체 UI 텍스트 번역”, “모든 박스스코어 임포트에서 미등록 이름 수집”, “수동 입력 다이얼로그에서 한글명 병기”는 현재 코드와 일치하지 않는다.

| 영역 | 판정 | 요약 |
|---|---|---|
| 앱 시작 시 언어 적용 | 통과 | GUI import 전에 설정 언어를 적용함 |
| 첫 실행 언어 선택 | 통과(정적 검증) | 선택값 저장 및 English 선택 시 프로세스 재시작 코드 존재 |
| 설정 화면 언어 변경 | 통과 | 저장 후 재시작 필요 안내가 구현됨 |
| 전체 UI 번역 커버리지 | 실패 | 누락된 `tr()` 키 7개와 다수의 하드코딩 한국어 UI 문자열 존재 |
| 한글 이름 조합/표시 순서 | 통과 | 양쪽 파트 완성 조건과 한국/서양식 순서가 구현됨 |
| 미등록 이름 대기열 | 부분 통과 | MLB Only가 켜진 임포트와 초기 스탯 임포트에서는 동작하나, MLB Only를 끄면 박스스코어 수집 호출이 생략됨 |
| 자동 추천 | 통과 | 성씨, 참조값, 접미사/접두사, 하이픈, 퍼지, 음역 폴백이 구현됨 |
| 매핑 다이얼로그 | 통과 | 오프스크린 생성 및 현재 대기열 36행 로드 확인 |
| 주요 화면 한글명 표시 | 부분 통과 | 기록·예측·레이팅에는 구현됐으나 수동 입력 선수 목록에는 없음 |
| UI 언어와 한글 이름의 독립성 | 통과 | English UI에서도 한글명 조합 결과가 유지됨 |

## 2. 확인된 정상 구현

### 2.1 UI 언어 전환 기반

- `main.py`는 설정을 읽고 `set_language()`를 호출한 뒤 `gui.app`을 import한다. 모듈 수준에서 번역된 문자열에도 의도한 언어가 적용되는 순서다.
- `AppSettings`와 `SettingsManager`는 `language`, `language_selected`를 로드·저장한다.
- `gui/app.py`의 `_LanguageSelectDialog`는 첫 설정 전 표시되며, 선택값 저장과 English 선택 시 `subprocess.Popen()` 후 종료 흐름을 갖는다.
- `gui/views/setup_view.py`는 Language 콤보 값을 저장하고 변경 시 재시작 필요 메시지를 표시한다.

### 2.2 한글 이름 처리

- `KoreanNameMapper.format_player_name()`은 성과 이름이 모두 존재할 때 한쪽 매핑이 빠지면 빈 문자열을 반환한다.
- `Nation == "South Korea"`는 성+이름, 그 외 국가는 이름+공백+성 순서를 사용한다.
- 로스터의 `FirstName`, `LastName`, `Nation`을 player ID로 연결해 축약된 DB 이름을 보완한다.
- 초기 스탯 임포트는 MLB 행의 이름 파트를 `source="stats"`로 대기열에 기록한다.
- 박스스코어 수집 함수 자체는 `games.is_mlb = 1`로 MLB 선수만 선별하고, 매핑이 있는 파트와 축약명은 제외한다.
- 번들/사용자 CSV 병합 시 사용자 데이터가 나중에 적용되어 우선한다.
- 마일스톤 기록, 예측, 레이팅 일괄 편집 화면의 한글명 컬럼 연결을 확인했다.

## 3. 발견된 문제

### [높음] UI 번역 커버리지가 문서 설명보다 불완전함

정적 AST 검사 결과 `tr()`에 전달되는 고정 키 494개 중 7개가 한국어 딕셔너리에 없었다. 한국어 모드에서 다음 문구가 영어 원문으로 표시된다.

- `Season Games`
- `Season Year`
- `The season year currently in progress in OOTP...`
- `saved_games Folder`
- `⚙️  Tracking Settings`
- `📁  OOTP Integration`
- `🛠️  Tools`

모두 `gui/views/setup_view.py`의 초기 설정 UI에서 사용된다. 비슷하지만 다른 키(`Season Games:`, `📁  OOTP Integration Settings`)만 번역 딕셔너리에 있어 fallback이 발생한다.

또한 `tr()`를 거치지 않는 한국어 사용자 노출 문자열이 다수 있다. 대표적으로 다음 경로가 English UI에서도 한국어로 남는다.

- `core/stats/player_display.py`: `타격`, `투구`, `기록 없음`, `한글명`, `박스스코어 표기`, `[수동]`
- `core/db/reset.py`: DB 초기화 요약 전체
- `core/milestone/predictor.py`, `core/milestone/prediction_store.py`: 가능/불가/데이터 없음 문구
- `core/roster/rating_fields.py`: 레이팅 섹션 제목
- 여러 validation/error 경로의 한국어 메시지

따라서 “전체 앱 UI 텍스트 커버”와 “모든 메시지 번역” 주장은 충족되지 않는다.

### [중간] MLB Only를 끄면 박스스코어 이름 대기열 수집이 생략됨

`gui/workers/import_worker.py`와 `gui/workers/reimport_worker.py`는 `settings.import_mlb_only`가 참일 때만 `note_players_from_boxscore_import()`를 호출한다. 그러나 이 함수 내부에서 이미 MLB 경기만 필터링한다.

그 결과 MLB Only를 끄고 MLB와 비 MLB 경기를 함께 가져오는 사용자는, 같은 배치에 포함된 MLB 선수의 미등록 이름도 대기열에 넣지 못한다. 문서의 “박스스코어를 임포트할 때 자동 수집” 설명과 다르다.

### [중간] 수동 입력 선수 목록에 한글명이 병기되지 않음

`gui/widgets/manual_milestone_dialog.py`의 선수 콤보는 `format_player_list_label()` 또는 `format_manual_entry_label()`만 사용한다. 한글 이름 mapper를 불러오거나 `korean_display_for_player()`를 호출하는 경로가 없다.

문서 2-8의 “수동 입력 다이얼로그 — 선수 선택 목록에 한글명 병기”는 현재 구현되지 않은 것으로 판정한다.

### [낮음] 문서와 기본 파일의 정보가 오래됨

- 문서는 기본 데이터를 성 64개·이름 34개라고 설명하지만 현재 CSV는 성 1,029개·이름 1,242개다.
- `data/settings.json.example`에는 `language`, `language_selected` 필드가 없다. 런타임 기본값으로 기능은 동작하지만 문서의 저장 예시와 배포용 예제 파일이 일치하지 않는다.
- 번역 전용 자동 테스트가 없어 위 누락 키와 하드코딩 문자열을 회귀 시 자동 탐지하지 못한다.

## 4. 테스트 결과

### 관련 기능 테스트

다음 테스트 묶음은 워크스페이스 내부 임시 디렉터리를 사용해 실행했으며 **26개 모두 통과**했다.

```text
tests/test_korean_names.py
tests/test_korean_name_suggest.py
tests/test_bundle_updates.py
tests/test_player_display.py

26 passed in 0.89s
```

확인 범위에는 한국/서양식 이름 순서, 부분 매핑 차단, 축약명+로스터 보완, 대기열 저장, 사용자 데이터 우선, 자동 추천, 번들 병합이 포함된다.

### 추가 스모크/정적 검사

- Qt 오프스크린 모드에서 첫 실행 언어 선택 다이얼로그와 한글 이름 매핑 다이얼로그 생성 성공
- 매핑 다이얼로그에서 현재 pending 36행 로드 확인
- 한국어/English 전환 시 `tr("Milestone Records")` 결과 전환 확인
- English 전환 후에도 `문동주`, `마이크 트라우트` 조합 결과 유지 확인
- 고정 `tr()` 키 검사: 494개 사용, 한국어 딕셔너리 511개, 사용 키 누락 7개

### 전체 회귀 테스트

```text
168 passed, 6 skipped, 39 failed, 6 errors
```

전체 테스트는 green 상태가 아니다. 실패·오류의 대다수는 저장소에 테스트가 요구하는 `samples/boxscore_html`, `samples/initial_stats`, `samples/game_logs` 픽스처가 없어서 발생했다. 별도로 `test_should_record_streak_on_break_thresholds`는 현재 정책값과 테스트 기대값이 다른 비 로컬라이제이션 회귀다. 따라서 전체 회귀 결과는 로컬라이제이션 실패 증거로 보지 않았지만, 배포 전 테스트 환경 복구가 필요하다.

## 5. 권고 조치

1. 누락된 7개 키를 `_KO`에 추가하고, 사용자 노출 하드코딩 문자열을 `tr()` 경로로 이동한다.
2. 박스스코어 임포트 후 이름 수집 호출을 `import_mlb_only` 조건 밖으로 옮긴다. 함수 내부 MLB 필터는 유지한다.
3. 수동 입력 선수 콤보를 만들 때 roster 이름과 mapper를 함께 사용해 한글명을 병기한다.
4. `data/settings.json.example`에 두 언어 필드를 추가하고 문서의 기본 매핑 건수를 현재 값 또는 자동 산출 방식으로 갱신한다.
5. 정적 `tr()` 키 완전성, English 모드의 하드코딩 한국어, 첫 실행 설정 저장을 검증하는 테스트를 추가한다.
6. 누락된 `samples/` 픽스처와 연속기록 정책 테스트 불일치를 복구한 뒤 전체 회귀 테스트를 다시 실행한다.

## 6. 검증 한계

- 실제 OOTP 설치·실제 사용자 save를 이용한 종단간 임포트는 수행하지 않았다.
- English 선택 시 새 프로세스가 실제로 재기동되는 동작은 부작용을 피하기 위해 코드 경로만 검증했다.
- GUI 다이얼로그는 오프스크린 생성과 데이터 로드까지 검증했으며, 사용자의 실제 클릭·OS 기본 앱 열기까지 자동화하지 않았다.

---

## 7. 2026-06-22 변경 이력 재검수

### 7.1 재검수 판정

`docs/localization_features.md` 하단의 **“2026-06-22 — 로컬라이제이션 검수 후 개선”** 변경 이력을 기준으로 재검수했다.

종합 판정은 **부분 반영 / 추가 수정 필요**다.

이전에 지적한 누락 번역 키, 박스스코어 대기열 호출 조건, 기본 설정 예제와 문서의 매핑 건수는 정상적으로 수정됐다. 지정된 화면의 하드코딩 문자열도 대부분 번역 경로로 이동했다. 그러나 전체 UI 번역 커버리지는 아직 완성되지 않았고, 수동 입력 선수 목록의 한글명 병기 수정은 표시 문자열이 실제 선수명 데이터로 유입되는 회귀를 만들었다.

| 변경 이력 항목 | 재검수 판정 | 검수 결과 |
|---|---|---|
| 누락된 `tr()` 키 7개 추가 | 통과 | 고정 `tr()` 키 508개를 검사한 결과 `_KO` 누락 0개 |
| `player_display.py` 번역 | 통과 | English 모드에서 `Batting`, `Korean Name`, `Boxscore name`, `[Manual]` 출력 확인 |
| DB 초기화 요약 번역 | 통과 | English 모드에서 7개 요약 행이 모두 영문으로 출력됨 |
| 예측 문자열 번역 | 통과(코드·회귀 테스트) | predictor와 prediction store가 동일한 번역 키를 사용하도록 변경됨 |
| 레이팅 섹션 번역 | 통과 | 영어 키 저장 후 다이얼로그에서 `tr(section.title)`을 적용함 |
| 박스스코어 대기열 조건 수정 | 통과(코드 경로) | import/reimport 양쪽 호출이 `import_mlb_only` 조건 밖으로 이동함 |
| 수동 입력 목록 한글명 병기 | 실패 | 화면 병기는 되지만 표시값이 이적·부상 선수명 데이터로 그대로 전달됨 |
| `settings.json.example` 갱신 | 통과 | `language`, `language_selected` 필드 존재 확인 |
| 문서 매핑 건수 갱신 | 통과 | 현재 CSV 행 수인 성 1,029개·이름 1,242개와 일치 |
| “UI 번역 커버리지 완성” | 실패 | 번역되지 않은 사용자 노출 validation/error 문자열이 여전히 존재 |

### 7.2 정상 반영된 변경

#### 누락 번역 키

AST 기반 정적 검사 결과는 다음과 같다.

```text
static_tr_keys=508
ko_entries=545
missing=0
dynamic_calls=5
```

이전 검수에서 발견한 7개 누락 키는 모두 추가됐다. 초기 설정 화면의 `Season Year`, `Season Games`, `saved_games Folder`, 세 카드 제목과 시즌 툴팁이 한국어 모드에서 번역된다.

#### 지정된 하드코딩 UI 문자열

- `core/stats/player_display.py`: English 모드 출력 정상
- `core/db/reset.py`: 숫자 천 단위 포맷을 유지하면서 한·영 요약 출력 정상
- `core/milestone/predictor.py`, `core/milestone/prediction_store.py`: 예측 결과가 현재 언어의 번역 키를 사용함
- `core/roster/rating_fields.py`, `gui/widgets/player_rating_dialog.py`: 내부 제목은 영어 키, 화면 표시는 `tr()` 결과를 사용함

#### 대기열·기본 파일·문서

- `gui/workers/import_worker.py`와 `gui/workers/reimport_worker.py` 모두 `note_players_from_boxscore_import()`를 조건 없이 호출한다. 함수 내부의 `games.is_mlb = 1` 필터가 유지되어 의도한 범위만 수집한다.
- `data/settings.json.example`의 언어 필드와 문서의 매핑 건수가 실제 파일과 일치한다.

### 7.3 재검수에서 발견된 문제

#### [높음] 수동 입력 한글명 병기가 선수명 저장·조회 값을 오염시킴

`gui/widgets/manual_milestone_dialog.py`는 콤보 표시 문구를 다음처럼 구성한다.

```text
Mike Trout / 마이크 트라우트
```

하지만 `_combo_text()`는 표시 문구 전체인 `combo.currentText()`를 반환한다. 이 값은 다음 경로에서 실제 선수명으로 사용된다.

- 이적 폼: `joining_players`, `leaving_players`
- 부상 폼: `player_name`

오프스크린 GUI 재현 결과:

```text
combo_label='Mike Trout / 마이크 트라우트'
combo_value='Mike Trout / 마이크 트라우트'
parsed_transfer=['Mike Trout / 마이크 트라우트']
value_is_canonical=False
```

따라서 선택 목록의 한글명 **표시**는 구현됐지만, 이적 시 player ID 조회가 실패하거나 부상 기록에 장식된 표시 문자열이 선수명으로 저장될 수 있다. 마일스톤 탭은 콤보의 player ID를 직접 해석하므로 같은 문제가 발생하지 않는다.

권장 수정은 표시 레이블과 원본 값을 분리하는 것이다. 콤보 item data에 player ID와 canonical full name을 유지하고, 이적 선택 처리 및 부상 폼 생성 시 표시 문자열이 아닌 canonical name을 사용해야 한다.

#### [중간] “UI 번역 커버리지 완성”은 아직 충족되지 않음

변경 이력에 명시한 주요 파일은 수정됐지만, English 모드에서 한국어로 반환되는 사용자 노출 validation/error 문자열이 남아 있다. 실제 확인 예시는 다음과 같다.

```text
validate_manual_injury(...) in English mode
→ ['선수를 입력하세요.', '부상 내용을 입력하세요.', '소속팀을 입력하세요.']
```

추가 확인된 대표 경로:

- `core/milestone/manual_entry.py`: 수동 기록·이적·부상 검증 오류와 중복 경고
- `core/milestone/definitions.py`: 마일스톤 정의 검증 오류
- `core/milestone/record_edit.py`: 기록 편집 검증 오류
- `core/milestone/checker.py`: 수동 기록 관련 오류
- `core/stats/aggregator.py`: 비 MLB 박스스코어 오류
- `core/roster/player_registry.py`, `core/roster/editor.py`, `core/roster/korean_names.py`: 사용자 입력·파일 오류

이 문자열들은 다이얼로그나 임포트 결과에서 사용자에게 표시될 수 있으므로 “버튼·레이블·메시지 전체 번역” 기준에서는 미완료다. 한편 첫 실행 언어 선택창의 한·영 병기 문자열과 한글 이름/음역 데이터는 기능상 의도된 한국어이므로 이 미완료 판정에서 제외했다.

#### [낮음] 변경 내용을 직접 보호하는 자동 테스트가 추가되지 않음

현재 테스트에는 다음 회귀를 직접 검출하는 항목이 없다.

- 모든 고정 `tr()` 키가 `_KO`에 존재하는지
- English 모드 validation/error가 한국어를 반환하지 않는지
- 수동 입력 콤보의 표시명과 canonical 선수명이 분리되는지
- `import_mlb_only=False`일 때도 import/reimport worker가 이름 수집 함수를 호출하는지

이번 수동 입력 회귀도 기존 테스트가 UI 표시값의 데이터 전달을 검사하지 않아 통과했다.

### 7.4 재검수 테스트 결과

관련 테스트 범위를 확대해 실행했다.

```text
tests/test_korean_names.py
tests/test_korean_name_suggest.py
tests/test_bundle_updates.py
tests/test_player_display.py
tests/test_manual_milestone.py
tests/test_db_reset.py

50 passed in 0.98s
```

정적 번역 키 검사는 누락 0개로 통과했고, Qt 오프스크린으로 English 출력과 수동 입력 콤보를 검증했다. 수동 입력 콤보 스모크 테스트에서 위 canonical name 회귀가 재현됐다.

전체 테스트 결과는 이전과 동일하다.

```text
168 passed, 6 skipped, 39 failed, 6 errors
```

대다수 실패·오류는 여전히 저장소에 없는 `samples/` 픽스처 때문이며, 비 로컬라이제이션 연속기록 정책 불일치 1건도 유지된다. 따라서 전체 회귀 테스트 환경은 아직 복구되지 않았다.

### 7.5 재검수 결론 및 우선 조치

변경 이력에 명시된 수정의 대부분은 의도대로 반영됐다. 수동 입력 한글명 병기는 사용자에게 보이는 결과만 충족하고 데이터 무결성을 깨뜨릴 수 있으므로 배포 전 수정이 필요하다.

우선순위는 다음과 같다.

1. 수동 입력 콤보의 표시값과 canonical 선수명을 분리하고, 이적·부상 저장 경로 테스트를 추가한다.
2. 남은 사용자 노출 validation/error 문자열을 영어 키 기반 `tr()` 경로로 이동한다.
3. 정적 번역 키 완전성과 English 출력에 대한 자동 회귀 테스트를 추가한다.
4. 누락된 `samples/` 픽스처를 복구해 전체 테스트를 green 상태로 만든다.

---

## 8. 2026-06-22 (1차) 변경 이력 검수

### 8.1 검수 기준과 판정

`docs/localization_features.md`의 **“2026-06-22 (1차) — 로컬라이제이션 검수 후 개선”** 항목을 기준으로 현재 코드를 다시 검수했다. 현재 작업 트리에는 1차 변경과 이후 2차 보완이 함께 존재하므로, 1차 요구사항의 구현 여부와 2차 변경 이후의 회귀 여부를 함께 확인했다.

판정은 **1차 변경 항목 반영 완료 / 전체 로컬라이제이션 조건부 통과**다.

1차 변경 이력에 명시된 개별 수정은 모두 코드에 반영되어 있고 관련 화면·출력도 동작한다. 이전 재검수에서 발견한 수동 입력 canonical name 오염은 2차 수정으로 해결됐다. 다만 1차의 “로컬라이제이션 커버리지 완성”이라는 종합 표현은 아직 엄밀히 충족되지 않으며, 예측 캐시의 언어 전환 일관성 문제와 일부 사용자 노출 한국어 하드코딩이 남아 있다.

### 8.2 1차 변경 항목별 결과

| 1차 변경 항목 | 판정 | 검수 결과 |
|---|---|---|
| 누락 번역 키 7개 추가 | 통과 | 현재 고정 `tr()` 사용 키 누락 0개 |
| `player_display.py` 하드코딩 제거 | 통과 | 역할·한글명·박스스코어명·수동 레이블의 한·영 출력 정상 |
| DB 초기화 요약 번역 | 통과 | 7개 요약 행이 현재 언어로 출력됨 |
| predictor 예측 결과 번역 | 통과(단, 캐시 주의) | 생성 시 현재 언어를 반영하나 저장된 결과의 언어 전환 문제가 있음 |
| prediction store 상태 번역 | 부분 통과 | 번역 생성은 정상이나 번역문 자체를 DB에 저장함 |
| 레이팅 섹션 제목 번역 | 통과 | 영어 키와 `tr(section.title)` 연결 확인 |
| 박스스코어 이름 대기열 조건 수정 | 통과(코드 경로) | import/reimport 모두 `import_mlb_only` 조건 밖에서 호출 |
| 수동 입력 목록 한글명 병기 | 통과 | 화면 병기와 canonical 선수명 분리 모두 실제 GUI에서 확인 |
| `settings.json.example` 언어 필드 | 통과 | 두 필드가 예제 JSON에 존재 |
| 문서 이름 매핑 건수 | 통과 | 성 1,029개·이름 1,242개로 실제 CSV와 일치 |

### 8.3 정적 번역 검사

현재 코드의 고정 `tr()` 호출을 AST로 수집해 `_KO` 딕셔너리와 비교했다.

```text
static_tr_keys=537
ko_entries=579
missing=0
dynamic_calls=6
```

1차에서 추가한 7개 키를 포함해 고정 키 누락은 없다. 동적 호출에는 레이팅 섹션 제목처럼 제한된 영어 키 집합을 전달하는 경로가 포함되며, 해당 키가 `_KO`에 존재함을 별도로 확인했다.

### 8.4 UI 및 데이터 전달 재검증

Qt 오프스크린 환경에서 `Mike Trout` 선수를 임시 DB에 구성하고 수동 입력 다이얼로그를 검사했다.

```text
display='Mike Trout / 마이크 트라우트'
canonical='Mike Trout'
injury_player='Mike Trout'
transfer_text='Mike Trout'
english_errors=[
  'Please enter a player.',
  'Please enter the injury.',
  'Please enter the affiliated team.'
]
```

검수 결과:

- 선수 콤보에는 한글명이 정상 병기된다.
- 부상 폼에는 표시 문자열이 아닌 canonical 선수명만 전달된다.
- 이적 멀티선택에도 canonical 선수명만 추가된다.
- 2차에서 수정한 수동 입력 validation 메시지는 English 모드에서 영문으로 반환된다.

따라서 §7에서 지적했던 수동 입력 데이터 오염 회귀는 현재 코드에서 해결된 것으로 판정한다.

### 8.5 새로 확인된 문제

#### [중간] 예측 상태 캐시가 언어 변경을 즉시 반영하지 않음

`core/milestone/prediction_store.py`는 `tr()`로 번역한 `season_note`를 만들고, `core/stats/aggregator.py`의 `milestone_predictions.season_note` 컬럼에 번역문 자체를 저장한다. 예측 화면은 이 저장 문자열을 다시 번역하지 않고 그대로 표시한다.

한국어 상태에서 예측 행을 저장한 뒤 English로 언어만 전환하는 검사를 수행한 결과:

```text
stored_ko='시즌 전 — 달성 가능성 미정'
after_switch_en='시즌 전 — 달성 가능성 미정'
current_en='Pre-season — achievability unknown'
matches_current_language=False
```

앱 언어를 바꿔 재시작하더라도 기존 예측 캐시가 다시 계산되기 전까지 이전 언어가 남을 수 있다. 이 문제는 1차 변경의 “prediction store 상태 문자열 번역”이 생성 시점에는 동작하지만 언어 전환 관점에서는 완전하지 않음을 의미한다.

권장 방식은 다음 중 하나다.

1. DB에는 언어 중립적인 상태 코드와 수치만 저장하고 화면에서 `tr()`로 조합한다.
2. 최소 수정으로는 언어 변경 시 현재 시즌 prediction cache를 무효화하거나 재생성한다.

#### [중간] 사용자 노출 한국어 하드코딩이 일부 남아 있음

1·2차에서 많은 validation 문자열을 번역했지만 다음 대표 경로는 English 모드에서도 한국어가 노출될 수 있다.

- `core/stats/aggregator.py`: `MLB 박스스코어가 아닙니다.` 임포트 오류
- `core/roster/player_registry.py`: 선수 이름 입력 오류
- `core/roster/editor.py`: 지원하지 않는 로스터 형식 오류
- `core/roster/korean_names.py`: CSV 저장·입력 오류
- `core/milestone/manual_entry.py`: 지원하지 않는 이적 유형 fallback 오류
- `core/milestone/implementation.py`: 수동 입력 필요 메시지

경기 설명·음역 데이터·첫 실행 언어 선택창의 의도된 한글은 이 판정에서 제외했다. 사용자에게 오류나 안내로 직접 표시되는 문자열만 잔여 문제로 분류했다.

#### [낮음] 1차 변경을 직접 보호하는 테스트 부족

관련 기존 테스트는 통과하지만 다음 항목을 직접 고정하는 자동 테스트는 여전히 없다.

- 고정 `tr()` 키와 `_KO`의 완전성
- `import_mlb_only=False`에서 worker의 이름 수집 호출
- 수동 입력 GUI의 표시값/canonical 값 분리
- 언어 전환 후 prediction cache의 표시 언어

### 8.6 테스트 결과

1차 기능과 연관된 테스트 범위를 확대해 실행했다.

```text
tests/test_korean_names.py
tests/test_korean_name_suggest.py
tests/test_bundle_updates.py
tests/test_player_display.py
tests/test_manual_milestone.py
tests/test_db_reset.py
tests/test_milestone_definitions_io.py

53 passed in 1.39s
```

전체 테스트 결과:

```text
168 passed, 6 skipped, 39 failed, 6 errors
```

전체 결과는 이전 검수와 동일하다. 실패·오류의 대부분은 저장소에 없는 `samples/` 픽스처에 기인하며, 비 로컬라이제이션 연속기록 정책 테스트 불일치 1건도 남아 있다. 전체 테스트 환경은 여전히 green 상태가 아니다.

### 8.7 결론

2026-06-22 (1차) 변경 이력에 적힌 구체적인 수정은 모두 확인됐고, 핵심 로컬라이제이션 동작은 정상이다. 2차 보완으로 수동 입력 canonical name 문제도 해결됐다.

배포 전 남은 우선 조치는 다음과 같다.

1. prediction cache에 번역문을 저장하지 않도록 언어 중립화하거나 언어 변경 시 캐시를 재생성한다.
2. 남은 사용자 노출 오류 문자열을 `tr()` 경로로 이동한다.
3. 위 두 항목과 1차 변경을 보호하는 자동 회귀 테스트를 추가한다.
4. 누락된 `samples/` 픽스처를 복구해 전체 테스트를 green 상태로 만든다.
