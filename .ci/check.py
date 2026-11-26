#!/usr/bin/env python3
"""Checks the published site before every GitHub Pages deploy (CI copy of ~/Projects/iothreads-site/check.py).

    python3 .ci/check.py    # exit 1 on any FAIL

Checks: honesty grep (sales-copy gate), internal links and anchors resolve,
one h1 per page, unique titles and descriptions, description length, alt text
on images, JSON-LD parses, lang set, only allowed slots remain.
"""
import html, json, pathlib, re, sys
from html.parser import HTMLParser

# live/ is what GitHub Pages serves (io-threads.com); dist/ is the old GoDaddy build. Pass --dist to check that instead.
DIST = pathlib.Path(__file__).resolve().parent.parent  # the repo root is what Pages serves
ALLOWED_SLOTS = {"[YOUR TWO-LINE BACKGROUND]"}
# Sample data and merch rewards on the sample report, not offer prices (operator 11-15). Any other $ value still fails.
SAMPLE_PRICES = {"sample-report.html": {"$5,200", "$28", "$64", "$32", "$1"}}
HONESTY = re.compile(r"coming soon|coming to testflight|in-app purchase|trusted by|clients? (say|love|trust)|guarantee|certified|compliant with|world-class|best-in-class|"
                     r"seamless|revolution|cutting-edge|unlock|leverage|most clients|we've helped|our clients|attestation|public data|deterministic|filing-grade|regulatory-grade|certificate|"
                     r"free (?:api|tier|keys?|plan)\b", re.I)   # no free API plan since 2026-11-18 (accounts are free)
# Allowed only inside an explicit denial (e.g. "doesn't certify compliance").
DENIAL = re.compile(r"(isn't|aren't|doesn't|not|no)\b[^.]{0,60}$", re.I)


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
    for need in ("robots.txt", "sitemap.xml", "404.html", "index.html", "assets/og-card.png"):
        if not (DIST / need).exists(): fails.append(f"missing {need}")
    for x in notes: print("NOTE", x)
    for x in fails: print("FAIL", x)
    print(f"{len(pages)} pages checked: {'OK' if not fails else f'{len(fails)} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
