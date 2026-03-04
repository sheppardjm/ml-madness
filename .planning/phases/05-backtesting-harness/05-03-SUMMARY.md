---
phase: 05-backtesting-harness
plan: "03"
subsystem: backtesting
tags: [logistic-regression, walk-forward-cv, espn-scoring, brier-score, temporal-isolation, validation, json]

# Dependency graph
requires:
  - phase: 05-02
    provides: backtest() orchestrator, backtest/results.json
  - phase: 03-03
    provides: evaluation_results.json (Phase 3 benchmark Brier scores per year)
  - phase: 03-01
    provides: build_matchup_dataset() for temporal isolation check

provides:
  - "validate_phase5() callable that runs all 4 Phase 5 success criteria"
  - "Temporal isolation hard assert: max(train_df.Season) == 2024 for 2025 fold"
  - "Brier cross-reference: backtest per-year scores match evaluation_results.json to 7 decimal places (delta=0)"
  - "Reproducibility verified: re-run backtest() produces 0 differences in per_year data"
  - "BACK-01: 2025 ESPN score 1200 in [1100,1300]; bracket breakdown printed"
  - "Phase 5: 4/4 criteria PASS"

affects:
  - 06-ensemble-model
  - 07-model-comparison-dashboard

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Variable shadowing guard: loop variables (r_correct, r_total) must not reuse outer-scope counter names (total, passed) -- silent correctness bug"
    - "Reproducibility check: deep copy original per_year before re-run; compare with _compare_per_year() using float tolerance 1e-9"
    - "Dynamic upset counts: read from results dict, never hardcode -- forward-compatible for ensemble model changes"

key-files:
  created:
    - src/backtest/validate.py
  modified: []

key-decisions:
  - "brier_tolerance=1e-4 parameter, but actual delta=0.0 for all 4 years (identical floating-point computation path); 4-decimal requirement well satisfied"
  - "validate_phase5() loads existing results.json and only calls backtest() for C4 reproducibility re-run (not at startup) -- avoids double computation when results already exist"
  - "Fixed variable shadowing bug: inner loop used 'total = per_round_total.get(...)' which overwrote the outer 'total=4' counter, causing summary to print '4/1 criteria PASS'; renamed to r_total"

patterns-established:
  - "validate.py: single callable validate_phase5() runs all criteria, raises AssertionError on failure -- importable for regression testing"
  - "validate.py: _compare_per_year() ignores generated_at (changes each run), compares all numeric fields with 1e-9 float tolerance"

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 5 Plan 03: Phase 5 Validation Summary

**validate_phase5() confirms all 4 criteria: temporal isolation (max train season=2024), Brier delta=0 vs evaluation_results.json, all 4 years present with dynamic upset counts, and reproducible re-run producing 0 differences; 2025 ESPN=1200**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T04:51:19Z
- **Completed:** 2026-03-04T04:54:05Z
- **Tasks:** 1 of 1
- **Files modified:** 1

## Accomplishments

- Implemented `validate_phase5()` in `src/backtest/validate.py` with all 4 Phase 5 success criteria plus BACK-01 validation
- Temporal isolation hard assert: `assert max(train_df['Season']) == 2024` passes with confidence (actually 2024 confirmed)
- Brier cross-reference against `evaluation_results.json` shows exact 0.0 delta for all 4 years -- same computation path
- Reproducibility: re-running `backtest()` produces 0 differences in `per_year` data (float comparison 1e-9)
- 2025 ESPN score 1200/1920 (62.5%) confirmed in [1100, 1300]

## Task Commits

Each task was committed atomically:

1. **Task 1: validate_phase5() with all 4 Phase 5 success criteria** - `77e3f48` (feat)

**Plan metadata:** _(see final metadata commit)_

## Files Created/Modified

- `src/backtest/validate.py` - `validate_phase5()`, `_load_or_run_backtest()`, `_compare_per_year()`, `__main__` block

## Decisions Made

- **brier_tolerance=1e-4 parameterized but delta=0**: Actual Brier comparison shows exact floating-point equality (delta=0.00e+00 for all 4 years), because both backtest() and evaluation_results.json run the same walk-forward computation with random_state=42. The tolerance parameter provides flexibility for future model variants.
- **Only run backtest() for C4**: C1-C3 load existing results.json; C4 re-runs backtest() to test reproducibility. Avoids unnecessary double computation at startup.
- **Variable shadowing bug fixed**: Inner per-round loop used `total = per_round_total.get(rname, "?")` which silently overwrote the outer `total=4` counter. Summary printed "4/1 criteria PASS" instead of "4/4". Renamed loop vars to `r_correct` and `r_total`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed variable shadowing: inner loop 'total' overwrote outer 'total=4' counter**

- **Found during:** Task 1 (validate_phase5 implementation) -- discovered when running verification
- **Issue:** The per-round accuracy display loop used `total = per_round_total.get(rname, "?")` in loop body, which reassigned the outer-scope `total = 4` variable. After the loop, `total` held the Championship round count (1), causing the summary to print "Phase 5: 4/1 criteria PASS"
- **Fix:** Renamed loop variables to `r_correct` and `r_total` to avoid shadowing the outer counter
- **Files modified:** `src/backtest/validate.py`
- **Verification:** Summary now prints "Phase 5: 4/4 criteria PASS"
- **Committed in:** `77e3f48` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minor bug fix -- correctness of display output only, all assertions were passing correctly.

## Issues Encountered

None beyond the variable shadowing bug (documented above).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 5 complete: all 4 success criteria PASS
- `validate_phase5()` is importable as regression test for Phase 6 ensemble model changes
- `backtest/results.json` is authoritative Phase 5 benchmark (mean_brier=0.1900, mean_ESPN=912.5)
- Phase 6 ensemble model must beat mean_brier=0.1900 on the same walk-forward protocol

---
*Phase: 05-backtesting-harness*
*Completed: 2026-03-03*
