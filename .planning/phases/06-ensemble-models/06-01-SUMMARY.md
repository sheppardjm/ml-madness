---
phase: 06-ensemble-models
plan: 01
subsystem: model-training
tags: [xgboost, lightgbm, optuna, temporal-cv, brier-score, hyperparameter-tuning, arm64]

# Dependency graph
requires:
  - phase: 03-baseline-model-and-temporal-validation
    provides: walk_forward_splits(), FEATURE_COLS, build_matchup_dataset(), ClippedCalibrator, LR baseline 0.1900
  - phase: 05-backtesting-harness
    provides: validated temporal isolation and backtest reproducibility

provides:
  - XGBoost Optuna sweep pipeline with walk-forward CV (run_optuna_sweep_xgb)
  - Per-year XGBoost evaluation with Brier and log-loss (evaluate_xgb)
  - Best XGBoost hyperparameters (models/xgb_params.json)
  - xgboost 3.2.0 and lightgbm 4.6.0 installed in project venv

affects:
  - 06-02-lightgbm (lgb already done; xgb completes the parallel base model pair)
  - 06-03-neural-net (third base model)
  - 06-04-stacking-ensemble (consumes xgb_params.json alongside lgb_params.json)
  - 06-05-ensemble-evaluation (uses evaluate_xgb for per-model comparison)

# Tech tracking
tech-stack:
  added: [xgboost==3.2.0, lightgbm==4.6.0]
  patterns:
    - "XGBoost class imbalance via scale_pos_weight per fold (not class_weight)"
    - "arm64 libomp fix: copy MacPorts arm64 libomp.dylib + install_name_tool rpath patch"
    - "Optuna sweep pattern: WARNING verbosity, minimize direction, 50 trials"

key-files:
  created:
    - src/models/train_xgboost.py
    - models/xgb_params.json
  modified:
    - pyproject.toml (xgboost/lightgbm already added in 06-02 commit d1cf316)

key-decisions:
  - "XGBoost uses scale_pos_weight=(y==0).sum()/(y==1).sum() per fold, not class_weight='balanced'"
  - "verbosity=0 (XGBoost) vs verbose=-1 (LightGBM) -- not interchangeable"
  - "arm64 libomp missing on Intel-Homebrew Mac: copy from MacPorts tbz2 + rpath patch"
  - "XGBoost mean Brier 0.1908 vs LR baseline 0.1900 (+0.0008) -- near-baseline, within stacking ensemble range"

patterns-established:
  - "XGBoost pattern: scale_pos_weight per fold, verbosity=0, n_jobs=1, random_state=42"
  - "Both gradient boosting models (XGB + LGB) follow same Optuna+walk-forward pattern"

# Metrics
duration: 8min
completed: 2026-03-04
---

# Phase 06 Plan 01: XGBoost Training Pipeline Summary

**XGBoost 50-trial Optuna sweep with walk-forward CV achieving mean Brier 0.1908 vs LR baseline 0.1900, using scale_pos_weight per fold and arm64 libomp fix on macOS**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-04T05:40:11Z
- **Completed:** 2026-03-04T05:48:18Z
- **Tasks:** 2
- **Files modified:** 3 (pyproject.toml already updated, train_xgboost.py + xgb_params.json created)

## Accomplishments

- XGBoost and LightGBM packages installed and importable (xgboost 3.2.0, lightgbm 4.6.0)
- 50-trial Optuna sweep finds best hyperparameters: n_estimators=98, max_depth=2, lr=0.0813, subsample=0.792, colsample_bytree=0.791, min_child_weight=7, reg_alpha=0.395, reg_lambda=6.803
- evaluate_xgb() logs per-year Brier and log-loss for 2022-2025 compared to LR baseline 0.1900
- scale_pos_weight computed per fold from training labels (no class_weight for XGBoost)
- No test-set leakage: StandardScaler fit on training data only per fold
- arm64 libomp missing on Intel-Homebrew Mac resolved without sudo

## Task Commits

Each task was committed atomically:

1. **Task 1: Install XGBoost and LightGBM dependencies** - `6a8d10a` (chore)
2. **Task 2: Create XGBoost training pipeline with Optuna sweep** - `7d1e00a` (feat)

**Plan metadata:** `(docs commit follows)`

## XGBoost Results

| Year | Brier  | Log-Loss | N Games |
|------|--------|----------|---------|
| 2022 | 0.1898 | 0.5542   | 63      |
| 2023 | 0.2112 | 0.6120   | 63      |
| 2024 | 0.1837 | 0.5443   | 62      |
| 2025 | 0.1787 | 0.5250   | 60      |
| Mean | 0.1908 | 0.5589   |         |

