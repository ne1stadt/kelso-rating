"""Kelso web app: server-rendered pages over the published SQLite build + a few JSON endpoints.

Pages are plain HTML (no client framework). JavaScript only adds behaviour: search suggestions,
the history chart, the calculator, live estimates and the cube.
"""
from __future__ import annotations

import contextlib
import hashlib
import threading
import json
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from kelso import live
from kelso.config import EVENT_NAMES, EVENT_SHORT, EVENTS

from . import fmt
from .store import EID, get_store

HERE = Path(__file__).parent
STATIC = HERE / "static"
PAGE = 100

templates = Jinja2Templates(directory=HERE / "templates")
FLAGS = {p.stem for p in (STATIC / "flags").glob("*.svg")}


def _static_version() -> str:
    h = hashlib.sha1()
    for p in sorted((STATIC / "css").glob("*")) + sorted((STATIC / "js").glob("*")):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


STATIC_V = _static_version()
_logo = (STATIC / "img" / "logo.svg").read_text()
LOGO_INNER = _logo[_logo.index(">") + 1: _logo.rindex("</svg>")]   # first paint before cube.js runs
env = templates.env
env.globals.update(EVENTS=EVENTS, EVENT_SHORT=EVENT_SHORT, EVENT_NAMES=EVENT_NAMES, EVENT_META=fmt.EVENT_META,
                   STATIC_V=STATIC_V, FLAGS=FLAGS, LOGO_INNER=LOGO_INNER)
env.filters.update(result=lambda raw, e: fmt.fmt_result(e, raw), rating=fmt.rating, delta=fmt.delta,
                   top_share=fmt.top_share, ev=lambda i: EVENTS[i], tojson_compact=lambda v: json.dumps(v, separators=(",", ":")))


def render(request, name, ctx, cache=300, status=200):
    s = get_store()
    ctx.update(request=request, meta=s.meta, stats=s.meta["stats"], countries=s.countries, continents=s.continents)
    r = templates.TemplateResponse(request, name, ctx, status_code=status)
    if cache:
        r.headers["Cache-Control"] = f"public, max-age={cache}"
    return r


def _int(v, default, lo=1, hi=10**9):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _region(s, region: str):
    """'' = world, '_Europe' = continent, 'PL' = country (by iso2). Returns (kind, id, label)."""
    if region in s.continents:
        return "continent", region, s.continents[region]["name"]
    cid = s.iso2_to_country.get(region.upper()) if region else None
    if cid:
        return "country", cid, s.countries[cid]["name"]
    return "world", None, "World"


# ====================================================================== pages
async def rankings(request: Request):
    s = get_store()
    qp = request.query_params
    event = qp.get("event", "")
    event = event if event in EID else ""
    kind, rid, label = _region(s, qp.get("region", ""))
    page = _int(qp.get("page"), 1)
    off = (page - 1) * PAGE
    if not event:
        where, col, args = {"world": ("overall IS NOT NULL", "rank_world", ()),
                            "continent": ("continent_id = ?", "rank_continent", (rid,)),
                            "country": ("country_id = ?", "rank_country", (rid,))}[kind]
        total = s.one(f"SELECT COUNT(*) FROM persons WHERE {where} AND overall IS NOT NULL", *args)[0]
        rows = [dict(r) for r in s.q(f"""SELECT pk, wca_id, name, country_id, overall, n_events, best_event, best_rating,
                       {col} AS rank FROM persons WHERE {where} AND overall IS NOT NULL ORDER BY {col}, pk LIMIT ? OFFSET ?""",
                                     *args, PAGE, off)]
        if rows:
            evs = s.q(f"SELECT ppk, eid, rating FROM event_ratings WHERE ppk IN ({','.join('?' * len(rows))})",
                      *[r["pk"] for r in rows])
            by = {}
            for e in evs:
                by.setdefault(e["ppk"], []).append((e["eid"], e["rating"]))
            for r in rows:
                es = by.get(r["pk"], [])
                tot = sum(10 ** (x / 400) for _, x in es) or 1
                r["events"] = sorted([{"e": EVENTS[i], "r": x, "share": 10 ** (x / 400) / tot} for i, x in es],
                                     key=lambda d: EID[d["e"]])
    else:
        eid = EID[event]
        where, col, args = {"world": ("e.eid = ?", "e.rank_world", (eid,)),
                            "continent": ("e.eid = ? AND e.continent_id = ?", "e.rank_continent", (eid, rid)),
                            "country": ("e.eid = ? AND e.country_id = ?", "e.rank_country", (eid, rid))}[kind]
        total = s.one(f"SELECT COUNT(*) FROM event_ratings e WHERE {where}", *args)[0]
        rows = [dict(r) for r in s.q(f"""SELECT p.wca_id, p.name, p.country_id, e.raw, e.rating, {col} AS rank,
                       c.id AS comp_id, c.name AS comp_name FROM event_ratings e JOIN persons p ON p.pk = e.ppk
                       LEFT JOIN competitions c ON c.pk = e.cpk WHERE {where} ORDER BY {col}, e.ppk LIMIT ? OFFSET ?""",
                                     *args, PAGE, off)]
    pages = max(1, math.ceil(total / PAGE))
    regions = {"continents": sorted(s.continents.values(), key=lambda c: c["name"]),
               "countries": sorted((c for c in s.countries.values() if c["iso2"] and not c["id"].startswith("X")),
                                   key=lambda c: c["name"])}
    return render(request, "rankings.html", dict(rows=rows, event=event, region=qp.get("region", ""), region_label=label,
                                                 region_kind=kind, page=page, pages=pages, total=total, regions=regions))


