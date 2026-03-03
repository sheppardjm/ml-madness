---
phase: 02-current-season-and-bracket-data
plan: 01
subsystem: data-pipeline
tags: [cbbdata, torvik, barthag, parquet, duckdb, requests, fuzzy-matching, team-normalization]

# Dependency graph
requires:
  - phase: 01-historical-data-pipeline
    provides: "team_normalization.parquet with canonical names; cutoff_dates.py with get_cutoff()"
provides:
  - "cbbdata REST API client (get_cbbdata_token, fetch_torvik_ratings, fetch_cbbdata_teams)"
  - "current_season_stats.parquet: 364 D1 teams with barthag, adj_o, adj_d, adj_t, wab"
  - "team_normalization.parquet updated: espn_slug (360 teams) and cbbdata_name (362 teams) populated"
  - "get_cutoff(2026) returning 2026-03-15"
  - "team_aliases.csv expanded to 101 entries covering all cbbdata name variants"
affects:
  - phase: 02-02 (bracket fetch uses espn_slug column now populated)
  - phase: 03 (feature engineering joins on cbbdata_name and kaggle_team_id from stats)
  - phase: 04 (model training uses barthag, adj_o, adj_d as core features)

# Tech tracking
tech-stack:
  added:
    - requests>=2.32.5 (HTTP client for cbbdata REST API)
  patterns:
    - "cbbdata REST auth: POST /api/auth/login with {username,password} -> {api_key: str} (dict format, not list)"
    - "cbbdata data endpoints return raw Parquet bytes: pd.read_parquet(BytesIO(response.content))"
    - "Archive fallback strategy: year-end ratings unavailable -> fall back to archive/date snapshot"
    - "HTTPAdapter with Retry(total=3, backoff_factor=1) on all cbbdata sessions"

key-files:
  created:
    - src/ingest/cbbdata_client.py
    - .planning/phases/02-current-season-and-bracket-data/02-01-SUMMARY.md
  modified:
    - src/utils/cutoff_dates.py (added 2026 entry)
    - pyproject.toml (added requests dependency)
    - src/normalize/build_team_table.py (added update_normalization_with_cbbdata())
    - data/seeds/team_aliases.csv (59 -> 101 entries)
    - data/processed/team_normalization.parquet (espn_slug and cbbdata_name populated)
    - data/processed/current_season_stats.parquet (created: 364 team efficiency metrics)

key-decisions:
  - "cbbdata login response format is dict with api_key key (not list as documented in R package)"
  - "cbbdata year-end ratings (/torvik/ratings) has no 2025-26 data as of 2026-03-03; archive fallback uses 2025-03-16 snapshot (end of 2024-25 season)"
  - "current_season_stats.parquet uses best available data (2024-25 season end) as proxy — must be refreshed when cbbdata indexes 2025-26 season"
  - "fuzzy match guard added to prevent directional-prefix false positives (E Illinois->Illinois, West Georgia->Georgia St.)"
  - "42 additional team_aliases.csv entries added for cbbdata name variants not resolvable by fuzzy matching"
  - "cbbdata registration endpoint requires email and confirm_password fields (not just username+password)"

patterns-established:
  - "Archive fallback: when year-end endpoint empty, use archive + Selection Sunday date filter"
  - "Name matching cascade: exact cbbdata_name, exact canonical_name, exact kaggle_name, fuzzy with ambiguity guards"
  - "Seed file expansion: when fuzzy fails, add to team_aliases.csv rather than silently dropping"

# Metrics
duration: 22min
completed: 2026-03-03
---

# Phase 2 Plan 01: cbbdata API Client and Efficiency Metrics Summary

