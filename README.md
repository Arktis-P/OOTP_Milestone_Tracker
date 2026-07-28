# OOTP Milestone Tracker

Out of the Park Baseball(OOTP)의 세이브 데이터를 읽어 선수·팀 마일스톤, 연속 기록, 선수별 기록, 기록 달성 예측을 관리하는 Windows 데스크톱 애플리케이션입니다.

**현재 버전:** 0.1.9  
**대상 환경:** Windows, Python 3.11 이상, PyQt6, SQLite

> README용 화면 이미지는 아직 저장소에 포함되어 있지 않습니다. 깨진 이미지 링크를 넣지 않고, 촬영할 화면과 상태만 [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md)에 정리했습니다.

## 무엇을 할 수 있나요

- OOTP 박스스코어 HTML을 가져와 경기·시즌·통산·팀 마일스톤을 자동 기록합니다.
- 타격·투구 stats export를 초기값으로 가져와 프로그램 도입 전 시즌·통산 기록을 채웁니다.
- 현재 시즌의 선수 기록, 통산 기록, 포스트시즌 기록, 경기별 로그를 조회합니다.
- 현재값과 목표값을 비교해 통산 마일스톤 달성 예측과 임박 항목을 보여줍니다.
- 진행 중인 연속 기록과 저장된 종료 연속 기록을 확인하고 CSV로 내보냅니다.
- 마일스톤, 수상, 팀 이동, 부상 기록을 수동으로 추가·수정·삭제합니다.
- 시즌 종료 후 stats export를 기준으로 AVG/OBP/SLG/OPS/ERA 같은 비율 마일스톤을 판정합니다.
- MLB·KBO 로스터 레이팅을 열어 단일 선수 또는 조건별 일괄 편집 후 수정 파일을 저장합니다.
- OOTP 세이브마다 별도 SQLite DB를 사용해 여러 리그의 기록을 분리합니다.
- 한글 이름 매핑 CSV와 선택적 Gemini 설정으로 선수 이름 표시를 보정합니다.

## 설치 및 실행

### 소스 코드로 실행

```powershell
git clone https://github.com/Arktis-P/OOTP_Milestone_Tracker.git
cd OOTP_Milestone_Tracker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy data\settings.json.example data\settings.json
python main.py
```

PowerShell 실행 정책 때문에 `.venv\Scripts\activate`가 막히면 가상환경을 활성화하지 않고 다음처럼 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

최초 실행 시 언어를 선택한 뒤 **설정** 화면에서 OOTP 세이브를 지정합니다. 소스 실행의 사용자 데이터는 저장소의 `data/` 아래에 생성됩니다.

### Windows 배포본 사용

릴리스 압축 파일이 제공되는 경우 압축을 풀고 `ootp_milestone_tracker.exe`를 실행합니다. 배포본의 사용자 데이터는 다음 폴더에 저장되며, 앱을 업데이트해도 설정·DB·이름 매핑 파일은 유지됩니다.

```text
%APPDATA%\OOTP_Milestone_Tracker\
```

### 개발자용 명령

```powershell
pytest
python build.py
```

`python build.py`는 PyInstaller one-folder 배포본과 `dist/ootp_milestone_tracker_v0.1.9.zip` 형식의 압축 파일을 생성합니다.

## OOTP에서 준비할 파일과 경로

| 준비물 | 기본 위치 또는 파일명 | 사용하는 화면 | 용도와 주의사항 |
|---|---|---|---|
| `saved_games` 폴더 | `Documents\Out of the Park Developments\OOTP Baseball {버전}\saved_games` | 설정 | 앱이 OOTP 20-26의 기본 문서 폴더를 자동 탐색하거나 사용자가 직접 지정합니다. 자동 탐색되지 않는 버전이나 위치는 수동으로 선택합니다. 폴더 안에 `.lg` 리그 폴더가 있어야 합니다. |
| 활성 리그 폴더 | `{리그명}.lg` | 설정 | 선택한 리그를 기준으로 DB, 박스스코어, stats, 로스터 경로가 파생됩니다. |
| stats export | `import_export\player_batting_stats.txt`, `import_export\player_pitching_stats.txt` | 기존 기록 가져오기, 달성 기록 | 과거 시즌·통산 초기값, 오프시즌 갱신, 시즌 종료 비율 기록 판정에 사용합니다. |
| 박스스코어 HTML | `news\html\box_scores\game_box_*.html` | 대시보드, 달성 기록, 선수 기록 | 새 경기 import, 마일스톤·연속 기록 판정, 현재 시즌 누적 기록에 사용합니다. |
| 게임 로그 HTML | `news\html\game_logs\log_{game_id}.html` | 달성 기록, 선수 기록 | 경기 로그 버튼과 수동 설명 참고 패널에 사용합니다. 없으면 기록 import 자체는 가능하지만 로그 열기는 제한됩니다. |
| MLB/KBO 로스터 export | `import_export\mlb_rosters`, `import_export\kbo_rosters` 또는 같은 이름의 `.csv`/`.txt` 파일 | 레이팅 편집 | 통계와 마일스톤에는 반영되지 않고 레이팅 편집 전용으로 사용합니다. |

