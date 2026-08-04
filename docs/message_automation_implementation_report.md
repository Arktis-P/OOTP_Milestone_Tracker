# 뉴스 메시지 자동화 구현 보고

## 구현 요약

- OOTP `messageN.txt` discovery를 엄격한 파일명 규칙과 숫자 정렬로 정리했다.
- OOTP 27 `messages.dat` 바이너리에서 메시지 날짜를 직접 복구한다.
- JSON/CSV 날짜 sidecar fallback을 유지해 테스트와 수동 검증 경로를 보존했다.
- 스캔 결과를 신규, 이미 반영, 변경 재검토, 제외, 오류, 날짜 필요로 구분한다.
- `processed_messages`에 source fingerprint, 상태, 생성/중복 record id, 오류를 durable하게 저장한다.
- 메시지 저장은 기존 수동 기록 API를 재사용하고 메시지별 savepoint로 원자성을 보장한다.
- 정책 제외 메시지는 제외 상태로 저장하고, 날짜 누락 후보는 영구 제외하지 않는다.
- 가져오기 센터/검토 화면에서 비동기 스캔, 검토, 승인 저장, 취소 흐름을 지원한다.

## 변경 파일 범위

주요 구현 파일:

- `core/milestone/message_automation/discovery.py`
- `core/milestone/message_automation/processed.py`
- `core/milestone/message_automation/parser.py`
- `core/milestone/message_automation/extract.py`
- `core/milestone/message_automation/recorder.py`
- `core/milestone/message_automation/service.py`
- `gui/workers/message_scan_worker.py`
- `gui/views/import_center_view.py`
- `gui/views/message_review_view.py`
- `gui/widgets/message_review_model.py`

주요 테스트 파일:

- `tests/test_message_discovery.py`
- `tests/test_processed_messages.py`
- `tests/test_message_date_recovery.py`
- `tests/test_message_scan_worker.py`
- `tests/test_message_batch_apply.py`
- `tests/test_message_workflow_completion.py`
- `tests/test_message_review_last_mile.py`
- `tests/test_import_center_app_integration.py`

## `messages.dat` 검증

실제 OOTP 27 세이브 5개를 로컬에서만 분석했다. 확인된 레코드 수는 10,098 / 207 / 942 /
5,639 / 43건이며, 모두 sibling message inventory의 최대 message ID와 일치했다.

확인된 구조:

- 테이블 시작: byte 58
- 예약 slot: 0
- 레코드 크기: 115 bytes
- message id: record +0
- 날짜: record +96 (`day`, `month`, `uint16 year`)

다른 metadata 필드는 아직 unknown으로 남겼다. unknown version은 지원하지 않고 warning과
unsupported 결과로 degrade한다.

## 검증 결과

현재 문서화 기준 검증 결과:

| 명령 | 결과 |
|------|------|
| `.venv\Scripts\python.exe -m pytest -q` | 641 passed, 2 skipped |
| `python scripts/verify_message_automation.py` | 46 fixtures parsed, 제외 fixture는 zero forms |
| `python build.py` | 성공, `dist/ootp_milestone_tracker_v0.1.9.zip` 생성 |

PyInstaller 분석과 Windows 배포 패키지 생성을 완료했다.

## 작업자 사용 및 이슈

- 오케스트레이터가 작업 분해, 구현 통합, 최종 문서화를 담당했다.
- 하위 구현 작업자는 메시지 discovery/persistence/UI 흐름/검증 범위를 나누어 작업했다.
- 일부 외부 worker 호출은 네트워크/연결 문제로 실패하거나 중단되어, 동일 범위는 로컬에서 재검토 후 통합했다.
- 실제 OOTP 세이브 데이터 분석은 로컬에서만 수행했고 외부 모델에 원본 세이브나 개인 리그 데이터를 전송하지 않았다.

## 남은 위험

- OOTP 27 외 버전의 `messages.dat` 바이너리 포맷은 미확인이다.
- `messages.dat`의 날짜 외 필드는 의미를 확정하지 않았다.
