# 마일스톤 기준 규칙

마일스톤 기준은 `data/milestones.csv`에서 정의합니다 (레거시 JSON도 로드 가능).
앱은 이 파일을 읽어 달성 여부를 판정합니다.

## 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | string | 고유 식별자 (DB `milestone_records.milestone_key`와 매핑) |
| `label` | string | GUI 표시용 이름 |
| `stat` | string | 비교할 통계 항목 (아래 stat 코드 참조) |
| `threshold` | number | 달성 기준값 |
| `scope` | string | `game` / `season` / `career` / `team_game` / `team_season` / `team_manual` (`season_ratio` 비활성) |
| `direction` | string | `higher`(기본) 또는 `lower` (ERA, WHIP 등) |
| `grade` | string | `common` / `uncommon` / `rare` / `epic` / `legendary` (GUI 표시 서식용) |
| `track_from` | number | (선택) 예측 감시 목록 진입 최소 통계값. 미지정 시 career `threshold * 0.8` |
| `near_n` | number | (선택) 임박 표시 기준 — 남은 수치가 이 값 이하면 "🔥 임박". 미지정 시 `threshold * 0.05` (정수 내림) |

## CSV 형식

```csv
category,key,label,scope,stat,threshold,direction,grade,track_from,near_n
batting,career_hr_500,통산 500홈런,career,career_hr,500,higher,legendary,400,20
pitching,season_era_200,시즌 2점대 ERA,season_ratio,season_era,2.99,lower,legendary
```

## scope별 판정

| scope | 시점 | 데이터 소스 | 중복 방지 |
|-------|------|-------------|-----------|
| `game` | 박스스코어 import 직후 | 해당 경기 `batting_logs` / `pitching_logs` | `(player_id, milestone_key, game_id)` |
| `season` | import 직후 | 시즌 누계 (박스스코어만, 초기값 제외) | `(player_id, milestone_key, season)` |
| `career` | import 직후 | `career_*_init` + 박스스코어 UNION | `(player_id, milestone_key)` |
| `team_game` | 박스스코어 import 직후 | 해당 경기 팀 단위 이벤트 (`tracked_teams`만) | `(team, milestone_key, game_id)` |
| `team_season` | import 직후 | 시즌 팀 승수 누계 | `(team, milestone_key, season)` |
| `team_manual` | 사용자 수동 입력 | 포스트시즌·우승 등 | `(team, milestone_key, season)` |

팀 기록은 `milestone_records.player_id = 0`, `team` 컬럼에 구단명을 저장합니다.

## 팀 마일스톤 (`team_game`)

`tracked_teams`에 등록된 구단이 경기에 출전할 때만 자동 감지합니다.

| stat | 조건 |
|------|------|
| `starter_all_hit` | 선발 타자(`is_substitute = 0`) 전원 1안타 이상 |
| `starter_all_rbi` | 선발 타자 전원 1타점 이상 |
| `all_hit` | 출장 타자 전원 1안타 이상 |
| `all_rbi` | 출장 타자 전원 1타점 이상 |
| `team_no_hitter` | 해당 경기 팀 투수 노히터 (`pitching_logs.is_no_hitter`) |
| `team_perfect_game` | 해당 경기 팀 투수 퍼펙트 (`pitching_logs.is_perfect_game`) |

## 팀 마일스톤 수동 입력 (`team_manual`)

마일스톤 기록 탭 **팀 마일스톤 수동 입력**에서 `team_manual` 항목만 선택할 수 있습니다.
와일드카드·디비전·리그·월드시리즈 우승 등 시즌당 1회 기록되며, 중복 시 거부됩니다.

## 특수 투구 기록 (game scope)

박스스코어 import 시 `pitching_logs`에 자동 계산:

| 플래그 | 조건 |
|--------|------|
| `is_cg` | 해당 팀 투수 1명만 등판 |
| `is_sho` | 완투 + 0실점 |
| `is_no_hitter` | 완봉 + 상대팀 안타 0 |
| `is_perfect_game` | 노히터 + 상대 BB/HBP/실책 0 |

연쇄 관계: perfect → no_hitter → sho → cg

## 비율 스탯 (`season_ratio`) — 비활성

타율·ERA 등 `season_ratio` 마일스톤은 커리어 종료 시점을 감지할 수 없어 현재 비활성입니다.
체커 `ACTIVE_SCOPES`에서 제외되며, 예측 탭(`PREDICTABLE_SCOPES`)에도 포함되지 않습니다.

## 초기값 (career scope)

프로그램 도입 이전 기록은 `player_batting_stats.txt` / `player_pitching_stats.txt`를
`career_batting_init` / `career_pitching_init`에 저장합니다.
통산 집계 시 박스스코어 로그와 UNION 합산합니다.

## direction

- `higher` (기본): `current >= threshold`
- `lower`: `current <= threshold` (예: ERA 2.99 이하)

## 임박 예측 (`near_n`)

통산(career) scope 예측 탭·대시보드에서 `remaining <= near_n`이면 **임박**으로 표시합니다.
페이스 계산이나 시즌 경기수 추정은 사용하지 않으며, 절대 수치 비교만 합니다.

## 사용자 정의 마일스톤 추가

`milestones.csv`에 행을 추가한 뒤 앱을 재시작합니다.

```csv
batting,season_hr_40,시즌 40홈런,season,season_hr,40,higher,rare
```
