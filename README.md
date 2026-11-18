# io-threads-site

The static site at https://io-threads.com, published by GitHub Pages.

| Path | What |
|---|---|
| `*.html` | Public pages (each carries its own `<style>`); `app.html`, `ops.html` are member/admin pages (`noindex`) |
| `iolin/` | iolin web: `index.html` + `sw.js` (runs a model on the visitor's own device) |
| `downloads/` | Public downloads (e.g. the evaluation skill) |
| `.ci/` | `check.py` (copy rules, links, metadata), `smoke.py` (browser smoke test), `iolin_usertest.py` (full iolin user test) |
| `.github/workflows/pages.yml` | Secret scan → checks → smoke → publish. Pages only publishes when all pass. |

Ship: edit, run `python3 .ci/check.py && python3 .ci/smoke.py`, push to `main`, watch the "Check and publish site" run.

Related repos (private): `io-threads-server` (Supabase backend), `io-threads-content` (offers, sales, brand, legal drafts), `iolin` (host app), `client-template`.
