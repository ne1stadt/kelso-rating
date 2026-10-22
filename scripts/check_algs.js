// Verifies web/static/js/algs.js with the cube model in web/static/js/cube.js.
//   node scripts/check_algs.js            report
//   node scripts/check_algs.js --write    also write web/static/js/algs-verified.js (what the site plays)
// OLL: first two layers preserved. PLL: also every top sticker stays the top colour, and the
// permutation structure (after the best AUF) must match the case name. LS: cross + three slots
// preserved; labelled ZBLS if the case it solves has a misoriented last-layer edge.
const path = require("path");
const fs = require("fs");
const K = require(path.join(__dirname, "../web/static/js/cube.js"));
const A = require(path.join(__dirname, "../web/static/js/algs.js"));

const SOLVED = K.solved();
const colourAt = (st) => Object.fromEntries(st.map((s) => [K.key(s), s.c]));
const ref = colourAt(SOLVED);
const isCentre = (p) => Math.abs(p[0]) + Math.abs(p[1]) + Math.abs(p[2]) === 1;

function preserved(st, keep) {
  const now = colourAt(st);
  return SOLVED.every((s) => !keep(s.p) || now[K.key(s)] === s.c);
}
const F2L = (p) => p[1] <= 0 || (isCentre(p) && p[1] === 1);
const SLOTS = (p) => isCentre(p) || (p[1] <= 0 && !(p[0] === 1 && p[2] === 1));

// pieces of the U layer: position -> sorted colours of the piece that sits there
function uPieces(st) {
  const m = {};
  st.forEach((s) => { if (s.p[1] === 1 && !isCentre(s.p)) (m[s.p.join(",")] = m[s.p.join(",")] || []).push(s.c); });
  for (const k in m) m[k] = m[k].sort().join("");
  return m;
}
const HOME = uPieces(SOLVED);
function structure(st) {
  const now = uPieces(st), moved = { c: [], e: [] };
  for (const pos in now) if (now[pos] !== HOME[pos]) {
    const p = pos.split(",").map(Number);
    (p[0] && p[2] ? moved.c : moved.e).push(p);
  }
  const kind = (arr, isCorner) => {
    if (!arr.length) return "0";
    if (arr.length === 3) return "3cyc";
    if (arr.length === 2) {
      const [a, b] = arr, opposite = a[0] === -b[0] && a[2] === -b[2];
      return isCorner ? (opposite ? "diag" : "adj") : (opposite ? "opp" : "adj");
    }
    return "4";
  };
  return { c: kind(moved.c, true), e: kind(moved.e, false), n: moved.c.length + moved.e.length };
}
// the structure is only defined up to AUF: collect it for all four
function aufStructures(st) {
  return ["", "U", "U2", "U'"].map((auf) => { const s = structure(auf ? K.applyAlg(st, auf) : st); return s.c + "/" + s.e; });
}
const EXPECT = { Ua: "0/3cyc", Ub: "0/3cyc", H: "0/4", Z: "0/4", Aa: "3cyc/0", Ab: "3cyc/0", E: "4/0",
  T: "adj/opp", F: "adj/opp", Ja: "adj/adj", Jb: "adj/adj", Ra: "adj/adj", Rb: "adj/adj",
  V: "diag/adj", Y: "diag/adj", Na: "diag/opp", Nb: "diag/opp", Ga: "3cyc/3cyc", Gb: "3cyc/3cyc", Gc: "3cyc/3cyc", Gd: "3cyc/3cyc" };

function edgesOriented(st) {   // every U-coloured edge sticker faces up
  return st.every((s) => s.c !== "U" || isCentre(s.p) || (s.p.filter((x) => x).length !== 2) || s.n[1] === 1);
}