## 처음 사용하는 순서

1. `python main.py` 또는 exe로 앱을 실행합니다.
2. 최초 실행 언어를 선택합니다.
3. **설정**에서 `saved_games` 폴더를 자동 탐색 또는 수동 지정하고 활성 리그를 선택합니다.
4. **설정**에서 현재 시즌, 시즌 경기 수, 추적 팀을 저장합니다.
5. OOTP에서 `player_batting_stats.txt`와 `player_pitching_stats.txt`를 export합니다.
6. **기존 기록 가져오기**에서 두 파일을 선택하고 **Initial setup — load all data through completed season** 모드로 **Load Database**를 실행합니다.
7. OOTP 경기 후 생성된 `game_box_*.html`을 **대시보드**, **달성 기록**, 또는 **선수 기록**의 **Import Boxscores**로 가져옵니다.
8. **대시보드**에서 최근 마일스톤, 임박 예측, 진행 중 연속 기록, 설정 체크리스트가 정상인지 확인합니다.
9. **달성 기록**, **선수 기록**, **기록 달성 예측**에서 첫 기록이 원하는 선수·팀에 반영됐는지 확인합니다.

## 새 경기 후 반복 사용

```text
OOTP에서 새 경기 진행
→ 박스스코어 파일 생성 확인
→ Import Boxscores 실행
→ 대시보드에서 최근 기록과 연속 기록 확인
→ 필요 시 달성 기록에서 수동 이벤트 추가
→ 선수 기록과 기록 달성 예측에서 상세 확인
```

앱은 이전에 처리한 박스스코어의 파일명과 수정 시간을 DB에 저장합니다. 변경 없는 파일은 건너뛰고, OOTP가 방금 쓰는 중인 파일처럼 import 시작 후 변경된 파일은 다음 실행으로 미룹니다.

오프시즌 또는 시즌 종료 후에는 OOTP stats 파일을 다시 export한 뒤 **기존 기록 가져오기**의 **Off-season update — add previous season + compare** 모드를 사용합니다. 현재 시즌 값 차이만 보고 저장하지 않으려면 **Mid-season compare — check differences without saving** 모드를 사용합니다.

## 화면별 기능 인벤토리

### 대시보드

| 항목 | 내용 |
|---|---|
| 사용 목적 | 앱 실행 직후 현재 리그 상태, 준비 단계, 최근 성과, 임박 예측, 진행 중 연속 기록을 한 화면에서 확인합니다. |
| 진입 화면 | 사이드바 **대시보드**. |
| 필요한 입력 | 설정 완료된 활성 리그, 현재 시즌, 추적 팀, 박스스코어 폴더. 예측에는 기존 기록 가져오기 또는 박스스코어 기록이 필요합니다. |
| 주요 조작 | **Import Boxscores**, **MLB Only**, **Cancel**, **Import Existing Records**, 최근 기록 클릭, 임박 예측 클릭, **View Ended Streaks**. |
| 확인 가능한 결과 | 최근 마일스톤 10개, 임박 예측 10개, 진행 중 연속 기록, 마지막 import 시각, 세팅 체크리스트. |
| 제한 및 주의사항 | 박스스코어 폴더가 없으면 import가 시작되지 않습니다. **MLB Only**가 켜져 있으면 KBO, WBC 등 비 MLB 박스스코어는 건너뜁니다. 종료 연속 기록은 **Streak Center** 대화상자에서 읽기 전용으로 봅니다. |

### 달성 기록

