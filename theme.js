/* Site theme toggle (Dusk / Twilight / Dawn) at the bottom of every page.
   Dusk is the default and sets nothing, so the page follows the device as before. */
(function(){
  var KEY="iot-site-theme", NAMES=[["dusk","Dusk"],["twilight","Twilight"],["dawn","Dawn"]], root=document.documentElement;
  function get(){try{var t=localStorage.getItem(KEY);return t==="twilight"||t==="dawn"?t:"dusk"}catch(x){return "dusk"}}
  function apply(t){
    if(t==="dusk"){root.removeAttribute("data-site");root.removeAttribute("data-theme")}
    else{root.setAttribute("data-site",t);root.setAttribute("data-theme",t==="twilight"?"dark":"light")}
    var m=document.querySelector('meta[name="theme-color"]');
    if(m)m.setAttribute("content",t==="dawn"?"#D9C7A7":t==="twilight"?"#0E2547":"#141D2D");
    document.querySelectorAll(".sitetheme button").forEach(function(b){b.setAttribute("aria-pressed",b.getAttribute("data-t")===t?"true":"false")});
  }
  function build(){
    var box=document.createElement("div");box.className="sitetheme";box.setAttribute("role","group");box.setAttribute("aria-label","Site theme");
    var l=document.createElement("span");l.textContent="Theme";box.appendChild(l);
    NAMES.forEach(function(n){var b=document.createElement("button");b.type="button";b.setAttribute("data-t",n[0]);b.textContent=n[1];
      b.addEventListener("click",function(){try{if(n[0]==="dusk")localStorage.removeItem(KEY);else localStorage.setItem(KEY,n[0])}catch(x){}apply(n[0])});box.appendChild(b)});
    var host=document.querySelector("footer.site > div:last-child")||document.querySelector("footer")||document.querySelector("main")||document.body;
    host.appendChild(box);apply(get());
  }
  window.addEventListener("storage",function(e){if(e.key===KEY)apply(get())});   // other open tabs follow
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",build);else build();
})();
