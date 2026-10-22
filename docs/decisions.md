# Decision log

Short records of the decisions behind the site: what was chosen, why, and what it costs. Newest decisions are appended at the end.

---

## ADR-001 · One immutable SQLite file per export, built offline

**Decision.** All official data is precomputed by a batch job into a single SQLite file. The web process opens it read-only (`immutable=1`) and never writes.

**Why.** The data changes once a day and is read many times. SQLite needs no server and no tuning, and it is fast for indexed lookups. With immutable files there are no locks and no migrations, and backups are just copies. Rejected alternatives: PostgreSQL (a daemon, memory, and operations work for a read-only workload), and static HTML for every page (300 k person pages and 19 k competition pages on each rebuild, while search and filters still need a server).

**Cost.** ~340 MB per build on disk, two builds kept. A full rebuild every day instead of in-place updates, which is acceptable because it takes ~8 s.

## ADR-002 · Ranged download of only the needed zip members

**Decision.** Read the export zip through HTTP Range requests (`HttpRangeFile` + `zipfile`) and extract only persons, competitions, results, countries and continents.

**Why.** It cuts daily traffic from 381 MB to 132 MB (−65%), and download time with it. It is polite to an upstream that rate-limits. The bytes are identical to a full download, verified with `cmp`.

**Cost.** It depends on the export staying a zip on a server that honours `Range`. If it stops doing so, `HttpRangeFile` fails at the first request and the code can fall back to a plain download (`fetch_export(local_zip=...)` already supports a local archive).

## ADR-003 · Atomic publish by symlink swap

**Decision.** Each build writes `kelso-<export>-<ts>.sqlite`, then `os.replace`s a temporary symlink onto `current.sqlite`. The web process resolves the symlink on every request.

**Why.** Zero downtime, no restart, no half-written reads; rollback is re-pointing the link.

## ADR-004 · Frozen base, renewed annually and deliberately

**Decision.** Follow the paper (§3.4): estimate the field distributions on a base export, freeze them, and rate new results against them as new members. `update` never renews the base; `renew` is a separate command, run once a year at an announced date. The first base of this deployment is the export of **2026-10-16** (the paper used 2026-10-14; ratings agree to a median of 0.25 points).

**Why.** Ratings stay stable (paper criterion 4): a competitor's rating moves only when their own results do. It also makes the expensive part (fitting) a yearly job and keeps daily work to table lookups.

**Cost.** New events (FTO from January 2027) enter only at the next renewal after a common group with 3x3 exists. Rating drift accumulates and is released once a year, with the per-event shift published.

## ADR-005 · Frozen base as per-event lookup tables

**Decision.** Store the frozen base not as kernel objects but as one monotone table per event: log result → rating, ~2,048 knots placed at equal arc length of the exact curve. Results that are base PBs keep their exact member rating from `base_pbs.parquet`.

**Why.** One representation serves the nightly build, the live estimates and the browser calculator, so all three agree exactly. Lookups are a binary search. The tables are 220 KB gzipped, small enough to ship to the browser, so the calculator needs no server round trip per keystroke.

**Accuracy.** Measured against the exact new-member formula over all events: max |error| 0.56 points, p99 0.002 points. Uniform knots had a 5-point error at the 4x4 top, where the exact formula switches to the kernel sum. Arc-length knots fixed it.

## ADR-006 · Rating history as a cumulative sum of odds

**Decision.** History is computed from the identity `10^(R/400) = Σ_e 10^(R_e/400)` (paper eq. 5): each PB improvement contributes an odds increment, and the rating after each competition is `400·log10` of the per-person running sum.

**Why.** It is one vectorised pass over 2.24 M improvements instead of re-aggregating 17 event ratings at 1.19 M (person, competition) points. It follows from K = 400 and makes histories nearly free.

**Convention.** Histories are measured against the *current* base: they show how results accumulated on one fixed scale, not what the site would have displayed on that historical date. The person and competition pages state this.

## ADR-007 · Live competitions: on demand, via public WCIF, estimated

**Decision.** Competitions not in the export are read from the public WCIF only when a page asks. Responses are cached (2 min running, 1 h ended, 15 min for lists) with single flight and stale-while-revalidate. Changes are rated against the frozen base and labelled "Estimated".

**Why.** It is a performance-driven trade-off, as the brief allowed. Polling every running competition (dozens on a weekend) would cost constant upstream traffic for pages that are mostly never opened. The cost here is proportional to interest, bounded per competition, and zero when idle. WCIF was chosen over WCA Live GraphQL because it also covers competitions scored inside the WCA website (`scoretaking_software: "internal"`, about a third of current competitions).

**Cost.** The first visitor of a competition waits 2–8 s (the WCA API is slow), which is covered by the cube loader. Each pending competition is estimated independently against the export's PBs. A competitor in two pending competitions is not chained.

## ADR-008 · Server-rendered HTML, vanilla JS, no build step

**Decision.** Jinja templates rendered by Starlette. Small per-page scripts (`kelso.js` shared, plus `chart.js`, `calculator.js`, `live.js`, `competitions.js`). Vendored assets: the WCA event icon font (`@cubing/icons`, 7.6 KB, MIT), `flag-icons` (MIT), KaTeX (MIT; only on the About page).

**Why.** "First of all it is a rating system": the rankings must be fast and work without JS. Total CSS + JS is ~40 KB uncompressed, and the home page is 21 KB gzipped. There is no toolchain to maintain on a hobby project.

## ADR-009 · Python for both pipeline and web

**Decision.** One language. The pipeline reuses the paper's code (`KCDF`, `Rater`, `lse`) with unchanged behaviour. The web server is Starlette + uvicorn.

**Why.** Credibility: the site computes exactly what the paper describes (validated against the paper's CSV). One runtime to deploy. The heavy work is NumPy and Arrow, not Python loops.

**Memory work.** Pandas idioms over 4.7 M rows peaked at 3.1 GB (ingest) and 2.35 GB (build). Streaming Arrow with small blocks, integer IDs, packed sort keys and `ufunc.accumulate` / `reduceat` brought this down to 1.2 GB and 1.24 GB, with identical output (verified table by table against the pandas version). `update` runs the steps as separate processes.

## ADR-010 · No accounts in v1

**Decision.** No registration or login. Person pages are found through search (name or WCA ID, FTS5 with diacritics folded, prefix matching).

**Future.** Sign in with the WCA (OAuth2, `public` scope gives the WCA ID) would store only a cookie with the WCA ID: "my rating" in the header and the calculator prefilled. No server-side user table is needed for that.

## ADR-011 · Port and process defaults

`python -m kelso serve` defaults to `127.0.0.1:8040` (8000 is commonly taken by other dev servers). In production run behind nginx with `--workers 2`. Each worker holds its own ~130 MB of caches.

## ADR-012 · The cube plays verified algorithms

**Decision.** The logo and the loader play real OLL, PLL and ZBLS/F2L algorithms on a full 54-sticker model instead of random layer turns. The algorithm list is checked against the model at build time (`scripts/check_algs.js`), and only verified algorithms ship (`algs-verified.js`).

**Why.** The audience are cubers: a wrong algorithm, or a wrong case name under a correct one, would be noticed and would undercut a site whose point is credibility. Checking with the model is cheap (0.3 s for 123 algorithms) and catches both kinds of error. Case names for OLL are not shown (only OCLL is derived), because the numbering could not be verified independently.

**Cost.** ~10 KB more JavaScript on every page (≈ 3 KB gzipped). The full-axis renderer required the slab-splitting draw order described in `design.md`.
