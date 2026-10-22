/* Rating history: one series at a time (overall or one event), drawn as a step line because a
 * rating only changes at competitions. Crosshair + tooltip snap to the nearest change. */
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("chart-data").textContent);
  var host = document.getElementById("chart");
  if (!host) return;
  var current = "overall";
  var NS = "http://www.w3.org/2000/svg";

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceStep(span, n) {
    var raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  }
  function t(d) { return new Date(d + "T00:00:00Z").getTime(); }

  function draw() {
    var pts = (data.series[current] || []).map(function (p) { return { x: t(p[0]), d: p[0], y: p[1], c: p[2] }; });
    host.innerHTML = "";
    if (!pts.length) { host.innerHTML = '<p class="muted">No history.</p>'; return; }
    var W = host.clientWidth, H = host.clientHeight, m = { l: 44, r: 12, t: 12, b: 26 };
    var now = Date.now();
    var x0 = pts[0].x - 1000 * 3600 * 24 * 30, x1 = Math.max(now, pts[pts.length - 1].x);
    var ys = pts.map(function (p) { return p.y; });
    var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
    var pad = Math.max(40, (yhi - ylo) * 0.12);
    ylo = Math.max(0, ylo - pad); yhi = yhi + pad;
    var step = niceStep(yhi - ylo, 4);
    ylo = Math.floor(ylo / step) * step; yhi = Math.ceil(yhi / step) * step;
    function X(v) { return m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (v - ylo) / (yhi - ylo)) * (H - m.t - m.b); }

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Rating history chart" }, host);
    var g = el("g", { class: "grid" }, svg), ax = el("g", { class: "axis" }, svg);
    for (var v = ylo; v <= yhi + 1e-9; v += step) {
      el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, g);
      el("text", { x: m.l - 8, y: Y(v) + 4, "text-anchor": "end" }, ax).textContent = Math.round(v);
    }
    var y0 = new Date(x0).getUTCFullYear() + 1, y1 = new Date(x1).getUTCFullYear();
    var every = Math.max(1, Math.ceil((y1 - y0 + 1) / Math.max(2, Math.floor((W - 60) / 70))));
    for (var yr = y0; yr <= y1; yr += every) {
      var xx = X(Date.UTC(yr, 0, 1));
      el("text", { x: xx, y: H - 6, "text-anchor": "middle" }, ax).textContent = yr;
    }
    // step path: hold each value until the next change, then to today
    var d = "M" + X(pts[0].x) + "," + Y(pts[0].y);
    for (var i = 1; i < pts.length; i++) d += "H" + X(pts[i].x) + "V" + Y(pts[i].y);
    d += "H" + X(x1);
    el("path", { class: "area", d: d + "V" + Y(ylo) + "H" + X(pts[0].x) + "Z" }, svg);
    el("path", { class: "line", d: d }, svg);
    var last = pts[pts.length - 1];
    el("circle", { class: "dot", cx: X(last.x), cy: Y(last.y), r: 4 }, svg);

    var cross = el("line", { class: "cross", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
    var hot = el("circle", { class: "dot", r: 5, visibility: "hidden" }, svg);
    var tip = document.createElement("div");
    tip.className = "tip"; tip.hidden = true; host.appendChild(tip);
    var hit = el("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" }, svg);
    function move(ev) {
      var r = svg.getBoundingClientRect(), mx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
      var best = 0, bd = Infinity;
      pts.forEach(function (p, i) { var dd = Math.abs(X(p.x) - mx); if (dd < bd) { bd = dd; best = i; } });
      var p = pts[best], prev = pts[best - 1];
      cross.setAttribute("x1", X(p.x)); cross.setAttribute("x2", X(p.x)); cross.setAttribute("visibility", "visible");
      hot.setAttribute("cx", X(p.x)); hot.setAttribute("cy", Y(p.y)); hot.setAttribute("visibility", "visible");
      var diff = prev ? '<span class="up"> ' + Kelso.fmtDelta(p.y - prev.y) + "</span>" : ' <span class="muted">first</span>';
      tip.innerHTML = '<div class="muted">' + p.d + "</div><div>" + Kelso.esc(data.names[p.c] || p.c) + "</div><div><b>" + Math.round(p.y) + "</b>" + diff + "</div>";
      tip.hidden = false;
      var tx = X(p.x) + 12, tw = tip.offsetWidth;
      if (tx + tw > W) tx = X(p.x) - tw - 12;
      tip.style.left = Math.max(0, tx) + "px";
      tip.style.top = Math.max(0, Y(p.y) - 70) + "px";
    }
    function leave() { tip.hidden = true; cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden"); }
    hit.addEventListener("mousemove", move);
    hit.addEventListener("touchmove", move, { passive: true });
    hit.addEventListener("mouseleave", leave);
    hit.addEventListener("click", function () {
      var id = tip.hidden ? null : pts.reduce(function (a, p) { return Math.abs(X(p.x) - parseFloat(cross.getAttribute("x1"))) < 1 ? p.c : a; }, null);
      if (id) location.href = "/competitions/" + id;
    });
  }

  document.querySelectorAll(".series-pick button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".series-pick button").forEach(function (x) { x.classList.toggle("on", x === b); });
      current = b.dataset.s;
      document.getElementById("chart-title").textContent = current === "overall" ? "Rating history" : Kelso.SHORT[current] + " rating history";
      draw();
    });
  });
  draw();
  if (window.ResizeObserver) new ResizeObserver(function () { draw(); }).observe(host);
})();
