# README 저장소 검증 결과

README 개편 전 저장소의 코드·설정·기존 문서를 기준으로 기능과 사용 흐름을 검증한 결과입니다.

## 검증 범위

- `main.py`
- `requirements.txt`
- `data/settings.json.example`
- `gui/app.py`
- `gui/sidebar_nav.py`
- 기존 `README.md`
- 마일스톤·로스터·설정 관련 `docs/` 문서

## 확인된 실행 환경

- 애플리케이션 진입점: `python main.py`
- Python: 3.11 이상
- GUI: PyQt6
- 기록 저장: SQLite
- HTML 파싱: Beautiful Soup
- 테스트: `pytest`
- Windows 빌드: `python build.py`

## 실제 사이드바 화면

`gui/sidebar_nav.py`와 `gui/app.py`를 대조한 결과, 현재 사이드바 화면은 7개입니다.

1. 대시보드
2. 달성 기록
3. 선수 기록
4. 기록 달성 예측
5. 기존 기록 가져오기
6. 레이팅 편집
7. 설정

### 수정한 기존 문서 표현

기존 README에는 **연속 기록 센터**가 독립 탭처럼 표현된 부분이 있었습니다. 현재 `gui/app.py`에는 해당 독립 페이지가 없으므로, README에서는 연속 기록을 대시보드·달성 기록·선수 기록 내부 기능으로 설명했습니다.

## 설정에서 확인된 항목

`data/settings.json.example` 기준으로 다음 설정이 존재합니다.

- OOTP 버전
- 현재 시즌
- OOTP 세이브 루트
- 활성 세이브와 경로
- 박스스코어 폴더
- 게임 로그 폴더
- `import_export` 폴더
- 로스터 파일
- 초기 stats 폴더
- 추적 팀
- 커스텀 MLB 팀
- 언어
- MLB 전용 import 여부
- 시즌 경기 수
- 타자·투수 비율 기록 자격 기준

## 확인된 입력 데이터

| 입력 | 사용 목적 |
|---|---|
| `player_batting_stats.txt` | 타자 과거 시즌·통산 초기값 및 갱신 |
| `player_pitching_stats.txt` | 투수 과거 시즌·통산 초기값 및 갱신 |
| `news/html/box_scores/*.html` | 경기별 기록, 현재 시즌 누적, 마일스톤·연속 기록 |
| MLB·KBO 로스터 | 레이팅 편집 전용 |

로스터 파일은 통계·마일스톤 import와 분리된 기능으로 확인했습니다.

## 검증된 사용자 흐름

```text
1. 앱 설치 또는 실행
2. 설정에서 OOTP 세이브·시즌·추적 팀 지정
3. 기존 기록 가져오기에서 타격·투구 stats 반영
4. 대시보드·달성 기록·선수 기록에서 박스스코어 import
5. 대시보드에서 전체 상태 확인
6. 달성 기록에서 자동·수동 이벤트 확인
7. 선수 기록과 기록 달성 예측에서 상세 결과 확인
8. 이후 경기마다 새 박스스코어 반복 import
9. 필요 시 stats를 refresh
```

## README에 반영한 주의사항

- stats import 작업 중에는 설정 변경과 앱 종료가 제한될 수 있음
- 커스텀·신생팀은 stats export에 팀 행이 없으면 선수 목록에 나타나지 않을 수 있음
- 수정된 최신 박스스코어는 교체 가능하지만 과거 경기와 같은 날짜의 복수 경기는 제한될 수 있음
- 세이브마다 별도의 SQLite DB를 사용함
- 소스 실행과 exe 실행의 사용자 데이터 위치가 다름

## 아직 실행으로 검증하지 못한 항목

이번 검증은 GitHub 저장소 코드와 문서를 기준으로 수행했습니다. 다음 항목은 Windows 로컬 환경에서 실제 앱을 실행해야 최종 확인할 수 있습니다.

- OOTP 실제 export 메뉴의 정확한 클릭 경로
- 모든 import 모드의 완료 메시지와 소요 동작
- 화면별 최신 렌더링 상태
- 배포용 exe의 실제 압축 해제·실행 흐름
- README용 스크린샷

이 항목들은 코드에서 확인되지 않은 내용을 추측해 README에 추가하지 않았습니다.
