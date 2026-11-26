/* io threads payment and sign-in links. This is the only file to edit.
   Paste each hosted link between the quotes, then commit and push. Empty = that button falls back to an email to team@.
   stripe: Stripe Payment Links (card, Apple Pay, Google Pay). Dashboard → Payment Links → New → recurring price.
   square: Square payment links (Square Dashboard → Online → Payment links → subscription).
   Lifetime: closed to new sales 2026-11-17 (links blanked; existing holders keep the plan).
   portal: Stripe customer portal login link (Settings → Billing → Customer portal → "Login link"). Members sign in there by email code.
   Money goes straight from the payer to your Stripe or Square account; no card details ever touch this site. */
window.IOT_PAY = {
  stripe: { Builder: { m: "", y: "" }, Buyer: { m: "", y: "" }, Partner: { m: "", y: "" }, Lifetime: "" },
  square: { Builder: { m: "https://square.link/u/xIlkX7Cb", y: "" }, Buyer: { m: "https://square.link/u/gKoiSiI1", y: "" }, Partner: { m: "https://square.link/u/gYnG7De1", y: "" }, Lifetime: "" },
  portal: "",
  /* In-page payments (square-pay.js). appId and locationId are public; the secret token lives only on the payment server (Supabase Edge Functions; api = https://<project>.supabase.co/functions/v1).
     Leave appId empty to keep the hosted Square links above. A sandbox- appId uses Square's test environment.
     turnstileSiteKey: the public Cloudflare Turnstile site key for io-threads.com (Cloudflare → Turnstile → Add site). Empty = no check
     on the page. Set it together with TURNSTILE_SECRET on the payment server and the same value in PAY_EXPECTED (.ci/check.py). */
  sdk: { appId: "sq0idp-1s8ZblRtSjareUcO7Q6X9Q", locationId: "L61Q2TYHHTM3G", api: "https://tckvatqkjfrvavleunzk.supabase.co/functions/v1", turnstileSiteKey: "" }
};
