# Requirements: March Madness 2026 Bracket Predictor

**Defined:** 2026-03-13
**Core Value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — the model must produce better-than-seed-based predictions validated against historical tournament results.

## v1.1 Requirements

Requirements for Selection Sunday readiness, pool strategy optimization, UI enrichment, and model enhancement.

### Stability

- [ ] **STAB-01**: v1.0-stable git tag created before any v1.1 development begins
- [ ] **STAB-02**: E2E smoke test passes (bracket renders, MC simulation runs, overrides cascade correctly, champion displayed)

### Pool Strategy Optimizer

- [ ] **POOL-01**: Value score table showing `win_prob - pick_pct` for all 68 teams at Final Four and Championship rounds, sorted by leverage
- [ ] **POOL-02**: Seed-based pick popularity priors as default input (historically calibrated from tournament_games.parquet — no manual entry required for MVP)
- [ ] **POOL-03**: Champion recommendation callout highlighting top-2 undervalued champion candidates with plain-language explanation
- [ ] **POOL-04**: Configurable scoring system with default ESPN standard (1-2-4-8-16-32) and user-adjustable round weights
- [ ] **POOL-05**: Pool size input that adjusts optimizer risk tolerance (chalk strategy for <50 entrants, contrarian for 100+)

### UI Matchup Context

- [ ] **UIMX-01**: Side-by-side stat comparison panel for any bracket game showing barthag, adjOE, adjDE, wab, and seed for both teams
- [ ] **UIMX-02**: Color-coded advantage indicators per metric (green for advantage, red for disadvantage — KenPom-style)
- [ ] **UIMX-03**: Historical seed matchup win rate queried from tournament_games.parquet (e.g., "#5 vs #12 seeds: favorites win 65% historically")

### Model Enhancement

- [ ] **MODL-01**: Conference tournament depth/wins ingested as new data source for all historical seasons
- [ ] **MODL-02**: Conference tournament performance added as model feature, validated to improve Brier score before permanent inclusion
- [ ] **MODL-03**: Season year parameterized in build_stats_lookup() — remove hard-coded 2025 so pipeline works with 2026 data

### Data Refresh & Retraining

- [ ] **DATA-01**: cbbdata 2025-26 season data availability checked with explicit go/no-go decision by EOD 2026-03-14; fallback is v1.0 model with "2024-25 proxy data" label
- [ ] **DATA-02**: Data vintage label displayed in UI sidebar showing which season's stats are active and when they were last refreshed
- [ ] **DATA-03**: Retrain script (scripts/retrain.py) orchestrating ingest → train → Brier comparison → artifact backup before swap
- [ ] **DATA-04**: BACKTEST_YEARS updated to include 2026 in temporal_cv.py; SELECTION_SUNDAY_DATES updated with 2026-03-15 in cutoff_dates.py

### Selection Sunday Operations

- [ ] **SDAY-01**: Fetch live 68-team bracket on Selection Sunday (2026-03-15 after 6 PM ET) via ESPN auto-fetch pipeline; CSV fallback ready if auto-fetch returns <68 teams
- [ ] **SDAY-02**: Generate full bracket predictions with final model and display complete bracket with win probabilities in UI

## Future Requirements

Deferred to v2.0 or post-tournament.

### Pool Optimizer Enhancements
- **POOL-F01**: Automated ESPN/Yahoo pick percentage scraping or paste-import
- **POOL-F02**: Expected score calculator against simulated opponent field
- **POOL-F03**: Full 7-round value table (all rounds, not just FF/Championship)
- **POOL-F04**: Chalk risk warning when bracket correlates too strongly with public picks

### UI Enhancements
- **UIMX-F01**: Advancement probability sparkline per team (round-by-round MC odds)
- **UIMX-F02**: SHAP feature importance per matchup (requires shap dependency)
- **UIMX-F03**: Four-factor breakdown (eFG%, TO%, OR%, FTR) — requires additional data ingestion

### Model Improvements
- **MODL-F01**: Hyperparameter re-tuning on expanded dataset (only if Brier regresses)
- **MODL-F02**: Feature importance drift analysis post-retrain
- **MODL-F03**: Explainability/feature importance in UI

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-generated "optimal bracket" | Users distrust what they can't inspect; show value signals and let user decide |
| Real-time tournament tracking | Different product; matchup context is pre-game only |
| Multi-user / social features | Personal tool — no auth needed |
| Calcutta / auction pool optimizer | Entirely different EV calculation; not bracket format |
| Automated CI/CD retraining pipeline | Once-per-year personal tool; 50-line script is sufficient |
| Pick percentage scraping | ESPN/Yahoo HTML changes yearly; manual entry with seed priors is reliable |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STAB-01 | TBD | Pending |
| STAB-02 | TBD | Pending |
| POOL-01 | TBD | Pending |
| POOL-02 | TBD | Pending |
| POOL-03 | TBD | Pending |
| POOL-04 | TBD | Pending |
| POOL-05 | TBD | Pending |
| UIMX-01 | TBD | Pending |
| UIMX-02 | TBD | Pending |
| UIMX-03 | TBD | Pending |
| MODL-01 | TBD | Pending |
| MODL-02 | TBD | Pending |
| MODL-03 | TBD | Pending |
| DATA-01 | TBD | Pending |
| DATA-02 | TBD | Pending |
| DATA-03 | TBD | Pending |
| DATA-04 | TBD | Pending |
| SDAY-01 | TBD | Pending |
| SDAY-02 | TBD | Pending |

**Coverage:**
- v1.1 requirements: 19 total
- Mapped to phases: 0
- Unmapped: 19 ⚠️

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after initial definition*
