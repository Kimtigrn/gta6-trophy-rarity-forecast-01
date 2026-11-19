"""gta6-trophy-rarity-forecast-01 entry: forecast each GTA VI PS5 trophy's
Exophase earn rate at the case target, as five quantiles per trophy.

Method (one paragraph): Exophase's page only moves when Exophase refreshes it,
so a case's history is a staircase: long flat stretches, then jumps in both
the players-tracked count N and every trophy's earn rate. A rate's trajectory
is therefore a race between players earning the trophy (which pushes the rate
up toward the share of players who will ever earn it) and new players joining
(which dilutes it). The dynamic model forecasts each trophy's rate at the
target as the average, in logit space, of two extrapolators fitted on the
history's distinct snapshots (consecutive identical reads carry no
information; reads before the launch are a different cohort and are excluded
from the fits): (A) a recency-weighted least-squares line of logit(rate)
against x = ln(1 + hours since the 2026-11-19T00:00Z launch), its slope
shrunk toward the cross-trophy median slope -- the house curve baseline's
shape, but fitted on all snapshots with a 24-hour half-life instead of only
the last 24 hours; (B) a maturity curve rate(t) = R * (1 - exp(-t/tau)),
fitted per trophy by a grid search over tau with R by weighted least squares,
which respects that a trophy's rate saturates as the player base matures
instead of growing forever on a log scale. The spread is the honest
combination of the curve fit's residual scatter, its slope uncertainty scaled
by how far the target sits past the fitted data, the disagreement between the
two extrapolators, and a base term for refresh timing (the page at the target
is whatever Exophase last refreshed before it). When the history is flat
(fewer than 3 distinct snapshots -- the launch-night practice cases), no
trend exists to fit, so the forecast falls back to the first-refresh prior:
the page's first refresh took players 638 -> 3,868 and trophies earned
943 -> 4,276, i.e. the newly tracked players held about one trophy each (the
opening mission's) and almost nothing else, so every rate but the one at 100%
fell to ~0.22x its pre-refresh value; the fallback median is 0.22 * last rate
(a trophy at 100% stays at 100%) with a wide spread.

Python 3.13, standard library only, no network, deterministic, fast.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# finds a model.py shipped beside this file (we ship none; kept for safety).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Launch: GTA VI released 2026-11-19; the house clock starts at 00:00Z.
RELEASE = "2026-11-19T00:00:00Z"

# Fallback (flat history): first-refresh dilution factor for rates, from the
# house's own numbers -- players 638 -> 3,868, trophies earned 943 -> 4,276:
# non-100% trophies' earners grew 305 -> 408 while players grew 6.06x, so a
# rate falls to (408/305) / (3868/638) = 0.2207 of its pre-refresh value.
DILUTE = 0.2207
# Fallback spread (logit units): a refresh we have not seen is uncertain, but
# the first refresh's totals pin the dilution well (see module docstring), so
# 0.6 covers the per-trophy allocation error without paying for width.
FALLBACK_SPREAD = 0.6
# Base spread for the dynamic model (refresh timing + structural error).
BASE_SPREAD = 0.35
# Regime risk: the player mix can change after the cut (a weekend surge of
# new players dilutes rates; a growth stall lifts them). It grows with the
# horizon, in logit units per sqrt(day).
REGIME_SPREAD = 0.15
# Ensemble weights for the dynamic model: the maturity curve respects
# saturation (a rate cannot grow on a log scale forever), so it carries more
# weight than the logit-linear trend, which overshoots saturating rates.
W_CURVE = 0.2
W_MATURITY = 0.6
# Persistence hedge: the post-cut player mix can change (a weekend surge of
# new players dilutes rates; a growth stall lifts them), and no trend fitted
# before the cut can see it. The ensemble median therefore keeps a weight on
# the no-change forecast (the last read's rate) instead of trusting the
# extrapolation fully.
PERSIST_WEIGHT = 0.2
# Spread clamps (logit units).
SPREAD_MIN = 0.25
SPREAD_MAX = 2.0


def parse_time(s: str) -> float:
    """ISO 8601 UTC timestamp -> epoch seconds (handles fractional seconds)."""
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def clamp(x: float, lo: float = 0.01, hi: float = 99.99) -> float:
    return min(hi, max(lo, x))


def logit(pct: float) -> float:
    p = clamp(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg: float) -> float:
    if lg >= 0:
        return 100.0 / (1.0 + math.exp(-lg))
    e = math.exp(lg)
    return 100.0 * e / (1.0 + e)


def round4(x: float) -> float | int:
    """Round to 4 decimals, half up, as JavaScript Math.round does it."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value == int(value) else value


