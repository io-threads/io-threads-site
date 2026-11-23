# Run: python3 .ci/iolin_usertest.py [url] [out-dir]   (default url = live site; the page defaults to the demo; ?live=1 opts in to a real model)
"""User test of io-threads.com/iolin/ as a new visitor ("Riley Test"). Headless Chromium has no WebGPU,
so real-model paths (?live=1) are checked for a graceful fallback; the default page is the demo (pre-recorded replies, no download)."""
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
    NET = []; pg.on("request", lambda r: NET.append(r.url))

    # 1. First visit: the tour
    pg.goto(URL + "?welcome=1", wait_until="networkidle"); pg.wait_for_timeout(1500)
    check("tour", "step 1 welcome shows on first visit", pg.is_visible("#tName"), "")
    # Real keystrokes, not fill(): fill() skips key events, which hid a bug that blocked typing here.
    pg.click("#tName"); pg.keyboard.type("Riley Test")
    check("tour", "name box accepts typed keys", pg.input_value("#tName") == "Riley Test", pg.input_value("#tName"))
    pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
    check("tour", "typed name shows in the window", pg.text_content("#tUser") == "riley test", pg.text_content("#tUser") or "")
    coach = pg.inner_text("#coach") if pg.query_selector("#coach") else ""
    check("demo", "default page is the demo: no model-CDN request, pre-recorded label", not [u for u in NET if any(h in u for h in ("esm.run", "huggingface.co", "cdn.jsdelivr.net"))] and "pre-recorded" in pg.inner_text("#dev"), [u for u in NET if "io-threads" not in u and "127.0.0.1" not in u][:3])
    check("tour", "step 2 device check explains no WebGPU and offers demo", re.search(r"demo", coach, re.I) and pg.query_selector("#tDemo, #tDemo2"), coach.replace("\n", " ")[:150])
    pg.click("#tDemo" if pg.query_selector("#tDemo") else "#tDemo2"); pg.wait_for_timeout(1500)
    q = pg.input_value("#tQ") if pg.query_selector("#tQ") else ""
    check("tour", "step 4 question pre-filled", "leave this device" in q, q)
    pg.click("#tQ"); pg.keyboard.type("?")
    check("tour", "question box accepts typed keys", len(pg.input_value("#tQ")) == len(q) + 1, pg.input_value("#tQ"))
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
    o = cmd(pg, "templates"); check("terminal", "templates lists the Instruct templates", all(k in o for k in ("release", "privacy", "inject", "drift")), o.replace("\n", " ")[:120])
    o = cmd(pg, "status"); check("terminal", "status reports model/device/storage", len(o.strip()) > 20, o.replace("\n", " ")[:150])
    o = cmd(pg, "model list"); check("terminal", "model list shows the 4 curated models", sum(k in o for k in ("0.6B", "1B", "3B", "8B")) >= 3, o.replace("\n", " ")[:150])
    o = cmd(pg, "model load small", 2500); check("terminal", "model load without WebGPU fails gracefully (no crash)", len(o.strip()) > 0 and not errs, o.replace("\n", " ")[:150])
    o = cmd(pg, "demo on"); check("terminal", "demo on", "demo" in o.lower(), o.strip()[:100])
    o = cmd(pg, "ask What is a signed receipt?", 5000); check("terminal", "ask → reply + signed receipt", "receipt" in o and "signed" in o, o.replace("\n", " ")[:160])
    pg.fill("#cmd", "ask Give me a long answer about receipts and why they matter in detail"); pg.press("#cmd", "Enter"); pg.wait_for_timeout(250)
    o = cmd(pg, "stop", 3000); check("terminal", "stop mid-reply", re.search(r"stop", o, re.I), o.replace("\n", " ")[:160])
    pg.fill("#cmd", ""); pg.focus("#cmd"); pg.keyboard.press("ArrowUp"); hv = pg.input_value("#cmd")
    check("terminal", "↑ recalls command history", hv == "stop", hv); pg.fill("#cmd", "")
    # Agent scores (iot API POST /v1/agents/scores): sample needs no key; the live call is mocked here, so no call is spent.
    o = cmd(pg, "agents")
    check("agents", "sample shows verdict, arms and a leader", "PASS" in o and "leader" in o and "rogue-scope" in o and "broke a rule" in o, o[-300:])
    o = cmd(pg, "agents live"); check("agents", "live without a key asks for one", "set your key first" in o, o)
    fake = "iot_" + "Z" * 30
    o = cmd(pg, "agents key " + fake); check("agents", "key is masked in the terminal", fake not in term(pg) and "iot_ZZZZ…" in o, o)
    pg.fill("#cmd", ""); pg.focus("#cmd"); pg.keyboard.press("ArrowUp"); hv = pg.input_value("#cmd"); pg.fill("#cmd", "")
    check("agents", "key is masked in command history", fake not in hv, hv)
    seen = {}
    def fake_api(route):
        seen["auth"] = route.request.headers.get("authorization", ""); seen["body"] = route.request.post_data or ""
        route.fulfill(status=200, headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "X-RateLimit-Remaining", "X-RateLimit-Remaining": "998"},
                      body=json.dumps({"verdict": "ABSTAIN", "task": "t", "floor": 0.8, "arms": [{"id": "<b>x</b>", "verdict": "ABSTAIN", "rate": 0.85, "ci95": [0.7, 0.93], "p_best": 0.5, "weight": 0.5, "result": "interval straddles the floor"}],
                                       "leader": {"id": "<b>x</b>", "p_best": 0.5, "decided": False}, "signal": "no clear leader yet"}))
    pg.route("**/functions/v1/iot/v1/agents/scores", fake_api)
    o = cmd(pg, 'agents {"arms":[{"id":"a","pass":9,"fail":1}]}', 1500)
    check("agents", "live call sends the key and the JSON typed", seen.get("auth") == "Bearer " + fake and '"pass":9' in seen.get("body", ""), seen)
    check("agents", "live result renders, arm names escaped", "ABSTAIN" in o and "998 calls left" in o and "<b>x</b>" in o and not pg.query_selector("#termPane b"), o[-250:])
    pg.unroute("**/functions/v1/iot/v1/agents/scores"); cmd(pg, "agents forget")
    # Local feed (local_feed.py on the visitor's machine), mocked: the page reads 127.0.0.1 with the tab-only token.
    o = cmd(pg, "feed watch"); check("feed", "feed without a token says how to connect", "connect first" in o, o)
    ftok = "feed_" + "Q" * 24; got = {}
    def fake_feed(route):
        got["auth"] = route.request.headers.get("authorization", "")
        route.fulfill(status=200, headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                      body=json.dumps({"name": "bus", "at": "2026-11-20T03:20:00Z", "took_ms": 1400, "every_s": 20, "rc": 0, "text": "┌─ MACHINE BUS <b>x</b>\n│ bridge: HEALTHY"}))
    pg.route("http://127.0.0.1:8806/v1/feed", fake_feed)
    o = cmd(pg, "feed connect " + ftok); check("feed", "feed token masked in the terminal", ftok not in term(pg), o)
    cmd(pg, "feed watch", 1200); outp = pg.inner_text("#outPane")
    check("feed", "feed shows the local terminal in Output, as text", "MACHINE BUS <b>x</b>" in outp and "bridge: HEALTHY" in outp and got.get("auth") == "Bearer " + ftok and not pg.query_selector("#outPane b"), outp[:160])
    pg.click('[data-t="term"]'); cmd(pg, "feed forget"); pg.unroute("http://127.0.0.1:8806/v1/feed")
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
    # The default page is the demo; "demo off" opens the real-model opt-in (?live=1) instead of leaving a dead terminal.
    cmd(pg, "demo off", 2500); pg.wait_for_load_state("networkidle")
    check("terminal", "demo off opens the real-model page (?live=1)", "live=1" in pg.url, pg.url)
    o = cmd(pg, "ask hello", 2500); check("terminal", "ask on the real-model page with no model → explains, no crash", len(o.strip()) > 0 and not errs, o.replace("\n", " ")[:150])
    pg.goto(URL, wait_until="networkidle"); pg.wait_for_timeout(1200)

    # 2b. Demo content: Iot tab, sample threads in the Finder list, board, every question answered, nav links
    check("demo", "first tab is named Iot", pg.inner_text('.tab[data-v="live"]').split()[1] == "Iot", pg.inner_text('.tab[data-v="live"]'))
    pg.click('.tab[data-v="instruct"]'); pg.wait_for_timeout(400)
    if pg.get_attribute("#fdrToggle", "aria-expanded") != "true": pg.click("#fdrToggle"); pg.wait_for_timeout(200)
    check("demo", "Threads open in List view with the four view buttons", pg.evaluate("document.getElementById('fdr').classList.contains('m-list')") and len(pg.query_selector_all(".vsw button")) == 4)
    pg.click('.vsw button[data-m="cols"]'); pg.wait_for_timeout(200)
    rows = pg.query_selector_all("#fdr .c2 .fi[data-id]"); titles = [r.inner_text() for r in rows]
    check("demo", "Finder lists the sample threads above the chat", len(rows) >= 4 and any("Release check" in t for t in titles)
          and pg.evaluate("document.getElementById('fdr').getBoundingClientRect().bottom <= document.getElementById('chat').getBoundingClientRect().top + 1"), titles[:5])
    rel = next((r for r in rows if "Release check" in r.inner_text()), None)
    if rel: rel.click(); pg.wait_for_timeout(400)
    check("demo", "clicking a thread opens it in the chat", "support-bot v4" in pg.inner_text("#chat") and "receipt" in pg.inner_text("#chat"), pg.inner_text("#chat")[:120])
    pg.click("#fdrNew"); pg.wait_for_timeout(300); pg.fill("#ask", "help me"); pg.click("#sendBtn"); pg.wait_for_timeout(5000)
    last = pg.query_selector_all("#chat .bub.a")[-1].inner_text().strip()
    check("demo", "'help me' gets a non-empty reply with a receipt", len(last) > 40 and "receipt" in last, last[:120])
    tp = pg.query_selector_all("#tpls button:not(.more)"); check("demo", "recent threads sit above the ask box", len(tp) >= 4 and any(b.get_attribute("aria-pressed") == "true" for b in tp), len(tp))
    pg.click("#tpls button.more"); pg.wait_for_timeout(300)
    check("demo", "templates live under Threads › Samples (10+)", len(pg.query_selector_all("#fdr .c2 .fi[data-tpl]")) >= 10, len(pg.query_selector_all("#fdr .c2 .fi[data-tpl]")))
    pg.click("#fdrNew"); pg.wait_for_timeout(300)
    check("demo", "an empty thread offers template cards", len(pg.query_selector_all("#chat .tcards button")) >= 6, len(pg.query_selector_all("#chat .tcards button")))
    pg.click('#tpls button.more'); pg.wait_for_timeout(200); pg.click('#fdr .c2 .fi[data-tpl="inject"]'); pg.wait_for_timeout(200); v = pg.input_value("#ask")
    check("demo", "a template prefills the ask box with [placeholders]", v.startswith("Prompt-injection test:") and "[" in v, v[:80])
    pg.click("#sendBtn"); pg.wait_for_timeout(6000); last = pg.query_selector_all("#chat .bub.a")[-1].inner_text().strip()
    check("demo", "a template gets its own pre-recorded reply + receipt", "rules held" in last and "receipt" in last, last[:120])
    pg.click('.tab[data-v="projects"]'); pg.wait_for_timeout(300)
    check("demo", "Projects board has template items", len(pg.query_selector_all("#zboard .bi")) >= 8, len(pg.query_selector_all("#zboard .bi")))
    nav = {a.inner_text().strip(): a.get_attribute("href") for a in pg.query_selector_all(".nav a")}
    check("links", "header nav goes to its pages, not home", nav.get("iostem API") == "/api.html" and nav.get("Account") == "/app.html" and nav.get("Enterprise") not in (None, "/", "https://io-threads.com"), nav)
    pg.click('.tab[data-v="live"]'); pg.wait_for_timeout(300)

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
    # 3b. Setup: model library, presets, serve to apps
    cards = pg.query_selector_all("#mlist .mc"); det = pg.inner_text("#mdet")
    check("setup", "model library: cards with fit, weights/license, training data, context", len(cards) >= 8 and all(k in det for k in ("This device", "Weights", "Training data", "Context")), f"{len(cards)} cards; " + det[:120].replace("\n", " "))
    pg.wait_for_timeout(2500); lb = pg.query_selector_all("#mdet .lb li")
    check("setup", "leaderboards from the benchmarks feed (or its snapshot), linked", len(lb) >= 1 and pg.query_selector("#mdet .lb a[href^='https://']") is not None, f"{len(lb)} boards; " + pg.inner_text("#mdet").split("Leaderboards")[-1][:120].replace("\n", " "))
    pg.fill("#mlQ", "deepseek"); pg.wait_for_timeout(300); n = len(pg.query_selector_all("#mlist .mc"))
    check("setup", "model search filters the library", n == 1, n)
    pg.click("#mlist .mc"); pg.wait_for_timeout(300); check("setup", "picking a card shows its details", "DeepSeek" in pg.inner_text("#mdet"), pg.inner_text("#mdet")[:80])
    pg.fill("#mlQ", ""); pg.select_option("#mlFilter", "data"); pg.wait_for_timeout(300); n = len(pg.query_selector_all("#mlist .mc"))
    check("setup", "filter 'training data published' narrows the list", 1 <= n < len(cards), n); pg.select_option("#mlFilter", "all"); pg.wait_for_timeout(200)
    pg.click('#presets button[data-preset="Precise"]'); pg.wait_for_timeout(300)
    check("setup", "preset Precise sets temp 0.2, top_p 0.9, max 512", (pg.input_value("#sTemp"), pg.input_value("#sTopP"), pg.input_value("#sMax")) == ("0.2", "0.9", "512"), (pg.input_value("#sTemp"), pg.input_value("#sTopP"), pg.input_value("#sMax")))
    pg.fill("#srvHost", "192.168.1.20"); pg.press("#srvHost", "Tab"); pg.fill("#srvPort", "9"); pg.press("#srvPort", "Tab"); pg.check("#srvKeyOn"); pg.wait_for_timeout(300)
    code = pg.inner_text("#srvCode"); check("setup", "server snippet uses the host/IP, port and API key", "http://192.168.1.20:9/v1" in code and "Bearer iolin-" in code, code[:120])
    pg.click('#snTabs button[data-snip="VS Code (Continue)"]'); pg.wait_for_timeout(200)
    check("setup", "IDE snippet (VS Code Continue) points at the server", "apiBase: http://192.168.1.20:9/v1" in pg.inner_text("#srvCode"), pg.inner_text("#srvCode")[:100])
    pg.click("#srvCopy"); pg.wait_for_timeout(200); check("setup", "Copy copies (or selects) the snippet", pg.inner_text("#srvCopy") in ("Copied", "Selected"), pg.inner_text("#srvCopy"))
    pg.fill("#srvHost", "127.0.0.1"); pg.press("#srvHost", "Tab"); pg.click("#srvTest"); pg.wait_for_timeout(3800); res = pg.inner_text("#srvRes")
    check("setup", "Test connection with nothing listening gives a clear answer", ("Couldn't connect" in res or "No answer" in res) and not errs, res[:140])
    pg.click('#presets button[data-preset="Balanced"]'); pg.fill("#srvPort", "1234"); pg.press("#srvPort", "Tab"); pg.uncheck("#srvKeyOn"); pg.wait_for_timeout(200)
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
    ph.evaluate("document.querySelector('.coach') && document.querySelector('.coach .skip') && document.querySelector('.coach .skip').click(); document.querySelector('.tab[data-v=\"setup\"]').click()"); ph.wait_for_timeout(600)
    check("layout", "phone Setup (models, server) fits the width", ph.is_visible("#mlist") and not ph.evaluate("document.documentElement.scrollWidth>innerWidth+1"), "")
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
