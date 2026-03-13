# Roadmap: March Madness 2026 Bracket Predictor

## Milestones

- ✅ **v1.0 MVP** - Phases 1-10 (shipped 2026-03-10)
- 🚧 **v1.1 Selection Sunday + Pool Strategy** - Phases 11-16 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-10) - SHIPPED 2026-03-10</summary>

Full phase details archived in `.planning/milestones/v1.0-ROADMAP.md`.

| Phase | Goal | Plans |
|-------|------|-------|
| 1. Historical Data Pipeline | Normalized game records 2003-2025 in DuckDB/Parquet | 3/3 |
| 2. Current Season and Bracket Data | 2025-26 stats + ESPN bracket auto-fetch pipeline | 2/2 |
| 3. Baseline Model and Temporal Validation | LR baseline, walk-forward CV, multi-year backtest | 4/4 |
| 4. Bracket Simulator | Monte Carlo 10K runs, championship score prediction | 4/4 |
| 5. Backtesting Harness | ESPN scoring against 2022-2025 historical brackets | 4/4 |
| 6. Ensemble Models | XGBoost + LightGBM + LR meta-learner, Brier 0.1692 | 4/4 |
| 7. Model Comparison Dashboard | Side-by-side model evaluation UI | 4/4 |
| 8. Feature Store | Validated API, VIF analysis, cutoff enforcement, 22 tests | 4/4 |
| 9. Bracket Visualization UI | 68-team SVG bracket with win probabilities | 4/4 |
| 10. Interactive Override UI | Manual pick overrides with downstream cascade | 4/4 |

</details>

---

### 🚧 v1.1 Selection Sunday + Pool Strategy (In Progress)

**Milestone Goal:** Refresh model with real 2025-26 data, fetch the live bracket on Selection Sunday, add a pool-strategy optimizer for large pools, and enrich the UI with matchup context — all before tournament tips off on 2026-03-19.

**Hard deadlines:**
- EOD 2026-03-14: go/no-go decision on cbbdata 2025-26 data availability
- 2026-03-15 after 6 PM ET: live bracket fetch window (Selection Sunday)
- 2026-03-19: tournament tip-off — app must be working

---

#### Phase 11: Stability Baseline

**Goal**: v1.0 is tagged and verified before any v1.1 work begins, creating an unconditional rollback point if the app breaks before tip-off.

**Depends on**: Nothing (safety gate before all v1.1 work)

**Requirements**: STAB-01, STAB-02

**Success Criteria** (what must be TRUE):
  1. `git tag v1.0-stable` exists and `git checkout v1.0-stable` restores a fully working app
  2. Running the E2E smoke test confirms the bracket renders, Monte Carlo simulation completes, pick overrides cascade correctly, and champion is displayed
  3. If the app is broken at any point before 2026-03-19, reverting to v1.0-stable restores a working predictor within minutes

**Plans**: TBD

Plans:
- [ ] 11-01: Tag v1.0-stable and run E2E smoke test

---

#### Phase 12: Data Refresh and Pipeline Hygiene

**Goal**: The go/no-go decision on 2025-26 season data is made and documented, the retrain orchestration script exists, pipeline constants are updated for 2026, and the UI shows which season's data is active.

**Depends on**: Phase 11

**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, MODL-03

**Success Criteria** (what must be TRUE):
  1. The sidebar shows a data vintage label (e.g., "Using 2024-25 proxy data — refreshed 2026-03-13") that updates when data changes
  2. Running `scripts/retrain.py` produces a pre/post Brier comparison and requires explicit confirmation before overwriting the model artifact
  3. `build_stats_lookup()` accepts a season year argument — passing 2026 does not raise an error (even if data is unavailable)
  4. `BACKTEST_YEARS` includes 2026 and `SELECTION_SUNDAY_DATES` includes 2026-03-15 in the relevant constants files
  5. A documented go/no-go decision on cbbdata 2025-26 availability exists (in a comment, log output, or note) by EOD 2026-03-14

**Plans**: TBD

Plans:
- [ ] 12-01: Parameterize build_stats_lookup() year, update BACKTEST_YEARS and SELECTION_SUNDAY_DATES constants
- [ ] 12-02: Check cbbdata 2025-26 availability, make go/no-go decision, add data vintage label to UI sidebar
- [ ] 12-03: Build scripts/retrain.py with ingest → train → Brier comparison → artifact backup flow

---

#### Phase 13: Pool Strategy Optimizer

**Goal**: Users can see which teams are undervalued relative to public pick popularity and make contrarian bracket decisions with a configurable scoring system and pool size context.

**Depends on**: Phase 11 (stable baseline), Phase 12 (data vintage known)

**Requirements**: POOL-01, POOL-02, POOL-03, POOL-04, POOL-05

**Success Criteria** (what must be TRUE):
  1. A Pool Strategy tab shows a value score table (`win_prob - pick_pct`) for all 68 teams at Final Four and Championship rounds, sorted by leverage
  2. The champion recommendation callout identifies the top-2 undervalued champion candidates with a plain-language explanation of why they have value
  3. Changing the pool size input (e.g., from 30 to 150 entrants) visibly shifts the optimizer's risk recommendation between chalk and contrarian strategy
  4. The scoring system fields default to ESPN standard (1-2-4-8-16-32) and changing round weights updates the value table
  5. Seed-based pick popularity priors are used as the default pick percentage baseline without requiring manual entry, and the data source assumption is visible in the UI

**Plans**: TBD

