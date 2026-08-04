# OOTP `messages.dat` 포맷 메모

현재 구현은 OOTP Baseball 27 세이브의 `messages.dat`에서 메시지 ID와 날짜만 읽는다.
이 포맷은 공개 사양이 아니므로 확인된 필드 외에는 사용하지 않는다.

## 확인된 OOTP 27 바이너리 레이아웃

로컬의 독립된 OOTP 27 세이브 5개에서 검증했다. 각 세이브의 sibling message inventory와
`messages.dat`에서 읽은 최대 메시지 ID가 일치했다.

| 확인 항목 | 값 |
|-----------|----|
| 파일 signature | `00 4F 4F 54 50` (`\0OOTP`) |
| 버전 바이트 | 27 |
| 테이블 시작 offset | 58 |
| 예약 레코드 | slot 0 |
| 레코드 크기 | 115 bytes |
| 메시지 ID | 레코드 offset +0, little-endian uint32 |
| 날짜 | 레코드 offset +96: day byte, month byte, year little-endian uint16 |

검증한 레코드 수:

| 세이브 | 확인된 메시지 레코드 수 |
|--------|------------------------|
| save 1 | 10,098 |
| save 2 | 207 |
| save 3 | 942 |
| save 4 | 5,639 |
| save 5 | 43 |

## 파서 정책

- `message_id == slot`이고 날짜가 유효한 레코드만 채택한다.
- slot 0은 예약 레코드로 보고 건너뛴다.
- 손상된 레코드는 경고로 남기고 다음 slot을 계속 검사한다.
- 연속 8개 비정상 slot은 보조 trailer로 보고 탐색을 끝낸다.
- 버전이 27이 아니거나 signature가 맞지 않으면 unsupported로 처리한다.
- 날짜 외 metadata는 의미가 확정되지 않아 노출하지 않는다.

## fallback 포맷

개발·검증용으로 JSON/CSV 날짜 sidecar도 계속 지원한다. 파일 확장자가 아니라 내용을 sniff한다.

JSON 예:

```json
{
  "message1433": "2027-07-20",
  "message1487.txt": "2027-07-22"
}
```

CSV 예:

```csv
source_id,date
message1433,2027-07-20
message1487,2027-07-22
```

## 제한

- OOTP 26 이하 또는 이후 버전은 아직 확인하지 않았다.
- 메시지 제목, 읽음 여부, 카테고리 등으로 보이는 다른 필드는 의미가 확정되지 않았다.
- 파일 수정 시각은 날짜 fallback으로 사용하지 않는다.
- 실제 세이브 바이너리는 로컬 분석에만 사용했고 외부로 전송하지 않았다.
