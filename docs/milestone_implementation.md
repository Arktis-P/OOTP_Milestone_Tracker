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

## 수동 입력 전용 (현행)

수상·리그 1위·플레이오프·명예의 전당·이적·부상 등 — 달성 기록 탭 **「기록 추가」** 통합 팝업.

선택 시 `「{이름}」 마일스톤은 수동으로 입력해야 합니다.` 안내 표시.

대상 stat: `title_*`, `award_*`, `hall_of_fame`, `retired_number`,
`division_title`, `wildcard_series_win`, `division_series_win`,
`league_championship_series_win`, `world_series_win`

이적·부상은 CSV 밖 `manual_event` (`manual_transfer_*`, `manual_injury`).

## 구현됨 — `messages/` 자동화 코어와 UI 흐름

박스스코어에 없는 수상·이적·부상·일부 포스트시즌은 OOTP `messages/` 텍스트로
분류·파싱하고 기존 수동 입력 폼과 `record_manual_*` 저장 경로로 기록한다.

- 필드 규칙: [`message_automation_field_rules.md`](message_automation_field_rules.md)
- 사용자 흐름: [`message_import_workflow.md`](message_import_workflow.md)
- `messages.dat` 포맷: [`messages_dat_format.md`](messages_dat_format.md)
- 샘플: `tests/fixtures/messages/`
- 수집: `scripts/collect_message_samples.py`
- 구현: `core/milestone/message_automation/`
- 검증: `python scripts/verify_message_automation.py`
- 일괄 기록: `import_message_files(checker, paths, message_dates=...)`

OOTP 27 `messages.dat`는 현재 바이너리 날짜 테이블을 직접 해석한다. 확인된 범위는
테이블 시작 58바이트, 예약 slot 0, 115바이트 고정 레코드, `message_id` +0,
날짜(day/month/uint16 year) +96이다. 다른 필드는 의미가 확정되지 않았으므로 노출하지
않고, 알 수 없는 버전·깨진 레코드는 경고와 함께 해당 메시지만 미해결로 둔다. JSON/CSV
날짜 맵도 개발·검증용 sidecar로 계속 지원한다.

동일 소스는 `processed_messages`의 source hash/mtime과 결과 상태로 멱등 처리한다.
기록 생성과 처리 상태 저장은 메시지 단위 savepoint로 묶이며, 실패한 메시지는 롤백 후
오류 상태만 남긴다. README의 「1차 제외」 fixture는 분류 결과와 제외 사유만 반환하고
기록 폼을 만들지 않는다.

전체 시즌 재검사는 [`season_validation_replay.md`](season_validation_replay.md)의
격리 DB 워크플로를 사용한다. 운영 DB와 설정을 변경하지 않고 대상 시즌
박스스코어·뉴스를 다시 입력하며, 처리·제외·오류 건수를 JSON 보고서로 남긴다.

OOTP 인게임 명칭: Gold Glove → **Great Glove**, Silver Slugger → **Platinum Stick**
(CSV key는 `award_gold_glove` / `award_silver_slugger` 유지).

---

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
- `gui/views/milestone_view.py` — 기록 추가·시즌 비율 버튼
- `core/milestone/message_automation/` — `messages/` 분류·파싱·기존 수동 API 기록
