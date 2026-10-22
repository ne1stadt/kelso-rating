/* Algorithms played by the cube. Every entry is verified by scripts/check_algs.js with the cube
 * model: OLL keeps the first two layers, PLL also keeps the top colour on top, last-slot (LS)
 * algorithms keep the cross and the other three F2L pairs. LS entries are labelled ZBLS when
 * they also orient the last-layer edges (checked, not assumed), otherwise F2L. */
(function (root) {
  "use strict";
  var PLL = [
    ["Aa", "x R' U R' D2 R U' R' D2 R2 x'"],
    ["Ab", "x R2 D2 R U R' D2 R U' R x'"],
    ["E", "x' R U' R' D R U R' D' R U R' D R U' R' D' x"],
    ["F", "R' U' F' R U R' U' R' F R2 U' R' U' R U R' U R"],
    ["Ga", "R2 U R' U R' U' R U' R2 U' D R' U R D'"],
    ["Gb", "R' U' R U D' R2 U R' U R U' R U' R2 D"],
    ["Gc", "R2 U' R U' R U R' U R2 U D' R U' R' D"],
    ["Gd", "R U R' U' D R2 U' R U' R' U R' U R2 D'"],
    ["H", "M2 U M2 U2 M2 U M2"],
    ["Ja", "x R2 F R F' R U2 r' U r U2 x'"],
    ["Jb", "R U R' F' R U R' U' R' F R2 U' R'"],
    ["Na", "R U R' U R U R' F' R U R' U' R' F R2 U' R' U2 R U' R'"],
    ["Nb", "R' U R U' R' F' U' F R U R' F R' F' R U' R"],
    ["Ra", "R U' R' U' R U R D R' U' R D' R' U2 R'"],
    ["Rb", "R2 F R U R U' R' F' R U2 R' U2 R"],
    ["T", "R U R' U' R' F R2 U' R' U' R U R' F'"],
    ["Ua", "M2 U M U2 M' U M2"],
    ["Ub", "M2 U' M U2 M' U' M2"],
    ["V", "R' U R' U' R D' R' D R' U D' R2 U' R2 D R2"],
    ["Y", "F R U' R' U' R U R' F' R U R' U' R' F R F'"],
    ["Z", "M' U M2 U M2 U M' U2 M2"]
  ];
  var OLL = [
    "R U2 R2 F R F' U2 R' F R F'", "F R U R' U' F' f R U R' U' f'", "f R U R' U' f' U' F R U R' U' F'",
    "f R U R' U' f' U F R U R' U' F'", "r' U2 R U R' U r", "r U2 R' U' R U' r'", "r U R' U R U2 r'",
    "l' U' L U' L' U2 l", "R U R' U' R' F R2 U R' U' F'", "R U R' U R' F R F' R U2 R'",
    "r U R' U R' F R F' R U2 r'", "F R U R' U' F' U F R U R' U' F'", "F U R U' R2 F' R U R U' R'",
    "R' F R U R' F' R F U' F'", "r' U' r R' U' R U r' U r", "r U r' R U R' U' r U' r'",
    "F R' F' R2 r' U R U' R' U' M'", "r U R' U R U2 r2 U' R U' R' U2 r", "r' R U R U R' U' M' R' F R F'",
    "r U R' U' M2 U R U' R' U' M'", "R U2 R' U' R U R' U' R U' R'", "R U2 R2 U' R2 U' R2 U2 R",
    "R2 D' R U2 R' D R U2 R", "r U R' U' r' F R F'", "F' r U R' U' r' F R", "R U2 R' U' R U' R'",
    "R U R' U R U2 R'", "r U R' U' M U R U' R'", "R U R' U' R U' R' F' U' F R U R'",
    "F R' F R2 U' R' U' R U R' F2", "R' U' F U R U' R' F' R", "L U F' U' L' U L F L'", "R U R' U' R' F R F'",
    "R U R2 U' R' F R U R U' F'", "R U2 R2 F R F' R U2 R'", "L' U' L U' L' U L U L F' L' F", "F R' F' R U R U' R'",
    "R U R' U R U' R' U' R' F R F'", "L F' L' U' L U F U' L'", "R' F R U R' U' F' U R",
    "R U R' U R U2 R' F R U R' U' F'", "R' U' R U' R' U2 R F R U R' U' F'", "F' U' L' U L F", "F U R U' R' F'",
    "F R U R' U' F'", "R' U' R' F R F' U R", "R' U' R' F R F' R' F R F' U R", "F R U R' U' R U R' U' F'",
    "r U' r2 U r2 U r2 U' r", "r' U r2 U' r2 U' r2 U r'", "F U R U' R' U R U' R' F'", "R U R' U R U' B U' B' R'",
    "l' U2 L U L' U' L U L' U l", "r U2 R' U' R U R' U' R U' r'", "R' F R U R U' R2 F' R2 U' R' U R U R'",
    "r' U' r U' R' U R U' R' U R r' U r", "R U R' U' M' U R U' r'"
  ];
  var LS = [
    "U R U' R'", "F' U' F", "R U R'", "U' R U R' U2 R U' R'", "U' R U2 R' U2 R U' R'",
    "U' R U' R' U F' U' F", "U' R U R' U R U R'", "U' R U2 R' U F' U' F", "R U' R' U R U' R' U2 R U' R'",
    "U F' U F U' F' U' F", "U' R U' R' U R U R'", "R U' R' U2 F' U' F", "R U2 R' U' R U R'",
    "F' U2 F U F' U' F", "U R U2 R' U R U' R'", "U2 R U R' U R U' R'", "U2 F' U' F U' F' U F",
    "U R U' R' U' R U' R' U R U' R'", "R U' R' U R U' R'", "F' U F U' F' U F", "R U R' U' R U R'",
    "R U R' U' R U R' U' R U R'", "U' R U' R' U2 R U' R'", "U R U R' U2 R U R'", "U2 R U' R' U' F' U' F",
    "U F' U' F U' R U R'", "R U' R' U' R U R' U2 R U' R'", "R U' R' U R U2 R' U R U' R'",
    "R U' R' U' R U' R' U F' U' F",
    "R' F R F' R U R'", "R U R' F R' F' R", "U R U' R' F R' F' R", "R U2 R' F R' F' R",
    "R U R' U' F R' F' R", "U' R U R' F R' F' R", "R' F R F' U R U' R'", "F R' F' R U R U' R'",
    "R U' R' F R' F' R", "U2 R' F R F' R U R'", "R U2 R' U' F' U' F", "R' F R F' R U2 R'",
    "U R U R' U' F R' F' R", "F R' F' R U R U2 R'", "R' F' R U R U' R' F", "U' R' F R F' R U R'"
  ];
  var list = [];
  PLL.forEach(function (p) { list.push({ set: "PLL", name: p[0], alg: p[1] }); });
  OLL.forEach(function (a) { list.push({ set: "OLL", name: "", alg: a }); });
  LS.forEach(function (a) { list.push({ set: "LS", name: "", alg: a }); });
  var api = { list: list };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.KelsoAlgs = api;
})(this);
