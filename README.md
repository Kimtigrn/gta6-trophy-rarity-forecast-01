# gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Kimtigrn/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Kimtigrn/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts each Grand Theft Auto VI PlayStation 5 trophy's earn rate on Exophase
at 2026-11-26T00:00Z, as five quantiles (5/25/50/75/95%) per trophy. Entry for
the MakeFun bounty `gta6-trophy-rarity-forecast-01` (mean pinball loss on the
logit scale; a prize needs a loss strictly below the best house entry).

## Run it

```sh
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Runs in ~0.1 s per case on one CPU, deterministic (two runs byte-identical).
No dependencies beyond the Python 3.13 standard library, no network.

## What it does

`main.py` reads one case file `/input/<id>.in` (or `$MAKEFUN_INPUT_DIR`) and
writes `/output/<id>.out` (or `$MAKEFUN_OUTPUT_DIR`): one row per trophy,
each five quantiles of that trophy's Exophase earn rate at the case's target.

The model, in one paragraph: Exophase's page only moves when Exophase
refreshes it, so a case's history is a staircase, and a trophy's rate is a
race between players earning it and new players joining (which dilutes it).
The forecast is the logit-space average of three components fitted on the
history's distinct snapshots: a maturity curve `rate(t) = R·(1−exp(−t/τ))`
per trophy (weight 0.6, τ by grid search), a recency-weighted logit-linear
trend in `ln(1 + hours since launch)` with its slope shrunk toward the
cross-trophy median (weight 0.2), and persistence at the last read's rate
(weight 0.2, a hedge against a post-cut change in the player mix that no
pre-cut trend can see). The spread combines the trend fit's residual and
slope uncertainty, the disagreement between the components, and a term that
grows with the horizon. When the history is flat (the launch-night practice
cases), no trend exists to fit, so the forecast falls back to the
first-refresh prior: the page's first refresh took players 638 → 3,868 and
trophies earned 943 → 4,276, so every rate but the one at 100% fell to
~0.22× its pre-refresh value. Full reasoning, variants tried, and risks:
see `NOTES.md`.

## Practice score (local, estimated truth)

The practice answers (the 04:30Z / 05:00Z reads) are not in the kit, so the
practice is scored locally against the refreshed page reconstructed from the
house's published totals (players 638 → 3,868, trophies earned 943 → 4,276):
non-100% trophies' earners grew 305 → 408 in aggregate, so each rate fell to
0.2207× its pre-refresh value (trophy 2 stayed at 100%). A sensitivity
variant assumes the new players earned nothing but the opening mission's
trophy (factor 0.1650×). Both bracket the house baseline's published ~1.51.

| entry | loss (0.2207× truth) | loss (0.1650× truth) |
|---|---|---|
| house baseline (starter) | 1.401279 | 1.687335 |
| **this entry** | **0.118652** | **0.175796** |

## Synthetic final backtests

Three simulated week-one worlds (generative trajectories with 4-hour
refreshes, cut at 2026-11-21T11:30Z, target 2026-11-26T00:00Z):

| world | this entry | house baseline | house curve baseline |
|---|---|---|---|
| maturity curves (rates saturate) | 0.136 | 0.318 | 0.275 |
| logit-linear rates | 0.170 | 0.366 | 0.218 |
| dilution shock (player surge after the cut) | 0.316 | 0.302 | 0.447 |

## Files

- `main.py` — the entry (single file, no other modules).
- `LICENSE` — MIT (as shipped in the kit's starter).
- `README.md` — this file.
- `NOTES.md` — method, variants tried with their scores, why the chosen
  model should generalise, known risks for the final.

---

Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards
