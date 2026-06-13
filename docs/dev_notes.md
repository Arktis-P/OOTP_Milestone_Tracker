# 개발 노트

## 백로그 (TODO)

- [x] **레이팅 일괄 편집** — MLB+KBO 통합 팝업, 인지도/유망주 규칙, `mod_*_rosters.txt` 저장
- [x] **마일스톤 기준 재정의** — `milestones_v1.csv` 반영 (266건), `boolean`·복합 threshold 로더 지원
- [x] **앱 내 마일스톤 기준 편집** — 설정 탭 팝업에서 기준 확인·추가·수정·삭제 (`milestones.csv`)
- [x] **수동 마일스톤 입력** — 통합 팝업(개인/팀), 수동 전용·시즌 비율 분리, `is_manual` 배지·상세 패널
- [x] **선수 이름 한글 매핑** — CSV 시드·pending 큐·설정 팝업·일괄 편집·마일스톤 기록·선수 기록·마일스톤 예측 탭 표시
- [x] **season_ratio** — 시즌 마감 후 「시즌 비율 마일스톤 기록」 버튼으로 타율·ERA 등 1회 판정 (`check_season_ratios`)
- [ ] **연속 기록(streak) 마일스톤** — 별도 Phase에서 설계·검증 예정 (`ACTIVE_SCOPES`에 `streak` 미포함)

## 2026-06-12 — 마일스톤 v1·판정 확장·수동 입력

### 배경·목표
- `milestones_v1.csv` 기준(266건)으로 기준 데이터·자동 판정·수동 입력 흐름을 한 번에 정리
- 박스스코어로 판정 가능한 항목은 자동화하고, 수상·플레이오프 등은 수동 전용 UI로 분리
- 사용자 확인: 홀드(`H (N)`), 그랜드슬램(`3 on`), 비율 스탯(시즌 종료 시), 선발 등판(`career_gs`) 추정 방식

### 1. 마일스톤 기준 데이터 (v1)
- `data/milestones.csv` — v1 스펙 266건으로 교체
- key 접두사 `bat_` / `pit_` / `team_` 통일, `team_season_wins_*` 오타 수정
- `direction=boolean`, 복합 threshold(`20-20` 등), `description_template` 컬럼 추가
- `core/milestone/definitions.py` — CSV 저장·검증, boolean·복합 threshold 로더

### 2. 앱 내 마일스톤 기준 관리
- 설정 탭 — 「마일스톤 기준 관리」팝업: 기준 확인·추가·수정·삭제
- `gui/widgets/milestone_definitions_dialog.py`, `milestone_definition_form_dialog.py`
- 저장 후 `gui/app.py` `_reload_milestones()`로 앱 전역 기준 갱신

### 3. 마일스톤 기록 CRUD·표시
- 마일스톤 기록 탭 — F2 / 「수정」팝업으로 개별 기록 편집, 「삭제」로 단건 삭제
- `core/milestone/record_edit.py`, `aggregator` update/delete 메서드
- 표 컬럼: 날짜·선수·한글명·마일스톤·경기수·상대팀·상대선수·설명·비고
- `record_backfill.py` — 기존 기록 `games_at_achievement` 백필
- `description_templates.py` — 설명 템플릿 A~D 자동 생성, E는 게임 로그 참고 패널
- 자동 기록 시 `record_context.py` — scope별 경기수·상대팀·상대선수(게임 로그 우선)

### 4. 수동 입력 UI
- `core/milestone/manual_entry.py` — 유연 날짜 파싱, 검증, 중복 확인, 달성값 후보
- `gui/widgets/manual_milestone_dialog.py` — 개인/팀 라디오, scope별 필드 표시
- **「수동 입력」** — 박스스코어로 판정 가능한 항목만 (`manual_only=False`)
- **「수동 전용 입력」** — 수상·리그 1위·플레이오프·명예의 전당 등 (`requires_external_data`)
  - 마일스톤 선택 시 `「{이름}」 마일스톤은 수동으로 입력해야 합니다.` 안내
- **「시즌 비율 마일스톤 기록」** — 시즌 마감 후 타율·출루·장타·OPS·ERA 1회 판정
- `MilestoneChecker.record_manual_milestone()` — `is_manual=1` INSERT
- DB: `opponent_team`, `opponent_player`, `description`, `games_at_achievement`, `is_manual` 마이그레이션