Plans:
- [ ] 13-01: Build src/pool/optimizer.py — compute_pool_strategy() with EV formula and seed-based pick priors
- [ ] 13-02: Build src/ui/pool_loader.py cache wrapper and Pool Strategy tab in app.py
- [ ] 13-03: Wire pool size input, scoring system configuration, and champion recommendation callout into the UI

---

#### Phase 14: UI Matchup Context

**Goal**: Clicking into any bracket matchup shows a side-by-side stat comparison with color-coded advantage indicators and historical seed win rates, without rebuilding any existing UI components.

**Depends on**: Phase 11 (stable baseline)

**Requirements**: UIMX-01, UIMX-02, UIMX-03

**Success Criteria** (what must be TRUE):
  1. Expanding any bracket game slot reveals a stat comparison panel showing barthag, adjOE, adjDE, wab, and seed for both teams
  2. Each metric has a color-coded advantage indicator — green for the team with the better value, red for the team with the worse value (KenPom-style)
  3. The panel shows the historical win rate for that seed matchup (e.g., "#5 seed vs #12 seed: favorites win 65% historically") drawn from tournament_games.parquet

**Plans**: TBD

Plans:
- [ ] 14-01: Build src/ui/matchup_context.py and src/ui/seed_history.py with @st.cache_data wrappers
- [ ] 14-02: Add load_stats_lookup_cached() to data_loader.py; integrate stat panels into override_controls.py expanders

---

#### Phase 15: Model Enhancement

**Goal**: Conference tournament depth is ingested as a feature for all historical seasons, validated to improve Brier score, and conditionally added to the model.

**Depends on**: Phase 12 (retrain script exists, pipeline parameterized)

**Requirements**: MODL-01, MODL-02

**Success Criteria** (what must be TRUE):
  1. Conference tournament wins/depth are available as a numeric column in the historical feature store for seasons where data is available
  2. Running the backtest with and without the conference tournament feature produces a documented Brier comparison — the feature is only merged to the model if Brier does not increase
  3. The ensemble retrain completes without errors when the new feature column is present, and the model artifact is backed up before any swap

**Plans**: TBD

Plans:
- [ ] 15-01: Ingest conference tournament depth data for historical seasons; add as model feature with Brier gate validation

---

#### Phase 16: Selection Sunday Operations

**Goal**: On Selection Sunday, the live 68-team bracket is fetched and loaded into the app, full win probability predictions are generated for every slot, and the complete bracket is displayed with the final model.

**Depends on**: Phases 11-15 (all v1.1 work complete; model is in its final state)

**Requirements**: SDAY-01, SDAY-02

**Success Criteria** (what must be TRUE):
  1. After Selection Sunday bracket announcement, running the fetch pipeline returns exactly 68 teams with seeds, regions, and slots populated
  2. If the auto-fetch returns fewer than 68 teams, the CSV fallback loads bracket_manual.csv and produces the same 68-team structure without error
  3. The app displays win probabilities for all 67 bracket slots, a champion prediction, and confidence percentage using the final model

**Plans**: TBD

Plans:
- [ ] 16-01: Verify ESPN auto-fetch against live bracket; confirm CSV fallback; generate full predictions and display in UI

---

## Progress

| Phase | Milestone | Requirements | Plans Complete | Status | Completed |
|-------|-----------|--------------|----------------|--------|-----------|
| 1. Historical Data Pipeline | v1.0 | DATA-01, DATA-03 | 3/3 | Complete | 2026-03-10 |
| 2. Current Season and Bracket Data | v1.0 | DATA-02, DATA-04 | 2/2 | Complete | 2026-03-10 |
| 3. Baseline Model and Temporal Validation | v1.0 | MODL-01, MODL-03, MODL-04 | 4/4 | Complete | 2026-03-10 |
| 4. Bracket Simulator | v1.0 | SIM-01 through SIM-04 | 4/4 | Complete | 2026-03-10 |
| 5. Backtesting Harness | v1.0 | BACK-01 through BACK-03 | 4/4 | Complete | 2026-03-10 |
| 6. Ensemble Models | v1.0 | MODL-02, MODL-05 | 4/4 | Complete | 2026-03-10 |
| 7. Model Comparison Dashboard | v1.0 | MODL-06 | 4/4 | Complete | 2026-03-10 |
| 8. Feature Store | v1.0 | FEAT-01 through FEAT-04 | 4/4 | Complete | 2026-03-10 |
| 9. Bracket Visualization UI | v1.0 | UI-01 through UI-03 | 4/4 | Complete | 2026-03-10 |
| 10. Interactive Override UI | v1.0 | UI-04 through UI-06 | 4/4 | Complete | 2026-03-10 |
| 11. Stability Baseline | v1.1 | STAB-01, STAB-02 | 0/TBD | Not started | - |
| 12. Data Refresh and Pipeline Hygiene | v1.1 | DATA-01, DATA-02, DATA-03, DATA-04, MODL-03 | 0/TBD | Not started | - |
| 13. Pool Strategy Optimizer | v1.1 | POOL-01 through POOL-05 | 0/TBD | Not started | - |
| 14. UI Matchup Context | v1.1 | UIMX-01, UIMX-02, UIMX-03 | 0/TBD | Not started | - |
| 15. Model Enhancement | v1.1 | MODL-01, MODL-02 | 0/TBD | Not started | - |
| 16. Selection Sunday Operations | v1.1 | SDAY-01, SDAY-02 | 0/TBD | Not started | - |
