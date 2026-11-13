/* io threads payment and sign-in links. This is the only file to edit.
   Paste each hosted link between the quotes, then commit and push. Empty = that button falls back to an email to team@.
   stripe: Stripe Payment Links (card, Apple Pay, Google Pay). Dashboard → Payment Links → New → recurring price.
   square: Square payment links (Square Dashboard → Online → Payment links → subscription).
   portal: Stripe customer portal login link (Settings → Billing → Customer portal → "Login link"). Members sign in there by email code.
   Money goes straight from the payer to your Stripe or Square account; no card details ever touch this site. */
window.IOT_PAY = {
  stripe: { Builder: { m: "", y: "" }, Buyer: { m: "", y: "" }, Partner: { m: "", y: "" } },
  square: { Builder: { m: "", y: "" }, Buyer: { m: "", y: "" }, Partner: { m: "", y: "" } },
  portal: ""
};