**cbbdata REST API client with archive fallback delivering 364 D1 team efficiency metrics (barthag, adjOE, adjDE) and team normalization updated with 360 ESPN slugs via torvik_team matching**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-03-03T04:35:17Z
- **Completed:** 2026-03-03T04:57:10Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Created `src/ingest/cbbdata_client.py` with full authentication, ratings fetch, teams fetch, and current season ingest
- Populated `team_normalization.parquet` with `espn_slug` (360/381 teams) and `cbbdata_name` (362/381 teams)
- Wrote `current_season_stats.parquet` with 364 D1 teams at 100% kaggle_team_id match rate — all have barthag, adj_o, adj_d
- Expanded `team_aliases.csv` from 65 to 101 entries to cover all cbbdata naming variants
- Added `2026: "2026-03-15"` to `SELECTION_SUNDAY_DATES`; `get_cutoff(2026)` now returns correct date

## Task Commits

1. **Task 1: Add 2026 cutoff, requests dep, create cbbdata client** - `ea8990c` (feat)
2. **Task 2: Update normalization with cbbdata names and ESPN slugs** - `9583b3d` (feat)
3. **Task 3: Fetch efficiency stats and write current_season_stats.parquet** - `d9a08d3` (feat)

## Files Created/Modified

- `src/ingest/cbbdata_client.py` - cbbdata REST client with auth, ratings, teams, season ingest
- `src/utils/cutoff_dates.py` - Added 2026 entry; updated error message range
- `pyproject.toml` / `uv.lock` - Added requests>=2.32.5 as explicit dependency
- `src/normalize/build_team_table.py` - Added update_normalization_with_cbbdata() with 4-pass matching
- `data/seeds/team_aliases.csv` - Expanded 65 -> 101 entries (36 new cbbdata name mappings)
- `data/processed/team_normalization.parquet` - espn_slug and cbbdata_name populated for 360/362 of 381 teams
- `data/processed/current_season_stats.parquet` - 364 teams, 100% match rate, all metrics populated

## Decisions Made

**cbbdata API response format:** The login endpoint returns `{"api_key": "..."}` (dict), not a JSON list as documented in the R package source. `get_cbbdata_token()` handles both formats for robustness.

**Archive fallback for missing 2026 data:** The cbbdata `torvik/ratings` endpoint has no 2025-26 season data as of 2026-03-03 (max available is year=2025 with 2025-03-16 snapshot). The implementation falls back to the archive endpoint, using the most recent pre-Selection-Sunday snapshot of the 2024-25 season. The `year` column in `current_season_stats.parquet` is 2025 (not 2026) to reflect this limitation. This must be refreshed once cbbdata indexes 2025-26 season data.

**Fuzzy match ambiguity guards:** Added `_is_ambiguous_match()` in `update_normalization_with_cbbdata()` to prevent false positives where directional prefixes (E, N, W) or direction words (West, East) cause abbreviated team names to match wrong cbbdata teams (e.g., "E Illinois" matching "Illinois", "West Georgia" matching "Georgia St.").

**Seed file expansion over silent dropping:** When fuzzy matching fails below 85% threshold, teams are logged with WARNING but not dropped. The correct fix is to add an explicit entry to `team_aliases.csv`. Applied for 36 teams.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] cbbdata login response format mismatch**

- **Found during:** Task 1 (testing get_cbbdata_token)
- **Issue:** RESEARCH.md documented `response.json()[0]` (list format) but actual API returns `{"api_key": "..."}` (dict format)
- **Fix:** Updated `get_cbbdata_token()` to detect dict vs list response and extract accordingly
- **Files modified:** src/ingest/cbbdata_client.py
- **Verification:** Authentication succeeds, API key extracted correctly
- **Committed in:** d9a08d3

**2. [Rule 1 - Bug] Fuzzy matching false positives for directional-prefix names**

- **Found during:** Task 2 (first run of update_normalization_with_cbbdata)
- **Issue:** `token_sort_ratio` matched "E Illinois" -> "Illinois" (score=89), "West Georgia" -> "Georgia St." (score=91), "N Illinois" -> "Illinois" (score=86) because token sorting places them alphabetically adjacent
- **Fix:** Added `_is_ambiguous_match()` guard that rejects matches where (a) short name has single-char directional prefix matching remainder, or (b) name starts with a directional word not present in the candidate
- **Files modified:** src/normalize/build_team_table.py
- **Verification:** E/N/W Illinois all correctly match Eastern/Northern/Western Illinois; West Georgia correctly gets no match
- **Committed in:** 9583b3d

