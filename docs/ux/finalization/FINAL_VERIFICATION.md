# UI/UX Final Verification — Acceptance Re-audit

## 현재 판정

**병합 보류**

W1~W8의 자동 검증 결과는 유지되지만, 코드 재검수에서 최종 인수 차단 결함이 확인됐다. 이후 검증 기준은 `docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`다.

## 기존 자동 검증 증거

- 브랜치: `codex/ui-ux-audit-improvements`
- 보고된 전체 pytest: `576 passed, 2 skipped`
- 보고된 집중 W1~W7 검증: `56 passed`
- scaled Windows offscreen capture: `18 / 18`
- 캡처 스크립트: `scripts/capture_ui_ux_screenshots.py`
- 캡처 위치: `docs/ux/screenshots/final/`

위 결과는 다음을 증명한다.

- 화면 생성과 기본 렌더링
- 지정된 자동 테스트 계약
- 예외 없는 offscreen 실행

다음을 증명하지 않는다.

- 분석한 시즌과 실제 저장 시즌의 일치
- 실제 시즌 후보 검토 가능 여부
- 과거 완료 뒤 신규 메시지의 대시보드 우선 표시
- 정책 제외 메시지의 반복 스캔 방지
- full-context 메시지 수정 자동완성
- 실제 Windows 125%의 잘림·겹침·키보드 이동

## 재검수 결과

| 영역 | 판정 | 사유 |
|---|---|---|
| W1 workflow/processed 영속성 | 통과 | 기본 commit과 별도 연결 복원 테스트 확인 |
| W2 박스스코어 결과 | 통과 | 네 terminal outcome과 구조화 payload 확인 |
| W3 날짜 누락 복구 | 통과 | 실제 fixture 날짜 지정 후 candidate 재분석 확인 |
| W4 시즌 최종 판정 | 실패 | 분석/저장 시즌 불일치 가능, 실제 후보 검토 화면 없음 |
| W5 메시지 정합성 | 실패 | completed가 pending을 가릴 수 있고 정책 제외 영속화 불완전 |
| W6 결과 라우팅 | 대체로 통과 | workflow별 기본 목적지 분리, 상세 오류 UX는 후속 마감 필요 |
| W7 공통 editor | 부분 통과 | typed editor 공유, 메시지 경로에 앱 문맥 미전달 |
| CSV 출처 | 실패 | 명시적 source가 수동/자동으로 축약됨 |
| CI | 미확정 | 정확한 제품 SHA와 성공 run ID 기록 없음 |
| 실제 Windows 125% | 미완료 | offscreen 1.25만 수행, native desktop 체크 미완료 |

## 새 필수 검증

### 시즌 최종 판정

- [ ] 명시적 season/request로 분석·저장
- [ ] 다른 `season_spin` 값이 결과에 영향 없음
- [ ] 실제 후보 선수·기록·값 검토 화면
- [ ] 분석 후 export 변경 시 저장 차단
- [ ] duplicate rerun과 source=season_final

### 메시지 정합성

- [ ] 완료 뒤 새 파일 → 대시보드 필요
- [ ] 완료 뒤 변경 파일 → 대시보드 필요
- [ ] 정책 제외 재실행 pending 0
- [ ] 사용자 제외 재실행 pending 0
- [ ] changed 상태에서 과거 record ID 유지
- [ ] candidate/date/error 잔존 시 completed 금지

### 공통 편집기

- [ ] 메시지 수정에서 실제 선수 자동완성
- [ ] 표시명 선택 후 올바른 player_id
- [ ] 실제 팀·마일스톤 목록
- [ ] source note 읽기 전용 보존

### 출처·결과 복원

- [ ] CSV가 boxscore/message/manual/season_final을 구분
- [ ] 재시작 후 마지막 result summary 복원
- [ ] persisted 오류 보고서 실제 확인

## GitHub Actions

다음 값이 모두 실제 값으로 채워져야 한다.

- 제품 코드 최종 SHA: `PENDING_FINAL_ACCEPTANCE_FIXES`
- workflow run ID: `PENDING`
- Linux job: `PENDING`
- Windows job: `PENDING`
- capture artifact: `PENDING`

워크플로 파일 존재만으로 통과하지 않는다.

## 실제 Windows 125% 체크리스트

- [ ] 1366×768 / 125% / 한국어
- [ ] 최소 창 / 125% / 한국어
- [ ] 1366×768 / 125% / 영어
- [ ] 대시보드와 4개 가져오기 workflow
- [ ] 시즌 후보 검토와 저장
- [ ] 뉴스 날짜 복구와 full-context 편집
- [ ] 완료·부분 성공·실패·취소 결과
- [ ] 오류 보고서
- [ ] 글자 잘림·겹침 없음
- [ ] 키보드 포커스 이동 정상

## 최종 결정 기준

`docs/UI_UX_FINAL_ACCEPTANCE_FIX_DIRECTIVE.md`의 A1~A5와 최종 인수 조건을 모두 통과한 뒤에만 다음 중 `병합 가능`을 선택한다.

- 현재: **병합 보류**
- 후속 검수 결과: `PENDING`
