# OOTP 입력 파일 포맷 명세

> 샘플 리그: `TestYukies_V0.0.2.lg` · 파서 구현 완료 (Phase 1)

## 세이브 폴더 내 경로

| 종류 | 세이브 내 경로 | 로컬 샘플 |
|------|----------------|-----------|
| 박스스코어 HTML | `{리그}/news/html/box_scores/` | `samples/boxscore_html/` |
| 게임 로그 HTML | `{리그}/news/html/game_logs/` | `samples/game_logs_html/` |

**파일명 패턴:** `game_box_{game_id}.html`, `log_{game_id}.html` (동일 game_id로 연결)

---

## 박스스코어 HTML — 파싱 결과 (`BoxscoreData`)

**파서:** `core/parser/boxscore_html.py` → `BoxscoreHTMLParser.parse()`

### GameMeta

| 필드 | 소스 | 예시 (game 13) |
|------|------|----------------|
| game_id | 파일명 / `GAME ID:` | 13 |
| date | `<title>` 또는 헤더 (ISO 변환) | 2026-03-27 |
| away_team / home_team | 라인스코어 `<td class="dl">` | New York Yankees / San Francisco Giants |
| away_record / home_record | 팀명 뒤 `(W-L)` | 0-2 / 2-0 |
| away_score / home_score | 라인스코어 R | 4 / 9 |
| away_innings / home_innings | 이닝별 득점 (홈 9회 `X`→0) | [0,0,…,1,1] / [1,3,4,1,0,0,0,0,0] |
| away_hits / home_hits, away_errors / home_errors | 라인스코어 H/E | 12/13, 2/0 |
| ballpark / attendance / game_time | GAME NOTES | Oracle Park / 35909 / 3:36 |

### BatterLine (팀별)

| 필드 | 소스 |
|------|------|
| player_name, player_id | `<a href="../players/player_{id}.html">` |
| position | 이름 뒤 텍스트 (2B, PR, RF 등) |
| is_substitute, sub_label | `a-`, `b-`, `c-` 접두 (&#160;&#160; 포함) |
| ab, r, h, rbi, bb, k, lob | `<td class="dc">` 순서 |
| avg, season_hr, season_rbi | **해당 경기까지 시즌 누적** (마지막 3컬럼) |

`Totals` 행(`tr.sortbottom`)은 제외.

### PitcherLine (팀별)

| 필드 | 소스 |
|------|------|
| player_name, player_id | `<a href>` |
| decision, decision_record | 이름 뒤 `W (1-0)`, `L (0-1)`, `S (N)` |
| ip | `2.1` → 2.333… (`parse_ip`) |
| h, r, er, bb, k, hr, bf, pi, era | `<td class="dc">` |

### 기타

| 필드 | 설명 |
|------|------|
| away/home_batting_notes | `<b>BATTING</b>` 이후 raw 텍스트 |
| game_notes | Player of the Game, Weather, Special Notes 등 |

---

## 게임 로그 HTML — 파싱 결과 (`GameLogData`)

> **용도:** DB 저장 대상 아님. 박스스코어로 마일스톤 달성이 확인된 뒤, **상대 투수·타석 상황** 등 맥락 파악용 참조.

**파서:** `core/parser/game_log_html.py` → `GameLogHTMLParser.parse()`

### InningData (이닝 블록별)

| 필드 | 소스 |
|------|------|
| inning_num, half | `TOP OF THE 2ND` / `BOTTOM OF THE 1ST` |
| batting_team, pitching_team | `팀 batting - Pitching for 팀` 헤더 |
| at_bats | `Batting:` 행 목록 |
| summary | `td.datathbg` 이닝 요약 |

### AtBatData

| 필드 | 소스 |
|------|------|
| batter_name, batter_id, batter_hand | `Batting: LHB/RHB/SHB {이름}` |
| pitcher_name, pitcher_id | 직전 `Pitching:` 행 |
| pitch_sequence | 우측 `<td>` raw 텍스트 (`<br>` → 줄바꿈) |
| result | `<b>` 태그 또는 마지막 투구 줄 → 정규화 |
| hit_type, exit_velocity, distance | 괄호 내 `Line Drive`, `EV N MPH`, `Distance : N ft` |

**결과 정규화:** SINGLE→Single, SOLO HOME RUN→Home Run, Strikes out→Strikeout 등

---

## 로스터 CSV

**파서:** `core/parser/roster_csv.py` — 기본 지원 (Phase 1 범위 외)

---

## 테스트

```bash
pytest tests/test_parsers.py -v
```

샘플: `game_box_13/14.html`, `log_13/14.html`
