# Architecture

Kelso is a small, read-mostly site over a public data set that changes once a day. The architecture follows from three facts:

1. **The rating is a pure function of personal bests under a frozen base** (paper §3.4). Between annual renewals, a competitor's rating depends only on their own results. Nothing has to be recomputed for anyone else when someone competes.
2. **The WCA publishes one full export per day.** It's a 380 MB zip that's ~1.3 GB unpacked, and most of it (scrambles, individual attempts) is irrelevant to the rating.
3. **Hosting budget is one small server.** The design target is a 2 vCPU / 2 GB VPS with no managed services.

The result is a nightly batch job that turns the export into one immutable SQLite file, and a thin web process that only reads it. Only competitions not yet in the export are fetched live, and only when someone opens one.

```
                 ┌──────────── daily (cron: hourly check, runs once per new export) ─────────────┐
 WCA export API ─┤ metadata (1 KB) → ranged download (~130 of 380 MB) → ingest → build → SQLite │
                 └───────────────────────────────────────────────────────────┬───────────────────┘
                                                frozen base (annual renewal) ─┤ conversion tables
                                                                              ▼
 Browser ◀──── HTML / JSON ────▶ Kelso web (Starlette, read-only SQLite, in-memory rank index)
                                       │  only when a live / pending competition page is opened
                                       ▼
                         WCA API (competition lists) + public WCIF (live results)
```

## Components