### 5. v1 자동 판정 로직
- `core/milestone/stat_maps.py` — v1 stat 매핑 확장
- `core/milestone/game_events.py` — 사이클링 히트, 그랜드슬램(`is_grand_slam` 플래그)
- `core/milestone/composite_stats.py` — 20-20 / 30-30 / 40-40 / 50-50
- `core/milestone/tier_filter.py` — 동일 stat 다단계 중복 제거(최고 threshold만)
- `core/milestone/implementation.py` — 자동/수동/비율 구분 (`requires_external_data`, `RATIO_SEASON_STATS`)
- `core/milestone/team_milestone.py` — 선발전원안타·타점·득점, `starter_all_run` 등
- `core/milestone/checker.py` — game / season / career / team 판정 대폭 확장
  - 비율 스탯은 import 시 스킵 → `check_season_ratios()`로만 기록
  - `season_holds` 시즌·통산 홀드 집계 반영

### 6. 박스스코어 파싱·DB (사용자 확인 반영)
| 항목 | 판정 기준 |
|------|-----------|
| **홀드** | pitching linescore `L. Jackson H (3)` — `H`가 홀드, 괄호 안 숫자는 시즌 누적 |
| **그랜드슬램** | BATTING `Home Runs` 노트의 `3 on`(만루) |
| **비율 스탯** | 타율·출루·장타·OPS·ERA — 시즌 종료 후 1회만 기록 |
| **선발 등판** | 팀별 첫 등판 투수 = 선발 추정 (`career_gs`) |

- `core/parser/common.py` — `HOLD_RE`
- `core/parser/boxscore_html.py` — `PitcherLine.hold_earned`, `season_holds`
- `core/parser/batting_notes.py` — `parse_grand_slam_players`, `player_has_grand_slam`
- `core/db/schema.py` — `pitching_logs.hold`, `season_holds`, `batting_logs.is_grand_slam`
- `core/stats/aggregator.py` — import·통산 홀드 집계 반영

### 7. 테스트·문서
- `tests/test_manual_milestone.py`, `tests/test_v1_milestone_logic.py`
- `tests/test_hold_grand_slam_parse.py` — 홀드·그랜드슬램 파싱
- `docs/milestone_implementation.md` — v1 자동/수동/비율 정책 정리
- **133 tests passed**

### 8. 기타 수정
- `korean_name_mapping_dialog.py` — `_part_label` → `self._part_label` 버그 수정
- 테스트 key 갱신: `career_hr_500` → `bat_career_hr_500` 등 v1 접두사

### 미완·후속
- 연속 기록(streak) 마일스톤 — 별도 Phase (`ACTIVE_SCOPES`에 `streak` 미포함)
- ERA 마일스톤 CSV: `pit_season_era_2` 라벨은 「2점대」이나 threshold 3.00 (의도 확인됨, CSV 유지)

## 2026-06-12 — Phase 8: 레이팅 일괄 편집

### 완료
- Step 0: OOTP 26 export 156컬럼 인덱스 확정 → `core/roster/columns.py`, `docs/roster_format.md`
- `Contact vR` = CSV `Contract Vr` (인덱스 32), `Velo Pot` = 인덱스 **156** (`samples/roster/` 실측)
- `load_combined_roster()` — MLB+KBO 병합, id 중복·무소속 처리, source 태그
- `bulk_rating.py` — 유망주/기본·유망주 인지도 배율 누적, Velocity 가산, 수비 1.1배
- `BulkRatingDialog` — 검색/리그/국가/포지션/유망주 필터, 적용 후 `mod_mlb_rosters.txt` / `mod_kbo_rosters.txt` 저장
- **성능** — `QTableView` + `BulkRatingTableModel`(가상화), `FameRadioDelegate`(인지도 셀에 라디오 버튼 페인트·클릭, 위젯 0개), 검색 250ms 디바운스, `load_ootp_roster_cached()`(mtime 캐시), 저장 시에만 `deepcopy` 스냅샷
- `tests/test_bulk_rating.py`, `tests/fixtures/roster_txt/mlb_rosters.txt`

## 2026-06-12 — Phase 7: 예측 확장 + 대시보드 + 이력보내기 + 타임라인