async def person(request: Request):
    s = get_store()
    wca_id = request.path_params["wca_id"].upper()
    p = s.one("SELECT * FROM persons WHERE wca_id = ?", wca_id)
    if p is None:
        raise HTTPException(404, "No competitor with this WCA ID")
    p = dict(p)
    evs = [dict(r) for r in s.q("""SELECT e.*, c.id AS comp_id, c.name AS comp_name, c.end_date FROM event_ratings e
                                   LEFT JOIN competitions c ON c.pk = e.cpk WHERE e.ppk = ? ORDER BY e.eid""", p["pk"])]
    tot = sum(10 ** (e["rating"] / 400) for e in evs) or 1
    for e in evs:
        e["event"] = EVENTS[e["eid"]]
        e["share"] = 10 ** (e["rating"] / 400) / tot
    part = [dict(r) for r in s.q("""SELECT pa.seq, pa.before, pa.after, pa.n_improved, c.id, c.name, c.end_date, c.country_id
                                    FROM participation pa JOIN competitions c ON c.pk = pa.cpk
                                    WHERE pa.ppk = ? ORDER BY pa.seq""", p["pk"])]
    hist = s.q("""SELECT h.eid, h.raw, h.rating, h.prev_rating, c.id AS comp_id, c.end_date FROM pb_history h
                  JOIN competitions c ON c.pk = h.cpk WHERE h.ppk = ? ORDER BY c.end_date""", p["pk"])
    improved = {}
    series = {"overall": [[c["end_date"], round(c["after"], 1), c["id"]] for c in part
                          if c["after"] is not None and (c["n_improved"] or 0) > 0]}
    for h in hist:
        e = EVENTS[h["eid"]]
        improved.setdefault(h["comp_id"], []).append({"e": e, "raw": h["raw"], "r": h["rating"], "prev": h["prev_rating"]})
        series.setdefault(e, []).append([h["end_date"], round(h["rating"], 1), h["comp_id"]])
    comp_names = {c["id"]: c["name"] for c in part}
    stats = s.meta["stats"]
    ctx = dict(p=p, evs=evs, comps=list(reversed(part)), improved=improved,
               chart={"series": series, "names": comp_names},
               best=max(evs, key=lambda e: e["rating"]) if evs else None,
               top=(p["rank_world"] / stats["rated"]) if p["rank_world"] else None,
               country=s.countries.get(p["country_id"]), continent=s.continents.get(p["continent_id"]))
    return render(request, "person.html", ctx)


async def search(request: Request):
    q = request.query_params.get("q", "").strip()
    rows = _search(q, 100) if q else []
    if len(rows) == 1:
        return RedirectResponse(f"/persons/{rows[0]['wca_id']}", status_code=302)
    return render(request, "search.html", dict(q=q, rows=rows), cache=60)


