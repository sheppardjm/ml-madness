---
phase: 06-ensemble-models
plan: 02
subsystem: modeling
tags: [lightgbm, optuna, gradient-boosting, temporal-cv, hyperparameter-tuning, brier-score]

# Dependency graph
requires:
  - phase: 03-baseline-model-and-temporal-validation
    provides: walk_forward_splits(), FEATURE_COLS, build_matchup_dataset(), LR baseline Brier=0.1900
  - phase: 05-backtesting-harness
    provides: confirmed benchmark Brier=0.1900, validated temporal isolation

provides:
  - LightGBM training pipeline with Optuna hyperparameter sweep (run_optuna_sweep_lgb)
  - Per-year Brier and log-loss evaluation (evaluate_lgb)
  - Best LightGBM hyperparameters: num_leaves=12, n_estimators=188, lr=0.0131, min_child_samples=15
  - Confirmed LightGBM mean Brier=0.1931 across 2022-2025 (within 0.003 of LR baseline)

affects:
  - 06-03-neural-network (wave 2; will merge LGB predictions into stacking ensemble)
  - 06-04-stacking-ensemble (directly consumes lgb_params.json for base model instantiation)
  - 06-05-ensemble-validation (uses evaluate_lgb() for final comparison table)

# Tech tracking
tech-stack:
  added:
    - lightgbm==4.6.0 (arm64 dylib fixed via libomp copy to uv Python lib dir)
  patterns:
    - "Same Optuna + walk-forward temporal CV pattern as XGBoost (06-01): minimize mean Brier across 4 folds"
    - "LightGBM class imbalance: class_weight='balanced' (not scale_pos_weight — that's XGBoost)"
    - "Suppress LightGBM output with verbose=-1 (not verbosity=0 — that's XGBoost)"
    - "Suppress sklearn feature-name warnings with warnings.filterwarnings inside predict_proba calls"

key-files:
  created:
    - src/models/train_lightgbm.py
    - models/lgb_params.json
  modified:
    - pyproject.toml (lightgbm dependency)
    - uv.lock

key-decisions:
  - "LightGBM mean Brier=0.1931 vs LR baseline 0.1900 (+0.0031 delta) -- expected; XGBoost/LGB base models slightly worse individually but gain from ensemble diversity"
  - "num_leaves=12 (far below max 60) -- Optuna found low-complexity model optimal for ~1000-sample dataset"
  - "arm64 libomp fix: copied arm64 libomp.dylib from Adobe Acrobat to uv Python lib dir (/Users/Sheppardjm/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/lib/); Intel Homebrew at /usr/local doesn't have arm64 version"
  - "verbose=-1 used (not verbosity=0 which is XGBoost) -- LightGBM-specific parameter"

patterns-established:
  - "LightGBM sklearn API: use class_weight='balanced' for imbalanced classification (71/29 split)"
  - "libomp fix pattern for arm64 Mac with Intel Homebrew: copy arm64 libomp to uv Python lib dir"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 6 Plan 02: LightGBM Training Pipeline Summary

**LightGBM with 50-trial Optuna sweep over 8 hyperparameters, walk-forward CV, class_weight='balanced'; best Brier=0.1931 (num_leaves=12, n_estimators=188)**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T05:42:15Z
- **Completed:** 2026-03-04T05:44:30Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Created `src/models/train_lightgbm.py` with `run_optuna_sweep_lgb()` and `evaluate_lgb()` following same temporal CV pattern as train_logistic.py
- Completed 50-trial Optuna sweep across 8 hyperparameters constrained for ~1000-sample dataset (num_leaves [10,60], min_child_samples [10,30])
- LightGBM mean Brier = 0.1931 across 2022-2025 (+0.003 vs LR baseline 0.1900 -- close, as expected for single base model)
- Saved best hyperparameters to `models/lgb_params.json` for stacking ensemble consumption
- Fixed arm64 libomp missing dependency blocking LightGBM import on this machine

## Task Commits