### 완료
- `milestones.csv` — `near_n` 컬럼 추가, career 항목별 임박 기준 설정
- `predictor.is_near()` / `MilestoneDefinition.effective_near_n()` — `remaining <= near_n` 판정
- 예측 탭 — "상태" 컬럼(🔥 임박), "임박만 보기" 필터, 임박 우선 정렬
- `gui/views/dashboard_view.py` — 최근 달성 10건, 임박 예측 10건, 박스스코어 가져오기, 기본 탭
- 마일스톤 기록 탭 — 전체 이력 CSV export (`utf-8-sig`)
- 선수 기록 탭 — `PlayerMilestoneTimeline` 커리어 마일스톤 패널
- `prediction_store` — `watched_keys` 버그 수정, `list_near_cached()`
- `docs/decisions/D-024-near-n-threshold.md` ADR
- `tests/test_near_prediction.py`

## 2025-06-11 — Phase 6: 팀 마일스톤 + 로스터 편집 + 예측 정리

### 완료
- `milestones.csv`: `season_ratio` 항목 제거, 팀 마일스톤 13개 추가 (`team_game` 6, `team_manual` 4, `team_season` 3)
- `ACTIVE_SCOPES` / `PREDICTABLE_SCOPES` — `season_ratio`·팀 scope 예측 제외, career만 예측
- `core/milestone/team_milestone.py` — 선발/출장 전원 안타·타점, 노히터·퍼펙트, 시즌 승수
- `MilestoneChecker` — `tracked_teams` 대상 팀·개인 마일스톤 자동 감지(비추적 팀 경기/선수 제외), `record_manual_team_milestone`
- DB: `batting_logs.is_substitute`, `milestone_records.team` 마이그레이션
- GUI: 마일스톤 기록 탭 개인/팀 필터, 팀 수동 입력 다이얼로그, 임포트 알림에 팀 건수
- 레이팅 편집 탭 — OOTP 로스터 자동 로드(MLB/KBO)·필터·개별 선수 팝업 편집·백업 후 저장
- `tests/test_team_milestones.py`, `tests/test_roster_editor.py`

## 2025-06-11 — Phase 5: GUI ↔ 로직 연결 + 포지션 필터

### 완료
- `MainWindow.data_refreshed` Signal — 박스스코어/초기값/마일스톤/설정 변경 시 탭 동기화
- `batting_logs.position`, `players.primary_position` 스키마 + 마이그레이션
- `update_primary_positions()` — 임포트 후 최빈 포지션 반영
- 선수 기록 탭 포지션 그룹 필터 (`position_filter.py`)
- `validate_no_overlap()` — init vs 박스스코어 시즌 겹침 경고 (`ErrorBanner`)
- `scripts/e2e_verify.py` — reset → init → boxscore CLI 검증

## 2025-06-11 — Phase 4: GUI 완성

### 구현 완료
- 선수 기록 탭: `tracked_teams` 선수 목록, 시즌/통산 전환, 경기별 드릴다운
- 마일스톤 예측 탭: career scope 미달성, 달성률 정렬, 시즌 달성 가능 여부
- Import 진행률: `ImportWorker.progress`, 인라인 `QProgressBar`
- UX: 상태바, `ErrorBanner`, `grade_styles`, `TrackedTeamsWidget`

### 해결된 이슈
- WBC가 시즌 기록에 섞임 → `games.is_mlb` 필터
- 팀 약칭 vs 풀네임 불일치 → `team_filter`, `player_roster`
- SQLite 스레드 오류 → 워커별 독립 DB 연결
- 선수 이름 약식 표시 → `player_display`, export 백필
- 잘못된 MLB 팀 추가 팝업 → `league_abbr == MLB` + 구단명 매칭

## 2025-06-11 — Phase 3: 마일스톤 체커 & 초기값 임포트

### 완료
- `career_batting_init` / `career_pitching_init` 테이블 + `InitialImporter`
- 통산 집계: init + 박스스코어 UNION (`aggregator` career 쿼리)
- `pitching_logs` 특수 기록 플래그 (`is_cg`, `is_sho`, `is_no_hitter`, `is_perfect_game`)
- `MilestoneChecker` — game / season / career / season_ratio scope
- Import 직후 자동 마일스톤 체크 (`ImportWorker`)
- GUI: 마일스톤 달성 다이얼로그, 이력 탭 필터, 시즌 종료 체크, 초기값 설정 탭
- `tests/test_milestone_checker.py`, `tests/test_initial_import.py`

## 2025-06-11 — Phase 2: DB 스키마 & 집계

