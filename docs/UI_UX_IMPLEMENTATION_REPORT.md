# UI/UX 최종화 구현 검수 보고서

> **현재 판정:** 주요 구조 구현 완료, 핵심 잔여 결함 수정 필요  
> **현재 최상위 지시서:** [`UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md)  
> 선행 지시서: [`UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md`](UI_UX_FINALIZATION_ORCHESTRATOR_DIRECTIVE.md)

## 기준과 브랜치

- 작업 브랜치: `codex/ui-ux-audit-improvements`
- 기반 기능: `codex/message-automation-validation`
- 기존 최종화 기준 커밋: `437219d`
- 최신 잔여 작업 검수 기준: 현재 브랜치 HEAD

## 전체 판정

가져오기 상태 모델, 대시보드 상태 계산, 메시지 재분석, 기존 반영 감지, 동적 현지화, 출처 마이그레이션과 CI 정의까지 구현됐다. 따라서 이전처럼 화면 구조나 문서만 변경된 상태는 아니다.

다만 다음 결함 때문에 `UI/UX 전면 개선 완료`로 판정하지 않는다.

1. 가져오기 작업 상태와 processed message 상태의 실제 commit·재연결 영속성 보장 필요
2. 박스스코어 completed·partial_success·failed·cancelled 연결 필요
3. `message_date_required` 메시지를 날짜 입력 후 복구할 수 있도록 수정 필요
4. 시즌 최종 판정의 실제 실행 경로 필요
5. 사용자 제외 영속화, 신규·변경·미처리 메시지 계산과 뉴스 완료 판정 보완 필요
6. workflow별 결과·오류 목적지 분리 필요
7. 수동 입력과 메시지 수정의 실제 공통 안내형 editor 필요
8. GitHub Actions 실제 성공 run과 Windows 125% 실검수 필요

## 구현된 기반

- `import_workflow_state` 기반 작업별 상태 계약
- `processed_messages` 기반 source ID·hash·mtime 추적
- 메시지별 생성·중복·오류 결과
- 메시지 재분석 callback과 상태 필터
- 메시지 category·reason·status·source·field 표시명 변환
- 기존 `source:<message-id>`의 `message_auto` 마이그레이션
- Linux 전체 회귀와 Windows offscreen smoke용 workflow 파일
- 한국어·영어 최종 캡처와 자동 검증 문서

## 최종 잔여 작업

오케스트레이터는 이 보고서를 다시 구현 계획으로 해석하지 않는다. 다음 문서를 열고 W1~W8을 하위 작업자에게 분배한다.

- `docs/UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`

해당 문서는 다음을 직접 지정한다.

- 수정할 함수와 파일
- 영속성·신호·상태 계산의 구현 방법
- 날짜 누락 복구 절차
- 시즌 최종 판정 연결 방식
- 작업별 결과 라우팅
- 공통 안내형 폼 구조
- 작업 선행 관계와 파일 소유권
- 필수 단위·통합 테스트
- 실제 사용자 시나리오
- CI·Windows 125% 최종 검수

## 현재 검증 근거

- 기존 보고 로컬 전체 테스트: `542 passed, 2 skipped`
- 기존 offscreen 캡처: 한국어·영어 16개 화면 생성
- 자동 캡처 증명 범위: 화면 생성, 지정 크기 렌더링, 주요 위젯 생성, 예외 없음
- GitHub Actions 실제 성공 run: 미확인
- 실제 Windows 125% 검증: 미완료

## 완료 판정 규칙

`UI_UX_LAST_MILE_ORCHESTRATOR_DIRECTIVE.md`의 W1~W8과 14절 완료 조건을 모두 충족해야 최종 완료로 변경한다.

특히 다음 중 하나라도 남으면 완료가 아니다.

- 외부 commit에 의존하는 영속성 테스트
- 실패·취소를 완료로 저장
- 날짜 누락 메시지 복구 불가
- 시즌 최종 판정의 단순 페이지 이동
- 사용자 제외 메시지의 재등장
- 전체 파일 수를 미처리 메시지 수로 표시
- workflow와 무관한 오류 화면 이동
- 번역된 2열 문자열 표만으로 공통 폼 완료 주장
- 실제 성공 CI run 없음
- offscreen 캡처만으로 Windows 125% 완료 주장
