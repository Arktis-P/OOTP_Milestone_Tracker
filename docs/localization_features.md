# 로컬라이제이션 관련 기능 설명

이 문서는 `feature/localization` 브랜치에서 개발된 **언어 관련 기능** 두 가지를 설명합니다.

1. **앱 UI 언어 전환** — 버튼, 레이블, 메시지 등을 한국어 / English로 전환
2. **OOTP 파일 내 한글 이름 처리** — 박스스코어·스탯 파일에 있는 선수 이름을 한글로 표시

이 두 기능은 **서로 독립적**입니다. UI 언어를 English로 설정해도 선수 이름을 한글로 표시하는 기능은 그대로 동작하고, 반대도 마찬가지입니다.

---

## 1. 앱 UI 언어 전환

### 1-1. 어떻게 동작하는가

앱이 시작될 때 `settings.json`에 저장된 `language` 값을 읽고, GUI 모듈을 로드하기 **전에** 언어를 설정합니다. 그 이후로 모든 UI 문자열은 `tr("English key")` 함수를 통해 반환됩니다.

```python
# main.py
settings = SettingsManager().load()
set_language(settings.language)   # "ko" 또는 "en"

from gui.app import run_app        # ← GUI 모듈은 이후에 임포트됨
```

`tr()` 함수의 동작:

| 언어 설정 | `tr("Milestone Records")` 반환값 |
|-----------|----------------------------------|
| `"ko"` | `"마일스톤 기록"` |
| `"en"` | `"Milestone Records"` (키 그대로) |
| 번역 키 없음 | 원문 fallback (한국어 문자열 포함) |

### 1-2. 번역 딕셔너리 (`core/i18n/translator.py`)

영어 문자열을 키, 한국어 번역을 값으로 하는 `_KO` 딕셔너리를 관리합니다. 약 670줄, 전체 앱 UI 텍스트를 커버합니다.

플레이스홀더가 있는 문자열도 그대로 키로 사용합니다:

```python
tr("Import failed: {message}").format(message=err)
tr("{count} games added").format(count=3)
```

번역이 적용된 UI 영역:

- 사이드바 메뉴 항목, 탭 제목
- 각 탭(대시보드, 마일스톤 기록, 스탯, 예측, 로스터, 설정)의 모든 버튼·레이블·메시지
- 모든 팝업 다이얼로그 (18개)
- 박스스코어 임포트 진행 메시지
- DB 경고 배너 (`format_overlap_warning()`)
- 번들 업데이트 파일 레이블 및 결과 다이얼로그

### 1-3. 언어 선택 다이얼로그

앱 **첫 실행 시** 초기 설정창 이전에 언어를 선택하는 팝업이 표시됩니다.

```
┌───────────────────────────────────────────────┐
│        OOTP Milestone Tracker                 │
│  언어를 선택해 주세요 / Select Language        │
│                                               │
│   [ 한국어 (Korean) ]    [ English ]          │
│                                               │
│              [ 계속 / Continue ]              │
└───────────────────────────────────────────────┘
```

**한국어** 선택 시:
- `language = "ko"`, `language_selected = true` 저장 → 설정창으로 진행

**English** 선택 시:
- `language = "en"`, `language_selected = true` 저장
- 현재 프로세스 종료 + 새 프로세스 시작 (`subprocess.Popen + sys.exit`)
- 재시작된 앱은 English UI로 설정창 표시

**이후 실행**: `language_selected = true`이면 다이얼로그를 건너뜁니다.

### 1-4. 설정에서 언어 변경

초기 설정 이후에도 설정 탭의 **Language** 드롭다운에서 변경할 수 있습니다. 변경 후 앱을 재시작하면 적용됩니다.

### 1-5. settings.json 저장 구조

```json
{
  "language": "ko",
  "language_selected": true
}
```

| 필드 | 의미 |
|------|------|
| `language` | `"ko"` 또는 `"en"` |
| `language_selected` | `true`이면 언어 선택 다이얼로그를 건너뜀 |

---

## 2. OOTP 파일 내 한글 이름 처리

### 2-1. 문제 상황

OOTP는 모든 선수 이름을 **로마자**로 저장합니다. 예를 들어 KBO 선수가 OOTP에 등록되어 있어도 파일 안에는 `"Dong-ju Moon"`, `"Kim"`, `"Taek-yun"` 처럼 영문으로만 기록되어 있습니다.

