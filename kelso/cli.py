"""Command line: python -m kelso <command>

  update   check the WCA export; if it is newer than the live database, fetch -> ingest -> build
           (meant for cron, e.g. hourly; costs one ~1 KB request when nothing changed)
  renew    re-estimate the frozen base from the current export (annual, announced in advance)
  ingest   parse the fetched export into data/work (part of update)
  build    rebuild the database from the already ingested export
  serve    run the web server
"""
from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

from .config import CURRENT_DB, DATA, RAW_DIR, WORK_DIR


def _live_export_date():
    if not CURRENT_DB.exists():
        return None
    con = sqlite3.connect(f"file:{CURRENT_DB.resolve()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT value FROM meta WHERE key='export_date'").fetchone()[0]
    finally:
        con.close()


def cmd_update(args):
    from .base import active_base
    from .fetch import export_metadata, fetch_export

    DATA.mkdir(parents=True, exist_ok=True)
    lock = open(DATA / ".update.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another update is running"); return 0
    t0 = time.time()
    meta = export_metadata()
    live = _live_export_date()
    # metadata endpoint says e.g. 2026-10-16T10:16:12Z, the archive's metadata.json 2026-10-16 10:16:12 UTC
    remote = meta["export_date"].replace("T", " ").replace("Z", "")[:19]
    if live and live[:19] >= remote and not args.force:
        print(f"up to date (export {live})"); return 0
    print(f"new export {remote} (live: {live}); fetching")
    try:
        if args.local_zip:
            info = fetch_export(RAW_DIR, local_zip=Path(args.local_zip))
        else:
            info = fetch_export(RAW_DIR, url=meta["tsv_url"])
    except urllib.error.HTTPError as e:
        if e.code == 429:  # the export host rate-limits downloads; the next scheduled run retries
            print("rate limited by the export host (HTTP 429); keeping the current database, retrying next run")
            return 75  # EX_TEMPFAIL
        raise
    print("fetched", json.dumps(info.get("_fetch")))
    # separate processes: each step's peak memory is returned to the OS before the next starts
    _step("ingest")
    if active_base() is None:
        print("no base yet: renewing from this export")
        _step("renew", "--no-build")
    _step("build")
    path = CURRENT_DB.resolve()
    if not args.keep_raw:
        shutil.rmtree(RAW_DIR, ignore_errors=True)
    print(f"published {path.name} in {time.time() - t0:.0f}s")
    return 0


def _step(*argv):
    subprocess.run([sys.executable, "-m", "kelso", *argv], check=True)


def cmd_ingest(args):
    from .ingest import ingest
    print("ingested", ingest(RAW_DIR, WORK_DIR))


def cmd_renew(args):
    from .base import renew
    d = renew(base_id=args.id)
    print("base", d)
    if not args.no_build:
        from .build import build
        print("published", build().name)


def cmd_build(args):
    from .build import build
    print("published", build().name)


def cmd_serve(args):
    import uvicorn
    uvicorn.run("web.app:app", host=args.host, port=args.port, workers=args.workers, proxy_headers=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kelso")
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update")
    u.add_argument("--force", action="store_true", help="rebuild even if the export is not newer")
    u.add_argument("--local-zip", help="use a downloaded export archive instead of fetching")
    u.add_argument("--keep-raw", action="store_true", help="keep the extracted TSVs")
    u.set_defaults(fn=cmd_update)
    r = sub.add_parser("renew")
    r.add_argument("--id", help="base id (default: export date)")
    r.add_argument("--no-build", action="store_true", help="only renew the base")
    r.set_defaults(fn=cmd_renew)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("ingest", help="parse the fetched TSVs into data/work").set_defaults(fn=cmd_ingest)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8040)
    s.add_argument("--workers", type=int, default=1)
    s.set_defaults(fn=cmd_serve)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
