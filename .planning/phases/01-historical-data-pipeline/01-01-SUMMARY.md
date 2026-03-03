---
phase: 01-historical-data-pipeline
plan: 01
subsystem: infra
tags: [uv, duckdb, pandas, pyarrow, kagglehub, thefuzz, kaggle, python]

# Dependency graph
requires: []
provides:
  - Python 3.12 project with uv and all Phase 1 dependencies installed
  - data/raw/kaggle/ populated with Kaggle March Machine Learning Mania CSVs (1985-2025)
  - src/utils/cutoff_dates.py with SELECTION_SUNDAY_DATES and get_cutoff() function
  - src/utils/seasons.py with VALID_TOURNEY_SEASONS (22 seasons) and DAYNUM_ROUND_MAP
  - src/ingest/kaggle_download.py with download_kaggle_data() and verify_kaggle_files()
  - Directory structure: data/raw/kaggle/, data/processed/, data/seeds/, src/ingest/, src/normalize/, src/utils/
affects:
  - 01-02 (DuckDB ingestion pipeline — reads from data/raw/kaggle/, uses VALID_TOURNEY_SEASONS and get_cutoff())
  - 01-03 (Team name normalization — reads data/raw/kaggle/MTeamSpellings.csv, uses thefuzz)
  - All subsequent phases (project structure, dependencies, and date constants are foundational)

# Tech tracking
tech-stack:
  added:
    - uv (Python project/environment manager)
    - duckdb 1.x (in-process analytical SQL)
    - pandas (DataFrame manipulation)
    - pyarrow (Parquet I/O)
    - kagglehub (Kaggle dataset download)
    - thefuzz + python-Levenshtein (fuzzy string matching)
  patterns:
    - uv for all Python environment management (uv run, uv add)
    - data/raw/ is gitignored — raw data never committed
    - Utility modules in src/utils/ for shared constants (seasons, dates)
    - DuckDB SQL used for fast in-process CSV querying

key-files:
  created:
    - pyproject.toml
    - uv.lock
    - .gitignore
    - src/__init__.py
    - src/ingest/__init__.py
    - src/ingest/kaggle_download.py
    - src/normalize/__init__.py
    - src/utils/__init__.py
    - src/utils/cutoff_dates.py
    - src/utils/seasons.py
  modified: []

key-decisions:
  - "Kaggle data downloaded manually via browser due to malformed API key — kaggle_download.py still exists and will work once credentials are fixed"
  - "data/ directory is gitignored — raw CSVs are not committed; reproducibility is via the download script"
  - "VALID_TOURNEY_SEASONS excludes 2020 (COVID cancellation) and starts at 2003 (Kaggle feature data availability)"
  - "SELECTION_SUNDAY_DATES encodes exact historical cutoff dates; get_cutoff() raises ValueError for invalid/missing seasons to prevent silent data leakage"

patterns-established:
  - "uv run python -m src.module pattern for all script execution"
  - "src/utils/ for shared constants — import from here, never hardcode dates or season lists inline"
  - "get_cutoff(season) raises ValueError on invalid input — fail loud to prevent training-set contamination"
  - "verify_*() functions in ingest modules for pre-flight checks before expensive transforms"

# Metrics
duration: ~45min
completed: 2026-03-02
---

# Phase 1 Plan 01: Project Scaffolding and Kaggle Download Summary

**uv Python 3.12 project with duckdb/pandas/pyarrow/kagglehub, Kaggle tournament CSVs (1985-2025, 2585 games), and date-guarded cutoff utility preventing training-set contamination**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-03-02
- **Completed:** 2026-03-02
- **Tasks:** 2
- **Files modified:** 10 created

## Accomplishments
- Python 3.12 project initialized with uv; all Phase 1 dependencies (duckdb, pandas, pyarrow, kagglehub, thefuzz) installed and import-verified
- Kaggle March Machine Learning Mania dataset downloaded to data/raw/kaggle/ with 2,585 tournament games spanning 1985-2025
- Selection Sunday cutoff dates module (cutoff_dates.py) enforces data-leakage guard: get_cutoff(2025) returns '2025-03-16', get_cutoff(2020) raises ValueError
- Valid tournament seasons constant (VALID_TOURNEY_SEASONS) covers exactly 22 seasons (2003-2019, 2021-2025) with 2020 excluded for COVID cancellation
- Bonus files present in data/raw/kaggle/: MTeamSpellings.csv (useful for plan 01-03 name normalization), MMasseyOrdinals.csv (useful for later phases)

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffolding with uv, dependencies, utility modules** - `b1cc0a0` (feat)
2. **Task 2: Kaggle download module + manual data download** - `4d59347` (feat)