앱은 이 로마자 이름을 **한글**(`"문동주"`, `"김택연"`)로 변환해서 표시하는 기능을 제공합니다.

> **팀 이름에 대해**: OOTP는 팀을 약칭(`NYY`, `LAD`, `LG` 등)으로 관리합니다. 팀 이름 자체는 별도로 한글화하지 않으며, 약칭이 그대로 표시됩니다.

### 2-2. 전체 흐름

```
OOTP 파일 (영문 이름)
        ↓
  박스스코어 / 스탯 임포트
        ↓
  [미등록 이름] → korean_names_pending.csv 대기열 추가
        ↓
  한글 이름 매핑 다이얼로그
        ↓
  [자동 추천값 표시 or 사용자 직접 입력]
        ↓
  저장 → korean_last_names.csv / korean_first_names.csv
        ↓
  앱 UI에서 한글 이름 표시 (선수명 (한글) 컬럼 등)
```

### 2-3. 이름 분리 방식

OOTP 박스스코어는 선수 이름을 `"Dong-ju Moon"` (First Last) 형식으로 기록합니다. 앱은 이를 성(`Moon`)과 이름(`Dong-ju`)으로 분리해서 각각 따로 매핑합니다.

```
"Dong-ju Moon"  →  last: "Moon"  +  first: "Dong-ju"
```

- **성** → `korean_last_names.csv` (`last_name` 컬럼)
- **이름** → `korean_first_names.csv` (`first_name` 컬럼)

성과 이름 모두 매핑이 있을 때만 한글 이름이 완성됩니다. 둘 중 하나만 있으면 표시하지 않습니다.

**표시 순서:**
- 한국인 선수 (`Nation = "South Korea"`): 성+이름 순 → `"문동주"`
- 그 외 선수: 이름+공백+성 순 → `"마이크 트라우트"`

### 2-4. 대기열(Pending) 시스템

박스스코어나 스탯 파일을 임포트할 때, 한글 매핑이 없는 이름을 자동으로 수집합니다:

```python
# 임포트 완료 후 자동 실행
note_players_from_boxscore_import(aggregator, game_ids)
```

수집된 이름은 `korean_names_pending.csv`에 저장됩니다:

```csv
part,name,source,first_seen
last,Moon,boxscore,2026-06-18
first,Dong-ju,boxscore,2026-06-18
last,Kim,boxscore,2026-06-18
```

이미 매핑이 있는 이름은 대기열에 추가되지 않습니다. 약칭 형태(`J. Kim`)는 분리하기 어려우므로 제외합니다.

로스터 파일(`mlb_rosters.csv`)이 있으면 선수의 `FirstName` / `LastName` / `Nation` 필드를 참조해 이름 분리를 더 정확하게 합니다.

### 2-5. 자동 추천 기능 (`core/roster/korean_name_suggest.py`)

한글 이름 매핑 다이얼로그를 열면 대기 목록에 자동 추천 한글 표기를 생성합니다. 추천은 아래 순서로 탐색합니다:

| 단계 | 방법 | 예시 |
|------|------|------|
| 1 | 한국인 성씨 정적 테이블 (성만) | `"Kim"` → `"김"` |
| 2 | CSV 참조 파일 대소문자 무시 정확 매칭 | `"moon"` = `"Moon"` → `"문"` |
| 3 | Jr./Sr./II/III 등 접미사 처리 | `"Moon Jr."` → `"문 주니어"` |
| 4 | Mc, Mac, O', Van, De 등 접두사 처리 | `"McDonald"` → `"맥도날드"` |
| 5 | 하이픈 분리 후 각 부분 개별 탐색 | `"Dong-ju"` → `"동주"` |
| 6 | 퍼지 매칭 (유사도 0.93 이상) | `"Seong"` ≈ `"Sung"` → `"성"` |
| 7 | 인접 매칭 (유사도 0.86 이상) | — |
| 8 | MLB 음역 규칙 엔진 (폴백) | 규칙 기반 영→한 변환 |

추천값은 다이얼로그에서 **회색 이탤릭**으로 표시되며, 사용자가 수정하지 않고 저장하면 그대로 매핑에 반영됩니다. 직접 입력하거나 수정하면 흰색으로 바뀝니다.

