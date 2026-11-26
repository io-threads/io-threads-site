# Run: python3 .ci/iolin_orbit.py [screenshot-dir]
"""Orbit test for the iolin live scene: serves this checkout on a free port and drives /iolin/?test=1 in headless
Chromium at 1280 and 390 px, light and dark. Checks framing at every 5° (nothing leaves the fixed per-zone viewBox,
which never changes within a zone), hold / cancel / lost-capture / drag settling with the 90° magnetic snap,
reduced motion, label overlap and the slider aria text at the four corners, no text selection and no page errors."""
import functools, http.server, math, pathlib, socketserver, sys, threading, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
Q = math.pi / 2
FAILS, N = [], [0]
SIDES = ["front", "right side", "back", "left side"]
LABELS = {"auth": 1, "devices": 2, "files": 2, "runs": 1, "agents": 1, "net": 0}

def check(name, ok, ev=""):
    N[0] += 1
    if not ok: FAILS.append(f"{name}: {ev}"); print("FAIL", name, "|", str(ev)[:300])

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/iolin/?test=1"

BOUNDS = """z => { const sc = document.getElementById('scene'), [x, y, w, h] = sc.getAttribute('viewBox').split(' ').map(Number), bad = [];
  const els = z === 'all' ? [...sc.children].filter(e => e.tagName !== 'defs') : [...sc.querySelectorAll(`[data-sz="${z}"]`)];
  for (const e of els) { const b = e.getBBox(); if (!b.width && !b.height) continue;
    if (b.x < x - .5 || b.y < y - .5 || b.x + b.width > x + w + .5 || b.y + b.height > y + h + .5) bad.push([e.getAttribute('data-sz') || e.tagName, Math.round(b.x), Math.round(b.y), Math.round(b.x + b.width), Math.round(b.y + b.height)]); }
  return {vb: sc.getAttribute('viewBox'), n: els.length, bad}; }"""
COVER = """z => { const sc = document.getElementById('scene'), w = +sc.getAttribute('viewBox').split(' ')[2]; let a = Infinity, b = -Infinity;
  for (const e of sc.querySelectorAll(`[data-sz="${z}"]`)) { const r = e.getBBox(); if (!r.width && !r.height) continue; a = Math.min(a, r.x); b = Math.max(b, r.x + r.width); }
  return (b - a) / w; }"""
COVERAGE = {}
LABS = """() => [...document.querySelectorAll('#scene .lab')].map(g => { const b = g.querySelector('rect').getBBox(); return {z: g.dataset.sz, x: b.x, y: b.y, w: b.width, h: b.height, t: g.textContent}; })"""

def nearest_q(a): return min(abs(a - k * Q) for k in range(5))

def settle(pg):
    """Wait until nothing runs; dt = in-page time from the release event to the settle (not Playwright round trips)."""
    t = time.time()
    while pg.evaluate("__iolinScene.busy()"):
        if time.time() - t > 1.5: break
        pg.wait_for_timeout(10)
    dt = pg.evaluate("window.__rel == null ? 0 : (__iolinScene.settledAt() - window.__rel) / 1000")
    y1 = pg.evaluate("__iolinScene.getYaw()"); pg.wait_for_timeout(80); y2 = pg.evaluate("__iolinScene.getYaw()")
    return dt, y1, y2

def scene_point(pg, frac):
    r = pg.evaluate("(() => { const b = document.getElementById('scene').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; })()")
    x, y = r[0] + r[2] * frac, r[1] + r[3] * 0.62
    hit = pg.evaluate(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return !!(e && e.closest('#scene')); }})()")
    return x, y, hit

