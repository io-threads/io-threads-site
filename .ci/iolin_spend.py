# Run: python3 .ci/iolin_spend.py [screenshot-dir]
"""Spend panel test for the iolin window's sidebar: serves this checkout on a free port and drives /iolin/?test=1 in
headless Chromium. Checks the Spend section (under Production, folds like the others) meters this browser's runs (demo
tokens counted from the demo's own text, labelled not billed), that budgets are set in an inline editor with validation
and a signed budget_change event, and that a budget is enforced before a run the three ways the host does it: stop (a
refused run with a receipt whose spend.action_taken is stop, and a Needs-you card), approve (an inline card: approve
runs it, deny refuses it), and downgrade (in the demo the target can't run, so it stops; with the test stand-in for
the WebLLM module it switches model and the receipt says so). Receipts with spend still verify and tamper still fails.
Host mode runs against a stubbed host (page.route): GET /v1/spend and /v1/admin/budgets, PUT budgets, POST an approval;
the console token stays out of storage. Layout in dawn, twilight and dusk at 1280 and 390: no page errors, no sideways
page scroll."""
import functools, http.server, json, pathlib, re, socketserver, sys, threading
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
HOST = "http://127.0.0.1:18787"   # never contacted: every request to it is answered by page.route below
TOKEN = "console-token-test-0123456789abcdef"

def boot(pg, url=URL):
    pg.goto(url, wait_until="networkidle"); pg.wait_for_function("window.__iolin && __iolin.ready"); pg.wait_for_timeout(500)
    if pg.is_visible("#tSkip"): pg.click("#tSkip"); pg.wait_for_timeout(200)
def run(pg, cmd, wait=0):
    pg.evaluate("c => { __iolin.run(c); }", cmd)
    if wait: pg.wait_for_timeout(wait)
def last(pg): return pg.evaluate("__iolin.last()")
def term(pg): return pg.text_content("#tlog") or ""
def lastline(pg, has="receipt v"): return pg.evaluate("h => [...document.querySelectorAll('#tlog .ln')].map(d => d.textContent).filter(t => t.includes(h)).at(-1) || ''", has)
def sp(pg): return pg.evaluate("__iolinTest.spend()")
def cols(pg): return {c["name"]: c for c in pg.evaluate("[...document.querySelectorAll('#kb .kcol')].map(c => ({name: c.getAttribute('aria-label'), cards: [...c.querySelectorAll('.kc')].map(k => ({id: k.dataset.id, zone: k.dataset.zone, text: k.innerText.replace(/\\n/g, ' ')}))}))")}
def card(pg, col, pred): return [k for k in cols(pg)[col]["cards"] if pred(k)]
def hscroll(pg): return pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
def receipts_count(pg): return pg.evaluate("(async () => (await new Promise(r => { const q = indexedDB.open('iolin'); q.onsuccess = () => { const g = q.result.transaction('receipts').objectStore('receipts').count(); g.onsuccess = () => r(g.result); }; })))()")
def ask_and_wait(pg, q):
    before = last(pg)["run_id"] if last(pg) else None
    run(pg, "ask " + q)
    pg.wait_for_function("rid => __iolin.last() && __iolin.last().run_id !== rid", arg=before, timeout=15000)
    pg.wait_for_timeout(250); return last(pg)
def spend_open(pg):
    h = pg.locator(".side button.sh", has_text="Spend")
    if h.get_attribute("aria-expanded") == "false": h.click(); pg.wait_for_timeout(100)
def set_budgets(pg, rows):
    """Open the editor, replace every budget with `rows` (dicts of field -> value), save."""
    spend_open(pg)
    if pg.locator("#spend [data-sp=edit]").get_attribute("aria-expanded") != "true": pg.click("#spend [data-sp=edit]")
    while pg.locator("#spend [data-rm]").count(): pg.locator("#spend [data-rm]").first.click()
    for i, r in enumerate(rows):
        pg.click("#spend [data-sp=add]")
        for f, v in r.items():
            sel = f"#spend [data-row='{i}'] [data-f='{f}']"
            if pg.locator(sel).evaluate("e => e.tagName") == "SELECT": pg.select_option(sel, v)
            else: pg.fill(sel, str(v))
    pg.click("#spend [data-sp=save]"); pg.wait_for_timeout(300)

