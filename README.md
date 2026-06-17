# OOTP Milestone Tracker

Out of the Park Baseball(OOTP) 시뮬레이션의 선수·팀 기록을 추적하고, 마일스톤 달성을 자동 감지·수동 기록·사전 예측하는 데스크톱 애플리케이션입니다.

**현재 버전:** 0.1.7

## 주요 기능

### 마일스톤 추적
- 박스스코어 HTML import 후 경기·시즌·통산·팀 단위 마일스톤 자동 감지
- **추적 팀** 필터 — 관심 구단 선수·팀 이벤트만 집중 (MLB 30팀 + **커스텀 팀** 등록 지원, 예: 확장팀 `SY`)
- **수동 입력** — 마일스톤, 수상, 이적(FA·트레이드 등), 부상을 통합 팝업에서 기록
- **수동 선수 등록** — 아직 DB에 없는 선수도 풀 네임으로 등록 후 기록 가능; 목록에는 `D. Moon` 형식으로 표시되며, 이후 박스스코어·stats import 시 **자동 병합**
- 시즌 마감 후 **시즌 비율 마일스톤**(타율·ERA 등) 일괄 판정
- **연속 기록(streak)** 마일스톤 — import 연동, scope 필터, CSV 내보내기
- 마일스톤 기준은 `milestones.csv`로 관리하며, 설정 탭에서 앱 내 편집 가능

### 마일스톤 예측
- 통산·시즌 마일스톤 달성 가능성 사전 예측
- `track_from` — 목표까지 **남은 수치** 기준으로 추적 시작 (기본: 목표의 15%)
- `near_n` 임박 항목 행 배경 강조

### 선수 기록
- 추적 팀 선수 목록, 시즌·통산 전환, 경기별 드릴다운(박스스코어 있을 때)
- **초기값(stats 파일)만으로도** 과거 시즌·통산 조회 가능 — 박스스코어 없을 때 `player_*_stats.txt` 기반 fallback
- 커스텀 팀은 stats export에 해당 팀 행이 있어야 필터에 잡힘 (`player_team_affiliations`)

### 데이터 import
| 소스 | 용도 |
|------|------|
| `news/html/box_scores/*.html` | 경기별 기록, 실시간 마일스톤, 현재 시즌 누적 |
| `player_batting_stats.txt` / `player_pitching_stats.txt` | 통산·과거 시즌 **초기값** (최초 1회 + 시즌 갱신) |
| `mlb_rosters` / `kbo_rosters` | **레이팅 편집** 전용 (통계·마일스톤과 무관) |

- **초기값 설정** 탭: first_time / refresh / mid_season 모드
- MLB 전용 import 옵션 (WBC·KBO 등 제외)
- 세이브(리그)마다 **별도 SQLite DB** — 세이브 전환 시 데이터 분리

### 기타
- **대시보드** — 최근 마일스톤, DB 요약, 빠른 이동
- **레이팅 편집** — MLB+KBO 로스터 조건별 일괄 수정, `mod_*_rosters.txt` 저장
- **한글 이름 매핑** — CSV 시드·pending 큐·설정 팝업, 마일스톤·기록·예측 탭 표시
- **설정** — OOTP 경로, 추적 팀, 마일스톤 기준, **현재 세이브 DB 초기화**

## 권장 사용 흐름

1. **설정** — OOTP 세이브의 `import_export` 경로 지정, 현재 시즌·추적 팀(커스텀 팀은 약칭·팀명 등록) 설정
2. **초기값 설정** — `player_batting_stats.txt`, `player_pitching_stats.txt` import (통산·과거 시즌 baseline)
3. **박스스코어 가져오기** — 선수 기록·마일스톤 탭에서 HTML import (진행 중 시즌 실시간 반영)
4. **마일스톤 기록 / 예측** — 자동 감지 확인, 필요 시 수동 입력
5. 시즌 중·시즌 후 — 초기값 refresh, 박스스코어 추가 import 반복

> **신생팀·확장팀 팁:** stats export에 아직 팀 기록이 없으면 통계 탭에 선수가 안 보일 수 있습니다. 그동안은 **수동 입력**으로 풀 네임 선수를 등록해 마일스톤을 기록하고, stats·박스스코어가 쌓이면 자동으로 연결됩니다.

## 기술 스택

- Python 3.11+
- PyQt6 (GUI)
- SQLite (세이브별 내부 DB, WAL 모드)
- CSV / JSON (마일스톤·설정·한글 이름)
- PyInstaller (Windows 배포)

## 설치 및 실행

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# settings.json 설정 (최초 1회)
copy data\settings.json.example data\settings.json
# data/settings.json 에 OOTP import_export 경로·현재 시즌 등 입력

python main.py
```

**배포본(exe)** 은 사용자 데이터를 `%APPDATA%\OOTP_Milestone_Tracker\`에 저장합니다. exe 업데이트 후에도 DB·설정·한글 CSV가 유지됩니다.

## 빌드

```bash
pip install pyinstaller
python build.py
```

산출물:
- `dist/ootp_milestone_tracker/ootp_milestone_tracker.exe`
- `dist/ootp_milestone_tracker_vX.X.X.zip`

## 테스트

```bash
pytest
```

## 프로젝트 구조

```
ootp_milestone_tracker/
├── main.py              # 진입점
├── core/                # 파싱, 집계, 마일스톤, DB, 설정
├── gui/                 # PyQt6 탭 UI
├── data/                # milestones.csv, settings 예시, 한글 CSV
├── docs/                # 파일 포맷, 마일스톤 규칙, 개발 노트
├── samples/             # 로컬 파서 테스트용 (Git 제외)
└── tests/
```

### GUI 탭

| 탭 | 설명 |
|----|------|
| 대시보드 | 요약·최근 마일스톤 |
| 마일스톤 기록 | 달성 이력, 수동 입력, 시즌 비율·streak |
| 선수 기록 | 추적 팀 선수 stats, 박스스코어 import |
| 마일스톤 예측 | 임박·추적 중인 마일스톤 |
| 초기값 설정 | stats 파일 import |
| 레이팅 편집 | MLB/KBO 로스터 레이팅 |
| 설정 | 경로, 팀, 마일스톤 기준, DB 초기화 |

## 설정·데이터 파일

| 파일 | 설명 |
|------|------|
| `data/milestones.csv` | 마일스톤 기준 (Git 포함, Excel 편집 가능) |
| `data/settings.json` | 앱 설정 (Git 제외) |
| `saves/{리그}_{해시}/records.db` | **세이브별** SQLite DB (자동 생성) |
| `korean_*_names.csv` | 한글 이름 매핑 |
| `CHANGELOG.md` | 버전별 변경 이력 |

## 로컬 샘플 (개발용)

OOTP 출력 샘플은 `samples/`에 두고 파서·테스트에 사용합니다 (Git 제외).

```
samples/
├── boxscore_html/
├── player_stats_txt/
└── roster/
```

## 문서

- `docs/releases/` — **릴리즈 노트** (버전별 사용자 안내)
- `docs/milestone_rules.md` — 마일스톤 scope·판정 규칙
- `docs/roster_format.md` — OOTP 로스터 export 포맷
- `docs/dev_notes.md` — 상세 개발·구현 노트
- `CHANGELOG.md` — 개발용 변경 이력
