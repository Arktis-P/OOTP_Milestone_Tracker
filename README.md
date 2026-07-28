# OOTP Milestone Tracker

Out of the Park Baseball(OOTP)의 박스스코어와 선수 통계 파일을 가져와 **경기·시즌·통산 기록, 연속 기록, 수상·이적·부상 이벤트를 한곳에서 추적하는 Windows 데스크톱 애플리케이션**입니다.

**현재 버전:** 0.1.9  
**환경:** Python 3.11+ · PyQt6 · SQLite · Windows

## 핵심 기능

- **마일스톤 자동 감지** — 박스스코어 HTML을 가져오면 경기·시즌·통산·팀 단위 기록을 판정합니다.
- **연속 기록 추적** — 진행 중인 기록과 최근 종료 기록을 선수·팀·시즌·유형별로 확인합니다.
- **기록 달성 예측** — 시즌 페이스와 최근 경기 추세를 바탕으로 다음 마일스톤까지의 진행 상황을 보여줍니다.
- **수동 이벤트 기록** — 마일스톤, 수상, 이적, 부상 기록을 통합 입력창에서 추가합니다.
- **선수 기록 조회** — 추적 팀 선수의 시즌·통산 기록과 경기별 상세 기록을 확인합니다.
- **기존 기록 가져오기** — OOTP의 타격·투구 통계 파일을 초기값 또는 시즌 갱신 자료로 사용합니다.
- **레이팅 편집** — MLB·KBO 로스터를 불러와 변경 전후를 비교하고 백업 후 수정 파일을 저장합니다.
- **세이브별 데이터 분리** — 리그마다 별도의 SQLite DB를 사용하여 기록이 섞이지 않습니다.
- **한글 이름 매핑** — 선수 이름을 CSV와 앱 내 설정을 통해 한글로 표시할 수 있습니다.

## 화면 구성

> 실제 화면 이미지는 준비 중입니다. 권장 캡처 위치와 파일명은 [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md)에 정리되어 있습니다.

| 화면 | 주요 용도 |
|---|---|
| 대시보드 | 최근 마일스톤, 임박 예측, 진행 중 연속 기록, DB 상태 확인 |
| 달성 기록 | 자동·수동 이벤트 조회, 필터링, 시즌 최종 기록 판정 |
| 선수 기록 | 선수별 시즌·통산 기록 조회 및 박스스코어 가져오기 |
| 기록 달성 예측 | 현재값, 목표값, 예상 추가치와 계산 근거 확인 |
| 연속 기록 센터 | 진행 중 기록과 최근 종료 기록 조회 |
| 기존 기록 가져오기 | 선수 통계 파일을 초기값·갱신 자료로 반영 |
| 레이팅 편집 | 로스터 레이팅 변경 전후 비교 및 저장 |
| 설정 | OOTP 경로, 시즌, 추적 팀, 마일스톤 기준, DB 관리 |

## 설치 및 실행

### 1. 저장소 내려받기

```bash
git clone https://github.com/Arktis-P/OOTP_Milestone_Tracker.git
cd OOTP_Milestone_Tracker
```

### 2. Python 가상환경과 패키지 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 설정 파일 생성

```bash
copy data\settings.json.example data\settings.json
```

이후 `data/settings.json`에 OOTP 세이브의 `import_export` 경로와 현재 시즌을 입력합니다. 앱을 실행한 뒤 **설정** 화면에서도 경로와 추적 팀을 변경할 수 있습니다.

### 4. 실행

```bash
python main.py
```

