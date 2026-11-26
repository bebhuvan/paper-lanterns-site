// Paper Lanterns: light or dark page, decided before the first paint so a dark page never flashes white.
// The reader's choice is "day", "night" or "auto" (follow the device); it lives in this browser only.
(function () {
  "use strict";
  var root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  var pref = "auto";
  try {
    var stored = window.localStorage.getItem("pl:theme");
    if (stored === "day" || stored === "night") { pref = stored; }
  } catch (err) { /* storage blocked: follow the device */ }

  function apply() {
    root.setAttribute("data-theme-pref", pref);
    root.setAttribute("data-theme", pref === "auto" ? (dark.matches ? "night" : "day") : pref);
  }
  apply();
  dark.addEventListener("change", function () { if (pref === "auto") { apply(); } });

  // site.js calls this when the reader picks a page colour.
  window.plSetTheme = function (value) {
    if (value !== "day" && value !== "night" && value !== "auto") { return; }
    pref = value;
    try {
      if (value === "auto") { window.localStorage.removeItem("pl:theme"); } else { window.localStorage.setItem("pl:theme", value); }
    } catch (err) { /* keep the choice for this page only */ }
    apply();
  };
})();
