# OOTP Message Fixtures (SuperYukies_V1.0.lg)

`messages/` 파서 개발용 샘플. 원본: OOTP Baseball 27 `SuperYukies_V1.0.lg`.

재수집:

```bash
python scripts/collect_message_samples.py
```

## 명칭 주의

| 기존(야구 일반) | OOTP 인게임 명칭 |
|-----------------|------------------|
| Gold Glove | **Great Glove** |
| Silver Slugger | **Platinum Stick** |

방출·웨이버·선수 구매는 인박스 뉴스가 나오지 않아 **의도적으로 제외**.

**기록 필드 규칙(설명·내용·비고 등):** [`docs/message_automation_field_rules.md`](../../../docs/message_automation_field_rules.md)

## 자동화 가능 항목

| 자동화 대상 | milestone / API | 샘플 fixture | 비고 |
|-------------|-----------------|--------------|------|
| 트레이드 | `manual_transfer_trade` | `trade_multi_player_*`, `trade_simple_*` | |
| FA 계약 | `manual_transfer_fa_contract` | `fa_signing_mlb_*`, `fa_signing_minor_*` | 설명: `{N}년 ${총액} FA 계약 체결` |
| 계약 연장 | `manual_transfer_extension_contract` | `contract_extension_*` | 설명: `{N}년 ${총액} 연장 계약 체결` |
| 부상 | `manual_injury` | `injury_game_*`, `injury_offfield_*` | 설명: `{부상 종류} 부상으로 {기간} 진단` |
| MVP | `award_mvp` | `award_mvp_*` | 투표 문구·추적팀 순위는 비고 |
| CY Young | `award_cy_young` | `award_cy_young_*` | 동일 |
| Great Glove | `award_gold_glove` (파싱어 Great Glove) | `award_great_glove_*` | |
| Platinum Stick | `award_silver_slugger` (파싱어 Platinum Stick) | `award_platinum_stick_*` | |
| 신인왕 | `award_rookie_of_year` | `award_rookie_of_year_*` | |
| 이달의 타자/투수/신인 | `award_player_of_month` | `award_batter_of_month_*`, `award_pitcher_of_month_*`, `award_rookie_of_month_*` | 직전 달. **이주의 선수는 기록 안 함** |
| 올스타 선발 | `award_all_star` | `award_all_star_selection_01` (로스터 발표) | `_02` 투표 시작은 **기록 안 함** (샘플만) |
| 디비전 우승 | `division_title` | `postseason_division_*` | |
| **월드시리즈 우승** | `world_series_win` | `postseason_world_series_*` | |
| 명예의 전당 헌액 | `hall_of_fame` | `hall_of_fame_01` | `_02` 투표 시작은 기록 안 함 |

### 샘플만 두고 1차 자동화에서 제외

| fixture | 이유 |
|---------|------|
| `postseason_wildcard_*` | CSV는 「와일드카드 **시리즈 승리**」 — 진출 확정과 불일치 |
| `postseason_playoff_clinch_*` | 대응 milestone key 없음 |
| `trade_deadline_news_*` | 실제 트레이드 아님 |
| `retirement_*` | 은퇴 마일스톤 미정의 |
| `award_all_star_selection_02`, `hall_of_fame_02` | 투표 시작 |

## 샘플 파일 목록

