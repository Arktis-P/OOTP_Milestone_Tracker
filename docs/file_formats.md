# OOTP 입력 파일 포맷 명세

> Phase 1에서 실제 OOTP 샘플 파일을 분석하며 이 문서를 채웁니다.

## 박스스코어 HTML (`.html`)

**경로 예시:** `{save}/news/html/box_scores/*.html`

| 필드 | 설명 | 파서 상태 |
|------|------|-----------|
| game_date | 경기 날짜 | 미구현 |
| home_team | 홈팀 | 미구현 |
| away_team | 원정팀 | 미구현 |
| batting stats | 타자별 AB, H, HR 등 | 미구현 |
| pitching stats | 투수별 IP, ER, SO 등 | 미구현 |

**파서:** `core/parser/boxscore_html.py`

---

## 박스스코어 TXT (`.txt`)

**경로 예시:** `{save}/news/text/box_scores/*.txt`

| 필드 | 설명 | 파서 상태 |
|------|------|-----------|
| (TBD) | 실제 샘플 분석 후 작성 | 미구현 |

**파서:** `core/parser/boxscore_txt.py`

---

## 로스터 / 통산 기록 CSV (`.txt`, `.csv`)

**경로 예시:** `{save}/players.csv` 또는 OOTP 내보내기 파일

| 필드 | 설명 | 파서 상태 |
|------|------|-----------|
| Name / name | 선수 이름 | 기본 지원 |
| Team / team | 소속 팀 | 기본 지원 |
| Position / Pos | 포지션 | 기본 지원 |
| Bats / Throws | 타격/투구 손 | 기본 지원 |

**파서:** `core/parser/roster_csv.py`

---

## 샘플 파일 추가 방법

1. `samples/` 디렉토리에 실제 OOTP 출력 파일을 추가 (Git 제외 권장)
2. 파서 구현 후 이 문서에 필드 매핑 기록
3. `docs/dev_notes.md`에 OOTP 버전별 차이점 기록
