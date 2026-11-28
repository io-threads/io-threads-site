"""Checkout resend test for square-pay.js with Turnstile on, fully stubbed: Square's SDK, Cloudflare Turnstile and the
payment server are answered by Playwright routes, and every other off-box request is aborted, so nothing real is called.

    python3 .ci/paytest.py [port]   (default 8827; serves the repo root on 127.0.0.1)

Cases (the Starter card checkout on join.html, which posts /subscribe):
  1. lost reply -> captcha 403 on the resend -> the next click resends again: same idempotencyKey and card token,
     a fresh, unused Turnstile token each time (a refused resend must never switch to a new key).
  2. a definite failure (400, no keep) -> the next try gets a new idempotencyKey.
  3. a card form that rejects the input doesn't spend the Turnstile token: the retry goes through without a new check.
  4. a widget that keeps erroring shows "didn't load. Use Pay with Square below", not "Complete the security check".
"""
import functools, http.server, json, pathlib, re, sys, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8827
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE, fails = f"http://127.0.0.1:{PORT}/", []

PAY_LINKS = re.sub(r'turnstileSiteKey:\s*""', 'turnstileSiteKey: "1x00000000000000000000AA"', (ROOT / "pay-links.js").read_text())
assert "1x00000000000000000000AA" in PAY_LINKS, "pay-links.js: turnstileSiteKey slot not found"
CARD = ".way[data-plan=Builder]"; BOX = CARD + " .paybox"
API = re.search(r'api:\s*"([^"]+)"', PAY_LINKS).group(1)

SQUARE_STUB = """
var n = 0;
window.Square = { payments: function () { return {
  paymentRequest: function () { return {}; },
  card: function () { return Promise.resolve({ attach: function () { return Promise.resolve(); },
    tokenize: function () { return Promise.resolve(window.__cardOk ? { status: "OK", token: "cnon-" + (++n) }
      : { status: "Invalid", errors: [{ message: "Card number is not valid." }] }); } }); },
  applePay: function () { return Promise.reject(new Error("no")); },
  googlePay: function () { return Promise.reject(new Error("no")); } }; } };
"""
# mode "ok": issues ts-1, ts-2, ... (a new one on each reset). mode "error": calls error-callback, never issues one.
TS_STUB = """
(function () { var n = 0, w = {};
  window.turnstile = {
    render: function (sel, o) { w = o; setTimeout(issue, 0); return "w1"; },
    reset: function () { setTimeout(issue, 0); } };
  function issue() { if (window.__tsMode === "error") w["error-callback"](); else w.callback("ts-" + (++n)); }
})();
"""


def run_case(b, name, script, ts_mode="ok", card_ok=True):
    """script: list of server replies, one per request: "lost" | (status, json). Returns (page, bodies)."""
    pg = b.new_page(); bodies = []; replies = list(script); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
    pg.add_init_script(f"window.__tsMode = {json.dumps(ts_mode)}; window.__cardOk = {json.dumps(card_ok)};")

    def router(route):
        u = route.request.url
        if u.startswith(BASE):
            if u.split("?")[0].endswith("/pay-links.js"): return route.fulfill(body=PAY_LINKS, content_type="application/javascript")
            return route.continue_()
        if re.match(r"https://(sandbox\.)?web\.squarecdn\.com/v1/square\.js", u): return route.fulfill(body=SQUARE_STUB, content_type="application/javascript")
        if u.startswith("https://challenges.cloudflare.com/turnstile/"): return route.fulfill(body=TS_STUB, content_type="application/javascript")
        if u.startswith(API) and route.request.method == "POST":
            bodies.append(json.loads(route.request.post_data or "{}"))
            r = replies.pop(0) if replies else (500, {"ok": False, "error": "unexpected extra request"})
            if r == "lost": return route.abort()
            return route.fulfill(status=r[0], body=json.dumps(r[1]), content_type="application/json",
                                 headers={"Access-Control-Allow-Origin": "*"})
        if u.startswith(API): return route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "POST"})
        return route.abort()   # nothing leaves the box

    pg.route("**/*", router)
    pg.goto(BASE + "join.html"); pg.wait_for_timeout(300)
    pg.click(CARD + " .pay")
    pg.wait_for_selector(BOX + " .sq-go", timeout=5000)
    pg.fill(BOX + " input[type=email]", "buyer@example.com")
    pg.wait_for_timeout(300)
    if errs: fails.append(f"{name}: page errors {errs}")
    return pg, bodies


