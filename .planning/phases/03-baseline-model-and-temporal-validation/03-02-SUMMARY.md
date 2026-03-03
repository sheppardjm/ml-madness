---
phase: 03-baseline-model-and-temporal-validation
plan: 02
subsystem: modeling
tags: [sklearn, optuna, logistic-regression, temporal-cv, joblib, brier-score, walk-forward]

# Dependency graph
requires:
  - phase: 03-01
    provides: build_matchup_dataset(), FEATURE_COLS, historical_torvik_ratings.parquet, features.py
  - phase: 02-01
    provides: current_season_stats.parquet used by build_stats_lookup()

provides:
  - Walk-forward temporal CV harness (BACKTEST_YEARS, walk_forward_splits, describe_splits)
  - Logistic regression baseline model with Optuna-tuned C (best_C=2.7277, Brier=0.1896)
  - models/logistic_baseline.joblib artifact with full metadata
  - predict_matchup() for arbitrary team-pair feature dict prediction
  - load_model() for artifact loading with sklearn version check

affects:
  - 03-03 (Brier score calibration evaluation uses these folds)
  - 03-04 (Seed baseline comparison uses same CV harness)
  - 03-05 (Phase 3 wrap-up references temporal CV as canonical eval framework)
  - 06 (Ensemble phase must beat this logistic baseline Brier score)
  - All future model evaluation in any phase

# Tech tracking
tech-stack:
  added: [optuna==4.7.0, joblib, sklearn==1.8.0]
  patterns:
    - Walk-forward temporal CV — all model evaluation uses walk_forward_splits() with BACKTEST_YEARS
    - Optuna minimize-Brier-score sweep for C selection (log-uniform 1e-3 to 100)
    - Per-fold StandardScaler fitting to prevent leakage from test set statistics
    - Artifact dict pattern — model artifacts include model, scaler, feature_names, train_seasons, best_C, sklearn_version

key-files:
  created:
    - src/models/temporal_cv.py
    - src/models/train_logistic.py
    - models/logistic_baseline.joblib
  modified: []

key-decisions:
  - "BACKTEST_YEARS = [2022, 2023, 2024, 2025] — 4 most recent tournaments as holdout years for walk-forward CV"
  - "Optuna log-uniform search over C in [1e-3, 100] with 50 trials; best C=2.7277 minimizes mean Brier score"
  - "StandardScaler fit on training fold only in each CV fold — prevents leakage from test set statistics"
  - "barthag_diff coefficient sign is negative due to multicollinearity with adjoe_diff/adjde_diff — expected with correlated features; adjoe_diff (+1.86) and adjde_diff (-1.73) dominate and capture the same signal"
  - "joblib artifact pattern: saves dict with model + scaler + feature_names + train_seasons + best_C + sklearn_version"

patterns-established:
  - "Temporal CV pattern: for each evaluation, always call walk_forward_splits(df) — never custom train/test splits"
  - "Scaler fit discipline: StandardScaler.fit_transform() only on train, .transform() only on test — never fit on test"
  - "Artifact loading: load_model() checks sklearn version and warns on mismatch before returning (model, scaler, features)"
  - "predict_matchup() takes feature dict keyed by FEATURE_COLS names — same interface used by all downstream callers"

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 3 Plan 02: Temporal CV Harness and Logistic Regression Baseline Summary

**Walk-forward temporal CV (4 folds, 2022-2025) with Optuna-tuned logistic regression; best C=2.7277, mean Brier score=0.1896 across holdout folds; model artifact at models/logistic_baseline.joblib**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T20:38:15Z
- **Completed:** 2026-03-03T20:41:00Z
- **Tasks:** 2 of 2
- **Files modified:** 3

## Accomplishments

- Walk-forward temporal CV harness with 4 holdout folds (2022, 2023, 2024, 2025) and data leakage guard asserted on every split
- Optuna 50-trial sweep (log-uniform C in [1e-3, 100]) with per-fold StandardScaler discipline; best C=2.7277, Brier=0.1896
- Trained logistic regression on all 1054 matchups (2008-2025, 17 seasons) and saved complete artifact to models/logistic_baseline.joblib
- predict_matchup() and load_model() utilities ready for downstream phase consumption

## Task Commits

Each task was committed atomically:

1. **Task 1: Walk-forward temporal cross-validation harness** - `04bf8ae` (feat)
2. **Task 2: Train logistic regression with Optuna sweep and save model** - `1690f96` (feat)

## Files Created/Modified

- `src/models/temporal_cv.py` - BACKTEST_YEARS, walk_forward_splits() generator, describe_splits() table printer
- `src/models/train_logistic.py` - run_optuna_sweep(), train_and_save(), load_model(), predict_matchup()
- `models/logistic_baseline.joblib` - Serialized artifact: model, scaler, feature_names, train_seasons, best_C, sklearn_version

## Decisions Made

- **Optuna log-uniform C search:** Used log=True in suggest_float to explore a wide range (1e-3 to 100) efficiently; log scale makes small and large C equally likely to be explored.
- **50 trials:** Sufficient for a 1D search; Optuna converges quickly with log-uniform sampling.
- **barthag_diff coefficient is negative (-0.82):** This is a multicollinearity artifact. barthag is computed from adjoe and adjde; with all three in the model, the partial effect of barthag reverses sign while adjoe_diff (+1.86) and adjde_diff (-1.73) capture the actual signal. Model predictions are directionally correct despite the sign flip.
- **Artifact dict pattern:** Stores all metadata needed for future prediction, version auditing, and phase 6 ensemble composition.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — all verifications passed on first run.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `walk_forward_splits()` is the canonical CV harness for all future model evaluation (phase 3-03, 3-04, phase 6 ensemble)
- `models/logistic_baseline.joblib` is the benchmark: ensemble in phase 6 must achieve lower Brier score
- `predict_matchup()` is ready for bracket simulation in phases 4-5
- Brier score calibration (03-03) can use the same folds and training infrastructure established here

---
*Phase: 03-baseline-model-and-temporal-validation*
*Completed: 2026-03-03*
