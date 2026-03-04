---
phase: 04-bracket-simulator
plan: 03
subsystem: simulator
tags: [numpy, monte-carlo, simulation, bracket, probability, vectorized]

# Dependency graph
requires:
  - phase: 04-02
    provides: simulate_bracket() with deterministic mode, slot tree, team-seed map
  - phase: 04-01
    provides: build_predict_fn, bracket_schema, ROUND_NAMES, slot_round_number
  - phase: 03-04
    provides: trained logistic model with ClippedCalibrator [0.05, 0.89]

provides:
  - simulate_bracket() monte_carlo mode with pre-computed 68x68 prob matrix
  - Vectorized numpy Bernoulli draws (n_runs simultaneously per slot)
  - Per-team advancement probabilities with human-readable round names
  - Champion prediction with confidence (fraction of 10K runs)
  - Reproducible simulation via seed parameter (PCG64 RNG)

affects:
  - 04-04 (score predictor - consumed alongside monte_carlo output)
  - 04-05 (bracket lock-in - will use monte_carlo advancement_probs)
  - 04-06 (export / UI contract - advancement_probs JSON schema)
  - 05-simulation-analysis (consumes advancement_probs for analysis)
  - 09-10-ui (displays champion confidence + advancement probs)

# Tech tracking
tech-stack:
  added: [numpy (np.random.default_rng, np.bincount, np.where, np.argmax)]
  patterns:
    - Pre-compute probability matrix once (NxN), then index vectorized per run
    - Vectorized Bernoulli: rng.random(n_runs) < prob_matrix[occ_i, occ_j]
    - Topological slot traversal with occupant arrays (dict[slot_id -> ndarray shape(n_runs,)])
    - All numpy types converted to native Python before returning (int/float)

key-files:
  created: []
  modified:
    - src/simulator/simulate.py

key-decisions:
  - "prob_matrix pre-computed once (4,624 calls) before any simulation runs -- critical for performance"
  - "RNG: np.random.default_rng(seed) with PCG64 -- seed=None is non-deterministic, seed=42 is reproducible"
  - "occupants dict stores np.ndarray(shape=(n_runs,), dtype=int32) per slot including seed-label starting slots"
  - "Champion = argmax(bincount(R6CH_occupants)) -- most frequent winner across all runs"
  - "advancement_probs includes 'Champion' key (alias for R6CH fraction) alongside 'Championship' (Championship game winner)"
  - "Monte Carlo champion (team 1222) matches deterministic champion -- model self-consistent"
  - "Performance: 10K runs in 0.21s on M-series Mac -- 143x headroom under 30s limit"

patterns-established:
  - "Vectorized occupant pattern: occupants[slot_id] = ndarray(n_runs) of team indices, not team IDs"
  - "Canonical pair ordering in prob_matrix: lower seed_num = row/strong index; same-seed tiebreak by team_id"
  - "All output conversion: {int(k): {str(r): float(p)} for k,r,p in ...} before returning"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 4 Plan 03: Monte Carlo Bracket Simulation Summary

**Monte Carlo mode with pre-computed 68x68 probability matrix and vectorized numpy draws producing per-team advancement probabilities and champion confidence in 0.21s for 10K runs**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T03:31:45Z
- **Completed:** 2026-03-04T03:33:53Z
- **Tasks:** 1 of 1
- **Files modified:** 1

## Accomplishments

- Pre-computed 68x68 win probability matrix (4,624 predict_fn calls once, not per-run)
- Vectorized numpy Bernoulli draws: all n_runs processed simultaneously per slot via `prob_matrix[occ_i, occ_j]` indexing
- Per-team advancement probabilities for all 68 teams across 7 rounds with human-readable names from ROUND_NAMES
- Champion prediction with confidence (team 1222 at 31.8% with seed=42, 10K runs) -- matches deterministic pick
- Reproducible output: same seed parameter produces bit-identical results across runs
- 10K simulations complete in 0.21s (143x headroom under the 30s requirement)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement pre-computed probability matrix and vectorized Monte Carlo** - `9f97c7e` (feat)

## Files Created/Modified

- `src/simulator/simulate.py` - Added `_build_prob_matrix()`, `_compute_advancement_probs()`, `_simulate_monte_carlo()` helpers; updated `simulate_bracket()` dispatcher to call Monte Carlo mode; updated `__main__` block with MC timing and top-10 contenders output

## Decisions Made

- **prob_matrix pre-computed once:** 4,624 predict_fn calls happen before simulation loop; each run indexes directly into the matrix (O(1) per matchup vs O(1) predict_fn call). Critical for vectorized performance.
- **RNG approach:** `np.random.default_rng(seed)` with PCG64 generator. `seed=None` gives non-deterministic runs; `seed=42` gives identical results across invocations.
- **Occupants as index arrays:** Stores team indices (not team_ids) in occupant arrays to enable direct `prob_matrix[occ_i, occ_j]` array indexing. `idx_to_team` dict converts back at output time.
- **"Champion" key in advancement_probs:** Added as alias to R6CH winning fraction. "Championship" = fraction winning the championship game slot; "Champion" = fraction winning the tournament. Both are identical for R6CH but the alias improves caller ergonomics.
- **dtype=int32 for occupant arrays:** Sufficient for up to 2B team indices; saves memory vs int64 for large n_runs.

## Deviations from Plan

None - plan executed exactly as written. All implementation details matched the plan spec (prob matrix, vectorized draws, ROUND_NAMES, Champion key, seed reproducibility).

## Issues Encountered

None. First implementation passed all verification assertions and performance checks on the first run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Monte Carlo simulation is ready for consumption by:
  - 04-04 (score predictor): `stats_lookup` is already in `simulate_bracket()` signature; MC result dict is the natural complement
  - 04-05 (bracket lock-in): `advancement_probs` dict provides per-team round probabilities for lock-in scoring
  - 04-06 (export/API): Both deterministic and MC results are JSON-serializable native Python types
- No blockers. The 04-03 must-haves are all verified:
  - Pre-computed matrix: confirmed (4,624 calls once)
  - Vectorized draws: confirmed (numpy where + rng.random)
  - Human-readable round names: confirmed (ROUND_NAMES keys)
  - Seed reproducibility: confirmed (identical output with seed=42)
  - Performance: confirmed (0.21s << 30s)

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-04*