def _search(q: str, limit: int):
    s = get_store()
    q = q.strip()
    if not q:
        return []
    cols = "p.wca_id, p.name, p.country_id, p.overall, p.rank_world"
    exact = s.q(f"SELECT {cols} FROM persons p WHERE p.wca_id = ?", q.upper())
    if exact:
        return [dict(r) for r in exact]
    if len(q) >= 4 and q[:4].isdigit():   # WCA ID prefix
        return [dict(r) for r in s.q(f"SELECT {cols} FROM persons p WHERE p.wca_id LIKE ? ORDER BY p.wca_id LIMIT ?",
                                     q.upper() + "%", limit)]
    terms = [t for t in "".join(ch if ch.isalnum() else " " for ch in q).split() if t]
    if not terms:
        return []
    match = " ".join(f'"{t}"*' for t in terms)
    rows = s.q(f"""SELECT {cols} FROM person_fts f JOIN persons p ON p.pk = f.rowid WHERE person_fts MATCH ?
                   ORDER BY p.overall IS NULL, p.rank_world LIMIT ?""", match, limit)
    return [dict(r) for r in rows]


async def competitions(request: Request):
    s = get_store()
    page = _int(request.query_params.get("page"), 1)
    recent = [dict(r) for r in s.q("""SELECT id, name, city, country_id, start_date, end_date, competitors, n_improved, sum_gain
                                      FROM competitions WHERE competitors > 0 ORDER BY end_date DESC, id LIMIT ? OFFSET ?""",
                                   50, (page - 1) * 50)]
    # live / pending lists come from the WCA API and load asynchronously (/api/competitions/live),
    # so this page never waits on an upstream service
    return render(request, "competitions.html", dict(recent=recent, page=page), cache=60)


async def competition(request: Request):
    s = get_store()
    cid = request.path_params["comp_id"]
    c = s.one("SELECT * FROM competitions WHERE id = ? AND competitors > 0", cid)
    if c is None:
        return render(request, "competition_live.html", dict(comp_id=cid), cache=30)
    c = dict(c)
    sort = request.query_params.get("sort", "gain")
    rows = [dict(r) for r in s.q("""SELECT p.wca_id, p.name, p.country_id, pa.before, pa.after, pa.n_improved, pa.ppk
                                    FROM participation pa JOIN persons p ON p.pk = pa.ppk WHERE pa.cpk = ?""", c["pk"])]
    ch = {}
    for h in s.q("SELECT ppk, eid, raw, rating, prev_rating FROM pb_history WHERE cpk = ? ORDER BY eid", c["pk"]):
        ch.setdefault(h["ppk"], []).append({"e": EVENTS[h["eid"]], "raw": h["raw"], "r": h["rating"], "prev": h["prev_rating"]})
    for r in rows:
        r["changes"] = ch.get(r["ppk"], [])
        r["gain"] = (r["after"] or 0) - (r["before"] or 0) if r["after"] is not None else 0
        r["new"] = r["before"] is None and r["after"] is not None
    key = {"gain": lambda r: (-r["gain"], r["name"]), "after": lambda r: (-(r["after"] or -1), r["name"]),
           "name": lambda r: r["name"]}.get(sort, lambda r: (-r["gain"], r["name"]))
    rows.sort(key=key)
    return render(request, "competition.html", dict(c=c, rows=rows, sort=sort,
                                                    n_new=sum(r["new"] for r in rows),
                                                    n_up=sum(1 for r in rows if r["gain"] > 0.5 and not r["new"])))


async def calculator(request: Request):
    return render(request, "calculator.html", {})


async def about(request: Request):
    s = get_store()
    st = s.meta["stats"]
    ceilings = sorted(({"e": e, "n": st["events"][e]["n"], "median": st["events"][e]["median"], "max": st["events"][e]["max"],
                        "rank": s.rank_of(st["events"][e]["max"])["rank"]} for e in EVENTS),
                      key=lambda r: -r["max"])
    timings = json.loads(s.meta.get("timings", "{}"))
    return render(request, "about.html", dict(ceilings=ceilings, timings=timings, base=s.meta["base"]))


# ====================================================================== JSON API
async def api_search(request: Request):
    rows = _search(request.query_params.get("q", ""), 8)
    s = get_store()
    for r in rows:
        r["iso2"] = (s.countries.get(r["country_id"]) or {}).get("iso2")
    return JSONResponse(rows, headers={"Cache-Control": "public, max-age=300"})