| 항목 | 내용 |
|---|---|
| 사용 목적 | 자동 감지된 마일스톤과 수동 입력 기록을 필터링, 편집, 삭제, export합니다. |
| 진입 화면 | 사이드바 **달성 기록**. |
| 필요한 입력 | 조회에는 DB 기록이 필요합니다. 수동 입력에는 날짜, 선수 또는 팀, 기록 종류, 값, 시즌, 경기 수, 상대, 설명·메모가 사용됩니다. 시즌 종료 비율 판정에는 최신 stats export가 필요합니다. |
| 주요 조작 | **Import Boxscores**, 주체·팀·범위·시즌·이벤트 유형·등급·출처 필터, 검색, **Add Record** 메뉴의 **Milestone/Award/Team Move/Injury**, **Export**의 **Full History CSV/Streak CSV**, **Determine Final Season Records**, **Edit**, **Delete**, 더블클릭으로 게임 로그 열기. |
| 확인 가능한 결과 | 날짜, 선수명, 한글명, 팀, 마일스톤, 유형, 출처, 상대, 설명, 메모, 연결된 게임 ID와 값. |
| 제한 및 주의사항 | 수동 기록은 자동 re-import에서 삭제되지 않습니다. 과거 경기 또는 같은 날짜 복수 경기의 안전한 재처리는 제한될 수 있습니다. 게임 로그 폴더나 `log_{game_id}.html`이 없으면 게임 로그 열기와 참고 문구 표시가 제한됩니다. |

### 선수 기록

| 항목 | 내용 |
|---|---|
| 사용 목적 | 추적 팀 선수별 시즌·통산·포스트시즌 기록과 개인 마일스톤 타임라인을 확인합니다. |
| 진입 화면 | 사이드바 **선수 기록**. |
| 필요한 입력 | 추적 팀 설정, 기존 기록 또는 박스스코어 import 결과. 게임별 로그 조회에는 박스스코어 import 데이터와 게임 로그 HTML이 필요합니다. |
| 주요 조작 | **Import Boxscores**, **MLB Only**, 시즌 선택, 포지션 필터, 선수 검색, **Season/Career/Postseason** 전환, **Batting/Pitching/Milestones** 탭, 시즌 기록 표 더블클릭. |
| 확인 가능한 결과 | 선수 목록, 한글 이름, 요약 카드, 타격·투구 기록, 개인 마일스톤 타임라인, 시즌 경기별 로그. |
| 제한 및 주의사항 | 통산 기록은 기존 stats 초기값과 이후 박스스코어를 합산합니다. 포스트시즌 기록은 가져온 박스스코어 기준입니다. Career/Postseason 모드에서는 경기별 로그 더블클릭이 열리지 않습니다. |

### 기록 달성 예측

| 항목 | 내용 |
|---|---|
| 사용 목적 | 통산 마일스톤의 현재값, 목표값, 남은 수치, 이번 시즌 페이스와 임박 여부를 확인합니다. |
| 진입 화면 | 사이드바 **기록 달성 예측**. |
| 필요한 입력 | `data/milestones.csv`의 `track_from` 기준, 추적 팀 선수, 기존 기록 또는 박스스코어 기록. |
| 주요 조작 | 선수 필터, 등급 필터, **Near Only**, **Regenerate List**, 표 더블클릭으로 선수 기록 이동. |
| 확인 가능한 결과 | 선수, 한글명, 마일스톤, 등급, 진행률, 임박 상태, 이번 시즌 근거. |
| 제한 및 주의사항 | 현재 화면은 통산 예측 중심입니다. 기준 범위에 들어온 선수만 표시되므로 기록이 없거나 추적 팀 밖인 선수는 보이지 않을 수 있습니다. |

### 기존 기록 가져오기

| 항목 | 내용 |
|---|---|
| 사용 목적 | OOTP stats export로 프로그램 도입 이전의 시즌·통산 베이스라인을 DB에 저장하거나 비교합니다. |
| 진입 화면 | 사이드바 **기존 기록 가져오기**. 대시보드의 **Import Existing Records** 버튼으로도 이동할 수 있습니다. |
| 필요한 입력 | `player_batting_stats.txt`, `player_pitching_stats.txt`, 현재 시즌 설정. 파일은 비어 있지 않고 읽을 수 있어야 합니다. |
| 주요 조작 | 파일별 **Browse**, **Batting**, **Pitching**, **Load Database**, import 모드 선택. |
| 확인 가능한 결과 | 타자·투수 import 선수 수, 반영 범위 시즌, 갱신일, 비교 결과 대화상자, 완료 메시지. |
| 제한 및 주의사항 | **Initial setup**은 현재 시즌보다 이전 시즌을 베이스라인으로 저장합니다. **Off-season update**는 전 시즌 차이를 비교한 뒤 저장 확인을 받습니다. **Mid-season compare**는 현재 시즌 차이를 보여주며 저장하지 않습니다. import 중에는 설정 변경과 앱 종료가 제한됩니다. |