def run(p, width, scheme):
    tag = f"{width}/{scheme}"
    ctx = p.chromium.launch().new_context(viewport={"width": width, "height": 900 if width > 600 else 844}, color_scheme=scheme)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.goto(URL, wait_until="networkidle"); pg.wait_for_timeout(800)
    if pg.query_selector("#tSkip") and pg.is_visible("#tSkip"): pg.click("#tSkip"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('scene').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(300)
    pg.evaluate("""(() => { const sc = document.getElementById('scene'); sc.addEventListener('pointerdown', e => { window.__pid = e.pointerId; window.__rel = null; }, true);
      for (const t of ['pointerup', 'pointercancel', 'lostpointercapture']) sc.addEventListener(t, () => { if (window.__rel == null) window.__rel = performance.now(); }, true); })()""")
    check(f"{tag} test hook present", pg.evaluate("!!window.__iolinScene"))
    check(f"{tag} hint chip shows before the first turn", pg.is_visible("#orbitHint"))

    # 1. framing: 0..355° in 5° steps, every element (all) or every zone element inside a fixed viewBox
    for z in ("all", "auth", "net", "devices", "files", "runs", "agents"):
        pg.evaluate(f"__iolinScene.zone('{z}')"); vbs, bad = set(), []
        for deg in range(0, 360, 5):
            pg.evaluate(f"__iolinScene.setYaw({deg * math.pi / 180})"); r = pg.evaluate(BOUNDS, z)
            vbs.add(r["vb"]); bad += [(deg, b) for b in r["bad"]]
        check(f"{tag} zone {z}: everything inside the viewBox at every 5°", not bad, bad[:4])
        check(f"{tag} zone {z}: viewBox constant", len(vbs) == 1, vbs)
        if z != "all":   # the zone's objects and labels at yaw 0 fill a fair share of the frame width
            pg.evaluate("__iolinScene.setYaw(0)"); cov = pg.evaluate(COVER, z); COVERAGE[(width, scheme, z)] = cov
            need = 0.35 if width > 560 else 0.25
            if not (width <= 560 and z == "auth"): check(f"{tag} zone {z}: covers ≥{need:.0%} of the frame width at 0°", cov >= need, round(cov, 3))
    pg.evaluate("__iolinScene.zone('all')")

    # 2. corners: labels don't overlap, the focused zone's labels all show, aria text
    for z in ("all", "auth", "devices", "files", "runs", "agents", "net"):
        pg.evaluate(f"__iolinScene.zone('{z}')")
        for i, deg in enumerate((0, 90, 180, 270)):
            pg.evaluate(f"__iolinScene.setYaw({deg * math.pi / 180})"); L = pg.evaluate(LABS)
            ov = [(a["t"], b["t"]) for j, a in enumerate(L) for b in L[j + 1:] if a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]]
            check(f"{tag} zone {z} @{deg}: no label overlap", not ov, ov)
            if z != "all": check(f"{tag} zone {z} @{deg}: focused labels visible", sum(l["z"] == z for l in L) == LABELS[z], [l["t"] for l in L])
            else: check(f"{tag} all @{deg}: at least 5 of 7 labels shown", len(L) >= 5, len(L))
            vt = pg.get_attribute("#scene", "aria-valuetext"); vn = pg.get_attribute("#scene", "aria-valuenow")
            check(f"{tag} @{deg}: aria", vt == f"viewing from the {SIDES[i]}" and vn == str(deg), (vt, vn))
    pg.evaluate("__iolinScene.zone('all')")
    if SHOTS:
        for deg in (0, 90, 180, 270):
            pg.evaluate(f"__iolinScene.setYaw({deg * math.pi / 180})"); pg.wait_for_timeout(60)
            pg.locator("#p-live").screenshot(path=str(SHOTS / (f"orbit_{deg}_{width}.png" if scheme == "dark" else f"orbit_{deg}_{width}_light.png")))

    # 3. hold 600 ms then release / pointercancel / lostpointercapture, and drags
    x, y, hit = scene_point(pg, 0.62); check(f"{tag} press point hits the scene", hit)
    for start, how in ((0, "up"), (75, "up"), (0, "cancel"), (75, "lost"), (0, "lost")):
        pg.evaluate(f"__iolinScene.setYaw({start * math.pi / 180})"); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(600)
        if how == "up": pg.mouse.up()
        elif how == "cancel": pg.evaluate("document.getElementById('scene').dispatchEvent(new PointerEvent('pointercancel', {pointerId: window.__pid, isPrimary: true, bubbles: true}))")
        else: pg.evaluate("document.getElementById('scene').releasePointerCapture(window.__pid)")
        y0 = pg.evaluate("__iolinScene.getYaw()"); dt, y1, y2 = settle(pg)
        if how != "up": pg.mouse.up()
        moved = (y0 - start * math.pi / 180) % (2 * math.pi)
        check(f"{tag} hold from {start}° ({how}): it turned", 0.05 < moved < 1.2, moved)
        check(f"{tag} hold from {start}° ({how}): settled within 400 ms, still after", dt <= 0.4 and abs(y1 - y2) < 1e-9 and not pg.evaluate("__iolinScene.busy()"), (round(dt, 3), y1, y2))
        if how == "cancel": check(f"{tag} cancel: stops where it is, no snap", abs(y1 - y0) < 1e-9, (y0, y1))
        else:
            nq = nearest_q(y1)
            check(f"{tag} hold from {start}° ({how}): on a corner or left outside ±15°", nq < 1e-3 or nq > math.radians(15) - 1e-6, math.degrees(nq))
        if start == 75 and how != "cancel": check(f"{tag} hold from 75° ({how}): snapped to 90°", abs(y1 - Q) < 1e-3, math.degrees(y1))
    for dx, expect in ((10, 0.0), (60, None), (-30, None)):
        pg.evaluate("__iolinScene.setYaw(0)"); pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + dx / 2, y, steps=3); pg.mouse.move(x + dx, y, steps=3); pg.mouse.up()
        dt, y1, y2 = settle(pg)
        check(f"{tag} drag {dx}px: settles within 400 ms", dt <= 0.4 and abs(y1 - y2) < 1e-9, (dt, y1))
        if expect is not None: check(f"{tag} drag {dx}px: snaps back to 0°", nearest_q(y1) < 1e-3 and min(y1, 2 * math.pi - y1) < 1e-3, math.degrees(y1))
        else: check(f"{tag} drag {dx}px: stays (no snap past 15°)", nearest_q(y1) > math.radians(15) - 1e-6, math.degrees(y1))
    check(f"{tag} hint chip gone after the first turn", not pg.is_visible("#orbitHint"))

    # 4. keys and reset
    pg.evaluate("__iolinScene.setYaw(0)"); pg.focus("#scene")
    pg.keyboard.press("ArrowRight"); check(f"{tag} → is 15°", abs(pg.evaluate("__iolinScene.getYaw()") - math.radians(15)) < 1e-9)
    pg.keyboard.press("ArrowLeft"); pg.keyboard.press("ArrowLeft"); check(f"{tag} ← ← wraps to 345°", abs(pg.evaluate("__iolinScene.getYaw()") - math.radians(345)) < 1e-9)
    pg.keyboard.press("PageUp"); check(f"{tag} PageUp +90°", abs(pg.evaluate("__iolinScene.getYaw()") - math.radians(75)) < 1e-9)
    pg.keyboard.press("PageDown"); pg.keyboard.press("PageDown"); check(f"{tag} PageDown −90° (wraps)", abs(pg.evaluate("__iolinScene.getYaw()") - math.radians(255)) < 1e-9)
    pg.keyboard.press("Home"); check(f"{tag} Home resets", pg.evaluate("__iolinScene.getYaw()") == 0)
    pg.keyboard.press("PageUp"); pg.click("#orbitReset"); check(f"{tag} Reset view button", pg.evaluate("__iolinScene.getYaw()") == 0)
    pg.wait_for_timeout(500); check(f"{tag} live region announces the settled view", pg.text_content("#orbitSay") == "viewing from the front", pg.text_content("#orbitSay"))

    # 5. no selection after double-click and a drag across the window; no page errors
    pg.evaluate("document.getElementById('scene').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200); x, y, hit = scene_point(pg, 0.62)
    pg.mouse.dblclick(x, y); pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(10, 10, steps=8); pg.mouse.up(); settle(pg)
    sel = pg.evaluate("String(getSelection())")
    check(f"{tag} no text selected after dblclick + drag", sel == "", sel[:80])
    check(f"{tag} no page errors", not errs, errs)
    ctx.browser.close()

def reduced(p):
    ctx = p.chromium.launch().new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle"); pg.wait_for_timeout(800)
    if pg.query_selector("#tSkip") and pg.is_visible("#tSkip"): pg.click("#tSkip"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('scene').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(300)
    for frac, want in ((0.62, 90), (0.3, 0)):
        x, y, _ = scene_point(pg, frac); pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(600)
        mid = pg.evaluate("__iolinScene.getYaw()"); pg.mouse.up(); dt, y1, _ = settle(pg)
        check(f"reduced motion: hold = one 90° step to {want}°", abs(math.degrees(mid) - want) < 1e-6 and abs(y1 - mid) < 1e-9 and dt < 0.1, (math.degrees(mid), math.degrees(y1), dt))
    check("reduced motion: no page errors", not errs, errs)
    ctx.browser.close()

with sync_playwright() as p:
    for w in (1280, 390):
        for sch in ("light", "dark"): run(p, w, sch)
    reduced(p)
srv.shutdown()
for (w, sch, z), c in sorted(COVERAGE.items()):
    if sch == "dark": print(f"coverage {w} {z}: {c:.1%}")
print(f"{N[0] - len(FAILS)}/{N[0]} checks passed")
sys.exit(1 if FAILS else 0)
