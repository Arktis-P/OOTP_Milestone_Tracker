# D-025 연속 기록 마일스톤 정책 제안

상태: 사용자 승인 대기
작성일: 2026-07-20

## 확인된 현재 동작

- `data/streak_policies.json`은 기록별 `min_value` 하나만 정의한다.
- 엔진은 진행 중 매 경기 마일스톤을 만들지 않고, 연속 기록이 끝날 때 `min_value` 이상이면 종료 이벤트 한 건을 저장한다.
- `rebuild_season_streaks()`는 해당 시즌의 자동 연속 기록을 삭제한 뒤 다시 만든다. 따라서 기존 기록 보존 정책과 양립하지 않는다.
- 선발·구원 무실점은 현재 최소 투구 이닝 조건이 없어 0.0이닝 등판도 성공으로 판정될 수 있다.
- MLB 방식의 무실점 이닝은 실점이 발생한 이닝의 실점 전 아웃을 포함하지 않지만, 경기 합계 데이터만으로는 이를 정확히 복원할 수 없다.

## 권장 데이터 모델

각 기록에 다음 필드를 분리한다.

- `tracking_start`: 내부 상태 추적 시작값
- `display_start`: 진행 중 화면 표시 시작값
- `milestone_thresholds`: 영구 마일스톤을 만드는 값
- `record_every_n_after`: 마지막 명시 임계값 이후 기록 간격
- `emit_end_event`: 임계값을 넘긴 기록이 끝날 때 최종 길이 한 건 저장 여부
- `minimum_opportunities`: 무타수 경기, 세이브 기회 없음 등을 skip하기 위한 조건
- `season_boundary_policy`: 정규시즌 종료 시 종료 이벤트를 만들고 다음 시즌을 0에서 시작하는 정책

기본 시즌 정책은 `regular_season_close_reset`을 권장한다. 후시즌은 정규시즌 기록에서 제외한다.

## 권장 기준

| 기록 | 현재 종료 기록 최소값 | 추적 / 표시 | 권장 마일스톤 | 이후 간격 | 최소 기회 조건 |
|---|---:|---:|---|---:|---|
| 팀 경기 연속 출장 | 50 | 25 / 50 | 100, 162 | 25 | 해당 팀 공식경기 실제 출전 |
| 연속 안타 | 10 | 5 / 10 | 15, 20, 25, 30, 35, 40 | 5 | `AB >= 1`; 무타수 경기는 skip |
| 연속 홈런 | 3 | 2 / 3 | 4, 5, 6, 7, 8 | 1 | `AB >= 1`; 볼넷·사구만 있으면 skip |
| 연속 타점 | 5 | 3 / 5 | 7, 10, 15 | 5 | `PA >= 1` |
| 연속 득점 | 7 | 4 / 7 | 10, 15, 20 | 5 | 실제 출전 1회 이상 |
| 연속 도루 | 3 | 2 / 3 | 4, 5, 6, 7, 8 | 1 | 실제 출전 1회 이상 |
| 연속 볼넷 | 10 | 5 / 10 | 15, 20, 22 | 1(20 이후) | `PA >= 1` |
| 연속 출루 | 15 | 10 / 15 | 20, 25, 30, 35, 40, 50 | 5 | `PA >= 1`; 볼넷·사구는 성공 |
| 연속 승리 결정 | 5 | 3 / 5 | 7, 10, 15 | 5 | 승=성공, 패=종료, 무결정=skip |
| 연속 세이브 성공 | 5 | 3 / 5 | 10, 15, 20, 25 | 5 | 세이브 기회만 평가, BS=종료 |
| 연속 QS | 5 | 3 / 5 | 7, 10, 15 | 5 | 선발, 6이닝 이상, 3자책 이하 |
| 선발 연속 무실점 등판 | 3 | 2 / 3 | 4, 5, 6 | 1 | 선발, 무실점, 5이닝 이상 |
| 구원 연속 무실점 등판 | 7 | 3 / 7 | 10, 15, 20, 25 | 5 | 구원, 무실점, 1이닝 이상 |
| 연속 무실점 이닝 | 15이닝 | 9 / 15이닝 | 20, 25, 30, 35, 40, 45, 50이닝 | 5이닝 | 이닝별 실점 자료가 없으면 근사값 표시 |

모든 행에서 `emit_end_event`는 임계값에 도달한 run에만 적용한다. 종료 이벤트는 최종 길이 한 건만 저장한다.

## 기존 데이터 호환 정책

권장안은 다음과 같다.

1. 기존 마일스톤 레코드는 immutable history로 보존한다.
2. 새 정책은 적용일 이후의 새 이벤트에만 적용한다.
3. 현재 진행 상태만 원시 경기 로그에서 재계산한다.
4. 재가져오기 시 자동 과거 기록을 삭제하지 않는다. 필요하면 `superseded` revision을 추가한다.
5. 새 이벤트에는 `policy_version`, `streak_run_id`, `event_type`, `threshold`를 저장해 중복 생성을 막는다.

## 사용자 결정 필요

- 위 권장 기준을 그대로 적용할지, 첫 마일스톤을 한 단계 완화할지
- 기존 기록은 보존하고 현재 진행 상태만 재계산할지
- 무실점 이닝을 현재 경기 합계 기반 근사값으로 유지할지, 이닝별 데이터가 확보될 때까지 영구 마일스톤 생성을 보류할지

## 근거 자료

- [SABR: Consecutive-Game Hitting Streaks](https://sabr.org/journal/article/consecutive-game-hitting-streaks/)
- [MLB: Consecutive home run games](https://www.mlb.com/news/consecutive-home-run-games-c265322182)
- [MLB: Streaks to watch for in 2026](https://www.mlb.com/news/mlb-streaks-to-watch-for-in-2026)
- [MLB: Nick Kurtz extends walk streak to 20 games](https://www.mlb.com/news/nick-kurtz-extends-walk-streak-to-20-games-for-athletics)
- [Baseball Reference: Quality Start](https://www.baseball-reference.com/glossary/quality-starts/)
- [MLB: Freddy Peralta extends scoreless streak](https://www.mlb.com/news/freddy-peralta-extends-scoreless-streak-in-brewers-loss)
- [MLB: Longest scoreless inning streaks](https://www.mlb.com/amp/news/longest-scoreless-inning-streaks-in-history.html)
- [MLB: Most consecutive games played](https://www.mlb.com/news/most-consecutive-games-played-in-mlb-history-c282212708)