### 2-6. 참조 파일 구조

```
data/
├── korean_last_names.csv      ← 성 매핑 (앱 번들 기본값 + 사용자 추가)
├── korean_first_names.csv     ← 이름 매핑 (앱 번들 기본값 + 사용자 추가)
└── korean_names_pending.csv   ← 아직 한글 미등록 이름 대기열
```

번들 파일과 사용자 파일을 모두 읽어 병합하며, **사용자 파일이 우선**합니다. 앱 업데이트 시 번들에 새 매핑이 추가되면 `Run Merge Update` 기능으로 사용자 파일에 병합할 수 있습니다.

기본 제공 데이터: 성 1,029개, 이름 1,242개

CSV 형식:

```csv
last_name,korean
Moon,문
Kim,김
Park,박
```

```csv
first_name,korean
Dong-ju,동주
Taek-yun,택연
```

### 2-7. 한글 이름 매핑 다이얼로그 (`gui/widgets/korean_name_mapping_dialog.py`)

**설정 탭 → "Open Pending Mappings"** 버튼으로 열 수 있습니다.

```
┌────────────────────────────────────────────────────────────────────┐
│  Pending Mappings                                                  │
│  한글 표기 필요: 42건 · 추천 38건 · 표시 42건                      │
│  [검색...]                                 [Refresh List]          │
│  Edit CSV: [Last Name CSV] [First Name CSV] [Pending List CSV]     │
├──────┬──────────────┬──────────────┬────────────────┬─────────────┤
│ Type │ Full Name    │ Romanized    │ Korean Name    │ Source      │
├──────┼──────────────┼──────────────┼────────────────┼─────────────┤
│ 성   │ … Moon       │ Moon         │ 문 (회색)      │ boxscore    │
│ 이름 │ Dong-ju …    │ Dong-ju      │ 동주 (회색)    │ boxscore    │
│ 성   │ … Smith      │ Smith        │ (직접 입력)    │ boxscore    │
└──────┴──────────────┴──────────────┴────────────────┴─────────────┘
│                              [Save Entered Items]  [Close]        │
└────────────────────────────────────────────────────────────────────┘
```

- **회색** 항목: 자동 추천값. 수정 없이 저장하면 매핑에 반영됨
- **흰색** 항목: 사용자가 직접 입력한 값
- **빈 칸** 항목: 추천 실패, 사용자가 직접 입력 필요
- "Edit CSV" 버튼: 각 CSV 파일을 OS 기본 앱(엑셀, 메모장 등)으로 바로 열기

### 2-8. 앱 UI에서 한글 이름이 표시되는 위치

| 탭 / 기능 | 표시 방식 |
|-----------|-----------|
| 마일스톤 기록 탭 | "Player Name (Korean)" 컬럼 |
| 마일스톤 예측 탭 | "Korean Name" 컬럼 |
| 수동 입력 다이얼로그 | 선수 선택 목록에 한글명 병기 |
| 레이팅 편집 | 로스터 목록에 한글명 표시 (매핑이 있을 때) |

---

## 3. 두 기능의 관계 정리

| 구분 | UI 언어 전환 | 선수 이름 한글 표시 |
|------|-------------|---------------------|
| 제어 위치 | `settings.json` → `language` 필드 | CSV 매핑 파일 |
| 적용 대상 | 버튼, 레이블, 다이얼로그 메시지 | 선수 이름 컬럼 |
| 소스 | `core/i18n/translator.py` | `core/roster/korean_names.py` |
| 기본값 | 한국어 (`"ko"`) | 매핑 없으면 빈 칸 |
| 독립성 | 서로 영향 없음 | 서로 영향 없음 |

UI를 English로 설정해도 매핑된 선수 이름은 한글로 표시됩니다. UI를 한국어로 설정해도 매핑이 없는 선수 이름은 영문으로 표시됩니다.

---

## 변경 이력 (Changelog)

### 2026-06-22 (3차) — 8차 검수 결과 반영

검수 보고서(`docs/localization_verification_report.md` §8)에서 확인된 문제들을 수정했습니다.

#### 예측 캐시 언어 중립화 ([중간])

