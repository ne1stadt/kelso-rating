/* Kelso: shared client helpers, the header cube, search suggestions and the cube loader. */
(function () {
  "use strict";
  var K = (window.Kelso = window.Kelso || {});
  var EVENTS = ["333", "222", "444", "555", "666", "777", "333bf", "333fm", "333oh", "clock", "minx", "pyram", "skewb", "sq1", "444bf", "555bf", "333mbf"];
  var SHORT = { "333": "3x3", "222": "2x2", "444": "4x4", "555": "5x5", "666": "6x6", "777": "7x7", "333bf": "3BLD", "333fm": "FMC", "333oh": "OH",
    clock: "Clock", minx: "Megaminx", pyram: "Pyraminx", skewb: "Skewb", sq1: "Square-1", "444bf": "4BLD", "555bf": "5BLD", "333mbf": "MBLD" };
  K.EVENTS = EVENTS; K.SHORT = SHORT;

  // ------------------------------------------------------------ formatting (mirrors web/fmt.py)
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  K.fmtTime = function (cs) {
    if (!(cs > 0)) return "";
    var s = Math.floor(cs / 100), c = cs % 100, h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    s = s % 60;
    if (h) return h + ":" + pad(m) + ":" + pad(s) + "." + pad(c);
    if (m) return m + ":" + pad(s) + "." + pad(c);
    return s + "." + pad(c);
  };
  K.fmtMbf = function (v) {
    var dd = Math.floor(v / 1e7), tt = Math.floor(v / 100) % 1e5, mm = v % 100, solved = 99 - dd + mm;
    return solved + "/" + (solved + mm) + " " + Math.floor(tt / 60) + ":" + pad(tt % 60);
  };
  K.fmtResult = function (e, raw) {
    if (!(raw > 0)) return "";
    if (e === "333mbf") return K.fmtMbf(raw);
    if (e === "333fm") return (raw / 100).toFixed(2);
    return K.fmtTime(raw);
  };
  K.fmtDelta = function (x) {
    var r = Math.round(x);
    return r > 0 ? "+" + r : r === 0 ? "±0" : "−" + Math.abs(r);
  };
  K.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  };
  K.flag = function (iso2) {
    return iso2 && /^[A-Z]{2}$/.test(iso2) && !/^X/.test(iso2)
      ? '<img class="flag" loading="lazy" alt="' + iso2 + '" src="/static/flags/' + iso2.toLowerCase() + '.svg">' : "";
  };
  K.icon = function (e, title) {
    return '<span class="cubing-icon event-' + e + '" title="' + K.esc(title || SHORT[e]) + '"></span>';
  };

  // ------------------------------------------------------------ algorithms
  // window.KelsoAlgs: [set, name, alg] rows, every one verified by scripts/check_algs.js
  K.randomAlg = function () {
    var list = window.KelsoAlgs || [["PLL", "T", "R U R' U' R' F R2 U' R' U' R U R' F'"]];
    var a = list[Math.floor(Math.random() * list.length)];
    return { set: a[0], name: a[1], alg: a[2], label: a[0] + (a[1] ? " · " + a[1] : "") };
  };

  // ------------------------------------------------------------ header cube
  // The logo keeps its moves across page loads (sessionStorage). Hovering it, and every
  // navigation, plays a random OLL / PLL / ZBLS algorithm; going home through the logo plays
  // the whole history backwards. Very long histories rewind on their own.
  var REST = { axis: 1, layer: 1, angle: -0.38 };   // the logo's signature twisted top layer
  var MAX_HISTORY = 160;
  function store(key, val) { try { if (val === undefined) return JSON.parse(sessionStorage.getItem(key) || "null"); sessionStorage.setItem(key, JSON.stringify(val)); } catch (e) { return null; } }

  function initBrandCube() {
    var host = document.getElementById("brand-cube");
    if (!host || !window.KelsoCube) return;
    var saved = store("kelso-cube-v2") || {}, history = saved.history || [], state;
    try { state = KelsoCube.applyAlg(KelsoCube.solved(), history.join(" ")); } catch (e) { history = []; state = KelsoCube.solved(); }
    var cube = new KelsoCube.Cube(host, { size: 64, state: state, history: history, rest: REST });
    var link = host.closest("a");
    function save(pending) { store("kelso-cube-v2", { history: cube.history, pending: pending || null }); }
    function playRandom(total) {
      var a = K.randomAlg();
      if (link) link.title = a.label + ": " + a.alg;
      cube.play(a.alg, { total: total });
    }
    cube.onturn = function () { save(); };
    var pending = saved.pending;
    if (pending === "solve") setTimeout(function () { cube.solve(1400); }, 100);
    else if (pending === "alg") setTimeout(function () { playRandom(1500); }, 80);
    save();

    host.addEventListener("mouseenter", function () { if (!cube.busy) playRandom(1700); });
    document.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || a.target || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      var url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.pathname.indexOf("/static/") === 0 || url.pathname.indexOf("/api/") === 0) return;
      var home = a.classList.contains("brand") || cube.history.length > MAX_HISTORY;
      save(home ? "solve" : "alg");
    });
    K.brandCube = cube;
  }

  // ------------------------------------------------------------ loader: the cube solves case after case
  // Each round sets up the case of a random algorithm and plays the algorithm with its notation
  // underneath, the current move highlighted. Longer algorithms play faster.
  K.loader = function (el, text) {
    el.innerHTML = '<div class="loader"><svg viewBox="0 0 64 64" aria-hidden="true"></svg>' +
      '<div class="alg-label"></div><div class="alg" aria-hidden="true"></div><div>' + K.esc(text || "Loading…") + "</div></div>";
    var svg = el.querySelector("svg"), label = el.querySelector(".alg-label"), line = el.querySelector(".alg");
    var cube = new KelsoCube.Cube(svg, { size: 64 });
    var stopped = false, timer = null;
    function round() {
      if (stopped) return;
      var a = K.randomAlg(), toks = KelsoCube.tokens(a.alg);
      cube.state = KelsoCube.applyAlg(KelsoCube.solved(), KelsoCube.invert(a.alg));
      cube.history = [];
      cube.draw();
      label.textContent = a.label;
      line.innerHTML = toks.map(function (t) { return "<span>" + K.esc(t) + "</span>"; }).join(" ");
      var spans = line.querySelectorAll("span");
      timer = setTimeout(function () {
        if (stopped) return;
        cube.play(a.alg, { total: 2400, record: false, onmove: function (i) {
          spans.forEach(function (s, j) { s.className = j < i ? "done" : j === i ? "on" : ""; });
        } });
        cube.onidleOnce(function () {
          spans.forEach(function (s) { s.className = "done"; });
          timer = setTimeout(round, 650);
        });
      }, 420);
    }
    round();
    return { stop: function () { stopped = true; clearTimeout(timer); cube.queue = []; } };
  };

  // ------------------------------------------------------------ search suggestions
  K.attachSuggest = function (input, opts) {
    opts = opts || {};
    var box = document.createElement("div");
    box.className = "suggest"; box.hidden = true;
    input.parentNode.appendChild(box);
    var timer = null, items = [], sel = -1, last = "";
    function render() {
      box.innerHTML = items.map(function (r, i) {
        return '<a href="/persons/' + r.wca_id + '" data-i="' + i + '" class="' + (i === sel ? "sel" : "") + '">' + (K.flag(r.iso2) || "<span></span>") +
          '<span><span class="nm">' + K.esc(r.name) + '</span> <span class="id">' + r.wca_id + "</span></span>" +
          '<span class="r">' + (r.overall != null ? Math.round(r.overall) : "–") + "</span></a>";
      }).join("");
      box.hidden = !items.length;
    }
    function query() {
      var q = input.value.trim();
      if (q === last) return; last = q;
      if (q.length < 2) { items = []; render(); return; }
      fetch("/api/search?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (rows) {
        if (input.value.trim() !== q) return;
        items = rows; sel = -1; render();
      }).catch(function () {});
    }
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(query, 140); });
    input.addEventListener("keydown", function (ev) {
      if (box.hidden) return;
      if (ev.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); render(); ev.preventDefault(); }
      else if (ev.key === "ArrowUp") { sel = Math.max(-1, sel - 1); render(); ev.preventDefault(); }
      else if (ev.key === "Enter" && sel >= 0) { ev.preventDefault(); choose(items[sel]); }
      else if (ev.key === "Escape") { box.hidden = true; }
    });
    box.addEventListener("click", function (ev) {
      var a = ev.target.closest("a"); if (!a) return;
      if (opts.onPick) { ev.preventDefault(); choose(items[+a.dataset.i]); }
    });
    document.addEventListener("click", function (ev) { if (!box.contains(ev.target) && ev.target !== input) box.hidden = true; });
    function choose(r) {
      if (opts.onPick) { opts.onPick(r); box.hidden = true; input.value = r.name; last = input.value; }
      else location.href = "/persons/" + r.wca_id;
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    initBrandCube();
    var q = document.querySelector(".top .search input");
    if (q) K.attachSuggest(q);
  });
})();
