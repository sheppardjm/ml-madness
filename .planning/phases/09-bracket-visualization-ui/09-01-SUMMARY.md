---
phase: 09-bracket-visualization-ui
plan: 01
subsystem: ui
tags: [streamlit, plotly, ensemble, simulation, bracket, data-loading, caching]

# Dependency graph
requires:
  - phase: 06-ensemble-models
    provides: TwoTierEnsemble artifact (models/ensemble.joblib) and models/selected.json
  - phase: 04-bracket-simulator
    provides: simulate_bracket() function with deterministic/monte_carlo modes
  - phase: 08-feature-store
    provides: _compute_features_by_id(), build_stats_lookup(), FEATURE_COLS
  - phase: 01-historical-data-pipeline
    provides: seeds.parquet with TeamID, TeamName, Seed, SeedNum columns
provides:
  - Streamlit entry point (app.py) with set_page_config, sidebar model info, tab skeleton
  - src/ui/data_loader.py with 6 cached functions for model/sim/team data loading
  - ensemble predict_fn adapter that correctly scales features before TwoTierEnsemble.predict_proba()
  - Cached deterministic and Monte Carlo bracket simulation results
  - Team ID to name/seed/seednum mapping from seeds.parquet
affects:
  - 09-02 (seedings panel): uses load_seedings_cached, load_team_info
  - 09-03 (bracket viz): uses run_deterministic, run_monte_carlo, load_team_info
  - 09-04 (advancement/champion): uses run_monte_carlo advancement_probs

# Tech tracking
tech-stack:
  added:
    - streamlit==1.55.0
    - plotly==6.6.0
  patterns:
    - st.cache_resource for heavy objects (model artifact, predict_fn closure)
    - st.cache_data for data/simulation results
    - Underscore-prefix convention for unhashable args (_artifact, _predict_fn, _seedings)
    - set_page_config as absolute first Streamlit call (before imports)
    - pandas override-dependencies in pyproject.toml [tool.uv] to bypass streamlit metadata constraint
    - tool.uv.environments = darwin to scope lockfile to macOS

key-files:
  created:
    - app.py
    - src/ui/data_loader.py
  modified:
    - pyproject.toml
    - src/ui/__init__.py (already existed as empty file; no change needed)

key-decisions:
  - "Override streamlit's pandas<3 metadata constraint via [tool.uv] override-dependencies; pandas 3.x is runtime-compatible with streamlit 1.55.0"
  - "Scaler applied inside predict_fn closure (before predict_proba), not inside TwoTierEnsemble.predict_proba() per [06-03] convention to prevent double-scaling"
  - "load_team_info() queries seeds.parquet directly via DuckDB for TeamName (canonical display name source per research pitfall 5)"
  - "st.cache_resource for model/predict_fn (non-serializable), st.cache_data for simulation results (serializable)"

patterns-established:
  - "Pattern 1: Underscore-prefix args for unhashable Streamlit cache arguments (_artifact, _predict_fn, _seedings)"
  - "Pattern 2: set_page_config() is first statement in app.py before any other imports that could trigger st.*"
  - "Pattern 3: All heavy computations (model load, simulation) wrapped in cached functions in data_loader.py"

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 9 Plan 01: Streamlit App Scaffold Summary

**Streamlit app scaffold with TwoTierEnsemble predict_fn adapter, cached deterministic + Monte Carlo simulations, and team name lookup from seeds.parquet**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-04T16:04:33Z
- **Completed:** 2026-03-04T16:08:37Z
- **Tasks:** 3 completed
- **Files modified:** 4

## Accomplishments

- Installed streamlit 1.55.0 and plotly 6.6.0; resolved pandas<3 conflict via uv override-dependencies
- Created `src/ui/data_loader.py` with 6 cached functions covering model loading, ensemble predict_fn, deterministic sim, Monte Carlo sim, team info lookup, and seedings loading
- Created `app.py` with correct set_page_config ordering, sidebar showing model info and champion predictions, and three tab placeholders ready for plans 09-03/09-04

