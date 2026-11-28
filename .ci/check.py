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
# turnstileSiteKey: the public Cloudflare Turnstile site key square-pay.js renders in the checkout. "" = no widget (the
# server skips the check while TURNSTILE_SECRET is unset). Once set, it is pinned like every other value: put the exact key
# here in the same commit that sets it in pay-links.js, so a swapped key (someone else's widget) fails CI.
PAY_SDK = {"appId": "sq0idp-1s8ZblRtSjareUcO7Q6X9Q", "locationId": "L61Q2TYHHTM3G", "api": "https://tckvatqkjfrvavleunzk.supabase.co/functions/v1",
           "turnstileSiteKey": ""}
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


# Characters Python and JavaScript don't agree on (review of fix/payments-redteam): JS ends a // comment at U+2028,
# U+2029 and \r as well as \n, so `// note<U+2028>window.IOT_PAY.sdk.api = "..."` was stripped here as one comment but
# RUN by the browser. Fail closed: pay-links.js may not contain any line terminator other than \n, any control
# character other than \n and \t, any Unicode space, zero-width or bidi character, and its code (outside comments)
# must be plain ASCII. Read it with read_bytes().decode() (pay_source) so newline translation can't hide a \r.
PAY_BAD_CHARS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u00a0\u1680\u180e\u2000-\u200f\u2028-\u202f\u205f-\u206f\u3000\ufeff\ufff9-\ufffb]")


def pay_source(path):
    """A file's exact text: bytes decoded as UTF-8 (strict), no newline translation."""
    return path.read_bytes().decode("utf-8")


def parse_pay_links(src):
    """pay-links.js as a Python dict, or PayParseError. The file must be exactly `window.IOT_PAY = <object>;` where the
    object holds only identifier or quoted keys (each once) and plain quoted-string or object values."""
    bad = PAY_BAD_CHARS.search(src)
    if bad: raise PayParseError(f"character U+{ord(bad.group(0)):04X} at offset {bad.start()} (JS and this check could read the file differently)")
    # Comments may mention anything; only code counts. Strings are matched first so "https://" isn't read as a comment.
    # A // comment ends at any JS line terminator (only \n can remain after the check above, but stay exact).
    code = re.sub(r"(\"(?:[^\"\\\n\r\u2028\u2029]|\\.)*\"|'(?:[^'\\\n\r\u2028\u2029]|\\.)*')|/\*.*?\*/|//[^\n\r\u2028\u2029]*", lambda m: m.group(1) or " ", src, flags=re.S)
    if not code.isascii(): raise PayParseError("non-ASCII character outside a comment")
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


def pay_links_fails(src, name="pay-links.js", expected=None):
    """Everything wrong with a pay-links.js source against PAY_EXPECTED, or `expected` (the self-test's fixture)
    (empty list = OK)."""
    try:
        tree = parse_pay_links(src)
    except PayParseError as e:
        return [f"{name}: {e} - payment config must be plain quoted strings (PAY_EXPECTED in .ci/check.py)"]
    return [f"{name}: {d} (PAY_EXPECTED in .ci/check.py)" for d in _pay_diff(PAY_EXPECTED if expected is None else expected, tree)]


# A write to the payment config: assignment (= += ||= ...), Object.assign/defineProperty/defineProperties/setPrototypeOf
# or Reflect.set/defineProperty with IOT_PAY in the arguments, or delete. Also the whole object replaced through a
# quoted key (window["IOT_PAY"] = ..., third review: `"]` after IOT_PAY got past the first alternative).
_ASSIGN = r"\s*(?:[-+*/%&|^]|\|\||&&|\?\?|<<|>>>?|\*\*)?=(?!=)"
PAY_WRITE = re.compile(r"\bIOT_PAY\b(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]))*" + _ASSIGN
                       + r"|[\"'`]IOT_PAY[\"'`]\s*\](?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]))*" + _ASSIGN
                       + r"|\b(?:Object\.(?:assign|defineProperty|defineProperties|setPrototypeOf)|Reflect\.(?:set|defineProperty|deleteProperty))\s*\([^)]*\bIOT_PAY\b"
                       r"|\bdelete\s+[\w$.\[\]\s]*\bIOT_PAY\b")