| Path | Role |
| --- | --- |
| `kelso/config.py` | Paths, events, rating constants, cache TTLs |
| `kelso/rating.py` | The rating: `KCDF`, `Rater` (ported unchanged from the paper's `core.py`), `ConversionTables` (frozen base as lookup tables) |
| `kelso/fetch.py` | Export metadata check; `HttpRangeFile` + `zipfile` to pull single members out of the remote zip |
| `kelso/ingest.py` | Streams `results.tsv` (6.98 M rows) into a 4.73 M-row parquet of best single/average per person × competition × event |
| `kelso/base.py` | Base renewal: fits the 17 field distributions + 16 linkings, stores base PB ratings and conversion tables |
| `kelso/build.py` | Nightly build: PB history, ratings, rating history, ranks, competition stats → one SQLite file, atomically published |
| `kelso/live.py` | Competitions not in the export: competition lists, WCIF fetch, estimated rating changes; TTL cache with single flight and stale-while-revalidate |
| `kelso/cli.py` | `python -m kelso update | renew | ingest | build | serve` |
| `web/` | Starlette app, Jinja templates, static assets (no build step, no client framework) |
| `scripts/build_paper_pdf.py` | Renders the paper (docx) to the downloadable PDF via KaTeX + headless Chrome |

## Data flow

### 1. When to fetch

* The WCA regenerates the export once a day (around 10:15 UTC at the time of writing). Its metadata endpoint `GET /api/v0/export/public` returns `export_date`, `tsv_url` and sizes in about 1 KB.
* `python -m kelso update` runs **hourly from cron**. It compares `export_date` with the one stored in the live database. When nothing changed (23 of 24 runs) it exits after that one small request (~1 s).
* The export host **rate-limits downloads**. During development, the fourth full download in a few hours returned HTTP 429. The pipeline therefore downloads at most once per new export, never retries a 429 in a loop, and exits with `EX_TEMPFAIL` (75) so the next hourly run retries. The live database stays in service meanwhile.

### 2. What to fetch: ranged zip members

The export zip compresses each member separately and keeps its central directory at the end. `HttpRangeFile` is a seekable file over HTTP `Range` requests; wrapping it in `zipfile.ZipFile` reads the directory (a few KB) and then only the byte ranges of the needed members:

| Member | Compressed | Used for |
| --- | --- | --- |
| `results.tsv` | 118 MB | every round result (best, average) |
| `competitions.tsv` | 5 MB | names, places, dates (chronological order) |
| `persons.tsv` | 5 MB | names, countries |
| `countries.tsv`, `continents.tsv`, `metadata.json` | < 1 MB | regions, export date |
| **skipped:** `result_attempts`, `scrambles`, `ranks_*`, … | 253 MB | — |

Measured: **132 MB fetched of 381 MB (35%) in 17 s**, byte-identical to a full download. Members are read in archive order, and read-ahead is capped at each member's end so no bytes from skipped members are pulled.

Why not `ranks_single`/`ranks_average`, which already hold personal bests? Because the site shows *histories* (rating after each competition, rating changes per competition), which need every result, not just the current best.

### 3. Ingest (≈ 4.5 s, peak ≈ 1.2 GB)

`results.tsv` is streamed with Arrow in 2 MB blocks. Larger blocks made the reader's read-ahead hold up to 1 GB. Every string ID is immediately replaced by its integer position in the persons, competitions and events lists (`pc.index_in`), so only compact int arrays are held. The reduction to one row per person × competition × event (best single, best average) is a sort + `minimum.reduceat` on one packed int64 key instead of a pandas groupby (which peaked at 3.1 GB).

Output in `data/work/`: `results.parquet` (33 MB, ids as integer positions), `persons`, `competitions` (+ competitor counts), `countries`, `continents`, `ingest.json`.

### 4. Base renewal (annual, ≈ 60 s)

Equating practice, adopted by the paper: the field distributions are estimated once on a base population and then frozen (ADR-004). `python -m kelso renew`:

1. builds the PB matrix W (persons × 17 events) from the ingested export;
2. fits `Rater(W)`, which estimates 17 kernel-continuized field distributions and 16 common-group linkings (0.5 s);
3. rates every base personal best as a *member* of the field → `base_pbs.parquet` (wca_id, event, value, rating);
4. reduces the frozen base to **conversion tables**, one monotone table per event mapping log result → rating for results *outside* the base field (the paper's new-member rule). Knots (≈ 2,048 per event) are placed at equal arc length of the exact curve, so they crowd where the rating is steep. Measured against the exact formula, the maximum error is 0.56 points and the p99 is 0.002 points;
5. writes `tables.npz` (server) and `tables.json` (220 KB gzipped, browser calculator).

Validation against the paper's published ratings (`paper/.../ratings_2026-10-14.csv`, base two days older): the top 5 are identical, and the median absolute difference over 293,517 competitors is 0.25 points. The few large differences are competitors with new PBs in those two days.

The first `update` on an empty data directory renews automatically. After that, renewal is a deliberate, announced command, never a side effect of a nightly run.

### 5. Build (≈ 8 s, peak ≈ 1.24 GB)

All official numbers on the site are precomputed:

1. **PB history.** Results are sorted by (person, event, competition order) using one packed key. A running minimum that resets per group marks every result that improved a personal best (2.24 M rows). MBLD is keyed by the dense rank of its rated value, so ties follow the paper exactly.
2. **Ratings.** Every PB that ever stood is rated through the conversion tables. If it *is* the base PB, it gets the base member rating instead, which reproduces the paper's numbers exactly.
3. **History as a cumulative sum (ADR-006).** With K = 400 the overall rating is `400·log10(S)`, where `S = Σ_e 10^(R_e/400)`. Improving event e from R to R′ changes S by `10^(R′/400) − 10^(R/400)`. Summing increments per (person, competition) and taking a per-person cumulative sum gives every competitor's rating before and after every competition (1.19 M rows) without re-aggregating anything. The last history value equals the directly computed current rating to 5·10⁻¹³.
4. **Current state.** Current event ratings with world, continent and country ranks per event; overall rating with world, continent and country ranks; competition stats; a rating histogram and thresholds for the site.
5. **Write and publish.** The build writes a new file `data/db/kelso-<export>-<ts>.sqlite` with no journal, creates indexes and FTS5 afterwards, then atomically swaps the symlink `data/db/current.sqlite` to it. It keeps the newest two builds.

Each stage's time and peak memory are stored in the database's `meta` table (`timings`, `peak_rss_mb`).

| Table | Rows | Purpose |
| --- | --- | --- |
| `persons` | 300 k | current overall rating, ranks, counts |
| `event_ratings` | 918 k | current PB, event rating, event ranks, competition where set |
| `pb_history` | 2.24 M | every PB improvement with its rating and the previous rating |
| `participation` | 1.19 M | overall rating before/after each competition |
| `competitions` | 19 k | metadata, competitors, number improved |
| `person_fts` | FTS5 | name / WCA ID search (diacritics folded) |

The file is about 340 MB. Integer surrogate keys (`pk`) keep the big tables narrow.

### 6. Serving

* **Starlette + Jinja2**, server-rendered HTML. JavaScript only enhances: search suggestions, chart, calculator, live estimates and the cube. No build step, no framework.
* SQLite is opened **read-only with `immutable=1`**: no locks and no WAL checks, safe because published files never change. Every request re-resolves the symlink (one `readlink`), so a new build is picked up without a restart.
* Per build, the store caches metadata, the sorted array of all overall ratings (2.3 MB; the rank of any hypothetical rating is a binary search), the conversion tables and the set of exported competitions.
* Measured on a laptop: rankings page 3–15 ms, person page 2–30 ms, competition page with 1,864 competitors 50 ms; home page **21 KB gzipped**; server RSS **≈ 130 MB**.
* HTTP caching: official pages `max-age=300`, live JSON `max-age=30`, static assets immutable for a year behind a content hash (`?v=`), and conversion tables with `ETag = base id`. A CDN or nginx cache in front would absorb almost all traffic.

### 7. Live path: competitions not yet in the export

A competition is "live or pending" if the WCA API lists it as running, or ended within the last 14 days, and it has no results in our database.

* **One upstream format.** The public WCIF (`/api/v0/competitions/{id}/wcif/public`) carries live round results both for competitions scored in WCA Live and for those scored in the WCA website itself (`scoretaking_software: "internal"`). WCA Live's GraphQL would cover only the former.
* **No background polling.** Upstream is contacted only when someone opens a live page or the competitions index. Responses are cached in memory and on disk (`data/cache`):

| Data | TTL | Notes |
| --- | --- | --- |
| Competition lists (ongoing + recently ended) | 15 min | parallel paging via the `Total` header; warmed at startup |
| WCIF of a running competition | 2 min | page auto-refreshes after the TTL |
| WCIF of an ended, unexported competition | 1 h | |

* **Single flight + stale-while-revalidate.** One lock per key means a popular competition costs one upstream request per TTL however many people watch it. Once something is cached, an expired entry is served immediately while one background thread refreshes it. A failed refresh keeps the stale copy. At most 4 concurrent upstream requests.
* **Estimate.** For each competitor: best single/average per event at the competition → if better than their PB in the database, rate it through the frozen tables → `S′ = S − 10^(R_old/400) + 10^(R_new/400)`. Newcomers without a WCA ID are rated from the competition alone. The world rank after the competition comes from the in-memory rank index. The page labels these as estimates.
* The WCA API is slow (2–8 s per request). The competitions index therefore renders the official list from SQLite instantly and loads the live sections asynchronously behind the cube loader.
* When the next export contains the competition, its page switches to the official precomputed view automatically.

## Resource budget

| Step | Time | Peak memory | Network |
| --- | --- | --- | --- |
| Hourly check, no new export | ~1 s | ~50 MB | 1 KB |
| Ranged download | ~17 s | ~100 MB | 132 MB |
| Ingest | ~4.5 s | ~1.2 GB | — |
| Build + publish | ~8 s | ~1.24 GB | — |
| **Daily update total** | **~35 s** | **~1.25 GB** (steps run as separate processes) | **132 MB/day** |
| Base renewal (annual) | ~60 s | ~1.9 GB | — |
| Web server, steady | — | ~130 MB | live pages only |
| Disk | | | ~0.7 GB (two DB builds) + 30 MB base + ~50 MB work |

A 2 GB VPS is enough. On a 1 GB machine, add swap for the nightly job; the web server itself is unaffected.

## Deployment

```
# once
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m kelso update             # first run also creates the base

# cron (user crontab): check hourly, a new export is processed within the hour
17 * * * *  cd /srv/kelso && .venv/bin/python -m kelso update >> data/update.log 2>&1

# web: one uvicorn process behind nginx (TLS, gzip, optional proxy cache)
.venv/bin/python -m kelso serve --host 127.0.0.1 --port 8040 --workers 2
```

Sample systemd and nginx files are in `deploy/`.

## Failure modes

| Failure | Effect |
| --- | --- |
| Export host down or rate-limiting | Update exits (75); yesterday's database keeps serving; next hourly run retries |
| Export format major version changes | Ingest fails loudly on missing columns; database unchanged. `export_format_version` is stored in `meta` |
| Build crashes midway | Only a `.tmp` file is left; the symlink still points to the previous build |
| WCA API / WCIF down | Official pages unaffected; live sections show "unavailable" or serve the stale cached copy |
| Server restart | Disk cache keeps live data; the competition list is re-warmed in the background |

## Possible next steps

* **Fast lane for posted results.** Competitions are often posted hours before the next daily export. Their official results (`/api/v0/competitions/{id}/results`) could be merged into an overlay database between exports. This is deliberately left out of v1: the live path already shows them (as estimates), and one write path keeps the system simple.
* **Uncertainty intervals.** The paper's conversion bootstrap (~35 min per renewal) could run at renewal and be stored with the base.
* **WCA OAuth login** for "my rating" without searching (see `decisions.md`, ADR-010).
