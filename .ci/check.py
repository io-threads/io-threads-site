#!/usr/bin/env python3
"""Checks the published site before every GitHub Pages deploy (CI copy of ~/Projects/iothreads-site/check.py).

    python3 .ci/check.py    # exit 1 on any FAIL

Checks: honesty grep (sales-copy gate), internal links and anchors resolve,
one h1 per page, unique titles and descriptions, description length, alt text
on images, JSON-LD parses, lang set, only allowed slots remain, payment destinations pinned.
"""
import html, json, pathlib, re, sys
from html.parser import HTMLParser

# live/ is what GitHub Pages serves (io-threads.com); dist/ is the old GoDaddy build. Pass --dist to check that instead.
DIST = pathlib.Path(__file__).resolve().parent.parent  # the repo root is what Pages serves
ALLOWED_SLOTS = {"[YOUR TWO-LINE BACKGROUND]"}
# Sample data and merch rewards on the sample report, not offer prices (operator 11-15). Any other $ value still fails.
SAMPLE_PRICES = {"sample-report.html": {"$5,200", "$28", "$64", "$32", "$1"}}
HONESTY = re.compile(r"trusted by|clients? (say|love|trust)|guarantee|certified|compliant with|world-class|best-in-class|"
                     r"seamless|revolution|cutting-edge|unlock|leverage|most clients|we've helped|our clients|attestation|public data|deterministic|filing-grade|regulatory-grade|certificate|"
                     r"free (?:api|tier|keys?|plan)\b", re.I)   # no free API plan since 2026-11-18 (accounts are free)
# Allowed only inside an explicit denial (e.g. "doesn't certify compliance").
DENIAL = re.compile(r"(isn't|aren't|doesn't|not|no)\b[^.]{0,60}$", re.I)


# Payment destinations (purple-team M5). pay-links.js decides where money goes: the hosted square.link checkouts, and
# for in-page checkout the Square app, location and the server that charges the card. A swapped value sends buyers'
# money elsewhere (or charges them the wrong plan's price), so pay-links.js is PARSED (not pattern-matched) and must equal
# PAY_EXPECTED exactly: every key in its slot, every value a plain string, no duplicate keys, nothing else. Changing a
# link, the Square app or location, or the payment server fails CI unless PAY_EXPECTED is edited in the same commit, in
# plain sight of review.
PAY_SDK = {"appId": "sq0idp-1s8ZblRtSjareUcO7Q6X9Q", "locationId": "L61Q2TYHHTM3G", "api": "https://tckvatqkjfrvavleunzk.supabase.co/functions/v1"}
PAY_EXPECTED = {
    "stripe": {"Builder": {"m": "", "y": ""}, "Buyer": {"m": "", "y": ""}, "Partner": {"m": "", "y": ""}, "Lifetime": ""},
    "square": {
        "Builder": {"m": "https://square.link/u/xIlkX7Cb", "y": ""},   # Builder monthly
        "Buyer": {"m": "https://square.link/u/gKoiSiI1", "y": ""},     # Buyer monthly
        "Partner": {"m": "https://square.link/u/gYnG7De1", "y": ""},   # Partner monthly
        "Lifetime": "",
    },
    "portal": "",
    "sdk": PAY_SDK,   # Square application id (production), location id, production payment server
}


def _pay_values(t):
    if isinstance(t, dict):
        for v in t.values(): yield from _pay_values(v)
    elif t: yield t


# Every non-empty value above: the only payment destinations any served file may name.
PAY_ALLOWED = set(_pay_values(PAY_EXPECTED))
# Values that name a payment destination wherever they appear in a served page or script.
PAY_SHAPES = re.compile(r"https?://(?:square\.link|checkout\.square\.site|buy\.stripe\.com)/[^\s\"'<>)]*|\b(?:sandbox-)?sq0id[a-z]-[A-Za-z0-9_-]+|"
                        r"https://[a-z0-9]+\.supabase\.co/functions/v1\b")
# Files that may mention IOT_PAY at all: the config, and the two readers. Nobody else touches the payment config.
PAY_READERS = {"square-pay.js", "join.html"}


class PayParseError(ValueError):
    pass