# Any computed or quoted write onto the global object, in any served file (third review): window["IOT_"+"PAY"] = ...
# never names IOT_PAY, so the reader allow-list can't see it. Nothing on the site needs one.
# (Up to the first "]=" in the statement, so a nested bracket like self[["IOT","PAY"].join("_")] = ... is caught too.)
GLOBAL_BRACKET_WRITE = re.compile(r"\b(?:window|self|globalThis|top|parent|frames)\s*\[[^;\n]*?\]" + _ASSIGN)
# square-pay.js locks the window.IOT_PAY binding as well as freezing the object, so no later script can replace it
# (deepFreeze alone left `window.IOT_PAY = {...}` working). This exact statement is the one IOT_PAY write it may make.
PAY_LOCK = re.compile(r'Object\.defineProperty\(\s*window\s*,\s*"IOT_PAY"\s*,\s*\{\s*value:\s*deepFreeze\(window\.IOT_PAY\)\s*,'
                      r'\s*writable:\s*false\s*,\s*configurable:\s*false\s*,\s*enumerable:\s*true\s*\}\s*\)')
PAY_LOAD = re.compile(r'<script src="pay-links\.js"></script>\s*<script src="square-pay\.js"></script>')


def pay_use_fails(root):
    """Only pay-links.js writes IOT_PAY; only PAY_READERS read it, without writing; join.html loads pay-links.js then
    square-pay.js (which freezes it) with nothing in between."""
    fails = []
    for g in sorted(set(root.glob("**/*.html")) | set(root.glob("**/*.js"))):
        if ".git" in g.parts or ".ci" in g.parts or ".github" in g.parts or g == root / "pay-links.js": continue
        src, rel = g.read_text(errors="ignore"), str(g.relative_to(root))
        for m in GLOBAL_BRACKET_WRITE.finditer(src):
            fails.append(f"{rel}: computed write to the global object ({m.group(0)[:60]!r}); it could replace IOT_PAY without naming it")
        if not re.search(r"IOT_PAY", src): continue
        if rel == "square-pay.js": src = PAY_LOCK.sub("", src, count=1)   # its one allowed write: the lock
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
    if sp.exists() and not PAY_LOCK.search(sp.read_text(errors="ignore")):
        fails.append('square-pay.js: must freeze window.IOT_PAY and lock the binding before reading it '
                     '(Object.defineProperty(window, "IOT_PAY", { value: deepFreeze(window.IOT_PAY), writable: false, configurable: false, enumerable: true }))')
    return fails


def pay_destination_fails(root, expected=None):
    """pay-links.js pinned, IOT_PAY written nowhere else, and no other served page or script carries a payment
    destination off the allow-list. `expected`: the self-test's fixture instead of PAY_EXPECTED."""
    f = root / "pay-links.js"
    if not f.exists(): return ["pay-links.js: missing"]
    try:
        src = pay_source(f)
    except UnicodeDecodeError as e:
        return [f"pay-links.js: not valid UTF-8 ({e.reason} at byte {e.start})"]
    allowed = PAY_ALLOWED if expected is None else set(_pay_values(expected))
    fails = pay_links_fails(src, expected=expected) + pay_use_fails(root)
    for g in sorted(root.glob("*.html")) + sorted(root.glob("*.js")) + sorted(root.glob("**/*.html")) + sorted(root.glob("**/*.js")):
        if g == f or ".git" in g.parts or ".ci" in g.parts or ".github" in g.parts: continue
        for m in set(PAY_SHAPES.findall(g.read_text(errors="ignore"))):
            if m not in allowed: fails.append(f"{g.relative_to(root)}: payment destination {m!r} is not on the allow-list (PAY_EXPECTED in .ci/check.py)")
    return sorted(set(fails))


# The self-test runs on this fixed fixture, never on the live pay-links.js (third review): swaps built by replacing the
# live file's literal values stopped applying as soon as the operator rotated a link (edit pay-links.js and
# PAY_EXPECTED together, the documented way), and CI then failed with "a swapped ... was not caught". The fixture keeps
# every slot the swaps need (a filled Square link per plan, an empty Stripe link, an empty portal, the sdk line) and is
# checked against PAY_FIXTURE_EXPECTED. The live file is still checked against PAY_EXPECTED by pay_destination_fails.
PAY_FIXTURE_SDK = {"appId": "sq0idp-FixtureApp0000000000000", "locationId": "LFIXTURE00000", "api": "https://fixtureproject00000000.supabase.co/functions/v1",
                   "turnstileSiteKey": "0x4AAAAAAAFixtureKey00"}
PAY_FIXTURE_EXPECTED = {
    "stripe": {"Builder": {"m": "", "y": ""}, "Buyer": {"m": "", "y": ""}, "Partner": {"m": "", "y": ""}, "Lifetime": ""},
    "square": {"Builder": {"m": "https://square.link/u/FixBld01", "y": ""}, "Buyer": {"m": "https://square.link/u/FixBuy02", "y": ""},
               "Partner": {"m": "https://square.link/u/FixPrt03", "y": ""}, "Lifetime": ""},
    "portal": "",
    "sdk": PAY_FIXTURE_SDK,
}
PAY_FIXTURE = """/* self-test fixture, same layout as pay-links.js */
window.IOT_PAY = {
  stripe: { Builder: { m: "", y: "" }, Buyer: { m: "", y: "" }, Partner: { m: "", y: "" }, Lifetime: "" },
  square: { Builder: { m: "https://square.link/u/FixBld01", y: "" }, Buyer: { m: "https://square.link/u/FixBuy02", y: "" }, Partner: { m: "https://square.link/u/FixPrt03", y: "" }, Lifetime: "" },
  portal: "",
  sdk: { appId: "sq0idp-FixtureApp0000000000000", locationId: "LFIXTURE00000", api: "https://fixtureproject00000000.supabase.co/functions/v1", turnstileSiteKey: "0x4AAAAAAAFixtureKey00" }
};
"""


