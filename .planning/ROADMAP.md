# Roadmap: March Madness 2026 Bracket Predictor

## Overview

This project builds a Python-first ML pipeline that ingests 20+ years of NCAA tournament data, engineers efficiency-based features, trains a stacking ensemble, simulates 10,000 bracket outcomes via Monte Carlo, and surfaces results through an interactive Streamlit bracket UI. The five architectural layers — data pipeline, feature store, model layer, bracket simulator, and web UI — are built in strict dependency order, with backtesting and ensemble model selection woven in after a validated baseline exists. The deliverable is a working bracket predictor ready before Selection Sunday 2026 (mid-March).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Historical Data Pipeline** - Ingest, clean, and normalize 20+ years of tournament data from Kaggle and resolve team name conflicts across all sources
- [x] **Phase 2: Current Season and Bracket Data** - Pull 2025-26 season stats from CBBpy/cbbdata and wire up the ESPN auto-fetch pipeline for Selection Sunday
- [x] **Phase 3: Baseline Model and Temporal Validation** - Train a logistic regression baseline with walk-forward temporal CV and establish Brier score / log-loss as the evaluation standard
- [x] **Phase 4: Bracket Simulator** - Build deterministic and Monte Carlo bracket simulation over all 67 tournament games with slot-addressed bracket JSON output
- [x] **Phase 5: Backtesting Harness** - Replay the feature-to-simulator pipeline against 2022–2025 tournament snapshots to validate the baseline and surface calibration issues
- [x] **Phase 6: Ensemble Models** - Add XGBoost and LightGBM base models, stack them with logistic regression as meta-learner, and calibrate ensemble output
- [x] **Phase 7: Model Comparison Dashboard** - Produce a side-by-side performance table (baseline vs. ensemble) across all backtest years with per-round and upset-detection metrics
- [x] **Phase 8: Feature Store** - Formalize the feature computation layer with a tested API, VIF analysis, and verified cutoff-date enforcement for historical replay
- [ ] **Phase 9: Bracket Visualization UI** - Streamlit app displaying the full 68-team bracket as programmatic SVG with predicted winners and per-game win probabilities
- [ ] **Phase 10: Interactive Override UI** - Add manual pick overrides to the bracket UI with downstream cascade recalculation and championship score display

## Phase Details

### Phase 1: Historical Data Pipeline

**Goal**: Normalized game records covering 2003–2025 seasons are stored in DuckDB/Parquet with verified cutoff dates and a team name normalization table that resolves conflicts across all four data sources.

**Depends on**: Nothing (first phase)

**Requirements**: DATA-01, DATA-03

**Success Criteria** (what must be TRUE):
  1. Running the ingestion script produces Parquet files covering 2003–2025 tournament games with no duplicate game records
  2. Every team that appeared in the 2003–2025 tournaments has a canonical name entry in the normalization table, with aliases mapped from ESPN, Kaggle, Sports-Reference, and cbbdata
  3. Loading any team's stats for a given season returns only data dated on or before that year's Selection Sunday (cutoff enforcement verified)
  4. First Four play-in games are correctly distinguished from Round of 64 games in the stored records

**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Project scaffolding, dependencies, Kaggle dataset download, cutoff dates and seasons modules
- [ ] 01-02-PLAN.md — DuckDB ingestion pipeline: tournament games (with First Four tagging), regular season, and seeds to Parquet
- [ ] 01-03-PLAN.md — Team name normalization table with alias seed CSV, plus end-to-end data pipeline verification

---

### Phase 2: Current Season and Bracket Data

**Goal**: 2025-26 season stats are available in the database via CBBpy and cbbdata, and an auto-fetch pipeline is ready to pull the 68-team bracket from ESPN on Selection Sunday with a tested manual CSV fallback.

**Depends on**: Phase 1 (team name normalization table must exist before current data is merged)

**Requirements**: DATA-02, DATA-04

**Success Criteria** (what must be TRUE):
  1. Running the current-season ingestion script populates per-team adjusted efficiency metrics (adjOE, adjDE, barthag) for all 2025-26 Division I teams, normalized against the Phase 1 name table
  2. The bracket auto-fetch script returns a structured 68-team seedings object from the ESPN unofficial API without manual intervention
  3. When the ESPN API is unavailable, loading a manually prepared bracket CSV produces the same 68-team seedings object with no code changes
  4. All 68 bracket teams have corresponding 2025-26 season stats in the database before simulation can run

