---
phase: 08-feature-store
plan: 01
subsystem: feature-engineering
tags: [features, team-resolution, api, pytest, statsmodels, cutoff-dates]

dependency-graph:
  requires:
    - 01-historical-data-pipeline (team_normalization.parquet)
    - 02-current-season-and-bracket-data (cutoff_dates.py SELECTION_SUNDAY_DATES)
    - 03-baseline-model (FEATURE_COLS, build_stats_lookup)
  provides:
    - Public name-based compute_features() API with as_of_date validation
    - Internal _compute_features_by_id() for ID-based callers
    - _resolve_team_id() with team name -> kaggle_team_id resolution
    - pytest and statsmodels dependencies for Phase 8 testing
  affects:
    - 08-02 and later plans that import compute_features() by name

tech-stack:
  added:
    - pytest>=9.0.2
    - statsmodels>=0.14.6
  patterns:
    - Module-level lazy cache (_TEAM_NAME_LOOKUP) for name lookup performance
    - Public/internal API separation (compute_features vs _compute_features_by_id)
    - as_of_date validation against SELECTION_SUNDAY_DATES dict values

key-files:
  created: []
  modified:
    - src/models/features.py
    - src/backtest/backtest.py
    - src/simulator/bracket_schema.py
    - pyproject.toml
    - uv.lock

decisions:
  - id: "08-01-a"
    decision: "as_of_date validated against SELECTION_SUNDAY_DATES.values() (date strings), not keys (season ints) -- callers pass YYYY-MM-DD strings, not season years"
  - id: "08-01-b"
    decision: "Torvik snapshot satisfies cutoff by construction (cbbdata archive endpoint) -- no re-filtering of stats_lookup needed in compute_features(); as_of_date is a validation-only parameter"
  - id: "08-01-c"
    decision: "_TEAM_NAME_LOOKUP is a module-level cache; invalidated only on process restart -- acceptable for CLI and test usage; no invalidation mechanism needed"
  - id: "08-01-d"
    decision: "Name resolution covers canonical_name, kaggle_name, cbbdata_name columns only (espn_name excluded per decision [02-02] -- 317/381 empty strings)"

metrics:
  duration: "~3 min"
  completed: "2026-03-04"
  tasks-completed: 2
  tasks-total: 2
---

# Phase 8 Plan 01: Feature Store Public API Summary

**One-liner:** Name-based `compute_features(team_a, team_b, season)` API wrapping `_compute_features_by_id()` with team name resolution from team_normalization.parquet and `as_of_date` validation against SELECTION_SUNDAY_DATES.

## What Was Built

Two tasks executed:

**Task 1: Dependencies + pytest config**
- `uv add pytest>=9.0.2 statsmodels>=0.14.6` (6 packages installed: pytest, statsmodels, patsy, pluggy, pygments, iniconfig)
- Added `[tool.pytest.ini_options]` to pyproject.toml with `testpaths=["tests"]`, `pythonpath=["."]`, `addopts="-v"`

**Task 2: Name-based compute_features() API**
- Renamed existing `compute_features()` to `_compute_features_by_id()` -- same 4-arg signature, same behavior
- Added `_TEAM_NAME_LOOKUP: dict[str, int] | None = None` module-level cache
- Added `_get_name_lookup(processed_dir)` -- reads team_normalization.parquet via DuckDB, maps canonical_name/kaggle_name/cbbdata_name to kaggle_team_id; skips empty strings per decision [02-02]
- Added `_resolve_team_id(name, processed_dir)` -- raises `ValueError` with example valid names if not found
- Added public `compute_features(team_a, team_b, season, stats_lookup, processed_dir, as_of_date)` API:
  - Validates `as_of_date` against `SELECTION_SUNDAY_DATES.values()` if provided
  - Resolves team_a and team_b to IDs via `_resolve_team_id()`
  - Builds stats_lookup if not provided
  - Delegates to `_compute_features_by_id()`
- Updated `build_matchup_dataset()` to call `_compute_features_by_id()` internally
- Updated `backtest.py`: replaced `compute_features` import with `_compute_features_by_id`; updated 2 call sites (baseline predict_fn and ensemble predict_fn)
- Updated `bracket_schema.py`: replaced `compute_features` import with `_compute_features_by_id`; updated 1 call site in `build_predict_fn()`

## Verification Results

| Check | Result |
|-------|--------|
| `compute_features("Duke", "Michigan", 2025)` returns 6-key dict | PASS |
| `compute_features(..., as_of_date="2025-03-16")` returns same dict | PASS (identical values) |
| `compute_features(..., as_of_date="2099-01-01")` raises ValueError | PASS |
| Unknown team name raises ValueError with helpful message | PASS |
| `_compute_features_by_id(2025, 1181, 1276, sl)` returns same dict | PASS |
| `build_matchup_dataset()` builds 1054 matchups, no errors | PASS |
| `python -m src.simulator.bracket_schema` exits 0 | PASS |
| `import pytest` prints 9.0.2 | PASS |
| `import statsmodels` prints 0.14.6 | PASS |

## Sample Output

```
compute_features("Duke", "Michigan", 2025) →
{
  'adjoe_diff': 13.332197927203993,
  'adjde_diff': -3.1437300045644037,
  'barthag_diff': 0.07351311615879397,
  'seed_diff': -4,
  'adjt_diff': -3.7158273601246066,
  'wab_diff': 3.356028168568991
}
```

Duke (seed 1) vs Michigan (seed 5): Duke has +13.3 adj offensive efficiency advantage and -4 seed difference (Duke = better seed = lower SeedNum), matching expected directions from decision [03-01].

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 08-01-a | Validate as_of_date against SELECTION_SUNDAY_DATES.values() (YYYY-MM-DD strings) | Callers naturally pass date strings; season-based lookup would require extra parsing |
| 08-01-b | as_of_date is validation-only; no re-filtering of stats_lookup | Torvik snapshots satisfy cutoff by construction (Pattern 3 from research doc) |
| 08-01-c | _TEAM_NAME_LOOKUP is a module-level cache; no invalidation | CLI/test usage restarts process; acceptable performance tradeoff |
| 08-01-d | Name resolution excludes espn_name | 317/381 entries are empty strings per decision [02-02] |

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

- Phase 08-02 can import `compute_features(team_a, team_b, season)` directly
- The `_compute_features_by_id()` internal API is unchanged; all existing callers (backtest, simulator) work without behavioral changes
- pytest is now available for test authoring in subsequent plans
- statsmodels is available for regression/calibration analysis in Phase 8
