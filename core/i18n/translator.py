"""Translation engine — English keys → target language strings."""

from __future__ import annotations

from datetime import datetime, timedelta

_language: str = "ko"

# fmt: off
_KO: dict[str, str] = {

    "games":                           "경기",
    "outs":                            "아웃",
    "Milestone records are unavailable.": "마일스톤 기록을 사용할 수 없습니다.",
    "Predictions are unavailable.":    "예측을 사용할 수 없습니다.",
    "Open a league database and try again.": "리그 데이터베이스를 연 뒤 다시 시도하세요.",

    # ── Relative time formatting (shared) ────────────────────────────────
    "Today {time}":                     "오늘 {time}",
    "Yesterday {time}":                 "어제 {time}",

    # ── Readiness checklist (core/app_state.py) ──────────────────────────
    "Active league selected":           "활성 리그 선택",
    "No league selected yet.":          "아직 리그를 선택하지 않았습니다.",
    "Tracked teams configured":         "추적 팀 설정",
    "No tracked teams configured yet.": "아직 추적 팀을 설정하지 않았습니다.",
    "Existing records imported":        "기존 기록 가져오기 완료",
    "Existing career/season records have not been imported yet.":
        "기존 통산·시즌 기록을 아직 가져오지 않았습니다.",
    "Through {season} season · {batting:,} batters / {pitching:,} pitchers":
        "{season}시즌까지 · 타자 {batting:,}명 / 투수 {pitching:,}명",
    "Boxscores imported":               "박스스코어 가져오기 완료",
    "No boxscores have been imported yet.": "아직 박스스코어를 가져오지 않았습니다.",
    "{games:,} MLB games imported":     "MLB {games:,}경기 가져옴",
    "Getting Started":                  "시작 체크리스트",
    "✅ Setup complete":                "✅ 설정 완료",
    "Select League →":                  "리그 선택하기 →",
    "Import Existing Records →":        "기존 기록 가져오기 →",
    "Import Boxscores →":               "박스스코어 가져오기 →",
    "Go →":                             "이동 →",

    # ── Sidebar navigation ──────────────────────────────────────────────
    "Record Inspector":             "기록 검사기",
    "Dashboard":                    "대시보드",
    "Achievement Records":          "달성 기록",
    "Player Stats":                 "선수 스탯",
    "Achievement Predictions":      "기록 달성 예측",
    "Tools & Settings":             "도구 & 설정",
    "Import Existing Records":      "기존 기록 가져오기",
    "Rating Editor":                "능력치 편집기",
    "Settings":                     "설정",
    "Bundle update available":      "번들 업데이트 있음",
    "● Checking data...":           "● 확인 중...",
    "● Data OK":                    "● 데이터 정상",
    "⚠ No league selected":         "⚠ 리그 미설정",
    "⚠ Data connection issue":      "⚠ 데이터 연결 오류",
    "Select a league in Settings.": "설정에서 리그를 선택하세요.",
    "{league} · Season {season}":   "{league} · {season}시즌",
    "DB: {path}":                   "DB: {path}",

    # ── App / status bar ────────────────────────────────────────────────
    "Settings saved":               "설정 저장",
    "(No league selected)":         "(리그 미선택)",
    "All":                          "전체",
    "League Settings":              "리그 설정",
    "OOTP Milestone Tracker — Settings": "OOTP Milestone Tracker — 설정",
    "League: {league} · Season {season} · Tracked: {teams} · Last import: {last} · DB: {games} games / {players} players (click to configure)":
        "리그: {league} · {season}시즌 · 추적팀: {teams} · 마지막 가져오기: {last} · DB: {games}경기 / {players}명 (클릭해서 설정)",

    # ── Dashboard ───────────────────────────────────────────────────────
    "⚡ OOTP Simulation Control Panel":  "⚡ OOTP 시뮬레이션 컨트롤 패널",
    "📥  Import Boxscores":             "📥  박스스코어 가져오기",
    "MLB Only":                         "MLB만",
    "→ Import Existing Records":        "→ 기존 기록 가져오기",
    "View All Achievement Records →":   "전체 달성 기록 보기 →",
    "🏆  Recent Milestones (last 10)":  "🏆  최근 마일스톤 (최근 10개)",
    "View All Predictions →":           "전체 예측 보기 →",
    "🔥  Upcoming (Near)":              "🔥  다가오는 마일스톤 (근접)",
    "Active League: {league}  ·  Season {season}  ·  Last import: {last}":
        "활성 리그: {league}  ·  {season}시즌  ·  마지막 가져오기: {last}",
    "No recent milestone records.":     "최근 마일스톤 기록이 없습니다.",
    "No near career milestones.":       "근접한 커리어 마일스톤이 없습니다.",
    "Import boxscores to automatically detect milestones.":
        "박스스코어를 가져오면 자동으로 마일스톤을 탐지합니다.",
    "Import Boxscores":                 "박스스코어 가져오기",
    "Go to Achievement Records":        "달성 기록 화면으로 이동",
    "vs {opponent}":                    "vs {opponent}",
    "{season} season":                  "{season}시즌",
    "No predictable records.":          "예측 가능한 기록이 없습니다.",
    "Import existing career/season records first.":
        "기존 시즌·통산 기록을 먼저 가져와 주세요.",
    "{current:,.0f} / {target:,.0f}  ·  {remaining:,.0f} remaining":
        "{current:,.0f} / {target:,.0f}  ·  {remaining:,.0f} 남음",
    "   {label} — {remaining:,} remaining":  "   {label} — {remaining:,} 남음",
    "Boxscore folder not configured. Select a league in Settings.":
        "박스스코어 폴더가 설정되지 않았습니다. 설정에서 리그를 선택하세요.",

    # ── Import progress (shared across views) ───────────────────────────
    "Checking milestones... ({current}/{total}) {filename}":
        "마일스톤 확인 중... ({current}/{total}) {filename}",
    "Checking streaks... ({current}/{total}) {filename}":
        "연속기록 확인 중... ({current}/{total}) {filename}",
    "Importing boxscores... ({current}/{total}) {filename}":
        "박스스코어 가져오는 중... ({current}/{total}) {filename}",
    "{count} games added":              "{count}경기 추가됨",
    "{count} non-MLB skipped":          "{count}개 MLB 외 스킵",
    "{count} milestones achieved":      "{count}개 마일스톤 달성",
    "Some errors: {count} — ":         "일부 오류: {count}개 — ",
    "Import Complete":                  "가져오기 완료",
    "Details":                          "세부 정보",
    "Import failed: {message}":         "가져오기 실패: {message}",
    "No new games":                     "새 경기 없음",
    "{count} errors":                   "오류 {count}건",
    "View New Milestones":              "새 마일스톤 보기",
    "View First Error":                 "첫 오류 확인",
    "Import Errors":                    "가져오기 오류",
    "View Errors ({count})":            "오류 {count}건 보기",
    "Error Message":                    "오류 내용",
    "Unknown error":                    "알 수 없는 오류",
    "Copy Selected":                    "선택 항목 복사",
    "Copy All":                         "전체 복사",
    "{count} import error(s)":          "가져오기 오류 {count}건",
    "{remaining:,.0f} remaining":       "{remaining:,.0f}개 남음",
    "{current:,.0f} / {target:,.0f}  ·  {pct:.1f}%":
        "{current:,.0f} / {target:,.0f}  ·  {pct:.1f}%",
    "Continue":                         "계속",
    "Cancel":                           "취소",
    "Export File Problem":              "스탯 Export 파일 문제",
    "No Season Data":                   "시즌 데이터 없음",
    "No OOTP stats export was found in: {path}":
        "다음 폴더에서 OOTP 스탯 Export 파일을 찾지 못했습니다: {path}",
    "No export file was selected. Choose the OOTP stats files and retry.":
        "Export 파일이 선택되지 않았습니다. OOTP 스탯 파일을 확인한 뒤 다시 시도하세요.",
    "Export file not found: {path}":     "Export 파일을 찾지 못했습니다: {path}",
    "The export file is empty: {path}": "Export 파일이 비어 있습니다: {path}",
    "The export file cannot be read: {path} ({error})":
        "Export 파일을 읽을 수 없습니다: {path} ({error})",
    "The export file could not be parsed: {path} ({error})":
        "Export 파일을 분석할 수 없습니다: {path} ({error})",
    "The export file has no data rows: {path}":
        "Export 파일에 스탯 데이터 행이 없습니다: {path}",
    "Export the {season} season player stats from OOTP before continuing.\n\n"
    "If you still need to export, select Cancel. If the stats files "
    "already exist, select Continue.":
        "계속하기 전에 OOTP에서 {season}시즌 선수 스탯을 Export하세요.\n\n"
        "아직 Export가 필요하면 취소를, 스탯 파일이 이미 있으면 계속을 선택하세요.",
    "{season} season AVG/OBP/SLG/OPS/ERA milestones will be judged from "
    "the exported OOTP stats files.\n\n"
    "If you still need to export, select Cancel. If these files are the "
    "latest export, select Continue.":
        "{season}시즌 타율/출루율/장타율/OPS/ERA 마일스톤을 OOTP 스탯 "
        "Export 파일로 판정합니다.\n\n"
        "아직 Export가 필요하면 취소를, 최신 파일이 맞으면 계속을 선택하세요.",
    "No export folder is configured. Set it in Settings and retry.":
        "Export 폴더가 설정되지 않았습니다. 설정에서 지정한 뒤 다시 시도하세요.",
    "Not found: {path}":                "파일 없음: {path}",
    "The export files contain no {season} season MLB records, "
    "so nothing was judged or saved.":
        "Export 파일에 {season}시즌 MLB 기록이 없어 아무 기록도 판정하거나 저장하지 않았습니다.",
    "The export files do not contain current {season} season rows. "
    "Export both batting and pitching player stats from OOTP, then retry.":
        "Export 파일에 현재 {season}시즌 타격/투구 기록이 들어 있지 않습니다. "
        "OOTP에서 타격과 투구 선수 스탯을 모두 Export한 뒤 다시 시도하세요.",
    "The exported stats look older than the imported boxscores. "
    "Export the final {season} season player stats from OOTP, then retry.":
        "Export 스탯이 가져온 박스스코어 누적보다 오래된 중간 시즌 파일일 수 있습니다. "
        "OOTP에서 {season}시즌 최종 선수 스탯을 Export한 뒤 다시 시도하세요.",
    "Showing {shown} of {total} issue(s):":
        "전체 {total}건 중 대표 {shown}건:",
    "{player_name} · {category}/{stat}: Export {export_value} < boxscore {db_value}":
        "{player_name} · {category}/{stat}: Export {export_value} < 박스스코어 {db_value}",

    # ── Milestone view — table columns ───────────────────────────────────
    "Date":                             "날짜",
    "Player Name":                      "선수명",
    "Player Name (Korean)":             "선수명 (한글)",
    "Team":                             "팀",
    "Milestone":                        "마일스톤",
    "Games":                            "경기",
    "Opponent":                         "상대팀",
    "Opp. Player":                      "상대선수",
    "Description":                      "설명",
    "Notes":                            "메모",

    # ── Milestone view — filters & buttons ───────────────────────────────
    "All (subject)":                    "전체 (대상)",
    "Personal Only":                    "개인만",
    "Team Only":                        "팀만",
    "All Teams":                        "전체 팀",
    "All Scopes":                       "전체 범위",
    "Game":                             "경기",
    "Season":                           "시즌",
    "Career":                           "커리어",
    "Team Game":                        "팀경기",
    "Team Season":                      "팀시즌",
    "Streak":                           "연속기록",
    "Search player, team, or milestone...": "선수, 팀, 마일스톤 검색...",
    "🌐 Open Game Log":                 "🌐 게임 로그 열기",
    "Refresh":                          "새로고침",
    "Export to CSV":                    "CSV 내보내기",
    "Export Streak":                    "연속기록 내보내기",
    "➕ Manual Entry":                  "➕ 수동 입력",
    "Team Move":                        "팀 이동",
    "Export":                           "내보내기",
    "Full History CSV":                 "전체 기록 CSV",
    "Streak CSV":                       "연속 기록 CSV",
    "More":                             "더보기",
    "Determine Final Season Records":   "시즌 최종 기록 판정",
    "Edit":                             "수정",
    "Delete":                           "삭제",
    "F2: Edit · Del: Delete · Double-click: Game Log": "F2: 수정 · Del: 삭제 · 더블클릭: 게임 로그",
    "Milestone History":                "마일스톤 이력",
    "Subject":                          "대상",
    "Search":                           "검색",
    "Imports Major League boxscores only. KBO, WBC, etc. are skipped.":
        "메이저리그 박스스코어만 가져옵니다. KBO·WBC 등은 건너뜁니다.",

    # ── Milestone view — export dialogs ─────────────────────────────────
    "Export Milestone History":         "마일스톤 이력보내기",
    "Exports the full milestone history (regardless of current filter).\nDo you want to continue?":
        "전체 마일스톤 이력을 내보냅니다 (현재 필터와 무관).\n계속하시겠습니까?",
    "Export complete: {filepath}":      "내보내기 완료: {filepath}",
    "Export Streak Records ({season} season)": "연속기록 내보내기 ({season}시즌)",
    "Streak export failed: {error}":    "연속기록 내보내기 실패: {error}",
    "{season} season — {count} streak CSV file(s) saved.\n{dir}\n{files}":
        "{season}시즌 연속기록 CSV {count}개를 저장했습니다.\n{dir}\n{files}",
    "Select Season":                    "시즌 선택",
    "Please select a season year in the season filter and try again.":
        "시즌 필터에서 연도를 선택한 뒤 다시 시도하세요.",
    "Records AVG/OBP/SLG/OPS/ERA milestones for {season} season based on current DB.\n\nRecommended to run once after the season ends. Continue?":
        "{season}시즌 타율·출루율·장타율·OPS·ERA 마일스톤을 현재 DB 기준으로 기록합니다.\n\n시즌이 끝난 뒤 한 번 실행하는 것을 권장합니다. 계속하시겠습니까?",
    "{season} season — {count} ratio milestone(s) recorded":
        "{season}시즌 비율 마일스톤 {count}건 기록",
    " ({count} candidates)":            " (달성 후보 {count}건)",

    # ── Milestone view — edit / delete ───────────────────────────────────
    "Please select a record to edit.":  "수정할 기록을 선택하세요.",
    "The selected record could not be found.": "선택한 기록을 찾을 수 없습니다.",
    "Please select a record to delete.": "삭제할 기록을 선택하세요.",
    "Delete Milestone Record":          "마일스톤 기록 삭제",
    "Delete the following record?\n\n{target} · {label}\n{date}":
        "다음 기록을 삭제하시겠습니까?\n\n{target} · {label}\n{date}",
    "Failed to delete the record.":     "기록을 삭제하지 못했습니다.",
    "Milestone record deleted.":        "마일스톤 기록을 삭제했습니다.",

    # ── Milestone view — meta panel ──────────────────────────────────────
    "Value: {value}":                   "달성 수치: {value}",
    "Season: {season}":                 "시즌: {season}",
    "Game ID: {game_id}":               "경기 ID: {game_id}",
    "Manual entry":                     "수동 입력",

    # ── Stats view ───────────────────────────────────────────────────────
    "View Career Records":           "통산 기록 보기",
    "Season":                        "시즌",
    "Career":                        "통산",
    "Postseason":                    "포스트시즌",
    "Career postseason stats (from imported boxscores)":
        "통산 포스트시즌 기록 (임포트된 박스스코어 기준)",
    "Search player...":              "선수 검색...",
    "Filter list by name or ID. Does not re-query DB on each input.":
        "이름·ID로 목록을 필터합니다. 입력마다 DB를 다시 읽지 않습니다.",
    "Stat":                          "항목",
    "Batting":                       "타격",
    "Pitching":                      "투구",
    "No records":                    "기록 없음",
    "Boxscore name":                 "박스스코어 표기",
    "[Manual]":                      "[수동]",
    "Milestones":                    "마일스톤",
    "Position":                      "포지션",
    "Tracked Players":               "추적 대상 선수",
    "Please select a player.":       "선수를 선택하세요.",
    "Career stats (init through {coverage} season + boxscores)":
        "통산 기록 (init {coverage}시즌까지 + 박스스코어)",
    "No initial stats — boxscore records only":
        "초기값 없음 — 박스스코어 기록만 집계",
    "{season} season stats (initial value — stats file, no boxscores)":
        "{season}시즌 기록 (초기값 — stats 파일, 박스스코어 없음)",
    "{season} season stats (double-click: game-by-game log)":
        "{season}시즌 기록 (더블클릭: 경기별 기록)",
    "Stats":                         "기록",
    "Boxscore folder not configured. Click the status bar at the bottom to select a league.":
        "박스스코어 폴더가 설정되지 않았습니다. 하단 상태바를 클릭해 리그를 선택하세요.",
    "No players to display. Check that initial stats (stats file) are imported and that custom teams have their abbreviation and name registered in Settings.":
        "표시할 선수가 없습니다. 기존 기록 가져오기( stats 파일 )을 했는지, 커스텀 팀은 설정에서 약칭·팀 이름을 등록했는지 확인하세요.",
    "No players to display. Run initial setup or import boxscores, then check again.":
        "표시할 선수가 없습니다. 기존 기록 가져오기 또는 박스스코어 가져오기 후 다시 확인하세요.",
    "Personal: {count}":             "개인 {count}",
    "Team: {count}":                 "팀 {count}",

    # ── Predict view ─────────────────────────────────────────────────────
    "🔄 Regenerate List":           "🔄 목록 재생성",
    "Rebuilds the career milestone tracking list from scratch.\nNormally updated automatically when boxscores are imported.":
        "추적 대상 통산 마일스톤 목록을 처음부터 다시 만듭니다.\n평소에는 박스스코어 가져오기 시 자동으로 갱신됩니다.",
    "All Players":                   "전체 선수",
    "All Grades":                    "전체 등급",
    "🔥 Near Only":                 "🔥 임박만 보기",
    "Achievement Predictions (Career)": "기록 달성 예측 (통산)",
    "Player":                        "선수",
    "Grade":                         "등급",
    "Korean Name":                   "한글명",
    "Current":                       "현재값",
    "Target":                        "목표값",
    "Remaining":                     "남은 수치",
    "Progress":                      "달성률",
    "Status":                        "상태",
    "This Season":                   "이번 시즌",
    "No data":                       "데이터 없음",
    "Pre-season — achievability unknown": "시즌 전 — 달성 가능성 미정",
    "Achievable (+{amount})":        "가능 (+{amount})",
    "Not achievable (+{amount}, {after} remaining after season)":
        "불가 (+{amount}, 시즌 후 {after} 남음)",
    "Career Achievement Predictions":  "통산 기록 달성 예측 목록",
    "No career milestone predictions to display.\nNo players are within tracking range, or check your tracked teams and boxscores.":
        "표시할 통산 마일스톤 예측이 없습니다.\n남은 수치가 추적 시작 기준 이하인 선수가 없거나, 추적 팀·박스스코어를 확인하세요.",
    "🔥 Near":                       "🔥 임박",

    # ── Initial import view ───────────────────────────────────────────────
    "Initial setup — load all data through completed season":
        "최초 설정 — 완료 시즌까지 전체 적재",
    "Off-season update — add previous season + compare":
        "비시즌 갱신 — 직전 시즌 추가 + 비교",
    "Mid-season compare — check differences without saving":
        "시즌 중 비교 — 저장 없이 차이만 확인",
    "📥  Load Database":            "📥  데이터베이스 적재",
    "File Selection":                "파일 선택",
    "Import Mode":                   "임포트 모드",
    "Register Historical Career & Season Baseline Stats":
        "과거 통산 및 시즌 Baseline 초기값 등록",
    "Loads career baseline data from player_batting_stats.txt · player_pitching_stats.txt exported from OOTP.":
        "OOTP에서 export한 player_batting_stats.txt · player_pitching_stats.txt 파일로 통산 베이스라인을 적재합니다.",
    "Browse":                        "찾아보기",
    "Select {filename}":             "{filename} 선택",
    "Mid-season Import":             "시즌 중 임포트",
    "Data for the current season ({season}) will not be saved to the DB.\nOnly a comparison with boxscore totals will be run.\n\nContinue?":
        "현재 시즌({season}) 데이터는 DB에 저장되지 않습니다.\n박스스코어 집계값과 비교만 실행합니다.\n\n계속하시겠습니까?",
    "File Required":                 "파일 필요",
    "Please select a batting file.": "타격 파일을 선택하세요.",
    "Please select a pitching file.": "투구 파일을 선택하세요.",
    "Please select a batting or pitching file.": "타격 또는 투구 파일을 선택하세요.",
    "Saving... ({current}/{total}) {filename}":
        "저장 중... ({current}/{total}) {filename}",
    "Done":                          "완료",
    "Import completed successfully.": "임포트가 완료되었습니다.",
    "Import Failed":                 "임포트 실패",
    "Error":                         "오류",
    "Off-season update — {prev_season} season comparison results":
        "비시즌 갱신 — {prev_season}시즌 비교 결과",
    "Mid-season compare — {season} season (not saved)":
        "시즌 중 비교 — {season}시즌 (저장되지 않음)",
    "Previous season update comparison": "이전 시즌 갱신 비교",
    "Add based on file":             "파일 기준으로 추가",
    "Comparison Result":             "비교 결과",
    "{prev_season} season: no differences between boxscores and file values.\nUpdate based on file?":
        "{prev_season}시즌: 박스스코어와 파일값 차이가 없습니다.\n파일 기준으로 갱신할까요?",
    "Batting: {batting_players:,} players · through {coverage} season (updated {batting_at})\nPitching: {pitching_players:,} players · through {coverage} season (updated {pitching_at})":
        "타격: {batting_players:,}명 · {coverage}시즌까지 (갱신 {batting_at})\n투구: {pitching_players:,}명 · {coverage}시즌까지 (갱신 {pitching_at})",

    # ── Import / roster errors ────────────────────────────────────────────
    "Not an MLB boxscore.":              "MLB 박스스코어가 아닙니다.",
    "Unsupported roster format. An OOTP export (.txt) file is required.":
        "지원하지 않는 로스터 형식입니다. OOTP export (.txt) 파일이 필요합니다.",
    "Please enter a player name.":       "선수 이름을 입력하세요.",
    "Cannot save 「{name}」.\nThe file may be open in OneDrive sync or another program (Excel, Notepad, etc.). Close the file and try again.":
        "「{name}」 파일을 저장할 수 없습니다.\nOneDrive 동기화 중이거나 Excel·메모장 등 다른 프로그램에서 해당 파일을 열어 두었을 수 있습니다. 파일을 닫은 뒤 다시 시도하세요.",
    "Please enter both the name and Korean notation.":
        "이름과 한글 표기를 모두 입력하세요.",

    # ── Roster view ───────────────────────────────────────────────────────
    "Name":                          "이름",
    "League":                        "리그",
    "Age":                           "나이",
    "File: (none)":                  "파일: (없음)",
    "Load":                          "불러오기",
    "Bulk Edit...":                  "일괄 편집...",
    "Save Backup":                   "원본 복사본 저장",
    "Apply Filter":                  "필터 적용",
    "Loads roster from the save's import_export folder. Double-click a player to edit ratings.":
        "세이브의 import_export 폴더에서 로스터를 불러옵니다. 선수 더블클릭으로 레이팅을 편집하세요.",
    "Min Age":                       "최소 나이",
    "Max Age":                       "최대 나이",
    "Rating Editor":                 "레이팅 편집",
    "Roster List":                   "로스터 목록",
    "(No save configured)":          "(세이브 미설정)",
    "File: (no save configured)":    "파일: (세이브 미설정)",
    "File Not Found":                "파일 없음",
    "No active save is configured.\nSelect a league in the Settings tab.":
        "활성 세이브가 설정되지 않았습니다.\n설정 탭에서 리그를 선택하세요.",
    "File: {path}":                  "파일: {path}",
    "Roster file not found.\n\nPath: {path}\n({label} — OOTP roster export required in import_export folder)":
        "로스터 파일을 찾을 수 없습니다.\n\n경로: {path}\n({label} — import_export 폴더에 OOTP 로스터 export 필요)",
    "Load Failed":                   "로드 실패",
    "Loaded: {name} ({count:,} players)": "로드됨: {name} ({count:,}명)",
    "No Data":                       "데이터 없음",
    "Please load the roster first.": "먼저 로스터를 불러오세요.",
    "Filter result: {count:,} players": "필터 결과: {count:,}명",
    "No Save Configured":            "세이브 미설정",
    "No active save is configured.": "활성 세이브가 설정되지 않았습니다.",
    "Roster Error":                  "로스터 오류",
    "No original file to back up.":  "저장할 원본 파일이 없습니다.",
    "Backup Failed":                 "백업 실패",
    "Backup Complete":               "백업 완료",
    "Copy saved:\n{path}":           "복사본 저장:\n{path}",
    "Confirm Backup":                "백업 확인",
    "No backup has been saved yet.\nCreate a backup now before saving?":
        "원본 복사본을 먼저 저장하지 않았습니다.\n지금 백업을 만든 뒤 저장할까요?",
    "Save Failed":                   "저장 실패",
    "Saved":                         "저장 완료",
    "Saved to: {path}":              "저장 위치: {path}",

    # ── Setup view ───────────────────────────────────────────────────────
    "Season Year":                        "시즌 연도",
    "Season Games":                       "시즌 경기 수",
    "saved_games Folder":                 "saved_games 폴더",
    "📁  OOTP Integration":              "📁  OOTP 연동",
    "⚙️  Tracking Settings":             "⚙️  추적 설정",
    "🛠️  Tools":                         "🛠️  도구",
    "The season year currently in progress in OOTP.\nUsed for boxscore import filtering, initial stats import, and milestone evaluation.":
        "현재 OOTP에서 진행 중인 시즌 연도입니다.\n박스스코어 임포트 필터링, 초기값 임포트, 마일스톤 평가에 사용됩니다.",
    "OOTP saved_games folder path":      "OOTP saved_games 폴더 경로",
    "Verify Path":                       "경로 확인",
    "Auto-detected":                     "자동 감지됨",
    "Manual":                            "수동",
    "Open Pending Mappings":             "대기 매핑 열기",
    "Run Merge Update":                  "업데이트 병합 실행",
    "Edit Milestone Definitions":        "마일스톤 정의 편집",
    "Save All Settings & Refresh Data":  "전체 설정 저장 및 데이터 갱신",
    "Confirm & Start":                   "확인 및 시작",
    "OOTP Save Folder":                  "OOTP 세이브 폴더",
    "League Selection":                  "리그 선택",
    "Current Season":                    "현재 시즌",
    "Season Year:":                      "시즌 연도:",
    "Match the OOTP season in progress. (e.g., playing 2026 season → 2026)":
        "현재 진행 중인 OOTP 시즌에 맞춰 설정하세요. (예: 2026시즌 진행 중 → 2026)",
    "Tracking Settings":                 "추적 설정",
    "Tracked Teams:":                    "추적 팀:",
    "Season Games:":                     "시즌 경기 수:",
    "Language:":                         "언어:",
    "Select from 30 MLB teams or add manually. You will only be prompted to add new teams during initial import if expansion teams or other new MLB franchises are added to your game.":
        "30개 MLB 팀 중 선택하거나 수동으로 추가하세요. 확장팀 또는 새 MLB 프랜차이즈가 게임에 추가된 경우 초기 임포트 중에만 새 팀 추가 안내가 표시됩니다.",
    "Korean Names":                      "한글 이름",
    "Manage Korean name mappings for romanized first/last names. Enter any unregistered items here after loading stats or boxscores.":
        "로마자 성·이름의 한글 이름 매핑을 관리합니다. 스탯 또는 박스스코어 로드 후 미등록 항목을 여기에 입력하세요.",
    "Reference File Updates":            "참조 파일 업데이트",
    "Merges newly added milestones, streak rules, and Korean name mappings into your local files after an app update.":
        "앱 업데이트 후 새로 추가된 마일스톤, 연속기록 규칙, 한글 이름 매핑을 로컬 파일에 병합합니다.",
    "Milestone Definitions":             "마일스톤 정의",
    "Manage the milestone list used for achievement evaluation in milestones.csv.":
        "milestones.csv에서 달성 평가에 사용되는 마일스톤 목록을 관리합니다.",
    "Selected path:":                    "선택 경로:",
    "OOTP SAVED_GAMES Root":             "OOTP SAVED_GAMES 루트",
    "Scanned Save Leagues":              "검색된 세이브 리그",
    "Current Active Season":             "현재 활성 시즌",
    "Tracked Team List":                 "추적 팀 목록",
    "+ Add Team Manually":               "+ 팀 수동 추가",
    "Total Season Games":                "시즌 총 경기 수",
    "Language":                          "언어",
    "📁  OOTP Integration Settings":     "📁  OOTP 연동 설정",
    "🛠️  Advanced Modules & Data Tools": "🛠️  고급 모듈 & 데이터 도구",
    "Korean Name Auto-mapping":          "한글 이름 자동 매핑",
    "Processes pending romanized name → Korean conversion items.":
        "대기 중인 로마자 이름 → 한글 변환 항목을 처리합니다.",
    "Edit Milestone Criteria":           "마일스톤 기준 편집",
    "Defines milestone types and grade thresholds in milestones.csv.":
        "milestones.csv에서 마일스톤 유형 및 등급 기준을 정의합니다.",
    "Update App Reference Files":        "앱 참조 파일 업데이트",
    "Merges local milestone ruleset and Korean name mapping patches.":
        "로컬 마일스톤 규칙 및 한글 이름 매핑 패치를 병합합니다.",
    "Refresh Status":                    "상태 새로고침",
    "🚨 Full DB Reset":                  "🚨 전체 DB 초기화",
    "🔄 Re-import Individual Boxscores": "🔄 개별 박스스코어 재임포트",
    "🌱 Remove Spring Training Games":   "🌱 스프링 트레이닝 기록 제거",
    "🔁 Recover Regular Season Games":   "🔁 정규 시즌 기록 복구",
    "Scanning...":                       "검사 중...",
    "No spring training games found in tracked data.":
        "추적 데이터에 스프링 트레이닝 기록이 없습니다.",
    "Removed {count} spring training games.":
        "스프링 트레이닝 기록 {count}건을 제거했습니다.",
    "Removed {count} spring training games from tracked data.":
        "추적 데이터에서 스프링 트레이닝 기록 {count}건을 제거했습니다.",
    "Cleanup Complete":                  "정리 완료",
    "Recovered {count} regular season games.":
        "정규 시즌 기록 {count}건을 복구했습니다.",
    "Recovery Complete":                 "복구 완료",
    "Recovery Failed":                   "복구 실패",
    "Checked {checked} file(s) modified since the latest spring training "
    "game ({cutoff_date}).\nRecovered {count} regular season game(s).":
        "가장 최근 스프링 트레이닝 경기({cutoff_date}) 이후 수정된 파일 {checked}개를 "
        "검사했습니다.\n정규 시즌 기록 {count}건을 복구했습니다.",
    "{count} error(s):":                 "오류 {count}건:",
    "{count} new items available (app v{version})": "{count}개의 새 항목 사용 가능 (앱 v{version})",
    "Update Reference Files... ({count})": "참조 파일 업데이트... ({count})",
    "All reference files are up to date.": "모든 참조 파일이 최신 상태입니다.",
    "Update Reference Files...":         "참조 파일 업데이트...",
    "Auto-detection failed. Use [Browse] to select the saved_games folder manually.":
        "자동 감지 실패. [찾아보기]를 사용해 saved_games 폴더를 직접 선택하세요.",
    "Auto-detection successful: {count} path(s) found.":
        "자동 감지 성공: {count}개 경로 발견.",
    "Select OOTP saved_games folder":    "OOTP saved_games 폴더 선택",
    "Auto-detected: OOTP {version} — {path}": "자동 감지됨: OOTP {version} — {path}",
    "Invalid Path":                      "잘못된 경로",
    "The selected folder is not an OOTP saved_games directory.\n\nMake sure you selected the saved_games folder.\n(It must contain league folders or .lg folders.)":
        "선택한 폴더가 OOTP saved_games 디렉토리가 아닙니다.\n\nsaved_games 폴더를 선택했는지 확인하세요.\n(리그 폴더 또는 .lg 폴더가 포함되어야 합니다.)",
    "Invalid saved_games path.":         "잘못된 saved_games 경로입니다.",
    "Valid saved_games path.":           "유효한 saved_games 경로입니다.",
    "No valid league folders found under saved_games.":
        "saved_games 아래 유효한 리그 폴더가 없습니다.",
    "(Please select a league)":          "(리그를 선택하세요)",
    "League Required":                   "리그 선택 필요",
    "Please select a league to re-import first.": "먼저 재임포트할 리그를 선택하세요.",
    "Please select a league first.":     "먼저 리그를 선택하세요.",
    "Path Required":                     "경로 필요",
    "Box score folder is not set.":      "박스스코어 폴더가 설정되지 않았습니다.",
    "Select a league to view DB status.": "DB 상태를 보려면 리그를 선택하세요.",
    "No saved game, milestone, or initial stats data.":
        "세이브 게임, 마일스톤 또는 초기값 데이터가 없습니다.",
    "Please select a league to reset first.": "먼저 초기화할 리그를 선택하세요.",
    "Current save":                      "현재 세이브",
    "No saved data":                     "저장된 데이터 없음",
    "Reset Data":                        "데이터 초기화",
    "All tracking data for save 「{save_name}」 will be deleted.\n\n{detail}\n\nMilestone records, season/career stats, and predictions will be permanently deleted. Continue?":
        "세이브 「{save_name}」의 모든 추적 데이터가 삭제됩니다.\n\n{detail}\n\n마일스톤 기록, 시즌/통산 스탯, 예측이 영구 삭제됩니다. 계속하시겠습니까?",
    "MLB games: {games}":                "MLB 경기: {games}건",
    "Recorded players: {players}":       "기록 선수: {players}명",
    "Milestone records: {count}":        "마일스톤 기록: {count}건",
    "Career batting init players: {count}": "통산 초기값 (타격): {count}명",
    "Career pitching init players: {count}": "통산 초기값 (투구): {count}명",
    "Career milestone predictions: {count}": "통산 마일스톤 예측: {count}건",
    "Init coverage: through {season} season": "초기값 시즌 커버리지: {season}시즌까지",
    "Reset Failed":                      "초기화 실패",
    "Could not delete the DB file.\n{error}": "DB 파일을 삭제할 수 없습니다.\n{error}",
    "Reset Complete":                    "초기화 완료",
    "Current save data has been reset.\nPlease import existing records and boxscores again.":
        "현재 세이브 데이터가 초기화되었습니다.\n기존 기록 가져오기와 박스스코어 가져오기를 다시 실행하세요.",
    "Korean Name Mapping...":            "한글 이름 매핑...",
    "Input Required":                    "입력 필요",
    "Please select the OOTP save folder.": "OOTP 세이브 폴더를 선택하세요.",
    "This is not an OOTP saved_games folder. Please verify the path.":
        "OOTP saved_games 폴더가 아닙니다. 경로를 확인하세요.",
    "League Selection Required":         "리그 선택 필요",
    "Please select a league.":           "리그를 선택하세요.",
    "Restart Required":                  "재시작 필요",
    "Language change will take effect after restarting the app.":
        "언어 변경 사항은 앱을 재시작한 후 적용됩니다.",

    # ── app_dialog.py button defaults ────────────────────────────────────
    "Save":                              "저장",
    "OK":                                "확인",
    "Update based on file":              "파일 기준으로 갱신",

    # ── milestone_dialog.py ───────────────────────────────────────────────
    "Newly Achieved Milestones":         "새로 달성된 마일스톤",
    "Achievement Date":                  "달성일",
    "Achievement List":                  "달성 목록",

    # ── edit_milestone_record_dialog.py / shared form labels ─────────────
    "Edit Milestone Record":             "마일스톤 기록 수정",
    "Date:":                             "날짜:",
    "Achieved Value:":                   "달성값:",
    "Season:":                           "시즌:",
    "Games:":                            "경기수:",
    "Opponent:":                         "상대팀:",
    "Opp. Player:":                      "상대선수:",
    "Description:":                      "설명:",
    "Notes:":                            "비고:",
    "Record not found.":                 "기록을 찾을 수 없습니다.",
    "Record Info":                       "기록 정보",
    "Input Error":                       "입력 오류",
    "Achieved value must be a number.":  "달성값은 숫자여야 합니다.",
    "Season and games must be integers.": "시즌·경기수는 정수여야 합니다.",

    # ── player_rating_dialog.py ───────────────────────────────────────────
    "Rating Editor — {name}":            "레이팅 편집 — {name}",
    "Ratings":                           "레이팅",
    # ── rating_fields.py section titles ──────────────────────────────────
    "Player Info":                       "선수 기본 정보",
    "Batter Current Ratings":            "타자 현재 레이팅",
    "Batter Potential":                  "타자 포텐셜",
    "Batter Other":                      "타자 기타",
    "Running / Tactics":                 "주루/작전",
    "Defense":                           "수비",
    "Pitcher Basic":                     "투수 기본",
    "Pitcher Current Ratings":           "투수 현재 레이팅",
    "Pitcher Potential":                 "투수 포텐셜",
    "Pitch Type Current Ratings":        "투구 종류 현재 레이팅",
    "Pitch Type Potential":              "투구 종류 포텐셜",
    "Pitcher Other":                     "투수 기타",
    "HBP (Pitcher)":                     "HBP (투수)",

    # ── dev_boxscore_reimport_dialog.py ──────────────────────────────────
    "Re-import Boxscores (Dev)":         "박스스코어 다시 불러오기 (개발용)",
    "Select a boxscore HTML file to re-import. Games already in the DB will be deleted and re-parsed. (Streak state may differ from a full season reprocess.)":
        "박스스코어 HTML을 선택해 다시 불러옵니다. 이미 DB에 있는 경기도 삭제 후 재파싱·마일스톤 기록합니다. (연속 기록 상태는 시즌 전체 재처리와 다를 수 있습니다.)",
    "Load List":                         "목록 불러오기",
    "Select Folder...":                  "폴더 선택...",
    "Add Files...":                      "파일 추가...",
    "Away @ Home":                       "원정 @ 홈",
    "Game ID":                           "게임 ID",
    "Filename":                          "파일명",
    "Imported":                          "불러옴",
    "Scan folder: {path}":               "스캔 폴더: {path}",
    "Scan folder: (no boxscore folder configured — select a folder or file)":
        "스캔 폴더: (설정된 박스스코어 폴더 없음 — 폴더 또는 파일을 선택하세요)",
    "{count} files":                     "{count}개 파일",
    "Folder Not Found":                  "폴더 없음",
    "Select a boxscore folder first, or verify the league path in settings.":
        "박스스코어 폴더를 먼저 선택하거나 설정에서 리그 경로를 확인하세요.",
    "Select Boxscore Folder":            "박스스코어 폴더 선택",
    "Select Boxscore HTML":              "박스스코어 HTML 선택",
    "File Format":                       "파일 형식",
    "Not a game_box_*.html file: {filename}":
        "game_box_*.html 형식이 아닙니다: {filename}",
    "Re-import Selected Game":           "선택 경기 다시 불러오기",
    "Boxscore Files":                    "박스스코어 파일",
    "Confirm Re-import":                 "다시 불러오기 확인",
    "The following game will be re-imported.\n\n{match}\nDate: {date}\nFile: {filename}\n\nExisting DB data and milestone records for this game will be deleted and reprocessed.":
        "다음 경기를 다시 불러옵니다.\n\n{match}\n날짜: {date}\n파일: {filename}\n\n기존 DB 데이터와 해당 경기 마일스톤 기록이 삭제된 뒤 다시 처리됩니다.",
    "Processing: {filename}":            "처리 중: {filename}",
    "Re-import Failed":                  "다시 불러오기 실패",
    "Unknown error":                     "알 수 없는 오류",
    "Re-import failed":                  "다시 불러오기 실패",
    "Game re-imported successfully":     "경기 다시 불러오기 완료",
    "Skipped (unexpected state)":        "스킵됨 (예상치 못한 상태)",
    "{count} milestone(s) recorded":     "마일스톤 {count}건 기록",
    "Re-import complete":                "다시 불러오기 완료",
    "Re-import Complete":                "다시 불러오기 완료",

    # ── init_compare_dialog.py ────────────────────────────────────────────
    "Boxscore Total":                    "박스스코어 집계",
    "File Value":                        "파일값",
    "Diff":                              "차이",
    "No differences.":                   "차이가 없습니다.",
    "File may contain games not yet in boxscore DB.":
        "박스스코어에 없는 경기가 파일에 포함됐을 수 있습니다.",
    "Stat Differences":                  "통계 차이",

    # ── korean_name_mapping_dialog.py ─────────────────────────────────────
    "Korean Name Mapping":               "한글 이름 매핑",
    "Unregistered names from boxscore/stats imports accumulate here.\nMaps first/last names based on OOTP full name (First Last) format. Korean players show in Last+First order; others in First+Last.\nGray suggestions are auto-proposed from bundle/user CSV mappings and MLB transliteration rules. Leave as-is and save to apply; delete to exclude.":
        "박스스코어·스탯 불러오기 중 등록되지 않은 성/이름이 여기에 쌓입니다.\nOOTP 풀 네임(First Last) 기준으로 성·이름을 나눠 매핑합니다. 한국인은 성+이름, 그 외는 이름+성 순으로 표시됩니다.\n회색 추천 표기는 번들·사용자 매핑 CSV와 MLB 중계식 규칙을 바탕으로 자동 제안합니다. 그대로 두고 저장하면 매핑에 반영되며, 지우면 저장에서 제외됩니다.",
    "Search romanized...":               "로마자 검색...",
    "Refresh List":                      "목록 새로고침",
    "Edit CSV:":                         "CSV 편집:",
    "Last Name CSV":                     "성 매핑 CSV",
    "First Name CSV":                    "이름 매핑 CSV",
    "Pending List CSV":                  "대기 목록 CSV",
    "Type":                              "구분",
    "Full Name (Ref)":                   "풀 네임(참고)",
    "Romanized":                         "로마자",
    "Korean Name (Suggestion)":          "한글 표기 (추천)",
    "Source":                            "출처",
    "Pending Mappings":                  "매핑 대기 목록",
    "Save Entered Items":                "입력한 항목 저장",
    "CSV file not found.\n{path}":       "CSV 파일을 찾을 수 없습니다.\n{path}",
    "Open Failed":                       "열기 실패",
    "Could not open CSV with default app.\nPath: {path}":
        "기본 프로그램으로 CSV를 열지 못했습니다.\n경로: {path}",
    "Korean name needed: {count:,}":     "한글 표기 필요: {count:,}건",
    " · Suggested: {count:,}":           " · 추천 {count:,}건",
    " · Showing: {count:,}":             " · 표시 {count:,}건",
    "Auto-suggested. Save without editing to apply to mappings.":
        "자동 추천 표기입니다. 수정·삭제하지 않고 저장하면 매핑에 반영됩니다.",
    "Manually entered.":                 "직접 입력한 표기입니다.",
    "Last":                              "성",
    "First":                             "이름",
    "Failed to save Korean name mapping file.": "한글 매핑 파일을 저장하지 못했습니다.",
    "Save Error":                        "저장 오류",
    "{count:,} Korean name(s) saved.":   "{count:,}건의 한글 표기를 저장했습니다.",
    "No Changes":                        "변경 없음",
    "No Korean names to save.":          "저장할 한글 표기가 없습니다.",

    # ── manual_milestone_dialog.py ─────────────────────────────────────────
    "Manual Entry":                      "수동 입력",
    "Record":                            "기록",
    "Award":                             "수상",
    "Injury":                            "부상",
    "Add Record":                        "기록 추가",
    "Target:":                           "대상:",
    "Personal":                          "개인",
    "Player:":                           "선수:",
    "Team:":                             "팀:",
    "Milestone:":                        "마일스톤:",
    "Games in:":                         "동안 경기수:",
    "Enter full name or select from list (e.g., Dong-ju Moon)":
        "풀 네임 입력 또는 목록 선택 (예: Dong-ju Moon)",
    "+ Add Player":                      "+ 선수 추가",
    "Games played up to this point":     "이 시점까지 출장한 경기수",
    "Select tracked team players from the list, or enter a full name directly / use '+ Add Player' to register players not yet in the DB.":
        "추적 팀 선수는 목록에서 고르고, 아직 DB에 없는 선수는 풀 네임을 직접 입력하거나 '+ 선수 추가'로 등록할 수 있습니다.",
    "Records player transfer events such as contracts and trades. Separate multiple players with commas.":
        "계약·트레이드 등 선수 이동 내역을 기록합니다. 합류·이탈 선수는 쉼표로 구분하세요.",
    "Records injury events such as player injuries and returns.":
        "선수 부상 발생·복귀 등 부상 관련 내역을 기록합니다.",
    "e.g., Hamstring, shoulder surgery":  "예: 햄스트링, 어깨 수술",
    "e.g., 3 days, 3 weeks, 5-6 months": "예: 3일, 3주, 5-6달",
    "e.g., Dong-ju Moon, A. Judge (comma-separated)":
        "예: Dong-ju Moon, A. Judge (쉼표 구분)",
    "Joining:":                          "합류:",
    "Leaving:":                          "이탈:",
    "Type:":                             "유형:",
    "Join Team:":                        "합류팀:",
    "Counterpart Team:":                 "상대팀:",
    "Affil. Team:":                      "소속팀:",
    "Injury:":                           "부상:",
    "Duration:":                         "기간:",
    "Awards, league leaders, and other items not auto-detected from boxscores.":
        "수상·리그 1위 등 박스스코어에서 자동 판정되지 않는 항목입니다.",
    "Can be auto-detected from boxscores, but use this to supplement or correct.":
        "박스스코어로 자동 판정 가능하지만 수동으로 보완·수정할 때 사용합니다.",
    "Check date format":                 "날짜 형식을 확인하세요",
    "Add Player":                        "선수 추가",
    "Enter full name (e.g., Dong-ju Moon):":
        "풀 네임을 입력하세요 (예: Dong-ju Moon):",
    "Please select a milestone.":        "마일스톤을 선택하세요.",
    "Season must be a number.":          "시즌은 숫자여야 합니다.",
    "Games must be an integer.":         "동안 경기수는 정수여야 합니다.",
    "Select a player or enter a full name.": "선수를 선택하거나 풀 네임을 입력하세요.",
    "Duplicate Check":                   "중복 확인",
    "{dup_msg}\nAdd anyway?":            "{dup_msg}\n그래도 추가하시겠습니까?",
    "Save All":                          "모두 저장",
    "+ Add to List":                     "+ 목록에 추가",
    "Remove Selected":                   "선택 삭제",
    "Records to add:":                   "추가할 기록:",
    "Target":                            "대상",
    "Achieved Value":                    "달성값",
    "Add One at a Time":                 "하나씩 입력하기",
    "Add Row":                            "행 추가",
    "Enter records directly in the table below, or use "
    "'Add One at a Time' for the classic single-record form.":
        "아래 표에 바로 입력하세요. 기존 방식으로 하나씩 입력하려면 "
        "'하나씩 입력하기'를 사용하세요.",
    "Games in":                          "동안 경기수",
    "Duration":                          "기간",
    "Affil. Team":                       "소속팀",
    "Row {n}":                           "{n}번 행",
    "Add Award":                         "수상 추가",
    "Add Milestone":                     "마일스톤 추가",
    "Add Team Move":                     "이적 추가",
    "Add Injury":                        "부상 추가",
    "Add":                               "추가",
    "Required":                          "필수 입력",
    "Auto (date year)":                  "자동 (날짜의 연도)",
    "Auto in-season":                    "시즌 중 자동",
    "Off-season transfer: please enter the season directly.":
        "비시즌 이적입니다. 시즌을 직접 입력해주세요.",
    "Translating via Gemini...":         "제미나이로 번역 중...",
    "Please add at least one record.":   "기록을 하나 이상 추가하세요.",

    # ── team_milestone_dialog.py ──────────────────────────────────────────
    "Manual Team Milestone Entry":       "팀 마일스톤 수동 입력",
    "Team Milestone":                    "팀 마일스톤",
    "Only manual entry items (postseason, championships, etc.) are shown.":
        "포스트시즌·우승 등 수동 기록 항목만 표시됩니다.",
    "Please select a team and milestone.": "팀과 마일스톤을 선택하세요.",
    "Duplicate":                         "중복",
    "This milestone has already been recorded for this season.":
        "이미 해당 시즌에 기록된 마일스톤입니다.",

    # ── mlb_team_discovery.py ─────────────────────────────────────────────
    "New MLB Teams Discovered":          "새 MLB 팀 발견",
    "New MLB teams (expansion teams, etc.) not in the standard 30 were found in the player stats export.\n\n{teams}\n\nAdd to the tracked team selection list?":
        "player stats export에서 기존 MLB 30개 팀에 없는 신규 MLB 구단(확장 팀 등)이 발견되었습니다.\n\n{teams}\n\n추적 팀 선택 목록에 추가할까요?",

    # ── player_game_log_dialog.py ─────────────────────────────────────────
    "{player_name} — Season {season} Game Log":
        "{player_name} — {season}시즌 경기별 기록",
    "Result":                            "결과",
    "Game-by-Game Log":                  "경기별 기록",
    "Double-click date: open game log HTML": "날짜 더블클릭: 게임 로그 HTML 열기",

    # ── player_milestone_timeline.py ──────────────────────────────────────
    "No milestones achieved yet.":       "아직 달성한 마일스톤이 없습니다.",

    # ── tracked_teams_widget.py ───────────────────────────────────────────
    "Add Custom Team":                   "팀 수동 추가",
    "Abbreviation:":                     "약칭:",
    "Team Name:":                        "팀 이름:",
    "Add":                               "추가",
    "Team Info":                         "팀 정보",
    "All Players (no team filter)":      "전체 선수 (팀 필터 없음)",
    "Add Custom Team...":                "팀 수동 추가…",
    "Remove Selected":                   "선택 제거",
    "Please enter both an abbreviation and a team name.": "약칭과 팀 이름을 모두 입력하세요.",
    "Already Registered":                "이미 등록됨",
    "{abbr} is already in the standard 30 MLB teams.": "{abbr}는 기본 MLB 30개 팀에 포함되어 있습니다.",
    "{abbr} has already been added.":    "{abbr}는 이미 추가된 팀입니다.",

    # ── milestone_definitions_dialog.py ──────────────────────────────────
    "Milestone Definition Management":   "마일스톤 기준 관리",
    "Milestone definitions used for achievement detection.\nFile: {path}":
        "마일스톤 달성 판정에 사용되는 기준 목록입니다.\n파일: {path}",
    "Search by key, name, scope...":     "key·이름·scope 검색...",
    "Display Name":                      "표시 이름",
    "Category":                          "분류",
    "Active":                            "활성",
    "Double-click to edit":              "더블클릭: 수정",
    "Definitions List":                  "기준 목록",
    "Total {total} · Active {active}":   "전체 {total}건 · 활성 {active}건",
    " · Showing {shown}":                " · 표시 {shown}건",
    "Please select a definition to edit.": "수정할 기준을 선택하세요.",
    "Please select a definition to delete.": "삭제할 기준을 선택하세요.",
    "Delete Milestone Definition":       "마일스톤 기준 삭제",
    "'{label}' ({key}) definition will be deleted.\n\nRecorded milestone history will not be deleted.":
        "'{label}' ({key}) 기준을 삭제하시겠습니까?\n\n이미 기록된 마일스톤 이력은 삭제되지 않습니다.",

    # ── milestone_definition_form_dialog.py ──────────────────────────────
    "Edit Milestone Definition":         "마일스톤 기준 수정",
    "Add Milestone Definition":          "마일스톤 기준 추가",
    "(none)":                            "(없음)",
    "Active (used in checker & predictions)": "활성 (체커·예측에 사용)",
    "Category:":                         "분류:",
    "Display Name:":                     "표시 이름:",
    "Track from (remaining):":           "추적 시작 (남은 수):",
    "Near (remaining):":                 "임박 (남은 수):",
    "Description Template:":             "설명 템플릿:",
    "Definition Info":                   "기준 정보",
    "Displays in the prediction list when remaining is at or below this value. Default: 15% of threshold.":
        "목표까지 남은 수치가 이 값 이하일 때 예측 목록에 표시합니다. 기본값: threshold의 15%.",
    "Highlighted as near when remaining is at or below this value. Default: 5% of threshold.":
        "목표까지 남은 수치가 이 값 이하일 때 임박으로 강조합니다. 기본값: threshold의 5%.",

    # ── bulk_rating_table.py ──────────────────────────────────────────────
    "None":                              "미선택",
    "Regional":                          "지역구",
    "National":                          "전국구",
    "Superstar":                         "슈퍼스타",
    "Reg":                               "지역",
    "Nat":                               "전국",
    "Super":                             "슈퍼",
    "English Name":                      "영문명",
    "Prospect":                          "유망주",
    "Base Fame":                         "기본 인지도",
    "Prospect Fame":                     "유망주 인지도",
    "Click to select · Click again to deselect": "클릭으로 선택 · 같은 항목을 다시 클릭하면 미선택",

    # ── table_widgets.py ──────────────────────────────────────────────────
    "Search...":                         "검색...",

    # ── setup_view.py (remaining) ─────────────────────────────────────────
    "Developer Tools":                   "개발 도구",

    # ── bundle_updates.py ─────────────────────────────────────────────────
    "Milestone Criteria":               "마일스톤 기준",
    "Streak Policies":                  "연속기록 정책",
    "Korean Last Name Mappings":        "한글 성 매핑",
    "Korean First Name Mappings":       "한글 이름 매핑",
    "Update Failed":                    "업데이트 실패",
    "Reference File Update":            "기준 파일 업데이트",
    "Reference files merged successfully.": "기준 파일이 병합되었습니다.",

    # ── validation.py ─────────────────────────────────────────────────────
    "Career stats warning: {seasons} season(s) exist in both initial data and boxscores. Career totals may be inflated. Re-import from the Import Existing Records tab, excluding those seasons.":
        "통산 집계 경고: {seasons}시즌이 초기값과 박스스코어에 모두 존재합니다. 통산 수치가 부풀려질 수 있습니다. 기존 기록 가져오기 탭에서 해당 시즌을 제외하고 재임포트하세요.",

    # ── workers ───────────────────────────────────────────────────────────
    "Re-importing boxscore: {filename}": "박스스코어 다시 불러오기: {filename}",
    "Checking milestones...":            "마일스톤 확인 중...",
    "Processing streak records...":      "연속 기록 처리 중...",
    "Updating prediction list...":       "예측 목록 갱신 중...",
    "Re-parsing BATTING notes":          "BATTING 노트 재파싱",
    "(display limit: 5,000 players)":    "(표시 상한 5,000명)",

    # ── bulk_rating_dialog.py ─────────────────────────────────────────────
    "Bulk Rating Editor":                "레이팅 일괄 편집",
    "mlb_rosters / kbo_rosters files not found.":
        "mlb_rosters / kbo_rosters 파일을 찾을 수 없습니다.",
    "No player data in roster.":         "로스터에 선수 데이터가 없습니다.",
    "Apply prospect rating boost (nation filter: applies to that nation only)":
        "유망주 레이팅 증가 적용 (국가 필터 선택 시 해당 국가만)",
    "Reference date: {date} (last import date takes priority)":
        "기준일: {date} (마지막 가져오기 날짜 우선)",
    "Search by name...":                 "이름 검색...",
    "All":                               "전체",
    "Nation":                            "국가",
    "Prospects only":                    "유망주만 보기",
    "Showing {shown:,} / {total:,} players": "표시 {shown:,}명 / 전체 {total:,}명",
    "Options":                           "옵션",
    "Filter":                            "필터",
    "Player List":                       "선수 목록",
    "No rating changes to apply.":       "적용할 레이팅 변경이 없습니다.",
    "Applying... {index}/{total}":       "적용 중... {index}/{total}",
    "Apply and Save":                    "적용 후 저장",

    # ── Milestone view — game log ─────────────────────────────────────────
    "Game log directory is not configured.": "게임 로그 경로가 설정되지 않았습니다.",
    "Game log file not found.":         "게임 로그 파일을 찾을 수 없습니다.",
    "Could not read game log.":         "게임 로그를 읽을 수 없습니다.",
    "No at-bat records for this player in the game log.":
        "해당 선수의 타석 기록이 게임 로그에 없습니다.",
    "Game Log Reference (not auto-filled — for reference only)":
        "게임 로그 참고 (자동 작성 아님 — 참고용)",
    "※ Use this as reference when entering the Description field manually.":
        "※ 위 내용을 참고해 「설명」을 직접 입력하세요.",
    "Game Log":                         "게임 로그",
    "No linked game for this manually entered record.":
        "수동 입력 기록에는 연결된 경기가 없습니다.",
    "File not found:\n{path}":          "파일을 찾을 수 없습니다:\n{path}",

    # ── Transfer event type labels ────────────────────────────────────────
    "FA Contract":                       "FA 계약",
    "Extension Contract":                "연장 계약",
    "Trade":                             "트레이드",
    "Player Purchase":                   "선수 구매",

    # ── manual_entry.py validation errors ────────────────────────────────
    "Please select a team.":             "팀을 선택하세요.",
    "Please enter a season.":            "시즌을 입력하세요.",
    "Please enter games at achievement.": "동안 경기수를 입력하세요.",
    "Please select a transfer type.":    "이적 유형을 선택하세요.",
    "Please enter joining or leaving players.": "합류 또는 이탈 선수를 입력하세요.",
    "Please enter the joining team.":    "합류팀을 입력하세요.",
    "Please enter a player.":            "선수를 입력하세요.",
    "Please enter the injury.":          "부상 내용을 입력하세요.",
    "Please enter the affiliated team.": "소속팀을 입력하세요.",
    "Player not found: {name}":          "선수를 찾을 수 없습니다: {name}",
    "Already recorded career milestone.": "이미 기록된 통산 마일스톤입니다.",
    "Already recorded for this season.": "이미 해당 시즌에 기록된 마일스톤입니다.",
    "Already recorded team milestone for this season.":
        "이미 해당 시즌에 기록된 팀 마일스톤입니다.",
    "Already recorded on the same date.": "이미 같은 날짜에 동일 항목이 있습니다.",
    "No players to record.":             "기록할 선수가 없습니다.",
    "Unsupported transfer type.":        "지원하지 않는 이적 유형입니다.",

    # ── record_edit.py validation errors ─────────────────────────────────
    "Please enter a date.":              "날짜를 입력하세요.",
    "Please check date format.":         "날짜 형식을 확인하세요.",

    # ── definitions.py validation errors ─────────────────────────────────
    "Please enter a key.":               "key를 입력하세요.",
    "Key can only contain letters, numbers, and underscores.":
        "key는 영문·숫자·밑줄만 사용할 수 있습니다.",
    "Key already in use: {key}":         "이미 사용 중인 key입니다: {key}",
    "Invalid category: {category}":      "유효하지 않은 category: {category}",
    "Invalid scope: {scope}":            "유효하지 않은 scope: {scope}",
    "Invalid direction: {direction}":    "유효하지 않은 direction: {direction}",
    "Invalid grade: {grade}":            "유효하지 않은 grade: {grade}",
    "Please enter a display name (label).": "표시 이름(label)을 입력하세요.",
    "Please enter a stat.":              "stat을 입력하세요.",
    "Threshold for boolean must be 1.":  "boolean 기준의 threshold는 1이어야 합니다.",
    "Threshold must be greater than 0.": "threshold는 0보다 커야 합니다.",
    "Unknown description_template: {template}":
        "알 수 없는 description_template: {template}",

    # Streak Center
    "Streak Center":                    "연속기록 센터",
    "Season {season}. Ended and best values are available stored streak records only.":
        "{season}시즌. 종료 및 최고 값은 저장된 연속기록만 표시됩니다.",
    "Active":                           "진행 중",
    "Recent Ended":                     "최근 종료",
    "Player":                           "선수",
    "Team":                             "팀",
    "Type":                             "유형",
    "Value":                            "값",
    "Start":                            "시작",
    "Last":                             "마지막",
    "Date":                             "날짜",
    "Reason":                           "사유",
    "Stored description":               "저장된 설명",
    "Search":                           "검색",
    "Streaks could not be loaded.":      "연속기록을 불러올 수 없습니다.",
    "The database may be unavailable or from an older version.":
        "데이터베이스를 사용할 수 없거나 이전 버전일 수 있습니다.",
    "Stored ended streaks could not be loaded.":
        "저장된 종료 연속기록을 불러올 수 없습니다.",
    "All players":                      "전체 선수",
    "All teams":                        "전체 팀",
    "All types":                        "전체 유형",
    "No active streaks match these filters.":
        "이 필터와 일치하는 진행 중 연속기록이 없습니다.",
    "Import boxscores or clear filters to see active streaks.":
        "진행 중 연속기록을 보려면 박스스코어를 가져오거나 필터를 해제하세요.",
    "No stored ended streak records match these filters.":
        "이 필터와 일치하는 저장된 종료 연속기록이 없습니다.",
    "Ended streaks appear here only after streak events have been stored.":
        "종료 연속기록은 연속기록 이벤트가 저장된 뒤에만 여기에 표시됩니다.",
    "Unknown":                          "알 수 없음",
    "Ended":                            "종료",
    "Milestone":                        "마일스톤",
    "Stored record":                    "저장된 기록",
    "Ended and best values shown here are available stored streak records only.":
        "여기에 표시되는 종료 및 최고 값은 저장된 연속기록만 포함합니다.",
    "IP":                               "이닝",
}
# fmt: on

