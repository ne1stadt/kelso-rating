# Site design

## Principles

1. **It is a rating first.** The home page is the ranking table, rendered on the server. It is fully usable without JavaScript and is about 21 KB gzipped.
2. **WCA-familiar, not a copy.** The site uses the same event icons (the `cubing-icons` font the WCA site uses), the WCA-style row of event icons for picking an event, clean tables, flags and tabular numbers. It has its own identity: the cube logo and a calm blue accent.
3. **Credible.** Numbers come with their meaning: the rating unit, percentiles, breadth credit, each event's weight in the overall, and "estimated" labels for live data. The About page keeps the math.
4. **Light and dark.** All colours are CSS tokens. Dark mode follows the OS (`prefers-color-scheme`), with a `data-theme` hook for a future toggle.

## Logo: the twisted cube

A 3x3 cube drawn in isometric view with its **top layer turned about 22°**. It shows the moment of a turn, which is what cubing is about, and reads as a cube even at 16 px (favicon). It sits next to the lowercase wordmark **kelso** with a small "rating" caption. The cube uses the standard colour scheme (white top, green front, red right), and side faces are shaded by a light from the upper left.

The logo is not an image but the output of `static/js/cube.js`, a small SVG renderer over a full 3x3 model (54 stickers) that animates turns on every axis. The same code runs in Node to produce the static `img/logo.svg` (favicon and first paint) and in the browser to animate.

## Interactive elements: real algorithms

The cube doesn't turn at random: it plays real speedcubing algorithms, **OLL, PLL and last-slot (ZBLS / F2L)**, from `static/js/algs.js` (123 algorithms).

| Where | Behaviour |
| --- | --- |
| **Header logo** | Hovering plays a random algorithm; the link's tooltip names it (`PLL · T: R U R' U' …`). The cube **remembers its moves across pages** (sessionStorage). Every navigation plays another algorithm as the new page appears, so browsing slowly scrambles the last layer. Clicking the logo (going home) **rewinds the whole history** in about 1.4 s, and very long histories rewind on their own. The signature twisted top layer straightens before turns on other axes and returns when the cube is idle. |
| **Loading** | Anything that waits on the WCA (live competition lists, live estimates) shows a larger cube that sets up the case of a random algorithm and then solves it, with the set and case name (`PLL · Aa`, `OLL · OCLL`, `ZBLS`) and the notation underneath. The current move is highlighted. Then the next case. |
| **Speed** | Each algorithm takes about the same time (~1.5 s in the header, ~2.4 s in the loader), so longer algorithms play faster: 60–240 ms per move, double turns 1.45× a quarter turn. |
| **Navigation underline** | The active section has an accent bar under it. |
| **Error page** | The logo cube, as a 404 illustration. |

All animation respects `prefers-reduced-motion`: turns are then applied instantly.

**Notation supported:** R L U D F B, slices M E S, wide moves (r or Rw, …), rotations x y z, with `'` and `2`.

**Rendering:** while a move animates, the cube is split along the move's axis into boxes of layers that share an angle (for R: the static L+M box and the turning R box). Boxes along one axis are separated by parallel planes, so drawing them back to front with back-face culling is exact, with no 3D library.

**Every algorithm is verified** by `node scripts/check_algs.js --write` against the model, which generates `algs-verified.js` (the file the site loads):

* OLL must preserve the first two layers; PLL must also keep every top sticker on top.
* PLL names are checked three ways: the permutation structure after AUF must match the name; all 21 cases must be distinct up to AUF and y-rotation; and 14 names are confirmed by a second, independent algorithm that solves the same named case (this distinguishes a/b pairs).
* Last-slot algorithms must preserve the cross and the other three F2L pairs. They are labelled **ZBLS** only if the case they solve has a misoriented last-layer edge (40 of 45), otherwise F2L. OLL cases whose edges are already oriented are labelled OCLL (exactly 7, as expected).

## Pages and use cases

| Use case (`use-cases.md`) | Page | Notes |
| --- | --- | --- |
| Review Kelso rankings | `/` | 100 per page; region filter (world, continent, country); event picker switches to the event-rating ranking. Each row shows rating, **event icons faded by that event's share of the competitor's summed odds** (where the rating comes from), best event and breadth credit. |
| Navigate to user detailed view | `/persons/{wca_id}` | Rating, world/continent/country ranks, percentile, best event + breadth decomposition, rating-history chart, events table (PB, event rating, world and national event rank, weight in overall, competition where set), and the competition list with rating before/after. |
| Review Kelso changes in a user's rating based on event | person page chart | Series switcher: Overall or any single event. Step line (ratings change only at competitions), crosshair tooltip with competition and change; click goes to the competition. The competition table lists improved events with new ratings and deltas. |
| Find user by name or WCA ID | header search | Suggestions while typing (name prefix per word, diacritics folded, exact WCA ID, WCA ID prefix); `/search` result page; a single hit redirects to the person. |
| Read about the Kelso rating | `/about` | What the rating means, reading the numbers, comparison with Kinch / Sum of Ranks / mean / best event, live event-ceiling table, the calculation with equations (KaTeX), the reference field and updates, evidence, the data-pipeline diagram, limitations. **PDF of the full paper** to download. |
| Hypothetical rating from input times | `/calculator` | 17 inputs (times, FMC mean, MBLD as `solved/attempted time`). Computed in the browser from the frozen conversion tables. World rank and percentile come from `/api/rank`. Start from any competitor's PBs and edit them, compared against their current rating. State lives in the URL hash, so a result can be shared as a link. |
| Review an ended competition | `/competitions/{id}` | Precomputed: before/after/change per competitor, improved events with new event ratings, summary cards, sorting by gain, rating or name. |
| Review an ongoing competition (estimated) | `/competitions/{id}` (not in export) | Same layout, filled from live WCIF results, labelled *Estimated* with a live dot and update time, auto-refreshing while the competition runs. Newcomers without a WCA ID are included. |
| (future) Log in with WCA | — | See ADR-010. |

`/competitions` lists running competitions and ones awaiting the export (loaded asynchronously from the WCA API), then the official results from the database, newest first.

## Visual language

* **Type:** system UI font stack (no web-font download); tabular numerals for every rating and rank; ratings in bold.
* **Colour tokens:** ink and muted greys, one accent blue (`#0a5bd3` light / `#5c9dff` dark), green only for rating gains, red only for the live indicator and the PDF badge.
* **Charts:** one series at a time, a 2 px step line in the accent colour with a faint area, a recessive grid, a crosshair and tooltip, and the endpoint marked. The title names the series, so there is no legend.
* **Layout:** 1120 px max width, 16 px gutters. Below 760 px, secondary columns (events strip, best event, breadth, set-at competition) hide, the navigation wraps under the logo, and tables scroll horizontally inside their card.

## Performance budget

| Asset | Size |
| --- | --- |
| `site.css` | ~19 KB (≈ 5 KB gzipped) |
| `cube.js` + `kelso.js` + `algs-verified.js` | ~26 KB (≈ 9 KB gzipped) |
| Event icon font | 7.6 KB |
| Home page HTML | ≈ 190 KB raw / 21 KB gzipped (100 rows) |
| Calculator tables | 540 KB raw / 220 KB gzipped, cached by base id, calculator only |
| KaTeX | About page only |

Static files are cached as immutable for a year behind a content hash; pages for 5 minutes.
