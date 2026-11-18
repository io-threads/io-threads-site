# Run: python3 .ci/iolin_usertest.py [url] [out-dir]   (default url = live site; headless Chromium has no WebGPU, so it uses demo mode)
"""User test of io-threads.com/iolin/ as a new visitor ("Riley Test"). Headless Chromium has no WebGPU,
so real-model paths are checked for a graceful fallback and everything else runs in demo mode."""
import json, sys, pathlib, re
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://io-threads.com/iolin/"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".")
R = []
def check(area, name, ok, ev=""):
    R.append((area, name, bool(ok), str(ev)[:160])); print(("PASS" if ok else "FAIL"), area, "|", name, "|", str(ev)[:160])

def term(pg): return pg.inner_text("#termPane")
def cmd(pg, c, wait=900):
    if not pg.is_visible("#cmd"):
        if pg.is_visible('[data-t="term"]'): pg.click('[data-t="term"]')
        else: pg.click('.tab[data-v="live"]')
        pg.wait_for_timeout(300)
        if not pg.is_visible("#cmd") and pg.is_visible('[data-t="term"]'): pg.click('[data-t="term"]'); pg.wait_for_timeout(200)
    before = len(term(pg)); pg.fill("#cmd", c); pg.press("#cmd", "Enter"); pg.wait_for_timeout(wait)
    return term(pg)[before:]

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:150]))
    pg.on("dialog", lambda d: d.accept())

    # 1. First visit: the tour
    pg.goto(URL + "?welcome=1", wait_until="networkidle"); pg.wait_for_timeout(1500)
    check("tour", "step 1 welcome shows on first visit", pg.is_visible("#tName"), "")
    pg.fill("#tName", "Riley Test"); pg.click("#tGo"); pg.wait_for_timeout(1200)
    coach = pg.inner_text("#coach") if pg.query_selector("#coach") else ""
    check("tour", "step 2 device check explains no WebGPU and offers demo", re.search(r"demo", coach, re.I) and pg.query_selector("#tDemo, #tDemo2"), coach.replace("\n", " ")[:150])
    pg.click("#tDemo" if pg.query_selector("#tDemo") else "#tDemo2"); pg.wait_for_timeout(1500)
    q = pg.input_value("#tQ") if pg.query_selector("#tQ") else ""
    check("tour", "step 4 question pre-filled", "leave this device" in q, q)
    pg.click("#tAsk"); pg.wait_for_timeout(5000)
    pg.wait_for_selector("#tVer:not([disabled])", timeout=15000)
    pg.click("#tVer"); pg.wait_for_timeout(1500)
    c5 = term(pg)
    check("tour", "step 5 Verify shows VALID", "VALID" in c5.split("verify")[-1] and "Verified" in pg.inner_text("#coach"), c5.replace("\n", " ")[-120:])
    pg.wait_for_selector("#tTam:not([disabled])", timeout=5000); pg.click("#tTam"); pg.wait_for_timeout(1500)
    c5 = term(pg)
    check("tour", "step 5 'Edit one word' shows INVALID", "INVALID" in c5, c5.replace("\n", " ")[-120:])
    pg.click("#tDone"); pg.wait_for_timeout(1000)
    check("tour", "tour ends in Instruct", pg.is_visible("#p-instruct"), "")
    check("tour", "?welcome=1 removed from URL", "welcome" not in pg.url, pg.url)
    title = pg.inner_text("#tUser")
    check("identity", "titlebar personalised with the name", "riley" in title.lower(), title.replace("\n", " ")[:120])
    pg.screenshot(path=str(OUT / "ut-01-after-tour.png"))

    # 2. Terminal commands
    pg.click('[data-t="term"]'); pg.wait_for_timeout(300)
    o = cmd(pg, "help"); check("terminal", "help lists commands", all(k in o for k in ("model", "ask", "verify", "tamper", "export")), o[:120])
    o = cmd(pg, "status"); check("terminal", "status reports model/device/storage", len(o.strip()) > 20, o.replace("\n", " ")[:150])
    o = cmd(pg, "model list"); check("terminal", "model list shows the 4 curated models", sum(k in o for k in ("0.6B", "1B", "3B", "8B")) >= 3, o.replace("\n", " ")[:150])
    o = cmd(pg, "model load small", 2500); check("terminal", "model load without WebGPU fails gracefully (no crash)", len(o.strip()) > 0 and not errs, o.replace("\n", " ")[:150])
    o = cmd(pg, "demo on"); check("terminal", "demo on", "demo" in o.lower(), o.strip()[:100])
    o = cmd(pg, "ask What is a signed receipt?", 5000); check("terminal", "ask → reply + signed receipt", "receipt" in o and "signed" in o, o.replace("\n", " ")[:160])
    pg.fill("#cmd", "ask Give me a long answer about receipts and why they matter in detail"); pg.press("#cmd", "Enter"); pg.wait_for_timeout(250)
    o = cmd(pg, "stop", 3000); check("terminal", "stop mid-reply", re.search(r"stop", o, re.I), o.replace("\n", " ")[:160])
    pg.fill("#cmd", ""); pg.focus("#cmd"); pg.keyboard.press("ArrowUp"); hv = pg.input_value("#cmd")
    check("terminal", "↑ recalls command history", hv == "stop", hv); pg.fill("#cmd", "")
    o = cmd(pg, "receipts"); n_rec = len(re.findall(r"\bv\d+\s", o)); check("terminal", "receipts lists every run", n_rec >= 3, o.replace("\n", " | ")[:200])
    o = cmd(pg, "verify 2", 1500); check("terminal", "verify 2 → VALID", "VALID" in o and "INVALID" not in o, o.strip()[:120])
    o = cmd(pg, "tamper 2", 1500); check("terminal", "tamper 2 → INVALID with the changed field", "INVALID" in o, o.strip()[:140])
    o = cmd(pg, "verify", 1500); check("terminal", "verify (latest) still VALID after tamper of another", "VALID" in o, o.strip()[:120])
    o = cmd(pg, "recap", 1500); check("terminal", "recap summarises the session", len(o.strip()) > 20, o.replace("\n", " ")[:160])
    o = cmd(pg, "set name Riley T"); title = pg.inner_text("#tUser")
    check("settings", "set name updates the window", "riley t" in (title + o).lower(), (title or o).replace("\n", " ")[:120])
    o = cmd(pg, "set temp 0.4"); check("settings", "set temp 0.4", "0.4" in o, o.strip()[:100])
    o = cmd(pg, "set max 256"); check("settings", "set max 256", "256" in o, o.strip()[:100])
    o = cmd(pg, "set system Be brief and cite receipts"); check("settings", "set system", "brief" in o.lower() or "system" in o.lower(), o.strip()[:100])
    o = cmd(pg, "set temp 9"); check("settings", "set temp 9 rejected (range 0-1.5)", "0 to 1.5" in o, o.strip()[:100])
    o = cmd(pg, "set temp abc"); check("settings", "set temp abc rejected", "0 to 1.5" in o, o.strip()[:100])
    o = cmd(pg, "set max -5"); check("settings", "set max -5 rejected", "64 to 4096" in o, o.strip()[:100])
    o = cmd(pg, "set name    "); check("settings", "blank name rejected", "usage" in o or "empty" in o, o.strip()[:100])
    o = cmd(pg, "sessions"); check("sessions", "sessions lists the current one", len(o.strip()) > 5, o.replace("\n", " | ")[:150])
    o = cmd(pg, "sessions new"); o2 = cmd(pg, "sessions"); check("sessions", "sessions new adds a session", o2.count("\n") >= 2 or "2" in o2, o2.replace("\n", " | ")[:150])
    o = cmd(pg, "open README.md"); check("files", "open README.md", len(o.strip()) > 10 or pg.is_visible("#outPane"), o.strip()[:120])
    o = cmd(pg, "open settings.json"); check("files", "open settings.json shows the saved settings", "256" in (o + pg.inner_text("#outPane")) or "temp" in (o + pg.inner_text("#outPane")).lower(), o.strip()[:120])
    o = cmd(pg, "open nope.txt"); check("files", "open unknown file → clear message", len(o.strip()) > 0 and not errs, o.strip()[:100])
    o = cmd(pg, "flarb"); check("terminal", "unknown command → hint, no crash", len(o.strip()) > 0 and not errs, o.strip()[:100])
    with pg.expect_download(timeout=8000) as dl: cmd(pg, "export", 1500)
    path = OUT / "ut-export.json"; dl.value.save_as(str(path)); ex = json.loads(path.read_text())
    exs = json.dumps(ex)
    check("data", "export downloads iolin-workspace.json", dl.value.suggested_filename == "iolin-workspace.json", dl.value.suggested_filename)
    check("data", "export has sessions + receipts + public key", "receipt" in exs.lower() and "public" in exs.lower(), list(ex)[:8])
    check("data", "export contains no private key", not re.search(r'"(d|privateKey|private_key|pkcs8)"\s*:', exs), "")
    o = cmd(pg, "demo off"); check("terminal", "demo off", "off" in o.lower(), o.strip()[:100])
    o = cmd(pg, "ask hello", 2500); check("terminal", "ask with demo off and no model → explains, no crash", len(o.strip()) > 0 and not errs, o.replace("\n", " ")[:150])
    cmd(pg, "demo on")

    # 3. Panels and buttons
    pg.click('[data-t="out"]'); pg.wait_for_timeout(300); check("panels", "Output tab", pg.is_visible("#outPane"), "")
    pg.click('[data-t="term"]')
    for v in ("instruct", "projects", "setup", "live"):
        pg.click(f'.tab[data-v="{v}"]'); pg.wait_for_timeout(400)
        check("panels", f"{v.title()} tab opens", pg.is_visible(f"#p-{v}"), "")
    pg.click('.tab[data-v="instruct"]'); pg.fill("#ask", "Instruct tab question: what changed?"); pg.click("#sendBtn"); pg.wait_for_timeout(5000)
    o = cmd(pg, "receipts"); check("panels", "Instruct Send creates a run + receipt", len(re.findall(r"\bv\d+\s", o)) > n_rec, o.replace("\n", " | ")[-160:])
    pg.click('.tab[data-v="setup"]'); pg.wait_for_timeout(300)
    check("panels", "Setup shows the saved name/temp/max", pg.input_value("#sName").lower().startswith("riley") and pg.input_value("#sTemp") in ("0.4",) and pg.input_value("#sMax") == "256",
          (pg.input_value("#sName"), pg.input_value("#sTemp"), pg.input_value("#sMax")))
    pg.fill("#sTemp", "7"); pg.press("#sTemp", "Tab"); pg.wait_for_timeout(600)
    check("settings", "Setup temp 7 snaps back to the saved 0.4", pg.input_value("#sTemp") == "0.4", pg.input_value("#sTemp"))
    pg.fill("#sMax", ""); pg.press("#sMax", "Tab"); pg.wait_for_timeout(600)
    check("settings", "Setup empty max snaps back to 256", pg.input_value("#sMax") == "256", pg.input_value("#sMax"))
    pg.click("#loadBtn"); pg.wait_for_timeout(2000); check("panels", "Setup 'Download and start' without WebGPU fails gracefully", not errs, errs)
    pg.click('.tab[data-v="live"]'); pg.wait_for_timeout(300)
    zones = pg.query_selector_all("[data-z]")
    if zones: zones[0].click(); pg.wait_for_timeout(800)
    check("panels", "live space zone click (zoom)", zones and not errs, f"{len(zones)} zones")
    files = pg.query_selector_all("#tree [data-cmd]")
    if files: files[-1].click(); pg.wait_for_timeout(600)
    check("panels", "workspace tree file click", files and not errs, f"{len(files)} items")
    recs = pg.query_selector_all("[data-recap]")
    if recs: recs[0].click(); pg.wait_for_timeout(1200)
    check("panels", "Agent sessions Recap chip", recs and not errs, f"{len(recs)} chips")
    vers = pg.query_selector_all("#vers [data-v]")
    if vers: vers[0].click(); pg.wait_for_timeout(1200)
    check("panels", "Versions item click verifies", vers and not errs, f"{len(vers)} versions; " + term(pg)[-90:].replace("\n", " "))
    nt = len(pg.query_selector_all("#tasks [data-cmd]"))
    for i in range(nt):
        t = pg.query_selector_all("#tasks [data-cmd]")[i]; c = t.get_attribute("data-cmd")
        if c == "export":
            with pg.expect_download(timeout=8000): t.click()
        else: t.click()
        pg.wait_for_timeout(900)
    check("panels", "Tasks run (verify all / model / sync / export)", nt and not errs, f"{nt} tasks")
    prod = pg.inner_text("#prodMeta") + " " + pg.inner_text("#sRuns")
    check("panels", "Production card counts runs", re.search(r"\d", pg.inner_text("#sRuns")), prod.replace("\n", " ")[:100])
    pg.screenshot(path=str(OUT / "ut-02-panels.png"))

    # 4. Reload keeps everything; tour doesn't reappear
    pg.reload(wait_until="networkidle"); pg.wait_for_timeout(2000)
    o = cmd(pg, "receipts")
    check("persistence", "reload keeps receipts", len(re.findall(r"\bv\d+\s", o)) >= n_rec, o.replace("\n", " | ")[:150])
    check("persistence", "reload keeps the name", "riley" in pg.inner_text("#tUser").lower(), pg.inner_text("#tUser"))
    check("persistence", "tour doesn't restart on reload", not pg.is_visible("#tName"), "")
    o = cmd(pg, "tour", 800); check("tour", "tour command replays it", pg.is_visible("#coach"), o.strip()[:80])
    if pg.query_selector("#tSkip"): pg.click("#tSkip"); pg.wait_for_timeout(500)
    o = cmd(pg, "clear"); check("terminal", "clear empties the terminal", len(term(pg).strip()) < 120, len(term(pg)))

    # 5. Full screen and phone layout
    pg.click("#fullBtn"); pg.wait_for_timeout(800); check("layout", "Open full screen", pg.is_visible("#closeFs"), "")
    pg.click("#closeFs"); pg.wait_for_timeout(500)
    ph = ctx.new_page(); ph.set_viewport_size({"width": 390, "height": 844}); ph.goto(URL, wait_until="networkidle"); ph.wait_for_timeout(1500)
    check("layout", "phone 390px: no sideways scroll", not ph.evaluate("document.documentElement.scrollWidth>innerWidth+1"), "")
    ph.click("#fullBtn"); ph.wait_for_timeout(800)
    check("layout", "phone full screen fits the width", not ph.evaluate("document.documentElement.scrollWidth>innerWidth+1"), "")
    ph.screenshot(path=str(OUT / "ut-03-phone.png")); ph.close()

    # 6. Import into a fresh browser
    ctx2 = b.new_context(viewport={"width": 1280, "height": 900}); p2 = ctx2.new_page(); p2.on("dialog", lambda d: d.accept())
    p2.goto(URL, wait_until="networkidle"); p2.wait_for_timeout(1500)
    if p2.query_selector("#tSkip") and p2.is_visible("#tSkip"): p2.click("#tSkip")
    p2.click('.tab[data-v="setup"]'); p2.set_input_files("#impFile", str(path)); p2.wait_for_timeout(1500)
    o = p2.inner_text("#termPane"); p2.fill("#cmd", "receipts"); p2.press("#cmd", "Enter"); p2.wait_for_timeout(800)
    o2 = p2.inner_text("#termPane")
    check("data", "import restores sessions/receipts in a new browser", len(re.findall(r"\bv\d+\s", o2)) >= n_rec, o2[-160:].replace("\n", " | "))
    ctx2.close()

    # 7. Erase everything
    pg.click('.tab[data-v="setup"]'); pg.click("#wipeBtn"); pg.wait_for_timeout(2000)
    o = cmd(pg, "receipts"); check("data", "Erase everything wipes receipts", not re.findall(r"\bv\d+\s", o), o.replace("\n", " | ")[:120])
    check("errors", "no page errors in the whole run", not errs, errs)
    b.close()

ok = sum(r[2] for r in R); print(f"\n{ok}/{len(R)} passed")
(OUT / "ut-results.json").write_text(json.dumps(R, indent=1))
