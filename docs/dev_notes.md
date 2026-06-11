# 개발 노트

## 2025-06-11 — Phase 6: 팀 마일스톤 + 로스터 편집 + 예측 정리

### 완료
- `milestones.csv`: `season_ratio` 항목 제거, 팀 마일스톤 13개 추가 (`team_game` 6, `team_manual` 4, `team_season` 3)
- `ACTIVE_SCOPES` / `PREDICTABLE_SCOPES` — `season_ratio`·팀 scope 예측 제외, career만 예측
- `core/milestone/team_milestone.py` — 선발/출장 전원 안타·타점, 노히터·퍼펙트, 시즌 승수
- `MilestoneChecker` — `tracked_teams` 대상 팀 마일스톤 자동 감지, `record_manual_team_milestone`
- DB: `batting_logs.is_substitute`, `milestone_records.team` 마이그레이션
- GUI: 마일스톤 기록 탭 개인/팀 필터, 팀 수동 입력 다이얼로그, 임포트 알림에 팀 건수
- 로스터 편집 탭 — CSV 로드·필터·일괄 수정(set/+/-)·백업 후 저장
- `tests/test_team_milestones.py`, `tests/test_roster_editor.py`

### 미구현 (향후)
- `season_ratio` (타율, ERA 등) — 커리어 종료 시점 감지 불가로 별도 Phase 예정

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
