# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** Phase 2, Plan 2 complete — bracket fetch pipeline operational; ready for 02-03 (phase completion verification) or Phase 3

## Current Position

Phase: 2 of 10 (Current Season and Bracket Data) — In progress
Plan: 2 of 3 in phase 02 (02-01 and 02-02 complete)
Status: 02-02 complete — ESPN bracket auto-fetch, CSV fallback, team resolution, stats coverage verification
Last activity: 2026-03-03 — Completed 02-02-PLAN.md (fetch_bracket.py: full bracket pipeline)

Progress: [████░░░░░░] 17% (5/30 plans estimated)

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: ~21 min
- Total execution time: ~1.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-historical-data-pipeline | 3 | ~70 min | ~23 min |
| 02-current-season-and-bracket-data | 2 | ~27 min | ~14 min |

**Recent Trend:**
- Last 5 plans: 01-02 (~20 min), 01-03 (~5 min), 02-01 (~22 min), 02-02 (~5 min)
- Trend: Well-scoped plans with clear prior context execute in 5-10 min; complex integrations 20-25 min

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Phase 8 (Feature Store) is formally ordered after Phase 7 but should be implemented alongside Phase 3 in practice — feature function begins inline and is later formalized
- [Roadmap]: Phases 9 and 10 (UI) can begin once Phase 4's bracket JSON contract is stable, allowing parallel work with Phases 5-7
- [Research]: Direct barttorvik.com scraping is blocked by Cloudflare — use cbbdata API instead (free key required before Phase 2 begins)
- [Research]: ESPN unofficial API endpoint for 2026 bracket must be verified on Selection Sunday — do not assume 2025 format is stable; manual CSV fallback is required
- [01-01]: VALID_TOURNEY_SEASONS starts at 2003 (Kaggle supplemental feature data availability) and excludes 2020 (COVID cancellation) — 22 seasons total
- [01-01]: get_cutoff() raises ValueError on invalid/missing seasons to prevent silent training-set contamination
- [01-01]: Kaggle API key was malformed at execution time — data downloaded manually; kaggle_download.py exists and works with valid credentials
- [01-02]: DuckDB reads DayNum as BIGINT from CSV; DATE + BIGINT arithmetic fails — always CAST(DayNum AS INTEGER) in all future ingest scripts
- [01-02]: 2021 had no First Four games (COVID bubble tournament) — IsFirstFour is correctly absent for 2021 in tournament_games.parquet
- [01-02]: Kaggle 2026 competition dataset includes 2026 regular season in progress (3893 games through 2026-02-04) — downstream queries must apply get_cutoff() for 2026 predictions
- [01-03]: data/seeds/*.csv is committed to git (changed .gitignore from data/ to data/raw/ and data/processed/) — seed files are hand-curated code artifacts, not data
- [01-03]: canonical_name defaults to kaggle_name for teams without alias overrides; team_aliases.csv only needed for cross-source conflicts (101 teams total as of 02-01)
- [01-03]: All four Phase 1 ROADMAP success criteria verified — zero duplicates, correct season coverage, First Four correctly labeled, cutoff enforcement passing
- [01-03]: get_season_stats_with_cutoff() is the canonical stat query interface — all downstream phases must use this function to avoid data leakage
- [02-01]: cbbdata login API response format is dict with api_key key, NOT a list as documented in R package (response.json()[0] fails; use response.json()["api_key"])
- [02-01]: cbbdata torvik/ratings endpoint has no 2025-26 season data as of 2026-03-03 — max available is year=2025 with date 2025-03-16; archive fallback used as proxy
- [02-01]: current_season_stats.parquet contains 2024-25 season metrics (not 2025-26) — must refresh when cbbdata indexes 2025-26 data (check year=2026 returning >0 barthag rows)
- [02-01]: team_aliases.csv expanded from 65 to 101 entries — cbbdata uses full names where Kaggle uses abbreviations; explicit mapping required for ~36 teams
- [02-01]: Fuzzy match ambiguity guard required to prevent directional-prefix false positives (E+Illinois->Illinois, West+Georgia->Georgia St.) in token_sort_ratio matching
- [02-01]: cbbdata account credentials: username=madness2026 — CBD_USERNAME/CBD_PASSWORD env vars must be set before running cbbdata ingestion scripts
- [02-02]: ESPN bracket data only available after Selection Sunday (2026-03-15) — fetch_espn_bracket() returns 0 rows before that date (expected, not an error)
- [02-02]: espn_name column in team_normalization has 317/381 empty strings (not NULLs) — filter on `espn_name != ''` not just `IS NOT NULL` in all downstream queries
- [02-02]: resolve_bracket_teams() uses 4-pass matching (espn_name -> canonical_name -> slug -> fuzzy@80) — raises AssertionError on unresolved teams to force fix before simulation

### Pending Todos

- Refresh current_season_stats.parquet when cbbdata indexes 2025-26 season (check /api/torvik/ratings?year=2026 for non-empty barthag)
- On Selection Sunday (2026-03-15): run `uv run python -m src.ingest.fetch_bracket` to confirm auto-fetch returns 68 teams; if <68, populate data/seeds/bracket_manual.csv

### Blockers/Concerns

- [Important]: current_season_stats.parquet contains 2024-25 season metrics as proxy — downstream modeling will use last season's efficiency as 2026 features; acceptable but suboptimal
- [Time-sensitive]: Must run bracket fetch on/after Selection Sunday (2026-03-15 after 6 PM ET); CSV fallback is ready if ESPN auto-fetch fails
- [Non-blocking]: Kaggle API key malformed — fix ~/.kaggle/kaggle.json for future automated refreshes, but not required until next Kaggle dataset refresh
- [Resolved - 02-02]: Bracket fetch pipeline operational — ESPN auto-fetch + CSV fallback + team resolution + stats coverage verification all functional
- [Resolved - Pre-Phase 2]: cbbdata API key obtained; authentication working; Python REST access confirmed
- [Resolved - 02-01]: 2026 Selection Sunday date (2026-03-15) added to SELECTION_SUNDAY_DATES; get_cutoff(2026) now works
- [Resolved - 02-01]: espn_slug column populated for 360/381 teams in team_normalization.parquet
- [Resolved - 01-01]: Kaggle 2025 data confirmed present — MNCAATourneyCompactResults.csv covers 1985-2025, max season = 2025
- [Resolved - 01-02]: All three Parquet files written — tournament_games.parquet (1449 games), seeds.parquet (1472 entries), regular_season.parquet (122775 games)
- [Resolved - 01-03]: team_normalization.parquet complete — 381 teams, 100% tournament coverage, 101 cross-source aliases resolved

## Session Continuity

Last session: 2026-03-03
Stopped at: Completed 02-02-PLAN.md — ESPN bracket auto-fetch + CSV fallback + team resolution + stats coverage verification in src/ingest/fetch_bracket.py
Resume file: None
