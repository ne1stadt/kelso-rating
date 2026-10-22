"""Paths, event metadata and constants of the Kelso rating.

The rating constants follow Table 3 of the paper; changing any of them changes the
rating and must go through a base renewal (see docs/decisions.md, ADR-004).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("KELSO_ROOT", Path(__file__).resolve().parent.parent))
DATA = Path(os.environ.get("KELSO_DATA", ROOT / "data"))

RAW_DIR = DATA / "raw"          # needed TSV members of the latest export (deleted after a build)
WORK_DIR = DATA / "work"        # slim parquet extracted from the export
BASE_DIR = DATA / "base"        # frozen reference populations, one folder per renewal
DB_DIR = DATA / "db"            # built SQLite databases; CURRENT_DB is a symlink to the live one
CACHE_DIR = DATA / "cache"      # WCIF / WCA API responses for live competitions
CURRENT_DB = DB_DIR / "current.sqlite"

WCA_EXPORT_API = "https://www.worldcubeassociation.org/api/v0/export/public"
WCA_API = "https://www.worldcubeassociation.org/api/v0"
USER_AGENT = "kelso-rating/0.1 (non-commercial cross-event rating; +https://github.com/)"

# Members of the export zip that the pipeline reads. The rest (scrambles, result_attempts,
# ranks_*) is about two thirds of the archive and is never downloaded.
EXPORT_MEMBERS = [
    "metadata.json",
    "WCA_export_persons.tsv",
    "WCA_export_competitions.tsv",
    "WCA_export_results.tsv",
    "WCA_export_countries.tsv",
    "WCA_export_continents.tsv",
]

# The 17 rated events, in WCA order. Order matters: it is the column order of every matrix.
EVENTS = ["333", "222", "444", "555", "666", "777", "333bf", "333fm", "333oh", "clock",
          "minx", "pyram", "skewb", "sq1", "444bf", "555bf", "333mbf"]
ANCHOR = "333"
SINGLE_EVENTS = {"333bf", "444bf", "555bf", "333mbf"}   # rated by best single (Section 2)
EVENT_NAMES = {
    "333": "3x3x3 Cube", "222": "2x2x2 Cube", "444": "4x4x4 Cube", "555": "5x5x5 Cube",
    "666": "6x6x6 Cube", "777": "7x7x7 Cube", "333bf": "3x3x3 Blindfolded",
    "333fm": "3x3x3 Fewest Moves", "333oh": "3x3x3 One-Handed", "clock": "Clock",
    "minx": "Megaminx", "pyram": "Pyraminx", "skewb": "Skewb", "sq1": "Square-1",
    "444bf": "4x4x4 Blindfolded", "555bf": "5x5x5 Blindfolded", "333mbf": "3x3x3 Multi-Blind",
}
EVENT_SHORT = {
    "333": "3x3", "222": "2x2", "444": "4x4", "555": "5x5", "666": "6x6", "777": "7x7",
    "333bf": "3BLD", "333fm": "FMC", "333oh": "OH", "clock": "Clock", "minx": "Megaminx",
    "pyram": "Pyraminx", "skewb": "Skewb", "sq1": "Square-1", "444bf": "4BLD",
    "555bf": "5BLD", "333mbf": "MBLD",
}

# Rating constants (paper, Table 3)
MEDIAN_RATING = 1200.0
UNIT = 400.0          # points per tenfold odds
K = 400.0             # aggregation constant; = UNIT, so overall odds are the sum of event odds
FLOOR = 0.0

# Conversion table resolution: points per event on a log-result grid (ADR-005).
TABLE_POINTS = 2048

# Live competitions
LIVE_TTL_ONGOING = 120        # seconds a WCIF of a running competition is reused
LIVE_TTL_PENDING = 3600       # ended, results not yet in the export
COMP_LIST_TTL = 900           # list of ongoing / recently ended competitions
PENDING_LOOKBACK_DAYS = 14    # how far back to look for ended competitions missing from the export
