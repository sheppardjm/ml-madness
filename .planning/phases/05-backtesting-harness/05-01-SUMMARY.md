---
phase: 05-backtesting-harness
plan: 01
subsystem: testing
tags: [duckdb, sklearn, brier-score, log-loss, espn-scoring, backtest]

# Dependency graph
requires:
  - phase: 04-bracket-simulator
    provides: simulate_bracket() output format, slot_round_number(), ROUND_NAMES from bracket_schema
  - phase: 03-baseline-model-and-temporal-validation
    provides: tournament_games.parquet, seeds.parquet, ClippedCalibrator, FEATURE_COLS
  - phase: 01-historical-data-pipeline
    provides: MNCAATourneySeedRoundSlots.csv, tournament_games.parquet, seeds.parquet
provides:
  - build_actual_slot_winners(): DuckDB-based lookup of 67 actual slot winners per season
  - score_bracket(): ESPN bracket scoring with per-round accuracy (10/20/40/80/160/320 points)
  - compute_game_metrics(): Brier/log-loss/accuracy/upset-detection from fold predictions
  - ESPN_ROUND_POINTS and ESPN_MAX_SCORE constants
affects:
  - 05-02-backtesting-orchestration: consumes all three functions in the backtest loop
  - 05-03-results-reporting: uses ESPN score and per_round_accuracy for reporting

# Tech tracking
tech-stack:
  added: []
  patterns:
    - DuckDB CTE join pattern: seeds.parquet (filtered by season) + MNCAATourneySeedRoundSlots.csv (no Season column) + tournament_games.parquet
    - Batch sklearn prediction: scaler.transform() -> calibrated_clf.predict_proba() (not per-game predict_fn calls)
    - ESPN bracket scoring: skip round 0 (First Four), score rounds 1-6 with point doubling per round

key-files:
  created:
    - src/backtest/__init__.py
    - src/backtest/scoring.py
  modified: []

key-decisions:
  - "build_actual_slot_winners() uses DISTINCT in team_slots CTE -- seed labels like W01 appear multiple times in SeedRoundSlots (one row per round), DISTINCT prevents duplicate slot lookups"
  - "score_bracket() normalizes predicted_slots to handle both flat {slot_id: team_id} and nested {slot_id: {team_id: ...}} formats from simulate_bracket()"
  - "compute_game_metrics() uses batch scaler.transform() + predict_proba() not per-game predict_fn -- avoids O(n) closure call overhead in orchestration loop"
  - "ESPN_MAX_SCORE=1920: 32x10 + 16x20 + 8x40 + 4x80 + 2x160 + 1x320 = 1920"

patterns-established:
  - "Slot scoring pattern: slot_round_number() == 0 -> skip (First Four); else -> ESPN_ROUND_POINTS[round_num]"
  - "Upset definition: label=0 in matchup encoding (lower seed / team_b won); upset_correct = (y_prob < 0.5) & (y_test == 0)"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 5 Plan 1: Backtesting Scoring Module Summary

**DuckDB-based actual slot winner lookup, ESPN bracket scoring (perfect=1920), and batch game metrics (Brier/log-loss/accuracy/upset-detection) for 4-year backtest harness**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T04:40:26Z
- **Completed:** 2026-03-04T04:42:58Z
- **Tasks:** 1 of 1
- **Files modified:** 2

## Accomplishments
- `build_actual_slot_winners()` returns exactly 67 slot winners for all 4 backtest years (2022-2025) via DuckDB CTE join across seeds.parquet, MNCAATourneySeedRoundSlots.csv, and tournament_games.parquet
- `score_bracket()` correctly computes ESPN bracket scores with doubling point values per round (10/20/40/80/160/320), skips First Four, perfect bracket = 1920
- `compute_game_metrics()` batch-predicts Brier/log-loss/accuracy and upset detection rate from fold-specific scaler+calibrator (4-arg form ready for 05-02)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create scoring.py with actual slot winners, ESPN scoring, and game-level metrics** - `e3f567b` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `src/backtest/__init__.py` - Package marker for backtest module
- `src/backtest/scoring.py` - build_actual_slot_winners(), score_bracket(), compute_game_metrics(), ESPN constants

## Decisions Made
- `build_actual_slot_winners()` uses DISTINCT in the team_slots CTE because seed labels like W01 appear multiple times in MNCAATourneySeedRoundSlots.csv (one row per round 1-6). Without DISTINCT, teams appear 6 times each and the join would produce duplicate winners.
- `score_bracket()` normalizes the `predicted_slots` argument: it accepts both flat `{slot_id: team_id}` (plain dict) and nested `{slot_id: {'team_id': ..., 'win_prob': ..., 'round': ...}}` formats (simulate_bracket() output). This makes the function compatible with Phase 4's bracket JSON contract without requiring callers to extract team_ids first.
- `compute_game_metrics()` uses `scaler.transform()` + `calibrated_clf.predict_proba()` in batch mode rather than calling `predict_fn()` per game. This is intentional for the orchestration loop where calling predict_fn individually would invoke the closure hundreds of times per fold.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three scoring functions are complete and verified against all 4 backtest years.
- `build_actual_slot_winners()` returns 67 winners for 2022/2023/2024/2025.
- `score_bracket()` correctly scores perfect bracket at 1920 and empty bracket at 0.
- `compute_game_metrics()` produces the exact 7-key dict that 05-02 expects.
- Ready for 05-02 (backtest orchestration loop) to call all three functions.

---
*Phase: 05-backtesting-harness*
*Completed: 2026-03-04*