- **`core/milestone/prediction_store.py`**: `_season_note()`가 `tr()`로 번역한 문자열을 DB에 저장하던 문제를 수정했습니다. 이제 번역 대신 언어 중립적 코드(`"pre_season"`, `"achievable|{n}"`, `"not_achievable|{n}|{m}"`)를 DB에 저장합니다.
  - `_season_note()` 반환값을 언어 중립 코드로 변경.
  - `render_season_note(note: str) -> str` 공개 함수 추가: 저장된 코드를 현재 언어로 변환합니다.
- **`gui/views/predict_view.py`**: `item.season_note`를 직접 표시하던 부분을 `render_season_note(item.season_note)` 호출로 변경했습니다. 언어 전환 후 재시작해도 예측 상태(`"가능 (+...)"`, `"시즌 전 — 달성 가능성 미정"` 등)가 현재 설정 언어로 올바르게 표시됩니다.

#### 남은 사용자 노출 한국어 하드코딩 제거 ([중간])

- **`core/stats/aggregator.py`**: `import_game()` 의 `"MLB 박스스코어가 아닙니다."` 오류 문자열을 `tr("Not an MLB boxscore.")`으로 변경. `from core.i18n import tr` 추가.
- **`core/roster/player_registry.py`**: `add_manual_player()`의 `"선수 이름을 입력하세요."` 두 곳을 `tr("Please enter a player name.")`으로 변경. `from core.i18n import tr` 추가.
- **`core/roster/editor.py`**: `load()`의 `"지원하지 않는 로스터 형식입니다. OOTP export (.txt) 파일이 필요합니다."` 를 `tr("Unsupported roster format. An OOTP export (.txt) file is required.")`으로 변경. `from core.i18n import tr` 추가.
- **`core/roster/korean_names.py`**: CSV 저장 실패 오류와 `apply_mapping()` 입력 검증 오류를 tr()로 변경. `from core.i18n import tr` 추가.
  - `_format_store_io_error()`: 파일 저장 불가 오류 메시지 → `tr("Cannot save 「{name}」.\n...")`
  - `apply_mapping()`: 입력값 검증 오류 → `tr("Please enter both the name and Korean notation.")`
- **`core/milestone/manual_entry.py`**: `build_transfer_records()`의 fallback 오류 `"지원하지 않는 이적 유형입니다."` → `tr("Unsupported transfer type.")` (키는 기존에 등록됨).
- **`core/i18n/translator.py`**: 5개 신규 키 추가 (`"Not an MLB boxscore."`, `"Please enter a player name."`, `"Unsupported roster format..."`, `"Cannot save 「{name}」..."`, `"Please enter both the name and Korean notation."`).

---

### 2026-06-22 (2차) — 재검수 결과 반영

재검수 보고서(`docs/localization_verification_report.md` §7)에서 발견된 문제들을 수정했습니다.

#### 수동 입력 콤보 canonical name 오염 수정 ([높음])

- **`gui/widgets/manual_milestone_dialog.py`**: 선수 콤보에 한글명을 병기할 때 표시 레이블(`"Mike Trout / 마이크 트라우트"`)이 이적·부상 저장 경로에 선수명으로 전달되는 버그를 수정했습니다.
  - `_fill_player_combo()`: 항목 추가 시 canonical base_label을 `Qt.ItemDataRole.UserRole + 1`에 저장합니다.
  - `_configure_player_multipick_combo()`의 `on_activated`: 드롭다운 선택 시 canonical name을 사용해 comma-separated 명단을 구성합니다.
  - `_canonical_player_text()` 헬퍼 추가: 현재 선택 항목의 canonical name(한글 접미사 제외)을 반환합니다.
  - 부상 폼의 `player_name`: `_combo_text()` 대신 `_canonical_player_text()` 사용.

#### 이적 유형 레이블 번역 적용 ([중간])

- **`core/milestone/manual_entry.py`**: `TRANSFER_EVENT_LABELS` 값을 English 키(`"FA Contract"`, `"Extension Contract"`, `"Trade"`, `"Player Purchase"`)로 변경.
- **`gui/widgets/manual_milestone_dialog.py`**: 콤보 추가 시 `tr(label)` 적용.
- **`core/i18n/translator.py`**: 이적 유형 4개 키 추가.

#### 사용자 노출 validation/error 문자열 번역 ([중간])

아래 파일들의 한국어 validation 에러 문자열을 `tr()` 경로로 변경했습니다.