### 레이팅 편집

| 항목 | 내용 |
|---|---|
| 사용 목적 | OOTP 로스터 export를 열어 선수 레이팅을 확인하고 단일 또는 일괄 수정 파일을 만듭니다. |
| 진입 화면 | 사이드바 **레이팅 편집**. |
| 필요한 입력 | 활성 세이브의 `import_export` 폴더 안에 있는 `mlb_rosters` 또는 `kbo_rosters` 계열 파일. `.csv`/`.txt` 확장자 또는 같은 이름의 폴더 안 첫 CSV/TXT 파일도 찾습니다. |
| 주요 조작 | 리그 선택, **Load**, 포지션·최소 나이·최대 나이 필터, 검색, 행 더블클릭 단일 선수 편집, **Bulk Edit...**, **Save Backup**, **Save**. |
| 확인 가능한 결과 | 이름, 한글명, 팀, 리그, 포지션, 나이, CON/POW/STU 요약, 백업 파일, 수정 로스터 파일. |
| 제한 및 주의사항 | 화면 표시는 최대 5,000명까지입니다. 저장 전 백업을 만들도록 유도합니다. 로스터 편집 결과는 마일스톤 DB나 통계 import에 자동 반영되지 않습니다. |

### 설정

| 항목 | 내용 |
|---|---|
| 사용 목적 | OOTP 세이브 연결, 추적 팀, 언어, 기준 파일, DB 상태와 고급 복구 도구를 관리합니다. |
| 진입 화면 | 사이드바 **설정** 또는 하단 상태바 클릭. 최초 실행 시에는 설정 창이 먼저 열립니다. |
| 필요한 입력 | `saved_games` 루트, 리그, 현재 시즌, 시즌 경기 수, 추적 팀. 선택 입력으로 Gemini API Key, 선호 모델, 커스텀 팀, 한글 이름 매핑이 있습니다. |
| 주요 조작 | 자동 탐색 또는 수동 경로 검증, 리그 새로고침, 추적 팀 추가·제거, **Open Pending Mappings**, **Edit Milestone Definitions**, **Run Merge Update**, **Refresh Status**, **Re-import Individual Boxscores**, **Remove Spring Training Games**, **Recover Regular Season Games**, **Full DB Reset**, **Save All Settings & Refresh Data**. |
| 확인 가능한 결과 | 선택된 리그 경로, 파생된 DB 경로, 저장된 경기·선수·마일스톤 요약, reference 파일 업데이트 배지, 언어 변경 안내. |
| 제한 및 주의사항 | 언어 변경은 앱 재시작 후 적용됩니다. **Full DB Reset**은 현재 세이브의 기록 DB를 삭제하므로 기존 기록과 박스스코어를 다시 가져와야 합니다. 개발자 도구는 잘못 사용하면 현재 세이브 데이터가 크게 바뀔 수 있습니다. |

## 마일스톤 기준과 데이터 저장

마일스톤 기준은 `data/milestones.csv`에 정의되어 있으며, 앱에서는 사용자 데이터 폴더의 `milestones.csv`를 사용합니다. 주요 scope는 `game`, `season`, `career`, `season_ratio`, `team_game`, `team_season`, `streak`입니다.

