---
phase: 08-feature-store
plan: 03
subsystem: testing
tags: [pytest, vif, features, symmetry, cutoff, statsmodels, conftest]

# Dependency graph
requires:
  - phase: 08-01
    provides: compute_features() name-based public API, _compute_features_by_id(), build_stats_lookup(), FEATURE_COLS, _TEAM_NAME_LOOKUP cache
  - phase: 08-02
    provides: compute_vif() function, models/vif_report.json artifact, VIF threshold analysis

provides:
  - pytest test suite for the feature store API (22 tests, 0 failures)
  - SC-1 coverage: known matchup sign tests and approximate value ranges for Duke/Michigan 2025
  - SC-2 coverage: barthag_diff VIF > 10 asserted, all others < 10 asserted, vif_report.json structure verified
  - SC-3 coverage: as_of_date='2025-03-16' tested explicitly; invalid as_of_date raises ValueError
  - SC-4 coverage: symmetry feats(A,B) + feats(B,A) == 0 for 3 team pairs across 3 seasons
  - Error handling tests: unknown team (ValueError), missing season (KeyError)
affects:
  - Future feature store changes must keep all 22 tests passing
  - Any changes to compute_features signature or behavior trigger regression failures
  - Phase 9 (UI) can run pytest as a smoke test before deployment

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Session-scoped stats_lookup fixture built once per run (not per test)
    - autouse reset_name_cache fixture prevents _TEAM_NAME_LOOKUP cross-test pollution
    - Module-scoped matchup_df fixture for expensive dataset builds within a module
    - Parametrized sign tests for readable test naming via pytest.mark.parametrize

key-files:
  created:
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_features.py
    - tests/test_vif.py
  modified: []

key-decisions:
  - "seed_diff returns int (not float) from _compute_features_by_id because stats_lookup stores seed_num as int; relaxed isinstance check to (int, float) in test"
  - "Plan team IDs Houston=1220 and UCLA=1437 were wrong (1220=Hofstra, 1437=Villanova); used correct IDs Houston=1222, UCLA=1417 with canonical names 'Houston' and 'UCLA'"
  - "Gonzaga/UCLA 2024 and Houston/Alabama 2023 chosen for symmetry multi-pair test; Houston/Alabama 2023 has seed_diff=0 (both seed 1) but symmetry still holds"

patterns-established:
  - "Fixture scope hierarchy: session (stats_lookup), module (matchup_df), function (default)"
  - "autouse fixtures for cache reset prevent silent cross-test state contamination"
  - "Parametrized sign tests document expected model behavior as executable specification"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 8 Plan 03: Feature Store Test Suite Summary

**Pytest suite for feature store: 22 tests covering SC-1 through SC-4 using Duke/Michigan/Gonzaga/UCLA/Houston/Alabama fixtures with session-scoped fixtures for performance**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T14:46:42Z
- **Completed:** 2026-03-04T14:48:54Z
- **Tasks:** 3
- **Files created:** 4

## Accomplishments

- Created full pytest test suite (22 tests) covering all four Phase 8 success criteria: known matchup fixtures (SC-1), VIF thresholds (SC-2), as_of_date cutoff enforcement (SC-3), and perspective symmetry (SC-4)
- Session-scoped `stats_lookup` fixture avoids rebuilding expensive lookup per test; `reset_name_cache` autouse fixture prevents cross-test pollution via `_TEAM_NAME_LOOKUP`
- Module-scoped `matchup_df` fixture in test_vif.py avoids repeated dataset builds for the 5 VIF tests
- All 22 tests pass with `uv run pytest tests/ -v` in ~0.5s

## Task Commits

1. **Task 1: Create test infrastructure and conftest.py** - `b210a59` (chore)
2. **Task 2: Create test_features.py covering SC-1, SC-3, SC-4** - `a085feb` (test)
3. **Task 3: Create test_vif.py covering SC-2** - `13150b7` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `tests/__init__.py` - Empty package marker for pytest test discovery
- `tests/conftest.py` - Shared fixtures: session-scoped `stats_lookup`, autouse `reset_name_cache`
- `tests/test_features.py` - 17 tests: SC-1 sign/value/id-match, SC-3 as_of_date, SC-4 symmetry, error handling
- `tests/test_vif.py` - 5 tests: SC-2 VIF thresholds, vif_report.json artifact validation

## Decisions Made

- `seed_diff` is returned as `int` (not `float`) from `_compute_features_by_id()` because `seed_num` is stored as `int` in the stats_lookup dict; relaxed `isinstance` check to `(int, float)` since the plan's intent was "not None or NaN" not strict float typing
- Plan specified Houston=1220, UCLA=1437 as team IDs -- these are incorrect (1220=Hofstra, 1437=Villanova); corrected to Houston=1222 and UCLA=1417 which map to canonical names "Houston" and "UCLA"

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect plan-specified team IDs for Houston and UCLA**

- **Found during:** Task 2 (test_features.py symmetry multi-pair test)
- **Issue:** Plan specified Houston=1220 and UCLA=1437, but those IDs map to Hofstra and Villanova respectively; using wrong IDs would make tests use incorrect teams silently
- **Fix:** Queried team_normalization.parquet to confirm correct IDs (Houston=1222, UCLA=1417) and used canonical names "Houston" and "UCLA" in parametrize arguments
- **Files modified:** tests/test_features.py
- **Verification:** `compute_features("Houston", "Alabama", 2023)` and `compute_features("Gonzaga", "UCLA", 2024)` resolve correctly; symmetry holds
- **Committed in:** a085feb (Task 2 commit)

**2. [Rule 1 - Bug] seed_diff type assertion too strict (int vs float)**

- **Found during:** Task 2 (test_compute_features_returns_all_keys)
- **Issue:** Test asserted `isinstance(val, float)` but `seed_diff` returns `int` (-4) because `stats_lookup["seed_num"]` stores integer seed numbers; test failed with "AssertionError: Value for seed_diff is not float: <class 'int'>"
- **Fix:** Changed assertion to `isinstance(val, (int, float))` with separate `math.isfinite` and `math.isnan` checks
- **Files modified:** tests/test_features.py
- **Verification:** All 17 test_features.py tests pass
- **Committed in:** a085feb (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes correct silent errors in the plan spec. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 22 tests pass; feature store is fully tested with regression protection
- Phase 08 is now complete (08-01 API, 08-02 VIF, 08-03 test suite)
- Any future changes to `compute_features()` signature or `_compute_features_by_id()` behavior will be caught immediately
- Phase 9 (UI) can use `uv run pytest tests/` as a pre-deployment smoke test

---
*Phase: 08-feature-store*
*Completed: 2026-03-04*
