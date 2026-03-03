---
phase: 03-baseline-model-and-temporal-validation
plan: 01
subsystem: database
tags: [cbbdata, torvik, parquet, duckdb, pandas, feature-engineering, sklearn]

# Dependency graph
requires:
  - phase: 01-historical-data-pipeline
    provides: tournament_games.parquet, seeds.parquet, team_normalization.parquet
  - phase: 02-current-season-and-bracket-data
    provides: current_season_stats.parquet (2025 season efficiency metrics)

provides:
  - data/processed/historical_torvik_ratings.parquet — 5971 rows, 17 seasons (2008-2025)
  - src/models/features.py — compute_features(), build_stats_lookup(), build_matchup_dataset()
  - FEATURE_COLS constant (6 differential features)
  - 1054-row matchup training dataset with zero NaN features

affects:
  - 03-02 (logistic regression baseline — consumes build_matchup_dataset())
  - 03-03 (walk-forward CV — consumes matchup dataset seasonal splits)
  - All later modeling phases — depend on FEATURE_COLS and compute_features()

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Stats lookup dict keyed by (season, kaggle_team_id) for O(1) feature computation
    - Canonical matchup ordering: team_a = lower SeedNum (better seed)
    - CBBDATA_NAME_OVERRIDES pre-pass before fuzzy matching for known ambiguous API names
    - build_stats_lookup() merges historical + current_season data, handles year→season rename

key-files:
  created:
    - src/models/__init__.py
    - src/models/features.py
  modified:
    - src/ingest/fetch_historical_ratings.py
    - data/seeds/team_aliases.csv
    - data/processed/team_normalization.parquet (gitignored artifact — rebuilt from aliases)
    - data/processed/historical_torvik_ratings.parquet (gitignored artifact)

key-decisions:
  - "cbbdata only has year-end ratings for 2008-2024; 2003-2007 unavailable, 2025 uses archive snapshot"
  - "CBBDATA_NAME_OVERRIDES dict added to fetch_historical_ratings.py for 4 ambiguous fuzzy match cases"
  - "team_aliases.csv bug fixed: ID 1299 was mislabeled NC Central, corrected to NC A&T with North Carolina A&T cbbdata_name"
  - "NC State: cbbdata sends both N.C. State (older) and North Carolina St. (newer) — both handled via direct cbbdata_name and override"
  - "build_stats_lookup() replaces historical 2025 data with current_season_stats.parquet (freshest Phase 2 output)"
  - "313 pre-2008 games dropped from matchup dataset — acceptable, 17 seasons still sufficient for walk-forward CV"

patterns-established:
  - "compute_features() raises KeyError on missing teams (fail-fast, no silent NaN propagation)"
  - "build_matchup_dataset() drops missing-stats rows with warnings (not errors) — returns clean DataFrame"
  - "FEATURE_COLS ordering is canonical — all downstream models must use this exact order"

# Metrics
duration: 12min
completed: 2026-03-03
---

# Phase 3 Plan 01: Historical Ratings Ingestion and Feature Engineering Summary

**Torvik efficiency ratings for 17 seasons (2008-2025) fetched via cbbdata API, team normalization bugs fixed, and 6-feature differential matchup dataset (1054 games) built using DuckDB-backed stats lookup**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-03T20:21:32Z
- **Completed:** 2026-03-03T20:34:04Z
- **Tasks:** 2
- **Files modified:** 4 (code) + 2 (gitignored parquet artifacts)

## Accomplishments
- Fetched 5971 rows of Torvik efficiency ratings (adjOE, adjDE, barthag, tempo, WAB) across 17 seasons (2008-2025), 99.6% team match rate
- Fixed critical team_aliases.csv bug: ID 1299 was mislabeled NC Central (should be NC A&T), causing NC State and NC A&T to map to wrong Kaggle IDs across all seasons
- Built `src/models/features.py` with `compute_features()`, `build_stats_lookup()`, and `build_matchup_dataset()` — returns 1054 clean matchups with zero NaN features

## Task Commits

Each task was committed atomically:

1. **Task 1: Fetch historical Torvik ratings** - `a851db9` (feat)
2. **Task 2: Build compute_features() and matchup dataset** - `4906a18` (feat)

## Files Created/Modified
- `src/ingest/fetch_historical_ratings.py` — Added CBBDATA_NAME_OVERRIDES dict and pre-pass matching logic for 4 ambiguous team names
- `data/seeds/team_aliases.csv` — Fixed NC A&T (1299) mislabel, added NC Central (1300), Col Charleston (1158), Saint Francis → St Francis PA (1384)
- `src/models/__init__.py` — Empty package marker created
- `src/models/features.py` — FEATURE_COLS, compute_features(), build_stats_lookup(), build_matchup_dataset()
- `data/processed/team_normalization.parquet` — Rebuilt with corrected aliases (gitignored)
- `data/processed/historical_torvik_ratings.parquet` — 5971 rows, 17 seasons (gitignored)