def click(pg):
    pg.wait_for_function("() => !document.querySelector('" + BOX + " .sq-go').disabled", timeout=5000)
    pg.click(BOX + " .sq-go"); pg.wait_for_timeout(250)
    return pg.eval_on_selector(BOX + " .sq-msg", "e => e.textContent") if pg.query_selector(BOX + " .sq-msg") else ""


def check(name, cond, detail=""):
    print(("ok  " if cond else "FAIL"), name, detail if not cond else "")
    if not cond: fails.append(f"{name} {detail}")


with sync_playwright() as p:
    b = p.chromium.launch()
    try:
        # 1. lost reply, captcha refusal on the resend, then a successful resend.
        pg, bodies = run_case(b, "captcha-resend", ["lost", (403, {"ok": False, "captcha": True, "error": "The security check expired. Try again."}), (200, {"ok": True, "activating": True})])
        for _ in range(3): click(pg)
        pg.wait_for_timeout(200)
        keys = [x.get("idempotencyKey") for x in bodies]; srcs = [x.get("cardToken") for x in bodies]; tts = [x.get("turnstileToken") for x in bodies]
        check("captcha-resend: three requests", len(bodies) == 3, f"got {len(bodies)}")
        check("captcha-resend: one idempotencyKey", len(bodies) == 3 and len(set(keys)) == 1 and keys[0], f"{keys}")
        check("captcha-resend: same card token", len(bodies) == 3 and len(set(srcs)) == 1, f"{srcs}")
        check("captcha-resend: a fresh Turnstile token each time", len(bodies) == 3 and all(tts) and len(set(tts)) == 3, f"{tts}")
        check("captcha-resend: done", "Card saved" in pg.inner_text(BOX))
        pg.close()

        # 2. a definite failure gives the next try a new key.
        pg, bodies = run_case(b, "definite-fail", [(400, {"ok": False, "error": "Card declined. Nothing was charged."}), (200, {"ok": True})])
        click(pg); click(pg); pg.wait_for_timeout(200)
        check("definite-fail: new key after a definite failure", len(bodies) == 2 and bodies[0]["idempotencyKey"] != bodies[1]["idempotencyKey"], f"{[x.get('idempotencyKey') for x in bodies]}")
        check("definite-fail: new card token", len(bodies) == 2 and bodies[0]["cardToken"] != bodies[1]["cardToken"])
        pg.close()

        # 3. a rejected card form doesn't spend the Turnstile token.
        pg, bodies = run_case(b, "card-reject", [(200, {"ok": True})], card_ok=False)
        m = click(pg)
        check("card-reject: card error shown", "not valid" in m, m)
        pg.evaluate("window.__cardOk = true")
        m = click(pg); pg.wait_for_timeout(200)
        check("card-reject: retry not blocked by the security check", "security check" not in m, m)
        check("card-reject: retry sent with the first token", len(bodies) == 1 and bodies[0].get("turnstileToken") == "ts-1", f"{[x.get('turnstileToken') for x in bodies]}")
        pg.close()

        # 4. a widget that only errors points the buyer at Pay with Square.
        pg, bodies = run_case(b, "ts-error", [], ts_mode="error")
        m = click(pg)
        check("ts-error: says the check didn't load", "didn't load" in m and "Pay with Square" in m, m)
        check("ts-error: nothing sent", not bodies, f"{len(bodies)}")
        pg.close()
    finally:
        b.close(); srv.shutdown()
for x in fails: print("FAIL", x)
sys.exit(1 if fails else 0)
