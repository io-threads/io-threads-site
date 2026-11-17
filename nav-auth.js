/* Header for signed-in members: "Log in" becomes "Account" and "Join now" hides. Reads only the saved session's presence
   (no network, no library), so it can be wrong for an expired session; the Account page checks properly. */
(function () {
  try {
    var K = "sb-tckvatqkjfrvavleunzk-auth-token", raw = sessionStorage.getItem(K) || localStorage.getItem(K);
    var s = raw && JSON.parse(raw);
    if (!s || !s.refresh_token) return;
  } catch (e) { return; }
  document.querySelectorAll("header a.login").forEach(function (a) {
    a.href = "app.html"; a.lastChild.textContent = "Account";
    if (/app\.html$/.test(location.pathname)) a.setAttribute("aria-current", "page");
  });
  document.querySelectorAll('header a.btn.solid[href="join.html"]').forEach(function (a) { a.style.display = "none"; });
})();

