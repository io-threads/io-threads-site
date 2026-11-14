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

  // Monthly plans: email, name, card form, subscribe.
  function monthly(card) {
    var plan = card.getAttribute("data-plan"), box = card.querySelector(".paybox"), pay = card.querySelector(".pay");
    var hosted = (links[plan] || {}).m || "";
    shell(box, plan + " · $" + PRICES[plan] + "/month");
    var f = el('<div class="sq-f"><input type="email" autocomplete="email" placeholder="Email for your receipt and access" aria-label="Email" required>' +
      '<input type="text" autocomplete="name" placeholder="Name" aria-label="Name"><div class="sq-card" id="sq-card-' + plan + '"></div>' +
      '<button type="button" class="sq-go">Subscribe · $' + PRICES[plan] + '/mo</button><p class="sq-msg" aria-live="polite">Billed monthly to this card. Cancel any time by emailing team@io-threads.com.</p></div>');
    box.appendChild(f);
    if (hosted) { f.appendChild(el('<p class="sq-or">or</p>')); f.appendChild(sqButton(hosted)); }
    var x = trust(box);
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
      cardObj.tokenize({ intent: "STORE", customerInitiated: true, sellerKeyedIn: false,
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
      '<apple-pay-button class="sq-apple" buttonstyle="black" type="plain" locale="en-US" role="button" tabindex="0" aria-label="Pay with Apple Pay" hidden></apple-pay-button><div id="sq-gpay" hidden></div>' +
      '<p class="sq-or" hidden>or pay by card</p><div class="sq-card" id="sq-card-life"></div>' +
      '<button type="button" class="sq-go">Pay $999</button><p class="sq-msg" aria-live="polite"></p></div>');
    box.appendChild(f);
    if (hosted) { f.appendChild(el('<p class="sq-or">or</p>')); f.appendChild(sqButton(hosted)); }
    var x = trust(box);
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
    ap.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && apple) { e.preventDefault(); if (email()) charge(apple.tokenize()); } });
    gp.addEventListener("click", function () { if (!google) return; if (!email()) return; charge(google.tokenize()); });
    go.addEventListener("click", function () { if (!cardObj || !email()) return; charge(cardObj.tokenize(details())); });
  }

  function start() {
    document.querySelectorAll(".way[data-plan]").forEach(function (c) { if (PRICES[c.getAttribute("data-plan")] && c.querySelector(".paybox")) monthly(c); });
    lifetime();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
