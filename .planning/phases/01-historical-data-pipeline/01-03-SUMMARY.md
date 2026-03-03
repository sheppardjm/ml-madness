---
phase: 01-historical-data-pipeline
plan: 03
subsystem: database
tags: [duckdb, parquet, pandas, thefuzz, team-normalization, ncaa, fuzzy-matching, python]

# Dependency graph
requires:
  - phase: 01-01
    provides: "thefuzz + python-Levenshtein installed, data/raw/kaggle/ downloaded, src/normalize/__init__.py stub, src/utils/cutoff_dates.py with get_cutoff()"
  - phase: 01-02
    provides: "tournament_games.parquet, regular_season.parquet, seeds.parquet"
provides:
  - data/seeds/team_aliases.csv — hand-curated alias overrides for 59 teams with known cross-source naming conflicts
  - data/processed/team_normalization.parquet — canonical team name table for all 381 D1 teams (273 tournament teams, 100% coverage)
  - src/normalize/fuzzy_match.py — generate_alias_candidates() bootstrap helper using thefuzz token_sort_ratio
  - src/normalize/build_team_table.py — build_normalization_table() and verify_normalization_coverage() functions
  - src/utils/query_helpers.py — get_tourney_games(), get_season_stats_with_cutoff(), get_team_name() convenience functions
  - All four Phase 1 ROADMAP success criteria verified and passing
