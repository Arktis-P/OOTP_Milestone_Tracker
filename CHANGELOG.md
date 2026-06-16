# Changelog

## [0.1.6] - 2026-06-16

### Added
- stats 파일만으로도 선수 목록·시즌·통산 통계 조회 (박스스코어 없을 때 init 테이블 fallback)
- 커스텀 MLB 팀 추적: `player_team_affiliations` 및 팀명 부분 일치 매칭
- 세이브별 DB 분리, 설정에서 현재 세이브 데이터 초기화

### Changed
- 초기값 import 시 현재 시즌 stats 스냅샷 저장 (통산 커버리지는 기존과 동일)
- roster/소속 동기화 시 export 파일의 최신 시즌도 반영

### Fixed
- 초기값 임포트 중 `cannot start a transaction within a transaction` 오류
- DB 초기화 후 예측 탭 등에서 닫힌 DB 참조 오류
- DB 초기화 시 WinError 32 (파일 사용 중) 처리

## [0.1.5] - 2026-06-16

### Fixed
- 초기값 임포트 시 `database is locked` 오류 수정 (WAL 모드, 저장 중 메인 DB 연결 해제)

## [0.1.4] - 2026-06-16

### Changed
- 통산 마일스톤 예측 `track_from`을 남은 수치 기준으로 변경 (기본: 목표의 15% 남음)
- `near_n` 임박 항목을 예측 목록에서 행 배경색으로 강조

## [0.1.0] - 2025-06-11

### Added
- 프로젝트 초기 스캐폴딩 (core, gui, data, docs)
- SQLite 집계 및 마일스톤 체크/예측 기본 로직
- PyQt6 탭 기반 GUI (마일스톤, 기록, 예측, 로스터)
- PyInstaller 빌드 스크립트 (`build.py`)
