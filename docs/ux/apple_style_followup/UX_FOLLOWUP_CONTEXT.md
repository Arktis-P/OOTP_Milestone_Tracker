# Apple-style UX Follow-up Context

- 브랜치: `codex/apple-style-ux` (`c4ff0c6`, 시작 시 원격과 일치)
- 목적: 상태 복원, 복구·재시도, 타입 역할, 접근성, Windows 검증 기준을 기존 UX 위에 보강한다.
- 기술: Python 3.11+, PyQt6/Fusion QSS, SQLite, `SettingsManager`, `QStackedWidget`, `QThread` worker.
- 기준: `.skills/ootp-milestone-ux/SKILL.md`, `docs/ux/UX_CONTEXT.md`, `docs/ux/UX_VERIFICATION.md`.

## 이미 구현됨

- 선수 검색 즉시 갱신, 결과 수, 빈 결과 초기화, 선택 보존
- 달성 기록 필터 요약, 빈 결과 복구, record id 선택 보존
- 공통 포커스 링과 대량 편집 전용 변경 미리보기
- 대량 저장 백업 파일명과 복구 안내

## 실제 미완료

- 반응성·배율·키보드·상태 복원의 정량 기준
- 창 geometry, 마지막 화면, 주요 splitter, 선수 기록 모드의 재실행 복원
- 타입 역할 토큰과 체크박스·탭·고대비 포커스
- 가져오기 실패 후 화면 내 재시도 행동과 접근 가능한 진행 상태
- 저장 결과/백업 위치를 바로 여는 후속 행동

## 브랜치 혼합 위험

`master...HEAD`에는 UX 외에 예측, 집계, 연속 기록, Gemini/한글 이름, 로스터 안전 저장 변경이 포함된다. 이는 현 브랜치의 선행 이력이며 이번 작업에서 되돌리거나 재구성하지 않는다. 후속 변경은 UX 파일과 직접 테스트로만 제한한다.

## 채택/제외 원칙

- 채택: 즉시 피드백, 선택·위치 보존, 예측 가능한 복구, 정보 계층, 키보드 포커스, 상태의 텍스트 표현.
- 제외: 모바일 제스처, 장식적 바운스, 중첩 반투명, 새 애니메이션 의존성.

## 수정 금지

DB 스키마, 파서, 집계, 마일스톤 판정·예측 공식, CSV/JSON 도메인 형식, 세이브별 DB 격리 계약.
