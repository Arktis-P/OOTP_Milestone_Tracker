# OOTP Milestone Tracker

Out of the Park Baseball(OOTP) 시뮬레이션 게임의 선수/팀 기록을 추적하고,
마일스톤 달성 여부 확인 및 예측 기능을 제공하는 데스크톱 애플리케이션입니다.

## 기능

- 선수/팀 경기·시즌·통산 기록의 마일스톤 달성 여부 확인
- 달성한 마일스톤 기록 입력 및 이력 관리
- 시즌 전/중반 시점 마일스톤 달성 사전 예측
- 선수 시즌/통산 기록 조회
- 로스터 파일의 조건별 레이팅 일괄 수정

## 기술 스택

- Python 3.11+
- PyQt6 (GUI)
- SQLite (내부 DB)
- JSON / CSV (사용자 편집 가능 설정)
- PyInstaller (배포)

## 설치 및 실행

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# settings.json 설정 (최초 1회)
copy data\settings.json.example data\settings.json
# data/settings.json 에 OOTP 파일 경로 입력

python main.py
```

## 프로젝트 구조

```
ootp_milestone_tracker/
├── main.py              # 진입점
├── core/                # 파싱, 집계, 마일스톤 로직
├── gui/                 # PyQt6 UI
├── data/                # milestones.json, settings.json, records.db
└── docs/                # 파일 포맷 명세, 개발 노트
```

## 개발 단계

| Phase | 내용 |
|-------|------|
| 1 | 파싱 검증 (박스스코어 샘플 파일) |
| 2 | DB 설계 & 집계 |
| 3 | 마일스톤 체커 |
| 4 | GUI 기본 골격 |
| 5 | GUI ↔ 로직 연결 |
| 6 | 예측 & 로스터 편집 |
| 7 | 빌드 & 배포 |

## 빌드

```bash
pip install pyinstaller
python build.py
```

빌드 결과물: `dist/ootp_milestone_tracker/` 및 `dist/ootp_milestone_tracker_vX.X.X.zip`

## 설정 파일

- `data/milestones.json` — 마일스톤 기준 정의 (Git 포함)
- `data/settings.json` — 앱 설정, OOTP 파일 경로 (Git 제외, 로컬)
- `data/records.db` — SQLite DB (자동 생성, Git 제외)

자세한 내용은 `docs/` 디렉토리를 참조하세요.
