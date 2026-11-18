#!/usr/bin/env python3
"""Link check for every page the site serves, subfolders included (iolin/).   python3 .ci/links.py [--external]

Each href/src is resolved from the page's own URL (so "api.html" on /iolin/ means /iolin/api.html, the way a browser
reads it), then:
  - a same-site target (relative, root-relative, or https://io-threads.com/...) must be a file GitHub Pages serves;
  - a #fragment must be an id on the target page;
  - a link whose words name a page ("iot API", "Account") must not land on the home page: that's how a placeholder
    href="https://io-threads.com" slipped through and sent visitors home (mark a deliberate one with data-link-home);
  - hrefs that page scripts set (a.href = "...", location = "...", window.open("...")) get the same checks,
    resolved from every page that loads the script.
--external also sends a HEAD request to each outside link (slow; off in CI). Exit 1 on any FAIL."""
import pathlib, re, sys, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://io-threads.com/"
HOSTS = {"io-threads.com", "www.io-threads.com"}
SKIP_DIRS = {".git", ".github", ".ci", "node_modules", ".netlify", "_site"}
SKIP_SCHEMES = ("mailto:", "tel:", "data:", "javascript:", "blob:", "sms:")
# Words that honestly mean "the home page" (brand marks, logos, Home).
HOME_WORDS = re.compile(r"^(|io|io threads|iothreads|home|home page|back home|go home|go to the home page|back to home|io threads home)$", re.I)
JS_NAV = re.compile(r"""(?:\.href\s*=|location(?:\.href)?\s*=|location\.(?:assign|replace)\(|window\.open\()\s*["']([^"'$`]+)["']""")


class Page(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True)
        s.ids, s.links, s.scripts, s.inline_js = set(), [], [], []
        s._a, s._text, s._in_script = None, [], False
    def handle_starttag(s, t, a):
        a = dict(a)
        for k in ("id", "name"):
            if a.get(k) and (k == "id" or t == "a"): s.ids.add(a[k])
        if t == "a" and a.get("href") is not None:
            s._a, s._text = a, [a["aria-label"]] if a.get("aria-label") else []
        for attr in ("href", "src"):
            v = a.get(attr)
            if v is None or t == "a": continue
            if t == "link" and a.get("rel") in ("preconnect", "dns-prefetch"): continue
            s.links.append((t, attr, v, ""))
        if t == "script":
            s._in_script = not a.get("src") and a.get("type") not in ("application/ld+json", "importmap")
            if a.get("src"): s.scripts.append(a["src"])
    def handle_endtag(s, t):
        if t == "a" and s._a is not None:
            # data-link-home marks a link that starts at home on purpose (a script repoints it, e.g. the ops preview "Open").
            text = "home" if "data-link-home" in s._a else " ".join(" ".join(s._text).split())
            s.links.append(("a", "href", s._a["href"], text))
            s._a = None
        if t == "script": s._in_script = False
    def handle_data(s, d):
        if s._a is not None and not s._a.get("aria-label"): s._text.append(d)
        if s._in_script: s.inline_js.append(d)


def serves(path):
    """The file GitHub Pages would answer for a URL path, or None."""
    p = urllib.parse.unquote(path).lstrip("/")
    cands = [p] if p and not p.endswith("/") else []
    cands += [p + "index.html"] if p.endswith("/") or not p else [p + ".html", p + "/index.html"]
    for c in cands:
        f = ROOT / c
        if f.is_file() and not any(part in SKIP_DIRS for part in f.relative_to(ROOT).parts): return f
    return None


def main():
    external = "--external" in sys.argv
    pages = sorted(f for f in ROOT.rglob("*.html") if not any(p in SKIP_DIRS for p in f.relative_to(ROOT).parts))
    parsed = {}
    for f in pages:
        pp = Page(); pp.feed(f.read_text(errors="replace")); parsed[f] = pp
    fails, outside, checked = [], set(), 0

    def check(page, kind, raw, text):
        nonlocal checked
        raw = raw.strip()
        if not raw or raw.startswith(SKIP_SCHEMES) or "${" in raw or "{{" in raw: return
        rel = page.relative_to(ROOT).as_posix()
        base = SITE + rel
        url = urllib.parse.urljoin(base, raw)
        u = urllib.parse.urlsplit(url)
        if u.scheme not in ("http", "https"): return
        if u.hostname not in HOSTS:
            outside.add(url.split("#")[0]); return
        checked += 1
        where = f"{rel}: {kind} {raw!r}" + (f" ('{text[:40]}')" if text else "")
        target = serves(u.path)
        if target is None:
            fails.append(f"{where} -> {u.path} doesn't exist on the site"); return
        if u.fragment and target.suffix == ".html" and target in parsed and u.fragment not in parsed[target].ids:
            fails.append(f"{where} -> #{u.fragment} isn't an id on {target.relative_to(ROOT).as_posix()}")
        if kind == "a" and target == ROOT / "index.html" and not u.fragment and not HOME_WORDS.match(text.strip(" ·→←›‹")):
            if page != ROOT / "index.html":
                fails.append(f"{where} -> lands on the home page, but its words name something else; point it at the real page")

    js_cache = {}
    for f, pp in parsed.items():
        for tag, attr, v, text in pp.links:
            check(f, tag if tag == "a" else f"{tag}[{attr}]", v, text)
        sources = ["\n".join(pp.inline_js)]
        for s in pp.scripts:
            u = urllib.parse.urlsplit(urllib.parse.urljoin(SITE + f.relative_to(ROOT).as_posix(), s))
            if u.hostname in HOSTS:
                js = serves(u.path)
                if js is not None:
                    if js not in js_cache: js_cache[js] = js.read_text(errors="replace")
                    sources.append(js_cache[js])
        for src in sources:
            for m in JS_NAV.finditer(src):
                check(f, "script nav", m.group(1), "")

    if external:
        for url in sorted(outside):
            try:
                urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "io-threads-linkcheck"}), timeout=15)
            except Exception as e:
                code = getattr(e, "code", None)
                if code not in (403, 405, 429): fails.append(f"external {url}: {code or type(e).__name__}")

    for x in fails: print("FAIL", x)
    print(f"{len(pages)} pages, {checked} same-site links checked" + (f", {len(outside)} outside links HEAD-checked" if external else f", {len(outside)} outside links skipped")
          + f": {'OK' if not fails else f'{len(fails)} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