## Decisions Made
- **cbbdata year coverage**: API only has year-end ratings for 2008-2024. Seasons 2003-2007 returned empty/no-barthag for both primary and archive endpoints. Accepted 17 seasons (not 22) — walk-forward CV still works since 2022-2025 backtest years each have 10+ training seasons.
- **NC State name ambiguity**: cbbdata sends 'N.C. State' (older seasons) and 'North Carolina St.' (newer seasons) for the same team. Both are now handled: 'N.C. State' direct-matches via cbbdata_name in normalization; 'North Carolina St.' is caught by CBBDATA_NAME_OVERRIDES pre-pass.
- **Saint Francis name change**: cbbdata sends 'St. Francis PA' (older seasons) and 'Saint Francis' (recent, post-rename). normalization has cbbdata_name='Saint Francis' (direct match for recent); 'St. Francis PA' handled by CBBDATA_NAME_OVERRIDES.
- **2025 stats**: build_stats_lookup() replaces historical 2025 archive data with current_season_stats.parquet (Phase 2 output) for the freshest pre-Selection-Sunday metrics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed team_aliases.csv ID 1299 mislabeling NC A&T as NC Central**
- **Found during:** Task 1 (historical ratings matching)
- **Issue:** aliases.csv had `1299,NC Central,...,North Carolina Central` but Kaggle's MTeams.csv shows ID 1299 = 'NC A&T' and ID 1300 = 'NC Central'. This caused NC A&T stats to be attributed to 'NC Central' canonical name, and more critically, caused 'North Carolina A&T' from cbbdata to fuzzy-match to 'North Carolina' (ID 1314) — wrong team ID.
- **Fix:** Updated aliases.csv: 1299 → NC A&T with cbbdata_name='North Carolina A&T'; added new row 1300 → NC Central with cbbdata_name='North Carolina Central'
- **Files modified:** `data/seeds/team_aliases.csv`
- **Verification:** NC State correctly maps to ID 1301 across all 17 seasons in historical_torvik_ratings.parquet; NC A&T maps to 1299
- **Committed in:** a851db9 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed NC State fuzzy match false positive (North Carolina St. → North Carolina)**
- **Found during:** Task 1 (post-run data quality check)
- **Issue:** cbbdata sends 'North Carolina St.' in newer seasons. Fuzzy score vs 'North Carolina' (90) > vs 'NC State' (32), so NC State games were attributed to North Carolina's ID (1314) — critically wrong for model training.
- **Fix:** Added `"North Carolina St.": "NC State"` to CBBDATA_NAME_OVERRIDES pre-pass in fetch_historical_ratings.py
- **Files modified:** `src/ingest/fetch_historical_ratings.py`
- **Verification:** `SELECT DISTINCT canonical_name FROM historical_torvik_ratings.parquet WHERE cbbdata_name = 'North Carolina St.'` returns 'NC State' only
- **Committed in:** a851db9 (Task 1 commit)

**3. [Rule 1 - Bug] Fixed Charleston fuzzy match false positive (Charleston → Charleston So)**
- **Found during:** Task 1 (post-run data quality check)
- **Issue:** cbbdata sends 'Charleston' (College of Charleston). Fuzzy matched to 'Charleston So' (Charleston Southern, ID 1149) — wrong school entirely.
- **Fix:** Added `"Charleston": "Col Charleston"` to CBBDATA_NAME_OVERRIDES; added cbbdata_name='College of Charleston' to aliases.csv for ID 1158
- **Files modified:** `src/ingest/fetch_historical_ratings.py`, `data/seeds/team_aliases.csv`
- **Committed in:** a851db9 (Task 1 commit)

**4. [Rule 1 - Bug] Fixed Saint Francis fuzzy match false positive (Saint Francis → San Francisco)**
- **Found during:** Task 1 (post-run data quality check)
- **Issue:** cbbdata sends 'Saint Francis' (St Francis PA, post-rename) in 2024-2025. Fuzzy score vs 'San Francisco' = exactly 85 (threshold), causing mismatch. St Francis PA made the 2025 tournament, making this critical for model correctness.
- **Fix:** Changed cbbdata_name for ID 1384 to 'Saint Francis' in aliases.csv; added `"St. Francis PA": "St Francis PA"` to CBBDATA_NAME_OVERRIDES to handle older seasons
- **Files modified:** `src/ingest/fetch_historical_ratings.py`, `data/seeds/team_aliases.csv`
- **Committed in:** a851db9 (Task 1 commit)

---

**Total deviations:** 4 auto-fixed (all Rule 1 - Bug)
**Impact on plan:** All fixes necessary for correct team ID assignment in training data. NC State fix is critical — 11 tournament appearances would have had wrong efficiency metrics. No scope creep.

## Issues Encountered
- cbbdata archive endpoint returns 404/empty for years 2003-2007 (Torvik ratings database apparently starts ~2007-08 season). Graceful skip implemented, final dataset covers 2008-2025 (17 seasons). The plan noted this was acceptable.

## User Setup Required
None — cbbdata credentials were provided via CBD_USERNAME/CBD_PASSWORD env vars.

## Next Phase Readiness
- `build_matchup_dataset()` returns 1054 clean matchups ready for logistic regression training in 03-02
- `compute_features()` is importable and tested — ready for walk-forward CV in 03-03
- Historical seasons coverage: 2008-2025 gives 10+ training seasons before each of the 2022-2025 backtest holdouts
- No blockers for 03-02

---
*Phase: 03-baseline-model-and-temporal-validation*
*Completed: 2026-03-03*
