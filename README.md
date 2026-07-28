# OOTP Milestone Tracker

Out of the Park Baseball(OOTP)의 박스스코어와 선수 통계 파일을 가져와 **경기·시즌·통산 마일스톤, 연속 기록, 선수 기록과 달성 예측을 추적하는 Windows 데스크톱 애플리케이션**입니다.

**현재 버전:** 0.1.9  
**환경:** Windows · Python 3.11+ · PyQt6 · SQLite

> 화면 이미지는 준비 중입니다. 촬영할 화면과 README 삽입 위치는 [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md)에 정리되어 있습니다.

## 이 프로그램으로 할 수 있는 일

- OOTP 박스스코어 HTML을 가져와 경기·시즌·통산·팀 마일스톤을 자동으로 기록합니다.
- 선수와 팀의 진행 중 연속 기록 및 최근 종료 기록을 확인합니다.
- 현재 기록, 목표 기록, 시즌 페이스를 바탕으로 다음 마일스톤 달성 가능성을 확인합니다.
- 마일스톤, 수상, 이적, 부상 이벤트를 수동으로 추가합니다.
- 추적 팀 선수의 시즌·통산 기록과 경기별 기록을 조회합니다.
- OOTP의 기존 타격·투구 통계를 초기값으로 가져옵니다.
- MLB·KBO 로스터 레이팅을 편집하고 변경 전후를 비교합니다.
- 세이브마다 별도 SQLite DB를 사용해 서로 다른 리그의 기록을 분리합니다.
- 선수 이름을 한글 이름 CSV와 앱 설정을 통해 매핑합니다.

## 주요 화면과 기능

현재 앱의 사이드바는 다음 7개 화면으로 구성됩니다.

| 화면 | 기능 | 주요 사용 시점 |
|---|---|---|
| **대시보드** | 최근 마일스톤, 임박 예측, 진행 중 연속 기록, 데이터 상태 확인 | 앱 실행 직후 전체 상태를 확인할 때 |
| **달성 기록** | 자동·수동 이벤트 조회, 유형·중요도 필터, 수동 기록 입력 | 달성한 기록과 수상·이적·부상을 확인할 때 |
| **선수 기록** | 선수별 시즌·통산 기록, 최근 이벤트, 다음 마일스톤, 경기별 상세 조회 | 특정 선수의 기록을 자세히 볼 때 |
| **기록 달성 예측** | 현재값, 목표값, 예상 추가치와 계산 근거 확인 | 가까운 마일스톤을 확인할 때 |
| **기존 기록 가져오기** | 타격·투구 stats 파일을 초기값 또는 갱신 자료로 반영 | 처음 설정하거나 시즌 기록을 갱신할 때 |
| **레이팅 편집** | MLB·KBO 로스터 레이팅 변경 전후 미리보기 및 저장 | 로스터 레이팅을 편집할 때 |
| **설정** | OOTP 경로, 시즌, 추적 팀, 마일스톤 기준, 이름 매핑, DB 관리 | 최초 설정 또는 세이브 변경 시 |

연속 기록은 별도의 사이드바 화면이 아니라 **대시보드, 달성 기록, 선수 기록 내부**에서 확인합니다.

## 설치 및 실행

### 방법 A. 소스 코드로 실행

```bash
git clone https://github.com/Arktis-P/OOTP_Milestone_Tracker.git
cd OOTP_Milestone_Tracker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy data\settings.json.example data\settings.json
python main.py
```

최초 실행 후에는 앱의 **설정** 화면에서 OOTP 세이브와 데이터 경로를 지정할 수 있습니다.

### 방법 B. Windows 배포본 사용

배포용 exe가 제공되는 경우 압축을 풀고 `ootp_milestone_tracker.exe`를 실행합니다.

배포본의 사용자 데이터는 다음 위치에 저장됩니다.

```text
%APPDATA%\OOTP_Milestone_Tracker\
```

프로그램을 업데이트해도 DB, 설정, 한글 이름 CSV는 이 폴더에 유지됩니다.

## OOTP에서 준비할 데이터

| 데이터 | 파일·경로 | 용도 |
|---|---|---|
| 타자 통계 | `player_batting_stats.txt` | 과거 시즌·통산 기록 초기값 및 갱신 |
| 투수 통계 | `player_pitching_stats.txt` | 과거 시즌·통산 기록 초기값 및 갱신 |
| 경기 기록 | `news/html/box_scores/*.html` | 경기별 기록, 현재 시즌 누적, 마일스톤·연속 기록 판정 |
| 로스터 | `mlb_rosters` / `kbo_rosters` | 레이팅 편집 전용 |

