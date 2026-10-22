"""Display formatting shared by templates (mirrored in static/js/kelso.js for the browser)."""
from __future__ import annotations

from kelso.config import EVENT_NAMES, EVENT_SHORT, EVENTS


def fmt_time(cs: int) -> str:
    if cs is None or cs <= 0:
        return ""
    s, c = divmod(int(cs), 100)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}.{c:02d}"
    if m:
        return f"{m}:{s:02d}.{c:02d}"
    return f"{s}.{c:02d}"


def fmt_mbf(v: int) -> str:
    v = int(v)
    dd, tt, mm = v // 10_000_000, (v // 100) % 100_000, v % 100
    solved = 99 - dd + mm
    attempted = solved + mm
    t = f"{tt // 60}:{tt % 60:02d}" if tt < 3600 else f"{tt // 3600}:{tt % 3600 // 60:02d}:{tt % 60:02d}"
    return f"{solved}/{attempted} {t}"


def fmt_result(event, raw) -> str:
    """raw is the WCA encoding of the value that enters the rating (average or single per event)."""
    if raw is None or raw <= 0:
        return ""
    if event in ("333mbf", 13):
        return fmt_mbf(raw)
    if event == "333fm":
        return f"{raw / 100:.2f}"   # FMC enters by mean of 3, stored x100
    return fmt_time(raw)


def rating(x) -> str:
    return "" if x is None else f"{x:.0f}"


def delta(x) -> str:
    if x is None:
        return ""
    r = round(x)
    return f"+{r}" if r > 0 else ("±0" if r == 0 else f"−{abs(r)}")


def top_share(share: float) -> str:
    p = share * 100
    if p < 0.01:
        return "top 0.01%"
    if p < 1:
        return f"top {p:.2f}%"
    if p < 10:
        return f"top {p:.1f}%"
    return f"top {p:.0f}%"


EVENT_META = [{"id": e, "short": EVENT_SHORT[e], "name": EVENT_NAMES[e]} for e in EVENTS]