def parse_pay_links(src):
    """pay-links.js as a Python dict, or PayParseError. The file must be exactly `window.IOT_PAY = <object>;` where the
    object holds only identifier or quoted keys (each once) and plain quoted-string or object values."""
    # Comments may mention anything; only code counts. Strings are matched first so "https://" isn't read as a comment.
    code = re.sub(r"(\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')|/\*.*?\*/|//[^\n]*", lambda m: m.group(1) or " ", src, flags=re.S)
    m = re.fullmatch(r"\s*window\.IOT_PAY\s*=\s*(\{.*\})\s*;?\s*", code, flags=re.S)
    if not m: raise PayParseError("must be exactly one 'window.IOT_PAY = {...};' and nothing else")
    toks, i, body = [], 0, m.group(1)
    tok = re.compile(r"\s+|(\"[^\"\\\n]*\"|'[^'\\\n]*')|([A-Za-z_$][A-Za-z0-9_$]*)|([{}:,])")
    while i < len(body):
        t = tok.match(body, i)
        if not t: raise PayParseError(f"unexpected {body[i:i + 20]!r} (only quoted strings, keys, braces, colons, commas)")
        i = t.end()
        if t.group(1): toks.append(("str", t.group(1)[1:-1]))
        elif t.group(2): toks.append(("id", t.group(2)))
        elif t.group(3): toks.append((t.group(3), t.group(3)))
    pos = 0

    def take(kind):
        nonlocal pos
        if pos >= len(toks) or toks[pos][0] != kind:
            got = toks[pos][1] if pos < len(toks) else "end of file"
            raise PayParseError(f"expected {kind!r}, got {got!r} (values must be plain quoted strings)")
        pos += 1
        return toks[pos - 1][1]

    def obj():
        take("{"); out = {}
        while True:
            if pos < len(toks) and toks[pos][0] == "}": pos_close(); return out
            k = toks[pos][1] if pos < len(toks) and toks[pos][0] in ("id", "str") else None
            if k is None: raise PayParseError("expected a key")
            advance()
            if k in out: raise PayParseError(f"duplicate key {k!r} (in JS the last one wins)")
            take(":")
            if pos < len(toks) and toks[pos][0] == "{": out[k] = obj()
            else: out[k] = take("str")
            if pos < len(toks) and toks[pos][0] == ",":
                advance()
                if pos < len(toks) and toks[pos][0] == "}": raise PayParseError("trailing comma")
            elif pos < len(toks) and toks[pos][0] == "}": pos_close(); return out
            else: raise PayParseError("expected ',' or '}'")

    def advance():
        nonlocal pos
        pos += 1

    def pos_close():
        take("}")

    tree = obj()
    if pos != len(toks): raise PayParseError("text after the object")
    return tree


def _pay_diff(want, got, path=""):
    if isinstance(want, dict):
        if not isinstance(got, dict): return [f"{path or 'IOT_PAY'} must be an object"]
        out = [f"{path}{'.' if path else ''}{k}: missing" for k in want if k not in got]
        out += [f"{path}{'.' if path else ''}{k}: not allowed (not in PAY_EXPECTED)" for k in got if k not in want]
        for k in want:
            if k in got: out += _pay_diff(want[k], got[k], f"{path}{'.' if path else ''}{k}")
        return out
    return [] if got == want else [f"{path} must be {want!r} (got {got!r})"]


def pay_links_fails(src, name="pay-links.js"):
    """Everything wrong with a pay-links.js source against PAY_EXPECTED (empty list = OK)."""
    try:
        tree = parse_pay_links(src)
    except PayParseError as e:
        return [f"{name}: {e} - payment config must be plain quoted strings (PAY_EXPECTED in .ci/check.py)"]
    return [f"{name}: {d} (PAY_EXPECTED in .ci/check.py)" for d in _pay_diff(PAY_EXPECTED, tree)]


# A write to the payment config: assignment (= += ||= ...), Object.assign/defineProperty/defineProperties/setPrototypeOf
# or Reflect.set/defineProperty with IOT_PAY in the arguments, or delete.
PAY_WRITE = re.compile(r"\bIOT_PAY\b(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]))*\s*(?:[-+*/%&|^]|\|\||&&|\?\?|<<|>>>?|\*\*)?=(?!=)"
                       r"|\b(?:Object\.(?:assign|defineProperty|defineProperties|setPrototypeOf)|Reflect\.(?:set|defineProperty|deleteProperty))\s*\([^)]*\bIOT_PAY\b"
                       r"|\bdelete\s+[\w$.\[\]\s]*\bIOT_PAY\b")
