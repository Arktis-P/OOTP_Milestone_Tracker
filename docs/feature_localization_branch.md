# feature/localization 브랜치 개발 내용

> 기준 브랜치: `master` → `feature/localization`  
> 커밋 수: 11개 (+ 현재 세션 미커밋 포함)  
> 변경 파일 수: 68개, +4,916줄 / -1,174줄

---

## 목차

1. [다크모드 UI 전면 개편](#1-다크모드-ui-전면-개편)
2. [앱 로컬라이제이션 (한국어 / English 전환)](#2-앱-로컬라이제이션-한국어--english-전환)
3. [한글 이름 자동 추천 기능](#3-한글-이름-자동-추천-기능)
4. [연속기록 설명 자동 생성](#4-연속기록-설명-자동-생성)
5. [홈런 다중 파싱 수정](#5-홈런-다중-파싱-수정)
6. [연속기록 추적 기준 조정](#6-연속기록-추적-기준-조정)
7. [세이브별 DB 분리 및 마이그레이션](#7-세이브별-db-분리-및-마이그레이션)
8. [기타 버그 수정 및 테스트 추가](#8-기타-버그-수정-및-테스트-추가)

---

## 1. 다크모드 UI 전면 개편

**관련 커밋**: `8ee4502`, `4fc15d3`, `9a97a45`, `7ee5868`, `bfac3e0`  
**변경 파일**: `gui/theme.py`, `gui/sidebar_nav.py`, `gui/widgets/card_panel.py`, `gui/widgets/app_dialog.py`, `gui/widgets/grade_styles.py`, 각 view 파일 전체

### 1-1. 통합 테마 시스템 (`gui/theme.py`)

기존에 각 파일마다 흩어져 있던 색상 하드코딩을 단일 `theme.py`로 통합했다.

| 범주 | 상수 예시 | 값 |
|------|-----------|-----|
| 배경 | `BG_WINDOW`, `BG_SIDEBAR`, `BG_PANEL`, `BG_ELEVATED` | `#1e1e1e` 계열 |
| 텍스트 | `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TEXT_MUTED` | `#cccccc` 계열 |
| 액센트 | `ACCENT`, `ACCENT_HOVER`, `ACCENT_PRESSED` | `#0078d4` (VS Code 블루) |
| 시맨틱 | `RED_BG/BORDER/TEXT`, `AMBER_BG/BORDER/TEXT`, `BLUE_BG/BORDER/TEXT`, `GREEN_TEXT` | — |

이 상수들을 `panel_style()`, `button_style()`, `table_style()` 등 헬퍼 함수로 조합해 반환하는 구조. 각 위젯은 `theme.panel_style()` 한 줄로 일관된 스타일을 적용한다.

기존 `SLATE_*`, `EMERALD_*` 등 tailwind 스타일 별칭도 하위호환을 위해 유지.

### 1-2. 사이드바 리뉴얼 (`gui/sidebar_nav.py`)

178줄 전면 재작성. 주요 변경:
- 메뉴 항목마다 **아이콘 + 레이블** 레이아웃으로 변경
- 선택된 탭: 좌측 `ACCENT` 컬러 세로 바 + `BG_ELEVATED` 배경 강조
- 번들 업데이트 뱃지: `"Bundle update available"` 조건부 표시 (주황색 dot)
- DB 연결 상태 (`SQLite DB Connected`) 하단 상태 표시

### 1-3. CardPanel 위젯 (`gui/widgets/card_panel.py`)

그룹 UI의 표준 컴포넌트로 신규 추가. `QFrame` 기반으로 `BG_PANEL` 배경 + `BORDER` 1px 테두리 + `border-radius: 6px` 스타일. `QGroupBox` 대신 설정창과 각 탭의 섹션 구분에 사용.

두 버전:
- `CardPanel(title)` — 헤더 레이블 포함
- `CardPanel()` — 헤더 없는 순수 패널

### 1-4. AppDialog 기반 클래스 (`gui/widgets/app_dialog.py`)

모든 팝업 다이얼로그의 공통 베이스 클래스로 신규 추가. 주요 기능:
- 자동 다크 팔레트 적용 (`apply_dark_palette()`)
- 표준 버튼 헬퍼 (`ok_button()`, `save_button()`)
- `Escape` 키 닫기 기본 연결
- 다이얼로그 제목 폰트 통일

기존 18개 다이얼로그 위젯이 이 클래스를 상속하도록 변경.

### 1-5. 등급 스타일 (`gui/widgets/grade_styles.py`)

마일스톤 등급(S / A / B / C / D) 배지 색상을 theme 상수 기반으로 재정의. 예측 뷰, 마일스톤 뷰의 Grade 셀에 일관 적용.

### 1-6. 첫 실행 설정창 레이아웃 재설계 (`gui/views/setup_view.py`)

`_build_first_run_layout()` 전면 교체:

**이전**: `QGroupBox` + `QFormLayout` 단일 컬럼  
**이후**: `CardPanel` 2열 그리드

```
┌──────────────────────────────┬──────────────────────────┐
│ 📁 OOTP Integration          │ ⚙️ Tracking Settings      │
│  · 세이브 폴더               │  · 추적 팀                │
│  · 리그 선택                 │  · 시즌 경기 수           │
│  · 현재 시즌                 │  · 언어                   │
│                              ├──────────────────────────┤
│                              │ 🛠️ Tools                  │
│                              │  · 한글 이름 매핑         │
│                              │  · 참조 파일 업데이트     │
│                              │  · 마일스톤 정의 편집     │
└──────────────────────────────┴──────────────────────────┘
```

---

## 2. 앱 로컬라이제이션 (한국어 / English 전환)

**관련 커밋**: `aa58fc3` + 현재 세션 작업  
**변경 파일**: `core/i18n/translator.py`, `core/i18n/__init__.py`, `core/config/settings_manager.py`, `main.py`, `gui/app.py`, gui 전체 33개 파일

### 2-1. 번역 엔진 (`core/i18n/translator.py`)

gettext 방식의 경량 번역 시스템:

```python
from core.i18n import tr

label = tr("Milestone Records")   # ko → "마일스톤 기록", en → "Milestone Records"
```

- **영어 키 → 한국어 값** 구조의 `_KO` 딕셔너리 (~670줄)
- `tr(key)`: ko 모드면 `_KO[key]` 반환, en 모드면 key 그대로 반환, 키 없으면 fallback
- `set_language(lang)` / `get_language()`: 언어 전역 설정

플레이스홀더 포함 문자열도 그대로 키로 사용:
```python
tr("Import failed: {message}").format(message=err)
tr("Career stats warning: {seasons} season(s) exist in both initial data and boxscores. "
   "Career totals may be inflated. "
   "Re-import from the Initial Setup tab, excluding those seasons.").format(seasons=seasons_str)
```

번역 항목 카테고리:
- 사이드바 메뉴 / 상태바
- 대시보드, 마일스톤 기록, 스탯, 예측, 로스터, 설정 등 각 탭 전체
- 18개 다이얼로그 위젯의 모든 버튼·레이블·메시지
- Workers의 progress 문자열
- bundle_updates 파일 레이블 및 다이얼로그
- DB 중복 경고 배너

### 2-2. 모듈 임포트 순서 보장 (`main.py`)

```python
# GUI 모듈 임포트 전에 언어 설정
settings = SettingsManager().load()
set_language(settings.language)

from gui.app import run_app  # ← 여기서 모듈 레벨 tr() 상수 평가
```

모듈 레벨에서 `tr()` 결과를 상수로 쓰는 코드(`COLUMNS = [tr("Name"), ...]`)가 있어도 언어 설정 이후에 임포트되므로 안전하다.

### 2-3. 언어 선택 다이얼로그 (`gui/app.py` — `_LanguageSelectDialog`)

앱 **첫 실행** 시, 초기 설정창 이전에 표시되는 언어 선택 팝업:

```
┌─────────────────────────────────────────┐
│  OOTP Milestone Tracker                 │
│  언어를 선택해 주세요 / Select Language  │
│                                         │
│   [한국어 (Korean)]   [English]         │
│                                         │
│         [계속 / Continue]               │
└─────────────────────────────────────────┘
```

동작 흐름:
- **한국어** 선택 → `language="ko"` 유지, `language_selected=True` 저장, 설정창 진행
- **English** 선택 → `language="en"`, `language_selected=True` 저장 → `subprocess.Popen` + `sys.exit()` 으로 프로세스 재시작 → 영어 UI로 설정창 표시
- 이후 실행: `language_selected=True`이므로 다이얼로그 스킵

### 2-4. AppSettings 신규 필드 (`core/config/settings_manager.py`)

```python
@dataclass
class AppSettings:
    language: str = "ko"            # "ko" | "en"
    language_selected: bool = False  # 다이얼로그 재표시 방지
```

`save()` / `_parse_json()` 양쪽에 반영되어 `settings.json`에 직렬화됨.

### 2-5. 번역 적용 범위

| 레이어 | 적용 |
|--------|------|
| `gui/views/` (7개) | 완료 |
| `gui/widgets/` (18개) | 완료 |
| `gui/workers/` (import, reimport) | 완료 |
| `gui/app.py`, `gui/sidebar_nav.py` | 완료 |
| `core/config/bundle_updates.py` | 완료 (FILE_LABELS, 다이얼로그) |
| `core/db/validation.py` | 완료 (overlap 경고 배너) |
| `gui/workers/initial_import_worker.py` | 해당 없음 (UI 문자열 없음) |
| `core/milestone/description_templates.py` | 적용 제외 (게임 데이터, 항상 한국어) |

---

## 3. 한글 이름 자동 추천 기능

**관련 커밋**: `3d16abc`, `912089d`  
**변경 파일**: `core/roster/korean_name_suggest.py`, `core/roster/korean_name_reference.py`, `core/roster/mlb_name_phonetic.py`, `data/korean_last_names.csv`, `data/korean_first_names.csv`, `gui/widgets/korean_name_mapping_dialog.py`

### 3-1. 문제 배경

선수 이름이 OOTP에는 로마자로 저장(`"Dong-ju Moon"`)되지만, 앱 UI에는 한글(`"문동주"`)로 표시하고 싶다. 기존에는 사용자가 수동으로 입력해야 했는데, 자동으로 한글 표기를 추천해 주는 기능을 추가했다.

### 3-2. 추천 파이프라인 (`core/roster/korean_name_suggest.py`)

`suggest_korean_name(part, roman)` 함수가 아래 순서로 후보를 탐색한다:

```
1. 한국인 성씨 정적 테이블 직접 매칭 (last name only)
   예: "Kim" → "김", "Park" → "박", "Lee" → "이"

2. CSV 참조 파일에서 대소문자 무시(ci) 정확 매칭
   korean_last_names.csv / korean_first_names.csv

3. 접미사 분리 후 재탐색
   예: "Moon Jr." → base="Moon", suffix="주니어"

4. 로마자 접두사 처리 후 나머지 탐색
   예: "McDonald" → "맥" + lookup("Donald")
       "Van Gorder" → "반 " + lookup("Gorder")

5. 하이픈 이름: 각 세그먼트 개별 탐색 후 결합
   예: "Dong-ju" → lookup("Dong") + lookup("ju")

6. 퍼지 매칭 (difflib, cutoff 0.93)
   예: "Seong" ~ "Sung" → "성"

7. 인접 매칭 (cutoff 0.86)

8. MLB 음역 규칙 엔진 (mlb_name_phonetic.py)
   영어 → 한글 규칙 기반 음역 폴백
```

### 3-3. 참조 파일 시스템 (`core/roster/korean_name_reference.py`)

번들 기본값(`data/korean_last_names.csv`, `data/korean_first_names.csv`)과 사용자 파일을 병합. 사용자 데이터가 우선한다. 결과는 캐시에 저장되어 반복 로드를 방지.

CSV 컬럼: `last_name` (또는 `first_name`) + `korean`

초기 데이터: 성 64개 / 이름 34개 번들 제공.

### 3-4. MLB 음역 규칙 엔진 (`core/roster/mlb_name_phonetic.py`)

CSV 참조에도 없는 이름에 대한 규칙 기반 폴백. KBO 중계 표준 음역 규칙을 구현:
- 이중자음 / 모음 결합 패턴
- 어두/어말 위치별 다른 처리
- 영어 특수 자소(th, ph, ck, ng 등) 처리

294줄 분량의 규칙 테이블 포함.

### 3-5. UI 연동 (`gui/widgets/korean_name_mapping_dialog.py`)

한글 이름 매핑 다이얼로그가 대기 목록을 로드할 때 자동으로 추천값을 생성:

- 추천값이 있는 항목: **회색 이탤릭** 표시, 툴팁으로 `"자동 추천 표기입니다. 수정·삭제하지 않고 저장하면 매핑에 반영됩니다."` 안내
- 직접 입력한 항목: 일반 흰색 표시, `"직접 입력한 표기입니다."` 툴팁
- 상단 요약 레이블: `"한글 표기 필요: 42건 · 추천 38건 · 표시 42건"` 형식

저장 시 추천값과 수동값 모두 `korean_last_names.csv` / `korean_first_names.csv`에 기록.

### 3-6. 무한 루프 수정 (`912089d`)

첫 번째 구현(`3d16abc`)에서 `korean_name_mapping_dialog.py`의 리스트 갱신이 저장 → 갱신 → 저장을 재귀 호출하는 무한 루프 버그 발생. `_refreshing` 플래그 guard로 수정.

---

## 4. 연속기록 설명 자동 생성

**관련 커밋**: `e4e294e`  
**변경 파일**: `core/db/schema.py`, `core/streak/engine.py`, `core/streak/policies.py`, `core/streak/tracker.py`

### 4-1. DB 스키마 변경 (`core/db/schema.py`)

`milestone_records` 테이블에 `description TEXT` 컬럼 추가. 기존 테이블에는 `ALTER TABLE` 마이그레이션으로 자동 추가.

### 4-2. 설명 포맷 함수 (`core/streak/policies.py`)

연속기록 달성 시 `description` 필드에 자동으로 채울 텍스트를 생성:

```python
format_streak_description(
    start_date="2026-04-05",
    end_date="2026-05-22",
    value=21,
    streak_type="hit",
    policies=policies,
)
# → "2026-04-05 부터 2026-05-22 까지, 21경기 연속"
```

날짜 없이 수치만 있는 경우: `"21경기 연속"`  
투구 이닝 연속(`unit="outs"`)의 경우: `"15.0이닝 연속"` 형식으로 outs→IP 변환.

### 4-3. 연속기록 엔진 / 트래커 연동 (`core/streak/engine.py`, `tracker.py`)

연속기록이 종료되어 마일스톤으로 기록될 때, 시작 날짜(`start_date`)와 종료 날짜(`end_date`)를 추적해 두었다가 `format_streak_description()`으로 설명을 채운다. 이전에는 `description`이 빈 문자열이었다.

---

## 5. 홈런 다중 파싱 수정

**관련 커밋**: `fd5fe91`  
**변경 파일**: `core/parser/batting_notes.py`, `core/stats/aggregator.py`, `gui/workers/import_worker.py`

### 5-1. 문제

한 경기에 홈런 2개를 친 경우, OOTP 박스스코어의 BATTING 섹션에:

```
Home Runs:
  J. Smith 2 (5th Inning, solo; 8th Inning, 1 on)
```

형태로 기록된다. 기존 파서는 이 패턴을 1개로 읽어 실제보다 홈런 수가 적게 집계되는 버그가 있었다.

### 5-2. 수정 (`core/parser/batting_notes.py`)

`_resolve_game_event_count()` 로직 보강:
- `"Name N (season, Xth Inning ...; Yth Inning ...)"` 패턴에서 이닝 세그먼트 수를 카운트해 게임 내 이벤트 횟수로 사용
- 이닝 정보 없이 세미콜론만 있는 경우 → 외부 카운트 `N` 우선
- `assign_batting_events_to_lineup()` 추가: 같은 팀에 동명이인이 있을 때 이닝 단위 순서로 각 선수에 이벤트를 배분

### 5-3. 집계 로직 업데이트 (`core/stats/aggregator.py`)

박스스코어 임포트 시 `assign_batting_events_to_lineup()`을 사용하도록 변경. 기존 홈런 합산이 부정확했던 경우를 위해 `refresh_batting_events()` 함수를 추가해 기존 DB 레코드를 재계산할 수 있게 함.

---

## 6. 연속기록 추적 기준 조정

**관련 커밋**: `cfe1e6a`  
**변경 파일**: `data/streak_policies.json`

### 변경 내용

`streak_policies.json`에서 일부 연속기록 추적 기준값 조정. 예를 들어 안타 연속기록의 `min_value`, 삼진 연속기록의 기준 등을 현실 OOTP 게임 데이터에 맞게 조정.

이 파일은 `bundle_updates` 시스템을 통해 앱 업데이트 시 사용자 로컬 파일에 자동 병합된다 (`added_paths` 방식).

---

## 7. 세이브별 DB 분리 및 마이그레이션

**관련 커밋**: `912089d` (부분)  
**변경 파일**: `core/config/save_db.py`, `data/.legacy_shared_db_migrated`

### 7-1. 세이브별 독립 DB

기존에는 모든 세이브가 단일 `data/records.db`를 공유했다. 이번 변경으로 세이브마다 고유한 경로(`data/saves/<save_name>/records.db`)를 사용하도록 변경.

`save_db_relative_path(save_path)` 함수가 세이브 이름에서 해시를 생성해 안전한 디렉토리 이름을 만든다.

### 7-2. 레거시 마이그레이션 (`migrate_legacy_shared_db`)

앱이 시작되거나 세이브가 선택될 때 자동으로 실행:
1. `data/records.db` (공유 DB)가 존재하는지 확인
2. 존재하면 현재 세이브의 새 경로로 복사
3. `data/.legacy_shared_db_migrated` 마커 파일 생성 후 스킵

`AppSettings.db_path`도 `save_db_relative_path()`의 반환값으로 자동 설정된다.

---

## 8. 기타 버그 수정 및 테스트 추가

### 8-1. 추가된 테스트

| 파일 | 내용 |
|------|------|
| `tests/test_batting_events_refresh.py` | 홈런 다중 파싱 및 배분 로직 검증 (47줄) |
| `tests/test_batting_notes_counts.py` | 다양한 BATTING 노트 패턴 파싱 검증 (12줄) |
| `tests/test_korean_name_suggest.py` | 추천 엔진 입출력 검증 (89줄) |
| `tests/test_save_db.py` | 세이브 DB 경로 생성 / 마이그레이션 검증 (35줄) |
| `tests/test_save_switch.py` | 세이브 전환 시 DB 경로 변경 동작 검증 (95줄) |
| `tests/test_streak_tracker.py` | 연속기록 추적 엣지케이스 보강 (23줄 추가) |

### 8-2. 파일 열기 유틸 (`gui/utils/file_open.py`)

OS 기본 프로그램으로 파일을 여는 크로스 플랫폼 헬퍼 (`open_file_in_default_app()`) 추가. 한글 이름 매핑 다이얼로그의 "CSV 편집" 버튼에서 사용.

### 8-3. README 업데이트

`README.md`에 로컬라이제이션, 세이브별 DB 분리, 한글 이름 자동 추천 기능 관련 내용 갱신 (+53줄 변경).

---

## 요약 테이블

| 기능 | 파일 수 | 상태 |
|------|---------|------|
| 다크모드 UI 전면 개편 | ~20개 | 완료 |
| 로컬라이제이션 (한/영 전환) | ~35개 | 완료 |
| 한글 이름 자동 추천 | 5개 | 완료 |
| 연속기록 설명 자동 생성 | 5개 | 완료 |
| 홈런 다중 파싱 수정 | 3개 | 완료 |
| 연속기록 추적 기준 조정 | 1개 (JSON) | 완료 |
| 세이브별 DB 분리 | 2개 | 완료 |
| 테스트 추가 | 6개 | 완료 |
