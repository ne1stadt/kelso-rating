# Kelso rating

A cross-event rating for WCA speedcubers on the Elo scale, as a website.

Every personal best is placed on one scale: the odds, in Elo units (400 points per tenfold odds), of beating the personal best of a random member of the 3x3 field. Other events are linked to the 3x3 field by kernel-smoothed equipercentile linking. A competitor's overall rating sums those odds across events. The method is described in the paper in `paper/`, and the site serves its PDF on the *Kelso system* page.

## Quick start

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m kelso update     # ~1 min: fetches ~130 MB of the WCA export, creates the base, builds the database
.venv/bin/python -m kelso serve      # http://127.0.0.1:8040
```

Commands (`python -m kelso …`):

| Command | What it does |
| --- | --- |
| `update` | Checks the WCA export date (1 KB). If there is a new export: ranged download → ingest → build → atomic publish. Run hourly from cron. `--force`, `--local-zip FILE`, `--keep-raw` |
| `renew` | Re-estimates the frozen reference field from the current export (annual, announced) and rebuilds |
| `ingest`, `build` | The individual steps of `update` |
| `serve` | Web server (`--host`, `--port`, `--workers`) |

`node scripts/check_algs.js --write` verifies the cube's OLL/PLL/ZBLS algorithms (`web/static/js/algs.js`) and regenerates `algs-verified.js`.

`scripts/build_paper_pdf.py` re-renders `web/static/files/kelso-rating-paper.pdf` from the paper's docx (needs Chrome or Chromium).

## Layout

```
kelso/      pipeline + rating (fetch, ingest, base, build, live) and the CLI
web/        Starlette app, templates, static assets
docs/       architecture.md · decisions.md · design.md · use-cases.md
deploy/     systemd units (web + hourly update timer), nginx sample
paper/      the paper and its supplement (code, reference outputs, ratings)
data/       (git-ignored) export parts, parquet, bases, SQLite builds, caches
```

## Data

This information is based on competition results owned and maintained by the World Cube Association, published at https://worldcubeassociation.org/results. Kelso is an independent, non-commercial project and is not affiliated with the WCA. Event icons: [cubing/icons](https://github.com/cubing/icons) (MIT). Flags: [flag-icons](https://github.com/lipis/flag-icons) (MIT). Math: [KaTeX](https://katex.org) (MIT).
