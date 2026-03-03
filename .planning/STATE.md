# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** Phase 1 — Historical Data Pipeline

## Current Position

Phase: 1 of 10 (Historical Data Pipeline)
Plan: 2 of 3 in current phase
Status: In progress — plan 01-02 complete, ready for 01-03
Last activity: 2026-03-02 — Completed 01-02-PLAN.md (DuckDB CSV-to-Parquet ingestion pipeline)

Progress: [██░░░░░░░░] 7% (2/30 plans estimated)

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: ~32 min
- Total execution time: ~1.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-historical-data-pipeline | 2 | ~65 min | ~32 min |

**Recent Trend:**
- Last 5 plans: 01-01 (~45 min), 01-02 (~20 min)
- Trend: Improving — simpler plans execute faster

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Phase 8 (Feature Store) is formally ordered after Phase 7 but should be implemented alongside Phase 3 in practice — feature function begins inline and is later formalized
- [Roadmap]: Phases 9 and 10 (UI) can begin once Phase 4's bracket JSON contract is stable, allowing parallel work with Phases 5-7
- [Research]: Direct barttorvik.com scraping is blocked by Cloudflare — use cbbdata API instead (free key required before Phase 2 begins)
- [Research]: ESPN unofficial API endpoint for 2026 bracket must be verified on Selection Sunday — do not assume 2025 format is stable; manual CSV fallback is required
- [01-01]: data/ is gitignored — raw Kaggle CSVs are not committed; reproducibility via download script
- [01-01]: VALID_TOURNEY_SEASONS starts at 2003 (Kaggle supplemental feature data availability) and excludes 2020 (COVID cancellation) — 22 seasons total
- [01-01]: get_cutoff() raises ValueError on invalid/missing seasons to prevent silent training-set contamination
- [01-01]: Kaggle API key was malformed at execution time — data downloaded manually; kaggle_download.py exists and works with valid credentials
- [01-02]: DuckDB reads DayNum as BIGINT from CSV; DATE + BIGINT arithmetic fails — always CAST(DayNum AS INTEGER) in all future ingest scripts
- [01-02]: 2021 had no First Four games (COVID bubble tournament) — IsFirstFour is correctly absent for 2021 in tournament_games.parquet
- [01-02]: Kaggle 2026 competition dataset includes 2026 regular season in progress (3893 games through 2026-02-04) — downstream queries must apply get_cutoff() for 2026 predictions

### Pending Todos

None yet.

### Blockers/Concerns

- [Pre-Phase 2]: cbbdata API free key must be obtained at cbbdata.aweatherman.com before Phase 2 begins — verify Python REST access (documentation is R-centric)
- [Resolved - 01-01]: Kaggle 2025 data confirmed present — MNCAATourneyCompactResults.csv covers 1985-2025, 2,585 games, max season = 2025
- [Resolved - 01-02]: All three Parquet files written — tournament_games.parquet (1449 games), seeds.parquet (1472 entries), regular_season.parquet (122775 games)
- [Hard deadline]: Auto-fetch bracket pipeline (Phase 2, plan 02-03) must be operational before Selection Sunday 2026 (mid-March) — one-shot operation with no retry window
- [Non-blocking]: Kaggle API key malformed — fix ~/.kaggle/kaggle.json for future automated refreshes, but not required for plan 01-03
- [Note]: 2026 Selection Sunday date not yet in SELECTION_SUNDAY_DATES — must be added once announced (mid-March 2026) to enable get_cutoff(2026)

## Session Continuity

Last session: 2026-03-02
Stopped at: Completed 01-02-PLAN.md — DuckDB ingestion pipeline, three Parquet files written, write_parquet.py orchestrator verified; ready to run plan 01-03
Resume file: None
