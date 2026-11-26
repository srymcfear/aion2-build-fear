import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_FILE = ROOT / "members.json"
DATA_DIR = ROOT / "data"
META_FILE = DATA_DIR / "meta.json"


def extract_page_data(page):
    """Extract live CP, iLvl, Avatar, Soul Resonance, and item scores from rendered DOM."""
    return page.evaluate(
        """() => {
            const text = document.body.innerText.replace(/\\r/g, '');
            const avatarEl = document.querySelector('img[src*="/img/p/"]');
            const avatar = avatarEl ? avatarEl.src : null;

            const cpMatch = text.match(/COMBAT POWER[\\s\\S]{0,60}?([\\d,]{5,})/i);
            const ilvlMatch = text.match(/ITEM LEVEL[\\s\\S]{0,60}?([\\d,]{3,})/i);

            const srBlock = text.match(/SOUL RESONANCE[\\s\\S]{0,240}/i);
            let score = null, tier = null, pot = null;
            if (srBlock) {
                const s1 = srBlock[0].match(/(\\d{1,3})\\s+(Dormant|Stirring|Strong|Radiant)/i);
                if (s1) {
                    score = parseInt(s1[1], 10);
                    tier = s1[2];
                }
            }
            if (score === null) {
                const s2 = text.match(/(\\d{1,3})\\s+(Dormant|Stirring|Strong|Radiant)\\s+SOUL RESONANCE/i);
                if (s2) {
                    score = parseInt(s2[1], 10);
                    tier = s2[2];
                }
            }
            const potMatch = text.match(/(\\d{1,3})\\s+within reach/i);
            if (potMatch) pot = parseInt(potMatch[1], 10);

            // Extract gear piece scores (e.g., "46 Stirring", "94 Radiant")
            const gearScores = [];
            const gearMatches = text.matchAll(/^(.+?)\\n(?:Main hand|Off hand|Helmet|Shoulders|Torso|Pants|Gloves|Boots|Cape|Necklace|Earring|Ring|Bracelet).*?\\n(\\d{1,3}\\s+(?:Dormant|Stirring|Strong|Radiant))/gm);
            for (const gm of gearMatches) {
                gearScores.push({ name: gm[1].trim(), score: gm[2].trim() });
            }

            return {
                avatar,
                cp: cpMatch ? cpMatch[1] : null,
                ilvl: ilvlMatch ? ilvlMatch[1] : null,
                score,
                tier,
                pot,
                gearScores
            };
        }"""
    )


def main():
    DATA_DIR.mkdir(exist_ok=True)
    config = json.loads(MEMBERS_FILE.read_text(encoding="utf-8"))
    meta = json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.exists() else {"AVATARS": {}, "ICONS": {}, "SKILL_ICONS": {}}

    server = config.get("server", "zikel")
    region = config.get("region", "as")
    members = config.get("members", [])
    meta["members"] = members

    success_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        for name in members:
            member_file = DATA_DIR / f"{name}.json"
            entry = json.loads(member_file.read_text(encoding="utf-8")) if member_file.exists() else {"name": name}
            base_url = f"https://aion2index.com/c/{region}/{server}/{name}/upgrades"
            print(f"Fetching {name}...")

            try:
                # 1. PvE Meta
                page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector("text=/Soul Resonance/i", timeout=30000)
                page.wait_for_timeout(1500)
                pve = extract_page_data(page)

                if pve.get("avatar"):
                    meta.setdefault("AVATARS", {})[name] = pve["avatar"]
                if pve.get("cp"):
                    entry["cp"] = pve["cp"]
                if pve.get("ilvl"):
                    entry["ilvl"] = pve["ilvl"]

                pve_block = entry.setdefault("pve", {})
                if pve.get("score") is not None:
                    pve_block["score"] = pve["score"]
                if pve.get("tier"):
                    pve_block["tier"] = pve["tier"]
                if pve.get("pot") is not None:
                    pve_block["pot"] = pve["pot"]

                # Sync gear scores if matched
                if pve.get("gearScores") and entry.get("gear"):
                    for gs in pve["gearScores"]:
                        for g in entry["gear"]:
                            if g["name"].lower().startswith(gs["name"].lower()):
                                g["score"] = gs["score"]
                                break

                # 2. PvP Meta
                page.goto(f"{base_url}?meta=pvp", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector("text=/Soul Resonance/i", timeout=30000)
                page.wait_for_timeout(1500)
                pvp = extract_page_data(page)

                if pvp.get("cp"):
                    entry["cpPvp"] = pvp["cp"]
                if pvp.get("ilvl"):
                    entry["ilvlPvp"] = pvp["ilvl"]

                pvp_block = entry.setdefault("pvp", {})
                if pvp.get("score") is not None:
                    pvp_block["score"] = pvp["score"]
                if pvp.get("tier"):
                    pvp_block["tier"] = pvp["tier"]
                if pvp.get("pot") is not None:
                    pvp_block["pot"] = pvp["pot"]

                if pve.get("score") is None and pvp.get("score") is None:
                    raise ValueError("Extracted empty Soul Resonance for both PvE and PvP")

                member_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                success_count += 1
                print(
                    f"  OK: CP={entry.get('cp')} | iLvl={entry.get('ilvl')} | "
                    f"PvE={pve_block.get('score')} ({pve_block.get('tier')}) -> {pve_block.get('pot')} | "
                    f"PvP={pvp_block.get('score')} ({pvp_block.get('tier')}) -> {pvp_block.get('pot')}"
                )
            except Exception as exc:
                print(f"  ERROR: Failed to update {name}: {exc}")

        browser.close()

    if success_count == 0:
        print("FATAL: No members were updated successfully.")
        sys.exit(1)

    vn_tz = timezone(timedelta(hours=7))
    meta["updatedAt"] = datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M (UTC+7)")
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved data/meta.json at {meta['updatedAt']} ({success_count}/{len(members)} members updated)")


if __name__ == "__main__":
    main()
