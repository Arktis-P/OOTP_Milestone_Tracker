# 시즌 격리 재검사

`scripts/replay_season_validation.py`는 운영 세이브 DB를 건드리지 않고 한 시즌의
박스스코어와 뉴스 메시지를 별도 SQLite DB에 다시 입력한다. 파서나 저장 로직을
수정한 뒤 같은 원본으로 결과를 반복 비교할 때 사용한다.

## 기본 경로와 안전 규칙

- 검증 DB: `data/validation/<save-slug>/season-<YYYY>/records.db`
- 결과 보고서: 같은 디렉터리의 `replay_report.json`
- 운영 DB와 검증 DB의 정규화된 경로가 같으면 실행을 거부한다.
- 기존 검증 DB 삭제·재생성은 `--reset`을 지정한 경우에만 수행한다.
- `settings.json`, `import_state`, 운영 DB는 변경하지 않는다.
- `--reset` 없이 다시 실행하면 처리한 박스스코어와 뉴스는 건너뛴다.

## 실행

현재 설정의 활성 세이브와 시즌을 사용한다.

```powershell
.\.venv\Scripts\python.exe scripts\replay_season_validation.py --reset
```

세이브, 시즌, 추적 팀을 명시할 수도 있다.

```powershell
.\.venv\Scripts\python.exe scripts\replay_season_validation.py `
  --save-path "C:\...\MyLeague.lg" `
  --season 2027 `
  --tracked-teams "SY" `
  --mlb-only `
  --reset
```

입력 파일을 분류하고 보고서만 만들려면 `--dry-run`을 사용한다. 전체 보고서를
표준 출력으로 확인하려면 `--json`을 추가한다.

## 뉴스 날짜 맵

OOTP의 `messages.dat`는 공개된 안정적 포맷이 없는 바이너리 파일이므로 현재
직접 해석하지 않는다. 파일 수정 시각을 경기 날짜로 추측하지도 않는다.
정확한 날짜가 필요한 이적·FA·연장계약·부상은 JSON 또는 CSV 날짜 맵을 전달한다.

JSON:

```json
{
  "message1433": "2027-07-20",
  "message1487.txt": "2027-07-22"
}
```

CSV:

```csv
filename,date
message1433.txt,2027-07-20
message1487.txt,2027-07-22
```

```powershell
.\.venv\Scripts\python.exe scripts\replay_season_validation.py `
  --message-dates .\message_dates.csv `
  --reset
```

날짜가 없어서 기록하지 못한 메시지는 보고서의
`messages.missing_date_count`와 `messages.missing_date_sources`에 남는다.
날짜 맵이나 본문 연도가 대상 시즌과 다르면 `outside_season_sources`로 제외한다.

## 보고서 확인 항목

- `boxscores.source_total`, `season_selected`: 전체 원본과 대상 시즌 선택 수
- `boxscores.imported`, `skipped_spring_training`, `errors`: 경기 처리 결과
- `boxscores.achievements_found`, `achievement_records_created`: 마일스톤 판정 결과
- `messages.categories`, `exclusion_reasons`: 뉴스 분류·제외 근거
- `messages.records_created`, `missing_date_count`, `errors`: 뉴스 저장 결과
- `db_summary`: 격리 DB의 경기·선수·마일스톤 최종 건수

검증 재생은 박스스코어 마일스톤과 뉴스 자동 기록을 대상으로 한다. 연속 기록,
예측 갱신, 한글 이름 메모 갱신은 실행하지 않으며 보고서 `out_of_scope`에도
명시된다.