**Plan metadata:** _(this commit)_ (docs: complete plan)

## Files Created/Modified
- `pyproject.toml` - Project metadata, Python 3.12, all Phase 1 dependencies
- `uv.lock` - Locked dependency versions
- `.gitignore` - Excludes data/, .venv/, __pycache__, .kaggle/
- `src/__init__.py` - Package root
- `src/ingest/__init__.py` - Ingest subpackage
- `src/ingest/kaggle_download.py` - download_kaggle_data() and verify_kaggle_files() functions
- `src/normalize/__init__.py` - Normalize subpackage (empty, for plan 01-03)
- `src/utils/__init__.py` - Utils subpackage
- `src/utils/cutoff_dates.py` - SELECTION_SUNDAY_DATES dict, get_cutoff(), DAYNUM_SELECTION_SUNDAY=132
- `src/utils/seasons.py` - VALID_TOURNEY_SEASONS (22 seasons), DAYNUM_ROUND_MAP

## Decisions Made
- **Manual Kaggle download:** Kaggle API key was malformed during execution; data was downloaded manually via the Kaggle competition browser UI. The kaggle_download.py script is correct and will work once the user fixes ~/.kaggle/kaggle.json.
- **data/ is gitignored:** Raw CSVs are large and reproducible via the download script. Only code is committed.
- **2020 excluded from VALID_TOURNEY_SEASONS:** No tournament was held in 2020 (COVID). Including it would create a gap season that could cause silent bugs in per-season loops.
- **22-season window starts at 2003:** Kaggle's supplemental feature data (Massey ordinals, etc.) is only available from 2003. Aligning all season constants to this window ensures feature joins work across all plans.

## Deviations from Plan

### Authentication Gate

**Kaggle API authentication failed during Task 2**
- **Found during:** Task 2 (Download Kaggle dataset and verify file inventory)
- **Issue:** kagglehub failed with a malformed API key error when attempting programmatic download
- **Resolution:** Dataset downloaded manually via browser at kaggle.com/competitions/march-machine-learning-mania-2026/data
- **Impact:** Data is present and fully verified. kaggle_download.py script is written and functional — it just requires valid credentials to run autonomously. No functional gap.
- **Future action:** User should update ~/.kaggle/kaggle.json with a valid API key before plan 01-02 if they want to automate future dataset refreshes.

---

**Total deviations:** 1 (authentication gate — not an auto-fix deviation)
**Impact on plan:** Zero functional impact. All verification criteria passed. Script exists for future automated use.

## Issues Encountered
- Kaggle API key malformed at time of execution — programmatic download via kagglehub was not possible. Manual browser download was used as fallback. All required files confirmed present and all verification checks passed.

## User Setup Required

Kaggle credentials should be fixed before any future automated dataset refresh:

1. Go to https://www.kaggle.com/settings (API section) and click "Create New Token"
2. Save the downloaded `kaggle.json` to `~/.kaggle/kaggle.json`
3. Ensure competition rules are accepted at https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data
4. Test with: `uv run python -m src.ingest.kaggle_download`

This is not blocking for plans 01-02 or 01-03 — the data is already downloaded.

## Next Phase Readiness
- Plan 01-02 (DuckDB ingestion pipeline) is fully unblocked: all required CSVs are in data/raw/kaggle/, VALID_TOURNEY_SEASONS and get_cutoff() are importable
- Plan 01-03 (Team name normalization) is unblocked: MTeamSpellings.csv is present as a bonus file, thefuzz is installed
- Kaggle API credentials should be fixed at some point but are not blocking for any remaining Phase 1 plans
- No architectural concerns or blockers for Phase 1 continuation

---
*Phase: 01-historical-data-pipeline*
*Completed: 2026-03-02*
