---
phase: 08-feature-store
plan: 02
subsystem: modeling
tags: [vif, multicollinearity, statsmodels, variance_inflation_factor, feature_validation, sc2]

# Dependency graph
requires:
  - phase: 03-baseline-model-and-temporal-validation
    provides: FEATURE_COLS canonical feature set locked by decision [03-01]
  - phase: 08-feature-store
    provides: statsmodels>=0.14.6 installed (08-01)
provides:
  - compute_vif() function accepting raw feature matrix and returning VIF DataFrame
  - models/vif_report.json with VIF values, decision, rationale, and sc2_assessment
  - Formal SC-2 compliance documentation for the multicollinearity audit
affects: [09-streamlit-ui, future-model-retraining]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "add_constant(X) must precede variance_inflation_factor() — statsmodels does NOT add intercept internally"
    - "VIF column index in X_with_const is i+1 (index 0 = constant, skip it)"

key-files:
  created:
    - src/models/vif_analysis.py
    - models/vif_report.json
  modified: []

key-decisions:
  - "add_constant(X) is required before calling variance_inflation_factor() despite plan doc saying otherwise — confirmed by empirical validation (adjt_diff VIF=1.0506 only if intercept column present)"
  - "barthag_diff VIF=11.2007 formally documented as EXCEEDS_THRESHOLD with KEEP_ALL decision per [03-01]"
  - "without_barthag scenario included for documentation: removing barthag_diff drops adjoe_diff/adjde_diff VIF from ~6.5/5.8 to 2.8/2.6, confirming the source of multicollinearity"

patterns-established:
  - "VIF pattern: always use add_constant(X, has_constant='add') before variance_inflation_factor(X_with_const, i+1)"
  - "Report pattern: JSON artifact includes both decision rationale and sc2_assessment for audit trail"

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 8 Plan 02: VIF Analysis Summary

**VIF multicollinearity audit on 1054-matchup matrix — barthag_diff VIF=11.2007 documented with KEEP_ALL decision per [03-01]; SC-2 formally satisfied**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-04T14:39:01Z
- **Completed:** 2026-03-04T14:44:00Z
- **Tasks:** 1 of 1 complete
- **Files modified:** 2

## Accomplishments

- `compute_vif()` function correctly applies `add_constant()` and returns DataFrame sorted by VIF descending
- barthag_diff identified as VIF=11.2007 (EXCEEDS_THRESHOLD), all other features below VIF 6.51
- adjt_diff VIF=1.0506 confirms correct intercept handling (sanity check passes)
- `models/vif_report.json` written with all required fields: decision, decision_rationale, sc2_assessment, without_barthag scenario
- SC-2 satisfied: formal VIF analysis conducted, one exceedance documented with accepted rationale

## Task Commits

Each task was committed atomically:

1. **Task 1: Create VIF analysis module** - `45d5d70` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/models/vif_analysis.py` - compute_vif() and run_vif_analysis() functions, CLI runner writing models/vif_report.json
- `models/vif_report.json` - Structured VIF report with barthag_diff=11.2007, KEEP_ALL decision, sc2_assessment, without_barthag sub-dict

## VIF Results

| Feature       | VIF     | Status             |
|---------------|---------|--------------------|
| barthag_diff  | 11.2007 | EXCEEDS_THRESHOLD  |
| adjoe_diff    | 6.5049  | BORDERLINE         |
| adjde_diff    | 5.7924  | BORDERLINE         |
| wab_diff      | 5.2115  | BORDERLINE         |
| seed_diff     | 3.9822  | OK                 |
| adjt_diff     | 1.0506  | OK                 |

Without barthag_diff: adjoe_diff drops to 2.78, adjde_diff to 2.60 — confirms barthag_diff is the source of multicollinearity with the offensive/defensive efficiency features.

## Decisions Made

- **add_constant() required:** The plan stated "do NOT add an intercept column — statsmodels handles intercept internally." This is incorrect. statsmodels' `variance_inflation_factor()` does NOT add an intercept; the caller must add it via `add_constant(X)`. Applied `add_constant(X, has_constant='add')` and adjusted column indices (skip index 0 = constant). Validated by adjt_diff VIF=1.0506 (would be 0 or NaN without proper intercept handling).
- **KEEP_ALL decision:** barthag_diff is retained per [03-01] locked feature set. Rationale documented: regularized LR (L2 penalty), XGBoost, and LightGBM are all robust to moderate multicollinearity; dropping barthag_diff would require full retraining of all Phase 3-6 models.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected intercept handling for variance_inflation_factor()**

- **Found during:** Task 1 (Create VIF analysis module)
- **Issue:** Plan instructed "Do NOT add an intercept column — statsmodels adds its own internally." This is false. statsmodels' `variance_inflation_factor()` does NOT add an intercept; without `add_constant()`, VIF values are incorrect.
- **Fix:** Used `add_constant(X, has_constant='add')` to prepend a constant column, then passed column indices i+1 (skipping index 0 = constant) to `variance_inflation_factor()`
- **Files modified:** src/models/vif_analysis.py
- **Verification:** adjt_diff VIF=1.0506 (expected ~1.05 for a nearly orthogonal feature); barthag_diff VIF=11.2007 matches pre-computed research value of ~11.2
- **Committed in:** 45d5d70 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug: incorrect statsmodels intercept behavior documented in plan)
**Impact on plan:** Fix was essential for correct VIF values. Without it, VIFs would be wrong and the SC-2 audit meaningless.

## Issues Encountered

The plan contained a factual error about statsmodels' API: "variance_inflation_factor(exog, exog_idx) handles intercept internally" — it does not. The correction was applied immediately per deviation Rule 1 and the note in the plan's own `Accumulated Context` section which correctly stated the fix needed.

## Next Phase Readiness

- SC-2 formally documented in `models/vif_report.json` — ready for Phase 8 remaining plans
- `compute_vif()` is importable from `src.models.vif_analysis` for any future feature analysis
- No blockers for Phase 9 (Streamlit UI) or remaining Phase 8 plans

---
*Phase: 08-feature-store*
*Completed: 2026-03-04*