**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — cbbdata API integration: auth client, fetch 2025-26 torvik ratings, populate espn_slug + cbbdata_name in team normalization table, write current_season_stats.parquet, add 2026 Selection Sunday date
- [ ] 02-02-PLAN.md — ESPN bracket auto-fetch + CSV fallback: scoreboard API parser, manual CSV loader, unified load_bracket() interface, bracket-to-stats coverage verification

---

### Phase 3: Baseline Model and Temporal Validation

**Goal**: A trained logistic regression baseline model exists on disk, walk-forward temporal validation infrastructure is operational, and the first multi-year backtest (2022–2025) establishes baseline Brier score and log-loss benchmarks.

**Depends on**: Phase 1 (historical game records), Phase 2 (current season stats), Phase 8 (feature vectors — see note)

**Requirements**: MODL-01, MODL-03, MODL-04

**Note**: Phase 8 (Feature Store) provides the `compute_features()` API. Phase 3 can proceed with an inline feature computation function that Phase 8 later formalizes, but the temporal CV harness built here is the canonical infrastructure for all subsequent model evaluation.

**Success Criteria** (what must be TRUE):
  1. A trained logistic regression model file exists at `models/logistic_baseline.joblib` and can be loaded to predict win probabilities for arbitrary team-pair inputs
  2. Walk-forward temporal validation runs without data leakage: training on years T-N through T-1 and evaluating on year T produces distinct, non-overlapping splits for 2022, 2023, 2024, and 2025
  3. Brier score and log-loss are computed and printed for each holdout year — a chalk-only model would score ~0.23 Brier; the baseline must score below that
  4. The model produces calibrated probabilities (neither team is assigned 90%+ win probability in a matchup between top-10 ranked opponents)

**Plans**: 4 plans

Plans:
- [ ] 03-01-PLAN.md — Historical Torvik ratings fetch (2003-2025 via cbbdata API) + inline compute_features() and build_matchup_dataset() for differential feature engineering
- [ ] 03-02-PLAN.md — Walk-forward temporal CV harness (year-grouped splits for 2022-2025) + logistic regression training with Optuna hyperparameter sweep + joblib model save
- [ ] 03-03-PLAN.md — Brier score and log-loss evaluation pipeline with chalk comparison table + calibration curve plot + overconfidence check for top-seed matchups
- [ ] 03-04-PLAN.md — Gap closure: isotonic calibration to eliminate overconfident predictions (P > 0.90) for top-10-seeded matchups

---

### Phase 4: Bracket Simulator

**Goal**: A `simulate_bracket()` function accepts team seedings, a predict function, and an optional override map, then fills all 67 tournament games using both deterministic (highest-probability winner) and Monte Carlo (10,000+ Bernoulli draws) modes, producing bracket JSON with full slot addressing.

**Depends on**: Phase 3 (trained model providing a predict function)

**Requirements**: SIML-01, SIML-02, SIML-03, SIML-04

**Success Criteria** (what must be TRUE):
  1. `simulate_bracket(seedings, predict_fn, mode="deterministic")` returns a bracket JSON object where every slot from Round of 64 through the championship is filled with exactly one team and a recorded win probability
  2. `simulate_bracket(seedings, predict_fn, mode="monte_carlo", n_runs=10000)` returns per-team advancement probabilities for each round and a champion confidence percentage
  3. The Monte Carlo distribution produces plausible upset rates: at least 5% of 10,000 simulations show a 10-or-higher seed reaching the Sweet 16 (calibration sanity check)
  4. The champion prediction includes a predicted championship game score (point total and margin)
  5. Passing an override map `{slot_id: team_id}` re-runs simulation from that slot forward, producing different downstream results

**Plans**: 6 plans

Plans:
- [x] 04-01-PLAN.md — Bracket slot schema (slot tree from Kaggle CSV, seedings loader, predict_fn builder, team-seed map)
- [x] 04-02-PLAN.md — Deterministic bracket fill (topological slot tree traversal, 67 slots with winners and probabilities)
- [x] 04-03-PLAN.md — Monte Carlo simulation (pre-computed 68x68 prob matrix, vectorized numpy Bernoulli draws, advancement probs)
- [x] 04-04-PLAN.md — Championship score prediction (rule-based tempo formula, integrated into deterministic output)
- [x] 04-05-PLAN.md — Override map injection (force winners in both modes, downstream cascade, upstream unaffected)
- [x] 04-06-PLAN.md — Calibration validation (upset rate check, all 5 success criteria verified)

