# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** v1.1 — Selection Sunday data refresh, pool strategy optimizer, UI enrichment, model retrain.

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-13 — Milestone v1.1 started

Progress: [░░░░░░░░░░] v1.1 starting

## Accumulated Context

### Decisions

All v1.0 decisions archived in `.planning/milestones/v1.0-ROADMAP.md`.
Key decisions carried forward:
- TwoTierEnsemble is the selected model (Brier 0.1692)
- ClippedCalibrator [0.05, 0.89] is the calibration strategy
- cbbdata is the data source (free Torvik metrics)
- DuckDB + Parquet is the storage layer

### Data Status (as of 2026-03-13)

- cbbdata has NOT indexed 2025-26 season — API returns 2024-25 archive as proxy
- Bracket fetch pipeline verified green — ESPN returns 0 teams (expected pre-Sunday), CSV fallback ready
- Team resolution: 64/64 test teams resolved, stats coverage: 64/64

### Blockers/Concerns

- [Important]: cbbdata 2025-26 data not yet available — must check again before/on Selection Sunday
- [Time-sensitive]: Selection Sunday 2026-03-15 after 6 PM ET — bracket fetch window
- [Dependency]: Model retrain blocked until 2025-26 season data available from cbbdata

## Session Continuity

Last session: 2026-03-13
Stopped at: v1.1 milestone initialization — defining requirements
Resume file: None
