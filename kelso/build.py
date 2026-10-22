"""Nightly build: export (slim parquet) + frozen base -> one immutable SQLite database.

Everything the site shows about official results is precomputed here, so the web process only
does indexed lookups. The build writes a new file and then atomically repoints the
`current.sqlite` symlink; readers never see a half-written database (ADR-003).

History trick (ADR-006): with K = 400 the overall rating is 400*log10(S), where S is the sum of
the event odds 10^(R_e/400). When a competitor improves a personal best, S changes by
odds(new) - odds(old). The whole rating history of every competitor is therefore one cumulative
sum over their competitions -- no per-person loop, no re-aggregation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .base import active_base
from .config import CURRENT_DB, DB_DIR, EVENTS, SINGLE_EVENTS, WORK_DIR
from .rating import ConversionTables, mbf_value, odds, overall_from_odds

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;
CREATE TABLE continents (id TEXT PRIMARY KEY, name TEXT) WITHOUT ROWID;
CREATE TABLE countries (id TEXT PRIMARY KEY, iso2 TEXT, name TEXT, continent_id TEXT) WITHOUT ROWID;
CREATE TABLE persons (
  pk INTEGER PRIMARY KEY, wca_id TEXT NOT NULL, name TEXT, country_id TEXT, continent_id TEXT,
  overall REAL, n_events INTEGER, best_event TEXT, best_rating REAL,
  rank_world INTEGER, rank_continent INTEGER, rank_country INTEGER,
  n_comps INTEGER, first_date TEXT, last_date TEXT);
CREATE TABLE competitions (
  pk INTEGER PRIMARY KEY, id TEXT NOT NULL, name TEXT, city TEXT, country_id TEXT,
  start_date TEXT, end_date TEXT, competitors INTEGER, events TEXT,
  n_improved INTEGER, sum_gain REAL);
CREATE TABLE event_ratings (
  ppk INTEGER, eid INTEGER, raw INTEGER, rating REAL, cpk INTEGER,
  country_id TEXT, continent_id TEXT,
  rank_world INTEGER, rank_continent INTEGER, rank_country INTEGER,
  PRIMARY KEY (ppk, eid)) WITHOUT ROWID;
CREATE TABLE pb_history (
  ppk INTEGER, eid INTEGER, cpk INTEGER, raw INTEGER, rating REAL, prev_rating REAL,
  PRIMARY KEY (ppk, eid, cpk)) WITHOUT ROWID;
CREATE TABLE participation (
  ppk INTEGER, cpk INTEGER, seq INTEGER, before REAL, after REAL, n_improved INTEGER,
  PRIMARY KEY (ppk, seq)) WITHOUT ROWID;
"""

INDEXES = """
CREATE UNIQUE INDEX persons_wca ON persons(wca_id);
CREATE INDEX persons_world ON persons(rank_world);
CREATE INDEX persons_continent ON persons(continent_id, rank_continent);
CREATE INDEX persons_country ON persons(country_id, rank_country);
CREATE INDEX persons_overall ON persons(overall);
CREATE UNIQUE INDEX competitions_id ON competitions(id);
CREATE INDEX competitions_date ON competitions(end_date);
CREATE INDEX er_world ON event_ratings(eid, rank_world);
CREATE INDEX er_continent ON event_ratings(eid, continent_id, rank_continent);
CREATE INDEX er_country ON event_ratings(eid, country_id, rank_country);
CREATE INDEX pbh_comp ON pb_history(cpk);
CREATE INDEX part_comp ON participation(cpk);
CREATE VIRTUAL TABLE person_fts USING fts5(name, wca_id, content='persons', content_rowid='pk',
  tokenize="unicode61 remove_diacritics 2");
INSERT INTO person_fts(person_fts) VALUES('rebuild');
ANALYZE;
"""


def _rss_mb() -> int:
    """Peak resident memory so far (MB); reported per stage in meta.timings."""
    import resource
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(r / (1 << 20) if sys.platform == "darwin" else r / 1024)


def _rank(values: pd.Series, groups: pd.Series | None = None) -> pd.Series:
    """Competition ranking (1, 2, 2, 4) on descending values; NaN stays NaN."""
    if groups is None:
        return values.rank(ascending=False, method="min")
    return values.groupby(groups).rank(ascending=False, method="min")


