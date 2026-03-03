---
phase: 01-historical-data-pipeline
plan: 02
subsystem: database
tags: [duckdb, parquet, kaggle, ncaa, tournament, first-four, play-in, seeds, regular-season]

# Dependency graph
requires:
  - phase: 01-01
    provides: "data/raw/kaggle/ CSVs downloaded, DAYNUM_ROUND_MAP and VALID_TOURNEY_SEASONS utilities"
provides:
  - data/processed/tournament_games.parquet (1449 games, 2003-2025 excl. 2020, with GameDate, Round, IsFirstFour)
  - data/processed/seeds.parquet (1472 entries, Region/SeedNum/IsFirstFour parsed from Seed string)
  - data/processed/regular_season.parquet (122775 games, 2003-2026, with WLoc H/A/N and GameDate)
  - src/ingest/parse_tourney.py — ingest_tournament_games() and ingest_tournament_seeds()
  - src/ingest/parse_regular_season.py — ingest_regular_season()
  - src/ingest/write_parquet.py — run_full_ingestion() orchestrator (re-runnable via python -m)
affects:
  - 01-03 (team name normalization reads from seeds.parquet and regular_season.parquet)
  - All feature phases (02+) that query tournament_games.parquet and regular_season.parquet
  - Bracket prediction phases that need round-labeled tournament results

# Tech tracking
tech-stack:
  added: []
  patterns:
    - DuckDB COPY...TO with FORMAT parquet and COMPRESSION zstd for all CSV-to-Parquet transforms
    - CAST(DayNum AS INTEGER) required for DATE + integer arithmetic in DuckDB (reads as BIGINT from CSV)
    - Conditional CASE expressions for season-aware round labeling (pre-2011 vs. 2011+)

key-files:
  created:
    - src/ingest/parse_tourney.py
    - src/ingest/parse_regular_season.py
    - src/ingest/write_parquet.py
    - data/processed/tournament_games.parquet
    - data/processed/regular_season.parquet
    - data/processed/seeds.parquet
  modified: []

key-decisions:
  - "DayNum must be CAST to INTEGER in DuckDB for DATE + integer arithmetic (CSV inference reads as BIGINT)"
  - "2021 had no First Four games (COVID bubble tournament) — correctly appears without IsFirstFour=true rows"
  - "2026 regular season data is included in Kaggle dataset (season in progress) — max_season=2026, 3893 games through 2026-02-04"
  - "Regular season includes Season=2020 (truncated season data useful for 2021 context features); tournament_games and seeds exclude 2020"

patterns-established:
  - "DuckDB COPY...TO (FORMAT parquet, COMPRESSION zstd) — single-statement CSV-to-Parquet with joins"
  - "Idempotent pipeline: write_parquet.py can be re-run and will overwrite all three Parquet files cleanly"
  - "Season-aware CASE logic: use Season < 2011 / Season >= 2011 to distinguish pre/post First Four era"

# Metrics
duration: ~20min
completed: 2026-03-02
---

# Phase 1 Plan 02: DuckDB CSV-to-Parquet Ingestion Summary

**DuckDB-based ingestion of Kaggle NCAA CSVs into three zstd-compressed Parquet files: 1449 tournament games with First Four/Play-In tagging, 1472 seed records with parsed region/seed fields, and 122775 regular season games with WLoc and GameDate**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-03T03:43:15Z
- **Completed:** 2026-03-03T04:03:00Z
- **Tasks:** 2
- **Files modified:** 3 created (ingest scripts), 3 produced (Parquet files)

## Accomplishments
- tournament_games.parquet: 1449 games across 22 seasons (2003-2025, no 2020), with computed GameDate, Round names, and IsFirstFour flag — pre-2011 play-in games labeled 'Play-In Game', 2011+ labeled 'First Four'
- seeds.parquet: 1472 seed entries with structured Region (W/X/Y/Z), SeedNum (integer), and IsFirstFour (True for a/b suffix seeds)
- regular_season.parquet: 122775 games (2003-2026) with WLoc (H/A/N verified present), GameDate, and team names
- Full pipeline orchestrator (write_parquet.py) is re-runnable via single command and produces idempotent output