def median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def distinct_snapshots(case):
    """History collapsed to distinct pages: (epoch, players, [rates]).

    Consecutive reads with the same players-tracked and the same rates are one
    snapshot; a read is skipped when its players count is missing/zero.
    """
    snaps = []
    prev = None
    for read in case.get("history") or []:
        n = read.get("players_tracked")
        rates = read.get("rates")
        if not n or n <= 0 or rates is None:
            continue
        key = (n, tuple(rates))
        if key == prev:
            continue
        prev = key
        try:
            t = parse_time(read.get("at") or read.get("slot"))
        except (ValueError, TypeError):
            continue
        snaps.append((t, float(n), list(rates)))
    return snaps


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    trophies = case["trophies"]
    n_tr = len(trophies)
    release = parse_time(case.get("game", {}).get("release_date", "2026-11-19") + "T00:00:00Z")
    target = parse_time(case["target"])

    def x_of(t):
        return math.log1p(max(0.0, (t - release) / 3600.0))

    def t_of(t):
        return (t - release) / 3600.0

    x_t = x_of(target)
    t_t = t_of(target)
    snaps = distinct_snapshots(case)

    # Last non-null rate per trophy (fallback anchor).
    last_rate = []
    for i in range(n_tr):
        r = None
        for _, _, rates in reversed(snaps):
            if i < len(rates) and rates[i] is not None:
                r = float(rates[i])
                break
        last_rate.append(r if r is not None else 0.0)

    if len(snaps) >= 3:
        return _dynamic(trophies, snaps, x_of, t_of, x_t, t_t, last_rate)
    return _fallback(trophies, last_rate)


# Maturity-curve time constants (hours) tried per trophy.
TAUS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]


def wols(xs, ys, ws):
    """Weighted least squares y ~ a + b*x. Returns (a, b, sd, se_b, xw_mean)."""
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    if sxx <= 0:
        return my, 0.0, 0.0, float("inf"), mx
    b = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / sxx
    a = my - b * mx
    n = len(xs)
    if n <= 2:
        return a, b, 0.0, float("inf"), mx
    ss = sum(w * (y - (a + b * x)) ** 2 for w, x, y in zip(ws, xs, ys))
    sd = math.sqrt(ss / (sw * (n - 2) / n))
    se_b = sd / math.sqrt(sxx)
    return a, b, sd, se_b, mx


