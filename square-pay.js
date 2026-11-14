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
  function post(path, body) {
    return fetch(cfg.api + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); });
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  var LOCK = '<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><rect x="2" y="5.5" width="8" height="5.5" rx="1.2" fill="currentColor"/><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';

  var css = document.createElement("style");
  css.textContent = ".sq-f{display:grid;gap:8px}.sq-f input{font:400 .95rem/1.2 var(--f-display);color:var(--ink);background:var(--paper);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;min-height:44px;width:100%;box-sizing:border-box}" +
    ".sq-f input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}.sq-card{min-height:90px}.sq-msg{margin:0;font:400 .85rem/1.35 var(--f-display);color:var(--muted)}.sq-msg.err{color:#c0392b}" +
    ".sq-go{all:unset;box-sizing:border-box;cursor:pointer;min-height:44px;border-radius:8px;display:grid;place-items:center;font:600 .98rem/1 var(--f-display);background:var(--ink);color:var(--paper)}.sq-go[disabled]{opacity:.5;cursor:wait}" +
    ".sq-apple{-webkit-appearance:-apple-pay-button;-apple-pay-button-type:plain;-apple-pay-button-style:black;display:block;width:100%;height:44px;border-radius:8px;cursor:pointer}.sq-or{margin:0;text-align:center;font:400 .78rem/1 var(--f-display);color:var(--muted)}" +
    ".sq-done{display:grid;gap:6px;text-align:center;padding:8px 0}.sq-done b{font:600 1.05rem/1.3 var(--f-display);color:var(--ink)}.sq-alt{justify-self:center;font:400 .8rem/1 var(--f-display);color:var(--muted)}";
  document.head.appendChild(css);

  function shell(box, sum) {
    box.innerHTML = "";
    box.appendChild(el('<p class="pb-sum">' + sum + "</p>"));
    return box;
  }
  function trust(box, fallback) {
    box.appendChild(el('<p class="pb-t">' + LOCK + "Secure checkout by Square · billed as Io Threads</p>"));
    if (fallback) box.appendChild(el('<a class="sq-alt" href="' + fallback + '">Or pay on Square\'s page</a>'));
    var x = el('<button type="button" class="pb-x">Cancel</button>');
    box.appendChild(x);
    return x;
  }
  function done(box, title, line) {
    box.innerHTML = '<div class="sq-done"><b>' + title + '</b><p class="sq-msg">' + line + "</p></div>";
  }

  // Monthly plans: email, name, card form, subscribe.
  function monthly(card) {
    var plan = card.getAttribute("data-plan"), box = card.querySelector(".paybox"), pay = card.querySelector(".pay");
    var hosted = (links[plan] || {}).m || "";
    shell(box, plan + " · $" + PRICES[plan] + "/month");
    var f = el('<div class="sq-f"><input type="email" autocomplete="email" placeholder="Email for your receipt and access" aria-label="Email" required>' +
      '<input type="text" autocomplete="name" placeholder="Name" aria-label="Name"><div class="sq-card" id="sq-card-' + plan + '"></div>' +
      '<button type="button" class="sq-go">Subscribe · $' + PRICES[plan] + '/mo</button><p class="sq-msg" aria-live="polite">Billed monthly to this card. Cancel any time by emailing team@io-threads.com.</p></div>');
    box.appendChild(f);
    var x = trust(box, hosted);
    x.addEventListener("click", function () { box.hidden = true; card.classList.remove("paying"); pay.focus(); });
    var cardObj = null, go = f.querySelector(".sq-go"), msg = f.querySelector(".sq-msg"), em = f.querySelector('[type=email]'), nm = f.querySelector('[type=text]');
    function init() {
      if (cardObj) return;
      load().then(function (p) { return p.card(); }).then(function (c) { cardObj = c; return c.attach("#sq-card-" + plan); })
        .catch(function () { msg.className = "sq-msg err"; msg.textContent = "The card form didn't load. Use the link below to pay on Square's page."; });
    }
    pay.addEventListener("click", function () { if (!box.hidden) init(); });
    go.addEventListener("click", function () {
      if (!cardObj) return;
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em.value.trim())) { msg.className = "sq-msg err"; msg.textContent = "Enter your email."; em.focus(); return; }
      go.disabled = true; msg.className = "sq-msg"; msg.textContent = "Checking your card…";
      var name = nm.value.trim();
      cardObj.tokenize({ intent: "STORE", customerInitiated: true, sellerKeyedIn: false, currencyCode: "USD",
        billingContact: { email: em.value.trim(), givenName: name.split(" ")[0] || undefined, familyName: name.split(" ").slice(1).join(" ") || undefined } })
        .then(function (t) {
          if (t.status !== "OK") throw new Error((t.errors && t.errors[0] && t.errors[0].message) || "Check your card details.");
          msg.textContent = "Starting your membership…";
          return post("/subscribe", { plan: plan, cardToken: t.token, email: em.value.trim(), name: name, idempotencyKey: key() });
        })
        .then(function (r) {
          if (!r.ok) throw new Error(r.error || "That didn't go through. Nothing was charged.");
          done(box, "Welcome to " + plan + ".", "Your membership is active. Square emails your receipt, and we'll email your access to " + em.value.trim() + ".");
        })
        .catch(function (e) { go.disabled = false; msg.className = "sq-msg err"; msg.textContent = e.message; });
    });
  }

  // Lifetime: Apple Pay, Google Pay or card, one charge of $999.
  function lifetime() {
    var box = document.getElementById("life-box"), pay = document.getElementById("life-pay");
    if (!box || !pay) return;
    var hosted = links.Lifetime || "";
    shell(box, "Lifetime · $999 once");
    var f = el('<div class="sq-f"><input type="email" autocomplete="email" placeholder="Email for your receipt and access" aria-label="Email" required>' +
      '<button type="button" class="sq-apple" aria-label="Pay with Apple Pay" hidden></button><div id="sq-gpay" hidden></div>' +
      '<p class="sq-or" hidden>or pay by card</p><div class="sq-card" id="sq-card-life"></div>' +
      '<button type="button" class="sq-go">Pay $999</button><p class="sq-msg" aria-live="polite"></p></div>');
    box.appendChild(f);
    var x = trust(box, hosted);
    x.addEventListener("click", function () { box.hidden = true; pay.focus(); });
    var em = f.querySelector('[type=email]'), msg = f.querySelector(".sq-msg"), go = f.querySelector(".sq-go"), ap = f.querySelector(".sq-apple"), gp = f.querySelector("#sq-gpay"), or = f.querySelector(".sq-or");
    var cardObj = null, apple = null, google = null, started = false;
    function fail(e) { msg.className = "sq-msg err"; msg.textContent = (e && e.message) || "That didn't go through. Nothing was charged."; go.disabled = false; }
    function email() { var v = em.value.trim(); if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return v; fail({ message: "Enter your email first." }); em.focus(); return null; }
    function charge(tokenPromise) {
      msg.className = "sq-msg"; msg.textContent = "Processing…"; go.disabled = true;
      tokenPromise.then(function (t) {
        if (t.status !== "OK") throw new Error((t.errors && t.errors[0] && t.errors[0].message) || "Payment was cancelled.");
        return post("/charge-lifetime", { sourceId: t.token, email: em.value.trim(), idempotencyKey: key() });
      }).then(function (r) {
        if (!r.ok) throw new Error(r.error || "That didn't go through. Nothing was charged.");
        done(box, "Lifetime is yours.", "Payment received. Square emails your receipt, and we'll email your access to " + em.value.trim() + ".");
      }).catch(fail);
    }
    var details = function () { return { amount: "999.00", currencyCode: "USD", intent: "CHARGE", customerInitiated: true, sellerKeyedIn: false, billingContact: { email: em.value.trim() } }; };
    function init() {
      if (started) return; started = true;
      load().then(function (p) {
        var req = p.paymentRequest({ countryCode: "US", currencyCode: "USD", total: { amount: "999.00", label: "io threads Lifetime" } });
        p.card().then(function (c) { cardObj = c; return c.attach("#sq-card-life"); }).catch(function () { fail({ message: "The card form didn't load. Use the link below to pay on Square's page." }); });
        p.applePay(req).then(function (a) { apple = a; ap.hidden = false; or.hidden = false; }).catch(function () {});
        p.googlePay(req).then(function (g) { google = g; gp.hidden = false; or.hidden = false; return g.attach("#sq-gpay", { buttonColor: "white", buttonType: "plain", buttonSizeMode: "fill" }); }).catch(function () {});
      }).catch(function () { fail({ message: "Payments didn't load. Use the link below to pay on Square's page." }); });
    }
    pay.addEventListener("click", function () { setTimeout(function () { if (!box.hidden) init(); }, 0); });
    // Apple requires the sheet to open straight from the tap, so tokenize() is the first call.
    ap.addEventListener("click", function () { if (!apple) return; if (!email()) return; charge(apple.tokenize()); });
    gp.addEventListener("click", function () { if (!google) return; if (!email()) return; charge(google.tokenize()); });
    go.addEventListener("click", function () { if (!cardObj || !email()) return; charge(cardObj.tokenize(details())); });
  }

  function start() {
    document.querySelectorAll(".way[data-plan]").forEach(function (c) { if (PRICES[c.getAttribute("data-plan")] && c.querySelector(".paybox")) monthly(c); });
    lifetime();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