로스터 파일은 **레이팅 편집에만 사용**하며 마일스톤 통계에는 반영되지 않습니다.

## 처음 사용하는 순서

### 1. OOTP 세이브와 경로 설정

앱의 **설정** 화면에서 다음 항목을 지정합니다.

- OOTP 버전과 현재 시즌
- OOTP 세이브 루트 또는 활성 세이브
- `import_export` 폴더
- 박스스코어 폴더
- 추적할 팀
- 필요 시 커스텀 MLB 팀 약칭과 팀명

설정을 저장하면 현재 세이브에 맞는 DB와 경로가 적용됩니다.

### 2. 기존 기록 가져오기

**기존 기록 가져오기** 화면에서 `player_batting_stats.txt`와 `player_pitching_stats.txt`가 있는 폴더를 선택합니다.

| 모드 | 용도 |
|---|---|
| `first_time` | 처음 사용할 때 과거 시즌·통산 기록을 초기값으로 저장 |
| `refresh` | 시즌 또는 통산 기록을 다시 갱신 |
| `mid_season` | 시즌 도중 현재 누적 기록을 기준값으로 반영 |

가져오기 작업은 백그라운드에서 실행됩니다. 작업 중에는 DB 연결 보호를 위해 설정 변경이나 앱 종료가 제한될 수 있습니다.

### 3. 박스스코어 가져오기

**대시보드**, **달성 기록** 또는 **선수 기록** 화면에서 박스스코어 import 기능을 사용합니다.

박스스코어를 가져오면 다음 내용이 반영됩니다.

- 경기별 선수 기록
- 현재 시즌 누적 기록
- 자동 감지된 마일스톤
- 진행 중이거나 종료된 연속 기록
- 선수 상세 화면의 경기별 기록

수정된 최신 박스스코어는 다시 가져오기를 통해 원본 경기 기록과 관련 마일스톤·연속 기록을 교체할 수 있습니다.

> 과거 경기 또는 같은 날짜에 복수 경기가 있는 경우에는 누적 기록의 안전한 재계산을 위해 재가져오기가 제한될 수 있습니다.

### 4. 결과 확인

- **대시보드**에서 최근 기록과 전체 상태를 확인합니다.
- **달성 기록**에서 자동·수동 이벤트를 필터링해 확인합니다.
- **선수 기록**에서 특정 선수의 시즌·통산·경기별 기록을 확인합니다.
- **기록 달성 예측**에서 다음 목표까지 남은 수치와 계산 근거를 확인합니다.

### 5. 필요한 이벤트 수동 입력

자동으로 가져올 수 없는 이벤트는 **달성 기록** 화면에서 추가합니다.

- 마일스톤
- 수상
- FA·트레이드 등 이적
- 부상

DB에 없는 선수도 풀 네임으로 먼저 등록할 수 있으며, 이후 stats 또는 박스스코어에서 같은 선수가 확인되면 자동 병합됩니다.

## 시즌 중 반복 사용

```text
새 경기 진행
→ 박스스코어 가져오기
→ 대시보드 확인
→ 달성 기록과 예측 확인
```

필요할 때 stats 파일을 다시 export하고 **기존 기록 가져오기**의 `refresh` 모드로 갱신합니다. 시즌 종료 후에는 최종 자격 조건을 반영해 타율·출루율·ERA 등의 비율 마일스톤을 판정할 수 있습니다.

## 기능별 사용법

### 마일스톤 자동 감지

`data/milestones.csv`의 기준에 따라 다음 범위를 판정합니다.

- 단일 경기 기록
- 시즌 누적 기록
- 통산 기록
- 팀 기록
- 연속 경기·연속 이닝 기록
- 시즌 종료 후 확정되는 비율 기록

기준은 CSV를 직접 편집하거나 앱의 **설정** 화면에서 변경할 수 있습니다.

### 기록 달성 예측

예측 화면에서는 현재 기록, 목표 기록, 목표까지 남은 수치, 시즌 전체 페이스, 최근 경기 페이스와 계산 근거를 확인합니다.

`track_from`은 목표까지 남은 수치가 어느 범위에 들어오면 추적을 시작할지 정하며, `near_n`은 임박 항목 강조 기준입니다.

### 선수 기록