_KO.update(
    {
        # Phase 1 UI/UX directive: remove leaked English labels in Korean mode.
        "Active Streaks": "진행 중인 연속 기록",
        "Recent Events": "최근 이벤트",
        "Next Milestones": "다음 마일스톤",
        "All Event Types": "모든 이벤트 유형",
        "Automatic": "자동 기록",
        "Official Milestone": "공식 마일스톤",
        "Reset Filters": "필터 초기화",
        "Close": "닫기",
        "Cancel": "취소",
        "Baseline": "기준값",
        "Analyzing": "분석 중",
        "Saving": "저장 중",
        "keep this window open": "이 창을 닫지 마세요",
        "common": "일반",
        "uncommon": "고급",
        "rare": "희귀",
        "epic": "영웅",
        "legendary": "전설",
        "Expand or collapse this section.": "이 섹션을 펼치거나 접습니다.",
    }
)

_KO.update(
    {
        "Import In Progress": "가져오기 진행 중",
        "reloading the application pages": "앱 화면을 다시 불러오는 중",
        "applying settings": "설정을 적용하는 중",
        "closing the application": "앱을 닫는 중",
        "Manual Records": "수동 기록",
        "Add milestone, award, team move, or injury records with guided forms.": "안내 양식으로 마일스톤, 수상, 팀 이동, 부상 기록을 추가합니다.",
        "Open manual record entry": "수동 기록 입력 열기",
        "Complete": "완료",
        "Needed": "필요",
        "Warning": "경고",
        "Running": "진행 중",
        "Not run yet": "아직 실행하지 않음",
        "No issue reported.": "보고된 문제가 없습니다.",
        "Start": "시작",
        "Open": "열기",
        "Result Summary": "결과 요약",
        "No import has run yet.": "아직 실행된 가져오기가 없습니다.",
        "Run an import to see what changed, what was skipped, and what needs review.": "가져오기를 실행하면 변경·건너뜀·검토 필요 항목이 여기에 표시됩니다.",
        "Processed: {items}": "처리됨: {items}",
        "Needs review: {items}": "검토 필요: {items}",
        "No detail counts available.": "세부 건수 정보가 없습니다.",
        "Workflow": "작업 흐름",
        "Each import keeps the same five stages so partial success and errors are traceable.": "모든 가져오기는 같은 5단계를 사용해 부분 성공과 오류를 추적할 수 있습니다.",
        "Check source files": "원본 파일 확인",
        "Confirm the files are present before parsing.": "분석 전에 필요한 파일이 있는지 확인합니다.",
        "Check": "확인",
        "Source": "원본",
        "Analyze and classify": "분석 및 분류",
        "Parse files and group candidate records.": "파일을 분석하고 후보 기록을 묶습니다.",
        "Analyze": "분석",
        "Review differences or extracted records": "차이 또는 추출 기록 검토",
        "Preview what will be saved and what needs review.": "저장될 내용과 검토가 필요한 항목을 미리 봅니다.",
        "Review": "검토",
        "Preview": "미리보기",
        "Save approved changes": "승인된 변경 저장",
        "Apply reviewed changes to the local database.": "검토한 변경을 로컬 데이터베이스에 반영합니다.",
        "Save": "저장",
        "Records": "기록",
        "Confirm result and unresolved items": "결과 및 미해결 항목 확인",
        "Keep completion, partial success, and errors visible on this page.": "완료, 부분 성공, 오류를 이 페이지에 유지합니다.",
        "Confirm": "확인",
        "Issues": "문제 항목",
        "Record Import Center": "기록 가져오기 센터",
        "Choose the import path, review the five-stage status, and keep the final completion, partial-success, or error summary visible on this page.": "가져오기 경로를 선택하고 5단계 상태를 검토한 뒤 완료·부분 성공·오류 요약을 이 페이지에서 확인합니다.",
        "Latest game import": "최신 경기 가져오기",
        "Import recent boxscore HTML and reflect current-season games, milestones, and active streaks.": "최근 박스스코어 HTML을 가져와 현재 시즌 경기, 마일스톤, 진행 중인 연속 기록을 반영합니다.",
        "Source: boxscore HTML files for routine repeated imports.": "원본: 반복 작업용 박스스코어 HTML 파일",
        "News message import": "뉴스 메시지 가져오기",
        "Review messages/messageN.txt extraction before saving awards, injuries, contracts, and milestones.": "수상, 부상, 계약, 마일스톤을 저장하기 전에 messages/messageN.txt 추출 결과를 검토합니다.",
        "Source: messages/messageN.txt with preview, save, and error handling.": "원본: 미리보기·저장·오류 처리를 포함한 messages/messageN.txt",
        "Career and historical season import": "통산 및 과거 시즌 가져오기",
        "Import or compare player_batting_stats.txt and player_pitching_stats.txt for initial setup and offseason refresh.": "초기 설정과 오프시즌 갱신을 위해 player_batting_stats.txt, player_pitching_stats.txt를 가져오거나 비교합니다.",
        "Source: player_batting_stats.txt and player_pitching_stats.txt.": "원본: player_batting_stats.txt 및 player_pitching_stats.txt",
        "Record import completed.": "기록 가져오기가 완료되었습니다.",
        "Record import partially completed. Some items need review.": "기록 가져오기가 부분 완료되었습니다. 일부 항목은 검토가 필요합니다.",
        "Record import stopped: {message}": "기록 가져오기가 중단되었습니다: {message}",
        "View records": "기록 보기",
        "Review issues": "문제 항목 검토",
        "Check errors": "오류 확인",
        "errors": "오류",
        "Import Workflow Status": "가져오기 작업 진행 상태",
        "Use this panel to decide the next safe action before records are changed.": "기록을 변경하기 전에 다음 안전 작업을 이 패널에서 판단합니다.",
        "Check tracked league and teams": "추적 리그와 팀 확인",
        "Current settings": "현재 설정",
        "A league is selected.": "리그가 선택되었습니다.",
        "Select a league before importing records.": "기록을 가져오기 전에 리그를 선택하세요.",
        "Open settings": "설정 열기",
        "Confirm career baseline is current": "통산 기준값 최신 여부 확인",
        "Current season {season}": "현재 시즌 {season}",
        "Baseline files are configured.": "기준 파일이 설정되었습니다.",
        "Import career and historical stats before relying on predictions.": "예측을 사용하기 전에 통산 및 과거 시즌 기록을 가져오세요.",
        "Import baseline": "기준 기록 가져오기",
        "Import center": "가져오기 센터",
        "Import latest boxscores": "최신 박스스코어 가져오기",
        "Boxscore folder is ready.": "박스스코어 폴더가 준비되었습니다.",
        "Configure the boxscore folder first.": "먼저 박스스코어 폴더를 설정하세요.",
        "Scan and review news messages": "뉴스 메시지 스캔 및 검토",
        "Message extraction should be previewed before saving records.": "메시지 추출 결과는 기록 저장 전에 미리 검토해야 합니다.",
        "Open review": "검토 열기",
        "Review ties, exclusions, missing dates, and errors": "동률, 제외, 날짜 누락, 오류 검토",
        "Confirm unresolved import items before considering the data complete.": "데이터를 완료로 보기 전에 미해결 가져오기 항목을 확인하세요.",
        "Review records": "기록 검토",
        "Achievement records": "달성 기록",
        "Finalize season-end records": "시즌 종료 기록 확정",
        "Season {season}": "{season} 시즌",
        "Run final checks after the season ends.": "시즌 종료 후 최종 검사를 실행하세요.",
        "Finalize": "확정",
        "News Message Review": "뉴스 메시지 검토",
        "Approve selected": "선택 항목 승인",
        "Approve all candidates": "모든 후보 승인",
        "Exclude selected": "선택 항목 제외",
        "Reanalyze selected": "선택 항목 재분석",
        "Apply date to selected": "선택 항목에 날짜 적용",
        "Save approved records": "승인 기록 저장",
        "Message title": "메시지 제목",
        "Player/Team": "선수/팀",
        "Status": "상태",
        "Planned records": "저장 예정 기록",
        "Original message": "원본 메시지",
        "Extracted result": "추출 결과",
        "Parsed messages": "분석된 메시지",
        "Candidate": "후보",
        "Approved": "승인됨",
        "Applied": "반영됨",
        "Excluded": "제외됨",
        "Date needed": "날짜 필요",
        "Error": "오류",
        "Common": "일반",
        "Uncommon": "고급",
        "Rare": "희귀",
        "Epic": "영웅",
        "Legendary": "전설",
        "Near": "근접",
        "Monitoring": "관찰 중",
        "Prediction Basis": "예측 근거",
        "Select a prediction to see the calculation basis.": "계산 근거를 보려면 예측 항목을 선택하세요.",
        "Prediction basis is unavailable for this row.": "이 행의 예측 근거를 사용할 수 없습니다.",
        "{player} · {milestone}\nGrade: {grade}\nCurrent {current:,.0f} / Target {target:,.0f} · Remaining {remaining:,.0f}\nBasis: {basis}": "{player} · {milestone}\n등급: {grade}\n현재 {current:,.0f} / 목표 {target:,.0f} · 남은 값 {remaining:,.0f}\n근거: {basis}",
        "Select a player to see role, mode, and source context.": "역할, 보기 모드, 원본 정보를 보려면 선수를 선택하세요.",
        "No player selected.": "선수가 선택되지 않았습니다.",
        "Recent events are shown in the Milestones tab after a player is selected.": "선수를 선택하면 최근 이벤트가 마일스톤 탭에 표시됩니다.",
        "Team unknown": "팀 알 수 없음",
        "Position unknown": "포지션 알 수 없음",
        "ID {player_id} · {team} · {position} · {mode} view": "ID {player_id} · {team} · {position} · {mode} 보기",
        "Streak Records": "연속 기록",
        "Season {season}. Active streaks and recently ended streaks are reviewed in one page.": "{season} 시즌. 진행 중인 연속 기록과 최근 종료 기록을 한 페이지에서 검토합니다.",
        "Filters": "필터",
        "Search player, team, type, or reason": "선수, 팀, 유형, 사유 검색",
        "Check the database and try again.": "데이터베이스를 확인한 뒤 다시 시도하세요.",
        "Import boxscores or clear filters.": "박스스코어를 가져오거나 필터를 초기화하세요.",
        "Ended streaks appear after streak events are stored.": "연속 기록 이벤트가 저장되면 종료 기록이 표시됩니다.",
        "Advanced Tools": "고급 도구",
        "Re-import Individual Boxscores": "개별 박스스코어 다시 가져오기",
        "Remove Spring Training Games": "스프링캠프 경기 제거",
        "Recover Regular Season Games": "정규 시즌 경기 복구",
        "Maintenance and recovery": "유지보수 및 복구",
        "Individual boxscore re-import": "개별 박스스코어 재가져오기",
        "Re-run a selected boxscore when a single source file needs repair.": "단일 원본 파일을 고쳐야 할 때 선택한 박스스코어를 다시 실행합니다.",
        "Spring training cleanup": "스프링캠프 정리",
        "Remove spring training games from tracked data without presenting it as normal import.": "스프링캠프 경기를 일반 가져오기처럼 보이지 않게 추적 데이터에서 제거합니다.",
        "Regular season recovery": "정규 시즌 복구",
        "Scan for regular season games that may have been skipped after cleanup.": "정리 후 누락됐을 수 있는 정규 시즌 경기를 스캔합니다.",
        "Refresh Status": "상태 새로고침",
        "Full DB Reset": "전체 DB 초기화",
        "Danger zone": "위험 구역",
        "Select a league to view DB status.": "DB 상태를 보려면 리그를 선택하세요.",
        "No saved game, milestone, or initial stats data.": "저장된 경기, 마일스톤, 초기 기록 데이터가 없습니다.",
        "League Required": "리그 필요",
        "Please select a league to re-import first.": "다시 가져올 리그를 먼저 선택하세요.",
        "Please select a league first.": "리그를 먼저 선택하세요.",
        "Path Required": "경로 필요",
        "Box score folder is not set.": "박스스코어 폴더가 설정되지 않았습니다.",
        "Removed {count} spring training games.": "스프링캠프 경기 {count}건을 제거했습니다.",
        "Scanning...": "스캔 중...",
        "Recovered {count} regular season games.": "정규 시즌 경기 {count}건을 복구했습니다.",
        "Recovery Failed": "복구 실패",
        "Current save": "현재 저장",
        "Confirm Full DB Reset": "전체 DB 초기화 확인",
        "Type the save name exactly to reset its app database:\n{save_name}": "앱 데이터베이스를 초기화하려면 저장 이름을 정확히 입력하세요:\n{save_name}",
        "Reset Cancelled": "초기화 취소됨",
        "Save name did not match. Nothing was deleted.": "저장 이름이 일치하지 않아 삭제하지 않았습니다.",
        "No saved data": "저장된 데이터 없음",
        "Reset Data": "데이터 초기화",
        "Reset Failed": "초기화 실패",
        "Reset Complete": "초기화 완료",
        "Current save data has been reset.": "현재 저장 데이터가 초기화되었습니다.",
    }
)

_TRANSLATIONS: dict[str, dict[str, str]] = {"ko": _KO}


def set_language(lang: str) -> None:
    global _language
    _language = lang.lower()


def get_language() -> str:
    return _language


def tr(text: str) -> str:
    if _language == "en":
        return text
    return _TRANSLATIONS.get(_language, {}).get(text, text)


def _parse_iso(iso_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def format_relative_datetime(iso_str: str | None) -> str:
    """Today HH:mm / Yesterday HH:mm / YYYY-MM-DD HH:mm / '-' for empty."""
    if not iso_str:
        return "-"
    dt = _parse_iso(iso_str)
    if dt is None:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str
    today = datetime.now().date()
    time_str = dt.strftime("%H:%M")
    if dt.date() == today:
        return tr("Today {time}").format(time=time_str)
    if dt.date() == today - timedelta(days=1):
        return tr("Yesterday {time}").format(time=time_str)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_full_datetime(iso_str: str | None) -> str:
    """Full timestamp for tooltips; '' for empty/unparseable values."""
    if not iso_str:
        return ""
    dt = _parse_iso(iso_str)
    if dt is None:
        return iso_str
    return dt.strftime("%Y-%m-%d %H:%M:%S")
