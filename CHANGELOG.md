# Changelog

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
