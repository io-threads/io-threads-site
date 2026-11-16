"""Browser smoke test run before every Pages deploy: each page loads with no script errors, and a logged-out
visitor to the members pages lands on log in.   python3 .ci/smoke.py   (serves the repo root on :8811)"""
import functools, http.server, pathlib, sys, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8811), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE, fails = "http://127.0.0.1:8811/", []

with sync_playwright() as p:
    b = p.chromium.launch()
    for f in sorted(x.name for x in ROOT.glob("*.html")):
        pg = b.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        r = pg.goto(BASE + f); pg.wait_for_timeout(900)
        errs = [e for e in errs if "Transition was skipped" not in e]
        if r.status != 200 or errs: fails.append(f"{f}: HTTP {r.status} {errs}")
        print(f, r.status, errs or "ok"); pg.close()
    for gated in ("app.html", "looop.html", "ops.html"):
        pg = b.new_page(); pg.goto(BASE + gated)
        try: pg.wait_for_url("**/login.html?next=" + gated + "*", timeout=10000); print(gated, "logged out -> login ok")
        except Exception: fails.append(f"{gated}: logged-out visitor not sent to login (at {pg.url})")
        pg.close()
    b.close()
srv.shutdown()
for x in fails: print("FAIL", x)
sys.exit(1 if fails else 0)
