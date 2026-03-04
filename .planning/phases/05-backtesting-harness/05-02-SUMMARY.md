---
phase: 05-backtesting-harness
plan: "02"
subsystem: backtesting
tags: [logistic-regression, walk-forward-cv, espn-scoring, brier-score, bracket-simulation, temporal-isolation, json]

# Dependency graph
requires:
  - phase: 05-01
    provides: build_actual_slot_winners(), score_bracket(), compute_game_metrics()
  - phase: 04-02
    provides: simulate_bracket(mode='deterministic'), load_seedings()
  - phase: 03-04
    provides: ClippedCalibrator, CLIP_LO, CLIP_HI, logistic_baseline.joblib artifact
  - phase: 03-01
    provides: FEATURE_COLS, build_matchup_dataset(), build_stats_lookup(), compute_features()
  - phase: 03-02
    provides: BACKTEST_YEARS, walk_forward temporal isolation pattern

provides:
  - "backtest() function orchestrating full feature-to-simulator-to-scoring pipeline"
  - "Per-year model refitting with strict Season < test_year temporal isolation"
  - "backtest/results.json with per_year metrics array and summary aggregates"
  - "mean_brier=0.1900, mean_ESPN=912.5, mean_accuracy=69.0% across 2022-2025"

affects:
  - 05-03-backtest-comparison-report
  - 06-ensemble-model
  - 07-model-comparison-dashboard

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Default-arg closure pattern for predict_fn to prevent late-binding bugs: make_predict_fn(_year=test_year, _scaler=scaler, _clf=calibrated_clf)"
    - "Temporal isolation: train_df = df[df['Season'] < test_year]; artifact provides best_C only"
    - "Layered aggregation: game-level metrics via compute_game_metrics(), bracket-level via score_bracket()"

key-files:
  created:
    - src/backtest/backtest.py
    - backtest/results.json
  modified: []

key-decisions:
  - "best_C extracted from artifact dict only (artifact['best_C']); scaler and model from artifact never used for predictions -- fresh refit per fold"
  - "make_predict_fn() factory with default-arg binding prevents late-binding Python closure bug (all 4 folds would otherwise share last loop iteration's scaler/clf)"
  - "stats_lookup built once outside loop and passed to both predict_fn and simulate_bracket() for efficiency"
  - "predict_fn returns 0.5 on KeyError (missing teams) -- handles First Four play-in teams absent from cbbdata stats"
  - "backtest/ output directory created automatically by pathlib; mkdir parents=True so it works from any working directory"
  - "numpy int64 values in training_seasons printed as-is (cosmetic, not functional) -- no impact on results"

patterns-established:
  - "backtest.py: load best_C only from artifact, refit scaler+model per year"
  - "backtest.py: make_predict_fn() factory pattern for closures capturing loop variables"

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 5 Plan 02: Backtest Orchestration Summary

**backtest() orchestrator re-fits LogisticRegression+ClippedCalibrator per year, simulates brackets deterministically, and scores against actual results yielding mean_brier=0.1900, mean_ESPN=912.5 across 2022-2025**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-04T04:45:26Z
- **Completed:** 2026-03-04T04:48:27Z
- **Tasks:** 1 of 1
- **Files modified:** 2

## Accomplishments

- Implemented `backtest()` in `src/backtest/backtest.py` with full temporal isolation: each fold re-fits StandardScaler + LogisticRegression(C=best_C) + ClippedCalibrator on Season < test_year only
- Integrated all Phase 3-5 modules: `build_matchup_dataset`, `build_stats_lookup`, `compute_features`, `load_seedings`, `simulate_bracket`, `build_actual_slot_winners`, `score_bracket`, `compute_game_metrics`
- Produced reproducible `backtest/results.json` with per-year bracket metrics (ESPN score, per-round accuracy) and game-level metrics (Brier, log-loss, accuracy, upset detection) plus summary aggregates
- Confirmed mean_brier=0.1900 exactly matches `evaluation_results.json` benchmark; game counts match (2024=62, 2025=60)

## Task Commits

Each task was committed atomically:

1. **Task 1: backtest() orchestration with per-year temporal refitting** - `06e83c5` (feat)

**Plan metadata:** _(see final metadata commit)_

## Files Created/Modified

- `src/backtest/backtest.py` - `backtest()` function, `make_predict_fn()` factory, `_print_results_table()`, `__main__` block
- `backtest/results.json` - Reproducible per-year and summary metrics, generated_at 2026-03-04

## Decisions Made

- **Default-arg closure pattern for predict_fn**: Used `make_predict_fn(_year=test_year, _scaler=scaler, _clf=calibrated_clf)` factory function with default arguments to bind each iteration's `scaler` and `calibrated_clf`. Without this, all 4 `predict_fn` closures would reference the same loop variable, causing all folds to use the last year's model.
- **best_C only from artifact**: `artifact['best_C']` extracted; the artifact's trained `model` and `scaler` keys are ignored. Each fold gets fresh scaler+model fit from temporal training slice.
- **stats_lookup built once**: Expensive operation called outside the year loop and passed to both `predict_fn` and `simulate_bracket(stats_lookup=stats_lookup)` for efficiency.
- **0.5 fallback for KeyError**: `predict_fn` returns 0.5 on `KeyError` from `compute_features()`. This handles First Four play-in teams (e.g., St. Francis PA) absent from the cbbdata stats snapshot.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Numpy int64 values appear in the "Training seasons" print output (cosmetic only -- `np.int64(2008)` instead of `2008`). This does not affect results or JSON output (JSON serialization uses native Python ints from the DataFrame).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `backtest/results.json` is ready for 05-03 comparison report
- Brier benchmark (0.1900) confirmed and ready for Phase 6 ensemble model to beat
- `backtest()` is importable as `from src.backtest.backtest import backtest` for programmatic use in Phase 6-7

---
*Phase: 05-backtesting-harness*
*Completed: 2026-03-04*