- **`core/milestone/manual_entry.py`**: `validate_manual_entry`, `validate_manual_transfer`, `validate_manual_injury`, `check_duplicate` 함수 전체 (15개 문자열)
- **`core/milestone/record_edit.py`**: `validate_record_update`, `normalize_achieved_date` (3개 문자열)
- **`core/milestone/definitions.py`**: `validate_milestone_definition` 함수 전체 (11개 문자열)
- **`core/milestone/checker.py`**: `record_manual_transfer`, `record_manual_injury`의 ValueError 메시지 2개
- **`core/i18n/translator.py`**: validation error 및 이적 유형 관련 총 34개 키 추가

---

### 2026-06-22 (1차) — 로컬라이제이션 검수 후 개선 (검수 보고서 기반)

검수 결과(`docs/localization_verification_report.md`)에서 발견된 문제들을 수정하여 로컬라이제이션 커버리지를 완성했습니다.

#### UI 번역 커버리지 완성 ([높음])

- **`core/i18n/translator.py` — 누락 키 추가**: 검수에서 발견된 7개 미번역 키를 `_KO` 딕셔너리에 추가했습니다.
  - `Season Year`, `Season Games`, `saved_games Folder`
  - `📁  OOTP Integration`, `⚙️  Tracking Settings`, `🛠️  Tools`
  - `The season year currently in progress in OOTP.\nUsed for...` (툴팁)

- **`core/stats/player_display.py` — 하드코딩 한국어 제거**: `"타격"`, `"투구"`, `"기록 없음"`, `"한글명"`, `"박스스코어 표기"`, `"[수동]"` 를 모두 `tr()` 경로로 변경했습니다. English UI에서도 영문으로 표시됩니다.

- **`core/db/reset.py` — DB 초기화 요약 번역**: `format_save_data_summary()`의 7개 한국어 줄(`MLB 경기`, `기록 선수` 등)을 `tr()` 키로 변경했습니다.

- **`core/milestone/predictor.py` — 예측 결과 문자열 번역**: `"데이터 없음"`, `"가능 (+...)"`, `"불가 (+..., 시즌 후 ... 남음)"` 등 8개 한국어 문자열을 `tr()` 로 변경했습니다.

- **`core/milestone/prediction_store.py` — 예측 상태 문자열 번역**: `"시즌 전 — 달성 가능성 미정"`, `"가능 (+...)"`, `"불가 (+...)"` 를 `tr()` 로 변경했습니다.

- **`core/roster/rating_fields.py` + `gui/widgets/player_rating_dialog.py` — 레이팅 섹션 제목 번역**: 12개 한국어 섹션 제목(`"선수 기본 정보"`, `"타자 현재 레이팅"` 등)을 영어 키로 변경하고, 다이얼로그에서 `tr()` 를 통해 표시합니다. `"HBP (투수)"` 레이블도 `"HBP (Pitcher)"` 영어 키로 변경했습니다.

#### 박스스코어 이름 대기열 수집 수정 ([중간])

- **`gui/workers/import_worker.py`**, **`gui/workers/reimport_worker.py`**: `note_players_from_boxscore_import()` 호출을 `if self.settings.import_mlb_only:` 조건 밖으로 이동했습니다. 이 함수는 내부에서 MLB 경기만 필터링하므로 MLB Only 설정과 무관하게 항상 동작합니다. MLB Only를 끄고 임포트해도 MLB 선수의 미등록 이름이 대기열에 수집됩니다.

#### 수동 입력 다이얼로그 한글명 병기 ([중간])

- **`gui/widgets/manual_milestone_dialog.py`**: 선수 콤보박스를 채울 때 `KoreanNameMapper`와 로스터 이름을 로드하여 각 선수의 한글명을 계산하고 레이블에 병기합니다. 예: `"[B] Mike Trout / 마이크 트라우트"`. 매핑이 없는 선수는 기존 레이블만 표시됩니다.

#### 기본 파일 및 문서 갱신 ([낮음])

- **`data/settings.json.example`**: `language`, `language_selected` 두 필드를 예제 파일에 추가했습니다.
- **`docs/localization_features.md`**: 기본 제공 이름 매핑 건수를 실제 현황(성 1,029개, 이름 1,242개)으로 정정했습니다.