def build(work: Path = WORK_DIR, db_dir: Path = DB_DIR, base: Path | None = None) -> Path:
    t0 = time.time()
    timings, peak = {}, {}
    base = base or active_base()
    if base is None:
        raise RuntimeError("no base: run `kelso renew` first")
    tables = ConversionTables.load(base / "tables.npz")
    base_meta = json.loads((base / "meta.json").read_text())
    info = json.loads((work / "ingest.json").read_text())

    persons = pd.read_parquet(work / "persons.parquet")
    comps = pd.read_parquet(work / "competitions.parquet")
    countries = pd.read_parquet(work / "countries.parquet")
    continents = pd.read_parquet(work / "continents.parquet")
    cont_of = dict(zip(countries["id"], countries["continent_id"]))
    persons["continent_id"] = persons["country_id"].map(cont_of)

    # ------------------------------------------------------------------ PB improvements
    # Plain numpy on compact arrays: pandas sort/groupby/merge over 4.7 M rows held ~1.5 GB.
    corder = comps.sort_values(["end_date", "start_date", "id"]).index.to_numpy()  # chronological
    seq_of_comp = np.empty(len(comps), dtype=np.int64)
    seq_of_comp[corder] = np.arange(len(comps))
    res = pd.read_parquet(work / "results.parquet")
    pid = res["pid"].to_numpy(np.int32)
    cid = res["cid"].to_numpy(np.int32)
    eid = res["eid"].to_numpy(np.int8)
    single, average = res["single"].to_numpy(np.int32), res["average"].to_numpy(np.int32)
    del res
    # participation: every (person, competition) with a result row, in chronological order
    pkey = np.unique((pid.astype(np.int64) << 20) | seq_of_comp[cid])
    # the result that enters the rating, as WCA raw value; an exact integer sort key per event
    single_ev = np.isin(eid, [EVENTS.index(e) for e in SINGLE_EVENTS])
    raw = np.where(single_ev, single, average)
    del single, average, single_ev
    ok = raw > 0
    pid, cid, eid, raw = pid[ok], cid[ok], eid[ok], raw[ok]
    del ok
    mbf = EVENTS.index("333mbf")
    # one packed key sorts by person, event, then competition order (19 + 5 + 20 bits)
    order = np.argsort((pid.astype(np.int64) << 25) | (eid.astype(np.int64) << 20) | seq_of_comp[cid])
    pid, cid, eid, raw = pid[order], cid[order], eid[order], raw[order]
    del order
    t = seq_of_comp[cid].astype(np.int32)
    okey = raw.astype(np.int64)
    m = eid == mbf   # MBLD: order by the rated value 1/m (dense rank keeps it an exact integer key)
    okey[m] = np.unique(mbf_value(raw[m]), return_inverse=True)[1]
    del m
    first = np.r_[True, (pid[1:] != pid[:-1]) | (eid[1:] != eid[:-1])]
    grp = np.cumsum(first) - 1
    # running best per (person, event): one accumulate over keys shifted down by group, so the
    # minimum resets at every group start (exact in int64)
    shifted = okey - (grp.astype(np.int64) << 32)
    best = np.minimum.accumulate(shifted)
    improved = first | (shifted < np.r_[0, best[:-1]])
    del shifted, best, okey
    pid, cid, eid, raw, t, first = (a[improved] for a in (pid, cid, eid, raw, t, first))
    del grp, improved
    timings["pb_history"] = round(time.time() - t0, 1); peak["pb_history"] = _rss_mb()

    # ratings of every PB that ever stood: base member rating if it is the base PB, else table
    value = np.where(eid == mbf, np.nan, raw.astype(np.float64))
    value[eid == mbf] = mbf_value(raw[eid == mbf])
    rating = np.empty(len(raw))
    for i, e in enumerate(EVENTS):
        m = eid == i
        rating[m] = tables.rate(e, value[m])
    bp = pd.read_parquet(base / "base_pbs.parquet")
    pid_of = pd.Series(persons.index.to_numpy(), index=persons["wca_id"].to_numpy())
    bpid = bp["wca_id"].map(pid_of)
    keep = bpid.notna().to_numpy()
    bkey = (bpid[keep].to_numpy(np.int64) << 5) | bp["event"].map({e: i for i, e in enumerate(EVENTS)}).to_numpy(np.int64)[keep]
    bval, brat = bp["value"].to_numpy()[keep], bp["rating"].to_numpy()[keep]
    del bp, bpid
    border = np.argsort(bkey)
    bkey, bval, brat = bkey[border], bval[border], brat[border]
    ikey = (pid.astype(np.int64) << 5) | eid
    j = np.clip(np.searchsorted(bkey, ikey), 0, len(bkey) - 1)
    is_base = (bkey[j] == ikey) & np.isclose(value, bval[j], rtol=1e-12, atol=0)
    rating[is_base] = brat[j][is_base]
    del bkey, bval, brat, ikey, j, is_base, value
    prev = np.where(first, np.nan, np.r_[np.nan, rating[:-1]])
    d_odds = odds(rating) - np.where(first, 0.0, odds(np.nan_to_num(prev)))
    imp = pd.DataFrame({"pid": pid.astype(np.int32), "eid": eid.astype(np.int8), "cid": cid.astype(np.int32),
                        "t": t.astype(np.int32), "raw": raw, "rating": rating, "prev_rating": prev})
    timings["rate"] = round(time.time() - t0, 1); peak["rate"] = _rss_mb()

    # ------------------------------------------------------------------ rating history
    # S (sum of odds) after each competition = running sum of the odds increments (ADR-006)
    ppid, pt = pkey >> 20, pkey & 0xFFFFF
    idx = np.searchsorted(pkey, (pid.astype(np.int64) << 20) | t)
    d = np.bincount(idx, weights=d_odds, minlength=len(pkey))
    n = np.bincount(idx, minlength=len(pkey))
    del idx, d_odds, pid, cid, eid, raw, t, rating, prev, first
    pfirst = np.r_[True, ppid[1:] != ppid[:-1]]
    gstart = np.flatnonzero(pfirst)
    pg = np.cumsum(pfirst) - 1
    S = pd.Series(d).groupby(pg).cumsum().to_numpy()   # per person: a global cumsum would lose precision
    S_before = S - d
    with np.errstate(invalid="ignore", divide="ignore"):
        after = np.where(S > 0.5, overall_from_odds(np.clip(S, 1e-9, None)), np.nan)
        before = np.where(S_before > 0.5, overall_from_odds(np.clip(S_before, 1e-9, None)), np.nan)
    part = pd.DataFrame({"pid": ppid.astype(np.int32), "cid": corder[pt].astype(np.int32), "t": pt.astype(np.int32),
                         "seq": (np.arange(len(pkey)) - gstart[pg]).astype(np.int32),
                         "before": before, "after": after, "n": n.astype(np.int16)})
    del pkey, ppid, pt, d, n, pfirst, gstart, pg, S, S_before, after, before
    timings["history"] = round(time.time() - t0, 1); peak["history"] = _rss_mb()

    # ------------------------------------------------------------------ current state
    cur = imp.groupby(["pid", "eid"]).tail(1)[["pid", "eid", "cid", "raw", "rating"]].copy()
    S = cur.assign(o=odds(cur["rating"])).groupby("pid")["o"].sum()
    persons["overall"] = np.nan
    persons.loc[S.index, "overall"] = overall_from_odds(S.to_numpy())
    best = cur.sort_values("rating", ascending=False).groupby("pid").head(1).set_index("pid")
    persons["n_events"] = cur.groupby("pid").size().reindex(persons.index).fillna(0).astype(int)
    persons["best_event"] = best["eid"].reindex(persons.index).map(lambda i: EVENTS[int(i)] if pd.notna(i) else None)
    persons["best_rating"] = best["rating"].reindex(persons.index)
    persons["rank_world"] = _rank(persons["overall"])
    persons["rank_continent"] = _rank(persons["overall"], persons["continent_id"])
    persons["rank_country"] = _rank(persons["overall"], persons["country_id"])
    pc = part.groupby("pid").agg(n=("cid", "size"), first=("t", "min"), last=("t", "max"))
    end_by_seq = comps["end_date"].to_numpy()[corder]
    persons["n_comps"] = pc["n"].reindex(persons.index).fillna(0).astype(int)
    persons["first_date"] = pd.Series(end_by_seq[pc["first"].to_numpy()], index=pc.index).reindex(persons.index)
    persons["last_date"] = pd.Series(end_by_seq[pc["last"].to_numpy()], index=pc.index).reindex(persons.index)

    cur["country_id"] = persons["country_id"].to_numpy()[cur["pid"].to_numpy()]
    cur["continent_id"] = persons["continent_id"].to_numpy()[cur["pid"].to_numpy()]
    cur["rank_world"] = _rank(cur["rating"], cur["eid"])
    cur["rank_continent"] = _rank(cur["rating"], [cur["eid"], cur["continent_id"]])
    cur["rank_country"] = _rank(cur["rating"], [cur["eid"], cur["country_id"]])

    gains = part.assign(g=(part["after"] - part["before"].fillna(0)).where(part["n"] > 0)).groupby("cid").agg(
        n_improved=("n", lambda x: int((x > 0).sum())), sum_gain=("g", "sum"))
    comps["n_improved"] = gains["n_improved"].reindex(comps.index).fillna(0).astype(int)
    comps["sum_gain"] = gains["sum_gain"].reindex(comps.index).fillna(0.0)
    timings["current"] = round(time.time() - t0, 1); peak["current"] = _rss_mb()

    # ------------------------------------------------------------------ statistics for the site
    O = persons["overall"].dropna()
    stats = {
        "rated": int(len(O)), "median": round(float(O.median()), 1), "max": round(float(O.max()), 1),
        "thresholds": {str(p): round(float(O.quantile(1 - p)), 1) for p in [0.5, 0.1, 0.01, 0.001, 0.0001]},
        "events": {e: {"n": int((cur["eid"] == i).sum()),
                       "median": round(float(cur.loc[cur["eid"] == i, "rating"].median()), 1),
                       "max": round(float(cur.loc[cur["eid"] == i, "rating"].max()), 1)} for i, e in enumerate(EVENTS)},
        "histogram": np.histogram(O, bins=np.arange(0, 3801, 50))[0].tolist(),
    }
    meta = {
        "export_date": info["export_date"], "export_format_version": info["export_format_version"],
        "base": json.dumps(base_meta), "base_id": base_meta["id"],
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": json.dumps(stats),
    }

    # ------------------------------------------------------------------ write SQLite
    db_dir.mkdir(parents=True, exist_ok=True)
    stamp = info["export_date"][:19].replace(" ", "T").replace(":", "")
    path = db_dir / f"kelso-{stamp}-{int(time.time())}.sqlite"
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA page_size=8192;" + SCHEMA)

    def ins(table, df, cols, chunk=100_000):
        # chunked: converting a 2 M-row frame to Python objects at once costs ~1 GB
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        for i in range(0, len(df), chunk):
            part = df[cols].iloc[i:i + chunk]
            con.executemany(sql, part.astype(object).where(part.notna(), None).itertuples(index=False, name=None))

    def day(s):
        return pd.to_datetime(s).dt.strftime("%Y-%m-%d")

    ins("meta", pd.DataFrame(list(meta.items()), columns=["key", "value"]), ["key", "value"])
    ins("continents", continents, ["id", "name"])
    ins("countries", countries, ["id", "iso2", "name", "continent_id"])
    P = persons.reset_index(names="pk")
    P["first_date"], P["last_date"] = day(P["first_date"]), day(P["last_date"])
    ins("persons", P, ["pk", "wca_id", "name", "country_id", "continent_id", "overall", "n_events", "best_event",
                       "best_rating", "rank_world", "rank_continent", "rank_country", "n_comps", "first_date", "last_date"])
    C = comps.reset_index(names="pk")
    C["start_date"], C["end_date"] = day(C["start_date"]), day(C["end_date"])
    ins("competitions", C.rename(columns={"city_name": "city", "event_specs": "events"}),
        ["pk", "id", "name", "city", "country_id", "start_date", "end_date", "competitors", "events", "n_improved", "sum_gain"])
    ins("event_ratings", cur.rename(columns={"pid": "ppk", "cid": "cpk"}),
        ["ppk", "eid", "raw", "rating", "cpk", "country_id", "continent_id", "rank_world", "rank_continent", "rank_country"])
    ins("pb_history", imp.rename(columns={"pid": "ppk", "cid": "cpk"}), ["ppk", "eid", "cpk", "raw", "rating", "prev_rating"])
    ins("participation", part.rename(columns={"pid": "ppk", "cid": "cpk", "n": "n_improved"}),
        ["ppk", "cpk", "seq", "before", "after", "n_improved"])
    timings["insert"] = round(time.time() - t0, 1); peak["insert"] = _rss_mb()
    con.executescript(INDEXES)
    timings["total"] = round(time.time() - t0, 1); peak["total"] = _rss_mb()
    con.execute("INSERT INTO meta VALUES ('timings', ?)", (json.dumps(timings),))
    con.execute("INSERT INTO meta VALUES ('peak_rss_mb', ?)", (json.dumps(peak),))
    con.commit()
    con.close()
    tmp.replace(path)
    publish(path)
    return path


def publish(path: Path, keep: int = 2):
    """Atomically point current.sqlite at `path`; delete all but the newest `keep` builds."""
    link = CURRENT_DB
    tmp_link = link.with_name(".current.tmp")
    tmp_link.unlink(missing_ok=True)
    os.symlink(path.name, tmp_link)
    os.replace(tmp_link, link)
    builds = sorted(link.parent.glob("kelso-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in builds[keep:]:
        old.unlink(missing_ok=True)