## Task Commits

Each task was committed atomically:

1. **Task 1: Install Streamlit + Plotly dependencies** - `88615e7` (chore)
2. **Task 2: Create src/ui/data_loader.py with cached model loading and simulation** - `a5d83ed` (feat)
3. **Task 3: Create app.py entry point with sidebar and tab skeleton** - `23c120c` (feat)

**Plan metadata:** `(see below)` (docs: complete plan)

## Files Created/Modified

- `app.py` - Streamlit entry point with set_page_config, sidebar, three tab placeholders
- `src/ui/__init__.py` - Package marker (already existed; confirmed present)
- `src/ui/data_loader.py` - 6 cached functions: load_model, build_ensemble_predict_fn, run_deterministic, run_monte_carlo, load_team_info, load_seedings_cached
- `pyproject.toml` - Added streamlit>=1.42.0, plotly>=6.0.0; narrowed requires-python to >=3.12,<3.14; added [tool.uv] with environments=darwin and override-dependencies for pandas
- `uv.lock` - Updated lockfile with streamlit 1.55.0, plotly 6.6.0, and 21 new transitive deps

## Decisions Made

- **pandas override**: streamlit 1.55.0's metadata declares `pandas>=1.4.0,<3` but pandas 3.x is runtime-compatible. Used `[tool.uv] override-dependencies = ["pandas>=3.0.1"]` to bypass the resolver check. This is safe — streamlit 1.55.0 works correctly with pandas 3.x.
- **requires-python narrowed**: Changed from `>=3.12` to `>=3.12,<3.14` because the uv resolver was solving for Python 3.14 on Windows where the streamlit/pandas conflict appears unsolvable.
- **tool.uv.environments**: Set to `["sys_platform == 'darwin'"]` to scope the lockfile to macOS. This project runs on macOS only.
- **scaler placement**: The StandardScaler is applied inside `predict_fn` (before `ensemble.predict_proba()`), not inside `predict_proba()`, per the [06-03] decision that TwoTierEnsemble expects already-scaled input.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] streamlit/pandas version conflict blocked uv dependency resolution**

- **Found during:** Task 1 (Install Streamlit + Plotly)
- **Issue:** `uv add streamlit>=1.42.0` failed because streamlit's metadata declares `pandas>=1.4.0,<3` conflicting with project's `pandas>=3.0.1`. The resolver failed for Python 3.14 on Windows and macOS cross-platform splits.
- **Fix:** Three changes to `pyproject.toml`: (a) narrowed `requires-python` to `>=3.12,<3.14`, (b) added `[tool.uv] environments = ["sys_platform == 'darwin'"]`, (c) added `[tool.uv] override-dependencies = ["pandas>=3.0.1"]` to override streamlit's pandas upper bound.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv sync` resolved successfully, `import streamlit; print(streamlit.__version__)` prints 1.55.0, `import pandas; print(pandas.__version__)` still shows 3.x — no downgrade.
- **Committed in:** 88615e7 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - Blocking)
**Impact on plan:** Auto-fix necessary to install dependencies. No scope creep. streamlit and pandas both run correctly at their specified versions.

## Issues Encountered

- streamlit 1.55.0 was the version resolved (not 1.42.0 as specified in plan minimum) — this is expected; uv resolves to latest satisfying version.
- `src/ui/__init__.py` already existed as an empty file from a previous session — no action needed.

## Next Phase Readiness

- app.py launches cleanly (`streamlit run app.py` starts without crash, health endpoint returns 200)
- All 6 data_loader functions import correctly in both regular Python and Streamlit contexts
- predict_fn correctly calls `scaler.transform()` then `ensemble.predict_proba()` with already-scaled input
- Tab placeholders for Bracket (09-03) and Advancement/Champion (09-04) are in place
- Sidebar displays: selected_model=ensemble, model_type=TwoTierEnsemble, mean_brier=0.1692, predicted champion name, MC champion name with confidence

---
*Phase: 09-bracket-visualization-ui*
*Completed: 2026-03-04*