배포용 exe는 사용자 데이터를 `%APPDATA%\OOTP_Milestone_Tracker\`에 저장합니다. 프로그램을 업데이트해도 DB·설정·한글 이름 CSV는 유지됩니다.

## 처음 사용하는 순서

1. **OOTP에서 데이터 내보내기**
   - `player_batting_stats.txt`
   - `player_pitching_stats.txt`
   - 경기 진행 후 `news/html/box_scores/*.html`
2. 앱의 **설정**에서 `import_export` 경로, 현재 시즌, 추적 팀을 지정합니다.
3. **기존 기록 가져오기**에서 선수 통계 파일을 불러옵니다.
4. **선수 기록** 또는 **달성 기록**에서 박스스코어 HTML을 가져옵니다.
5. **대시보드**, **달성 기록**, **기록 달성 예측**, **연속 기록 센터**에서 결과를 확인합니다.
6. 시즌 중에는 새 박스스코어를 반복해서 가져오고, 시즌 종료 후 통계 파일을 갱신합니다.

> **신생팀·확장팀:** 통계 export에 해당 팀의 기록이 아직 없으면 선수 목록에 나타나지 않을 수 있습니다. 이 경우 수동 입력으로 선수를 먼저 등록하면 이후 stats·박스스코어 import 시 자동으로 연결됩니다.

## 가져오는 데이터

| 소스 | 용도 |
|---|---|
| `news/html/box_scores/*.html` | 경기별 기록, 실시간 마일스톤, 현재 시즌 누적 기록 |
| `player_batting_stats.txt` | 타자 통산·과거 시즌 초기값과 갱신 |
| `player_pitching_stats.txt` | 투수 통산·과거 시즌 초기값과 갱신 |
| `mlb_rosters` / `kbo_rosters` | 레이팅 편집 전용 데이터 |

**기존 기록 가져오기**는 다음 모드를 지원합니다.

- `first_time` — 최초 초기값 설정
- `refresh` — 시즌·통산 기록 갱신
- `mid_season` — 시즌 중간 기준값 반영

세이브마다 별도의 DB를 사용하며, MLB 전용 import 옵션으로 WBC·KBO 등 다른 리그 데이터를 제외할 수 있습니다.

## 마일스톤 관리

마일스톤 기준은 `data/milestones.csv`에서 관리합니다. Excel 또는 앱의 설정 화면에서 편집할 수 있습니다.

주요 추적 범위:

- 단일 경기 기록
- 시즌 누적 기록
- 통산 기록
- 팀 기록
- 연속 경기·연속 이닝 기록
- 시즌 종료 후 확정되는 비율 기록

예측 기능은 `track_from` 값에 따라 목표까지 남은 수치가 일정 범위에 들어온 기록부터 추적하며, `near_n` 기준에 해당하는 임박 항목을 강조합니다.

## 수정된 박스스코어 다시 가져오기

가장 최근 경기의 박스스코어를 다시 가져오면 기존 경기 기록, 마일스톤, 연속 기록을 하나의 트랜잭션으로 교체합니다.

과거 경기이거나 같은 날짜에 복수 경기가 존재하는 경우에는 누적 기록 재생 과정의 안전을 위해 수정된 파일 가져오기가 제한될 수 있습니다.

## 기술 스택

- Python 3.11+
- PyQt6
- SQLite (세이브별 DB, WAL 모드)
- Beautiful Soup
- CSV / JSON
- PyInstaller
- pytest

## 프로젝트 구조

```text
OOTP_Milestone_Tracker/
├─ main.py                 # 애플리케이션 진입점
├─ core/                   # 파싱, 집계, 마일스톤, DB, 설정
├─ gui/                    # PyQt6 화면과 위젯
├─ data/                   # 마일스톤 기준, 설정 예시, 이름 매핑
├─ docs/                   # 규칙, 포맷, 릴리즈 및 개발 문서
├─ tests/                  # 자동화 테스트
└─ build.py                # Windows 배포본 빌드
```

## 테스트

```bash
pytest
```

## Windows 배포본 빌드

```bash
python build.py
```

산출물:

```text
dist/ootp_milestone_tracker/ootp_milestone_tracker.exe
dist/ootp_milestone_tracker_vX.X.X.zip
```

## 주요 설정·데이터 파일

| 파일 | 설명 |
|---|---|
| `data/milestones.csv` | 마일스톤 기준 |
| `data/settings.json` | 로컬 앱 설정, Git 제외 |
| `saves/{리그}_{해시}/records.db` | 세이브별 SQLite DB |
| `korean_*_names.csv` | 한글 이름 매핑 |
| `CHANGELOG.md` | 버전별 변경 이력 |

## 상세 문서

- [`docs/releases/`](docs/releases/) — 버전별 사용자 릴리즈 노트
- [`docs/milestone_rules.md`](docs/milestone_rules.md) — 마일스톤 범위와 판정 규칙
- [`docs/milestone_implementation.md`](docs/milestone_implementation.md) — 자동·수동 판정 구현
- [`docs/message_automation_field_rules.md`](docs/message_automation_field_rules.md) — 수상·이적·부상 메시지 필드 규칙
- [`docs/roster_format.md`](docs/roster_format.md) — OOTP 로스터 export 포맷
- [`docs/dev_notes.md`](docs/dev_notes.md) — 상세 개발 노트
- [`docs/public_release_followups.md`](docs/public_release_followups.md) — 공개 품질 후속 작업
- [`docs/readme_screenshot_plan.md`](docs/readme_screenshot_plan.md) — README용 화면 캡처 계획
- [`CHANGELOG.md`](CHANGELOG.md) — 전체 변경 이력

## 참고 사항

- OOTP 출력 샘플은 로컬 `samples/` 폴더에서 관리하며 Git에는 포함하지 않습니다.
- 커스텀 팀은 stats export에 해당 팀 행이 있어야 자동 필터링됩니다.
- 로스터 파일은 레이팅 편집에만 사용하며 마일스톤 통계에는 반영되지 않습니다.