**vs LR baseline: 0.1900 (delta=+0.0008, marginally worse)**

## Files Created/Modified

- `src/models/train_xgboost.py` - XGBoost Optuna sweep and per-year evaluation pipeline; exports run_optuna_sweep_xgb() and evaluate_xgb()
- `models/xgb_params.json` - Best XGBoost hyperparameters from 50-trial Optuna sweep
- `pyproject.toml` - xgboost>=3.2.0 and lightgbm>=4.6.0 dependencies (added in prior 06-02 commit d1cf316)

## Decisions Made

- **XGBoost uses scale_pos_weight, not class_weight**: XGBoost sklearn API does not support `class_weight='balanced'` (it's a LightGBM feature). The XGBoost-native equivalent is `scale_pos_weight = (y==0).sum() / (y==1).sum()` computed per fold.
- **verbosity=0 for XGBoost**: Suppresses per-iteration output. LightGBM uses `verbose=-1` — these are NOT interchangeable.
- **arm64 libomp fix**: System has Intel Homebrew at `/usr/local` (x86_64 libomp) but uv Python is arm64. XGBoost 3.2.0 arm64 wheel links against `/opt/homebrew/opt/libomp/lib/libomp.dylib` which doesn't exist. Fix: download arm64 libomp.dylib from MacPorts (libomp-20.1.6_0.darwin_24.arm64.tbz2), copy to xgboost lib dir, add rpath via `install_name_tool`.
- **Near-baseline XGBoost Brier**: 0.1908 vs 0.1900 (+0.0008). XGBoost alone doesn't beat LR, but this is expected — the value is in stacking (Phase 06-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] arm64 libomp missing for XGBoost 3.2.0 on Intel-Homebrew Mac**

- **Found during:** Task 1 (import verification)
- **Issue:** XGBoost 3.2.0 arm64 wheel links against `/opt/homebrew/opt/libomp/lib/libomp.dylib` which does not exist. System has Intel Homebrew at `/usr/local` with x86_64 libomp (incompatible architecture).
- **Fix:** Downloaded arm64 libomp.dylib from MacPorts package (libomp-20.1.6_0.darwin_24.arm64.tbz2), extracted to `/tmp/libomp-extract`, copied to `.venv/lib/python3.12/site-packages/xgboost/lib/libomp.dylib`, added rpath via `install_name_tool -add_rpath <xgboost_lib_dir> libxgboost.dylib`
- **Files modified:** `.venv/` (gitignored -- not committable; rpath is user-session persistent)
- **Verification:** `import xgboost; print(xgboost.__version__)` returns "3.2.0"
- **Committed in:** 6a8d10a (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Blocking fix required to make XGBoost importable. No scope creep.

## Issues Encountered

- **Note on 06-01 execution order**: pyproject.toml with xgboost/lightgbm dependencies was already committed in a prior 06-02 session (commit d1cf316). Task 1 verified the existing install was correct; no new pyproject.toml changes needed.

## User Setup Required

**Note for fresh environments**: If `.venv` is recreated, the arm64 libomp fix must be reapplied. Steps:
1. `curl -L "https://packages.macports.org/libomp/libomp-20.1.6_0.darwin_24.arm64.tbz2" -o /tmp/libomp-arm64.tbz2`
2. `tar -xjf /tmp/libomp-arm64.tbz2 -C /tmp/libomp-extract`
3. `cp /tmp/libomp-extract/opt/local/lib/libomp/libomp.dylib .venv/lib/python3.12/site-packages/xgboost/lib/libomp.dylib`
4. `install_name_tool -add_rpath "$(pwd)/.venv/lib/python3.12/site-packages/xgboost/lib" .venv/lib/python3.12/site-packages/xgboost/lib/libxgboost.dylib`

This is a macOS arm64 + Intel Homebrew environment issue only.

## Next Phase Readiness

- XGBoost base model ready for Phase 06-04 stacking ensemble
- models/xgb_params.json provides best hyperparameters for ensemble use
- evaluate_xgb() confirms temporal integrity: StandardScaler + scale_pos_weight per fold
- XGBoost Brier (0.1908) close to LR baseline (0.1900) — stacking with LGB (0.1931) and neural net may yield improvement
- No blockers for 06-02 (LightGBM), 06-03 (neural net), or 06-04 (stacking)

---
*Phase: 06-ensemble-models*
*Completed: 2026-03-04*