Each task was committed atomically:

1. **Task 1: Create LightGBM training pipeline with Optuna sweep** - `d1cf316` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/models/train_lightgbm.py` - LightGBM Optuna sweep pipeline; exports run_optuna_sweep_lgb() and evaluate_lgb()
- `models/lgb_params.json` - Best hyperparameters from 50-trial Optuna sweep
- `pyproject.toml` - lightgbm>=4.6.0 dependency added
- `uv.lock` - Updated lockfile

## Decisions Made

- **LightGBM mean Brier=0.1931 vs baseline 0.1900:** +0.0031 delta expected -- individual gradient boosting models often slightly underperform logistic regression on small datasets; ensemble diversity (not individual performance) is the goal
- **Optuna found num_leaves=12:** Far below the max 60 ceiling -- confirms small dataset needs very shallow trees; overfitting risk is real with deeper trees
- **class_weight='balanced':** LightGBM native support; unlike XGBoost (which needs scale_pos_weight), LightGBM handles this directly in the classifier constructor
- **verbose=-1:** LightGBM-specific parameter to suppress per-iteration output; XGBoost uses verbosity=0 (different API)
- **arm64 libomp fix:** Intel Homebrew at /usr/local has x86_64 libomp; arm64 Python (uv-managed) needs arm64 libomp; solution was copying from Adobe Acrobat's bundled arm64 libomp to uv's Python lib directory

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] arm64 libomp missing for LightGBM binary**
- **Found during:** Task 1 (initial LightGBM import test)
- **Issue:** LightGBM arm64 binary requires `/opt/homebrew/opt/libomp/lib/libomp.dylib` but machine has Intel Homebrew at `/usr/local` with x86_64 libomp; no arm64 libomp available from Homebrew
- **Fix:** Located arm64 libomp.dylib bundled with Adobe Acrobat (`/Applications/Adobe Acrobat DC/Adobe Acrobat.app/Contents/Frameworks/libomp.dylib`); copied to uv Python lib dir (`/Users/Sheppardjm/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/lib/libomp.dylib`) which is in LightGBM's rpath search list
- **Files modified:** /Users/Sheppardjm/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/lib/libomp.dylib (added, not tracked in git)
- **Verification:** `import lightgbm; print(lightgbm.__version__)` returns `4.6.0`
- **Committed in:** d1cf316 (Task 1 commit includes pyproject.toml/uv.lock)

**2. [Rule 1 - Bug] Suppressed noisy sklearn feature-name warnings**
- **Found during:** Task 1 (first training run)
- **Issue:** sklearn 1.8 warns "X does not have valid feature names, but LGBMClassifier was fitted with feature names" for every predict_proba() call when numpy arrays are passed; noisy output masking real errors
- **Fix:** Added `warnings.filterwarnings("ignore", message="X does not have valid feature names", ...)` around predict_proba() calls in both run_optuna_sweep_lgb() and evaluate_lgb()
- **Files modified:** src/models/train_lightgbm.py
- **Verification:** Re-run shows clean output without spurious warnings
- **Committed in:** d1cf316 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correct operation and clean output. No scope creep.

## Issues Encountered

- LightGBM binary is arm64 but machine's Homebrew is Intel (x86_64), creating a libomp architecture mismatch. Fixed via arm64 libomp from Adobe Acrobat. This is a machine-specific issue; any fresh arm64 Mac with Apple Silicon Homebrew at /opt/homebrew would not have this problem.

## Next Phase Readiness

- `src/models/train_lightgbm.py` ready for import by stacking ensemble (06-04)
- `models/lgb_params.json` with best hyperparameters saved and validated
- LightGBM Brier=0.1931 close to baseline; ensemble diversity (XGB + LGB + LR) is the path to beating 0.1900
- 06-01 (XGBoost) and 06-02 (LightGBM) are the two wave-1 plans; both should be complete before wave-2 proceeds

---
*Phase: 06-ensemble-models*
*Completed: 2026-03-04*
