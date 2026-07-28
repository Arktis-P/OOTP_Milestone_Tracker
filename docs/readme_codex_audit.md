# README 저장소 검증 결과

이 문서는 README를 현재 `master`의 코드, 설정, 테스트, 문서와 대조해 다시 작성하면서 확인한 근거를 기록한다. 기존 README 문장은 신뢰하지 않고 구현 파일을 기준으로 판단했다.

## 확인한 주요 파일

- `README.md`
- `main.py`
- `requirements.txt`
- `build.py`
- `core/config/settings_manager.py`
- `core/config/paths.py`
- `core/config/path_detector.py`
- `core/config/save_db.py`
- `core/stats/initial_import.py`
- `core/stats/aggregator.py`
- `core/parser/boxscore_html.py`
- `core/milestone/definitions.py`
- `core/milestone/checker.py`
- `core/streak/`
- `gui/app.py`
- `gui/sidebar_nav.py`
- `gui/views/dashboard_view.py`
- `gui/views/milestone_view.py`
- `gui/views/stats_view.py`
- `gui/views/predict_view.py`
- `gui/views/initial_import_view.py`
- `gui/views/roster_view.py`
- `gui/views/setup_view.py`
- `gui/widgets/`의 수동 입력, 연속 기록, 로스터, 설정 관련 대화상자
- `data/settings.json.example`
- `data/milestones.csv`
- `tests/`
- `docs/`

## 확인된 실행 환경과 명령

- 앱 진입점은 `main.py`의 `main()`이며, 설정 언어를 먼저 읽은 뒤 `gui.app.run_app()`을 import한다.
- 소스 실행 명령은 `python main.py`다.
- Python 가상환경 생성 명령은 `python -m venv .venv`다.
- 의존성 설치 명령은 `pip install -r requirements.txt`다.
- 테스트 명령은 `pytest`다.
- 빌드 명령은 `python build.py`다.
- `build.py`는 `PIL.Image`로 `assets/icon.ico`를 생성하므로 `requirements.txt`에 `Pillow`가 필요하다.

## 실제 사이드바 화면

`gui/sidebar_nav.py`의 `_nav_sections()`와 `gui/app.py`의 `_build_pages()`를 대조한 결과, 사이드바 화면은 다음 7개다.

1. 대시보드
2. 달성 기록
3. 선수 기록
4. 기록 달성 예측
5. 기존 기록 가져오기
6. 레이팅 편집
7. 설정

연속 기록은 독립 사이드바 화면이 아니다. 대시보드의 진행 중 연속 기록 카드와 **View Ended Streaks** 버튼, 선수 기록의 마일스톤/상세 영역, 달성 기록의 streak 필터와 CSV export에서 확인한다.

## 화면별 확인 기능

| 화면 | 코드에서 확인한 기능 |
|---|---|
| 대시보드 | Getting Started 체크리스트, **Import Boxscores**, **MLB Only**, 최근 마일스톤 10개, 임박 예측 10개, 진행 중 연속 기록, **View Ended Streaks**, 관련 화면 이동 |
| 달성 기록 | 주체·팀·scope·시즌·이벤트 유형·등급·출처·검색 필터, 수동 **Milestone/Award/Team Move/Injury** 추가, 편집·삭제, 게임 로그 열기, 전체 기록 CSV, 연속 기록 CSV, 시즌 종료 비율 기록 판정 |
| 선수 기록 | 추적 선수 목록, 시즌·통산·포스트시즌 모드, 포지션 필터, 검색, Batting/Pitching/Milestones 탭, 선수 요약, 경기별 로그 대화상자 |
| 기록 달성 예측 | 통산 예측 표, 선수·등급 필터, **Near Only**, **Regenerate List**, 더블클릭 선수 기록 이동 |
| 기존 기록 가져오기 | 타격·투구 stats 경로 입력, **Initial setup**, **Off-season update**, **Mid-season compare** 모드, preview 후 저장, 알 수 없는 팀 매핑 |
| 레이팅 편집 | MLB/KBO 로스터 load, 포지션·나이 필터, 검색, 행 더블클릭 단일 편집, **Bulk Edit...**, 백업, 저장 |
| 설정 | OOTP 20-26 기본 `saved_games` 자동 탐색, 수동 경로 검증, 리그 선택, 시즌·시즌 경기 수, 추적 팀, 언어, Gemini 설정, 한글 이름 매핑, 기준 파일 업데이트, 마일스톤 기준 편집, DB 상태, 개별 박스스코어 re-import, 스프링 트레이닝 삭제, 정규시즌 복구, DB reset |

## OOTP 데이터와 경로

`SettingsManager.ensure_derived_paths()`는 활성 리그 폴더에서 다음 경로를 파생한다.

