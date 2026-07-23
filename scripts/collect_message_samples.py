"""Collect curated OOTP message samples from a save into tests/fixtures/messages/."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "tests" / "fixtures" / "messages"
SAVE_NAME = "SuperYukies_V1.0.lg"

# Hand-picked samples from SuperYukies_V1.0.lg (verified message content).
# Note: OOTP uses "Great Glove" / "Platinum Stick" (not Gold Glove / Silver Slugger).
# Release / waiver news is omitted — those events do not produce reliable inbox messages.
MANUAL_PICKS: dict[str, list[tuple[str, str]]] = {
    # category -> [(source_file, note)]
    "trade_multi_player": [
        ("message1433.txt", "3-for-1 트레이드, In return 구문"),
        ("message1487.txt", "현금 포함 다자 트레이드"),
    ],
    "trade_simple": [
        ("message1435.txt", "1-for-1 트레이드"),
        ("message1477.txt", "2명 트레이드"),
    ],
    "trade_deadline_news": [
        ("message506.txt", "트레이드 데드라인 안내 (이벤트 자체는 마일스톤 아님)"),
    ],
    "injury_game": [
        ("message410.txt", "햄스트링, 3주 결장"),
        ("message1007.txt", "UCL 파열, 시즌 아웃"),
        ("message816.txt", "경기 중 발목 염좌, 1주 결장"),
    ],
    "injury_offfield": [
        ("message22.txt", "계단 넘어짐"),
        ("message179.txt", "훈련 중 부상"),
    ],
    "fa_signing_mlb": [
        ("message5095.txt", "MLB FA 계약 체결"),
        ("message5338.txt", "FA 영입 발표"),
    ],
    "fa_signing_minor": [
        ("message4968.txt", "마이너 FA 계약"),
    ],
    "contract_extension": [
        ("message114.txt", "15년 연장 계약"),
        ("message2396.txt", "MLB 연장 계약 ($72M / 4년)"),
        ("message9788.txt", "클로저 연장 계약"),
    ],
    "award_mvp": [
        ("message4841.txt", "AL MVP (Nick Kurtz)"),
        ("message4842.txt", "NL MVP (Do-young Kim, 2026)"),
        ("message10062.txt", "NL MVP (Do-young Kim, 2027)"),
    ],
    "award_cy_young": [
        ("message4834.txt", "AL CY Young 2026 (Tarik Skubal)"),
        ("message4835.txt", "NL CY Young 2026 (Freddy Peralta)"),
        ("message10058.txt", "NL CY Young 2027 (Dong-joo Moon)"),
    ],
    "award_great_glove": [
        ("message4802.txt", "AL Great Glove (골드글러브 대체명)"),
        ("message4803.txt", "NL Great Glove"),
        ("message4393.txt", "마이너 Great Glove (PIO)"),
    ],
    "award_platinum_stick": [
        ("message4820.txt", "AL Platinum Stick (실버슬러거 대체명)"),
        ("message4821.txt", "NL Platinum Stick"),
        ("message3152.txt", "마이너 Platinum Stick (FCL)"),
    ],
    "award_rookie_of_year": [
        ("message4324.txt", "리그 ROY 수상"),
        ("message4447.txt", "투수 ROY"),
    ],
    "award_batter_of_month": [
        ("message771.txt", "AL Batter of the Month (Judge)"),
        ("message772.txt", "NL Batter of the Month (Kim)"),
    ],
    "award_pitcher_of_month": [
        ("message773.txt", "AL Pitcher of the Month"),
        ("message774.txt", "NL Pitcher of the Month"),
    ],
    "award_rookie_of_month": [
        ("message809.txt", "신인 월간 수상"),
    ],
    "award_all_star_selection": [
        ("message2280.txt", "MLB 올스타 로스터 발표"),
        ("message1049.txt", "MLB 올스타 투표 시작"),
    ],
    "postseason_wildcard": [
        ("message4235.txt", "와일드카드 진출 확정 (Astros)"),
    ],
    "postseason_playoff_clinch": [
        ("message4335.txt", "플레이오프 진출 확정 (Brewers)"),
    ],
    "postseason_division": [
        ("message4202.txt", "AL West 디비전 우승 (Mariners)"),
        ("message4325.txt", "AL East 디비전 우승 (Orioles)"),
        ("message9587.txt", "NL East 디비전 우승 (Mets)"),
    ],
    "postseason_world_series": [
        ("message9924.txt", "WS 우승 — Seoul Yukies Sweep Tigers"),
    ],
    "retirement": [
        ("message441.txt", "은퇴 발표"),
    ],
    "hall_of_fame": [
        ("message5327.txt", "HOF 헌액 (당선)"),
        ("message5056.txt", "HOF 투표 시작"),
    ],
}

# Intentionally omitted: player_release / player_purchase / waiver
# — OOTP inbox does not emit reliable news for those events.
UNAVAILABLE_IN_SAVE: dict[str, str] = {
    "player_release": "방출/DFA는 인박스 뉴스로 나오지 않음 (의도적 제외)",
    "player_purchase": "선수 구매/웨이버 클레임은 인박스 뉴스로 나오지 않음 (의도적 제외)",
}


def find_save() -> Path:
    onedrive = Path(os.environ["USERPROFILE"]) / "OneDrive"
    matches = list(
        onedrive.glob(
            f"*/Out of the Park Developments/OOTP Baseball 27/saved_games/{SAVE_NAME}"
        )
    )
    if matches:
        return matches[0]
    for root, _dirs, _files in os.walk(onedrive):
        if root.endswith(SAVE_NAME) and "saved_games" in root:
            return Path(root)
    raise FileNotFoundError(f"Save not found: {SAVE_NAME}")


def main() -> None:
    save = find_save()
    msg_dir = save / "messages"
    all_msgs = list(msg_dir.glob("message*.txt"))

    if OUT_DIR.exists():
        for path in OUT_DIR.glob("*.txt"):
            path.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "source_save": SAVE_NAME,
        "source_path_hint": str(save),
        "total_messages_in_save": len(all_msgs),
        "naming_notes": {
            "great_glove": "OOTP 인게임 명칭 — 기존 Gold Glove에 해당",
            "platinum_stick": "OOTP 인게임 명칭 — 기존 Silver Slugger에 해당",
        },
        "categories": {},
        "unavailable_in_save": UNAVAILABLE_IN_SAVE,
    }

    total = 0
    for category, picks in MANUAL_PICKS.items():
        samples: list[dict[str, str]] = []
        for idx, (source_name, note) in enumerate(picks, start=1):
            src = msg_dir / source_name
            if not src.exists():
                raise FileNotFoundError(f"Missing source message: {src}")
            text = src.read_text(encoding="utf-8", errors="replace")
            title = text.split("\n", 1)[0].strip()
            dest_name = f"{category}_{idx:02d}.txt"
            shutil.copy2(src, OUT_DIR / dest_name)
            samples.append(
                {
                    "fixture_file": dest_name,
                    "source_file": source_name,
                    "title": title,
                    "note": note,
                }
            )
            total += 1
        manifest["categories"][category] = {"count": len(samples), "samples": samples}

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {total} fixtures to {OUT_DIR}")
    for category, picks in MANUAL_PICKS.items():
        print(f"  {category}: {len(picks)}")


if __name__ == "__main__":
    main()
