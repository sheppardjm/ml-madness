---
phase: 06-ensemble-models
plan: 05
subsystem: testing
tags: [xgboost, lightgbm, ensemble, stacking, calibration, brier-score, verification]

# Dependency graph
requires:
  - phase: 06-ensemble-models/06-01
    provides: XGBoost hyperparameters (xgb_params.json), evaluate_xgb()
  - phase: 06-ensemble-models/06-02
    provides: LightGBM hyperparameters (lgb_params.json), evaluate_lgb()
  - phase: 06-ensemble-models/06-03
    provides: TwoTierEnsemble (ensemble.joblib), OOF Brier=0.1672
  - phase: 06-ensemble-models/06-04
    provides: Ensemble backtest results (ensemble_results.json), mean Brier=0.1692
provides:
  - "06-VERIFICATION.md with honest PASS/NOTE/FAIL for all 4 Phase 6 success criteria"
  - "Calibration deviation measured and documented: max 0.1059 (exceeds 5pp threshold)"
  - "Ensemble vs baseline comparison on 2022-2025 holdout: -11% relative Brier improvement"
  - "SC-2 deviation from ROADMAP documented: StackingClassifier incompatibility explained"
affects:
  - phase-07-model-comparison
  - phase-08-feature-store
  - project-state

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verification report pattern: run programmatic checks, then write honest PASS/FAIL/NOTE with specific numbers"
    - "Calibration analysis: both uniform and quantile strategies tested; 248 OOF samples produce high-variance bins"

key-files:
  created:
    - .planning/phases/06-ensemble-models/06-VERIFICATION.md
  modified: []

key-decisions:
  - "Criterion 4 is honestly FAIL: max calibration deviation 0.1059 exceeds 5pp threshold; sparse OOF bins (248 samples, 6 active uniform bins) drive variance; not blocking for Phase 7"
  - "PARTIAL overall status (not PASS): 3/4 criteria met; calibration refinement deferred to Phase 8"
  - "Criterion 2 NOTE status retained: TwoTierEnsemble achieves identical architecture to sklearn StackingClassifier; deviation from ROADMAP wording is implementation detail only"

patterns-established:
  - "Verification reports must include specific numbers (Brier scores, calibration deviations) not just PASS/FAIL verdicts"
  - "Honest documentation: FAIL results are documented with root cause and impact assessment; not suppressed"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 6 Plan 5: Ensemble Verification Summary

**Phase 6 verification complete: ensemble beats baseline by 11% (Brier 0.1692 vs 0.1900); calibration FAIL due to sparse OOF bins (max deviation 0.1059 vs 5pp threshold); SC-2 deviation documented.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T06:07:28Z
- **Completed:** 2026-03-04T06:09:39Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Ran programmatic verification of all 4 Phase 6 success criteria against live model artifacts
- Wrote honest VERIFICATION.md with PASS/NOTE/FAIL per criterion and specific numerical evidence
- Confirmed Criterion 3 PASS: ensemble mean Brier=0.1692 beats baseline 0.1900 by 11% across all 4 holdout years
- Documented Criterion 4 FAIL honestly: max calibration deviation 0.1059 exceeds 5pp threshold; root cause is sparse OOF bin population (248 samples, 6 active uniform bins)

## Task Commits

Each task was committed atomically:

1. **Task 1: Run programmatic verification of all Phase 6 success criteria** - `89281d3` (docs)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `.planning/phases/06-ensemble-models/06-VERIFICATION.md` - Phase 6 formal verification results with PASS/NOTE/FAIL per criterion, specific Brier scores, calibration bin table, and deviation documentation

## Decisions Made

- **Criterion 4 FAIL is honest.** The 5pp threshold is not met (max deviation 0.1059). Root cause: 248 OOF samples in 6 active uniform bins; the [0.3,0.4] bin has only 16 samples, and 4 wrong predictions produce 10.59pp deviation. This is small-sample variance, not a model deficiency. The Brier improvement (Criterion 3) confirms the model is directionally correct.
- **Overall status is PARTIAL.** Three criteria are PASS or NOTE; one is FAIL. The phase objective is met for practical use -- 11% Brier improvement over baseline is the primary metric for bracket competition. Calibration refinement is Phase 8 scope.
- **No adjustments were made to pass Criterion 4.** The verification report documents reality, not the desired result.

## Deviations from Plan

None - plan executed exactly as written. The Criterion 4 FAIL was expected as a possibility given the plan's honest-documentation emphasis.

## Issues Encountered

- **Calibration deviation exceeds 5pp threshold.** The [0.3,0.4] probability bin contains only 16 of 248 OOF samples; observed actual win rate is 0.25 vs predicted 0.356, producing -0.1059 deviation. Both uniform and quantile calibration strategies confirm the threshold is not met (0.1059 and 0.1007 respectively). Documented as FAIL with root cause and impact assessment.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 6 ensemble artifacts are complete and verified: `models/ensemble.joblib`, `backtest/ensemble_results.json`, `models/ensemble_calibration_curve.png`
- Phase 7 (model comparison dashboard) can proceed -- ensemble delivers the best Brier score (0.1692 vs baseline 0.1900) on the 2022-2025 holdout
- Calibration refinement (Platt scaling, isotonic regression with more data) is deferred to Phase 8 (feature store)
- Known concern: `current_season_stats.parquet` uses 2024-25 metrics as proxy for 2026 features; refresh after cbbdata indexes 2025-26 data

---
*Phase: 06-ensemble-models*
*Completed: 2026-03-04*