| 카테고리 | fixture | 원본 | 제목 |
|----------|---------|------|------|
| trade_multi_player | `trade_multi_player_01.txt` | message1433.txt | Cincinnati Swaps McCrystal to Tokyo for Winker |
| trade_multi_player | `trade_multi_player_02.txt` | message1487.txt | Miami, Milwaukee Confirm Trade |
| trade_simple | `trade_simple_01.txt` | message1435.txt | Los Angeles-Minnesota Deal: Ruiz for Banuelos |
| trade_simple | `trade_simple_02.txt` | message1477.txt | Martin and Ramirez Traded |
| trade_deadline_news | `trade_deadline_news_01.txt` | message506.txt | Breaking ATL News: Trade Deadline |
| injury_game | `injury_game_01.txt` | message410.txt | More Injury Problems for Miami's Kyle Stowers |
| injury_game | `injury_game_02.txt` | message1007.txt | Injury Shuts Down Arrieche for Season |
| injury_game | `injury_game_03.txt` | message816.txt | Yordan Alvarez of Houston Injured, DTD |
| injury_offfield | `injury_offfield_01.txt` | message22.txt | Wilson Trips Running Up Stairs, May Miss Time |
| injury_offfield | `injury_offfield_02.txt` | message179.txt | Errant Ball KO's Toribio |
| fa_signing_mlb | `fa_signing_mlb_01.txt` | message5095.txt | SP Gray Commits to 1-Year Rockies Offer |
| fa_signing_mlb | `fa_signing_mlb_02.txt` | message5338.txt | SP May Excited to Play for Minnesota |
| fa_signing_minor | `fa_signing_minor_01.txt` | message4968.txt | SP Peralta Signs on with Boston |
| contract_extension | `contract_extension_01.txt` | message114.txt | Seoul, Moon Agree on 15-Year Extension |
| contract_extension | `contract_extension_02.txt` | message2396.txt | Mize Signs Extension with Tigers |
| contract_extension | `contract_extension_03.txt` | message9788.txt | San Francisco and Hentges Agree on Extension |
| award_mvp | `award_mvp_01.txt` | message4841.txt | 2026 #1 Player Chosen By AL |
| award_mvp | `award_mvp_02.txt` | message4842.txt | Great Year Gets Kim NL Most Valuable Player Award |
| award_mvp | `award_mvp_03.txt` | message10062.txt | Do-young Kim Takes MVP Trophy |
| award_cy_young | `award_cy_young_01.txt` | message4834.txt | #1 AL Hurler Named |
| award_cy_young | `award_cy_young_02.txt` | message4835.txt | Best Pitcher Honor Goes to Peralta of New York |
| award_cy_young | `award_cy_young_03.txt` | message10058.txt | Cy Young Award Goes to Seoul Hurler |
| award_great_glove | `award_great_glove_01.txt` | message4802.txt | Top Defensive Players Named by AL |
| award_great_glove | `award_great_glove_02.txt` | message4803.txt | Best Defenders Announced by NL |
| award_great_glove | `award_great_glove_03.txt` | message4393.txt | PIO Honors Top Glovemen for 2026 |
| award_platinum_stick | `award_platinum_stick_01.txt` | message4820.txt | Top Sluggers Win AL Platinum Stick Award Honors |
| award_platinum_stick | `award_platinum_stick_02.txt` | message4821.txt | National League Platinum Stick Award Winners Picked |
| award_platinum_stick | `award_platinum_stick_03.txt` | message3152.txt | Big Hitters Get Named FCL Platinum Stick Award Winners |
| award_rookie_of_year | `award_rookie_of_year_01.txt` | message4324.txt | BNBL Rookie of the Year Award Announced |
| award_rookie_of_year | `award_rookie_of_year_02.txt` | message4447.txt | PIO Best Newcomer Named |
| award_batter_of_month | `award_batter_of_month_01.txt` | message771.txt | New York's Judge Collects April Batting Honor |
| award_batter_of_month | `award_batter_of_month_02.txt` | message772.txt | Kim Crowned Batter of the Month in April |
| award_pitcher_of_month | `award_pitcher_of_month_01.txt` | message773.txt | Bradish Chosen April's Best AL Hurler |
| award_pitcher_of_month | `award_pitcher_of_month_02.txt` | message774.txt | NL Pitcher of the Month Goes to Cabrera |
| award_rookie_of_month | `award_rookie_of_month_01.txt` | message809.txt | April's Spotlight Falls on Rookie Star |
| award_all_star_selection | `award_all_star_selection_01.txt` | message2280.txt | MLB Headline News: The All-Star Game Rosters Have Been Announced |
| award_all_star_selection | `award_all_star_selection_02.txt` | message1049.txt | MLB News: The All-Star Game Voting Begins |
| postseason_wildcard | `postseason_wildcard_01.txt` | message4235.txt | Wild Card Clinched by Astros |
| postseason_playoff_clinch | `postseason_playoff_clinch_01.txt` | message4335.txt | Brewers Off to the Playoffs |
| postseason_division | `postseason_division_01.txt` | message4202.txt | American League West Division Winner is Seattle Mariners |
| postseason_division | `postseason_division_02.txt` | message4325.txt | Orioles Capture American League East Division |
| postseason_division | `postseason_division_03.txt` | message9587.txt | New York Mets Clinch First in National League East Division |
| postseason_world_series | `postseason_world_series_01.txt` | message9924.txt | Yukies Sweep Tigers |
| retirement | `retirement_01.txt` | message441.txt | New York Reliever Hill Will Retire |
| hall_of_fame | `hall_of_fame_01.txt` | message5327.txt | Hall of Fame Inducts Lee |
| hall_of_fame | `hall_of_fame_02.txt` | message5056.txt | HH Headline News: The Hall of Fame Voting Begins |

## 파싱 공통 포맷

```
<Player Name:player#39226>
<Team Name:team#18>
<Catcher:value_bold#0>
```

Great Glove / Platinum Stick은 포지션별 수상자 목록 형태입니다.
