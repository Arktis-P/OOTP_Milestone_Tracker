# OOTP Milestone Tracker UX Context

## 앱 목적

OOTP 세이브에서 선수·팀 기록을 가져와 마일스톤, 예측, 연속 기록을 빠르게 탐색하고 로스터 레이팅을 안전하게 편집하는 Windows 데스크톱 앱이다.

## 기술 스택과 UI 구조

- Python 3.11+, PyQt6, SQLite, PyInstaller
- `gui/app.py`: `QMainWindow`, 좌측 `SidebarNav`, 중앙 `QStackedWidget`, 하단 상태 표시줄
- `gui/theme.py`: Fusion 팔레트와 전역 QSS 토큰
- `gui/views/`: 대시보드, 달성 기록, 선수 기록, 예측, 초기 기록 가져오기, 레이팅 편집, 설정
- `gui/widgets/`: 카드, 상태 배너, 빈 상태, 선수 상세, 일괄 편집 등 재사용 UI
- 상태는 각 뷰의 위젯 상태와 `Aggregator` 조회 결과로 관리한다. 페이지 라우팅은 정수 인덱스 기반이다.
- 비동기 가져오기는 `QThread` 작업자와 signal/slot으로 처리한다.
- UI 테스트는 pytest 기반 모델·헬퍼 검증이 중심이며 전용 시각 회귀 체계는 없다.

## 핵심 사용자 흐름

1. 설정에서 세이브와 경로를 선택한다.
2. 초기 stats 또는 박스스코어를 가져온다.
3. 대시보드와 달성 기록에서 최근·임박·연속 기록을 확인한다.
4. 필터로 기록 범위를 좁히고 선수 상세로 이동한다.
5. 선수 기록에서 시즌/통산/포스트시즌을 전환하고 경기·마일스톤을 탐색한다.
6. 예측에서 현재값, 목표값, 남은값을 확인한다.
7. 레이팅 편집에서 대상 범위를 필터링하고 변경 계획을 확인한 뒤 백업과 함께 저장한다.
8. 오류는 배너 또는 대화상자에서 확인하고 다시 시도한다.

## 공통 UX 원칙

- 입력 즉시 시각적 피드백을 제공하고 비동기 작업 중에도 관련 없는 탐색은 유지한다.
- 목록 선택과 상세 정보의 공간적 연결을 보존한다.
- 선수명, 기록 종류, 값, 날짜와 현재/목표/남은 값을 장식보다 우선한다.
- 상태·완료·경고·오류·빈 결과를 텍스트와 색상으로 함께 구분한다.
- 대량 편집은 적용 대상 수, 변경 전후, 제외/실패, 백업·복구 경로를 저장 전에 제시한다.
- 모든 주요 조작에 명확한 키보드 포커스를 제공한다.
- PyQt 데스크톱 흐름에는 장식적 스프링·제스처·중첩 반투명을 도입하지 않는다.

## 주요 컴포넌트 위치

- 테마·상태 토큰: `gui/theme.py`
- 탐색: `gui/sidebar_nav.py`
- 상태 피드백: `gui/widgets/error_banner.py`, `gui/widgets/empty_state.py`
- 기록 탐색: `gui/views/milestone_view.py`, `gui/views/stats_view.py`, `gui/views/predict_view.py`
- 선수 상세: `gui/widgets/player_detail_summary.py`, `gui/widgets/player_milestone_timeline.py`
- 대량 편집: `gui/views/roster_view.py`, `gui/widgets/bulk_rating_dialog.py`, `gui/widgets/bulk_rating_table.py`

## 현재 Phase

Phase 6 통합 검증 완료. 실제 Windows 글꼴·배율 확인만 사용자 검수로 남겨 둔다.

## 결정 사항

- 기존 다크 테마, 사이드바, 카드/분할 패널 구조를 유지한다.
- 새 외부 UI·애니메이션 의존성을 추가하지 않는다.
- 짧은 상태 변화만 사용하며 애니메이션 자체를 목표로 삼지 않는다.
- 검색·필터는 로컬 데이터에서 즉시 적용하고 선택 보존 여부를 명확히 한다.
- 위험한 편집은 전용 미리보기에서 확인하며 취소가 기본 선택이다.

## 수정 금지 영역

- `core/db/` 스키마와 마이그레이션
- 파서, 집계, 마일스톤 판정·예측 계산
- CSV/JSON 데이터 형식
- 세이브별 DB 격리와 안전 저장 계약
