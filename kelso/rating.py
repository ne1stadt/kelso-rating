"""The rating itself: event ratings by kernel-smoothed equipercentile linking, aggregated by log-sum-exp.

KCDF, Rater, elo_from_q, lse and mbf_value are ported unchanged in behaviour from the
paper's supplement (code/core.py), so that a base built here reproduces the paper's numbers.
Additions for the site:

* Rater.q_new: rating of a result that is *not* a member of the base field (Section 3.1/3.4).
  For linked events it equals Rater.q; for the anchor it uses the new-member formula.
* ConversionTables: the frozen base reduced to one monotone lookup table per event
  (log result -> rating). Every result that is not a base personal best is rated through these
  tables -- on the server, in the nightly build, and in the browser calculator -- so all three
  agree to the last point.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr
from scipy.stats import norm

from .config import ANCHOR, EVENTS, FLOOR, K, MEDIAN_RATING, SINGLE_EVENTS, TABLE_POINTS, UNIT


def mbf_value(v):
    """MBLD result code -> 1/m with m = points + unused share of the hour (Section 2)."""
    v = np.asarray(v, dtype="int64")
    dd = v // 10_000_000
    tt = (v // 100) % 100_000
    return 1.0 / np.maximum((99 - dd) + (3600 - np.minimum(tt, 3600)) / 3600.0, 0.25)


def result_value(event: str, single, average):
    """The value that enters the rating for one round result, or NaN if it does not count.

    Averages for most events, best single for the blindfolded events and MBLD.
    """
    single = np.asarray(single, dtype="int64")
    average = np.asarray(average, dtype="int64")
    if event == "333mbf":
        return np.where(single > 0, mbf_value(np.where(single > 0, single, 0)), np.nan)
    col = single if event in SINGLE_EVENTS else average
    return np.where(col > 0, col.astype(float), np.nan)


class KCDF:
    """Kernel-continuized CDF of log values on a grid (paper eq. 2)."""

    def __init__(self, vals, hmult=1.0, G=8192):
        z = np.log(np.asarray(vals, float))
        n = len(z)
        mu = z.mean()
        sd = z.std()
        iqr = np.subtract(*np.percentile(z, [75, 25]))
        h = hmult * 0.9 * min(sd, iqr / 1.34) * n ** (-0.2)
        a = np.sqrt(sd ** 2 / (sd ** 2 + h ** 2))
        zz = a * z + (1 - a) * mu
        s = a * h
        lo, hi = zz.min() - 8 * s, zz.max() + 8 * s
        grid = np.linspace(lo, hi, G)
        dx = grid[1] - grid[0]
        hist = np.bincount(np.clip(np.round((zz - lo) / dx).astype(int), 0, G - 1), minlength=G).astype(float) / n
        k = np.arange(-int(8 * s / dx) - 1, int(8 * s / dx) + 2) * dx
        pdf = np.convolve(hist, norm.pdf(k, scale=s) * dx, mode="same")
        cdf = np.cumsum(pdf)
        cdf = cdf / cdf[-1]
        self.grid, self.cdf, self.h, self.n = grid, np.maximum.accumulate(cdf), h, n
        self.zz, self.s = zz, s

    def F(self, v):
        z = np.log(np.asarray(v, float))
        return np.interp(z, self.grid, self.cdf, left=0.0, right=1.0)

    def tail_F(self, v):
        """Exact continuized CDF for a few values (used for extreme results)."""
        z = np.log(np.atleast_1d(np.asarray(v, float)))
        out = np.empty(len(z))
        step = max(1, (8 << 20) // max(len(self.zz), 1))  # ~64 MB of temporaries per chunk
        for i in range(0, len(z), step):
            out[i:i + step] = ndtr((z[i:i + step, None] - self.zz[None, :]) / self.s).mean(axis=1)
        return out

    def Q(self, u):
        u = np.asarray(u, float)
        return np.exp(np.interp(u, self.cdf, self.grid))


def elo_from_q(q, floor=True):
    q = np.clip(q, 1e-12, 1 - 1e-12)
    r = MEDIAN_RATING + UNIT * np.log10(q / (1 - q))
    return np.maximum(FLOOR, r) if floor else r


class Rater:
    """Fits the reference field and the 16 linkings from a personal-best matrix W (persons x events)."""

    def __init__(self, W, anchor=ANCHOR, hmult=1.0):
        self.a = anchor
        self.ref = KCDF(W[anchor].dropna().values, hmult)
        self.links = {}
        for e in EVENTS:
            if e == anchor or e not in W:
                continue
            g = W[[e, anchor]].dropna()
            self.links[e] = (KCDF(g[e].values, hmult), KCDF(g[anchor].values, hmult), len(g))

    def faster_share_ref(self, t):
        t = np.atleast_1d(np.asarray(t, float))
        F = np.atleast_1d(self.ref.F(t))
        ext = F < 1e-4  # use exact kernel sum in the extreme fast tail
        if ext.any():
            F = F.copy()
            F[ext] = self.ref.tail_F(t[ext])
        return F

    def q(self, e, x):
        """Share of the reference field beaten by x; base members of the anchor field half-tie themselves."""
        x = np.atleast_1d(np.asarray(x, float))
        if e == self.a:
            return 1 - self.faster_share_ref(x)
        Fe, F3, n = self.links[e]
        u = np.atleast_1d(Fe.F(x))
        ext = u < 1e-3
        if ext.any():
            u = u.copy()
            u[ext] = Fe.tail_F(x[ext])
        t3 = F3.Q(u)
        N = self.ref.n  # the 3x3 equivalent is a new member of the reference field
        return 1 - (N * self.faster_share_ref(t3) + 0.5) / (N + 1)

    def q_new(self, e, x):
        """Share beaten by a result that is not in the base field (new member, Section 3.1)."""
        if e != self.a:
            return self.q(e, x)
        N = self.ref.n
        return 1 - (N * self.faster_share_ref(x) + 0.5) / (N + 1)

    def rate(self, e, x, floor=True):
        return elo_from_q(self.q(e, x), floor)

    def rate_new(self, e, x, floor=True):
        return elo_from_q(self.q_new(e, x), floor)


def lse(R, k=K):
    """Overall rating: k*log10(sum 10^(R_e/k)) over the entered events (NaN = not entered)."""
    M = np.asarray(R, float)
    M = np.where(np.isnan(M), -np.inf, M)
    m = np.max(M, axis=-1, keepdims=True)
    return m[..., 0] + k * np.log10(np.sum(10 ** ((M - m) / k), axis=-1))


def odds(R):
    """Contribution of an event rating to the overall sum (eq. 5 up to the constant 10^3)."""
    return 10.0 ** (np.asarray(R, float) / K)


def overall_from_odds(S):
    return K * np.log10(S)


@dataclass
class ConversionTables:
    """Per-event monotone map log(result) -> rating for results outside the base field.

    Knots are increasing log results; ratings are linearly interpolated between them. Beyond the
    fast end the rating is clamped (the event ceiling); beyond the slow end it is the floor.
    """
    xs: dict          # event -> increasing log results (knots)
    ratings: dict     # event -> rating at each knot (non-increasing)
    meta: dict

    @classmethod
    def build(cls, rater: Rater, W, points=TABLE_POINTS, meta=None):
        """Knots are placed at equal arc length of the exact curve (log result vs rating), so they
        crowd where the rating changes fastest -- the fast tail, where the paper's rule switches
        to the exact kernel sum and the curve is steep."""
        xs, ratings = {}, {}
        for e in EVENTS:
            v = W[e].dropna().values
            # from 70% of the world record to well past the slowest result: covers every
            # result that will plausibly appear before the next renewal
            a, b = np.log(v.min() * 0.7), np.log(v.max() * 1.5)
            dense = np.linspace(a, b, 6 * points)
            r = rater.rate_new(e, np.exp(dense))
            r = np.maximum.accumulate(r[::-1])[::-1]  # enforce monotone (rounding noise)
            seg = np.hypot(np.diff(dense) / (b - a), np.diff(r) / max(np.ptp(r), 1.0))
            arc = np.r_[0.0, np.cumsum(seg)]
            idx = np.unique(np.searchsorted(arc, np.linspace(0, arc[-1], points)).clip(0, len(dense) - 1))
            idx = np.unique(np.r_[0, idx, len(dense) - 1])
            xs[e], ratings[e] = dense[idx], r[idx]
        return cls(xs, ratings, meta or {})

    def rate(self, e, x):
        x = np.atleast_1d(np.asarray(x, float))
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.interp(np.log(x), self.xs[e], self.ratings[e])  # clamps at both ends
        out[~(x > 0)] = np.nan
        return out

    # --- persistence -------------------------------------------------------------------
    def save(self, path):
        np.savez_compressed(path, **{f"r_{e}": self.ratings[e] for e in EVENTS},
                            **{f"x_{e}": self.xs[e] for e in EVENTS},
                            meta=np.array(json.dumps(self.meta)))

    @classmethod
    def load(cls, path):
        z = np.load(path)
        return cls({e: z[f"x_{e}"] for e in EVENTS}, {e: z[f"r_{e}"] for e in EVENTS}, json.loads(str(z["meta"])))

    def to_json(self):
        """Compact form shipped to the browser calculator (ratings rounded to 0.1)."""
        return {
            "meta": self.meta,
            "events": {e: {"x": [round(float(v), 5) for v in self.xs[e]],
                           "r": [round(float(v), 2) for v in self.ratings[e]]} for e in EVENTS},
        }
