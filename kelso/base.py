"""Base renewal: estimate the reference distributions once and freeze them (paper, Section 3.4).

A base is a folder data/base/<id>/ with
  tables.npz      conversion tables (one monotone log-result -> rating table per event)
  tables.json     the same tables for the browser calculator
  base_pbs.parquet  every personal best of the base field with its *member* rating
  meta.json       export date, field sizes, creation time

Between renewals nothing in the base changes, so a competitor's rating changes only when
their own results change. Renewal is annual (configurable); see docs/decisions.md ADR-004.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import BASE_DIR, EVENTS, WORK_DIR
from .rating import ConversionTables, Rater, result_value


def event_values(results: pd.DataFrame) -> pd.DataFrame:
    """Add column `value` (what the rating uses; smaller is better) and `raw` (WCA encoding)."""
    out = []
    for i, e in enumerate(EVENTS):
        x = results[results.eid == i]
        v = result_value(e, x["single"].to_numpy(), x["average"].to_numpy())
        use_single = e in ("333bf", "444bf", "555bf", "333mbf")
        raw = (x["single"] if use_single else x["average"]).to_numpy()
        out.append(x.assign(value=v, raw=raw))
    df = pd.concat(out)
    return df[df["value"].notna()]


def personal_bests(work: Path = WORK_DIR) -> pd.DataFrame:
    """Current personal-best matrix W (index wca_id, columns EVENTS), as in the paper's build_W.py."""
    persons = pd.read_parquet(work / "persons.parquet", columns=["wca_id"])
    res = event_values(pd.read_parquet(work / "results.parquet"))
    pb = res.groupby(["pid", "eid"])["value"].min().unstack()
    pb.columns = [EVENTS[i] for i in pb.columns]
    pb.index = persons["wca_id"].to_numpy()[pb.index.to_numpy()]
    return pb.reindex(columns=EVENTS)


def renew(work: Path = WORK_DIR, base_root: Path = BASE_DIR, base_id: str | None = None) -> Path:
    t0 = time.time()
    info = json.loads((work / "ingest.json").read_text())
    export_date = info["export_date"][:10]
    base_id = base_id or export_date
    W = personal_bests(work)
    rater = Rater(W)
    t_fit = time.time() - t0

    rows = []
    for e in EVENTS:
        v = W[e].dropna()
        rows.append(pd.DataFrame({"wca_id": v.index, "event": e, "value": v.to_numpy(),
                                  "rating": rater.rate(e, v.to_numpy())}))
    base_pbs = pd.concat(rows, ignore_index=True)

    meta = {"id": base_id, "export_date": info["export_date"], "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "field_sizes": {e: int(W[e].notna().sum()) for e in EVENTS},
            "common_groups": {e: n for e, (_, _, n) in rater.links.items()},
            "reference_n": int(rater.ref.n), "competitors": int(W.notna().any(axis=1).sum())}
    tables = ConversionTables.build(rater, W, meta={"base": base_id, "export_date": info["export_date"]})

    d = base_root / base_id
    d.mkdir(parents=True, exist_ok=True)
    tables.save(d / "tables.npz")
    (d / "tables.json").write_text(json.dumps(tables.to_json(), separators=(",", ":")))
    base_pbs.to_parquet(d / "base_pbs.parquet", index=False)
    meta["seconds"] = {"fit": round(t_fit, 1), "total": round(time.time() - t0, 1)}
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    (base_root / "ACTIVE").write_text(base_id)
    return d


def active_base(base_root: Path = BASE_DIR) -> Path | None:
    f = base_root / "ACTIVE"
    return base_root / f.read_text().strip() if f.exists() else None
