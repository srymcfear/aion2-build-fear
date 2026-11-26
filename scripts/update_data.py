import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_FILE = ROOT / "members.json"
DATA_DIR = ROOT / "data"
META_FILE = DATA_DIR / "meta.json"


def extract_page_data(page):
    """Extract live CP, iLvl, Avatar, Soul Resonance, and Gear ratings from rendered DOM."""
    return page.evaluate(
        """() => {
            const text = document.body.innerText.replace(/\\r/g, '');
            const avatarEl = document.querySelector('img[src*="/img/p/"]');
            const avatar = avatarEl ? avatarEl.src : null;

            const cpMatch = text.match(/COMBAT POWER[\\s\\S]{0,60}?([\\d,]{5,})/i);
            const ilvlMatch = text.match(/ITEM LEVEL[\\s\\S]{0,60}?([\\d,]{3,})/i);

            // Match Soul Resonance block specifically
            const srBlock = text.match(/SOUL RESONANCE[\\s\\S]{0,200}/i);
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

            return {
                avatar,
                cp: cpMatch ? cpMatch[1] : null,
                ilvl: ilvlMatch ? ilvlMatch[1] : null,
                score,
                tier,
                pot
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
                page.wait_for_selector("text=SOUL RESONANCE", timeout=25000)
                page.wait_for_timeout(1200)
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

                # 2. PvP Meta
                page.goto(f"{base_url}?meta=pvp", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector("text=SOUL RESONANCE", timeout=25000)
                page.wait_for_timeout(1200)
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

                member_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  OK: CP={entry.get('cp')} | PvE={pve_block.get('score')} ({pve_block.get('tier')}) -> {pve_block.get('pot')} | PvP={pvp_block.get('score')} ({pvp_block.get('tier')}) -> {pvp_block.get('pot')}")
            except Exception as exc:
                print(f"  WARN: Failed to update {name}: {exc}")

        browser.close()

    vn_tz = timezone(timedelta(hours=7))
    meta["updatedAt"] = datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M (UTC+7)")
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved data/meta.json at", meta["updatedAt"])


if __name__ == "__main__":
    main()