## Task Commits

Each task was committed atomically:

1. **Task 1: Tournament games and seeds ingestion with First Four tagging** - `706b788` (feat)
2. **Task 2: Regular season games ingestion and pipeline orchestrator** - `826925d` (feat)

**Plan metadata:** _(this commit)_ (docs: complete plan)

## Files Created/Modified
- `src/ingest/parse_tourney.py` — ingest_tournament_games() and ingest_tournament_seeds(); season-aware Round CASE logic
- `src/ingest/parse_regular_season.py` — ingest_regular_season(); preserves WLoc; includes Season 2020 and 2026
- `src/ingest/write_parquet.py` — run_full_ingestion() orchestrator; verifies Kaggle files then writes all three Parquet outputs
- `data/processed/tournament_games.parquet` — 1449 rows, zstd compressed (19KB)
- `data/processed/seeds.parquet` — 1472 rows, zstd compressed (9.6KB)
- `data/processed/regular_season.parquet` — 122775 rows, zstd compressed (818KB)

## Decisions Made

- **CAST(DayNum AS INTEGER):** DuckDB's CSV auto-inference reads DayNum as BIGINT; DATE + BIGINT arithmetic fails in DuckDB 1.x. All date computations use explicit `CAST(r.DayNum AS INTEGER)`. This is a non-obvious DuckDB footgun that should be noted for future ingest scripts.

- **2021 First Four absent:** The 2021 COVID bubble tournament had no First Four games. The dataset correctly shows no DayNum 134/135 entries for 2021. This is real data behavior, not a bug.

- **2026 regular season included:** The Kaggle 2026 competition dataset includes the 2026 regular season in progress (3893 games through 2026-02-04). The filter `Season >= 2003` correctly includes this data. Downstream stat queries should apply cutoff dates via `get_cutoff()` to avoid using future data for 2026 predictions.

- **Season 2020 in regular_season.parquet:** The plan specifies including 2020 regular season data (useful for 2021 prediction context). The file includes Season=2020 records. Tournament and seeds files exclude 2020.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CAST(DayNum AS INTEGER) for DuckDB DATE arithmetic**
- **Found during:** Task 1 (Tournament games ingestion)
- **Issue:** DuckDB CSV inference reads DayNum column as BIGINT; `DATE + BIGINT` raises BinderException (DuckDB 1.x requires `DATE + INTEGER`)
- **Fix:** Added `CAST(r.DayNum AS INTEGER)` in all `DayZero::DATE + DayNum` expressions in both parse_tourney.py and parse_regular_season.py
- **Files modified:** src/ingest/parse_tourney.py, src/ingest/parse_regular_season.py
- **Verification:** All three ingest functions ran successfully; all verification checks passed
- **Committed in:** 706b788 (Task 1 commit), 826925d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was necessary for correct operation; no scope creep. All plan verification criteria met.

## Issues Encountered

- DuckDB BIGINT/INTEGER type mismatch for DATE arithmetic: documented as a pattern for future ingest scripts. Solution is straightforward: always cast DayNum to INTEGER before adding to a DATE.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 01-03 (team name normalization) is fully unblocked: seeds.parquet and regular_season.parquet are available; MTeamSpellings.csv is present in data/raw/kaggle/; thefuzz is installed
- All downstream feature phases can now query the three Parquet files via DuckDB
- write_parquet.py is the canonical re-ingestion command — run it after any Kaggle dataset refresh
- 2026 regular season data in regular_season.parquet must be filtered by `get_cutoff(2026)` once 2026 Selection Sunday date is known (mid-March 2026)

---
*Phase: 01-historical-data-pipeline*
*Completed: 2026-03-02*
