# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** v1.1 Phase 11 — Stability Baseline (tag v1.0-stable before any v1.1 work)

## Current Position

Phase: 11 of 16 (Stability Baseline)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-03-13 — v1.1 roadmap created (phases 11-16, 19 requirements mapped)

Progress: [░░░░░░░░░░] v1.1 starting (v1.0 complete: 37/37 plans)

## Accumulated Context

### Decisions

All v1.0 decisions in `.planning/milestones/v1.0-ROADMAP.md` and PROJECT.md Key Decisions table.
Key decisions carried forward:
- TwoTierEnsemble selected (Brier 0.1692) — do not retrain without Brier comparison gate
- ClippedCalibrator [0.05, 0.89] — re-validate bounds if retraining occurs
- cbbdata is the data source — 2025-26 data NOT available as of 2026-03-13

### Blockers/Concerns

- [Phase 12 gate]: cbbdata 2025-26 data must be checked by EOD 2026-03-14 — go/no-go required
- [Phase 15 conditional]: Model enhancement (MODL-01, MODL-02) runs only if conference tourney data is available and Brier doesn't regress
- [Hard deadline]: Selection Sunday 2026-03-15 after 6 PM ET — bracket fetch window; Phase 13 (pool optimizer) must ship before this
- [Hard deadline]: Tournament tip-off 2026-03-19 — app must work; Phase 11 stable tag is the rollback safety net

### Phase Ordering Note

Phase 11 before everything. Phase 12 before Phase 15 (retrain script is the prerequisite). Phases 13 and 14 can run in parallel after Phase 11. Phase 16 is last (live bracket fetch requires final model).

## Session Continuity

Last session: 2026-03-13
Stopped at: Roadmap created — ready to plan Phase 11
Resume file: None
