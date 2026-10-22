/* Hypothetical rating: parse results, rate them through the frozen conversion tables
 * (piecewise linear in log result, exactly as kelso.rating.ConversionTables.rate), aggregate by
 * log-sum-exp with K = 400. The world rank comes from /api/rank (binary search on the server). */
(function () {
  "use strict";
  var tables = null, current = null, rankTimer = null;
  var inputs = Array.prototype.slice.call(document.querySelectorAll("#calc-grid input"));
  var SINGLE = { "333bf": 1, "444bf": 1, "555bf": 1, "333mbf": 1 };

  function parseTime(s) {               // -> centiseconds
    s = s.trim().replace(",", ".");
    if (!s) return null;
    var m = s.match(/^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d*)?)$/);
    if (!m) return NaN;
    var h = 0, mi = 0;
    if (m[2] != null) { h = +m[1]; mi = +m[2]; } else if (m[1] != null) { mi = +m[1]; }
    return Math.round((h * 3600 + mi * 60 + parseFloat(m[3])) * 100);
  }
  // value that enters the rating (same as kelso.rating.result_value) and the WCA raw encoding
  function parse(e, s) {
    s = s.trim();
    if (!s) return null;
    if (e === "333mbf") {
      var m = s.match(/^(\d+)\s*\/\s*(\d+)\s+(.+)$/);
      if (!m) return NaN;
      var solved = +m[1], att = +m[2], t = parseTime(m[3]);
      if (!(att >= solved) || att < 2 || !(t > 0)) return NaN;
      var missed = att - solved, pts = solved - missed, sec = Math.round(t / 100);
      if (pts < 0) return NaN;
      var v = 1 / Math.max(pts + (3600 - Math.min(sec, 3600)) / 3600, 0.25);
      return { v: v, raw: (99 - pts) * 1e7 + sec * 100 + missed };
    }
    if (e === "333fm") {
      var f = parseFloat(s.replace(",", "."));
      if (!(f > 0) || /[^\d.,]/.test(s)) return NaN;
      return { v: Math.round(f * 100), raw: Math.round(f * 100) };
    }
    var cs = parseTime(s);
    return cs > 0 ? { v: cs, raw: cs } : NaN;
  }
  function rate(e, v) {
    var T = tables.events[e], x = Math.log(v), xs = T.x, rs = T.r, n = xs.length;
    if (x <= xs[0]) return rs[0];
    if (x >= xs[n - 1]) return rs[n - 1];
    var lo = 0, hi = n - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (xs[mid] <= x) lo = mid; else hi = mid; }
    return rs[lo] + (rs[hi] - rs[lo]) * (x - xs[lo]) / (xs[hi] - xs[lo]);
  }
  function lse(rs) {
    var m = Math.max.apply(null, rs);
    return m + 400 * Math.log10(rs.reduce(function (s, r) { return s + Math.pow(10, (r - m) / 400); }, 0));
  }

  function update() {
    if (!tables) return;
    var rs = [], best = null, hash = [];
    inputs.forEach(function (inp) {
      var e = inp.dataset.e, p = parse(e, inp.value), out = document.getElementById("r-" + e);
      inp.classList.toggle("bad", p !== null && !(p && p.v > 0));
      if (p && p.v > 0) {
        var r = rate(e, p.v);
        rs.push(r); out.textContent = Math.round(r);
        if (!best || r > best.r) best = { e: e, r: r };
        hash.push(e + "=" + encodeURIComponent(inp.value.trim()));
      } else out.textContent = "";
    });
    history.replaceState(null, "", hash.length ? "#" + hash.join("&") : location.pathname);
    var $ = function (id) { return document.getElementById(id); };
    $("out-n").textContent = rs.length;
    if (!rs.length) {
      ["out-overall", "out-rank", "out-top", "out-best", "out-breadth"].forEach(function (id) { $(id).textContent = "–"; });
      return;
    }
    var O = lse(rs);
    $("out-overall").textContent = Math.round(O);
    $("out-best").innerHTML = Kelso.icon(best.e) + " " + Math.round(best.r);
    $("out-breadth").textContent = "+" + Math.round(O - best.r);
    if (current && current.overall != null) {
      $("out-vs-k").hidden = $("out-vs").hidden = false;
      var d = O - current.overall;
      $("out-vs").innerHTML = '<span class="' + (d >= 0.5 ? "up" : d <= -0.5 ? "down" : "muted") + '">' + Kelso.fmtDelta(d) + "</span>";
    }
    clearTimeout(rankTimer);
    rankTimer = setTimeout(function () {
      fetch("/api/rank?r=" + O.toFixed(3)).then(function (r) { return r.json(); }).then(function (j) {
        $("out-rank").textContent = j.rank.toLocaleString() + " of " + j.total.toLocaleString();
        var p = j.top_share * 100;
        $("out-top").textContent = "top " + (p < 1 ? p.toFixed(2) : p < 10 ? p.toFixed(1) : p.toFixed(0)) + "%";
      });
    }, 150);
  }

  function fill(map) {
    inputs.forEach(function (inp) { inp.value = map[inp.dataset.e] || ""; });
    update();
  }

  fetch("/api/tables").then(function (r) { return r.json(); }).then(function (t) {
    tables = t;
    if (location.hash.length > 1) {
      var map = {};
      location.hash.slice(1).split("&").forEach(function (kv) { var p = kv.split("="); map[p[0]] = decodeURIComponent(p[1] || ""); });
      fill(map);
    } else update();
  });
  inputs.forEach(function (inp) { inp.addEventListener("input", update); });
  document.getElementById("clear").addEventListener("click", function () { current = null; document.getElementById("prefill-note").textContent = ""; document.getElementById("out-vs-k").hidden = document.getElementById("out-vs").hidden = true; fill({}); });
  document.getElementById("share").addEventListener("click", function () {
    if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(function () { document.getElementById("prefill-note").textContent = "Link copied."; });
  });
  Kelso.attachSuggest(document.getElementById("prefill"), {
    onPick: function (row) {
      fetch("/api/persons/" + row.wca_id).then(function (r) { return r.json(); }).then(function (p) {
        current = p;
        var map = {};
        Object.keys(p.events).forEach(function (e) { map[e] = Kelso.fmtResult(e, p.events[e].raw); });
        fill(map);
        document.getElementById("prefill-note").textContent = "Personal bests of " + p.name + " — change any result to compare.";
      });
    }
  });
})();
