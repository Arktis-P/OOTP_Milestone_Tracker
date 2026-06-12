# OOTP 로스터 export 포맷 (mlb_rosters / kbo_rosters)

> 검증 기준: **OOTP 26+** roster export (`samples/roster/mlb_rosters.txt`, `kbo_rosters.txt`)  
> 코드 상수: `core/roster/columns.py`

## 파일 구조

- 경로: `{세이브}/import_export/mlb_rosters.txt`, `kbo_rosters.txt`
- 인코딩: UTF-8 (BOM 가능)
- 줄바꿈: `\r\n` (원본 유지 권장)
- 주석: `//`로 시작하는 줄
- 컬럼 정의: `//id, del, team_id, ...` 한 줄 (156개 필드명)
- 데이터 행: CSV, 마지막에 `eol` 마커 (헤더 필드 수와 동일하게 패딩)

## 컬럼 수

| 항목 | 값 |
|------|-----|
| 명명 컬럼 | **157** |
| 데이터 행 | 157개 필드 + 행 끝 `eol` 마커 |

## OOTP export 오타 / 주의

| 논리명 | 실제 CSV 헤더 | 인덱스 |
|--------|---------------|--------|
| Contact vR | `Contract Vr` | 32 |
| Gap vR | `Gap Vr` | 33 |
| Avoid K vR | *(별도 컬럼 없음)* | `Ks vR` (36) 사용 |

> 구버전 포럼 샘플(156컬럼)에는 `Velo Pot`이 없었으나, 실제 `mlb_rosters`/`kbo_rosters` export에는 **마지막 컬럼(156)** 으로 존재함.

---

## 레이팅 영역별 컬럼 인덱스 (0-based)

### 1. 선수 기본 정보 (읽기 전용)

| 인덱스 | 헤더 | 샘플 설명 |
|--------|------|-----------|
| 0 | id | 선수 ID |
| 3 | Team Name | 소속 팀 |
| 4 | League Name | 리그명 |
| 5 | LastName | 성 |
| 6 | FirstName | 이름 |
| 7 | NickName | 닉네임 |
| 8 | UniformNumber | 등번호 |
| 9 | DayOB | 생일(일) |
| 10 | MonthOB | 생일(월) |
| 11 | YearOB | 생년 |
| 13 | Nation | 국적 |
| 17 | Height (cm) | 키 |
| 18 | Weight (kg) | 몸무게 |
| 19 | Bats | 타격 방향 코드 |
| 20 | Throws | 투구 팔 코드 |
| 21 | Position | 포지션 코드 (11=SP, 12=RP, 6=SS 등) |

### 2. 타자 현재 레이팅

| 인덱스 | 헤더 |
|--------|------|
| 26 | Contact vL |
| 27 | Gap vL |
| 28 | Power vL |
| 29 | Eye vL |
| 30 | Avoid K vL |
| 31 | BABIP vL |
| 32 | Contract Vr *(Contact vR)* |
| 33 | Gap Vr *(Gap vR)* |
| 34 | Power vR |
| 35 | Eye vR |
| 36 | Ks vR |
| 37 | BABIP vR |

### 3. 타자 포텐셜

| 인덱스 | 헤더 |
|--------|------|
| 38–43 | Contact Pot, Gap Pot, Power Pot, Eye Pot, Ks Pot, BABIP Pot |

### 4. 타자 기타

| 인덱스 | 헤더 | 비고 |
|--------|------|------|
| 44 | HBP | 타자 (1번째 HBP) |
| 45 | GB Batter type | |
| 46 | FB Batter type | |

### 5. 주루/작전

| 인덱스 | 헤더 |
|--------|------|
| 47–52 | speed, steal rate, steal, running, sac bunt, bunt hit |

### 6. 수비

| 인덱스 | 헤더 |
|--------|------|
| 67–70 | Infield Range, Infield Error, Infield Arm, DP |
| 71–72 | CatcherAbil, Catcher Arm |
| 73–75 | OF Range, OF Error, OF Arm |
| 155 | Catcher Framing |

### 7. 투수 기본

| 인덱스 | 헤더 |
|--------|------|
| 66 | ArmSlot |

### 8. 투수 현재 레이팅

| 인덱스 | 헤더 |
|--------|------|
| 53–54 | Move vL, Control vL |
| 55–56 | Movement vR, Control vR |
| 65 | Velocity |
| 122 | Stuff Overall |

### 9. 투수 포텐셜

| 인덱스 | 헤더 |
|--------|------|
| 57–58 | Move Pot, Control Pot |
| 124 | Stuff Pot. |
| 156 | Velo Pot |

### 10. 투구 종류 현재 (0–5)

| 인덱스 | 헤더 |
|--------|------|
| 125–136 | Fastball (scale: 0-5) … Knuckleball |

### 11. 투구 종류 포텐셜

| 인덱스 | 헤더 |
|--------|------|
| 137–148 | Fastball Pot.(scale: 0-5) … Knuckleball Pot. |

### 12. 투수 기타

| 인덱스 | 헤더 | 비고 |
|--------|------|------|
| 59 | HBP | 투수 (2번째 HBP) |
| 60–64 | WP, Balk, Stamina, Hold, GB% | |

---

## 일괄 편집 저장

- 입력: `mlb_rosters.txt`, `kbo_rosters.txt`
- 출력: 같은 폴더의 `mod_mlb_rosters.txt`, `mod_kbo_rosters.txt`
- 주석(`//`) 줄은 원본 그대로 유지

## 무소속 선수 중복

동일 `id`가 여러 행일 때:

1. `Team Name`이 비어 있거나 Free Agents 계열 → 제외
2. 소속 팀이 있는 행 우선
3. 둘 다 무소속이면 첫 행만 사용
