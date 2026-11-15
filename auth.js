/* io threads sign-in (Supabase Auth). The publishable key is public by design; data is protected by row-level security.
   Needs the supabase-js script loaded first. */
(function () {
  var URL = "https://tckvatqkjfrvavleunzk.supabase.co", KEY = "sb_publishable_q1qGRS3znQOnod-6whZONg_OrhNQVwJ";
  var sb = window.supabase.createClient(URL, KEY, { auth: { flowType: "implicit", persistSession: true, detectSessionInUrl: true } });
  window.iotAuth = {
    sb: sb,
    fn: URL + "/functions/v1",
    session: function () { return sb.auth.getSession().then(function (r) { return r.data.session; }); },
    // Only plain page names are allowed as a return target.
    safeNext: function (n) { return /^[a-z0-9-]+\.html(#[a-z0-9-]+)?$/i.test(n || "") ? n : "app.html"; },
    // Hide the page until we know who is viewing; send visitors without a session to log in.
    gate: function (page) {
      return this.session().then(function (s) {
        if (!s) { location.replace("login.html?next=" + encodeURIComponent(page)); return null; }
        document.documentElement.classList.remove("iot-gate");
        return s;
      });
    },
    signOut: function () { return sb.auth.signOut().then(function () { location.href = "./"; }); }
  };
  // Signed in: the header "Log in" link becomes "Account".
  iotAuth.session().then(function (s) {
    if (!s) return;
    document.querySelectorAll("a.login").forEach(function (a) {
      a.href = "app.html"; a.lastChild.textContent = "Account";
    });
  });
})();
