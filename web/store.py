"""Read side of the site: one immutable SQLite file per build, plus small in-memory helpers.

The database is opened read-only with immutable=1 (no locking, no journal checks) because a
published build is never modified. When the nightly build repoints current.sqlite, the next
request notices the new target and a fresh Store is created; old connections simply age out.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from functools import cached_property
from pathlib import Path

import numpy as np

from kelso.config import BASE_DIR, CURRENT_DB, EVENTS
from kelso.rating import ConversionTables

EID = {e: i for i, e in enumerate(EVENTS)}


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.local = threading.local()

    @property
    def db(self) -> sqlite3.Connection:
        con = getattr(self.local, "con", None)
        if con is None:
            con = sqlite3.connect(f"file:{self.path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
            con.row_factory = sqlite3.Row
            self.local.con = con
        return con

    def q(self, sql, *args):
        return self.db.execute(sql, args).fetchall()

    def one(self, sql, *args):
        return self.db.execute(sql, args).fetchone()

    # ------------------------------------------------------------------ cached per build
    @cached_property
    def meta(self) -> dict:
        m = {r["key"]: r["value"] for r in self.q("SELECT key, value FROM meta")}
        m["stats"] = json.loads(m["stats"])
        m["base"] = json.loads(m["base"])
        return m

    @cached_property
    def version(self) -> str:
        return self.path.stem

    @cached_property
    def countries(self) -> dict:
        return {r["id"]: dict(r) for r in self.q("SELECT * FROM countries")}

    @cached_property
    def continents(self) -> dict:
        return {r["id"]: dict(r) for r in self.q("SELECT * FROM continents")}

    @cached_property
    def iso2_to_country(self) -> dict:
        return {c["iso2"]: cid for cid, c in self.countries.items()}

    @cached_property
    def overall_sorted(self) -> np.ndarray:
        """Ascending overall ratings: rank of any hypothetical rating by binary search."""
        return np.array([r[0] for r in self.q("SELECT overall FROM persons WHERE overall IS NOT NULL ORDER BY overall")])

    def rank_of(self, rating: float) -> dict:
        arr = self.overall_sorted
        above = len(arr) - int(np.searchsorted(arr, rating, side="right"))
        return {"rank": above + 1, "total": int(len(arr)), "top_share": (above + 1) / len(arr)}

    @cached_property
    def tables(self) -> ConversionTables:
        return ConversionTables.load(BASE_DIR / self.meta["base_id"] / "tables.npz")

    @cached_property
    def tables_json_path(self) -> Path:
        return BASE_DIR / self.meta["base_id"] / "tables.json"

    @cached_property
    def comp_ids(self) -> set:
        """Competitions with results in the export (the table also lists announced, future ones)."""
        return {r[0] for r in self.q("SELECT id FROM competitions WHERE competitors > 0")}

    # ------------------------------------------------------------------ queries used by live estimates
    def current_pbs(self, wca_ids) -> dict:
        out: dict[str, dict[int, tuple[int, float]]] = {}
        ids = list(wca_ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            rows = self.q(f"""SELECT p.wca_id, e.eid, e.raw, e.rating FROM persons p JOIN event_ratings e ON e.ppk = p.pk
                              WHERE p.wca_id IN ({','.join('?' * len(chunk))})""", *chunk)
            for r in rows:
                out.setdefault(r["wca_id"], {})[r["eid"]] = (r["raw"], r["rating"])
        return out


_lock = threading.Lock()
_store: Store | None = None


def get_store() -> Store:
    """Store for the currently published build (re-resolved on every call: one readlink)."""
    global _store
    target = Path(os.path.realpath(CURRENT_DB))
    s = _store
    if s is None or s.path != target:
        with _lock:
            if _store is None or _store.path != target:
                if not target.exists():
                    raise FileNotFoundError("no database published yet: run `python -m kelso update`")
                _store = Store(target)
            s = _store
    return s
