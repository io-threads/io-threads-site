# Run: python3 .ci/iolin_board.py [screenshot-dir]
"""Board test for the iolin window's bottom panel: serves this checkout on a free port and drives /iolin/?test=1 in
headless Chromium. Checks the Board is the default tab with four columns whose cards come from the page's own state,
that an ask from the Board's command line goes Running -> Done with its receipt id, that tamper puts a FAIL card in
Needs you (and a clean verify of the stored receipt moves it to Done), that a card's Iot chip focuses its zone and
pulses the matching scene object, that a zone chosen in the scene filters the board (with a chip that clears it and
an aria-live note), that Terminal and Output still work, and the layout at 1280 and 390 px in dawn, twilight and dusk,
in full screen and with the installed-app (standalone) emulation: no page errors, no sideways page scroll."""
import functools, http.server, pathlib, re, socketserver, sys, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
FAILS, N = [], [0]

def check(name, ok, ev=""):
    N[0] += 1
    print("PASS" if ok else "FAIL", name, "|", str(ev)[:220])
    if not ok: FAILS.append(f"{name}: {ev}")

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
PORT = srv.server_address[1]; assert PORT not in (8787, 8811, 8812)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORT}/iolin/?test=1&sw=0"

COLS = "() => [...document.querySelectorAll('#kb .kcol')].map(c => ({name: c.getAttribute('aria-label'), n: +c.querySelector('h3 span').textContent, cards: [...c.querySelectorAll('.kc')].map(k => ({id: k.dataset.id, zone: k.dataset.zone, text: k.innerText}))}))"
def cols(pg): return {c["name"]: c for c in pg.evaluate(COLS)}
def col_text(pg, name): return " | ".join(k["text"].replace("\n", " ") for k in cols(pg)[name]["cards"])
def hscroll(pg): return pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
def skip_tour(pg):
    if pg.is_visible("#tSkip"): pg.click("#tSkip"); pg.wait_for_timeout(200)
def shot(pg, name, el="#win"):
    if SHOTS:
        loc = pg.locator(el)
        (loc.screenshot if el else pg.screenshot)(path=str(SHOTS / f"board_{name}.png"))