추적 팀의 선수를 선택해 다음 내용을 확인합니다.

- 시즌·통산 기록 전환
- 경기별 드릴다운
- 최근 달성 이벤트
- 진행 중 연속 기록
- 다음 마일스톤

박스스코어가 없어도 stats 파일의 초기값을 이용해 과거 시즌과 통산 기록을 표시할 수 있습니다.

### 레이팅 편집

MLB 또는 KBO 로스터를 불러와 레이팅을 수정하고 변경 전후를 미리 확인합니다. 저장 시 원본을 백업하고 `mod_*_rosters.txt` 형식의 수정 파일을 생성합니다.

## 데이터 저장과 세이브 분리

각 OOTP 세이브는 별도의 SQLite DB를 사용합니다.

```text
saves/{리그}_{해시}/records.db
```

주요 파일:

| 파일 | 설명 |
|---|---|
| `data/milestones.csv` | 마일스톤 기준 |
| `data/settings.json` | 소스 실행용 로컬 설정 |
| `saves/{리그}_{해시}/records.db` | 세이브별 기록 DB |
| `korean_*_names.csv` | 한글 이름 매핑 |
| `CHANGELOG.md` | 버전별 변경 이력 |

## 자주 발생하는 문제

### 선수가 목록에 나타나지 않음

- 추적 팀이 올바르게 설정됐는지 확인합니다.
- 커스텀 팀은 stats export에 해당 팀 행이 있어야 자동으로 필터링됩니다.
- 신생팀은 기록이 쌓이기 전까지 수동 선수 등록을 사용할 수 있습니다.

### 박스스코어를 가져와도 기록이 없음

- 박스스코어 경로가 현재 세이브를 가리키는지 확인합니다.
- 현재 시즌 설정이 박스스코어의 시즌과 일치하는지 확인합니다.
- MLB 전용 import 옵션으로 다른 리그 데이터가 제외되지 않았는지 확인합니다.

### 기존 기록 가져오기가 완료되지 않음

- 두 stats 파일이 같은 `import_export` 폴더에 있는지 확인합니다.
- 작업 중 설정 변경이나 앱 종료를 시도하지 않습니다.
- 다른 세이브의 파일을 선택하지 않았는지 확인합니다.

### 수정된 과거 경기를 다시 가져올 수 없음

현재는 최신 경기의 안전한 교체를 우선 지원합니다. 과거 경기나 같은 날짜의 복수 경기는 누적 기록 재생 기능의 제한으로 거부될 수 있습니다.

## 개발자용 실행

```bash
pytest
python build.py
```

빌드 산출물:

```text
dist/ootp_milestone_tracker/ootp_milestone_tracker.exe
dist/ootp_milestone_tracker_vX.X.X.zip
```

## 기술 스택

- Python 3.11+
- PyQt6
- SQLite (WAL 모드)
- Beautiful Soup
- Google Gen AI SDK
- CSV / JSON
- PyInstaller
- pytest

## 프로젝트 구조

```text
OOTP_Milestone_Tracker/
├─ main.py                 # 애플리케이션 진입점
├─ core/                   # 파싱, 집계, 마일스톤, DB, 설정
├─ gui/                    # PyQt6 화면과 위젯
├─ data/                   # 마일스톤 기준과 설정 예시
├─ docs/                   # 사용자·개발 문서
├─ tests/                  # 자동화 테스트
└─ build.py                # Windows 배포본 빌드
```

## 상세 문서

- [`docs/releases/`](docs/releases/) — 버전별 사용자 릴리즈 노트
- [`docs/milestone_rules.md`](docs/milestone_rules.md) — 마일스톤 범위와 판정 규칙
- [`docs/milestone_implementation.md`](docs/milestone_implementation.md) — 자동·수동 판정 구현
- [`docs/message_automation_field_rules.md`](docs/message_automation_field_rules.md) — 수상·이적·부상 메시지 규칙
- [`docs/roster_format.md`](docs/roster_format.md) — OOTP 로스터 export 포맷
- [`docs/dev_notes.md`](docs/dev_notes.md) — 개발 및 구현 노트
- [`docs/public_release_followups.md`](docs/public_release_followups.md) — 공개 품질 후속 작업
- [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md) — README 화면 캡처 계획
- [`docs/readme_codex_audit.md`](docs/readme_codex_audit.md) — README 저장소 검증 결과
- [`CHANGELOG.md`](CHANGELOG.md) — 전체 변경 이력
