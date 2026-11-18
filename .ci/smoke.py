"""Browser smoke test run before every Pages deploy: each page loads with no script errors, and a logged-out
visitor to the members pages lands on log in.   python3 .ci/smoke.py   (serves the repo root on :8811)"""
import functools, http.server, pathlib, re, sys, threading
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
    # Nav and footer links, clicked from the root and from a subfolder page: each must land on the page it names,
    # never silently on home (the iolin "iot API" bug). Links to io-threads.com itself are served from this checkout.
    import urllib.parse
    GATED = ("app.html", "looop.html", "ops.html")
    def norm(path): return "/" if path in ("", "/", "/index.html") else (path[:-5] if path.endswith(".html") else path).rstrip("/") or "/"
    for start in ("index.html", "iolin/"):
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.route(re.compile(r"^https://(www\.)?io-threads\.com/.*"), lambda route: route.continue_(url=BASE + urllib.parse.urlsplit(route.request.url).path.lstrip("/")))
        pg.goto(BASE + start); pg.wait_for_timeout(600)
        targets = pg.eval_on_selector_all("header a[href], nav a[href], footer a[href]",
            "els => els.map((e, i) => ({i, href: e.getAttribute('href'), abs: e.href, text: (e.getAttribute('aria-label') || e.textContent).trim().slice(0, 40), blank: e.target === '_blank'}))")
        for t in targets:
            u = urllib.parse.urlsplit(t["abs"])
            if u.scheme not in ("http", "https") or (u.hostname not in ("127.0.0.1", "io-threads.com", "www.io-threads.com")) or t["href"].startswith("#"): continue
            want = norm(u.path)
            if want == "/" and not re.fullmatch(r"(|io|io threads|home|home page|io threads home)", t["text"].lower().strip(" ·→←›‹")):
                fails.append(f"{start}: '{t['text']}' ({t['href']}) goes to the home page, but its words name another page"); continue
            q = b.new_page(viewport={"width": 1280, "height": 900})
            q.route(re.compile(r"^https://(www\.)?io-threads\.com/.*"), lambda route: route.continue_(url=BASE + urllib.parse.urlsplit(route.request.url).path.lstrip("/")))
            q.goto(BASE + start); q.wait_for_timeout(300)
            try:
                el = q.query_selector_all("header a[href], nav a[href], footer a[href]")[t["i"]]
                if t["blank"]: q.evaluate("e => e.removeAttribute('target')", el)
                with q.expect_navigation(timeout=10000): el.click(force=True)
                q.wait_for_timeout(200)
                got = norm(urllib.parse.urlsplit(q.url.replace("https://io-threads.com/", BASE)).path)
                ok = got == want or (want.lstrip("/") + ".html" in GATED or want.lstrip("/") in GATED) and got == "/login"
                if not ok: fails.append(f"{start}: '{t['text']}' ({t['href']}) landed on {got}, expected {want}")
            except Exception as e:
                fails.append(f"{start}: '{t['text']}' ({t['href']}) didn't navigate: {str(e)[:80]}")
            q.close()
        print(start, f"{len(targets)} nav/footer links clicked"); pg.close()
    b.close()
srv.shutdown()
for x in fails: print("FAIL", x)
sys.exit(1 if fails else 0)
