# 마일스톤 기준 규칙

마일스톤 기준은 `data/milestones.json`에서 정의합니다.
앱은 이 파일을 읽어 달성 여부를 판정합니다.

## 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | string | 고유 식별자 (DB `milestone_records.milestone_key`와 매핑) |
| `label` | string | GUI 표시용 이름 |
| `stat` | string | 비교할 통계 항목 (아래 stat 코드 참조) |
| `threshold` | number | 달성 기준값 |
| `scope` | `"career"` \| `"season"` | 통산 또는 시즌 기준 |

## stat 코드

| stat | 의미 | scope |
|------|------|-------|
| `career_h` | 통산 안타 | career |
| `career_hr` | 통산 홈런 | career |
| `career_w` | 통산 승 | career |
| `season_avg` | 시즌 타율 (H/AB) | season |
| `season_h` | 시즌 안타 | season |
| `season_hr` | 시즌 홈런 | season |
| `season_w` | 시즌 승 | season |

## 판정 로직

1. `scope`에 따라 시즌 또는 통산 집계 쿼리 실행
2. `stat`에 해당하는 현재 값 계산
3. `current_value >= threshold` 이면 달성
4. `milestone_records` 테이블에 `(player_id, milestone_key)` 중복 없이 기록

## 예측 로직 (시즌 scope)

- `pace = current_value / games_played`
- `projected = pace × season_games_total` (기본 162경기)
- `projected >= threshold` 이면 "달성 가능" 표시

통산 scope 마일스톤은 페이스 예측 대상에서 제외됩니다.

## 사용자 정의 마일스톤 추가

`milestones.json`에 항목을 추가한 뒤 앱을 재시작하거나 마일스톤 탭에서 "달성 여부 확인"을 실행합니다.

```json
{
  "key": "season_hr_40",
  "label": "시즌 40홈런",
  "stat": "season_hr",
  "threshold": 40,
  "scope": "season"
}
```
