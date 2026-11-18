/* Terms clickwrap for paid checkouts. OFF until the attorney signs off on terms.html and refund.html:
   then set LIVE = true and VERSION to the date on those pages (e.g. "2026-12-01"), and the payment server must accept
   only that version. While off, nothing is shown and window.IOT_TERMS.accepted() is always true.
   Pay code reads window.IOT_TERMS: refuse to start a charge unless accepted(), and send IOT_TERMS.version with it. */
(function () {
  var LIVE = false, VERSION = "";
  var boxes = [];
  window.IOT_TERMS = {
    live: LIVE, version: VERSION,
    accepted: function () { return !LIVE || boxes.some(function (b) { return b.checked; }); }
  };
  if (!LIVE || !VERSION) { window.IOT_TERMS.live = false; return; }
  // One required tick per pay area (elements marked data-terms-gate); its buttons stay disabled until ticked.
  function gate(area) {
    var id = "iot-terms-" + boxes.length, l = document.createElement("label"), c = document.createElement("input"), t = document.createElement("span");
    c.type = "checkbox"; c.id = id; c.required = true; l.htmlFor = id; l.className = "fine";
    t.innerHTML = ' I agree to the <a href="terms.html" target="_blank" rel="noopener">terms</a> and <a href="refund.html" target="_blank" rel="noopener">cancellation and refund policy</a>.';
    l.appendChild(c); l.appendChild(t); area.insertBefore(l, area.firstChild); boxes.push(c);
    var btns = area.querySelectorAll("button, a.btn");
    function sync() { [].forEach.call(btns, function (b) { if (b.tagName === "A") b.setAttribute("aria-disabled", String(!c.checked)); else b.disabled = !c.checked; }); }
    c.addEventListener("change", sync); sync();
    area.addEventListener("click", function (e) { if (!c.checked && e.target.closest("a.btn")) { e.preventDefault(); c.focus(); } }, true);
  }
  function run() { [].forEach.call(document.querySelectorAll("[data-terms-gate]"), gate); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