**3. [Rule 2 - Missing Critical] cbbdata 2026 season data unavailable — archive fallback**

- **Found during:** Task 3 (running fetch_torvik_ratings with year=2026)
- **Issue:** cbbdata API has no 2025-26 season data yet (max year=2025 in archive, ending 2025-06-30). Year=2026 returns empty DataFrame. The RESEARCH.md noted this as an open question.
- **Fix:** Added archive endpoint fallback that uses the most recent available pre-Selection-Sunday snapshot. For year=2026, falls back to year=2025 archive data (2025-03-16 snapshot, 364 teams). Documents clearly in code that this is previous-season proxy.
- **Files modified:** src/ingest/cbbdata_client.py
- **Verification:** 364 teams fetched, all with barthag/adj_o/adj_d, 100% match rate
- **Committed in:** d9a08d3

**4. [Rule 2 - Missing Critical] 36 additional team_aliases.csv entries for cbbdata name variants**

- **Found during:** Task 3 (ingestion had 34 unmatched teams on first run)
- **Issue:** Many cbbdata team names could not be fuzzy-matched to normalization table because the abbreviated Kaggle names are too dissimilar (e.g., "Saint Mary's" can't match "St Mary's CA", "N.C. State" can't match "NC State")
- **Fix:** Added explicit cbbdata_name entries to team_aliases.csv for all 36 unresolvable teams plus fixed Little Rock cbbdata name
- **Files modified:** data/seeds/team_aliases.csv, data/processed/team_normalization.parquet
- **Verification:** Match rate improved from 330/364 to 364/364 (100%)
- **Committed in:** d9a08d3

---

**Total deviations:** 4 auto-fixed (2 bugs, 2 missing critical)
**Impact on plan:** All auto-fixes essential for correctness. Archive fallback preserves project timeline. 100% match rate achieved.

## Issues Encountered

**cbbdata API registration format:** The registration endpoint required `email` and `confirm_password` fields (not just `username` + `password`). First registration attempts returned 500. Fixed by including all required fields. Account registered successfully: username=`madness2026`.

**cbbdata 2025-26 season data unavailable:** The most significant issue. As of 2026-03-03, cbbdata has not indexed the 2025-26 season data. The archive endpoint's maximum date is 2025-06-30 (end of 2024-25 season). The current season data must be refreshed once cbbdata updates its pipeline. Downstream phases should be aware that `current_season_stats.parquet` contains 2024-25 season metrics, not 2025-26.

**IUPUI renamed to IU Indy:** Cbbdata uses the new name "IU Indy" for Indiana University Indianapolis (formerly IUPUI). Added explicit alias mapping.

## Next Phase Readiness

**Ready for Phase 2, Plan 02 (bracket fetch):**
- `espn_slug` is populated for 360 teams — bracket fetch can match ESPN team IDs
- `cbbdata_name` populated for 362 teams — efficiency stats join is reliable
- `current_season_stats.parquet` exists with complete efficiency metrics

**Critical caveat:** `current_season_stats.parquet` contains 2024-25 season metrics (2025-03-16 snapshot), not 2025-26. This is the best available data from cbbdata as of the plan execution date. Needs refresh when cbbdata indexes 2025-26 season.

**Blocker for downstream phases:** cbbdata 2025-26 season data absent. Check `https://www.cbbdata.com/api/torvik/ratings?key=...&year=2026` periodically — when it returns >0 rows with barthag populated, re-run `ingest_current_season_stats()` to refresh.

---
*Phase: 02-current-season-and-bracket-data*
*Completed: 2026-03-03*
