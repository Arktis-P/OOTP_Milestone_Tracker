# 개발 노트

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

### 미해결 이슈
- OOTP 버전별 박스스코어 HTML 구조 차이 — 샘플 파일 필요
- 시즌 타율 마일스톤: 최소 AB 기준 미정
- 경기 수(`season_games_total`) 설정 파일화 필요
