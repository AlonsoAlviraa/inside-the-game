"""v9 screenshots: league, team page, pre-match. python scripts/screenshots_v9.py <url> [out]"""
import sys, time
from playwright.sync_api import sync_playwright
base, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for w, h in ((1280, 800), (1920, 1080)):
        pg = b.new_page(viewport={"width": w, "height": h}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base, wait_until="networkidle"); time.sleep(1)
        pg.select_option("#match", "1203"); time.sleep(3)
        pg.click('#tabs button[data-p="preview"]'); time.sleep(1.5)
        pg.screenshot(path=f"{out}/v9-{w}-prematch.png")
        pg.click('.views button[data-v="league"]'); time.sleep(3)
        pg.hover('.trow[data-t="falcons"]'); time.sleep(0.5)
        pg.screenshot(path=f"{out}/v9-{w}-league.png")
        pg.click('.trow[data-t="falcons"]'); time.sleep(2)
        pg.screenshot(path=f"{out}/v9-{w}-team.png")
        print(w, "errors:", errs)
        pg.close()
    b.close()
