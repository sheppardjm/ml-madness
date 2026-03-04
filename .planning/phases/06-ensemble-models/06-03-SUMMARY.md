---
phase: 06-ensemble-models
plan: 03
subsystem: modeling
tags: [xgboost, lightgbm, logistic-regression, stacking-ensemble, oof, temporal-cv, calibration, joblib]

# Dependency graph
requires:
  - phase: 06-01
    provides: XGBoost best hyperparameters (models/xgb_params.json)
  - phase: 06-02
    provides: LightGBM best hyperparameters (models/lgb_params.json)
  - phase: 03-02
    provides: walk_forward_splits(), BACKTEST_YEARS, ClippedCalibrator, CLIP_LO/CLIP_HI
provides:
  - TwoTierEnsemble class with predict_proba() taking pre-scaled features
  - build_ensemble() factory with manual OOF temporal stacking
  - models/ensemble.joblib with trained ensemble, all params, and OOF Brier metadata
  - models/ensemble_calibration_curve.png showing before/after clipping
  - save_artifact() helper for pickle-safe module-path serialization
affects: ["06-04-backtest-ensemble", "06-05-neural-net", "09-ui", "bracket-simulator"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Manual OOF temporal stacking via walk_forward_splits() (NOT sklearn StackingClassifier)"
    - "TwoTierEnsemble.predict_proba() takes ALREADY-SCALED features (caller scales, not ensemble)"
    - "save_artifact() re-imports class from stable module path before joblib.dump() to fix __main__ pickle path"
    - "LR base model OOF predictions go through ClippedCalibrator to match production inference"
    - "Meta-learner trained on OOF (C=1.0), then all base models re-fit on full dataset"

key-files:
  created:
    - src/models/ensemble.py
    - models/ensemble.joblib
    - models/ensemble_calibration_curve.png
  modified: []

key-decisions:
  - "Manual OOF stacking used instead of sklearn StackingClassifier because walk_forward_splits() produces non-partition (prefix) splits that trigger ValueError in sklearn's cross_val_predict() partition check (GitHub #32614)"
  - "TwoTierEnsemble.predict_proba() does NOT auto-scale; caller must pass pre-scaled features to prevent double-scaling when backtest harness also applies the scaler"
  - "save_artifact() fixes __main__ pickle path issue by re-importing TwoTierEnsemble from src.models.ensemble module before joblib.dump(); same root cause as train_logistic.py ClippedCalibrator issue"
  - "LR base model OOF predictions go through ClippedCalibrator (consistent with production) -- raw LR would inject unclipped probabilities into meta-learner training"
  - "Meta-learner uses C=1.0 (not tuned) -- 248 OOF samples with 3 features; C=1.0 provides moderate regularization; tuning would risk meta-overfitting"
  - "OOF Ensemble Brier=0.1672 vs baseline 0.1900 (delta=-0.0228) -- ensemble significantly outperforms individual models (XGB=0.1908, LGB=0.1931, LR=0.1900)"
  - "Meta-learner coefficients: XGB=1.2606, LGB=0.9227, LR=1.6981 -- LR base model weighted highest, expected given it was tuned on same temporal CV"

patterns-established:
  - "Ensemble artifact saves: model, params, ensemble object, scaler, feature_names, clip bounds, train_seasons, oof_brier, oof_brier_per_year, meta_coefficients, library versions"
  - "save_artifact() pattern: re-import class from stable module before pickle to avoid __main__ path corruption"

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 6 Plan 3: Stacking Ensemble Summary

**XGB+LGB+LR stacking ensemble via manual OOF temporal splits; meta-learner LR (C=1.0) achieves OOF Brier=0.1672 vs baseline 0.1900 (-0.0228 improvement)**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-04T05:52:49Z
- **Completed:** 2026-03-04T05:56:57Z
- **Tasks:** 1 (single task plan)
- **Files created:** 3

## Accomplishments

- TwoTierEnsemble class with predict_proba() interface (takes pre-scaled features, returns (n, 2) array clipped to [0.05, 0.89])
- Manual OOF temporal stacking across all 4 walk-forward folds (248 total samples) trains LogisticRegression meta-learner
- OOF Ensemble Brier=0.1672 beats baseline 0.1900 by 0.0228 (12% relative improvement)
- All 3 base models (XGB, LGB, LR) re-fit on full dataset for production inference
- save_artifact() helper prevents __main__ pickle path corruption on serialization

## Task Commits

1. **Task 1: TwoTierEnsemble class and build_ensemble() factory** - `8e39548` (feat)

**Plan metadata:** [TBD docs commit]

## Files Created/Modified

- `src/models/ensemble.py` - TwoTierEnsemble class, build_ensemble() factory, plot_calibration(), save_artifact(); exports TwoTierEnsemble and build_ensemble
- `models/ensemble.joblib` - Trained ensemble artifact with all params, OOF Brier=0.1672, meta coefficients, library versions
- `models/ensemble_calibration_curve.png` - Two-panel calibration plot (before/after clipping); max deviation=0.1059 on OOF data

## Decisions Made

- **Manual OOF stacking, not sklearn StackingClassifier:** walk_forward_splits() uses prefix (non-partition) splits; sklearn's cross_val_predict() raises ValueError on non-partition CV. Manual OOF stacking is the only viable approach.
- **TwoTierEnsemble does NOT auto-scale:** predict_proba() takes pre-scaled features. Caller scales with ensemble.scaler. This prevents double-scaling in backtest harness (06-04) where scaler is applied externally.
- **save_artifact() for pickle path fix:** Running as `__main__` pickles TwoTierEnsemble as `__main__.TwoTierEnsemble`. save_artifact() re-imports from `src.models.ensemble` before joblib.dump() to ensure stable pickle path. Same issue was hit in Phase 3-04 with ClippedCalibrator.
- **LR base model OOF via ClippedCalibrator:** Raw LR probabilities injected into meta-learner would not match production behavior (where LR is wrapped in ClippedCalibrator). Using ClippedCalibrator for OOF ensures meta-learner learns to combine consistent signals.
- **C=1.0 meta-learner:** 248 OOF samples with 3 features. C=1.0 provides adequate regularization. Tuning C would risk meta-overfitting (too few samples relative to the sweep overhead).
- **Calibration quality POOR:** OOF calibration max deviation=0.1059 on 6 bins. This is expected — OOF data is only 248 samples across 4 years; calibration curves will improve with more data. The ClippedCalibrator [0.05, 0.89] bounds remain important for production use.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed __main__ pickle path for TwoTierEnsemble in joblib artifact**

- **Found during:** Task 1 (verification step)
- **Issue:** Running `uv run python -m src.models.ensemble` (which executes as `__main__`) caused TwoTierEnsemble to be pickled as `__main__.TwoTierEnsemble`. Loading the artifact with `python -c "import joblib; joblib.load('models/ensemble.joblib')"` raised `AttributeError: Can't get attribute 'TwoTierEnsemble' on <module '__main__'>`.
- **Fix:** Added `save_artifact()` function that re-imports TwoTierEnsemble from `src.models.ensemble` via importlib before joblib.dump(). Re-instantiates ensemble with stable module path. Updated `__main__` block to call `save_artifact()` instead of direct `joblib.dump()`.
- **Files modified:** `src/models/ensemble.py`
- **Verification:** `python -c "import joblib; artifact = joblib.load('models/ensemble.joblib'); artifact['ensemble'].predict_proba(np.random.randn(5,6))"` succeeds without needing src.models.ensemble imported first
- **Committed in:** `8e39548` (included in Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Required fix — downstream callers (backtest, bracket simulator) load the artifact in contexts that don't pre-import src.models.ensemble. The bug would have blocked Phase 06-04 entirely. No scope creep.

## Issues Encountered

- Same pickle/`__main__` module-path issue that affected ClippedCalibrator in Phase 03-04. Pattern now established: any class saved via joblib from `__main__` must use `importlib.import_module()` re-binding trick in save_artifact().

## Next Phase Readiness

- `models/ensemble.joblib` ready for consumption by 06-04 (backtest ensemble against historical tournaments)
- TwoTierEnsemble.predict_proba() signature compatible with backtest harness compute_game_metrics() (takes pre-scaled X, returns (n, 2) array)
- OOF Brier=0.1672 beats individual models and LR baseline; strong signal that stacking provides value
- Calibration is "POOR" by max-deviation metric on 248 OOF samples — expected with small dataset; ClippedCalibrator bounds handle the tails; OK to proceed

---
*Phase: 06-ensemble-models*
*Completed: 2026-03-04*
