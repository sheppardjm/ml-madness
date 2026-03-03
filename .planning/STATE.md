# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** Phase 1 complete — ready for Phase 2 (Current Season Data Pipeline)

## Current Position

Phase: 1 of 10 (Historical Data Pipeline) — COMPLETE
Plan: 3 of 3 in phase 01 (all complete)
Status: Phase 1 complete — all four ROADMAP success criteria verified and passing
Last activity: 2026-03-02 — Completed 01-03-PLAN.md (team normalization table, query helpers, Phase 1 end-to-end verification)

Progress: [███░░░░░░░] 10% (3/30 plans estimated)

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~23 min
- Total execution time: ~1.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-historical-data-pipeline | 3 | ~70 min | ~23 min |

**Recent Trend:**
- Last 5 plans: 01-01 (~45 min), 01-02 (~20 min), 01-03 (~5 min)
- Trend: Excellent — well-scoped plans execute faster as the codebase matures

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
- [01-03]: canonical_name defaults to kaggle_name for teams without alias overrides; team_aliases.csv only needed for cross-source conflicts (59 teams out of 381)
- [01-03]: All four Phase 1 ROADMAP success criteria verified — zero duplicates, correct season coverage, First Four correctly labeled, cutoff enforcement passing
- [01-03]: get_season_stats_with_cutoff() is the canonical stat query interface — all downstream phases must use this function to avoid data leakage

### Pending Todos

None.

### Blockers/Concerns

- [Pre-Phase 2]: cbbdata API free key must be obtained at cbbdata.aweatherman.com before Phase 2 begins — verify Python REST access (documentation is R-centric)
- [Hard deadline]: Auto-fetch bracket pipeline (Phase 2, plan 02-03) must be operational before Selection Sunday 2026 (mid-March) — one-shot operation with no retry window
- [Non-blocking]: Kaggle API key malformed — fix ~/.kaggle/kaggle.json for future automated refreshes, but not required until next Kaggle dataset refresh
- [Note]: 2026 Selection Sunday date not yet in SELECTION_SUNDAY_DATES — must be added once announced (mid-March 2026) to enable get_cutoff(2026); get_cutoff(2026) currently raises ValueError
- [Phase 2]: espn_slug column in team_normalization.parquet is empty for all teams — Phase 2 must populate this once ESPN team list is available
- [Resolved - 01-01]: Kaggle 2025 data confirmed present — MNCAATourneyCompactResults.csv covers 1985-2025, max season = 2025
- [Resolved - 01-02]: All three Parquet files written — tournament_games.parquet (1449 games), seeds.parquet (1472 entries), regular_season.parquet (122775 games)
- [Resolved - 01-03]: team_normalization.parquet complete — 381 teams, 100% tournament coverage, 59 cross-source aliases resolved

## Session Continuity

Last session: 2026-03-02
Stopped at: Completed 01-03-PLAN.md — Phase 1 complete; all four ROADMAP success criteria verified; team_normalization.parquet, query_helpers.py, fuzzy_match.py, build_team_table.py all created and passing
Resume file: None
