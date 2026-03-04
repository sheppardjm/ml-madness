---
phase: 06-ensemble-models
plan: 04
subsystem: model-evaluation
tags: [xgboost, lightgbm, logistic-regression, stacking-ensemble, backtest, temporal-cv, brier-score]

# Dependency graph
requires:
  - phase: 06-03
    provides: TwoTierEnsemble class and OOF stacking architecture
  - phase: 05-02
    provides: backtest() orchestration harness and scoring pipeline
  - phase: 06-01
    provides: XGBoost hyperparameters (models/xgb_params.json)
  - phase: 06-02
    provides: LightGBM hyperparameters (models/lgb_params.json)
provides:
  - Extended backtest() function supporting model='ensemble' with per-fold temporal isolation
  - _build_fold_ensemble() helper: nested sub-fold OOF meta-learner per backtest year
  - backtest/ensemble_results.json: reproducible ensemble backtest results for 2022-2025
  - Mean ensemble Brier=0.1692 vs baseline 0.1900 (-11% relative improvement confirmed)
affects:
  - 06-05 (hyperparameter optimization / final model selection)
  - 07-model-comparison-dashboard (ensemble_results.json is primary input)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - _build_fold_ensemble() factory: per-fold ensemble built from scratch; models/ensemble.joblib never used in backtest
    - Nested sub-fold OOF: meta-learner trained on last 3 seasons before test_year (inner loop inside outer walk-forward)
    - make_ensemble_predict_fn() factory pattern: default-arg binding prevents late-binding closure bug
    - Dual output routing: model='baseline' -> backtest/results.json, model='ensemble' -> backtest/ensemble_results.json
    - TwoTierEnsemble as calibrated_clf: passed directly to compute_game_metrics() (satisfies predict_proba() interface)

key-files:
  created:
    - backtest/ensemble_results.json
  modified:
    - src/backtest/backtest.py

key-decisions:
  - "Per-fold ensemble built entirely from scratch for each backtest year -- models/ensemble.joblib is never loaded; ensures strict temporal isolation"
  - "Meta-learner in each fold uses nested OOF from last 3 available seasons before test_year (not the full walk_forward_splits OOF), matching 06-03 architecture"
  - "fold_scaler.transform() called by predict_fn caller; TwoTierEnsemble.predict_proba() receives already-scaled input (no double-scaling)"
  - "Ensemble results written to separate backtest/ensemble_results.json to preserve baseline results.json intact"
  - "Both models share the same __main__ entry point via sys.argv[1]: uv run python -m src.backtest.backtest [baseline|ensemble]"

patterns-established:
  - "_build_fold_ensemble() pattern: module-level private helper builds complete fold ensemble; returned (ensemble, scaler) tuple passed to make_ensemble_predict_fn()"
  - "make_ensemble_predict_fn() factory pattern with default-arg binding: prevents late-binding bug when loop variables change across folds"
  - "Model-agnostic compute_game_metrics(): TwoTierEnsemble.predict_proba() satisfies interface -- no special-casing needed for ensemble vs baseline"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 6 Plan 4: Ensemble Backtest Summary

**Per-fold TwoTierEnsemble backtest (2022-2025) achieves mean Brier=0.1692, beating logistic baseline 0.1900 by 11% relative (-0.0208 delta)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T06:02:14Z
- **Completed:** 2026-03-04T06:04:47Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Extended backtest() to support model='ensemble' alongside model='baseline' (baseline code path untouched, Brier still 0.1900)
- Implemented _build_fold_ensemble(): per-fold TwoTierEnsemble with nested sub-fold OOF from last 3 seasons before test_year (strict temporal isolation; models/ensemble.joblib never used)
- Ran full 2022-2025 ensemble backtest: mean Brier=0.1692, mean ESPN=1037.5, mean accuracy=74.3%
- Ensemble beats baseline in all 4 holdout years (2022: 0.1793, 2023: 0.1850, 2024: 0.1760, 2025: 0.1364)

## Task Commits

1. **Task 1: Extend backtest() with ensemble support and run 2022-2025** - `2eb97cc` (feat)

**Plan metadata:** (included in next commit with SUMMARY + STATE)

## Files Created/Modified

- `src/backtest/backtest.py` - Extended with _build_fold_ensemble() helper, ensemble branch in per-year loop, CLI arg support in __main__
- `backtest/ensemble_results.json` - Ensemble backtest results: per-year metrics + summary aggregates for 2022-2025

## Decisions Made

- Per-fold ensemble built entirely from scratch; models/ensemble.joblib is never loaded during backtesting -- ensures no test-set information leaks through the full-dataset artifact
- Meta-learner uses nested OOF from last 3 available seasons before test_year (not the entire walk_forward_splits range), exactly matching the 06-03 stacking architecture
- TwoTierEnsemble.predict_proba() receives already-scaled input -- fold_scaler.transform() is called in the predict_fn closure, not inside the ensemble (prevents double-scaling per 06-03 design constraint)
- Ensemble output routed to separate backtest/ensemble_results.json automatically (baseline output_path detection); preserves baseline results.json intact for downstream validation
- __main__ updated to accept sys.argv[1] for model selection: `uv run python -m src.backtest.backtest ensemble`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - implementation matched plan specification. The make_ensemble_predict_fn() factory pattern (preventing late-binding closure bug), the TwoTierEnsemble.predict_proba() interface compatibility with compute_game_metrics(), and the dual-output file routing all worked as designed.

## Ensemble Results Summary

| Year | Brier  | LogLoss | Acc    | ESPN  | Champion |
|------|--------|---------|--------|-------|----------|
| 2022 | 0.1793 | 0.5366  | 74.6%  | 690   | 1222     |
| 2023 | 0.1850 | 0.5475  | 66.7%  | 1100  | 1163     |
| 2024 | 0.1760 | 0.5251  | 72.6%  | 1260  | 1163     |
| 2025 | 0.1364 | 0.4351  | 83.3%  | 1100  | 1181     |
| Mean | 0.1692 | 0.5111  | 74.3%  | 1037.5 |         |

**Ensemble vs Baseline:** 0.1692 vs 0.1900 (delta=-0.0208, -11% relative) -- ENSEMBLE WINS

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- backtest/ensemble_results.json is ready for 06-05 (hyperparameter sweep / model finalization) and Phase 7 (model comparison dashboard)
- Central Phase 6 question answered: ensemble beats logistic baseline by 11% on the same walk-forward protocol
- Both result files preserved: baseline (results.json, Brier=0.1900) and ensemble (ensemble_results.json, Brier=0.1692)
- No blockers for 06-05

---
*Phase: 06-ensemble-models*
*Completed: 2026-03-04*
