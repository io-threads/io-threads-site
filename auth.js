/* io threads sign-in (Supabase Auth). The publishable key is public by design; data is protected by row-level security.
   Needs vendor/supabase-2.45.4.js loaded first. If it didn't load, gated pages show a message instead of staying blank. */
(function () {
  var URL = "https://tckvatqkjfrvavleunzk.supabase.co", KEY = "sb_publishable_q1qGRS3znQOnod-6whZONg_OrhNQVwJ";
  var GATED = ["app.html", "looop.html", "ops.html"];
  // Cloudflare Turnstile site key (public). Empty = no CAPTCHA widget. Production key: 0x4AAAAAAGGUVG4dTO_J01Xe.
  // It goes live in the same release that turns CAPTCHA on in Supabase production (secret in the Keychain,
  // "turnstile-secret"); a key here without that, or that without a key here, refuses sign-ins.
  // The e2e scripts swap in Cloudflare's always-pass test key for staging.
  var CAPTCHA_SITE_KEY = "";

  // Unhide a gated page and say what went wrong (used when sign-in can't load at all).
  function fail(msg) {
    var root = document.documentElement;
    if (!root.classList.contains("iot-gate")) return;
    root.classList.remove("iot-gate");
    var p = document.createElement("p");
    p.setAttribute("role", "alert");
    p.style.cssText = "max-width:440px;margin:96px auto;padding:16px 20px;border:1px solid var(--rule,#ddd);border-radius:12px;font:400 1rem/1.5 system-ui,sans-serif";
    p.innerHTML = msg + ' <a href="">Reload</a> or email <a href="mailto:team@io-threads.com">team@io-threads.com</a>.';
    document.body.innerHTML = "";
    document.body.appendChild(p);
  }

  // Magic-link errors come back in the URL hash, e.g. #error=access_denied&error_code=otp_expired.
  var hash = new URLSearchParams(location.hash.slice(1));
  var linkError = hash.get("error_code") || hash.get("error");

  if (!window.supabase) {
    window.iotAuth = null;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { fail("Sign-in couldn't load."); });
    else fail("Sign-in couldn't load.");
    return;
  }

  // "Keep me signed in": on (default) keeps the session in localStorage across browser restarts; off keeps it in
  // sessionStorage, so it ends when the browser closes. Storage can be blocked (private mode), so every call is guarded.
  var KEEP = "iot-keep";
  function keep() { try { return localStorage.getItem(KEEP) !== "0"; } catch (e) { return false; } }
  function get(st, k) { try { return st.getItem(k); } catch (e) { return null; } }
  function put(st, k, v) { try { st.setItem(k, v); } catch (e) {} }
  function drop(st, k) { try { st.removeItem(k); } catch (e) {} }
  var storage = {
    getItem: function (k) { return get(sessionStorage, k) || get(localStorage, k); },
    setItem: function (k, v) { if (keep()) { put(localStorage, k, v); drop(sessionStorage, k); } else { put(sessionStorage, k, v); drop(localStorage, k); } },
    removeItem: function (k) { drop(localStorage, k); drop(sessionStorage, k); }
  };
  var sb = window.supabase.createClient(URL, KEY, { auth: { flowType: "implicit", persistSession: true, detectSessionInUrl: true, autoRefreshToken: true, storage: storage } });

  window.iotAuth = {
    sb: sb,
    fn: URL + "/functions/v1",
    linkError: linkError,
    captchaKey: CAPTCHA_SITE_KEY,
    session: function () { return sb.auth.getSession().then(function (r) { return r.data.session; }); },
    // Server-checked: resolves to the user only when the saved session is genuine.
    user: function () { return sb.auth.getUser().then(function (r) { return r.error ? null : r.data.user; }, function () { return null; }); },
    // Only the members pages are valid return targets.
    remember: function (on) { try { localStorage.setItem(KEEP, on ? "1" : "0"); } catch (e) {} },
    safeNext: function (n) { return GATED.indexOf(n) >= 0 ? n : "app.html"; },
    // Hide the page until the server confirms who is viewing; anyone else goes to log in.
    gate: function (page) {
      var timer = setTimeout(function () { fail("Sign-in is taking too long to respond."); }, 8000);
      return sb.auth.getUser().then(function (r) {
        clearTimeout(timer);
        if (r.error || !r.data.user) {
          var q = "next=" + encodeURIComponent(page) + (linkError ? "&err=" + encodeURIComponent(linkError) : "");
          // Drop a saved session the server rejected, or login would send us straight back.
          var go = function () { location.replace("login.html?" + q); };
          sb.auth.signOut({ scope: "local" }).then(go, go);
          return null;
        }
        document.documentElement.classList.remove("iot-gate");
        return sb.auth.getSession().then(function (s) { return s.data.session; });
      }).catch(function () { clearTimeout(timer); fail("Sign-in couldn't be checked."); return null; });
    },
    signOut: function () { return sb.auth.signOut().then(function () { location.href = "./"; }); }
  };

  // Signed out in another tab: leave the members page.
  sb.auth.onAuthStateChange(function (event) {
    if (event === "SIGNED_OUT" && GATED.indexOf(location.pathname.split("/").pop()) >= 0) location.replace("login.html");
  });
})();
