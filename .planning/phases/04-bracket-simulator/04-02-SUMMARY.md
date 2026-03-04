---
phase: 04-bracket-simulator
plan: 02
subsystem: simulation
tags: [bracket, simulation, deterministic, topological-sort, seed-ordering, json]

# Dependency graph
requires:
  - phase: 04-01
    provides: build_slot_tree(), load_seedings(), build_team_seed_map(), build_predict_fn(), ROUND_NAMES, slot_round_number()
provides:
  - simulate_bracket() with deterministic mode filling all 67 tournament slots
  - Canonical seed ordering enforcement for predict_fn calls
  - JSON-serializable bracket output with team_id, win_prob, and round name per slot
  - Champion identification from R6CH slot
affects:
  - 04-03 (monte_carlo mode builds on simulate_bracket() signature)
  - 04-04 (score_predictor uses bracket result JSON structure)
  - 04-05 (bracket lock-in uses override_map param in simulate_bracket)
  - 04-06 (batch simulation uses simulate_bracket as core call)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - topological slot traversal (FF first, R1-R6 last)
    - canonical seed ordering pattern (lower seed number = team_a for predict_fn)
    - overlay-not-replace pattern for stats lookup merging (preserves fallback coverage)

key-files:
  created:
    - src/simulator/simulate.py
  modified:
    - src/models/features.py

key-decisions:
  - "simulate_bracket() signature designed for future modes: n_runs, seed, override_map, stats_lookup all accepted as no-ops in deterministic mode"
  - "monte_carlo raises NotImplementedError with explicit plan reference (04-03) for discoverability"
  - "build_stats_lookup() overlay fix: current_season_stats.parquet used for covered teams, historical 2025 rows preserved as fallback for First Four teams absent from cbbdata"

patterns-established:
  - "Canonical seed ordering: always pass lower seed number as team_a; if StrongSeed has higher seed number, swap and invert prob_a_wins"
  - "All output values explicitly cast to int/float (not numpy types) before placing in result dict for JSON serialization"

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 4 Plan 02: Bracket Simulator - Deterministic Mode Summary

**simulate_bracket() filling all 67 slots via topological traversal with canonical seed ordering; champion = team 1222 (P=0.5425) for 2025 season**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-04T03:27:37Z
- **Completed:** 2026-03-04T03:30:00Z
- **Tasks:** 1 of 1
- **Files modified:** 2

## Accomplishments

- Created `simulate_bracket()` implementing deterministic mode: always picks team with higher win probability (>= 0.5)
- Enforced canonical seed ordering for every predict_fn call: lower seed number (better seed) passed as team_a
- Fixed `build_stats_lookup()` to overlay current_season_stats rather than replace, preserving First Four team coverage
- All 67 bracket slots filled, champion identified, output fully JSON-serializable with native Python types

## Task Commits

Each task was committed atomically:

1. **Task 1: Create simulate.py with deterministic bracket fill** - `9d06c64` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `src/simulator/simulate.py` - simulate_bracket() with _simulate_deterministic() internal function; __main__ smoke test
- `src/models/features.py` - Fixed build_stats_lookup() to overlay current stats and preserve historical fallback for uncovered teams

## Decisions Made

- `simulate_bracket()` signature includes all future-mode params (n_runs, seed, override_map, stats_lookup) as no-ops in deterministic mode — avoids breaking callers when monte_carlo is added in 04-03
- `monte_carlo` mode raises `NotImplementedError("Monte Carlo mode not yet implemented -- see 04-03")` for explicit discoverability
- Unknown modes raise `ValueError` with clear message
- Internal `_simulate_deterministic()` helper keeps public API clean and leaves room for `_simulate_monte_carlo()` peer function in 04-03

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed build_stats_lookup() stats overlay dropping First Four team coverage**

- **Found during:** Task 1 (while running simulation smoke test)
- **Issue:** `current_season_stats.parquet` does not include all 68 tournament teams; First Four play-in teams (e.g., St. Francis PA, team 1384) sourced from Barttorvik may be absent from the cbbdata snapshot. Old code replaced ALL 2025 historical data with current_season_stats rows, dropping uncovered teams and causing `compute_features()` to return NaN features (KeyError in stats_lookup).
- **Fix:** Changed merge logic to: (a) keep all non-2025 historical rows, (b) keep 2025 historical rows for teams NOT in current_season_stats, (c) add current_season_stats rows. This overlay pattern ensures current_season_stats is authoritative for covered teams while uncovered First Four teams fall back to the historical snapshot.
- **Files modified:** `src/models/features.py`
- **Verification:** Simulation completes all 67 slots including First Four games (W16, X11, Y11, Y16 all resolved); team 1384 (St. Francis PA) correctly appears in R1Y8 slot.
- **Committed in:** `9d06c64` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Bug fix essential for correctness — without it, simulate_bracket() would crash on First Four matchups involving teams absent from cbbdata. No scope creep.

## Issues Encountered

None beyond the auto-fixed bug above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `simulate_bracket()` public API is stable and ready for 04-03 (monte_carlo) to add `_simulate_monte_carlo()` peer
- Bracket output JSON structure is finalized: `{mode, season, slots: {slot_id: {team_id, win_prob, round}}, champion: {team_id, win_prob}}`
- `override_map` param is stubbed and documented for 04-05 (bracket lock-in)
- `stats_lookup` param is accepted as no-op for 04-04 (score predictor) to consume

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-03*
