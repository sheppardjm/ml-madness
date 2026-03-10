# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** v1.0 shipped. Planning next milestone or Selection Sunday data refresh.

## Current Position

Phase: v1.0 complete (10 phases, 37 plans)
Plan: N/A — between milestones
Status: v1.0 MVP shipped. Ready for `/gsd:new-milestone` or Selection Sunday prep.
Last activity: 2026-03-10 — v1.0 milestone archived

Progress: [██████████] v1.0 complete

## Accumulated Context

### Decisions

All v1.0 decisions archived in `.planning/milestones/v1.0-ROADMAP.md`.
Key decisions carried forward:
- TwoTierEnsemble is the selected model (Brier 0.1692)
- ClippedCalibrator [0.05, 0.89] is the calibration strategy
- cbbdata is the data source (free Torvik metrics)
- DuckDB + Parquet is the storage layer

### Pending Todos

- Refresh current_season_stats.parquet when cbbdata indexes 2025-26 season (check /api/torvik/ratings?year=2026 for non-empty barthag)
- On Selection Sunday (2026-03-15): run `uv run python -m src.ingest.fetch_bracket` to confirm auto-fetch returns 68 teams; if <68, populate data/seeds/bracket_manual.csv

### Blockers/Concerns

- [Important]: current_season_stats.parquet contains 2024-25 season metrics as proxy — refresh when cbbdata indexes 2025-26
- [Time-sensitive]: Must run bracket fetch on/after Selection Sunday (2026-03-15 after 6 PM ET); CSV fallback is ready if ESPN auto-fetch fails

## Session Continuity

Last session: 2026-03-10
Stopped at: v1.0 milestone archived
Resume file: None