PAY_LOAD = re.compile(r'<script src="pay-links\.js"></script>\s*<script src="square-pay\.js"></script>')


def pay_use_fails(root):
    """Only pay-links.js writes IOT_PAY; only PAY_READERS read it, without writing; join.html loads pay-links.js then
    square-pay.js (which freezes it) with nothing in between."""
    fails = []
    for g in sorted(set(root.glob("**/*.html")) | set(root.glob("**/*.js"))):
        if ".git" in g.parts or ".ci" in g.parts or ".github" in g.parts or g == root / "pay-links.js": continue
        src, rel = g.read_text(errors="ignore"), str(g.relative_to(root))
        if not re.search(r"IOT_PAY", src): continue
        if rel not in PAY_READERS:
            fails.append(f"{rel}: mentions IOT_PAY; only pay-links.js (writes) and {', '.join(sorted(PAY_READERS))} (read) may")
            continue
        for m in PAY_WRITE.finditer(src):
            fails.append(f"{rel}: writes the payment config ({m.group(0)[:60]!r}); only pay-links.js may")
    join = root / "join.html"
    if join.exists():
        j = join.read_text(errors="ignore")
        if len(PAY_LOAD.findall(j)) != 1 or j.count('src="pay-links.js"') != 1 or j.count('src="square-pay.js"') != 1:
            fails.append('join.html: must load <script src="pay-links.js"></script> then <script src="square-pay.js"></script> once, nothing in between')
    sp = root / "square-pay.js"
    if sp.exists() and "deepFreeze(window.IOT_PAY)" not in sp.read_text(errors="ignore"):
        fails.append("square-pay.js: must freeze window.IOT_PAY before reading it (deepFreeze(window.IOT_PAY))")
    return fails


def pay_destination_fails(root):
    """pay-links.js pinned, IOT_PAY written nowhere else, and no other served page or script carries a payment
    destination off the allow-list."""
    f = root / "pay-links.js"
    if not f.exists(): return ["pay-links.js: missing"]
    fails = pay_links_fails(f.read_text()) + pay_use_fails(root)
    for g in sorted(root.glob("*.html")) + sorted(root.glob("*.js")) + sorted(root.glob("**/*.html")) + sorted(root.glob("**/*.js")):
        if g == f or ".git" in g.parts or ".ci" in g.parts or ".github" in g.parts: continue
        for m in set(PAY_SHAPES.findall(g.read_text(errors="ignore"))):
            if m not in PAY_ALLOWED: fails.append(f"{g.relative_to(root)}: payment destination {m!r} is not on the allow-list (PAY_EXPECTED in .ci/check.py)")
    return sorted(set(fails))