---

### Phase 5: Backtesting Harness

**Goal**: A `backtest()` function replays the feature-to-simulator pipeline against 2022, 2023, 2024, and 2025 tournament snapshots with strict data cutoff enforcement, producing a per-year accuracy and calibration table for the baseline model.

**Depends on**: Phase 3 (baseline model + temporal CV), Phase 4 (bracket simulator)

**Requirements**: BACK-01, BACK-02

**Success Criteria** (what must be TRUE):
  1. Running `backtest(year_range=[2022,2023,2024,2025], model="baseline")` produces a table showing per-round accuracy, ESPN bracket score equivalent, Brier score, log-loss, and upset-detection rate for each year without manual data preparation
  2. The 2025 backtest result uses only data available as of that year's Selection Sunday — post-tournament game records do not appear in the 2025 training set
  3. The multi-year backtest covers distinct variance profiles: 2022 (Saint Peter's Elite Eight), 2023 (FAU Final Four), 2024 (NC State run), and 2025 (all-chalk Final Four) are all represented with individual-year scores
  4. Backtest results are written to `backtest/results.json` and can be reproduced identically by re-running the harness

**Plans**: 3 plans

Plans:
- [x] 05-01-PLAN.md — Scoring helpers: actual slot winners, ESPN bracket scoring, game-level metrics
- [x] 05-02-PLAN.md — Backtest orchestration: per-year model refit, bracket simulation, JSON output
- [x] 05-03-PLAN.md — Validation: temporal isolation, 2025 verification (BACK-01), reproducibility

---

### Phase 6: Ensemble Models

**Goal**: XGBoost and LightGBM base models are trained with temporal CV, stacked with logistic regression as the meta-learner, and the ensemble output is calibrated — producing win probabilities that outperform the logistic regression baseline on multi-year Brier score.

**Depends on**: Phase 5 (backtest results establish what the baseline achieves; ensemble composition is guided by evidence)

**Requirements**: MODL-02

**Success Criteria** (what must be TRUE):
  1. XGBoost and LightGBM models are trained with the same walk-forward temporal splits as the baseline, and their individual Brier scores are logged alongside the baseline for comparison
  2. A stacking ensemble combines XGBoost, LightGBM, and logistic regression with logistic regression as the meta-learner, and a single `ensemble.predict_proba()` call returns calibrated win probabilities (NOTE: uses manual OOF temporal stacking via TwoTierEnsemble, not sklearn StackingClassifier, because StackingClassifier's cross_val_predict raises ValueError with non-partition walk-forward splits — see sklearn GitHub issue #32614)
  3. The ensemble achieves a lower multi-year Brier score than the logistic regression baseline alone on the 2022–2025 holdout set
  4. Calibration curves for the ensemble show predicted probabilities within 5 percentage points of actual win rates across decile bins

**Plans**: TBD

Plans:
- [ ] 06-01: XGBoost model training (optuna hyperparameter search; temporal CV; log Brier score and log-loss per year)
- [ ] 06-02: LightGBM model training (optuna hyperparameter search; temporal CV; log Brier score and log-loss per year)
- [ ] 06-03: Stacking ensemble assembly (manual OOF temporal stacking via TwoTierEnsemble; logistic regression meta-learner; walk_forward_splits for OOF generation)
- [ ] 06-04: Probability calibration (Platt scaling or isotonic regression on held-out calibration set; plot calibration curves before and after)
- [ ] 06-05: Ensemble backtest run (re-run Phase 5 harness with ensemble predict function; update backtest/results.json with ensemble row)

---

### Phase 7: Model Comparison Dashboard

**Goal**: A side-by-side comparison table shows baseline vs. ensemble performance across all backtest years, per round, and on upset detection rate — making it clear which model to use for the 2026 bracket.

**Depends on**: Phase 5 (baseline backtest results), Phase 6 (ensemble backtest results)

**Requirements**: BACK-03

**Success Criteria** (what must be TRUE):
  1. Running a single command prints (or displays in Streamlit) a formatted table comparing logistic regression baseline vs. XGBoost vs. LightGBM vs. ensemble across the 2022–2025 holdout years with per-round accuracy, overall Brier score, and upset detection rate
  2. The table includes a recommended model row identifying the best performer by multi-year Brier score
  3. A bar chart or heat map visualizes per-round accuracy differences between models, making it easy to see where the ensemble improves on the baseline

**Plans**: 3 plans in 3 waves

Plans:
- [ ] 07-01-PLAN.md — Comparison table formatter (create src/dashboard/ module; load backtest JSON; print formatted side-by-side table with per-year Brier, per-round accuracy, upset detection tradeoff)
- [ ] 07-02-PLAN.md — Visualization (matplotlib grouped bar chart of per-round accuracy; heatmap of Brier score by model and year; save as PNG)
- [ ] 07-03-PLAN.md — Model recommendation logic (select best model by multi-year mean Brier score; write models/selected.json with artifact path for Phase 9)

---

### Phase 8: Feature Store

**Goal**: A formalized `compute_features(team_a, team_b, season)` function with full test coverage, VIF analysis documenting multicollinearity levels, and verified cutoff-date enforcement for historical replay becomes the single source of feature vectors for all models and backtests.

**Depends on**: Phase 1 (normalized data), Phase 2 (current season stats)

**Note**: Phase 8 is ordered after Phase 7 because feature computation begins informally in Phase 3, evolves through Phases 5-6, and is formalized here after the feature set is stable. Phases 3-7 can use the inline feature function; Phase 8 replaces it with the tested, validated API. In execution, Phase 8 work should happen alongside Phase 3 in practice — but the formal acceptance criteria depend on the full feature set having been exercised through backtesting.

**Requirements**: (Supports MODL-01, MODL-02, MODL-03, MODL-04 — feature engineering is a prerequisite for all modeling requirements; this phase formally closes that prerequisite)

**Note on requirements mapping**: The feature store is the implementation substrate for the modeling requirements. Since MODL-01, MODL-02, MODL-03, MODL-04 are already mapped to Phases 3 and 6, Phase 8 formalizes the shared infrastructure. No v1 requirement is orphaned — this phase captures the formalization work that those requirements depend on.

**Success Criteria** (what must be TRUE):
  1. Calling `compute_features(team_a="Duke", team_b="Michigan", season=2025)` returns a named feature vector with adjOE differential, adjDE differential, barthag differential, seed differential, tempo differential, and WAB differential (Wins Above Bubble) — with unit tests covering known historical matchups
  2. VIF analysis on the feature matrix from 2003-2025 historical matchups is formally conducted, with all features documented — five features have VIF below 10, and the one exceedance (barthag_diff, VIF=11.2) has a KEEP_ALL decision documented in models/vif_report.json per decision [03-01], as regularized models (L2-penalized LR, XGBoost, LightGBM) are robust to moderate multicollinearity
  3. Calling `compute_features(..., as_of_date=selection_sunday_2025)` returns only stats available before that date — cutoff enforcement is by construction via the cbbdata archive endpoint (season-level aggregates fetched at or before Selection Sunday), with as_of_date validation confirming the date is a recognized Selection Sunday
  4. Swapping team A and team B inverts the differential signs exactly (feats(A,B) + feats(B,A) = 0 for all features) — feature-level perspective symmetry is verified with unit tests across multiple team pairs and seasons. Note: model-level probability symmetry (P(B beats A) = 1 - P(A beats B)) does not hold because the StandardScaler is trained on data where team_a is always the lower seed, producing non-zero feature means that break scaling symmetry. This is expected and documented.

**Plans**: 4 plans

Plans:
- [ ] 08-01-PLAN.md — Dependencies (pytest, statsmodels) + name-based compute_features() public API with team name resolution + rename internal function + update all call sites
- [ ] 08-02-PLAN.md — VIF analysis module (compute VIF on full feature matrix with statsmodels; document barthag_diff exceedance with KEEP decision; write models/vif_report.json)
- [ ] 08-03-PLAN.md — Pytest suite (known matchup fixtures, perspective symmetry, cutoff enforcement verification, VIF threshold tests; all SC-1 through SC-4 covered)
- [ ] 08-04-PLAN.md — Gap closure: update success criteria to match implementation decisions (VIF exceedance, cutoff-by-construction, feature-only symmetry, WAB naming)

---

### Phase 9: Bracket Visualization UI

**Goal**: A Streamlit application displays the full 68-team bracket as a programmatic SVG, showing predicted winners in each slot and per-game win probabilities, using the selected ensemble model's outputs.

**Depends on**: Phase 4 (bracket JSON contract), Phase 7 (model selection), Phase 8 (feature store API)

**Requirements**: WEBU-01, WEBU-02

**Success Criteria** (what must be TRUE):
  1. Launching `streamlit run app.py` renders a complete 68-team bracket in the browser, including First Four play-in games, with all 67 game slots filled with the predicted winning team
  2. Each game slot displays the win probability for the predicted winner alongside the two competing team names
  3. The bracket layout correctly shows all four regions (East, West, South, Midwest) with rounds progressing from left to right toward the championship
  4. A sidebar or panel shows round-by-round advancement probabilities for all 68 teams as a sortable table

**Plans**: 4 plans

Plans:
- [ ] 09-01-PLAN.md — Streamlit app scaffolding (install deps, model loading, ensemble predict_fn adapter, cached simulations, team name lookup, tab skeleton)
- [ ] 09-02-PLAN.md — SVG bracket layout algorithm (coordinate generation for 68-team bracket; slot positioning for all four regions, First Four, and Final Four)
- [ ] 09-03-PLAN.md — SVG bracket rendering + champion panel (programmatic SVG via st.components.v1.html with team names, seeds, win probs, connector lines, champion highlight; champion tab with MC confidence and top contenders)
- [ ] 09-04-PLAN.md — Advancement probability table (st.dataframe with ProgressColumn showing P(team reaches round) for all 68 teams across 7 round milestones; sortable, searchable)

---

### Phase 10: Interactive Override UI

**Goal**: Users can click a game slot in the bracket to override the predicted winner, and all downstream slots immediately recalculate using the Monte Carlo simulator with the override map applied.

**Depends on**: Phase 9 (bracket SVG UI), Phase 4 (override map injection in simulator)

**Requirements**: WEBU-03

**Success Criteria** (what must be TRUE):
  1. Clicking a team name in any bracket slot overrides the predicted winner for that game, and all subsequent rounds involving that slot immediately show updated predicted winners and win probabilities
  2. A "Reset to model picks" button restores the full bracket to the ensemble model's predictions in a single click
  3. The override state persists within a Streamlit session — refreshing the page or switching tabs does not clear manually entered overrides
  4. After an override, champion confidence percentage and advancement probabilities update to reflect the manual pick propagated through all downstream simulation

**Plans**: TBD

Plans:
- [ ] 10-01: Override state management (st.session_state override map; slot click events via SVG interaction or st.button workaround; persist across rerenders)
- [ ] 10-02: Cascade recalculation trigger (on override change, call simulate_bracket() with updated override map; update bracket JSON in session state)
- [ ] 10-03: UI feedback for overrides (visually distinguish overridden slots from model-predicted slots; show original model prediction alongside override)
- [ ] 10-04: Reset functionality (clear override map from session state; re-run simulation with empty override; restore all downstream predictions)
- [ ] 10-05: End-to-end override integration test (manually override a Round of 64 result; verify all 6 downstream rounds update correctly for the affected region)

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

Note: Phase 8 (Feature Store formalization) should be done in practice alongside Phase 3 but is formally gated on stable feature set after Phase 6. Phases 9 and 10 can begin once Phase 4's bracket JSON contract is stable.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Historical Data Pipeline | 3/3 | ✓ Complete | 2026-03-02 |
| 2. Current Season and Bracket Data | 2/2 | ✓ Complete | 2026-03-03 |
| 3. Baseline Model and Temporal Validation | 4/4 | ✓ Complete | 2026-03-04 |
| 4. Bracket Simulator | 6/6 | ✓ Complete | 2026-03-04 |
| 5. Backtesting Harness | 3/3 | ✓ Complete | 2026-03-04 |
| 6. Ensemble Models | 5/5 | ✓ Complete | 2026-03-04 |
| 7. Model Comparison Dashboard | 3/3 | ✓ Complete | 2026-03-04 |
| 8. Feature Store | 4/4 | ✓ Complete | 2026-03-04 |
| 9. Bracket Visualization UI | 0/4 | Not started | - |
| 10. Interactive Override UI | 0/5 | Not started | - |