def _dynamic(trophies, snaps, x_of, t_of, x_t, t_t, last_rate):
    # Fit points use post-launch snapshots only (t >= 0.5h): the launch-night
    # page is a pre-launch cohort, not a point on the post-launch trajectory.
    fit_snaps = [(t, n, rates) for t, n, rates in snaps if t_of(t) >= 0.5]
    if len(fit_snaps) < 3:
        fit_snaps = snaps
    t_last = max(t_of(t) for t, _, _ in fit_snaps)

    def weight(t):
        return 0.5 ** ((t_last - t_of(t)) / 24.0)  # 24h half-life

    # --- first pass: curve slopes, for the cross-trophy median --------------
    slopes = []
    per_trophy = []
    for i, trophy in enumerate(trophies):
        pts = [
            (x_of(t), logit(rates[i]), weight(t))
            for t, _, rates in fit_snaps
            if i < len(rates) and rates[i] is not None
        ]
        if len(pts) >= 3:
            a, b, _, _, _ = wols([p[0] for p in pts], [p[1] for p in pts],
                                 [p[2] for p in pts])
            slopes.append(b)
        per_trophy.append(pts)
    b_med = median(slopes) if slopes else 0.0
    b_med = min(2.0, max(-1.0, b_med))

    rows = []
    for i, trophy in enumerate(trophies):
        lr = last_rate[i]
        pts = per_trophy[i]
        if lr <= 0 or len(pts) < 3:
            if lr <= 0:
                # Nobody had earned it by the cut: a few may by the target.
                rows.append({"id": trophy["id"], "q": _quantiles(0.05, 1.3)})
            else:
                rows.append({"id": trophy["id"], "q": _quantiles(lr, 0.9)})
            continue

        # --- component A: logit(rate) linear in x, slope shrunk ------------
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ws = [p[2] for p in pts]
        a, b, sd_a, se_a, mx_a = wols(xs, ys, ws)
        w_n = len(pts) / (len(pts) + 3.0)
        b_use = min(2.0, max(-1.0, w_n * b + (1.0 - w_n) * b_med))
        a_use = sum(w * (y - b_use * x) for w, x, y in zip(ws, xs, ys)) / sum(ws)
        med_a = inv_logit(a_use + b_use * x_t)

        # --- component B: maturity curve rate = R*(1-exp(-t/tau)) -----------
        ts = []
        rs = []
        ws_b = []
        for t, _, rates in fit_snaps:
            if i < len(rates) and rates[i] is not None:
                ts.append(t_of(t))
                rs.append(rates[i])
                ws_b.append(weight(t))
        max_r = max(rs)
        best = None
        for tau in TAUS:
            m = [1.0 - math.exp(-t / tau) for t in ts]
            num = sum(w * r * mm for w, r, mm in zip(ws_b, rs, m))
            den = sum(w * mm * mm for w, mm in zip(ws_b, m))
            if den <= 0:
                continue
            r_fit = max(max_r, min(99.0, num / den))
            sse = sum(w * (r - r_fit * mm) ** 2
                      for w, r, mm in zip(ws_b, rs, m))
            if best is None or sse < best[0]:
                best = (sse, tau, r_fit)
        _, tau_best, r_best = best
        med_b = r_best * (1.0 - math.exp(-max(0.0, t_t) / tau_best))
        # Guard: a slow trophy cannot plausibly multiply many times over.
        med_b = min(med_b, max(4.0 * lr, lr))
        med_b = max(0.01, min(100.0, med_b))

        # --- ensemble median + spread --------------------------------------
        lg_a, lg_b, lg_c = logit(med_a), logit(med_b), logit(lr)
        med_lg = W_CURVE * lg_a + W_MATURITY * lg_b + PERSIST_WEIGHT * lg_c
        med = inv_logit(med_lg)
        # Weighted spread of the three component forecasts around the median.
        hedge = math.sqrt(
            W_CURVE * (lg_a - med_lg) ** 2
            + W_MATURITY * (lg_b - med_lg) ** 2
            + PERSIST_WEIGHT * (lg_c - med_lg) ** 2
        )
        horizon_days = max(0.0, t_t - t_last) / 24.0
        var = BASE_SPREAD * BASE_SPREAD + sd_a * sd_a + hedge * hedge
        var += (se_a * se_a) * (x_t - mx_a) ** 2
        var += (REGIME_SPREAD * REGIME_SPREAD) * horizon_days
        spread = min(SPREAD_MAX, max(SPREAD_MIN, math.sqrt(max(0.0, var))))
        rows.append({"id": trophy["id"], "q": _quantiles(med, spread)})
    return {"trophies": rows}


def _quantiles(med, spread):
    lg = logit(med)
    qs = [round4(min(100.0, max(0.0, inv_logit(lg + z * spread)))) for z in Z]
    # Rounding can break monotonicity at the edges; enforce it.
    for k in range(1, 5):
        if qs[k] < qs[k - 1]:
            qs[k] = qs[k - 1]
    return qs


def _fallback(trophies, last_rate):
    """Flat history: expect the first refresh to dilute every rate but a
    100% one to ~0.22x, with a wide spread (see module docstring)."""
    rows = []
    for trophy, r in zip(trophies, last_rate):
        if r >= 99.99:
            med, spread = 100.0, SPREAD_MIN
        elif r <= 0:
            med, spread = 0.05, 1.3
        else:
            med, spread = r * DILUTE, FALLBACK_SPREAD
        rows.append({"id": trophy["id"], "q": _quantiles(med, spread)})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
