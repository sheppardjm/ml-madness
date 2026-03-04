---
phase: 04-bracket-simulator
plan: "01"
subsystem: simulator
tags: [duckdb, joblib, logistic-regression, bracket, seedings, topological-sort]

# Dependency graph
requires:
  - phase: 03-baseline-model-and-temporal-validation
    provides: ClippedCalibrator model artifact at models/logistic_baseline.joblib
  - phase: 01-historical-data-pipeline
    provides: seeds.parquet with 68 tournament team seedings
  - phase: 02-current-season-and-bracket-data
    provides: current_season_stats.parquet for 2025 season features

provides:
  - src/simulator/__init__.py - package marker
  - src/simulator/bracket_schema.py - slot tree (67 slots), seedings (68 teams), predict_fn builder, team-seed map
  - ROUND_NAMES constant mapping round numbers 0-6 to display names
  - slot_round_number() helper for downstream round grouping

affects:
  - 04-02-simulate (consumes slot_tree, seedings, predict_fn)
  - 04-03-simulate-full (consumes all bracket_schema exports)
  - 04-04-score-predictor (consumes stats_lookup from build_predict_fn)
  - 04-05-monte-carlo (consumes predict_fn for sampling)
  - 04-06-output (consumes bracket result structures)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DuckDB read_csv/read_parquet for data loading in simulator layer"
    - "Closure pattern for predict_fn (captures model+scaler+stats_lookup)"
    - "Topological sort via slot_round_number key function (FF=0, R1-R6=1-6)"
    - "Seed label parsing: strip region prefix, strip a/b suffix, int() remainder"

key-files:
  created:
    - src/simulator/__init__.py
    - src/simulator/bracket_schema.py
  modified: []

key-decisions:
  - "FF slots identified as those not starting with 'R' (W16, X11, Y11, Y16 for 2025)"
  - "build_predict_fn returns (predict_fn, stats_lookup) tuple so 04-04 can access stats directly"
  - "predict_fn closure captures season at build time — caller must pass correct season to build_predict_fn"
  - "slot_round_number uses int(slot_id[1]) for R-prefixed slots — valid because Kaggle uses R1-R6 exclusively"

patterns-established:
  - "Slot canonical ordering: FF slots first (round 0), then R1 through R6 (rounds 1-6)"
  - "Team canonical ordering in predict_fn: team_a = lower seed number (better seed) — caller's responsibility"
  - "Seedings dict key format: exact Seed column value (e.g., 'W01', 'W16a') not just integer"

# Metrics
duration: 2min
completed: "2026-03-04"
---

# Phase 4 Plan 01: Bracket Schema Summary

**67-slot tournament tree loader with seedings dict, topological ordering, and ClippedCalibrator predict_fn closure via DuckDB and joblib**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T03:18:34Z
- **Completed:** 2026-03-04T03:20:18Z
- **Tasks:** 1/1
- **Files modified:** 2

## Accomplishments

- `build_slot_tree()` loads 67-slot bracket structure from MNCAATourneySlots.csv in topological order (FF slots first, championship last)
- `load_seedings()` returns 68 seed-label -> team_id mappings for any season, with format assertion
- `build_predict_fn()` wraps Phase 3 ClippedCalibrator in a closure returning `(predict_fn, stats_lookup)` for downstream simulation and scoring
- `build_team_seed_map()` parses integer seed numbers from seed labels including First Four a/b suffixes
- All verification checks pass: 67 slots, 68 seedings, 1v16 P=0.8900 (within expected range)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bracket_schema.py with slot tree, seedings, and predict_fn builder** - `a3aed2e` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/simulator/__init__.py` - Package marker for simulator module
- `src/simulator/bracket_schema.py` - Core bracket schema: slot tree, seedings, predict_fn, team-seed map, ROUND_NAMES

## Decisions Made

- **FF slot identification**: Slots not starting with 'R' are First Four (W16, X11, Y11, Y16 in 2025). This is robust to region name changes.
- **build_predict_fn returns tuple**: Returns `(predict_fn, stats_lookup)` to avoid re-loading stats in `score_predictor.py` (plan 04-04).
- **season captured in closure**: `predict_fn` uses the season passed to `build_predict_fn()` — this is correct since simulation for a given year uses that year's stats lookup.
- **Topological ordering key**: `slot_round_number(slot_id)` returns 0 for FF, `int(slot_id[1])` for R-prefixed — stable and correct for Kaggle's R1-R6 naming convention.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all data files present and in expected format. 1v16 prediction hits exactly 0.8900 (the ClippedCalibrator upper bound), which is expected for the strongest matchup type.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All Phase 4 downstream plans (04-02 through 04-06) can now import from `src.simulator.bracket_schema`
- `build_slot_tree()`, `load_seedings()`, and `build_predict_fn()` are the primary entry points
- For 2026 bracket simulation: run `build_predict_fn(season=2026)` after Selection Sunday data is loaded
- No blockers

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-04*
