"""Parse the export TSVs into the slim tables the rest of the pipeline uses.

results.tsv (6.9 M rows, ~670 MB) is reduced to one row per competitor x competition x event
holding the best single and the best average of that competition. Nothing downstream needs
rounds or attempts: the rating is a function of personal bests, and a personal-best history at
competition granularity is what the person and competition pages show.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from .config import EVENTS, RAW_DIR, WORK_DIR


def _read_tsv(path: Path, columns, types=None):
    return pacsv.read_csv(
        path,
        parse_options=pacsv.ParseOptions(delimiter="\t", quote_char=False, newlines_in_values=False),
        convert_options=pacsv.ConvertOptions(include_columns=columns, column_types=types or {},
                                             null_values=["NULL"], strings_can_be_null=True),
        read_options=pacsv.ReadOptions(block_size=2 << 20),
    )


def ingest(src: Path = RAW_DIR, out: Path = WORK_DIR) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((src / "metadata.json").read_text())

    # --- countries / continents ------------------------------------------------------------
    countries = _read_tsv(src / "WCA_export_countries.tsv", ["id", "iso2", "name", "continent_id"]).to_pandas()
    continents = _read_tsv(src / "WCA_export_continents.tsv", ["id", "name"]).to_pandas()
    countries.to_parquet(out / "countries.parquet", index=False)
    continents.to_parquet(out / "continents.parquet", index=False)

    # --- persons: sub_id 1 is the current name and country ----------------------------------
    p = _read_tsv(src / "WCA_export_persons.tsv", ["wca_id", "sub_id", "name", "country_id"],
                  {"sub_id": pa.int32()}).to_pandas()
    p = p[p.sub_id == 1].drop(columns="sub_id").drop_duplicates("wca_id").reset_index(drop=True)
    p.to_parquet(out / "persons.parquet", index=False)

    # --- competitions ---------------------------------------------------------------------
    c = _read_tsv(src / "WCA_export_competitions.tsv",
                  ["id", "name", "cell_name", "city_name", "country_id", "cancelled", "event_specs",
                   "year", "month", "day", "end_year", "end_month", "end_day"]).to_pandas()
    c["start_date"] = pd.to_datetime(dict(year=c.year, month=c.month, day=c.day), errors="coerce")
    c["end_date"] = pd.to_datetime(dict(year=c.end_year, month=c.end_month, day=c.end_day), errors="coerce")
    c["end_date"] = c["end_date"].fillna(c["start_date"])
    c = c.drop(columns=["year", "month", "day", "end_year", "end_month", "end_day"])
    c["cancelled"] = c["cancelled"].astype(str) == "1"
    c = c.reset_index(drop=True)

    # --- results -> best single / best average per person x competition x event -------------
    # Streamed in blocks; every string id is replaced by its integer position in the persons /
    # competitions / events lists straight away, so only compact int arrays are ever held
    # (peak memory ~0.5 GB instead of ~3 GB for a whole-table read).
    pid_set = pa.array(p["wca_id"].to_numpy(dtype=object))
    cid_set = pa.array(c["id"].to_numpy(dtype=object))
    eid_set = pa.array(EVENTS)
    reader = pacsv.open_csv(
        src / "WCA_export_results.tsv",
        read_options=pacsv.ReadOptions(block_size=2 << 20, use_threads=False),
        parse_options=pacsv.ParseOptions(delimiter="\t", quote_char=False),
        convert_options=pacsv.ConvertOptions(
            include_columns=["competition_id", "event_id", "person_id", "best", "average"],
            column_types={"best": pa.int32(), "average": pa.int32(), "competition_id": pa.string(),
                          "event_id": pa.string(), "person_id": pa.string()}))
    parts, n_rows = [], 0
    for batch in reader:
        n_rows += batch.num_rows
        ev = pc.index_in(batch.column("event_id"), value_set=eid_set)
        keep = pc.is_valid(ev)
        b = pa.Table.from_batches([batch]).filter(keep)
        parts.append((
            pc.index_in(b["person_id"], value_set=pid_set).to_numpy(zero_copy_only=False),
            pc.index_in(b["competition_id"], value_set=cid_set).to_numpy(zero_copy_only=False),
            pc.filter(ev, keep).to_numpy(zero_copy_only=False),
            b["best"].to_numpy(), b["average"].to_numpy()))
    pid, cid, eid, single, average = (np.concatenate([x[i] for x in parts]) for i in range(5))
    del parts
    pid, cid, eid = pid.astype(np.int64), cid.astype(np.int64), eid.astype(np.int64)

    # competitor counts per competition (everyone with a result row, valid or not)
    pairs = np.unique((cid << 20) | pid)
    c["competitors"] = np.bincount(pairs >> 20, minlength=len(c))[: len(c)]
    c.to_parquet(out / "competitions.parquet", index=False)
    del pairs

    # min over rounds per (person, competition, event) by sort + reduceat on one packed key;
    # this needs a few int arrays instead of a pandas groupby's ~1 GB of intermediates
    BIG = np.iinfo(np.int32).max
    single = np.where(single > 0, single, BIG)          # DNF -1, DNS -2, no result 0
    average = np.where(average > 0, average, BIG)
    key = (pid << 25) | (cid << 5) | eid
    del pid, cid, eid
    order = np.argsort(key, kind="stable")
    key = key[order]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    s_min = np.minimum.reduceat(single[order], starts)
    a_min = np.minimum.reduceat(average[order], starts)
    k = key[starts]
    del order, key, single, average
    ok = (s_min < BIG) | (a_min < BIG)
    k, s_min, a_min = k[ok], s_min[ok], a_min[ok]
    g = pd.DataFrame({"pid": (k >> 25).astype(np.int32), "cid": ((k >> 5) & 0xFFFFF).astype(np.int32),
                      "eid": (k & 0x1F).astype(np.int8),
                      "single": np.where(s_min < BIG, s_min, 0).astype(np.int32),   # 0 = no valid result
                      "average": np.where(a_min < BIG, a_min, 0).astype(np.int32)})
    g.to_parquet(out / "results.parquet", index=False)   # ids are positions in persons/competitions/EVENTS

    info = {"export_date": meta["export_date"], "export_format_version": meta["export_format_version"],
            "result_rows": n_rows, "person_comp_event_rows": int(len(g)), "persons": int(len(p)),
            "competitions": int(len(c))}
    (out / "ingest.json").write_text(json.dumps(info, indent=1))
    return info
