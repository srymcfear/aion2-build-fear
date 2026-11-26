import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_FILE = ROOT / "members.json"
DATA_FILE = ROOT / "data.json"


def extract_meta_stats(page):
    """Extract live CP, iLvl, Avatar, Soul Resonance score/tier/potential from rendered DOM."""
    return page.evaluate(
        """() => {
            const text = document.body.innerText;
            const avatarEl = document.querySelector('img[src*="/img/p/"]');
            const avatar = avatarEl ? avatarEl.src : null;

            // Combat Power & Item Level
            const cpMatch = text.match(/COMBAT POWER\\s*\\n\\s*([\\d,]+)/i);
            const ilvlMatch = text.match(/ITEM LEVEL\\s*\\n\\s*([\\d,]+)/i);

            // Soul Resonance
            const srMatch = text.match(/(\\d+)\\s+(Dormant|Stirring|Strong|Radiant)\\s+SOUL RESONANCE/i)
                         || text.match(/SOUL RESONANCE[\\s\\S]{0,120}?(\\d+)\\s+(Dormant|Stirring|Strong|Radiant)/i);
            const potMatch = text.match(/(\\d+)\\s+within reach/i);

            return {
                avatar,
                cp: cpMatch ? cpMatch[1] : null,
                ilvl: ilvlMatch ? ilvlMatch[1] : null,
                score: srMatch ? parseInt(srMatch[1], 10) : null,
                tier: srMatch ? srMatch[2] : null,
                pot: potMatch ? parseInt(potMatch[1], 10) : null,
            };
        }"""
    )


def main():
    config = json.loads(MEMBERS_FILE.read_text(encoding="utf-8"))
    data = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {"DB": {}, "AVATARS": {}, "ICONS": {}, "SKILL_ICONS": {}}

    server = config.get("server", "zikel")
    region = config.get("region", "as")
    members = config.get("members", [])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        for name in members:
            base_url = f"https://aion2index.com/c/{region}/{server}/{name}/upgrades"
            print(f"Fetching {name}...")
            try:
                # 1. PvE Meta
                page.goto(base_url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(1500)
                pve_stats = extract_meta_stats(page)

                if pve_stats.get("avatar"):
                    data.setdefault("AVATARS", {})[name] = pve_stats["avatar"]

                entry = data.setdefault("DB", {}).setdefault(name, {"name": name})
                if pve_stats.get("cp"):
                    entry["cp"] = pve_stats["cp"]
                if pve_stats.get("ilvl"):
                    entry["ilvl"] = pve_stats["ilvl"]

                pve_block = entry.setdefault("pve", {})
                if pve_stats.get("score") is not None:
                    pve_block["score"] = pve_stats["score"]
                if pve_stats.get("tier"):
                    pve_block["tier"] = pve_stats["tier"]
                if pve_stats.get("pot") is not None:
                    pve_block["pot"] = pve_stats["pot"]

                # 2. PvP Meta
                page.goto(f"{base_url}?meta=pvp", wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(1500)
                pvp_stats = extract_meta_stats(page)

                if pvp_stats.get("cp"):
                    entry["cpPvp"] = pvp_stats["cp"]
                if pvp_stats.get("ilvl"):
                    entry["ilvlPvp"] = pvp_stats["ilvl"]

                pvp_block = entry.setdefault("pvp", {})
                if pvp_stats.get("score") is not None:
                    pvp_block["score"] = pvp_stats["score"]
                if pvp_stats.get("tier"):
                    pvp_block["tier"] = pvp_stats["tier"]
                if pvp_stats.get("pot") is not None:
                    pvp_block["pot"] = pvp_stats["pot"]

                print(f"  OK: PvE={pve_block.get('score')} ({pve_block.get('tier')}), PvP={pvp_block.get('score')} ({pvp_block.get('tier')})")
            except Exception as exc:
                print(f"  WARN: Failed to update {name}: {exc}")

        browser.close()

    vn_tz = timezone(timedelta(hours=7))
    data["updatedAt"] = datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M (UTC+7)")
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved updated data.json at", data["updatedAt"])


if __name__ == "__main__":
    main()