const ok = [], bad = [];
for (const a of A.list) {
  let st;
  try { st = K.applyAlg(SOLVED, a.alg); } catch (e) { bad.push([a, e.message]); continue; }
  if (K.isSolved(st)) { bad.push([a, "does nothing"]); continue; }
  if (a.set === "OLL" && !preserved(st, F2L)) { bad.push([a, "breaks F2L"]); continue; }
  if (a.set === "PLL") {
    if (!preserved(st, F2L)) { bad.push([a, "breaks F2L"]); continue; }
    if (!st.every((s) => s.n[1] !== 1 || s.c === "U")) { bad.push([a, "changes orientation"]); continue; }
    const got = aufStructures(st);
    if (EXPECT[a.name] && !got.includes(EXPECT[a.name])) { bad.push([a, `structures ${got}, ${a.name} expects ${EXPECT[a.name]}`]); continue; }
  }
  if (a.set === "LS") {
    if (!preserved(st, SLOTS)) { bad.push([a, "breaks cross or another slot"]); continue; }
    const kase = K.applyAlg(SOLVED, K.invert(a.alg));
    a.set = edgesOriented(kase) ? "F2L" : "ZBLS";
  }
  if (a.set === "OLL" && edgesOriented(K.applyAlg(SOLVED, K.invert(a.alg)))) a.name = "corners";
  ok.push(a);
}
// PLL names: every case distinct, and independently remembered algorithms solve the same named case
const AUF = ["", "U", "U2", "U'"], YR = ["", "y", "y2", "y'"];
function sameCase(a1, a2) {
  const kase = K.applyAlg(SOLVED, K.invert(a1));
  for (const r of YR) for (const p of AUF) for (const q of AUF)
    if (K.isSolved(K.applyAlg(kase, [r, p, a2, q, r ? K.invert(r) : ""].join(" ")))) return true;
  return false;
}
const ALT = {
  Ua: "R U' R U R U R U' R' U' R2", Ub: "R2 U R U R' U' R' U' R' U R'", H: "R2 U2 R U2 R2 U2 R2 U2 R U2 R2",
  Z: "R' U' R U' R U R U' R' U R U R2 U' R'", Aa: "R' F R' B2 R F' R' B2 R2", Ab: "R B' R F2 R' B R F2 R2",
  Ja: "L' U' L F L' U' L U L F' L2 U L", Jb: "R U2 R' U' R U2 L' U R' U' L", Ra: "R U R' F' R U2 R' U2 R' F R U R U2 R'",
  Rb: "R' U2 R U2 R' F R U R' U' R' F' R2", E: "R2 U R' U' y R U R' U' R U R' U' R U R' y' R U' R2",
  Y: "F R U' R' U' R U R' F' R U R' U' R' F R F'", F: "R' U R U' R2 F' U' F U R F R' F' R2",
};
const plls = ok.filter((a) => a.set === "PLL");
plls.forEach((a, i) => plls.slice(i + 1).forEach((b) => { if (sameCase(a.alg, b.alg)) bad.push([b, `same case as ${a.name}`]); }));
for (const [n, alt] of Object.entries(ALT)) {
  const mine = plls.find((a) => a.name === n);
  if (mine && !sameCase(mine.alg, alt)) bad.push([mine, `does not solve the same case as the reference ${n} "${alt}"`]);
}

const by = (s) => ok.filter((a) => a.set === s).length;
console.log(`verified ${ok.length}/${A.list.length}: PLL ${by("PLL")}, OLL ${by("OLL")}, ZBLS ${by("ZBLS")}, F2L ${by("F2L")}`);
bad.forEach(([a, why]) => console.log(`  FAIL ${a.set} ${a.name || ""} "${a.alg}": ${why}`));
if (process.argv.includes("--write")) {
  const out = path.join(__dirname, "../web/static/js/algs-verified.js");
  const rows = ok.map((a) => [a.set, a.name === "corners" ? "OCLL" : a.name, a.alg]);
  fs.writeFileSync(out, "/* generated by scripts/check_algs.js --write from algs.js; every algorithm verified */\n" +
    "window.KelsoAlgs = " + JSON.stringify(rows) + ";\n");
  console.log("wrote", out);
}
process.exitCode = bad.length ? 1 : 0;
