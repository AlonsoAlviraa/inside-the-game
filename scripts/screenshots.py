"""UI screenshots + goal-sync check with headless Chrome.
usage: python scripts/screenshots.py <base_url> [out_dir] [--watch SEED]
Screens at 1280x800 and 1920x1080 (100% zoom). --watch plays a full match at 'Fast' and verifies that every goal
banner, scoreboard, timeline marker and commentary line agree with the event data."""
import json, sys, time, urllib.request
from playwright.sync_api import sync_playwright

base = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "docs/screenshots"
watch = int(sys.argv[sys.argv.index("--watch") + 1]) if "--watch" in sys.argv else None


def shot(pg, name):
    pg.screenshot(path=f"{out}/{name}.png")
    print("saved", name)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
    errs = []
    if watch is not None:
        evs = json.load(urllib.request.urlopen(f"{base}/api/match?seed={watch}"))["events"]
        goals = [e for e in evs if e["type"] == "goal"]
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base, wait_until="networkidle")
        pg.select_option("#match", str(watch))
        time.sleep(2)
        pg.click('#speed button[data-v="40"]')
        pg.click("#go")
        seen, t0 = [], time.time()
        while time.time() - t0 < 600 and not pg.is_visible("#ft.on"):
            if pg.is_visible("#goal.on"):
                st = pg.evaluate("""()=>({banner:document.getElementById('gscore').textContent,scorer:document.getElementById('gscorer').textContent,
                    board:document.getElementById('score').textContent,clock:document.getElementById('clock').textContent,
                    feedTop:document.querySelector('#feed li .ti').textContent,marks:document.querySelectorAll('.tl').length})""")
                if not seen or seen[-1]["banner"] != st["banner"]:
                    seen.append(st)
                    if len(seen) == 1:
                        shot(pg, "1920-goal-moment")
                time.sleep(0.2)
            else:
                time.sleep(0.25)
        ok = len(seen) == len(goals)
        for g, s in zip(goals, seen):
            h, a = list(g["score"].values())
            exp_board = f"{h} – {a}"
            good = s["board"] == exp_board and g["player"] in s["scorer"] and s["clock"] == f"{g['minute']}'" and str(h) in s["banner"]
            ok &= good
            print("goal", g["minute"], g["player"], exp_board, "->", s, "OK" if good else "MISMATCH")
        print("WATCH RESULT", "PASS" if ok else "FAIL", f"{len(seen)}/{len(goals)} goals", "errors:", errs)
        time.sleep(3)
        shot(pg, "1920-full-time-report")
        pg.close()
    for w, h in ((1280, 800), (1920, 1080)):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base, wait_until="networkidle")
        time.sleep(2)
        shot(pg, f"{w}-01-landing")
        pg.click('#speed button[data-v="40"]')
        pg.click("#go")
        time.sleep(40)
        pg.evaluate("window.scrollTo(0, document.querySelector('.controls').offsetTop-70)")
        time.sleep(1)
        shot(pg, f"{w}-02-match-centre")
        for t in ("win", "mom", "stats", "tactics", "compare", "agents", "ask"):
            pg.click(f'#tabs button[data-p="{t}"]')
            if t == "ask":
                pg.click("#sugg button")
                pg.wait_for_selector("#chat .msg small", timeout=90000)
            time.sleep(2)
            pg.evaluate("document.getElementById('tabs').scrollIntoView()")
            time.sleep(0.5)
            shot(pg, f"{w}-03-{t}")
        pg.click('#tabs button[data-p="preview"]')
        time.sleep(1)
        pg.evaluate("document.getElementById('tabs').scrollIntoView()")
        shot(pg, f"{w}-03-preview")
        pg.click('nav .views button[data-v="league"]')
        time.sleep(3)
        pg.evaluate("window.scrollTo(0, document.querySelector('main').offsetTop-70)")
        shot(pg, f"{w}-04-league")
        pg.close()
    print("page errors:", errs)
    b.close()
