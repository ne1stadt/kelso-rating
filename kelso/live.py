"""Competitions that are not (yet) in the export: running now, or ended and awaiting the next export.

Design (docs/architecture.md, "Live path"):
* Nothing is polled in the background. Upstream is only contacted when someone opens a page,
  and every response is cached with a TTL (2 min for a running competition, 1 h after it
  ended), with one in-flight request per key, so a busy page costs one upstream call per TTL.
* One source for every scoretaking system: the public WCIF of the competition, which carries
  live results whether the competition is scored in WCA Live or in the WCA website itself.
* Estimates are computed against the frozen base, exactly like official results, using the
  competitor's current personal bests from the database. They are labelled as estimates.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np

from .config import (CACHE_DIR, COMP_LIST_TTL, EVENTS, LIVE_TTL_ONGOING, LIVE_TTL_PENDING,
                     PENDING_LOOKBACK_DAYS, USER_AGENT, WCA_API)
from .rating import odds, overall_from_odds, result_value

EID = {e: i for i, e in enumerate(EVENTS)}


class TTLCache:
    """Tiny in-process cache with per-key locks (single flight) and a disk copy for restarts."""

    def __init__(self, name):
        self.mem: dict[str, tuple[float, object]] = {}
        self.locks: dict[str, threading.Lock] = {}
        self.guard = threading.Lock()
        self.dir = CACHE_DIR / name
        self.dir.mkdir(parents=True, exist_ok=True)

    def _disk(self, key):
        return self.dir / (urllib.parse.quote(key, safe="") + ".json")

    def get(self, key, ttl, loader):
        """Return (value, fetched_at). Fresh hit: served. Stale hit: served at once while one
        background thread refreshes it. Miss: load inline (single flight per key)."""
        now = time.time()
        hit = self.mem.get(key)
        if hit is None:
            f = self._disk(key)
            if f.exists():
                hit = (f.stat().st_mtime, json.loads(f.read_text()))
                self.mem[key] = hit
        if hit and now - hit[0] < ttl:
            return hit[1], hit[0]
        with self.guard:
            lock = self.locks.setdefault(key, threading.Lock())
        if hit:  # stale: refresh in the background unless a refresh is already running
            if lock.acquire(blocking=False):
                threading.Thread(target=self._refresh, args=(key, loader, lock), daemon=True).start()
            return hit[1], hit[0]
        with lock:
            hit = self.mem.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1], hit[0]
            return self._store(key, loader())

    def _store(self, key, val):
        ts = time.time()
        self.mem[key] = (ts, val)
        tmp = self._disk(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(val))
        tmp.replace(self._disk(key))
        return val, ts

    def _refresh(self, key, loader, lock):
        try:
            self._store(key, loader())
        except Exception:
            pass  # keep serving the stale copy; the next request retries
        finally:
            lock.release()


_lists = TTLCache("lists")
_wcif = TTLCache("wcif")
_upstream = threading.Semaphore(4)   # never more than 4 concurrent requests to the WCA


def _get_json(url, with_headers=False):
    with _upstream:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
            return (data, r.headers) if with_headers else data


def _all_pages(base_url, params, max_pages=10):
    """All pages of a paginated WCA API list: page 1 tells the total, the rest are fetched in parallel."""
    first, headers = _get_json(f"{base_url}?{urllib.parse.urlencode({**params, 'page': 1})}", with_headers=True)
    per = int(headers.get("Per-Page") or params.get("per_page", 25))
    total = int(headers.get("Total") or len(first))
    pages = min(max_pages, -(-total // per))
    if pages <= 1:
        return first
    with ThreadPoolExecutor(4) as ex:
        rest = ex.map(lambda p: _get_json(f"{base_url}?{urllib.parse.urlencode({**params, 'page': p})}"), range(2, pages + 1))
        return first + [c for batch in rest for c in batch]


def _slim_comp(c):
    return {k: c.get(k) for k in ("id", "name", "short_display_name", "city", "country_iso2", "start_date",
                                  "end_date", "event_ids", "results_posted_at", "cancelled_at", "competitor_limit")}


def competition_lists(known_ids) -> dict:
    """Ongoing competitions and ended competitions whose results are not in our database yet."""
    today = date.today()

    def load():
        t = today.isoformat()
        # ongoing_and_future is sorted by start date: the running competitions come first
        first = _get_json(f"{WCA_API}/competitions?" + urllib.parse.urlencode(
            {"ongoing_and_future": t, "sort": "start_date", "per_page": 100, "page": 1}))
        ongoing = [_slim_comp(c) for c in first if c["start_date"] <= t]
        start = (today - timedelta(days=PENDING_LOOKBACK_DAYS)).isoformat()
        recent = [_slim_comp(c) for c in _all_pages(f"{WCA_API}/competitions",
                                                    {"start": start, "end": t, "sort": "-end_date", "per_page": 100})
                  if c["end_date"] < t]
        return {"ongoing": ongoing, "recent": recent}

    data, ts = _lists.get(f"lists-{today.isoformat()}", COMP_LIST_TTL, load)
    pending = [c for c in data["recent"] if c["id"] not in known_ids and not c.get("cancelled_at")]
    ongoing = [c for c in data["ongoing"] if c["id"] not in known_ids and not c.get("cancelled_at")]
    return {"ongoing": ongoing, "pending": sorted(pending, key=lambda c: c["end_date"], reverse=True), "fetched_at": ts}


def fetch_wcif(comp_id: str, ongoing: bool):
    def load():
        w = _get_json(f"{WCA_API}/competitions/{urllib.parse.quote(comp_id)}/wcif/public")
        # keep only what the estimate needs; full WCIFs of big competitions are ~1 MB
        persons = [{"r": p["registrantId"], "id": p.get("wcaId"), "n": p["name"], "c": p.get("countryIso2")}
                   for p in w.get("persons", []) if p.get("registrantId") is not None]
        res = []
        for ev in w.get("events", []):
            if ev["id"] not in EID:
                continue
            for rnd in ev.get("rounds", []):
                for r in rnd.get("results", []):
                    if (r.get("best") or 0) > 0 or (r.get("average") or 0) > 0:
                        res.append([r["personId"], ev["id"], r.get("best") or 0, r.get("average") or 0])
        return {"id": w.get("id", comp_id), "name": w.get("name", comp_id), "persons": persons, "results": res,
                "schedule": {"start": (w.get("schedule") or {}).get("startDate"),
                             "days": (w.get("schedule") or {}).get("numberOfDays")}}

    return _wcif.get(comp_id, LIVE_TTL_ONGOING if ongoing else LIVE_TTL_PENDING, load)


def estimate(wcif: dict, store) -> list[dict]:
    """Estimated rating change of every competitor with a valid result at a competition not yet exported.

    store must provide: current_pbs(wca_ids) -> {wca_id: {eid: (raw, rating)}}, tables (ConversionTables),
    persons_info(wca_ids) -> {wca_id: {...}}.
    """
    best: dict[int, dict[str, list[int]]] = {}
    for pid, e, single, average in wcif["results"]:
        d = best.setdefault(pid, {}).setdefault(e, [0, 0])
        if single > 0 and (d[0] <= 0 or single < d[0]):
            d[0] = single
        if average > 0 and (d[1] <= 0 or average < d[1]):
            d[1] = average
    people = {p["r"]: p for p in wcif["persons"]}
    ids = [people[r]["id"] for r in best if r in people and people[r]["id"]]
    pbs = store.current_pbs(ids)
    out = []
    for reg, evs in best.items():
        p = people.get(reg)
        if p is None:
            continue
        cur = pbs.get(p["id"], {}) if p["id"] else {}
        S0 = float(sum(odds(r) for _, r in cur.values()))
        S1, changes = S0, []
        for e, (single, average) in evs.items():
            v = float(result_value(e, [single], [average])[0])
            if np.isnan(v):
                continue
            i = EID[e]
            raw_new = single if e in ("333bf", "444bf", "555bf", "333mbf") else average
            old = cur.get(i)
            if old is not None:
                v_old = float(result_value(e, [old[0]], [old[0]])[0])
                if not v < v_old:
                    continue
            r_new = float(store.tables.rate(e, v)[0])
            r_old = old[1] if old else None
            S1 += odds(r_new) - (odds(r_old) if old else 0.0)
            changes.append({"event": e, "raw": int(raw_new), "old_raw": int(old[0]) if old else None,
                            "rating": round(r_new, 1), "old_rating": round(r_old, 1) if old else None})
        before = float(overall_from_odds(S0)) if S0 > 0.5 else None
        after = float(overall_from_odds(S1)) if S1 > 0.5 else before
        out.append({"wca_id": p["id"], "name": p["n"], "iso2": p["c"], "before": before, "after": after,
                    "changes": sorted(changes, key=lambda c: EID[c["event"]])})
    return out
