# Follow-up Verification

기존 공통 기준은 `docs/ux/UX_VERIFICATION.md`를 따른다.

## 자동 검증 결과

| 영역 | 결과 | 근거 |
|---|---|---|
| 전체 회귀 | 통과 | 368 passed, 2 skipped |
| 대시보드 시각 구조 | 통과 | hero/단일 CTA, compact readiness chip, borderless 목록, 50~70px 행 높이, 한국어 번역 테스트 |
| 메모리 검색 | 통과 | 1,000명: 1건 1.95ms, 0건 2.21ms, 1,000건 11.77ms; 기준 <=100ms |
| 상태 복원 | 통과 | 전역 geometry/마지막 화면, 세이브별 splitter/모드/시즌, offscreen fallback |
| 키보드·접근성 | 통과 | StrongFocus, accessible name/description, focus QSS 집중 테스트 |
| 취소·복구 | 통과 | 파일 경계 취소, 즉시 요청 문구, preview/persist 분리, payload 보존 Retry |
| 저장 후 행동 | 통과 | 출력·백업 경로와 폴더 열기 실패 fallback 테스트 |
| 배율·언어 | 통과(자동) | 100/125/150%에서 ko/en offscreen 캡처 생성·육안 점검 |
| 고대비 | 통과(자동) | 150% 고대비 override 캡처에서 경계·선택·경고 비색상 단서 확인 |
| 프로젝트 UX 스킬 | 통과 | frontmatter 필드 2개, 138줄, placeholder 없음 |

## 세부 테스트

- 테마·고대비: 4 passed
- 핵심 화면 접근성: 3 passed
- 초기 가져오기: 11 passed
- 상태 복원·대량 편집·테마 통합 집중: 16 passed
- 대시보드 리디자인: 3 passed
- 전체: 368 passed, 2 skipped
- `git diff --check`: 통과

## 실제 Windows에서 사용자 확인 필요

- 시스템 배율 125/150/175%에서 창 전환, 사이드바, 선수 상세, 초기 가져오기 실제 글꼴 잘림 여부
- Windows 고대비 테마와 시스템 큰 텍스트 사용 시 포커스·선택·경고 판독성
- 실제 앱 종료/재실행 및 두 세이브 전환 시 상태 복원 체감
- 대용량 실제 export에서 파일 하나를 처리하는 동안 취소 대기 문구의 체감
