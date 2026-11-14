/* io threads payment and sign-in links. This is the only file to edit.
   Paste each hosted link between the quotes, then commit and push. Empty = that button falls back to an email to team@.
   stripe: Stripe Payment Links (card, Apple Pay, Google Pay). Dashboard → Payment Links → New → recurring price.
   square: Square payment links (Square Dashboard → Online → Payment links → subscription).
   Lifetime: a one-time $999 Payment Link (not recurring).
   portal: Stripe customer portal login link (Settings → Billing → Customer portal → "Login link"). Members sign in there by email code.
   Money goes straight from the payer to your Stripe or Square account; no card details ever touch this site. */
window.IOT_PAY = {
  stripe: { Builder: { m: "", y: "" }, Buyer: { m: "", y: "" }, Partner: { m: "", y: "" }, Lifetime: "" },
  square: { Builder: { m: "https://square.link/u/xIlkX7Cb", y: "" }, Buyer: { m: "https://square.link/u/gKoiSiI1", y: "" }, Partner: { m: "https://square.link/u/gYnG7De1", y: "" }, Lifetime: "https://square.link/u/A45sbXLT" },
  portal: "",
  /* In-page payments (square-pay.js). appId and locationId are public; the secret token lives only on the payment server.
     Leave appId empty to keep the hosted Square links above. A sandbox- appId uses Square's test environment. */
  sdk: { appId: "", locationId: "", api: "https://io-threads-pay.netlify.app" }
};