async def api_person(request: Request):
    s = get_store()
    wca_id = request.path_params["wca_id"].upper()
    p = s.one("SELECT pk, wca_id, name, country_id, overall, rank_world FROM persons WHERE wca_id = ?", wca_id)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    evs = s.q("SELECT eid, raw, rating FROM event_ratings WHERE ppk = ?", p["pk"])
    d = dict(p)
    d.pop("pk")
    d["events"] = {EVENTS[e["eid"]]: {"raw": e["raw"], "rating": e["rating"]} for e in evs}
    return JSONResponse(d, headers={"Cache-Control": "public, max-age=300"})


async def api_rank(request: Request):
    try:
        r = float(request.query_params["r"])
        if not math.isfinite(r):
            raise ValueError
    except (KeyError, ValueError):
        return JSONResponse({"error": "r required"}, status_code=400)
    return JSONResponse(get_store().rank_of(r), headers={"Cache-Control": "public, max-age=300"})


async def api_tables(request: Request):
    s = get_store()
    etag = '"' + s.meta["base_id"] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return FileResponse(s.tables_json_path, media_type="application/json",
                        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"})


def api_comp_lists(request: Request):
    try:
        lists = live.competition_lists(get_store().comp_ids)
    except Exception as exc:
        return JSONResponse({"error": f"WCA API unavailable ({exc})"}, status_code=502)
    return JSONResponse(lists, headers={"Cache-Control": "public, max-age=60"})


def api_live(request: Request):
    s = get_store()
    cid = request.path_params["comp_id"]
    if cid in s.comp_ids:
        return JSONResponse({"official": True, "id": cid})
    try:
        lists = live.competition_lists(s.comp_ids)
    except Exception:
        lists = {"ongoing": [], "pending": []}
    info = next((c for c in lists["ongoing"] if c["id"] == cid), None)
    ongoing = info is not None
    info = info or next((c for c in lists["pending"] if c["id"] == cid), None)
    try:
        wcif, ts = live.fetch_wcif(cid, ongoing=ongoing)
    except Exception as exc:
        return JSONResponse({"error": f"could not load competition from the WCA ({exc})"}, status_code=502)
    rows = live.estimate(wcif, s)
    for r in rows:
        r["rank_after"] = s.rank_of(r["after"])["rank"] if r["after"] is not None else None
    return JSONResponse({"official": False, "id": cid, "name": wcif["name"], "ongoing": ongoing, "info": info,
                         "fetched_at": datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds"),
                         "ttl": live.LIVE_TTL_ONGOING if ongoing else live.LIVE_TTL_PENDING,
                         "competitors": len(wcif["persons"]), "rows": rows},
                        headers={"Cache-Control": "public, max-age=30"})


async def not_found(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    try:
        return render(request, "error.html", dict(code=exc.status_code, detail=exc.detail), cache=0, status=exc.status_code)
    except FileNotFoundError:
        return Response(exc.detail, status_code=exc.status_code)


async def server_error(request: Request, exc: Exception):
    if isinstance(exc, FileNotFoundError):
        return Response("No rating database is published yet. Run: python -m kelso update", status_code=503)
    raise exc


routes = [
    Route("/", rankings),
    Route("/persons/{wca_id}", person),
    Route("/search", search),
    Route("/competitions", competitions),
    Route("/competitions/{comp_id}", competition),
    Route("/calculator", calculator),
    Route("/about", about),
    Route("/api/search", api_search),
    Route("/api/persons/{wca_id}", api_person),
    Route("/api/rank", api_rank),
    Route("/api/tables", api_tables),
    Route("/api/competitions/live", api_comp_lists),
    Route("/api/live/{comp_id}", api_live),
    Route("/favicon.ico", lambda r: RedirectResponse(f"/static/img/logo.svg", status_code=301)),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]

@contextlib.asynccontextmanager
async def lifespan(app):
    """Fill the competition-list cache in the background so the first visitor does not wait."""
    def warm():
        try:
            live.competition_lists(get_store().comp_ids)
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()
    yield


class StaticCache:
    """Versioned static URLs (?v=<hash of css/js>) are immutable; everything else gets an hour."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/static/"):
            return await self.app(scope, receive, send)
        versioned = b"v=" in scope.get("query_string", b"")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                headers.append((b"cache-control", b"public, max-age=31536000, immutable" if versioned else b"public, max-age=3600"))
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, send_wrapper)


app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(GZipMiddleware, minimum_size=1000), Middleware(StaticCache)],
                exception_handlers={HTTPException: not_found, 404: not_found, FileNotFoundError: server_error})
