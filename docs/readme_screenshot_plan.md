# README 스크린샷 촬영 계획

README에는 아직 실제 이미지 파일을 연결하지 않는다. 아래 계획은 촬영 위치와 필요한 화면 상태를 정리한 것이며, 이미지가 실제로 저장되고 검수되기 전까지 README에 이미지 링크를 추가하지 않는다.

## 저장 위치와 파일명

스크린샷을 추가할 때는 다음 폴더를 사용한다.

```text
docs/images/readme/
├─ dashboard.png
├─ achievement-records.png
├─ player-stats.png
├─ achievement-predictions.png
├─ import-existing-records.png
├─ rating-editor.png
└─ settings.png
```

파일명은 소문자와 하이픈을 사용한다. 같은 화면을 여러 크기로 중복 저장하지 않는다.

## 권장 촬영 순서

| 우선순위 | 파일명 | 실제 화면 | 보여줄 상태 | README 삽입 후보 |
|---:|---|---|---|---|
| 1 | `dashboard.png` | 대시보드 | **Getting Started**가 완료됐거나 거의 완료된 상태, 최근 마일스톤, 임박 예측, 진행 중 연속 기록 | 프로젝트 소개 아래 |
| 2 | `achievement-records.png` | 달성 기록 | 자동 기록과 수동 기록이 함께 있고, 유형·등급·출처 필터와 **Add Record**, **Export**가 보이는 상태 | 화면별 기능 인벤토리의 달성 기록 아래 |
| 3 | `player-stats.png` | 선수 기록 | 선수 목록, 시즌·통산·포스트시즌 전환, Batting/Pitching/Milestones 탭, 선수 요약 | 처음 사용하는 순서 또는 선수 기록 설명 아래 |
| 4 | `achievement-predictions.png` | 기록 달성 예측 | 선수·등급 필터, **Near Only**, 진행률과 이번 시즌 근거가 보이는 상태 | 기록 달성 예측 설명 아래 |
| 5 | `import-existing-records.png` | 기존 기록 가져오기 | 두 stats 파일 경로, 세 import 모드, **Load Database** 또는 비교 결과 | OOTP에서 준비할 파일과 경로 아래 |
| 6 | `rating-editor.png` | 레이팅 편집 | MLB/KBO 선택, 포지션·나이 필터, 로스터 목록, **Bulk Edit...**, **Save Backup**, **Save** | 레이팅 편집 설명 아래 |
| 7 | `settings.png` | 설정 | `saved_games` 경로, 리그, 시즌, 추적 팀, 고급 도구와 DB 상태 | 처음 사용하는 순서 3-4단계 근처 |

연속 기록은 독립 사이드바 화면이 아니다. 별도 이미지가 꼭 필요하면 `dashboard.png` 안의 진행 중 연속 기록이나 대시보드의 **View Ended Streaks**로 여는 **Streak Center** 대화상자를 촬영하되, README에는 독립 화면처럼 설명하지 않는다.

## 촬영 기준

- Windows 디스플레이 배율과 앱 창 크기를 모든 이미지에서 통일한다.
- 권장 폭은 1400-1800px이며 PNG로 저장한다.
- 실제 사용자 이름, 로컬 사용자 폴더, 개인 세이브 경로, API Key, 이메일 등 민감 정보는 보이지 않게 한다.
- 빈 DB나 오류 상태만 보이는 화면은 대표 이미지로 사용하지 않는다.
- 설명이 필요한 경우에도 팝업이나 드롭다운은 화면의 핵심 조작을 보여줄 때만 펼친다.
- 화면 텍스트가 README 설명과 일치하는지 촬영 직후 확인한다.

## README 삽입 기준

이미지가 실제로 존재하고 검수된 뒤에만 README에 상대 경로로 삽입한다. alt 문구는 화면 이름만 반복하지 말고, 이미지가 보여주는 기능을 설명한다. 아직 파일이 없을 때는 README 본문에 이미지 문법이나 HTML `img` 태그를 넣지 않는다.

## 자동 촬영 도입 전 확인

이 앱은 PyQt6 데스크톱 애플리케이션이므로 Playwright 기반 웹 스크린샷 대상이 아니다. 자동 촬영을 만들려면 테스트용 세이브 또는 fixture DB, 고정 창 크기, Qt 또는 Windows GUI 자동화, 화면 안정화 대기, 민감 정보 검사 절차가 먼저 필요하다.
