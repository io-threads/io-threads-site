/* io threads in-page payments with Square's Web Payments SDK.
   Runs only when pay-links.js has sdk.appId, sdk.locationId and sdk.api; otherwise the page keeps the hosted Square links.
   Lifetime ($999 once): Apple Pay, Google Pay or card, charged by the payment server.
   Monthly plans: card only. Square can't store a wallet payment for repeat billing, so a card is saved and Square bills it monthly.
   Card numbers go straight into Square's form; this page and our server only ever see a one-time token. */
(function () {
  var P = window.IOT_PAY || {}, cfg = P.sdk || {}, links = P.square || {};
  if (!cfg.appId || !cfg.locationId || !cfg.api) return;
  window.IOT_SQUARE_ON = true;

  var sandbox = /^sandbox-/.test(cfg.appId);
  var SDK = sandbox ? "https://sandbox.web.squarecdn.com/v1/square.js" : "https://web.squarecdn.com/v1/square.js";
  var PRICES = { Builder: "29.99", Buyer: "79.99", Partner: "199.00" };
  var payments = null, ready = null;

  function load() {
    if (ready) return ready;
    ready = new Promise(function (res, rej) {
      var s = document.createElement("script");
      s.src = SDK; s.onload = function () {
        try { payments = window.Square.payments(cfg.appId, cfg.locationId); res(payments); } catch (e) { rej(e); }
      };
      s.onerror = rej; document.head.appendChild(s);
    });
    return ready;
  }
  function key() { return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + "-" + Math.random().toString(36).slice(2, 10); }
  // A lost or timed-out reply means we don't know if Square charged, so say so instead of "nothing was charged".
  var UNKNOWN = "We couldn't confirm your payment. Check your email for a Square receipt before trying again, or email team@io-threads.com.";
  function post(path, body) {
    var ctl = window.AbortController ? new AbortController() : null, t = ctl && setTimeout(function () { ctl.abort(); }, 20000);
    return fetch(cfg.api + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl ? ctl.signal : undefined })
      .then(function (r) { clearTimeout(t); return r.json().catch(function () { return { ok: false }; }); },
        function () { clearTimeout(t); var e = new Error(UNKNOWN); e.unknown = true; throw e; });
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  var LOCK = '<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><rect x="2" y="5.5" width="8" height="5.5" rx="1.2" fill="currentColor"/><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';

  var css = document.createElement("style");
  css.textContent = ".sq-f{display:grid;gap:8px}.sq-f input{font:400 .95rem/1.2 var(--f-display);color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;min-height:44px;width:100%;box-sizing:border-box}" +
    ".sq-f input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}.paybox{min-width:0}.way.paying,.way.paying:hover{transform:none}.way .paybox:not([hidden]){position:fixed;inset:0;margin:auto;z-index:1000;width:min(440px,calc(100vw - 32px));height:max-content;max-height:calc(100vh - 32px);overflow:auto;padding:18px;background:var(--sheet);box-shadow:0 0 0 100vmax rgba(0,0,0,.6),0 24px 60px rgba(0,0,0,.5)}.sq-f{min-width:0}.sq-f>*{min-width:0;max-width:100%}.sq-card{min-height:0;margin-bottom:-24px}.sq-sq{all:unset;box-sizing:border-box;cursor:pointer;min-height:44px;border-radius:8px;display:flex;align-items:center;justify-content:center;gap:8px;font:600 .95rem/1 var(--f-display);background:#fff;color:#111;border:1px solid #d6d6d6}.sq-sq svg{flex:none}.sq-msg{margin:0;font:400 .85rem/1.35 var(--f-display);color:var(--muted)}.sq-msg.err{color:#c0392b}" +
    ".sq-go{all:unset;box-sizing:border-box;cursor:pointer;min-height:44px;border-radius:8px;display:grid;place-items:center;font:600 .98rem/1 var(--f-display);background:var(--ink);color:var(--paper)}.sq-go[disabled]{opacity:.5;cursor:wait}" +
    ".sq-apple{display:block;width:100%;height:44px;cursor:pointer;--apple-pay-button-width:100%;--apple-pay-button-height:44px;--apple-pay-button-border-radius:8px;--apple-pay-button-padding:0;--apple-pay-button-box-sizing:border-box}.sq-apple[hidden]{display:none}.sq-or{margin:0;text-align:center;font:400 .78rem/1 var(--f-display);color:var(--muted)}" +
    ".sq-done{display:grid;gap:6px;text-align:center;padding:8px 0}.sq-done b{font:600 1.05rem/1.3 var(--f-display);color:var(--ink)}.sq-alt{justify-self:center;font:400 .8rem/1 var(--f-display);color:var(--muted)}";
  document.head.appendChild(css);

  function shell(box, sum) {
    box.innerHTML = "";
    box.appendChild(el('<p class="pb-sum">' + sum + "</p>"));
    return box;
  }
function sqButton(href) { return el('<a class="sq-sq" href="' + href + '"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5" fill="#111"/><rect x="8" y="8" width="8" height="8" rx="1.5" fill="#fff"/></svg>Pay with Square</a>'); }
  function trust(box) {
    box.appendChild(el('<p class="pb-t">' + LOCK + "Secure checkout by Square · billed as Io Threads</p>"));
    var x = el('<button type="button" class="pb-x">Cancel</button>');
    box.appendChild(x);
    return x;
  }
  function done(box, title, line) {
    box.innerHTML = '<div class="sq-done"><b>' + title + '</b><p class="sq-msg">' + line + "</p></div>";
  }

  // One checkout for every plan: email, Apple Pay, Google Pay, card, or Square's own page.
  // Lifetime: one $999 charge. Monthly: the card is saved and billed monthly; a wallet pays the first month now and
  // Square emails a monthly invoice after that (Square can't save a wallet for repeat charges).
  function checkout(o) {
    var box = o.box, pay = o.pay, id = o.id, monthly = o.monthly;
    shell(box, o.title);
    var f = el('<div class="sq-f"><input type="email" autocomplete="email" placeholder="Email for your receipt and access" aria-label="Email" required>' +
      '<apple-pay-button class="sq-apple" buttonstyle="black" type="plain" locale="en-US" role="button" tabindex="0" aria-label="Pay with Apple Pay" hidden></apple-pay-button>' +
      '<div class="sq-gpay" id="sq-gpay-' + id + '" hidden></div><p class="sq-or sq-or1" hidden>or pay by card</p>' +
      '<div class="sq-card" id="sq-card-' + id + '"></div><button type="button" class="sq-go">' + o.cta + '</button>' +
      '<p class="sq-msg" aria-live="polite">' + (o.note || "") + "</p></div>");
    box.appendChild(f);
    if (o.hosted) { f.appendChild(el('<p class="sq-or">or</p>')); f.appendChild(sqButton(o.hosted)); }
    var x = trust(box);
    function close() { box.hidden = true; if (o.card) o.card.classList.remove("paying"); pay.setAttribute("aria-expanded", "false"); }
    x.addEventListener("click", function () { close(); pay.focus(); });
    if (o.card) document.addEventListener("click", function (e) { if (!box.hidden && !box.contains(e.target) && !pay.contains(e.target)) close(); });
    var em = f.querySelector("[type=email]"), msg = f.querySelector(".sq-msg"), go = f.querySelector(".sq-go"),
      ap = f.querySelector(".sq-apple"), gp = f.querySelector(".sq-gpay"), or1 = f.querySelector(".sq-or1");
    var cardObj = null, apple = null, google = null, started = false;
    // One idempotency key per checkout: a retry after a lost reply can't charge twice. A new key only after a definite "failed".
    var idem = key();
    function fail(e) { msg.className = "sq-msg err"; msg.textContent = (e && e.message) || "That didn't go through. Nothing was charged."; go.disabled = false; }
    function validEmail(v) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v || ""); }
    function needEmail() { if (validEmail(em.value.trim())) return true; fail({ message: monthly ? "Add your email first: it's where your membership and monthly invoices go." : "Add your email first: it's where your access goes." }); em.focus(); return false; }
    function finish(t, kind) {
      if (t.status !== "OK") throw new Error((t.errors && t.errors[0] && t.errors[0].message) || "Payment was cancelled.");
      var mail = em.value.trim();
      msg.className = "sq-msg"; msg.textContent = monthly ? "Starting your membership…" : "Processing…";
      if (!monthly) return send("/charge-lifetime", { sourceId: t.token, email: mail, idempotencyKey: idem });
      var b = { plan: o.plan, email: mail, idempotencyKey: idem };
      b[kind === "card" ? "cardToken" : "walletToken"] = t.token;
      return send("/subscribe", b);
    }
    // The last request sent, and the one whose reply was lost. A lost one is resent exactly (same token, same key) on the
    // next click, so Square replays its original result instead of seeing a new payment.
    var last = null, pending = null;
    function send(path, body) { last = { path: path, body: body }; return post(path, body); }
    function run(p, kind) { handle(p.then(function (t) { return finish(t, kind); })); }
    function replay() { msg.className = "sq-msg"; handle(post(pending.path, pending.body)); }
    function handle(reply) {
      go.disabled = true; msg.className = "sq-msg"; msg.textContent = "Processing…";
      reply.then(function (r) {
        pending = null;
        if (!r.ok) { if (!r.keep) idem = key(); throw new Error(r.error || "That didn't go through. Nothing was charged."); }
        var mail = em.value.trim();
        if (!monthly) return done(box, "Lifetime is yours.", "Payment received. Square emails your receipt, and we'll email your access to " + mail + ".");
        done(box, "Welcome to " + (o.name || o.plan) + ".", r.invoiced
          ? "First month paid. Square emails an invoice each month to " + mail + ", payable with Apple Pay, Google Pay or card."
          : "Your membership is active and billed monthly to this card. Square emails your receipt to " + mail + ".");
      }).catch(function (e) { if (e && e.unknown) pending = last; fail(e); });
    }
    function init() {
      if (started) return; started = true;
      load().then(function (p) {
        var req = p.paymentRequest({ countryCode: "US", currencyCode: "USD", total: { amount: o.amount, label: o.label } });
        p.card().then(function (c) { cardObj = c; return c.attach("#sq-card-" + id); }).catch(function () { fail({ message: "The card form didn't load. Use Pay with Square below." }); });
        p.applePay(req).then(function (a) { apple = a; ap.hidden = false; or1.hidden = false; }).catch(function () {});
        p.googlePay(req).then(function (g) { google = g; gp.hidden = false; or1.hidden = false; return g.attach("#sq-gpay-" + id, { buttonColor: "white", buttonType: "plain", buttonSizeMode: "fill" }); }).catch(function () {});
      }).catch(function () { fail({ message: "Payments didn't load. Use Pay with Square below." }); });
    }
    pay.addEventListener("click", function () { setTimeout(function () { if (!box.hidden) init(); }, 0); });
    // Apple requires the sheet to open straight from the tap: the email check is synchronous, tokenize() comes next.
    function wallet(w) { if (pending) return replay(); if (!w || !needEmail()) return; run(w.tokenize(), "wallet"); }
    ap.addEventListener("click", function () { wallet(apple); });
    ap.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); wallet(apple); } });
    gp.addEventListener("click", function () { wallet(google); });
    go.addEventListener("click", function () {
      if (pending) return replay();
      if (!cardObj || !needEmail()) return;
      var v = monthly ? { intent: "STORE", customerInitiated: true, sellerKeyedIn: false, billingContact: { email: em.value.trim() } }
        : { amount: o.amount, currencyCode: "USD", intent: "CHARGE", customerInitiated: true, sellerKeyedIn: false, billingContact: { email: em.value.trim() } };
      run(cardObj.tokenize(v), "card");
    });
  }

  function monthly(card) {
    var plan = card.getAttribute("data-plan"), name = card.getAttribute("data-name") || plan;   // Builder/Buyer/Partner sell as Starter/Pro/Scale
    checkout({ box: card.querySelector(".paybox"), pay: card.querySelector(".pay"), card: card, id: plan, monthly: true, plan: plan, name: name,
      title: name + " · $" + PRICES[plan] + "/month", amount: PRICES[plan], label: "io threads " + name + " (first month)",
      cta: "Subscribe by card · $" + PRICES[plan] + "/mo", hosted: (links[plan] || {}).m || "",
      note: "Card: billed monthly. Apple Pay or Google Pay: first month now, then a monthly invoice by email. Cancel any time." });
  }

  function lifetime() {
    var box = document.getElementById("life-box"), pay = document.getElementById("life-pay");
    if (!box || !pay) return;
    checkout({ box: box, pay: pay, id: "life", monthly: false, title: "Lifetime · $999 once", amount: "999.00",
      label: "io threads Lifetime", cta: "Pay $999 by card", hosted: links.Lifetime || "" });
  }

  function start() {
    document.querySelectorAll(".way[data-plan]").forEach(function (c) { if (PRICES[c.getAttribute("data-plan")] && c.querySelector(".paybox")) monthly(c); });
    lifetime();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