### 완료
- `core/db/schema.py` — games, players, batting_logs, pitching_logs, milestone_records
- `core/stats/aggregator.py` — import_boxscore, import_all_new (mtime 필터), 집계 쿼리
- `core/stats/ip_utils.py` — IP ↔ 아웃카운트 변환
- `core/parser/batting_notes.py` — doubles/hr/sb/gidp 등 노트 파싱
- `core/parser/pitching_notes.py` — game_score 등
- GUI `박스스코어 가져오기` 버튼 + `ImportWorker` (QThread)
- `data/milestones.json` — career/season/game scope 예시
- `tests/test_aggregator.py`

## 2025-06-11 — Phase 1: 박스스코어 / 게임 로그 HTML 파서

### 완료
- `core/parser/boxscore_html.py` — `BoxscoreHTMLParser` (메타, 라인스코어, 타격/투구, GAME NOTES)
- `core/parser/game_log_html.py` — `GameLogHTMLParser` (이닝별 타석, 결과 정규화)
- `core/parser/common.py` — 공통 유틸 (player_id, IP 변환, 결과 정규화)
- `core/stats/models.py` — BoxscoreData, GameLogData 등 데이터클래스
- `tests/test_parsers.py` — game 13/14 샘플 테스트 9건 통과
- 의존성: `beautifulsoup4`, `pytest`

### 데이터 해석 (사용자 확인 2025-06-11)

| 항목 | 결정 |
|------|------|
| 타자 테이블 AVG / season_hr / season_rbi | **해당 경기까지의 시즌 누적** — 맞음 |
| 이닝 득점 | **원정·홈 모두** `GameMeta.away_innings` / `home_innings`에 저장 |
| 대타/대주자 | 구분 중요도 낮음 — 일반 출장과 동일하게 집계 |
| 게임 로그 | **DB 저장 안 함** — 박스스코어로 마일스톤 달성 시 **상대·상황 파악**용 참조 |
| 마일스톤/DB 1차 소스 | **박스스코어 HTML** |

### 다음 (Phase 2)
- BoxscoreData → `batting_logs` / `pitching_logs` DB 저장
- 중복 방지 (game_id + player_id UNIQUE)
- GUI "박스스코어 가져오기" 연결

## 2025-06-11 — Phase 0: OOTP 세이브 폴더 감지 및 설정

### 완료
- `core/config/path_detector.py` — Windows/macOS 자동 탐지 (OOTP 20–26)
- `core/config/save_scanner.py` — 리그 폴더 스캔 및 유효성 검증
- `core/config/settings_manager.py` — settings.json read/write
- `gui/views/setup_view.py` — 최초 실행 설정 화면
- 앱 시작 분기: 설정 유효 → 메인 / 무효 → SetupView
- 상태바 클릭으로 리그 설정 변경

## 2025-06-11 — 프로젝트 초기화

### 완료
- 스펙 기반 디렉토리 구조 및 모듈 스켈레톤 생성
- SQLite 스키마 (`core/stats/aggregator.py`)
- 마일스톤 정의 로더, 체커, 예측기 기본 구현
- PyQt6 메인 윈도우 + 4개 탭 UI 골격
- `milestones.json`, `settings.json.example` 기본값

### 미구현 / 다음 단계

| Phase | 작업 |
|-------|------|
| 1 | 실제 OOTP 박스스코어 HTML/TXT 샘플로 파서 구현 |
| 2 | 집계 쿼리 검증, DB 마이그레이션 전략 |
| 3 | 마일스톤 체커 단위 테스트 |
| 5 | 파일 로드 → 파싱 → DB 저장 GUI 플로우 연결 |
| 7 | PyInstaller 빌드 및 경로 문제 해결 |

### 결정 사항
- `settings.json`은 Git 제외, `settings.json.example`을 템플릿으로 제공
- 박스스코어 파서는 Phase 1까지 stub (실제 샘플 필요)
- GUI DB 접근은 초기에는 동기 처리 (추후 QThread로 전환 가능)

### 샘플 리그 정보 (Phase 1 참조)

- 리그 폴더: `TestYukies_V0.0.2.lg` (`.lg` 확장자)
- 박스스코어: `{리그}/news/html/box_scores/game_box_{id}.html`
- 게임 로그: `{리그}/news/html/game_logs/log_{id}.html`
- 로컬 샘플: `samples/boxscore_html/` (8개), `samples/game_logs_html/` (8개)
- 게임 ID 13–20, 날짜 예시 03/27/2026

### 미해결 이슈
- OOTP 버전별 박스스코어 HTML 구조 차이 — 현재 샘플은 OOTP 26 기준
- 시즌 타율 마일스톤: 최소 AB 기준 미정
- 경기 수(`season_games_total`) 설정 파일화 필요