def _swap(src, old, new, count=-1):
    """src with old replaced; None when old isn't there (the case no longer applies to the fixture)."""
    return src.replace(old, new, count) if old in src else None


def pay_self_test():
    """The pin itself, on the fixture: the fixture passes, each kind of swap fails. Then the real join.html,
    square-pay.js and theme.js with the fixture as pay-links.js: they pass, each kind of write elsewhere fails."""
    import shutil, tempfile
    fx, X = PAY_FIXTURE, PAY_FIXTURE_EXPECTED
    fails_fx = lambda v: pay_links_fails(v, expected=X)
    b_m, y_m, p_m = (X["square"][k]["m"] for k in ("Builder", "Buyer", "Partner"))
    b_id, y_id = b_m.rsplit("/", 1)[1], y_m.rsplit("/", 1)[1]
    sdk_line = f'api: "{X["sdk"]["api"]}"'
    loc, app, api_host = X["sdk"]["locationId"], X["sdk"]["appId"], X["sdk"]["api"].split("/")[2]
    swaps = {
        "hosted link": _swap(fx, b_id, "EvIl0000"),
        "app id": _swap(fx, app, "sq0idp-AttackerApp000000000"),
        "location": _swap(fx, loc, "LATTACKER0000"),
        "api": _swap(fx, api_host, "evil.example"),
        "api blanked to an allowed value": _swap(fx, sdk_line, f'api: "{loc}"'),
        "built string": _swap(fx, f'"{loc}"', f'"{loc[:5]}" + "{loc[5:]}"'),
        "fetched": fx.rstrip() + "\nfetch(\"/x\");",
        "second assignment": fx.rstrip() + "\nwindow.IOT_PAY = {};",
        "stripe link": _swap(fx, 'Builder: { m: "", y: "" }', 'Builder: { m: "https://buy.stripe.com/evil", y: "" }', 1),
        # review of fix/payments-redteam: bare identifiers and duplicate keys got past the old regex pin.
        "(a) second api key after the pinned one": _swap(fx, sdk_line, sdk_line + ", api: window.name"),
        "(b) appId read from the page": _swap(fx, sdk_line, sdk_line + ", appId: document.referrer"),
        "(c) Builder link read from the page": _swap(fx, f'm: "{b_m}"', "m: document.referrer"),
        "(d) second sdk key": _swap(fx, '" }\n};', '" }, sdk: window.name\n};'),
        "Builder and Buyer links swapped": _swap(fx, b_id, "TMPSWAP0") and fx.replace(b_id, "TMPSWAP0").replace(y_id, b_id).replace("TMPSWAP0", y_id),
        "Partner link in Builder.y": _swap(fx, f'Builder: {{ m: "{b_m}", y: "" }}', f'Builder: {{ m: "{b_m}", y: "{p_m}" }}'),
        "extra key": _swap(fx, 'portal: "",', 'portal: "", next: "",'),
        "number value": _swap(fx, 'portal: ""', "portal: 1"),
        # second review: JS line terminators Python's // pattern ran past, and characters the two lex differently.
        "U+2028 after a // comment": fx.rstrip() + "\n// note\u2028window.IOT_PAY.sdk.api = \"https://evil.example/f\";\n",
        "U+2029 after a // comment": fx.rstrip() + "\n// note\u2029window.IOT_PAY.sdk.api = \"https://evil.example/f\";\n",
        "\\r after a // comment": fx.rstrip() + "\n// note\rwindow.IOT_PAY.sdk.api = \"https://evil.example/f\";\n",
        "non-ASCII in code": _swap(fx, 'portal: ""', 'portal\u0430: ""'),
        "zero-width space": _swap(fx, 'portal: ""', 'portal:\u200b ""'),
        # Turnstile site key: pinned once set; swapped, blanked, read from the page or missing all fail.
        "turnstile key swapped": _swap(fx, X["sdk"]["turnstileSiteKey"], "0x4AAAAAAAAttackerKey0"),
        "turnstile key blanked": _swap(fx, f'"{X["sdk"]["turnstileSiteKey"]}"', '""'),
        "turnstile key read from the page": _swap(fx, f'"{X["sdk"]["turnstileSiteKey"]}"', "window.name"),
        "turnstile key missing": _swap(fx, f', turnstileSiteKey: "{X["sdk"]["turnstileSiteKey"]}"', ""),
    }
    out = [] if not fails_fx(fx) else ["pay-links self-test: the fixture should pass: " + "; ".join(fails_fx(fx))]
    for k, v in swaps.items():
        if v is None or v == fx: out.append(f"pay-links self-test: case {k!r} no longer applies to the fixture (update PAY_FIXTURE)")
        elif not fails_fx(v): out.append(f"pay-links self-test: a swapped {k} was not caught")
    # Other files: the real tree passes; writes to IOT_PAY elsewhere, extra readers and a script slipped in between fail.
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iot-paycheck-"))
    try:
        for n in ("square-pay.js", "join.html", "theme.js", "terms-gate.js"):
            if (DIST / n).exists(): shutil.copy(DIST / n, tmp / n)
        (tmp / "pay-links.js").write_bytes(fx.encode("utf-8"))
        base = {n: (tmp / n).read_text() for n in ("join.html", "square-pay.js", "theme.js", "terms-gate.js") if (tmp / n).exists()}
        if pay_use_fails(tmp): out.append("pay-links self-test: the real join.html / square-pay.js should pass: " + "; ".join(pay_use_fails(tmp)))
        inline = '<script>window.IOT_PAY.sdk.api="https://evil.example/f";window.IOT_PAY.square.Builder.m="https://evil.example/pay";</script>'
        whole = '<script>window["IOT_PAY"]={stripe:{},square:{Builder:{m:"https://evil.example/pay"}}};</script>'
        cases = {
            "inline override between the two scripts": ("join.html", '<script src="pay-links.js"></script>', '<script src="pay-links.js"></script>' + inline),
            "override later in join.html": ("join.html", "</body>", inline + "</body>"),
            "IOT_PAY touched in theme.js": ("theme.js", None, '\nwindow.IOT_PAY.sdk.locationId="LATTACKER0000";'),
            "Object.assign in square-pay.js": ("square-pay.js", None, "\nObject.assign(window.IOT_PAY.sdk, {api: location.hash});"),
            "bracket write in join.html": ("join.html", "</body>", "<script>window.IOT_PAY['sdk']['api'] ||= x</script></body>"),
            # third review: the whole object replaced through a quoted or computed name, after terms-gate.js.
            "window[\"IOT_PAY\"]= in join.html": ("join.html", "</body>", whole + "</body>"),
            "window['IOT_PAY'].sdk= in join.html": ("join.html", "</body>", "<script>window['IOT_PAY'].sdk={api:'https://evil.example/f'}</script></body>"),
            "computed name in terms-gate.js": ("terms-gate.js", None, '\nwindow["IOT_"+"PAY"]={square:{Builder:{m:"https://evil.example/pay"}}};'),
            "computed name via self in join.html": ("join.html", "</body>", '<script>self[["IOT","PAY"].join("_")]={}</script></body>'),
            "square-pay.js no longer freezes": ("square-pay.js", "deepFreeze(window.IOT_PAY)", "window.IOT_PAY"),
            "square-pay.js no longer locks the binding": ("square-pay.js", "writable: false", "writable: true"),
        }
        for k, (n, old, new) in cases.items():
            if n not in base: out.append(f"pay-links self-test: case {k!r} no longer applies ({n} missing)"); continue
            v = base[n] + new if old is None else _swap(base[n], old, new, 1)
            if v is None or v == base[n]: out.append(f"pay-links self-test: case {k!r} no longer applies ({n} changed)"); continue
            (tmp / n).write_text(v)
            if not pay_use_fails(tmp): out.append(f"pay-links self-test: {k} was not caught")
            (tmp / n).write_text(base[n])
        # The whole check on a tree (bytes as written, no newline translation): the terminator swaps must fail there too.
        if pay_destination_fails(tmp, expected=X): out.append("pay-links self-test: the real tree should pass: " + "; ".join(pay_destination_fails(tmp, expected=X)))
        for k in ("U+2028 after a // comment", "U+2029 after a // comment", "\\r after a // comment"):
            (tmp / "pay-links.js").write_bytes(swaps[k].encode("utf-8"))
            if not pay_destination_fails(tmp, expected=X): out.append(f"pay-links self-test: {k} was not caught on a tree")
        (tmp / "pay-links.js").write_bytes(b"\xff" + fx.encode("utf-8"))
        if not pay_destination_fails(tmp, expected=X): out.append("pay-links self-test: invalid UTF-8 was not caught on a tree")
        (tmp / "pay-links.js").write_bytes(fx.encode("utf-8"))
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