소스 실행 시 사용자 데이터는 저장소의 `data/` 아래에 저장됩니다. 배포본 실행 시 사용자 데이터는 `%APPDATA%\OOTP_Milestone_Tracker\` 아래에 저장됩니다. 세이브별 DB는 다음 상대 경로 형식을 사용합니다.

```text
saves/{리그폴더명_slug}_{해시}/records.db
```

주요 파일은 다음과 같습니다.

| 파일 | 설명 |
|---|---|
| `data/settings.json.example` | 기본 설정 템플릿. 소스 실행 시 `data/settings.json`으로 복사해 사용할 수 있습니다. |
| `data/milestones.csv` | 번들 마일스톤 기준 파일. |
| `data/streak_policies.json` | 연속 기록 판정 정책. |
| `data/korean_first_names.csv`, `data/korean_last_names.csv` | 한글 이름 매핑 기준. |
| `data/korean_names_pending.csv.example` | 미확정 이름 매핑 대기 파일 템플릿. |
| `saves/{리그폴더명_slug}_{해시}/records.db` | 선택한 OOTP 세이브의 SQLite 기록 DB. |

## 문제가 생기면 먼저 확인할 것

### 앱이 바로 사용할 준비가 안 됨

- **대시보드**의 **Getting Started** 체크리스트에서 리그, 추적 팀, 기존 기록 import, 박스스코어 import 중 무엇이 남았는지 확인합니다.
- **설정**의 활성 리그 경로가 실제 `.lg` 폴더를 가리키는지 확인합니다.
- 현재 시즌과 시즌 경기 수가 OOTP 세이브의 진행 상황과 맞는지 확인합니다.

### 선수가 목록에 나타나지 않음

- **설정**에서 추적 팀이 비어 있지 않은지 확인합니다.
- 커스텀 MLB 팀은 stats export에 팀 약칭과 팀명이 있어야 자동 인식됩니다.
- stats 파일을 아직 가져오지 않았다면 **기존 기록 가져오기**를 먼저 실행합니다.
- 박스스코어만 가져온 선수는 가져온 경기 범위 안의 정보만 표시될 수 있습니다.

### 박스스코어를 가져와도 기록이 없음

- **설정**에서 박스스코어 폴더가 `news\html\box_scores`를 가리키는지 확인합니다.
- **MLB Only**가 켜져 있어 비 MLB 경기, 스프링 트레이닝, 다른 대회가 제외되지 않았는지 확인합니다.
- 파일명이 `game_box_*.html` 형식인지 확인합니다.
- import 중 파일이 수정된 경우 해당 파일은 다음 import로 미뤄질 수 있습니다.

### 기존 기록 가져오기가 실패하거나 완료되지 않음

- `player_batting_stats.txt`와 `player_pitching_stats.txt`가 비어 있지 않은지 확인합니다.
- 두 파일이 현재 선택한 리그의 `import_export`에서 export된 것인지 확인합니다.
- import 중 앱 종료나 설정 변경을 시도하지 말고 완료 메시지를 기다립니다.
- 알 수 없는 MLB 팀이 발견되면 앱의 안내에 따라 커스텀 팀 매핑을 저장합니다.

### 수정한 박스스코어를 다시 반영하고 싶음

- 일반 **Import Boxscores**는 변경된 기존 경기 파일을 바로 교체하지 않고 안전한 단일 경기 re-import 흐름을 요구할 수 있습니다.
- **설정**의 **Re-import Individual Boxscores**는 선택한 파일을 다시 가져오는 개발자 도구입니다.
- 현재 구현은 최신 경기 교체를 우선하며, 과거 경기나 같은 날짜 복수 경기처럼 누적 재계산이 애매한 경우 거부될 수 있습니다.

### 시즌 종료 비율 기록이 이상함

- **달성 기록**에서 시즌 필터를 해당 시즌으로 설정한 뒤 **Determine Final Season Records**를 실행합니다.
- 실행 전 OOTP에서 최종 `player_batting_stats.txt`와 `player_pitching_stats.txt`를 다시 export해야 합니다.
- export 값이 DB의 박스스코어 누적보다 작으면 앱은 오래된 export로 판단하고 경고합니다.

### 빌드가 실패함

- 가상환경이 활성화되어 있고 `pip install -r requirements.txt`를 완료했는지 확인합니다.
- `python build.py`는 `assets/icon.ico`, `assets/icon.png`, `version.txt`, `data/`의 번들 파일을 확인합니다.
- 빌드 결과는 `dist/` 아래에 생성됩니다.

## 상세 문서

- [`docs/file_formats.md`](docs/file_formats.md) - OOTP export와 HTML 파일 형식
- [`docs/roster_format.md`](docs/roster_format.md) - 로스터 export 형식과 레이팅 편집 전제
- [`docs/milestone_rules.md`](docs/milestone_rules.md) - 마일스톤 범위와 판정 규칙
- [`docs/milestone_implementation.md`](docs/milestone_implementation.md) - 자동·수동 마일스톤 구현 메모
- [`docs/message_automation_field_rules.md`](docs/message_automation_field_rules.md) - 수상·이적·부상 메시지 규칙
- [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md) - README 스크린샷 촬영 계획
- [`docs/readme_codex_audit.md`](docs/readme_codex_audit.md) - README 검증 감사 기록
- [`docs/releases/`](docs/releases/) - 버전별 릴리즈 노트
- [`CHANGELOG.md`](CHANGELOG.md) - 전체 변경 이력
