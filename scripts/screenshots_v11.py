"""v11 screenshots at 1280x800: live, AI room (handoffs + chaos), stats (ball metrics), tactics, league.
python scripts/screenshots_v11.py <url> [out] [prefix]"""
import sys
import time
from playwright.sync_api import sync_playwright
base, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
pre = sys.argv[3] if len(sys.argv) > 3 else "v11"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base, wait_until="networkidle")
    time.sleep(1.5)
    pg.select_option("#match", "58")
    time.sleep(2)
    pg.click('#speed button[data-v="40"]')
    pg.click("#go")
    time.sleep(25)
    pg.screenshot(path=f"{out}/{pre}-live.png")
    pg.click('#tabs button[data-p="agents"]')
    time.sleep(1)
    pg.select_option("#chaossev", "hard")
    pg.click("#chaosbtn")
    time.sleep(3)
    pg.screenshot(path=f"{out}/{pre}-chaos.png")
    pg.click('#tabs button[data-p="stats"]')
    time.sleep(1.5)
    pg.screenshot(path=f"{out}/{pre}-stats.png")
    pg.evaluate("document.getElementById('ballrec')?.scrollIntoView()")
    time.sleep(0.5)
    pg.screenshot(path=f"{out}/{pre}-ball-metrics.png")
    pg.click('#tabs button[data-p="tactics"]')
    time.sleep(2)
    pg.screenshot(path=f"{out}/{pre}-tactics.png")
    pg.click('.views button[data-v="league"]')
    time.sleep(3)
    pg.screenshot(path=f"{out}/{pre}-league.png")
    print("errors:", errs)
    b.close()
