// Paper Lanterns: small progressive enhancements. Every page reads fully without this file.
// DOM is built with createElement/textContent only (no innerHTML), so the strict CSP holds.
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");

  // Reading preferences live in this browser only; storage can be missing or blocked.
  function load(key) {
    try { return window.localStorage.getItem("pl:" + key); } catch (err) { return null; }
  }
  function save(key, value) {
    try { window.localStorage.setItem("pl:" + key, value); } catch (err) { /* private mode: keep the choice for this page only */ }
  }
  // The page colour is decided by theme.js before the first paint; size and width are applied here.
  var PREFS = { size: ["0", "1", "2", "3"], width: ["0", "1", "2"], theme: ["day", "night", "auto"] };
  function applyPref(name, value) {
    if (PREFS[name].indexOf(value) === -1) { return; }
    if (name === "theme") {
      if (window.plSetTheme) { window.plSetTheme(value); }
    } else {
      root.setAttribute("data-" + name, value);
    }
    document.querySelectorAll('[data-pref="' + name + '"]').forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-value") === value ? "true" : "false");
    });
  }
  ["size", "width"].forEach(function (name) {
    var stored = load(name);
    if (stored !== null) { applyPref(name, stored); }
  });
  function markTheme() {
    var pref = root.getAttribute("data-theme-pref") || "auto";
    all('[data-pref="theme"]').forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-value") === pref ? "true" : "false"); });
    var night = root.getAttribute("data-theme") === "night";
    all("[data-theme-toggle]").forEach(function (b) { b.setAttribute("aria-label", night ? "Light page" : "Dark page"); });
  }
  function initTheme() {
    markTheme();
    all("[data-theme-toggle]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!window.plSetTheme) { return; }
        window.plSetTheme(root.getAttribute("data-theme") === "night" ? "day" : "night");
        markTheme();
      });
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", markTheme);
  }

  function all(sel, scope) { return Array.prototype.slice.call((scope || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function initHome() {
    var detail = document.querySelector("[data-sal-detail]");
    if (detail) {
      var show = function (a) {
        all("[data-salutations] a").forEach(function (x) { x.classList.toggle("on", x === a); });
        detail.replaceChildren(
          el("span", "", a.dataset.from),
          (function () {
            var g = el("span", "glyph");
            g.setAttribute("aria-hidden", "true");
            g.append(el("span", "a"), el("span", "l"), el("span", "b"));
            var wrap = el("span", "pair");
            wrap.append(g);
            return wrap;
          })(),
          el("span", "", a.dataset.to),
          el("span", "mono", a.dataset.date),
          el("span", "book", a.dataset.book)
        );
      };
      all("[data-salutations] a").forEach(function (a) {
        a.addEventListener("mouseenter", function () { show(a); });
        a.addEventListener("focus", function () { show(a); });
      });
    }

    var chart = document.querySelector("[data-decades]");
    var table = document.querySelector("[data-decade-table]");
    var panel = document.querySelector("[data-decade-detail]");
    if (!chart || !table || !panel) { return; }
    var field = function (name) { return panel.querySelector('[data-f="' + name + '"]'); };
    var select = function (g) {
      var decade = g.getAttribute("data-decade");
      var row = table.querySelector('tr[data-decade="' + decade + '"]');
      if (!row) { return; }
      all(".lantern", chart).forEach(function (x) {
        var on = x === g;
        x.classList.toggle("on", on);
        x.setAttribute("aria-pressed", on ? "true" : "false");
        x.querySelector(".bulb").setAttribute("r", on ? "7.5" : "4.5");
      });
      var n = Number(row.dataset.count);
      field("decade").textContent = decade + "s";
      field("count").textContent = String(n);
      field("unit").textContent = n === 1 ? "letter" : "letters";
      field("rank").textContent = row.dataset.rank;
      field("share").setAttribute("width", String(Math.max(1, Number(row.dataset.share) * 100)));
      var items = all("[data-writer]", row).map(function (s) {
        var li = el("li", "", s.dataset.writer);
        li.append(el("span", "sub", s.dataset.sub));
        return li;
      });
      field("books").replaceChildren.apply(field("books"), items);
      var link = field("link");
      if (link) {
        link.setAttribute("href", "/explore/" + decade + "s/");
        field("linktext").textContent = "Read the letters of the " + decade + "s";
      }
    };
    all(".lantern", chart).forEach(function (g) {
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", g.querySelector("title").textContent);
      g.setAttribute("aria-pressed", g.classList.contains("on") ? "true" : "false");
      g.addEventListener("click", function () { select(g); });
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(g); }
      });
    });
  }

  // Book page tabs: underline the group currently on screen and keep its tab visible in the scrolling strip.
  function initTabs() {
    var tabs = document.querySelector("[data-tabs]");
    if (!tabs || !("IntersectionObserver" in window)) { return; }
    var links = {};
    all("[data-tab]", tabs).forEach(function (a) { links[a.getAttribute("data-tab")] = a; });
    var mark = function (id) {
      Object.keys(links).forEach(function (k) { links[k].setAttribute("aria-current", k === id ? "true" : "false"); });
      var a = links[id];
      if (a) { a.scrollIntoView({ block: "nearest", inline: "nearest" }); }
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { mark(e.target.id); } });
    }, { rootMargin: "-30% 0px -60% 0px" });
    all("[data-group]").forEach(function (g) { io.observe(g); });
  }

  function initBook() {
    initTabs();
    var input = document.querySelector("[data-find-input]");
    var status = document.querySelector("[data-find-status]");
    if (!input) { return; }
    var fold = function (s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };
    var rows = all("[data-find]").map(function (li) { return { li: li, text: fold(li.textContent) }; });
    input.addEventListener("input", function () {
      var q = fold(input.value.trim());
      var shown = 0;
      rows.forEach(function (r) {
        var hit = !q || r.text.indexOf(q) !== -1;
        r.li.hidden = !hit;
        if (hit) { shown += 1; }
      });
      all("[data-find-group]").forEach(function (g) { g.hidden = !g.querySelector("[data-find]:not([hidden])"); });
      status.textContent = q ? shown + (shown === 1 ? " letter matches" : " letters match") : "";
    });
  }

  function initLetter() {
    var reading = document.querySelector("[data-reading]");
    if (!reading) { return; }
    var phone = window.matchMedia("(max-width: 900px)");
    var panel = document.getElementById("panel");

    // Light a passage on its scan using the block's bbox (0..1000 on both axes of the page image).
    var light = function (blk, scroll) {
      var page = blk.getAttribute("data-page");
      var box = (blk.getAttribute("data-bbox") || "").split(" ").map(Number);
      all("[data-letter-text] .blk.lit").forEach(function (b) { b.classList.remove("lit"); });
      blk.classList.add("lit");
      all("[data-scan] figure").forEach(function (f) { f.classList.toggle("current", f.getAttribute("data-page") === page); });
      var fig = document.getElementById("scan-p" + page);
      if (!fig || box.length !== 4) { return; }
      var pad = 6;
      var x = Math.max(0, box[0] - pad), y = Math.max(0, box[1] - pad);
      var w = Math.min(1000, box[2] + pad) - x, h = Math.min(1000, box[3] + pad) - y;
      var r = fig.querySelector(".light"), bar = fig.querySelector(".light-bar");
      [["x", x], ["y", y], ["width", w], ["height", h]].forEach(function (kv) { r.setAttribute(kv[0], String(kv[1])); });
      [["x", Math.max(0, x - 14)], ["y", y], ["width", 4], ["height", h]].forEach(function (kv) { bar.setAttribute(kv[0], String(kv[1])); });
      if (scroll && phone.matches) {
        setView("page");
        revealLight(fig, y);
      }
    };
    // Scroll so the lit lines sit near the top of the screen, once the scan has a height.
    var revealLight = function (fig, y) {
      var img = fig.querySelector("img");
      var go = function () {
        var frame = fig.querySelector(".frame").getBoundingClientRect();
        window.scrollTo({ top: Math.max(0, window.scrollY + frame.top + frame.height * (y / 1000) - 96) });
      };
      if (img && !img.complete) { img.addEventListener("load", go, { once: true }); }
      go();
    };
    var hasScan = !!document.querySelector("[data-scan]");
    all("[data-letter-text] .blk").forEach(function (blk) {
      if (!hasScan) { return; }
      blk.setAttribute("tabindex", "0");
      blk.addEventListener("click", function (e) {
        if (e.target.closest("a")) { return; }
        light(blk, true);
      });
      blk.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); light(blk, true); }
      });
    });
    var target = window.location.hash && document.getElementById(window.location.hash.slice(1));
    if (target && target.classList.contains("blk")) { light(target, false); }

    var setView = function (view) {
      reading.setAttribute("data-view", view);
      all("[data-view]", document.querySelector(".view-seg")).forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-view") === view ? "true" : "false");
      });
      all("[data-view-toggle]").forEach(function (b) { b.setAttribute("aria-pressed", view === "page" ? "true" : "false"); });
      all("[data-view-toggle-label]").forEach(function (l) { l.textContent = view === "page" ? "Text" : "Scan"; });
    };
    all("[data-back-to-text]").forEach(function (b) {
      b.addEventListener("click", function () {
        setView("text");
        var lit = document.querySelector("[data-letter-text] .blk.lit");
        if (lit) { lit.scrollIntoView({ block: "center" }); lit.focus({ preventScroll: true }); } else { window.scrollTo({ top: 0 }); }
      });
    });
    all(".view-seg [data-view]").forEach(function (b) {
      b.addEventListener("click", function () { setView(b.getAttribute("data-view")); });
    });
    all("[data-view-toggle]").forEach(function (b) {
      b.addEventListener("click", function () {
        var toPage = reading.getAttribute("data-view") !== "page";
        setView(toPage ? "page" : "both");
        var lit = document.querySelector("[data-letter-text] .blk.lit");
        if (toPage && lit) {
          revealLight(document.querySelector("[data-scan] figure.current"), Number((lit.getAttribute("data-bbox") || "0 0").split(" ")[1]));
        } else if (lit) {
          lit.scrollIntoView({ block: "center" });
        } else {
          window.scrollTo({ top: 0 });
        }
      });
    });

    // The letters rail sits beside the text from 901px (and can be hidden); on phones it is a sheet from the bottom.
    // Reading settings are a sheet on phones and a small panel under the toolbar on computers.
    var prefs = document.getElementById("prefs");
    var scrim = document.querySelector("[data-sheet-scrim]");
    var wide = window.matchMedia("(min-width: 901px)");
    var opener = null;
    var setExpanded = function (sel, open) { all(sel).forEach(function (b) { b.setAttribute("aria-expanded", open ? "true" : "false"); }); };
    var syncScrim = function () {
      var phonePanel = !wide.matches && panel.classList.contains("open");
      var any = phonePanel || (prefs && !prefs.hidden);
      if (scrim) { scrim.hidden = !any; }
      root.classList.toggle("sheet-open", Boolean(any));
    };
    var togglePanel = function (open) {
      var isOpen = typeof open === "boolean" ? open : !panel.classList.contains("open");
      panel.classList.toggle("open", isOpen);
      panel.hidden = !isOpen && wide.matches;
      setExpanded("[data-panel-toggle][aria-expanded]", isOpen);
      if (isOpen && !wide.matches) {
        if (prefs) { prefs.hidden = true; setExpanded("[data-prefs-open]", false); }
        var here = panel.querySelector('[aria-current="page"]');
        if (here) { here.scrollIntoView({ block: "center" }); }
        panel.focus({ preventScroll: true });
      }
      syncScrim();
    };
    var togglePrefs = function (open) {
      if (!prefs) { return; }
      var isOpen = typeof open === "boolean" ? open : prefs.hidden;
      prefs.hidden = !isOpen;
      setExpanded("[data-prefs-open]", isOpen);
      if (isOpen) {
        if (!wide.matches && panel.classList.contains("open")) { togglePanel(false); }
        prefs.focus({ preventScroll: true });
      } else if (opener) {
        opener.focus({ preventScroll: true });
      }
      syncScrim();
    };
    if (wide.matches) {
      panel.classList.add("open");
      setExpanded("[data-panel-toggle][aria-expanded]", true);
    }
    wide.addEventListener("change", function (e) {
      panel.hidden = false;
      panel.classList.toggle("open", e.matches);
      setExpanded("[data-panel-toggle][aria-expanded]", e.matches);
      syncScrim();
    });
    all("[data-panel-toggle]").forEach(function (b) { b.addEventListener("click", function () { togglePanel(); }); });
    all("[data-prefs-open]").forEach(function (b) {
      b.addEventListener("click", function () { opener = b; togglePrefs(); });
    });
    all("[data-prefs-close]").forEach(function (b) { b.addEventListener("click", function () { togglePrefs(false); }); });
    if (scrim) {
      scrim.addEventListener("click", function () {
        togglePrefs(false);
        if (!wide.matches) { togglePanel(false); }
      });
    }

    all("[data-pref]").forEach(function (b) {
      b.addEventListener("click", function () {
        var name = b.getAttribute("data-pref"), value = b.getAttribute("data-value");
        applyPref(name, value);
        if (name === "theme") { markTheme(); } else { save(name, value); }
      });
    });

    var setFocus = function (on) {
      root.classList.toggle("focus", on);
      all("[data-focus]").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
      if (on) { togglePrefs(false); }
    };
    all("[data-focus]").forEach(function (b) { b.addEventListener("click", function () { setFocus(!root.classList.contains("focus")); }); });
    all("[data-focus-leave]").forEach(function (b) { b.addEventListener("click", function () { setFocus(false); }); });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") { return; }
      if (prefs && !prefs.hidden) { togglePrefs(false); } else if (!wide.matches && panel.classList.contains("open")) { togglePanel(false); } else if (root.classList.contains("focus")) { setFocus(false); }
    });

    var cite = document.querySelector("[data-cite]");
    if (cite) {
      var current = "text";
      all("[data-fmt]", cite).forEach(function (b) {
        b.addEventListener("click", function () {
          current = b.getAttribute("data-fmt");
          all("[data-fmt]", cite).forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
          all("[data-fmt-panel]", cite).forEach(function (p) { p.classList.toggle("current", p.getAttribute("data-fmt-panel") === current); });
        });
      });
      var copyBtn = cite.querySelector("[data-copy]");
      var label = cite.querySelector("[data-copy-label]");
      copyBtn.addEventListener("click", function () {
        var panelEl = cite.querySelector('[data-fmt-panel="' + current + '"]');
        var clone = panelEl.cloneNode(true);
        var k = clone.querySelector(".k");
        if (k) { k.remove(); }
        var text = clone.textContent.trim();
        var done = function (msg) { label.textContent = msg; };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { done("Copied"); }, function () { done("Select and copy"); });
        } else {
          done("Select and copy");
        }
      });
    }
  }

  // Search: Pagefind's static index, loaded only on /search/. Results are built from text nodes; the excerpt's
  // <mark> highlights are copied as elements, everything else in it as plain text (no HTML is inserted).
  function initSearch() {
    var form = document.querySelector("[data-search-form]");
    if (!form) { return; }
    var input = form.querySelector("[data-search-input]");
    var status = document.querySelector("[data-search-status]");
    var list = document.querySelector("[data-search-results]");
    var pagefind = null;
    var current = [];
    var shown = 0;
    var excerptNodes = function (html) {
      var doc = new DOMParser().parseFromString("<p>" + html + "</p>", "text/html");
      var out = [];
      doc.body.firstChild.childNodes.forEach(function (n) {
        if (n.nodeName === "MARK") { out.push(el("mark", "", n.textContent)); } else { out.push(document.createTextNode(n.textContent)); }
      });
      return out;
    };
    var renderMore = function () {
      var batch = current.slice(shown, shown + 10);
      shown += batch.length;
      var old = list.querySelector(".more");
      if (old) { old.remove(); }
      return Promise.all(batch.map(function (r) { return r.data(); })).then(function (items) {
        items.forEach(function (d) {
          var li = el("li");
          var a = el("a");
          a.href = d.url;
          a.append(el("span", "rt", (d.meta && d.meta.title) || d.url));
          if (d.meta && d.meta.where) { a.append(el("span", "rw", d.meta.where)); }
          var x = el("span", "rx");
          x.append.apply(x, excerptNodes(d.excerpt || ""));
          a.append(x);
          li.append(a);
          list.append(li);
        });
        if (shown < current.length) {
          var li = el("li", "more");
          var b = el("button", "btn", "Show more");
          b.type = "button";
          b.addEventListener("click", function () { renderMore(); });
          li.append(b);
          list.append(li);
        }
      });
    };
    var run = function (q) {
      q = q.trim();
      try { history.replaceState(null, "", q ? "?q=" + encodeURIComponent(q) : location.pathname); } catch (err) { /* history unavailable: the search still runs */ }
      if (!q) { list.replaceChildren(); status.textContent = ""; return; }
      status.textContent = "Searching…";
      var load = pagefind ? Promise.resolve(pagefind) : import("/pagefind/pagefind.js").then(function (m) { pagefind = m; return m; });
      load.then(function (pf) { return pf.debouncedSearch(q); }).then(function (search) {
        if (!search) { return; }
        current = search.results;
        shown = 0;
        list.replaceChildren();
        status.textContent = current.length ? current.length + (current.length === 1 ? " result" : " results") : "Nothing found. Try another word or a different spelling.";
        return renderMore();
      }).catch(function () { status.textContent = "Search could not load. Please reload the page."; });
    };
    form.addEventListener("submit", function (e) { e.preventDefault(); run(input.value); });
    input.addEventListener("input", function () { run(input.value); });
    var initial = new URLSearchParams(location.search).get("q");
    if (initial) { input.value = initial; run(initial); }
  }

  // Menu sheet: works as a plain <details> without JavaScript; with it, the page behind stops scrolling,
  // Escape closes it and focus moves to the first link.
  function initMenu() {
    var menu = document.querySelector("[data-menu]");
    if (!menu) { return; }
    menu.addEventListener("toggle", function () {
      root.classList.toggle("menu-open", menu.open);
      if (menu.open) {
        var first = menu.querySelector(".sheet-search");
        if (first) { first.focus(); }
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
    });
  }

  // Header: hidden while scrolling down past the first screenful, shown again on any scroll up. Never hidden while
  // the menu is open. Sets --header-offset so sticky group headings sit beneath it.
  function initHeader() {
    var header = document.querySelector(".site-header");
    if (!header) { return; }
    var menu = header.querySelector("[data-menu]");
    var last = window.scrollY;
    var ticking = false;
    var update = function () {
      ticking = false;
      var y = window.scrollY;
      var hide = y > 160 && y > last + 4 && !(menu && menu.open);
      var show = y < last - 4 || y < 80;
      if (hide) { header.classList.add("is-hidden"); }
      if (show) { header.classList.remove("is-hidden"); }
      header.classList.toggle("is-stuck", y > 8);
      var visible = !header.classList.contains("is-hidden");
      root.style.setProperty("--header-offset", visible ? header.offsetHeight + "px" : "0px");
      if (Math.abs(y - last) > 4) { last = y; }
    };
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  // WebMCP (W3C draft): expose read-only search and citation tools to agentic browsers when supported.
  function initWebMCP() {
    if (!navigator.modelContext || typeof navigator.modelContext.registerTool !== "function") { return; }
    try {
      navigator.modelContext.registerTool({
        name: "search_paper_lanterns",
        description: "Search all public-domain letters, books, essays, lectures, and speeches on Paper Lanterns.",
        inputSchema: {
          type: "object",
          properties: { query: { type: "string", description: "Search keywords, correspondent name, or quote" } },
          required: ["query"]
        },
        execute: function (args) {
          var q = String((args && args.query) || "").trim();
          if (!q) { return Promise.resolve({ results: [] }); }
          return import("/pagefind/pagefind.js")
            .then(function (pf) { return pf.search(q); })
            .then(function (res) { return Promise.all(res.results.slice(0, 10).map(function (r) { return r.data(); })); })
            .then(function (items) {
              return {
                results: items.map(function (d) {
                  return {
                    title: (d.meta && d.meta.title) || d.url,
                    where: (d.meta && d.meta.where) || "",
                    url: new URL(d.url, location.origin).href,
                    excerpt: (d.excerpt || "").replace(/<[^>]+>/g, "")
                  };
                })
              };
            });
        }
      });
      navigator.modelContext.registerTool({
        name: "get_page_metadata",
        description: "Return canonical URL, citation, and Schema.org JSON-LD metadata for the current Paper Lanterns page.",
        inputSchema: { type: "object", properties: {} },
        execute: function () {
          var ld = all('script[type="application/ld+json"]').map(function (s) {
            try { return JSON.parse(s.textContent); } catch (e) { return null; }
          }).filter(Boolean);
          var cite = document.querySelector('[data-fmt-panel="text"]');
          return Promise.resolve({
            url: location.href,
            title: document.title,
            citation: cite ? cite.textContent.replace(/^Citation/, "").trim() : "",
            schema: ld
          });
        }
      });
    } catch (err) { /* ignore unsupported WebMCP draft signatures */ }
  }

  function start() { initTheme(); initHeader(); initMenu(); initHome(); initBook(); initLetter(); initSearch(); initWebMCP(); }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", start); } else { start(); }
})();
