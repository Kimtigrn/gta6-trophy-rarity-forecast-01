# NOTES — gta6-trophy-rarity-forecast-01

## The problem

Forecast, for each of GTA VI's 55 PS5 trophies, its earn rate on Exophase's
trophy page at 2026-11-26T00:00Z — five quantiles per trophy, scored by mean
pinball loss on the logit scale. The final case (f00) is cut at the deadline
2026-11-21T11:30Z with ~2.5 days of history (reads every 10 minutes, the page
itself refreshing only every few hours); the target is 4.5 days past the cut.
The prize gate is a loss strictly below the best house entry (persistence
baseline ≈1.51 on the practice, curve baseline the same there, house model
forecast made 2026-11-21T09:30Z).

## What the data says

- The page is a staircase: 638 players tracked and every rate unchanged from
  2026-11-18T23:48Z through the 04:00Z read, then refreshed at 04:30Z to
  3,868 players and 4,276 trophies earned (from 943). The newly tracked
  players held ~1 trophy each on average, and the trophy at 100% ("Just Like
  Paradise", the opening mission) stayed at 100% — so the new cohort had
  essentially only done the opening mission. Non-100% trophies' earners grew
  305 → 408 while players grew 6.06×: each rate fell to ~0.22×.
- A rate is therefore a race: players earning the trophy (up, toward the
  share who will ever earn it) against new players joining (down, dilution).
  Early on dilution dominates; over a week, earning dominates for story
  trophies and dilution still bites for late ones.

## Model (as submitted)

Per trophy, the median is the logit-space average of three components
(weights 0.2 / 0.6 / 0.2), fitted on the history's distinct snapshots
(consecutive identical reads carry no information; reads before the launch
are a pre-launch cohort and are excluded from the fits):

1. **Maturity curve** (weight 0.6): `rate(t) = R·(1 − exp(−t/τ))`, τ by grid
   search over {2, 4, …, 2048} hours, R by recency-weighted least squares
   (24h half-life), R clamped to ≥ the max observed rate. This is the
   structurally right shape: a trophy's rate saturates as the player base
   matures; a log-linear trend cannot saturate and overshoots.
2. **Logit-linear trend** (weight 0.2): recency-weighted least squares of
   logit(rate) on `ln(1 + hours since launch)`, slope shrunk toward the
   cross-trophy median slope (weight n/(n+3)). Covers worlds where rates keep
   accelerating instead of saturating.
3. **Persistence** (weight 0.2): the last read's rate — a hedge against a
   post-cut change in the player mix (e.g. a weekend surge of new players)
   that no pre-cut trend can see.

The spread is the honest combination of a base term (0.35 logit), the trend
fit's residual scatter and slope uncertainty scaled by the extrapolation
distance, the weighted spread of the three component forecasts, and a regime
term (0.15·√horizon-days). A trophy nobody had earned by the cut gets
median 0.05% with a wide spread; a trophy with too few positive reads gets
persistence with a 0.9 spread.

**Flat-history fallback** (practice cases): median 0.22 × last rate (a
trophy at 100% stays at 100%), spread 0.6.

## Variants tried (and why they lost)

| variant | practice (0.2207× / 0.1650× truth) | synthetic final (maturity / curve / dilution) |
|---|---|---|
| house baseline (starter) | 1.401 / 1.687 | 0.318 / 0.366 / 0.302 |
| house curve baseline (reimpl.) | 1.401 / 1.687 | 0.275 / 0.218 / 0.447 |
| v1: log-earners + log-players power laws | 0.974 / 0.814 (bug) → 0.178 / 0.235 (fixed) | 1.34–1.53 / — / — |
| v2: curve + maturity, equal weights, base 0.35 | 0.119 / 0.176 | 0.155 / 0.105 / 0.500 |
| v2 + wider base 0.5 + regime term | 0.119 / 0.176 | 0.188 / 0.151 / 0.458 |
| v2 + 20% persistence hedge | 0.119 / 0.176 | 0.172 / 0.175 / 0.365 |
| **v3 (submitted): weights 0.2/0.6/0.2, base 0.35** | **0.119 / 0.176** | **0.137 / 0.170 / 0.316** |

- **v1 failed** because log-earners vs log-time is strongly concave (the
  rate saturates while players grow as a power law): a global linear fit
  extrapolates earners past the player count and clamps rates to 100%.
  (Its first practice run also exposed a real bug: `parse_time` rejected
  fractional seconds in read timestamps, dropping every snapshot — fixed by
  parsing with `fromisoformat`.)
- **Widening the spread** (base 0.35 → 0.5) cost ~0.03 on the maturity/curve
  worlds and bought only ~0.04 on the dilution world, so the base stayed 0.35.
- **The persistence hedge** earned its keep: it fixed the logit-linear
  component's systematic overshoot on saturating trophies (typical miss
  4.2 → 2.2 points in the maturity world) and halved the dilution-world loss.
- **Weighting maturity 0.6 over the trend 0.2** was the single biggest win
  after the hedge: the maturity fit recovers the true (R, τ) almost exactly
  on synthetic data, while the trend overshoots saturating trophies by
  1.5–2×. The trend keeps a 0.2 weight for worlds where rates accelerate.

## Validation

- Local pinball scorer implements RULES.txt exactly (logit with clamping to
  0.01–99.99; loss `2·max(τ·d, (τ−1)·d)`); it reproduces the starter's
  published practice loss (~1.51, bracketed 1.40–1.69 by the two truth
  reconstructions).
- Determinism: two runs byte-identical on practice and on a synthetic final
  (360 reads). Runtime ~0.1 s per case (limit 8 s). Output ~3 KB (limit
  65,536 bytes). Output shape validated: exactly one key, one row per
  trophy, five finite non-decreasing quantiles in [0, 100].
- Edge cases exercised: empty history, two distinct snapshots only, a
  trophy at 0.00%, null rates — all produce valid output, no crashes.

## Known risks for the final

- **Post-cut regime change** (the dilution world): a weekend surge of new
  players after the cut would dilute rates below the forecast. The hedge and
  the horizon-growing spread cover part of it; in the harshest simulated
  version the entry ties the house baseline instead of beating it.
- **Refresh timing**: the answer is the page as of Exophase's last refresh
  before 2026-11-26T00:00Z. A refresh landing just before the target vs
  hours before moves the answer by up to one refresh interval; the spread
  allows for it, the median cannot know it.
- **Practice truth is reconstructed, not observed**: the 0.22× factor is
  pinned in aggregate by the published totals, but the per-trophy split of
  the 408 new earners is assumed proportional to old earners. The practice
  score is a signal, not the prize: the final is one fresh case.
- **Trophy list changes**: the program forecasts whatever trophies the case
  lists; a trophy added after the cut would have no history and gets the
  never-earned prior (median 0.05%).