affects:
  - 02-01 and all Phase 2 plans (current season data source integration uses team_normalization.parquet as lookup)
  - All feature phases (03+) that need to join cross-source team stats by name
  - Bracket prediction phases that query regular season stats via get_season_stats_with_cutoff()

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Hand-curated seed CSV in data/seeds/ for known cross-source naming conflicts — fuzzy matching only bootstraps, not finalizes
    - DuckDB pandas merge + re-register pattern for overlay joins (read CSV, merge in pandas, register result, COPY TO parquet)
    - data/seeds/*.csv is committed (unlike data/raw/ and data/processed/) — seed files are code artifacts, not data
    - get_season_stats_with_cutoff() as the canonical cutoff-enforced stat query — all stat queries must go through this function

key-files:
  created:
    - src/normalize/fuzzy_match.py
    - src/normalize/build_team_table.py
    - src/utils/query_helpers.py
    - data/seeds/team_aliases.csv
  modified:
    - .gitignore (changed data/ → data/raw/ and data/processed/ to allow data/seeds/ to be committed)

key-decisions:
  - "data/seeds/*.csv committed to git: seed files are hand-curated code artifacts (unlike raw/processed data); changed .gitignore from data/ to data/raw/ and data/processed/"
  - "canonical_name defaults to kaggle_name: for teams with no alias override, canonical_name = TeamName from MTeams.csv; aliases only needed for cross-source conflicts"
  - "59 teams have alias entries: covers all known conflict cases (UConn, Miami FL/OH, Loyola Chicago/MD, St. John's, abbreviated school names, state university variants)"
  - "espn_slug column is empty in Phase 1: placeholder present in parquet schema, will be populated when ESPN data source is integrated in Phase 2"

patterns-established:
  - "from src.utils.query_helpers import get_season_stats_with_cutoff — all regular season stat queries must use this function for cutoff enforcement"
  - "team_normalization.parquet is the single source of truth for cross-source team lookups — never join by raw name string"
  - "verify_normalization_coverage() as pre-flight check — run after any schema change to confirm 100% tournament team coverage"
  - "data/seeds/ is the human-editable layer — to fix a team name conflict, edit team_aliases.csv and re-run build_team_table.py"

# Metrics
duration: ~5min
completed: 2026-03-02
---

# Phase 1 Plan 03: Team Name Normalization Summary

**DuckDB-backed canonical team normalization table with 381 teams, 59 hand-curated alias entries resolving UConn/Miami/Loyola/St. John's conflicts, 100% 2003-2025 tournament coverage, and Selection Sunday cutoff enforcement verified**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-03T03:48:59Z
- **Completed:** 2026-03-03T03:53:16Z
- **Tasks:** 2
- **Files modified:** 4 created, 1 modified

## Accomplishments
- team_normalization.parquet: 381 D1 teams, 100% coverage of 273 unique tournament teams (2003-2025), with canonical_name for all and espn_name/sr_slug/cbbdata_name for 59 known-conflict teams
- Hand-curated team_aliases.csv with 59 entries: covers UConn/Connecticut, Miami FL/Miami OH, Loyola Chicago/Loyola MD, St. John's, and abbreviated Kaggle names (TAM C. Christi, MTSU, CS Fullerton, etc.)
- query_helpers.py with get_season_stats_with_cutoff() enforcing Selection Sunday cutoff: verified 2025 returns 5641 games with latest date 2025-03-16
- All four Phase 1 ROADMAP success criteria satisfied: no duplicates (0), correct season coverage (2003-2025 excl 2020), First Four correctly labeled, cutoff enforcement verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Build team normalization table with seed aliases and fuzzy matching bootstrap** - `9187dc5` (feat)
2. **Task 2: End-to-end data pipeline verification and cutoff enforcement test** - `c892a42` (feat)

**Plan metadata:** _(this commit)_ (docs: complete plan)

## Files Created/Modified
- `src/normalize/fuzzy_match.py` — generate_alias_candidates() bootstrap helper using thefuzz token_sort_ratio; generates candidates for human review (not final truth)
- `src/normalize/build_team_table.py` — build_normalization_table() overlays team_aliases.csv onto MTeams.csv; verify_normalization_coverage() checks 100% tournament team coverage; __main__ block runs both
- `src/utils/query_helpers.py` — get_tourney_games(), get_season_stats_with_cutoff() (cutoff-enforced), get_team_name() convenience functions for downstream phases
- `data/seeds/team_aliases.csv` — 59 hand-curated rows: kaggle_team_id, canonical_name, kaggle_name, espn_name, sr_slug, cbbdata_name
- `.gitignore` — changed `data/` → `data/raw/` and `data/processed/` to allow data/seeds/*.csv to be committed as code artifacts

## Decisions Made

- **data/seeds/*.csv committed to git:** Seed files are hand-curated code artifacts, not large data files. The existing gitignore excluded all of `data/`. Changed to exclude only `data/raw/` and `data/processed/` so the seeds directory is trackable. This is necessary for reproducibility — without the seed file, build_team_table.py cannot produce correct alias mappings.

- **canonical_name defaults to kaggle_name:** For the 322 teams without alias overrides, canonical_name equals the raw TeamName from MTeams.csv. This is correct — Kaggle names like "Arizona", "Duke", "Kentucky" need no disambiguation. Only names that differ across sources need an entry in the seed CSV.

- **59 alias entries cover all observed conflicts:** Resolved Kaggle's abbreviated names (Ark Little Rock, C Michigan, TAM C. Christi, WI Green Bay, etc.), marketing rebrands (Connecticut → UConn canonical; espn_name = UConn), and disambiguation pairs (Miami FL / Miami OH, Loyola Chicago / Loyola MD).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed wrong kaggle_team_id for Southern University in seed CSV**
- **Found during:** Task 1 (build and verification of team_normalization table)
- **Issue:** Seed CSV used team ID 1381 (Southern Utah) instead of 1380 (Southern Univ) for the Southern University entry
- **Fix:** Corrected kaggle_team_id to 1380 in team_aliases.csv
- **Files modified:** data/seeds/team_aliases.csv
- **Verification:** Re-ran build_team_table.py; Southern Univ (1380) now shows canonical_name "Southern University"; verify_normalization_coverage() still 100%
- **Committed in:** 9187dc5 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed wrong espn_name for Cal State Bakersfield in seed CSV**
- **Found during:** Task 1 (review of espn_name entries)
- **Issue:** Seed CSV had espn_name="UC Santa Barbara" for Cal State Bakersfield (1167) — clearly a data entry error
- **Fix:** Corrected espn_name to "Cal State Bakersfield"
- **Files modified:** data/seeds/team_aliases.csv
- **Verification:** team_normalization.parquet shows correct espn_name for Cal State Bakersfield
- **Committed in:** 9187dc5 (Task 1 commit)

**3. [Rule 2 - Missing Critical] Updated .gitignore to track data/seeds/*.csv**
- **Found during:** Task 1 (git add attempt for team_aliases.csv)
- **Issue:** The entire data/ directory was gitignored; team_aliases.csv (a hand-curated code artifact, not a data file) could not be committed. Without committing this file, the build pipeline is not reproducible.
- **Fix:** Changed gitignore from `data/` to `data/raw/` and `data/processed/`, leaving data/seeds/ trackable
- **Files modified:** .gitignore
- **Verification:** git check-ignore confirms data/seeds/team_aliases.csv is no longer ignored; data/raw/ and data/processed/ still excluded
- **Committed in:** 9187dc5 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 2 missing critical)
**Impact on plan:** All auto-fixes necessary for correctness and reproducibility. No scope creep. Seed file content was corrected before final commit.

## Issues Encountered

- git negation pattern `!data/seeds/` does not work when parent `data/` is ignored — git ignores entire directory trees and negation cannot un-ignore a file inside an excluded parent. Fixed by making the gitignore more granular (data/raw/ and data/processed/ instead of data/).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- Phase 2 (current season data pipeline) is fully unblocked: team_normalization.parquet provides the lookup table, get_team_name() and get_season_stats_with_cutoff() are importable
- Phase 2 must populate espn_name, espn_slug, sr_slug, cbbdata_name, and ncaa_name for all remaining teams in team_normalization.parquet; currently only the 59 conflict teams have these populated
- Blocker remains: cbbdata API key needed before Phase 2 data source integration can begin
- espn_slug column exists in schema but is empty for all rows (including conflict teams) — Phase 2 can populate this once ESPN team list is pulled
- 2026 Selection Sunday date still unknown (mid-March 2026) — get_cutoff(2026) will raise ValueError until added to SELECTION_SUNDAY_DATES in cutoff_dates.py

---
*Phase: 01-historical-data-pipeline*
*Completed: 2026-03-02*
