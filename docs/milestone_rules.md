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
| `scope` | string | `game` / `season` / `career` / `season_ratio` |
| `direction` | string | `higher`(기본) 또는 `lower` (ERA, WHIP 등) |
| `grade` | string | `common` / `uncommon` / `rare` / `epic` / `legendary` (GUI 표시 서식용) |

## CSV 형식

```csv
category,key,label,scope,stat,threshold,direction,grade
batting,career_hr_500,통산 500홈런,career,career_hr,500,higher,legendary
pitching,season_era_200,시즌 2점대 ERA,season_ratio,season_era,2.99,lower,legendary
```

## scope별 판정

| scope | 시점 | 데이터 소스 | 중복 방지 |
|-------|------|-------------|-----------|
| `game` | 박스스코어 import 직후 | 해당 경기 `batting_logs` / `pitching_logs` | `(player_id, milestone_key, game_id)` |
| `season` | import 직후 | 시즌 누계 (박스스코어만, 초기값 제외) | `(player_id, milestone_key, season)` |
| `career` | import 직후 | `career_*_init` + 박스스코어 UNION | `(player_id, milestone_key)` |
| `season_ratio` | 시즌 종료 후 수동 | 시즌 누계 + 최소 자격 | `(player_id, milestone_key, season)` |

## 특수 투구 기록 (game scope)

박스스코어 import 시 `pitching_logs`에 자동 계산:

| 플래그 | 조건 |
|--------|------|
| `is_cg` | 해당 팀 투수 1명만 등판 |
| `is_sho` | 완투 + 0실점 |
| `is_no_hitter` | 완봉 + 상대팀 안타 0 |
| `is_perfect_game` | 노히터 + 상대 BB/HBP/실책 0 |

연쇄 관계: perfect → no_hitter → sho → cg

## 비율 스탯 자격 (`season_ratio`)

`settings.json`:

```json
{
  "season_games_total": 162,
  "ratio_qualifiers": {
    "batting_ab_per_game": 3.1,
    "pitching_ip_per_game": 1.0
  }
}
```

- 타격: `round(season_games_total × 3.1)` AB 이상 (162경기 → 502 AB)
- 투구: `season_games_total` IP 이상 (162경기 → 162 IP)

GUI **시즌 종료 체크** 버튼으로만 판정합니다.

## 초기값 (career scope)

프로그램 도입 이전 기록은 `player_batting_stats.txt` / `player_pitching_stats.txt`를
`career_batting_init` / `career_pitching_init`에 저장합니다.
통산 집계 시 박스스코어 로그와 UNION 합산합니다.

## direction

- `higher` (기본): `current >= threshold`
- `lower`: `current <= threshold` (예: ERA 2.99 이하)

## 사용자 정의 마일스톤 추가

`milestones.csv`에 행을 추가한 뒤 앱을 재시작합니다.

```csv
batting,season_hr_40,시즌 40홈런,season,season_hr,40,higher,rare
```