def pay_self_test():
    """The pin itself: the real files pass, each kind of swap fails."""
    import shutil, tempfile
    real = (DIST / "pay-links.js").read_text()
    sdk_line = 'api: "https://tckvatqkjfrvavleunzk.supabase.co/functions/v1"'
    swaps = {
        "hosted link": real.replace("xIlkX7Cb", "EvIl0000"),
        "app id": real.replace("sq0idp-1s8ZblRtSjareUcO7Q6X9Q", "sq0idp-AttackerApp000000000"),
        "location": real.replace("L61Q2TYHHTM3G", "LATTACKER0000"),
        "api": real.replace("tckvatqkjfrvavleunzk.supabase.co", "evil.example"),
        "api blanked to an allowed value": real.replace(sdk_line, 'api: "L61Q2TYHHTM3G"'),
        "built string": real.replace('"L61Q2TYHHTM3G"', '"L61Q2" + "TYHHTM3G"'),
        "fetched": real.rstrip() + "\nfetch(\"/x\");",
        "second assignment": real.rstrip() + "\nwindow.IOT_PAY = {};",
        "stripe link": real.replace('Builder: { m: "", y: "" }', 'Builder: { m: "https://buy.stripe.com/evil", y: "" }', 1),
        # review of fix/payments-redteam: bare identifiers and duplicate keys got past the old regex pin.
        "(a) second api key after the pinned one": real.replace(sdk_line, sdk_line + ", api: window.name"),
        "(b) appId read from the page": real.replace(sdk_line, sdk_line + ", appId: document.referrer"),
        "(c) Builder link read from the page": real.replace('m: "https://square.link/u/xIlkX7Cb"', "m: document.referrer"),
        "(d) second sdk key": real.replace(sdk_line + " }", sdk_line + " }, sdk: window.name"),
        "Builder and Buyer links swapped": real.replace("xIlkX7Cb", "TMPSWAP0").replace("gKoiSiI1", "xIlkX7Cb").replace("TMPSWAP0", "gKoiSiI1"),
        "Partner link in Builder.y": real.replace('Builder: { m: "https://square.link/u/xIlkX7Cb", y: "" }', 'Builder: { m: "https://square.link/u/xIlkX7Cb", y: "https://square.link/u/gYnG7De1" }'),
        "extra key": real.replace('portal: "",', 'portal: "", next: "",'),
        "number value": real.replace('portal: ""', "portal: 1"),
    }
    out = [] if not pay_links_fails(real) else ["pay-links self-test: the real pay-links.js should pass: " + "; ".join(pay_links_fails(real))]
    out += [f"pay-links self-test: a swapped {k} was not caught" for k, v in swaps.items() if v == real or not pay_links_fails(v)]
    # Other files: the real tree passes; writes to IOT_PAY elsewhere, extra readers and a script slipped in between fail.
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iot-paycheck-"))
    try:
        for n in ("pay-links.js", "square-pay.js", "join.html", "theme.js"):
            if (DIST / n).exists(): shutil.copy(DIST / n, tmp / n)
        base = {n: (tmp / n).read_text() for n in ("join.html", "square-pay.js", "theme.js") if (tmp / n).exists()}
        if pay_use_fails(tmp): out.append("pay-links self-test: the real join.html / square-pay.js should pass: " + "; ".join(pay_use_fails(tmp)))
        inline = '<script>window.IOT_PAY.sdk.api="https://evil.example/f";window.IOT_PAY.square.Builder.m="https://evil.example/pay";</script>'
        cases = {
            "inline override between the two scripts": ("join.html", base["join.html"].replace('<script src="pay-links.js"></script>', '<script src="pay-links.js"></script>' + inline)),
            "override later in join.html": ("join.html", base["join.html"].replace("</body>", inline + "</body>")),
            "IOT_PAY touched in theme.js": ("theme.js", base.get("theme.js", "") + '\nwindow.IOT_PAY.sdk.locationId="LATTACKER0000";'),
            "Object.assign in square-pay.js": ("square-pay.js", base["square-pay.js"] + "\nObject.assign(window.IOT_PAY.sdk, {api: location.hash});"),
            "bracket write in join.html": ("join.html", base["join.html"].replace("</body>", "<script>window.IOT_PAY['sdk']['api'] ||= x</script></body>")),
            "square-pay.js no longer freezes": ("square-pay.js", base["square-pay.js"].replace("deepFreeze(window.IOT_PAY)", "window.IOT_PAY")),
        }
        for k, (n, v) in cases.items():
            (tmp / n).write_text(v)
            if not pay_use_fails(tmp): out.append(f"pay-links self-test: {k} was not caught")
            (tmp / n).write_text(base[n] if n in base else "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out

class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.ids, s.hrefs, s.h1, s.imgs_noalt, s.lang, s.ld, s._ld, s.text = set(), [], 0, 0, None, [], False, []
    def handle_starttag(s, t, a):
        a = dict(a)
        if "id" in a: s.ids.add(a["id"])
        if t == "a" and a.get("href"): s.hrefs.append(a["href"])
        if t == "h1": s.h1 += 1
        if t == "img" and not a.get("alt"): s.imgs_noalt += 1
        if t == "html": s.lang = a.get("lang")
        if t == "script" and a.get("type") == "application/ld+json": s._ld = True
    def handle_endtag(s, t):
        if t == "script": s._ld = False
    def handle_data(s, d):
        if s._ld: s.ld.append(d)
        else: s.text.append(d)


def main():
    fails, notes = [], []
    pages = {f.name: f for f in DIST.glob("*.html")}
    parsed = {n: P() for n in pages}
    for n, f in pages.items():
        parsed[n].feed(f.read_text())
    titles, descs = {}, {}
    for n, f in pages.items():
        src, p = f.read_text(), parsed[n]
        text = " ".join(p.text)
        for m in HONESTY.finditer(text):
            before = text[max(0, m.start() - 80):m.start()]
            if not DENIAL.search(before):
                fails.append(f"{n}: honesty word '{m.group(0)}' near: ...{before[-50:]}{m.group(0)}")
        for m in re.finditer(r"\$\s?\d[\d,]*|\d+\s?%\s+of the original|\bper month\b|/\s?month", text):
            if n == "join.html" or m.group(0) in SAMPLE_PRICES.get(n, ()): continue  # operator approved prices on the Join page (2026-11-13)
            fails.append(f"{n}: price shown ({m.group(0)}): prices stay off the site, use Book a demo / Learn more")
        for s in set(re.findall(r"\[[A-Z][A-Z0-9 \-']{3,}\]", text)) - ALLOWED_SLOTS:
            fails.append(f"{n}: unexpected slot {s}")
        if p.h1 != 1: fails.append(f"{n}: {p.h1} h1 elements")
        if p.imgs_noalt: fails.append(f"{n}: {p.imgs_noalt} images without alt")
        if p.lang != "en": fails.append(f"{n}: html lang not set")
        t = re.search(r"<title>(.*?)</title>", src).group(1)
        d = re.search(r'<meta name="description" content="(.*?)">', src).group(1)
        if t in titles: fails.append(f"{n}: title duplicates {titles[t]}")
        if d in descs: fails.append(f"{n}: description duplicates {descs[d]}")
        titles[t], descs[d] = n, n
        if not 50 <= len(d) <= 160: fails.append(f"{n}: description is {len(d)} chars (keep 50-160 so search results don't cut it)")
        if len(html.unescape(t)) > 60: fails.append(f"{n}: title is {len(html.unescape(t))} chars (keep under 60)")
        if 'noindex' not in src:
            for tag in ('og:image" content="https://', 'twitter:card" content="summary_large_image', 'rel="canonical"', 'application/ld+json'):
                if tag not in src: fails.append(f"{n}: missing {tag.split(chr(34))[0]}")
        for blob in p.ld:
            try: json.loads(blob)
            except ValueError as e: fails.append(f"{n}: JSON-LD does not parse: {e}")
        for h in p.hrefs:
            if h.startswith(("http", "mailto:")): continue
            path, _, frag = h.partition("#")
            path = path.partition("?")[0]   # a query string (login.html?mode=signup) points at the same file
            target = path or n
            if path and not (DIST / path).exists(): fails.append(f"{n}: broken link {h}")
            elif frag and target in parsed and frag not in parsed[target].ids: fails.append(f"{n}: missing anchor {h}")
    # Pages carry their own CSS; the src/ motion and token checks run in the local build (check.py), not here.
    css = ""
    depth, stack, i = 0, [], 0
    for m in re.finditer(r"@media[^{]*\{|@supports[^{]*\{|[^{}]*\{|\}|[^{}]+", css):
        tok = m.group(0)
        if tok.endswith("{"):
            stack.append(tok.strip())
        elif tok == "}":
            if stack: stack.pop()
        else:
            if re.search(r"(^|;|\s)(animation(-name)?\s*:\s*(?!none)|view-transition-name\s*:)", tok) and not any("no-preference" in s for s in stack):
                fails.append(f"style.css: motion outside the reduced-motion guard: {tok.strip()[:70]}")
    if "@view-transition" in css and css.index("@view-transition") < css.index("prefers-reduced-motion:no-preference"):
        fails.append("style.css: @view-transition declared before the reduced-motion guard")
    if any((DIST / n).exists() for n in ("kit.html",)): fails.append("dist/kit.html: preview-only page leaked into production")
    fails += pay_self_test() + pay_destination_fails(DIST)
    for need in ("robots.txt", "sitemap.xml", "404.html", "index.html", "assets/og-card.png"):
        if not (DIST / need).exists(): fails.append(f"missing {need}")
    for x in notes: print("NOTE", x)
    for x in fails: print("FAIL", x)
    print(f"{len(pages)} pages checked: {'OK' if not fails else f'{len(fails)} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
