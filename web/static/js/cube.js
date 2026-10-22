/* Kelso cube: a full 3x3x3 model (54 stickers) drawn in SVG, with animated turns on every axis.
 *
 * Moves use standard notation: R L U D F B, slices M E S, wide moves r l u d f b (or Rw…),
 * rotations x y z, with ' and 2. A turn rotates the stickers of its layers by 90° about the axis.
 *
 * Rendering: while a move animates, the cube is split along the move's axis into boxes of layers
 * that share the same angle (e.g. R: [L+M] static, [R] turning). Boxes along one axis are separated
 * by parallel planes, so drawing them back to front, each with back-face culling, is exact.
 *
 * Works in the browser (window.KelsoCube) and in Node (module.exports), where it also verifies the
 * algorithm library (scripts/check_algs.js) and emits the static logo.
 */
(function (root) {
  "use strict";
  var COLORS = { U: "#ffffff", D: "#ffd500", F: "#009b48", R: "#b71234", B: "#0046ad", L: "#ff5800" };
  var BODY = "#161a1f", INNER = "#2a3038";
  var FACES = { U: [0, 1, 0], D: [0, -1, 0], F: [0, 0, 1], B: [0, 0, -1], R: [1, 0, 0], L: [-1, 0, 0] };
  var AX = { x: 0, y: 1, z: 2 };

  // ---------------------------------------------------------------- state: 54 stickers {p: cubie, n: normal, c: colour}
  function solved() {
    var st = [];
    Object.keys(FACES).forEach(function (f) {
      var n = FACES[f], a = n[0] ? 0 : n[1] ? 1 : 2, u = (a + 1) % 3, v = (a + 2) % 3;
      for (var i = -1; i <= 1; i++) for (var j = -1; j <= 1; j++) {
        var p = [0, 0, 0]; p[a] = n[a]; p[u] = i; p[v] = j;
        st.push({ p: p, n: n.slice(), c: f });
      }
    });
    return st;
  }
  function clone(st) { return st.map(function (s) { return { p: s.p.slice(), n: s.n.slice(), c: s.c }; }); }

  // right-handed rotation of v about axis a by angle t
  function rot(v, a, t) {
    var c = Math.cos(t), s = Math.sin(t), x = v[0], y = v[1], z = v[2];
    if (a === 0) return [x, c * y - s * z, s * y + c * z];
    if (a === 1) return [c * x + s * z, y, -s * x + c * z];
    return [c * x - s * y, s * x + c * y, z];
  }
  function roundv(v) { return [Math.round(v[0]), Math.round(v[1]), Math.round(v[2])]; }

  // ---------------------------------------------------------------- notation
  // base move -> axis, layers turned, sign of the angle for one clockwise quarter turn
  var BASE = {
    R: ["x", [1], -1], L: ["x", [-1], 1], M: ["x", [0], 1],
    U: ["y", [1], -1], D: ["y", [-1], 1], E: ["y", [0], 1],
    F: ["z", [1], -1], B: ["z", [-1], 1], S: ["z", [0], -1],
    r: ["x", [0, 1], -1], l: ["x", [-1, 0], 1], u: ["y", [0, 1], -1],
    d: ["y", [-1, 0], 1], f: ["z", [0, 1], -1], b: ["z", [-1, 0], 1],
    x: ["x", [-1, 0, 1], -1], y: ["y", [-1, 0, 1], -1], z: ["z", [-1, 0, 1], -1]
  };
  function parse(tok) {
    var m = /^([RLUDFBMESrludfbxyz])(w?)(2?)('?)(2?)$/.exec(tok);
    if (!m) throw new Error("bad move " + tok);
    var key = m[2] ? m[1].toLowerCase() : m[1], b = BASE[key];
    var q = (m[3] || m[5]) ? 2 : 1, inv = !!m[4];
    return { tok: tok, axis: AX[b[0]], layers: b[1], q: q, angle: b[2] * (inv ? -1 : 1) * q * Math.PI / 2 };
  }
  function tokens(alg) { return alg.trim().split(/\s+/).filter(Boolean); }
  function invertTok(t) { return /2'?$/.test(t) ? t.replace("'", "") : /'$/.test(t) ? t.slice(0, -1) : t + "'"; }
  function invert(alg) { return tokens(alg).reverse().map(invertTok).join(" "); }

  function apply(st, move) {
    var m = typeof move === "string" ? parse(move) : move;
    return st.map(function (s) {
      if (m.layers.indexOf(s.p[m.axis]) < 0) return s;
      return { p: roundv(rot(s.p, m.axis, m.angle)), n: roundv(rot(s.n, m.axis, m.angle)), c: s.c };
    });
  }
  function applyAlg(st, alg) { tokens(alg).forEach(function (t) { st = apply(st, t); }); return st; }

  function key(s) { return s.p.join(",") + "|" + s.n.join(","); }
  function isSolved(st) {
    var centre = {};
    st.forEach(function (s) { if (Math.abs(s.p[0]) + Math.abs(s.p[1]) + Math.abs(s.p[2]) === 1) centre[s.n.join(",")] = s.c; });
    return st.every(function (s) { return centre[s.n.join(",")] === s.c; });
  }

  // ---------------------------------------------------------------- renderer
  function Renderer(opts) {
    opts = opts || {};
    this.yaw = opts.yaw != null ? opts.yaw : -Math.PI / 4 + 0.12;
    this.pitch = opts.pitch != null ? opts.pitch : 0.52;
    this.size = opts.size || 64;
    this.inset = opts.inset != null ? opts.inset : 0.13;
  }
  Renderer.prototype.cam = function (p) { return rot(rot(p, 1, this.yaw), 0, this.pitch); };

  // angles: per layer (-1, 0, 1) rotation about `axis` (index 0..2)
  Renderer.prototype.markup = function (st, axis, angles) {
    var self = this, out = [], S = this.size / 5.6, cx = this.size / 2, cy = this.size / 2;
    axis = axis == null ? 1 : axis; angles = angles || [0, 0, 0];
    function pt(p) { var q = self.cam(p); return (cx + q[0] * S).toFixed(2) + "," + (cy - q[1] * S).toFixed(2); }
    function poly(ps, fill, extra) { out.push('<polygon points="' + ps.map(pt).join(" ") + '" fill="' + fill + '"' + (extra || "") + "/>"); }
    // group contiguous layers with equal angle into boxes
    var groups = [], cur = null;
    [-1, 0, 1].forEach(function (L) {
      var t = angles[L + 1] || 0;
      if (cur && Math.abs(cur.t - t) < 1e-9) cur.hi = L; else { cur = { lo: L, hi: L, t: t }; groups.push(cur); }
    });
    var axisCam = this.cam(FACES[["R", "U", "F"][axis]]);
    groups.sort(function (g, h) { return (g.lo + g.hi) * axisCam[2] - (h.lo + h.hi) * axisCam[2]; });
    groups.forEach(function (g) {
      var R = function (v) { return rot(v, axis, g.t); };
      for (var d = 0; d < 3; d++) for (var sgn = -1; sgn <= 1; sgn += 2) {
        var n = [0, 0, 0]; n[d] = sgn;
        var nr = R(n);
        if (self.cam(nr)[2] <= 1e-6) continue;                     // back face
        var outer = d !== axis || (sgn > 0 ? g.hi === 1 : g.lo === -1);
        var u = (d + 1) % 3, v = (d + 2) % 3;
        var lo = [-1.5, -1.5, -1.5], hi = [1.5, 1.5, 1.5];
        lo[axis] = g.lo - 0.5; hi[axis] = g.hi + 0.5;
        var c0 = [0, 0, 0]; c0[d] = sgn > 0 ? hi[d] : lo[d];
        var corners = [[lo[u], lo[v]], [hi[u], lo[v]], [hi[u], hi[v]], [lo[u], hi[v]]].map(function (uv) {
          var p = c0.slice(); p[u] = uv[0]; p[v] = uv[1]; return R(p);
        });
        poly(corners, outer ? BODY : INNER);
        if (!outer) continue;
        var shade = Math.max(0, Math.min(0.34, 0.15 - 0.2 * (nr[0] * -0.8 + nr[1] * 0.9 + nr[2] * 0.5)));
        st.forEach(function (s) {
          if (s.n[d] !== sgn || s.p[axis] < g.lo || s.p[axis] > g.hi) return;
          var h = 0.5 - self.inset / 2, ctr = [s.p[0] + 0.5 * s.n[0], s.p[1] + 0.5 * s.n[1], s.p[2] + 0.5 * s.n[2]];
          var q = [[-h, -h], [h, -h], [h, h], [-h, h]].map(function (uv) {
            var p = ctr.slice(); p[u] += uv[0]; p[v] += uv[1]; return R(p);
          });
          poly(q, COLORS[s.c]);
          if (shade > 0.01) poly(q, "#000", ' fill-opacity="' + shade.toFixed(2) + '"');
        });
      }
    });
    return out.join("");
  };
  Renderer.prototype.svg = function (st, axis, angles, attrs) {
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + this.size + " " + this.size + '" ' + (attrs || "") + ">" +
      this.markup(st, axis, angles) + "</svg>";
  };

  // ---------------------------------------------------------------- animated cube bound to an <svg>
  // rest: an optional resting twist {axis, layer, angle} (the logo's turned top layer); it is
  // straightened before turns on other axes and restored when the cube is idle.
  function Cube(host, opts) {
    opts = opts || {};
    this.host = host;
    this.r = new Renderer({ size: opts.size || 64 });
    this.state = opts.state || solved();
    this.history = (opts.history || []).slice();
    this.rest = opts.rest || null;
    this.restNow = this.rest ? this.rest.angle : 0;
    this.queue = [];
    this.busy = false;
    this.ms = opts.ms || 220;
    this.reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.anim = null;
    this.draw();
  }
  Cube.prototype.draw = function () {
    var a = this.anim, axis = a ? a.axis : (this.rest ? this.rest.axis : 1), ang = [0, 0, 0];
    if (this.rest && axis === this.rest.axis) ang[this.rest.layer + 1] = this.restNow;
    if (a) a.layers.forEach(function (L) { ang[L + 1] += a.t; });
    this.host.innerHTML = this.r.markup(this.state, axis, ang);
  };
  Cube.prototype._tween = function (ms, step, done) {
    if (this.reduced || ms <= 0) { step(1); done(); return; }
    var t0 = null;
    function frame(t) {
      if (t0 === null) t0 = t;
      var x = Math.min(1, (t - t0) / ms);
      step(x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
      if (x < 1) requestAnimationFrame(frame); else done();
    }
    requestAnimationFrame(frame);
  };
  // queue one move; opts: {ms, record, onstart}
  Cube.prototype.turn = function (tok, opts) {
    this.queue.push({ tok: tok, o: opts || {} });
    if (!this.busy) this._next();
  };
  Cube.prototype._next = function () {
    var self = this, job = this.queue.shift();
    if (!job) {
      this.busy = false;
      if (this.rest && this.restNow !== this.rest.angle) {          // restore the resting twist
        this.busy = true;
        this._tween(160, function (e) { self.restNow = self.rest.angle * e; self.draw(); }, function () { self.busy = false; if (!self.queue.length && self.onidle) self.onidle(); else self._next(); });
        return;
      }
      if (this.onidle) this.onidle();
      return;
    }
    this.busy = true;
    var m = parse(job.tok);
    if (this.rest && this.restNow !== 0 && m.axis !== this.rest.axis) {  // straighten the twist first
      this.queue.unshift(job);
      var from = this.restNow;
      this._tween(110, function (e) { self.restNow = from * (1 - e); self.draw(); }, function () { self.restNow = 0; self._next(); });
      return;
    }
    if (job.o.onstart) job.o.onstart();
    var ms = (job.o.ms || this.ms) * (m.q === 2 ? 1.45 : 1);
    this.anim = { axis: m.axis, layers: m.layers, t: 0 };
    this._tween(ms, function (e) { self.anim.t = m.angle * e; self.draw(); }, function () {
      self.anim = null;
      self.state = apply(self.state, m);
      if (job.o.record !== false) self.history.push(job.tok);
      self.draw();
      if (self.onturn) self.onturn(job.tok);
      self._next();
    });
  };
  // play an algorithm; longer algorithms play faster (about `total` ms, 60–240 ms per move)
  Cube.prototype.play = function (alg, opts) {
    opts = opts || {};
    var toks = tokens(alg), weight = toks.reduce(function (s, t) { return s + (/2/.test(t) ? 1.45 : 1); }, 0);
    var ms = Math.max(opts.min || 60, Math.min(opts.max || 240, (opts.total || 2600) / weight));
    var self = this;
    toks.forEach(function (t, i) {
      self.turn(t, { ms: ms, record: opts.record, onstart: opts.onmove ? function () { opts.onmove(i); } : null });
    });
  };
  // undo the recorded history quickly (the logo returning home)
  Cube.prototype.solve = function (total) {
    var self = this;
    if (this.busy) { this.onidleOnce(function () { self.solve(total); }); return; }
    var undo = invert(this.history.join(" "));
    this.history = [];
    if (undo) this.play(undo, { total: total || 1600, min: 22, max: 160, record: false });
  };
  Cube.prototype.onidleOnce = function (fn) {
    var self = this, prev = this.onidle;
    this.onidle = function () { self.onidle = prev; fn(); if (prev) prev(); };
  };
  Cube.prototype.isSolved = function () { return isSolved(this.state); };

  var api = { Renderer: Renderer, Cube: Cube, solved: solved, clone: clone, apply: apply, applyAlg: applyAlg,
              parse: parse, tokens: tokens, invert: invert, isSolved: isSolved, key: key, COLORS: COLORS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.KelsoCube = api;
})(this);