def spend_checks_receipt(r):
    s = r.get("spend") or {}
    ints = all(isinstance(s.get(k), int) for k in ("model_calls", "tokens_in", "tokens_out", "cost_micros"))
    bc_ok = all(isinstance(e["used"], int) and isinstance(e["limit"], int) and e["decision"] in ("ok", "warn", "over") for e in s.get("budgets_checked", []))
    fields = {"model_calls", "model", "tokens_in", "tokens_out", "usage_source", "usage_reason", "cost_micros", "currency", "cost_unit", "price_source", "price_table_digest", "budgets_checked", "action_taken"} <= set(s)
    return ints and bc_ok and fields, s

with sync_playwright() as p:
    b = p.chromium.launch()
    # ---------- 1280: browser source, budgets, the three enforcements ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    boot(pg)
    heads = pg.evaluate("[...document.querySelectorAll('.side > button.sh')].map(h => h.querySelector('span').textContent)")
    check("Spend section sits right under Production", "Spend" in heads and heads.index("Spend") == heads.index("Production") + 1, heads)
    h = pg.locator(".side button.sh", has_text="Spend")
    h.click(); pg.wait_for_timeout(100); folded = pg.is_hidden("#spend"); h.click(); pg.wait_for_timeout(100)
    check("Spend folds like the other sections", folded and pg.is_visible("#spend") and h.get_attribute("aria-expanded") == "true", "")
    check("no host: 'browser only', no host controls", pg.inner_text("#spMeta") == "browser only" and pg.locator("#spend .seg").count() == 0 and pg.locator("#spend [data-sp=refresh]").count() == 0, pg.inner_text("#spMeta"))
    check("no budgets yet says so", "No budgets in this browser" in pg.inner_text("#spend"), pg.inner_text("#spend")[:160])

    r = ask_and_wait(pg, "hello")
    ok, s = spend_checks_receipt(r)
    check("receipt carries spend with the host's field names (integers, cost in micros)", ok and s["action_taken"] == "none" and s["model_calls"] == 1, s)
    check("demo tokens counted from the demo's own text, cost 0, labelled not billed", s["tokens_in"] > 0 and s["tokens_out"] > 0 and s["cost_micros"] == 0 and s["usage_source"] == "demo-count" and "not billed" in s["usage_reason"], s)
    txt = pg.inner_text("#spend")
    check("panel: today's tokens in/out and cost", re.search(r"\d+\s*tokens in", txt) and "cost · USD" in txt and "demo, not billed" in txt and "Browser only" in txt, txt[:240])
    check("7-day sparkline with 7 days", pg.locator("#spend svg.spk rect").count() == 7 and "Tokens per UTC day" in pg.get_attribute("#spend svg.spk", "aria-label"), "")
    run(pg, "verify", 500); check("receipt with spend verifies", "· VALID" in lastline(pg, "ed25519") or "· VALID" in lastline(pg, "ecdsa"), lastline(pg))
    run(pg, "tamper", 500); check("tamper still fails", "INVALID" in lastline(pg) and "changed execution_mode" in lastline(pg), lastline(pg))
    run(pg, "verify", 400)

    # validation: nothing saved on a bad row, the errors say why
    spend_open(pg); pg.click("#spend [data-sp=edit]"); pg.click("#spend [data-sp=add]")
    pg.fill("#spend [data-row='0'] [data-f='limit']", "abc"); pg.fill("#spend [data-row='0'] [data-f='warn_pct']", "0"); pg.select_option("#spend [data-row='0'] [data-f='scope']", "model")
    pg.fill("#spend [data-row='0'] [data-f='match']", ""); pg.click("#spend [data-sp=save]"); pg.wait_for_timeout(200)
    et = pg.inner_text("#spend .spr .err") if pg.locator("#spend .spr .err").count() else ""
    check("validation: bad limit, warn % and empty match are refused inline", "Limit" in et and "Warn at" in et and "Match" in et and sp(pg)["budgets"] == [] and "Nothing was saved" in pg.inner_text("#spend"), et)
    check("no browser alert/prompt used (inline editor)", pg.locator("#spend .sped").count() == 1, "")
    pg.click("#spend [data-sp=cancel]")

    # 1-token stop budget: the next ask is refused with a receipt (action_taken stop) and a Needs-you card
    set_budgets(pg, [{"id": "tiny", "limit": "1", "action": "stop"}])
    st = sp(pg)
    check("budget saved with a signed budget_change event", st["budgets"] and st["budgets"][0]["tokens"] == 1 and st["events"][-1]["event"] == "budget_change", st["budgets"])
    run(pg, "spend events", 500); check("spend events verify (signed)", "budget_change" in term(pg)[-300:] and "VALID" in term(pg)[-300:], term(pg)[-200:])
    check("bar shows over (state + red bar)", pg.locator("#spend .spb.over").count() == 1 and "over" in pg.inner_text("#spend .spb.over .st").lower(), pg.inner_text("#spend .spb").replace("\n", " "))
    n0 = receipts_count(pg)
    r = ask_and_wait(pg, "hello")
    ok, s = spend_checks_receipt(r)
    check("ask hello is refused before the model runs", r["status"] == "refused" and "refused" in term(pg)[-400:] and "action_taken stop" in term(pg)[-400:], term(pg)[-200:])
    check("refused receipt: spend.action_taken stop, model_calls 0, the over budget listed", ok and s["action_taken"] == "stop" and s["model_calls"] == 0 and s["tokens_in"] == 0 and any(e["id"] == "tiny" and e["decision"] == "over" for e in s["budgets_checked"]), s)
    check("a receipt was stored for the refusal", receipts_count(pg) == n0 + 1, (n0, receipts_count(pg)))
    run(pg, "verify", 500); check("refused receipt verifies", r["run_id"][:8] in lastline(pg) and "· VALID" in lastline(pg) and "changed" not in lastline(pg), lastline(pg))
    run(pg, "tamper", 500); check("tampered refused receipt fails", r["run_id"][:8] in lastline(pg) and "INVALID" in lastline(pg), lastline(pg))
    run(pg, "verify", 400)
    rid = r["run_id"][:8]
    need = card(pg, "Needs you", lambda k: rid in k["text"])
    check("refusal is a Needs-you card with its receipt", need and "stopped · over budget" in need[0]["text"] and "budget tiny" in need[0]["text"], need)
    bud = card(pg, "Needs you", lambda k: k["id"].startswith("sp-browser-tiny"))
    check("the reached stop budget is a Needs-you card", bud and "Budget tiny reached" in bud[0]["text"] and "next run is refused" in bud[0]["text"], bud)
    check("spend cards' chips link to Builds · runs", all(k["zone"] == "runs" for k in need + bud) and "▤ spend · Runs" in bud[0]["text"], [k["text"][-40:] for k in need + bud])
    pg.locator(f"#kb .kc[data-id^='sp-browser-tiny'] .kc-iot").click(); pg.wait_for_timeout(400)
    check("chip focuses the Builds · runs zone", pg.input_value("#zsel") == "runs", pg.input_value("#zsel"))
    pg.locator("#bFilt").click(); pg.wait_for_timeout(150)
    acts = pg.inner_text("#spend .spact")
    check("last actions list the stop with its receipt id", "stop" in acts and rid in acts, acts)
    pg.locator(f"#spend .spact button", has_text=rid).click(); pg.wait_for_timeout(300)
    check("an action links to its receipt (opens it in Output)", r["run_id"] in (pg.text_content("#outPane") or ""), (pg.text_content("#outPane") or "")[:80])
    pg.click('.ttab[data-t="board"]')

    # approve: an inline card, no dialog; approve runs it, deny refuses it
    set_budgets(pg, [{"id": "ask1", "limit": "1", "action": "approve"}])
    dialogs = []; pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    before = last(pg)["run_id"]; run(pg, "ask hello", 600)
    check("over an approve budget, the run waits with an inline card", pg.locator("#spend .spask").count() == 1 and sp(pg)["pending"] and last(pg)["run_id"] == before, pg.inner_text("#spend")[:200])
    check("…and a Needs-you card", card(pg, "Needs you", lambda k: k["id"] == "sp-ask" and "needs approval" in k["text"]), "")
    if SHOTS: pg.locator("#spend").screenshot(path=str(SHOTS / "spend_1280_approve_card.png"))
    pg.click("#spend [data-sp=approve]")
    pg.wait_for_function("rid => __iolin.last().run_id !== rid", arg=before, timeout=15000); pg.wait_for_timeout(300)
    r = last(pg); check("Approve runs it: receipt action_taken approved", r["status"] == "completed" and r["spend"]["action_taken"] == "approved" and r["spend"]["model_calls"] == 1, r["spend"])
    before = r["run_id"]; run(pg, "ask hello again", 600); pg.click("#spend [data-sp=deny]")
    pg.wait_for_function("rid => __iolin.last().run_id !== rid", arg=before, timeout=15000); pg.wait_for_timeout(300)
    r = last(pg); check("Deny refuses it: receipt action_taken approve_denied", r["status"] == "refused" and r["spend"]["action_taken"] == "approve_denied" and r["spend"]["model_calls"] == 0, r["spend"])
    check("no browser dialogs at all", not dialogs, dialogs)
    before = last(pg)["run_id"]; run(pg, "ask typed approve", 600); run(pg, "spend approve")
    pg.wait_for_function("rid => __iolin.last().run_id !== rid", arg=before, timeout=15000); pg.wait_for_timeout(200)
    check("spend approve from the terminal works too", last(pg)["spend"]["action_taken"] == "approved", last(pg)["spend"]["action_taken"])

    # warning at warn %: a Needs-you card while the budget is past it
    used = sum((x["tokens_in"] or 0) + (x["tokens_out"] or 0) for x in sp(pg)["ledger"] if x["made"] and x["kind"] == "model")
    set_budgets(pg, [{"id": "soft", "limit": str(used * 2), "warn_pct": "40", "action": "stop"}])
    w = card(pg, "Needs you", lambda k: k["id"].startswith("sp-browser-soft"))
    check("a budget past its warn % is a Needs-you card", w and "Budget soft at 50%" in w[0]["text"] and "budget warning" in w[0]["text"], w)
    check("bar shows warn", pg.locator("#spend .spb.warn").count() == 1, "")
    r = ask_and_wait(pg, "warn check"); check("a run under the limit still goes ahead (warn only)", r["spend"]["action_taken"] == "none" and any(e["decision"] == "warn" for e in r["spend"]["budgets_checked"]), r["spend"]["budgets_checked"])
    check("signed spend_warning event recorded", any(e["event"] == "spend_warning" and e["budget_id"] == "soft" for e in sp(pg)["events"]), "")

    # downgrade in the demo: only the demo engine runs here, so the switch can't happen and the run stops (host rule)
    set_budgets(pg, [{"id": "dg", "limit": "1", "action": "downgrade", "downgrade_to": "Qwen3-0.6B-q4f16_1-MLC"}])
    check("downgrade_to offers the page's model list", pg.locator("#spend [data-sp=edit]").count() == 1 and sp(pg)["budgets"][0]["downgrade_to"] == "Qwen3-0.6B-q4f16_1-MLC", sp(pg)["budgets"])
    r = ask_and_wait(pg, "hello")
    check("demo: downgrade target can't run, so it stops (receipt says why)", r["spend"]["action_taken"] == "stop" and "not a model this page can run" in r.get("status", "") + json.dumps(r["spend"]) + term(pg)[-400:], term(pg)[-200:])
    if SHOTS:
        set_budgets(pg, [{"id": "day", "limit": "5000", "action": "stop"}, {"id": "ask", "scope": "task_kind", "match": "ask", "unit": "calls", "limit": "40", "action": "approve", "warn_pct": "10"}, {"id": "dg", "limit": "1", "action": "downgrade", "downgrade_to": "Qwen3-0.6B-q4f16_1-MLC"}])
        pg.locator(".side").screenshot(path=str(SHOTS / "spend_1280_sidebar.png"))
        pg.click("#spend [data-sp=edit]"); pg.wait_for_timeout(150); pg.locator("#spend").screenshot(path=str(SHOTS / "spend_1280_editor.png")); pg.click("#spend [data-sp=cancel]")
        pg.locator("#kb").screenshot(path=str(SHOTS / "spend_1280_board.png"))
    check("no page errors (browser flow)", not errs, errs)
    ctx.close()

    # ---------- downgrade that switches: the test stand-in for the WebLLM module (no WebGPU in headless) ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    boot(pg, URL + "&live=1&worker=0")
    pg.evaluate("__iolinTest.stubWebLLM()"); run(pg, "model load Llama-3.2-3B-Instruct-q4f16_1-MLC")
    pg.wait_for_function("document.getElementById('tModel').textContent.includes('Llama')", timeout=8000)
    r = ask_and_wait(pg, "hello")
    check("live: tokens come from the model's reported usage", r["spend"]["usage_source"] == "webllm usage" and r["spend"]["tokens_in"] == 7 and r["spend"]["tokens_out"] == 4 and r["spend"]["cost_micros"] == 0, r["spend"])
    set_budgets(pg, [{"id": "dg", "limit": "1", "action": "downgrade", "downgrade_to": "Qwen3-0.6B-q4f16_1-MLC"}])
    r = ask_and_wait(pg, "hello")
    check("downgrade switches to the smaller model before the run", r["model_manifest"]["model_id"] == "Qwen3-0.6B-q4f16_1-MLC" and r["spend"]["action_taken"] == "downgrade" and r["spend"]["downgraded_from"] == "Llama-3.2-3B-Instruct-q4f16_1-MLC", (r["model_manifest"]["model_id"], r["spend"]))
    dn = card(pg, "Done", lambda k: r["run_id"][:8] in k["text"])
    check("downgraded run is a Done card with a note", dn and "switched model" in dn[0]["text"] and "switched from Llama" in dn[0]["text"], dn)
    run(pg, "verify", 500); check("downgraded receipt verifies", r["run_id"][:8] in lastline(pg) and "· VALID" in lastline(pg) and "changed" not in lastline(pg), lastline(pg))
    run(pg, "tamper", 500); check("…and tamper fails", r["run_id"][:8] in lastline(pg) and "INVALID" in lastline(pg), lastline(pg))
    r = ask_and_wait(pg, "again")
    check("already on the smaller model: keeps running there", r["model_manifest"]["model_id"] == "Qwen3-0.6B-q4f16_1-MLC" and r["status"] == "completed", r["spend"]["action_taken"])
    set_budgets(pg, [{"id": "dg", "limit": "1", "action": "downgrade", "downgrade_to": "Qwen3-0.6B-q4f16_1-MLC", "hard_stop_pct": "100"}])
    r = ask_and_wait(pg, "past hard stop"); check("past hard_stop_pct it stops", r["spend"]["action_taken"] == "stop", r["spend"]["action_taken"])
    check("no page errors (downgrade flow)", not errs, errs)
    ctx.close()

    # ---------- host source against a stubbed host ----------
    ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    SEEN = {"put": None, "post": None, "hdr": set()}
    days = ["2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"]
    HB = [{"id": "day", "scope": "host", "match": None, "period": "day", "tokens": 2000000, "cost_micros": None, "calls": None, "action": "downgrade", "downgrade_to": "qwen2.5:0.5b", "hard_stop_pct": 150, "warn_pct": 80, "note": "", "cost": None},
          {"id": "cloud", "scope": "cloud", "match": None, "period": "day", "tokens": None, "cost_micros": 2000000, "calls": None, "action": "stop", "warn_pct": 80, "note": "", "cost": "2.00"}]
    SPEND = {"currency": "USD", "today": {"day": days[-1], "calls": 41, "tokens_in": 1200000, "tokens_out": 510000, "cost_micros": 1700000, "cost": "1.70", "cache_hits": 3, "unmetered_calls": 1},
             "last_7_days": {"by_day": {d: {"tokens_in": 100000 * (i + 1), "tokens_out": 40000 * (i + 1)} for i, d in enumerate(days)}},
             "budgets": [{**HB[0], "subject": "host", "used": {"tokens": 1710000}, "limit": {"tokens": 2000000}, "pct": {"tokens": 85}, "state": "warn"},
                         {**HB[1], "subject": "cloud", "used": {"cost_micros": 1700000}, "limit": {"cost_micros": 2000000}, "pct": {"cost_micros": 85}, "state": "warn"}],
             "pending_approvals": [{"id": "ap_1a2b3c", "kind": "spend", "reason": "budget agent (agent:folder-briefing@0.1) tokens used 500100 of 500000", "run_id": "run_77", "status": "pending"}]}
    LEDGER = {"rows": [{"at": days[-1] + "T10:00:00Z", "t": 0, "run_id": "run_70", "model": "llama3.2:3b", "cache_hit": True, "downgraded_from": None},
                       {"at": days[-1] + "T11:00:00Z", "t": 0, "run_id": "run_71", "model": "qwen2.5:0.5b", "cache_hit": False, "downgraded_from": "llama3.2:3b"}]}
    CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET, PUT, POST, OPTIONS"}
    def host(route):
        rq = route.request; path = rq.url.split("18787", 1)[1]
        if rq.method == "OPTIONS": return route.fulfill(status=204, headers=CORS)
        if path.startswith("/v1/status"): return route.fulfill(json={"runtime": {"models": ["llama3.2:3b", "qwen2.5:0.5b"]}}, headers=CORS)
        tok = rq.headers.get("x-iolin-console"); SEEN["hdr"].add(tok)
        if tok != TOKEN: return route.fulfill(status=401, json={"detail": "admin token required"}, headers=CORS)
        if path.startswith("/v1/spend/ledger"): return route.fulfill(json=LEDGER, headers=CORS)
        if path.startswith("/v1/spend"): return route.fulfill(json=SPEND, headers=CORS)
        if path.startswith("/v1/admin/budgets") and rq.method == "PUT": SEEN["put"] = json.loads(rq.post_data); return route.fulfill(json={"budgets": SEEN["put"]["budgets"], "warnings": []}, headers=CORS)
        if path.startswith("/v1/admin/budgets"): return route.fulfill(json={"budgets": HB, "prices": {"currency": "USD"}, "cache": {"enabled": True}}, headers=CORS)
        if path.startswith("/v1/approvals/"): SEEN["post"] = (path, json.loads(rq.post_data)); SPEND["pending_approvals"] = []; return route.fulfill(json={"approval": {"status": "approved"}}, headers=CORS)
        return route.fulfill(status=404, json={}, headers=CORS)
    pg.route(re.compile(r"^http://127\.0\.0\.1:18787/.*"), host)
    boot(pg)
    check("before pairing: browser only", pg.inner_text("#spMeta") == "browser only", "")
    spend_open(pg); pg.click("#spend [data-sp=edit]"); pg.click("#spend .sphost summary")
    pg.fill("#spHostUrl", HOST); pg.fill("#spHostTok", "wrong-token"); pg.click("#spend [data-sp=connect]"); pg.wait_for_timeout(600)
    check("wrong token: the host's 401 is shown, still browser only", "401" in pg.inner_text("#spend") and pg.inner_text("#spMeta") == "browser only", pg.inner_text("#spend")[-200:])
    pg.fill("#spHostTok", TOKEN); pg.click("#spend [data-sp=connect]"); pg.wait_for_timeout(800)
    txt = pg.inner_text("#spend")
    check("paired: host source with GET /v1/spend numbers", pg.inner_text("#spMeta") == "host" and "1,200,000" in txt and "510,000" in txt and "1.70" in txt and "3 cache hits" in txt, txt[:260])
    check("host bars from the host's budgets (warn)", pg.locator("#spend .spb.warn").count() == 2 and "then switch to qwen2.5:0.5b" in txt, "")
    check("host last actions: cache hit and downgrade", "cache hit" in pg.inner_text("#spend .spact") and "llama3.2:3b → qwen2.5:0.5b" in pg.inner_text("#spend .spact"), pg.inner_text("#spend .spact"))
    check("host pending approval is an inline card and a Needs-you card", pg.locator("#spend .spask [data-ap='ap_1a2b3c']").count() == 2 and card(pg, "Needs you", lambda k: k["id"] == "sp-hap-ap_1a2b3c"), "")
    check("host warnings are Needs-you cards", card(pg, "Needs you", lambda k: k["id"].startswith("sp-host-day") and "at 85%" in k["text"]), [k["id"] for k in cols(pg)["Needs you"]["cards"]])
    stored = pg.evaluate("""(async () => { const ls = JSON.stringify(Object.entries(localStorage)); const kv = await new Promise(r => { const q = indexedDB.open('iolin'); q.onsuccess = () => { const g = q.result.transaction('kv').objectStore('kv').getAll(); g.onsuccess = () => r(JSON.stringify(g.result)); }; }); return ls + kv; })()""")
    check("console token is in no storage (tab memory only), the URL is", TOKEN not in stored and HOST in stored and sp(pg)["host"]["hasToken"], len(stored))
    if SHOTS: pg.locator("#spend").screenshot(path=str(SHOTS / "spend_1280_host.png"))
    # edit host budgets: PUT the whole set
    spend_open(pg); pg.click("#spend [data-sp=edit]")
    check("host editor shows the host's budgets and scopes", pg.input_value("#spend [data-row='0'] [data-f='id']") == "day" and pg.locator("#spend [data-row='1'] [data-f='scope'] option[value=cloud]").count() == 1 and pg.input_value("#spend [data-row='1'] [data-f='limit']") == "2.00", "")
    pg.fill("#spend [data-row='1'] [data-f='limit']", "3.25"); pg.click("#spend [data-sp=save]"); pg.wait_for_timeout(600)
    put = SEEN["put"] or {}
    check("Save sends PUT /v1/admin/budgets with the whole set", put and [x["id"] for x in put["budgets"]] == ["day", "cloud"] and put["budgets"][1]["cost_micros"] == 3250000 and put["budgets"][0]["downgrade_to"] == "qwen2.5:0.5b" and "match" not in put["budgets"][0], put)
    check("host change is a signed local event too", sp(pg)["events"][-1]["event"] == "budget_change" and sp(pg)["events"][-1]["source"] == "host", "")
    pg.locator("#spend .spask [data-ap='ap_1a2b3c'][data-vd=approve]").click(); pg.wait_for_timeout(600)
    check("Approve on a host card sends POST /v1/approvals/{id}", SEEN["post"] and SEEN["post"][0] == "/v1/approvals/ap_1a2b3c" and SEEN["post"][1] == {"verdict": "approve"} and pg.locator("#spend .spask").count() == 0, SEEN["post"])
    pg.click("#spend [data-src=browser]"); pg.wait_for_timeout(200)
    check("switch back to Browser source", "browser · host paired" == pg.inner_text("#spMeta") and "Browser only" in pg.inner_text("#spend"), pg.inner_text("#spMeta"))
    pg.click("#spend [data-sp=edit]"); pg.click("#spend [data-sp=forget]"); pg.wait_for_timeout(200)
    check("Forget host: back to browser only, host controls hidden", pg.inner_text("#spMeta") == "browser only" and pg.locator("#spend .seg").count() == 0 and not sp(pg)["host"]["hasToken"], "")
    check("no page errors (host flow)", not errs, errs)
    ctx.close()

    # ---------- themes x widths ----------
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
    for env, scheme in (("dawn", "light"), ("twilight", "dark"), ("dusk", "dark")):
        for w in (1280, 390):
            kw = dict(viewport={"width": w, "height": 900 if w == 1280 else 844}, color_scheme=scheme)
            if w == 390: kw.update(user_agent=IPHONE, is_mobile=True, has_touch=True, device_scale_factor=2)
            ctx = b.new_context(**kw)
            ctx.add_init_script(f"try {{ localStorage.setItem('iot-site-theme', '{env}'); localStorage.setItem('iolin-orbit-hint', 'done'); }} catch (e) {{}}")
            pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            boot(pg); tag = f"{env} {w}"
            if w == 390 and "full" not in (pg.get_attribute("body", "class") or ""): pg.click("#fullBtn"); pg.wait_for_timeout(400)
            if w == 390: check(f"{tag}: Spend starts folded on a phone, like the others", pg.locator(".side button.sh", has_text="Spend").get_attribute("aria-expanded") == "false", "")
            ask_and_wait(pg, "hello")
            set_budgets(pg, [{"id": "day", "limit": "60", "action": "stop"}, {"id": "ask", "scope": "task_kind", "match": "ask", "unit": "calls", "limit": "3", "action": "approve", "warn_pct": "20"}])
            check(f"{tag}: theme applied", pg.get_attribute("#win", "data-env") == env, "")
            check(f"{tag}: panel renders (bars, sparkline, Set budgets)", pg.is_visible("#spend") and pg.locator("#spend .spb").count() == 2 and pg.locator("#spend svg.spk").count() == 1 and pg.is_visible("#spend [data-sp=edit]"), "")
            fg = pg.evaluate("getComputedStyle(document.querySelector('#spend .sptoday b')).color"); bg = pg.evaluate("getComputedStyle(document.getElementById('spend')).backgroundColor")
            check(f"{tag}: follows the window palette", fg != bg and bg == pg.evaluate("getComputedStyle(document.querySelector('.prod')).backgroundColor"), (fg, bg))
            inside = pg.evaluate("(() => { const s = document.getElementById('spend').getBoundingClientRect(); return [...document.querySelectorAll('#spend *')].every(e => { const r = e.getBoundingClientRect(); return !r.width || (r.left >= s.left - 1 && r.right <= s.right + 1); }); })()")
            check(f"{tag}: nothing spills out of the panel", inside, "")
            pg.click("#spend [data-sp=edit]"); pg.wait_for_timeout(150)
            inside = pg.evaluate("(() => { const s = document.getElementById('spend').getBoundingClientRect(); return [...document.querySelectorAll('#spend .sped *')].every(e => { const r = e.getBoundingClientRect(); return !r.width || (r.left >= s.left - 1 && r.right <= s.right + 1); }); })()")
            check(f"{tag}: editor fits the panel", inside, "")
            check(f"{tag}: no sideways page scroll", not hscroll(pg), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
            if SHOTS:
                pg.locator("#spend").screenshot(path=str(SHOTS / f"spend_{w}_{env}_editor.png")); pg.click("#spend [data-sp=edit]"); pg.wait_for_timeout(150)
                pg.locator("#spend").scroll_into_view_if_needed(); pg.locator("#spend").screenshot(path=str(SHOTS / f"spend_{w}_{env}.png"))
                if w == 1280: pg.locator("#win").screenshot(path=str(SHOTS / f"spend_{w}_{env}_window.png"))
            check(f"{tag}: no page errors", not errs, errs)
            ctx.close()
    b.close()
srv.shutdown()
print(f"\n{N[0] - len(FAILS)}/{N[0]} passed")
for f in FAILS: print("FAIL", f)
sys.exit(1 if FAILS else 0)
