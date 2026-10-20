"""Capture UI screenshots with headless Chrome: python scripts/screenshots.py [base_url] [out_dir]"""
import sys, time
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
out = sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    pg.goto(base, wait_until="networkidle")
    pg.screenshot(path=f"{out}/01-hero.png")
    pg.click('#speed button[data-v="40"]')
    pg.click("#go")
    pg.wait_for_selector("#feed li:not(.empty)", timeout=180000)
    time.sleep(45)
    pg.evaluate("window.scrollTo(0, document.getElementById('app').offsetTop)")
    time.sleep(1)
    pg.screenshot(path=f"{out}/02-live-room.png")
    for tab, name in (("agents", "03-agents-observability"), ("stats", "04-stats"), ("hl", "05-highlights")):
        pg.click(f'.tabs button[data-p="{tab}"]')
        time.sleep(1.5)
        pg.screenshot(path=f"{out}/{name}.png")
    pg.click('.tabs button[data-p="ask"]')
    pg.click("#sugg button")
    time.sleep(1)
    pg.wait_for_selector("#chat .msg small", timeout=90000)
    time.sleep(3)
    pg.evaluate("window.scrollTo(0, document.getElementById('app').offsetTop)")
    time.sleep(1)
    pg.screenshot(path=f"{out}/06-ask-the-analyst.png")
    pg.goto(base, wait_until="networkidle")
    pg.click("text=Jump to full-time report")
    pg.wait_for_selector("#ftbody h2", timeout=120000)
    time.sleep(1)
    pg.screenshot(path=f"{out}/07-full-time-report.png")
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    m.goto(base + "/#app", wait_until="networkidle")
    time.sleep(1)
    m.screenshot(path=f"{out}/08-mobile.png")
    b.close()
print("ok")
