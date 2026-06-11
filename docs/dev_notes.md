# 개발 노트

## 2025-06-11 — Phase 2: DB 스키마 & 집계

### 완료
- `core/db/schema.py` — games, players, batting_logs, pitching_logs, milestone_records
- `core/stats/aggregator.py` — import_boxscore, import_all_new, 집계 쿼리
- `core/stats/ip_utils.py` — IP ↔ 아웃카운트 변환
- `core/parser/batting_notes.py` — doubles/hr/sb/gidp 등 노트 파싱
- `core/parser/pitching_notes.py` — game_score 등
- GUI `박스스코어 가져오기` 버튼 + `ImportWorker` (QThread)
- `data/milestones.json` — career/season/game scope 예시 12개
- `tests/test_aggregator.py` — 6건 추가 (총 15건 통과)

### 다음 (Phase 3)
- import 직후 자동 마일스톤 체크 (game/season/career scope)
- predictor 갱신

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
