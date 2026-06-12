# 마일스톤 v1 구현 상태

`data/milestones.csv` (v1, 266건) 기준 자동·수동 판정 정리.

## 자동 판정 (박스스코어 import 시)

### 경기(game)
- 누적 타격·도루, 투수 탈삼진·완투/완봉/노히터/퍼펙트
- **사이클링 히트** — 1B+2B+3B+HR
- **그랜드슬램** — BATTING `Home Runs` 노트의 `3 on` (만루)
- 동일 stat 다단계 → 최고 threshold만 기록

### 시즌(season) — 누적
- 안타·홈런·타점·득점·도루·볼넷, 승·탈삼진·세이브·이닝
- **홀드** — pitching linescore `H (N)` (`N` = 시즌 누적 홀드)
- 20-20 / 30-30 / 40-40 / 50-50

### 시즌(season) — 비율 (시즌 종료 시 1회)
- 타율·출루·장타·OPS, ERA
- 마일스톤 기록 탭 **「시즌 비율 마일스톤 기록」** 버튼으로 실행 (시즌 마감 후 권장)

### 통산(career)
- 타격·투수 누적 스탯 (홀드는 경기별 `hold` + 초기값 TXT)

### 팀
- 선발전원안타/타점/득점, 팀 노히터·퍼펙트, 시즌 팀 승수

## 수동 입력 전용

수상·리그 1위·플레이오프·명예의 전당 등 — **「수동 전용 입력」** 버튼 사용.

선택 시 `「{이름}」 마일스톤은 수동으로 입력해야 합니다.` 안내 표시.

대상 stat: `title_*`, `award_*`, `hall_of_fame`, `retired_number`,
`division_title`, `wildcard_series_win`, `division_series_win`,
`league_championship_series_win`, `world_series_win`

## ERA threshold 참고

| key | 라벨 | threshold (ERA ≤) |
|-----|------|---------------------|
| pit_season_era_2 | ERA 2점대 이하 | 3.00 |
| pit_season_era_1 | ERA 1점대 이하 | 2.00 |
| pit_season_era_0 | ERA 0점대 | 1.00 |

## 코드 위치

- `core/parser/boxscore_html.py` — 홀드 `H (N)` 파싱
- `core/parser/batting_notes.py` — 그랜드슬램 `3 on` 파싱
- `core/milestone/implementation.py` — 수동 전용·비율 시즌 구분
- `gui/views/milestone_view.py` — 수동 전용·시즌 비율 버튼