| 경로 | 사용 |
|---|---|
| `{리그}.lg/news/html/box_scores` | 박스스코어 import |
| `{리그}.lg/news/html/game_logs` | 게임 로그 열기와 기록 설명 참고 |
| `{리그}.lg/import_export` | stats export와 로스터 export |

`InitialImporter`가 표준 stats 파일명으로 사용하는 값은 다음과 같다.

- `player_batting_stats.txt`
- `player_pitching_stats.txt`

박스스코어 파서는 `game_box_*.html` 파일명을 대상으로 하며, 파일명 또는 HTML에서 game id를 얻는다. 게임 로그 참조는 `log_{game_id}.html` 형식을 사용한다.

로스터 편집은 `import_export` 아래 `mlb_rosters`, `kbo_rosters`, 같은 stem의 `.csv`/`.txt` 파일, 또는 같은 stem 폴더 안의 첫 CSV/TXT 파일을 찾는다. 일괄 저장은 `mod_mlb_rosters.txt`, `mod_kbo_rosters.txt`를 생성한다.

## 데이터 저장 위치

`core/config/paths.py` 기준:

- 소스 실행: 저장소의 `data/`
- PyInstaller 배포본 실행: `%APPDATA%\OOTP_Milestone_Tracker\`

`core/config/save_db.py` 기준 세이브별 DB는 사용자 데이터 폴더 아래 `saves/{리그폴더명_slug}_{해시}/records.db` 형식이다.

## 검증한 제한 사항

- `InitialImportView`는 import 중 현재 작업 완료 전 다른 import 단계 실행, 설정 변경, 앱 종료를 막는다.
- `ImportWorker`는 박스스코어 import, 마일스톤 판정, 연속 기록 처리를 하나의 커밋 소유권으로 묶어 취소나 오류 시 반쪽 기록을 남기지 않도록 한다.
- `Aggregator.import_all_new()`는 이미 처리한 파일의 수정 시간이 같으면 건너뛰고, import 시작 후 파일이 바뀌면 다음 실행으로 미룬다.
- `MLB Only`가 켜져 있으면 비 MLB 박스스코어를 건너뛰며, 스프링 트레이닝 박스스코어도 추적하지 않는다.
- 변경된 기존 경기 파일은 일반 batch import에서 안전한 단일 경기 re-import 흐름을 요구할 수 있다.
- `Aggregator.reimport_boxscore_file()`은 과거 경기 또는 같은 날짜 복수 경기처럼 누적 재계산이 애매한 경우 안전하게 거부할 수 있다.
- `MilestoneView._record_season_ratio_milestones()`는 시즌 종료 비율 판정 전에 최신 stats export를 요구하고, export 값이 DB 누적보다 작으면 오래된 export로 경고한다.
- `RosterView`는 표시에 최대 5,000명 제한을 둔다.
- 레이팅 편집은 로스터 파일 수정 기능이며 통계 DB나 마일스톤 기준을 자동 변경하지 않는다.
- 언어 변경은 재시작 후 적용된다.
- **Full DB Reset**은 현재 세이브의 기록 DB를 삭제하므로 재import가 필요하다.

## README에서 의도적으로 쓰지 않은 것

- 실제로 저장소에 없는 스크린샷 이미지 링크.
- OOTP UI 안에서 export 메뉴를 누르는 정확한 클릭 경로.
- 배포 exe가 항상 존재한다는 표현.
- 연속 기록 센터를 독립 사이드바 화면처럼 보이게 하는 표현.
- 로스터 편집 결과가 마일스톤 통계에 자동 반영된다는 표현.

## 관련 테스트에서 확인한 범위

`tests/`에는 다음 기능을 검증하는 테스트가 있다.

- 박스스코어 파싱과 import, re-import, 오류 처리
- MLB only 필터, 스프링 트레이닝 제외, 포스트시즌 기록
- 기존 기록 import의 `first_time`, `refresh`, `mid_season` 흐름
- 마일스톤 판정과 수동 기록
- 시즌 종료 비율 기록 판정
- 선수 기록, 포지션 필터, 한글 이름 표시
- 기록 달성 예측과 progress 표시
- 연속 기록 모델과 CSV export
- 세이브별 DB, 경로 탐색, DB reset
- 로스터 경로, 행 접근, 레이팅 편집
- SQLite 동시성 및 데이터 새로고침 라우팅

## 아직 실행으로 확인이 필요한 항목

- 실제 OOTP 앱에서 export 메뉴의 정확한 조작 경로.
- 실제 사용자 세이브 데이터로 보는 모든 화면의 최종 렌더링.
- 배포 zip을 압축 해제한 뒤 exe를 실행하는 사용자 흐름.
- README용 스크린샷 촬영 결과와 민감 정보 검수.