with sync_playwright() as p:
    b = p.chromium.launch()
    # ---------- 1280, default theme: state, flow, linking ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.goto(URL, wait_until="networkidle"); pg.wait_for_function("window.__iolin && __iolin.ready"); pg.wait_for_timeout(600); skip_tour(pg)

    check("Board is the default bottom tab", pg.is_visible("#kb") and pg.get_attribute('.ttab[data-t="board"]', "aria-pressed") == "true" and not pg.is_visible("#termPane"), "")
    c = cols(pg)
    check("four columns in order", list(c) == ["Queued", "Running", "Needs you", "Done"], list(c))
    check("column counts match their cards", all(v["n"] == len(v["cards"]) for v in c.values()), {k: (v["n"], len(v["cards"])) for k, v in c.items()})
    st = pg.evaluate("({n: document.querySelectorAll('#vers [data-v]').length, last: __iolin.last() && __iolin.last().run_id.slice(0, 8), abst: document.querySelectorAll('#vers .abst').length, auth: document.querySelector('#scene .lab[data-sz=auth]').textContent})")
    done = col_text(pg, "Done"); need = col_text(pg, "Needs you"); run = col_text(pg, "Running")
    check("Done holds the receipts from state, each with its id", st["last"] and st["last"] in done and len(re.findall(r"receipt v\d+ · [0-9a-f]{8}", done)) >= min(6, st["n"]), done[:200])
    check("ABSTAIN count in Needs you matches the receipts", (f"{st['abst']} runs ABSTAIN" in need) if st["abst"] > 1 else True, need[:160])
    check("model and device cards are Running", "demo engine live" in run and "connected" in run and "▣ demo engine · Devices" in run, run[:200])
    m = re.search(r"(\d+) of (\d+) set", st["auth"]); unset = int(m.group(2)) - int(m.group(1))
    auth_need = [k for k in c["Needs you"]["cards"] if k["zone"] == "auth"]
    check("each auth item that isn't set is a Needs-you card (authRows)", len(auth_need) == unset and "iostem API key" in need and "◈ auth access" in need, (unset, len(auth_need)))
    check("every card shows owner, Iot chip and time", pg.evaluate("[...document.querySelectorAll('#kb .kc')].every(k => k.querySelector('.who b') && k.querySelector('.kc-iot') && k.querySelector('time'))"), "")
    check("tasks rows are cards (rechk, sync, export)", "verify-all" in done and "settings.json saved" in done and "Export the workspace" in col_text(pg, "Queued"), "")
    check("Needs-you count on the Board tab", pg.inner_text("#bNeed").strip() == str(c["Needs you"]["n"]), pg.inner_text("#bNeed"))
    shot(pg, "1280_twilight_default")

    # ask from the Board's command line: Running, then Done with the receipt id
    pg.fill("#bcmd", "ask hello board"); pg.press("#bcmd", "Enter")
    pg.wait_for_function("[...document.querySelectorAll('#kb .kcol[aria-label=Running] .kc')].some(k => k.innerText.includes('hello board'))", timeout=4000)
    check("a new ask shows in Running", "hello board" in col_text(pg, "Running"), col_text(pg, "Running")[:120])
    shot(pg, "1280_running")
    pg.wait_for_function("[...document.querySelectorAll('#kb .kcol[aria-label=Done] .kc')].some(k => k.innerText.includes('hello board'))", timeout=15000)
    rid = pg.evaluate("__iolin.last().run_id.slice(0, 8)")
    card = [k for k in cols(pg)["Done"]["cards"] if "hello board" in k["text"]][0]["text"]
    check("then moves to Done with its receipt id", rid in card and "hello board" not in col_text(pg, "Running"), card.replace("\n", " "))
    check("Board stays open and shows the last terminal line", pg.is_visible("#kb") and "signed" in pg.inner_text("#bLast"), pg.inner_text("#bLast"))
    pg.fill("#bcmd", "what is a receipt"); pg.press("#bcmd", "Enter")
    pg.wait_for_function("[...document.querySelectorAll('#kb .kcol[aria-label=Done] .kc')].some(k => k.innerText.includes('what is a receipt'))", timeout=15000)
    check("plain text on the Board line is asked", True, "")

    # tamper: a FAIL card in Needs you; verify of the stored receipt moves it to Done
    pg.fill("#bcmd", "tamper"); pg.press("#bcmd", "Enter"); pg.wait_for_timeout(700)
    need = col_text(pg, "Needs you")
    check("tamper puts a FAIL card in Needs you", "failed the check" in need and "FAIL" in need, need[:200])
    check("Board stays on Board, Output gets a dot", pg.is_visible("#kb") and "new" in pg.get_attribute('.ttab[data-t="out"]', "class"), "")
    shot(pg, "1280_needs_you")
    pg.fill("#bcmd", "verify"); pg.press("#bcmd", "Enter"); pg.wait_for_timeout(700)
    check("verify of the stored receipt moves it to Done", "failed the check" not in col_text(pg, "Needs you") and "re-checked" in col_text(pg, "Done"), col_text(pg, "Done")[:200])

    # card -> Iot: chip focuses the zone, pulses the item, scene comes into view
    pg.evaluate("window.scrollTo(0, document.body.scrollHeight)"); vb0 = pg.evaluate("__iolinScene.viewBox()")
    chip = pg.locator("#kb .kc[data-id=model] .kc-iot"); chip.click(); pg.wait_for_timeout(500)
    check("chip focuses the zone (select + viewBox)", pg.input_value("#zsel") == "devices" and pg.evaluate("__iolinScene.viewBox()") != vb0, (pg.input_value("#zsel"), vb0, pg.evaluate("__iolinScene.viewBox()")))
    check("chip pulses the matching scene object", pg.evaluate("!!document.querySelector('#scene g.pulse[data-item=model]') && !document.querySelector('#scene g.pulse[data-item=device]')"), "")
    check("scene scrolled into view", pg.evaluate("(r => r.top < innerHeight && r.bottom > 0)(document.getElementById('view').getBoundingClientRect())"), "")
    check("focus stays on the chip", pg.evaluate("document.activeElement && document.activeElement.classList.contains('kc-iot')"), "")
    shot(pg, "1280_chip_devices")
    pg.wait_for_timeout(2900)
    check("pulse ends", not pg.evaluate("!!document.querySelector('#scene g.pulse')"), "")
    check("focusing a zone filters the board to it", pg.is_visible("#bFilt") and all(z == "devices" for z in pg.evaluate("[...document.querySelectorAll('#kb .kc')].map(k => k.dataset.zone)")), "")
    pg.locator("#bFilt").click(); pg.wait_for_timeout(200)
    pg.locator("#kb .kc[data-id^=r-] .kc-iot").first.click(); pg.wait_for_timeout(300)
    check("receipt chip -> Runs zone + receipts stack", pg.input_value("#zsel") == "runs" and pg.evaluate("!!document.querySelector('#scene g.pulse[data-item=receipts]')"), pg.input_value("#zsel"))
    pg.locator("#bFilt").click(); pg.wait_for_timeout(200)
    pg.locator("#kb .kc[data-zone=auth] .kc-iot").first.click(); pg.wait_for_timeout(300)
    check("auth chip -> auth zone (checklist opens)", pg.input_value("#zsel") == "auth" and pg.is_visible("#authp"), "")

    # Iot -> card: a zone picked in the scene filters the board; the chip clears it
    pg.locator("#bFilt").click(); pg.wait_for_timeout(200)
    pg.click('#zones [data-z="files"]'); pg.wait_for_timeout(300)
    zs = pg.evaluate("[...document.querySelectorAll('#kb .kc')].map(k => k.dataset.zone)")
    check("scene zone filters the board", zs and all(z == "files" for z in zs), zs)
    check("visible 'filtered: Project files ×' chip", pg.is_visible("#bFilt") and "filtered: Project files" in pg.inner_text("#bFilt"), pg.inner_text("#bFilt"))
    check("aria-live says so", "filtered to Project files" in pg.inner_text("#boardSay"), pg.inner_text("#boardSay"))
    pg.select_option("#zsel", "net"); pg.wait_for_timeout(200)
    check("empty filtered columns say so", "No Networking cards here." in pg.inner_text("#kb"), "")
    pg.focus("#bFilt"); pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    check("chip clears the filter (keyboard)", not pg.is_visible("#bFilt") and pg.input_value("#zsel") == "all" and len(pg.evaluate("[...new Set([...document.querySelectorAll('#kb .kc')].map(k => k.dataset.zone))]")) > 2, pg.inner_text("#boardSay"))

    # keyboard: cards are buttons with a visible focus ring; Enter runs the card's command
    pg.locator("#kb .kc[data-id=sync] .kc-main").focus(); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    check("keyboard: a card runs its command", "see Output" in pg.inner_text("#bLast") and pg.get_attribute("#bLast", "data-t") == "out" and "temperature" in pg.text_content("#outPane"), pg.inner_text("#bLast"))
    ring = pg.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    check("focus-visible ring on cards", ring not in ("none", ""), ring)

    # Terminal and Output tabs still work
    pg.click('.ttab[data-t="term"]'); pg.wait_for_timeout(200)
    check("Terminal tab shows the terminal", pg.is_visible("#termPane") and pg.is_visible("#cmd") and not pg.is_visible("#kb"), "")
    before = len(pg.inner_text("#termPane")); pg.fill("#cmd", "help"); pg.press("#cmd", "Enter"); pg.wait_for_timeout(300)
    check("terminal commands still run", "tamper" in pg.inner_text("#termPane")[before:], "")
    pg.click('.ttab[data-t="out"]'); pg.wait_for_timeout(200)
    check("Output tab shows output", pg.is_visible("#outPane") and not pg.is_visible("#termPane"), "")
    pg.click('.ttab[data-t="term"]'); pg.fill("#cmd", "open settings.json"); pg.press("#cmd", "Enter"); pg.wait_for_timeout(300)
    check("open from the terminal still switches to Output", pg.is_visible("#outPane"), "")
    pg.click('.ttab[data-t="term"]'); pg.fill("#cmd", "verify"); pg.press("#cmd", "Enter"); pg.wait_for_timeout(300)
    check("verify from the terminal shows Output, then the terminal", pg.is_visible("#outPane"), "")
    pg.wait_for_timeout(1500); check("…and returns to the terminal", pg.is_visible("#termPane"), "")
    pg.click('.ttab[data-t="board"]'); pg.wait_for_timeout(200)
    check("back to Board", pg.is_visible("#kb"), "")
    check("no page errors (1280 flow)", not errs, errs)
    ctx.close()

    # ---------- themes x widths x modes ----------
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
    STANDALONE = """const mm = window.matchMedia.bind(window); window.matchMedia = q => /display-mode:\\s*standalone/.test(q) ? {matches: true, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; }} : mm(q);
      Object.defineProperty(navigator, 'standalone', {get: () => true});"""
    for env, scheme in (("dawn", "light"), ("twilight", "dark"), ("dusk", "dark")):
        for w in (1280, 390):
            for mode in (("window", "full") if w == 1280 else ("full", "standalone")):
                kw = dict(viewport={"width": w, "height": 900 if w == 1280 else 844}, color_scheme=scheme)
                if w == 390: kw.update(user_agent=IPHONE, is_mobile=True, has_touch=True, device_scale_factor=2)
                ctx = b.new_context(**kw)
                ctx.add_init_script(f"try {{ localStorage.setItem('iot-site-theme', '{env}'); localStorage.setItem('iolin-orbit-hint', 'done'); }} catch (e) {{}}")
                if mode == "standalone": ctx.add_init_script(STANDALONE)
                pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
                pg.goto(URL, wait_until="networkidle"); pg.wait_for_function("window.__iolin && __iolin.ready"); pg.wait_for_timeout(500); skip_tour(pg)
                tag = f"{env} {w} {mode}"
                check(f"{tag}: theme applied", pg.get_attribute("#win", "data-env") == env, pg.get_attribute("#win", "data-env"))
                if mode in ("full", "standalone") and "full" not in (pg.get_attribute("body", "class") or ""): pg.click("#fullBtn"); pg.wait_for_timeout(500)
                check(f"{tag}: four columns render", pg.evaluate("document.querySelectorAll('#kb .kcol').length") == 4 and pg.is_visible("#kb"), "")
                check(f"{tag}: no sideways page scroll", not hscroll(pg), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
                bg = pg.evaluate("getComputedStyle(document.getElementById('termBox')).backgroundColor"); panel = pg.evaluate("getComputedStyle(document.querySelector('.side')).backgroundColor")
                check(f"{tag}: board follows the window palette", bg == panel, (bg, panel))
                if w == 390:
                    sc = pg.evaluate("(k => [k.scrollWidth, k.clientWidth])(document.getElementById('kb'))")
                    check(f"{tag}: columns scroll sideways inside the board", sc[0] > sc[1], sc)
                    pg.locator("#kb .kc[data-id=model] .kc-iot").click(); pg.wait_for_timeout(500)
                    r = pg.evaluate("(r => [r.top, r.bottom, innerHeight])(document.getElementById('view').getBoundingClientRect())")
                    check(f"{tag}: chip brings the scene into view", pg.input_value("#zsel") == "devices" and r[0] < r[2] and r[1] > 0, r)
                    pg.locator("#bFilt").scroll_into_view_if_needed(); pg.wait_for_timeout(200)
                    shot(pg, f"{w}_{env}_{mode}", None)
                    pg.locator("#bFilt").click(); pg.wait_for_timeout(150)
                    pg.locator("#kb").scroll_into_view_if_needed(); pg.wait_for_timeout(200); shot(pg, f"{w}_{env}_{mode}_board", None)
                else:
                    shot(pg, f"{w}_{env}_{mode}", "#win" if mode == "window" else None)
                if mode == "standalone":
                    check(f"{tag}: standalone emulation active", pg.evaluate("matchMedia('(display-mode: standalone)').matches && navigator.standalone === true"), "")
                check(f"{tag}: no page errors", not errs, errs)
                ctx.close()

    # reduced motion: the pulse is a still outline, not an animation
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce"); pg = ctx.new_page()
    pg.goto(URL, wait_until="networkidle"); pg.wait_for_function("window.__iolin && __iolin.ready"); skip_tour(pg)
    pg.locator("#kb .kc[data-id=model] .kc-iot").click(); pg.wait_for_timeout(200)
    a = pg.evaluate("(g => g && [getComputedStyle(g).animationName, getComputedStyle(g).filter])(document.querySelector('#scene g.pulse'))")
    check("reduced motion: outline without animation", a and a[0] == "none" and "drop-shadow" in a[1], a)
    ctx.close()
    b.close()
srv.shutdown()
print(f"\n{N[0] - len(FAILS)}/{N[0]} passed")
for f in FAILS: print("FAIL", f)
sys.exit(1 if FAILS else 0)
