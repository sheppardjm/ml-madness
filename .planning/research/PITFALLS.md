# Domain Pitfalls: NCAA Bracket Prediction

**Domain:** NCAA Men's Basketball Tournament Bracket Predictor
**Last updated:** 2026-03-13 (v1.1 additions — pool optimizer, UI enrichment, model retraining)
**Previous version:** 2026-03-02 (v1.0 — foundational ML pitfalls)
**Confidence:** MEDIUM-HIGH — v1.0 pitfalls from multiple peer-reviewed and practitioner sources; v1.1 pitfalls from domain research, verified codebase inspection, and pool-strategy practitioner sources

---

## Part I: v1.1 Pitfalls (New)

Pitfalls specific to adding pool strategy optimization, UI enrichment, and model retraining to the existing v1.0 system under Selection Sunday time pressure (2026-03-15, 2 days away).

---

## Critical Pitfalls (v1.1)

Mistakes that cause the feature to be wrong, broken, or misleading at tournament tip-off.

---

### Pitfall V1.1-C1: Pool Optimizer Optimizes for Probability, Not Expected Pool Score

**What goes wrong:** The pool optimizer is built by re-using the existing `simulate_bracket()` deterministic output — picking the highest-probability team at every slot — and labeling this the "pool-optimized bracket." This produces a chalk bracket, which is exactly what the optimizer should be differentiating from.

**Why it happens:** The v1.0 simulator already fills brackets by probability. It feels natural to wrap this in a "pool optimizer" label. The conceptual error is conflating "who will probably win" (a prediction problem) with "who should I pick to maximize my expected pool score" (an optimization problem).

**Consequences:** The "contrarian bracket" is identical to the chalk bracket. In a 100+ person pool where 40-60% of entrants also pick chalk, this bracket has near-zero expected value above the median. The feature ships but provides no strategic value.

**Prevention:**
- The optimizer must treat each pick as having two inputs: win probability (from model) and pick popularity (from public data sources). A team that has a 40% win probability but is picked by only 15% of entrants has positive contrarian value. A team that has 65% win probability but is picked by 55% of entrants has negative contrarian value despite being the favorite.
- The expected value formula for a contrarian pick in a large pool is approximately: EV(pick) ∝ P(team advances) / P(public picks same team). A pick where your model's probability exceeds the public pick percentage creates positive expected value.
- Do NOT reuse `simulate_bracket(mode='deterministic')` as the optimizer output. The optimizer needs a separate code path that accounts for pick popularity.

**Warning signs:**
- The pool optimizer output bracket is identical to the deterministic bracket
- The optimizer does not have an input for "pool size" or "public pick percentages"
- Champion picks in the optimizer bracket are always a #1 or #2 seed

**Phase to address:** Pool optimizer implementation phase.

---

### Pitfall V1.1-C2: No Public Pick Percentage Data — Contrarian Logic Has No Baseline

**What goes wrong:** The optimizer uses a hardcoded or estimated public pick distribution (e.g., "assume 50% of people pick #1 seeds to win the championship") instead of actual observed public pick percentages. The "contrarian" calculation then reflects assumptions about public behavior, not actual public behavior.

**Why it happens:** Public pick percentage data is not available from a free, structured API. ESPN discontinued their comprehensive "Who Picked Whom" breakdown. Getting actual ownership data requires either a paid service (PoolGenius) or scraping from ESPN/Yahoo bracket challenge pages — neither is a clean free API.

**Consequences:** Two failure modes:
1. If the hardcoded pick rates are too high (overestimate chalk-picking), the optimizer over-recommends underdogs that the public isn't actually over-picking.
2. If hardcoded rates are too low, the optimizer under-penalizes popular picks and produces a bracket nearly as chalk as the baseline.

Both cases mean the optimizer is running on wrong data.

**Prevention:**
- Acknowledge this data gap explicitly before building the optimizer. The architecture decision is: (a) proxy with ESPN/Yahoo bracket challenge public pick percentages (requires scraping, reliability unknown), (b) proxy with betting market implied probabilities (public bets approximate public bracket picks), or (c) use a principled default model of public pick behavior (e.g., "public picks the higher seed ~70% of the time in R1, ~85% for seeds 1-4 in later rounds").
- The most defensible approach for v1.1 under time pressure: use historically calibrated seed-based pick popularity priors (which are documented in PoolGenius research) as the pick popularity proxy. This is honest about being an estimate.
- ESPN Tournament Challenge does show champion pick percentage and a "People's Bracket" — these are fetchable after brackets are announced (Selection Sunday) and before tournament starts. Plan to scrape these specific data points from the ESPN public bracket page.
- Yahoo Sports Bracket Challenge shows per-round pick percentages — a more complete source if accessible.

**Warning signs:**
- Optimizer config has no input field for actual pool or public pick data
- Optimizer documentation claims "contrarian" without specifying the source of the pick popularity baseline

**Phase to address:** Pool optimizer design phase; document the data source decision explicitly.

---

### Pitfall V1.1-C3: Model Retraining With Mismatched Season Data Silently Degrades Performance

**What goes wrong:** The model is retrained when cbbdata indexes 2025-26 data. The retraining uses the same `build_matchup_dataset()` call but the new `current_season_stats.parquet` now contains 2025-26 data. However, if the column schema, value ranges, or normalization approach changed between the 2024-25 proxy data and the real 2025-26 data, the retrained scaler and model embed different feature distributions, and predictions for 2026 bracket games silently shift.

**Why it happens:** The v1.0 codebase treats `current_season_stats.parquet` as the live season stats file. Replacing it triggers a full model retrain. If the cbbdata API returns data with slightly different column names, null handling, or rating scale calibration between the fallback (2024-25 archive) and the real 2025-26 data, no error is thrown — the model retrains on valid but different data.

**Consequences:** Subtle: the retrained model may have a slightly different Brier score but no obvious failure signal. The shift in efficiency metric distributions (e.g., 2025-26 had unusual parity or exceptional team clusters) could cause calibration to drift from the ClippedCalibrator [0.05, 0.89] bounds that were set on the v1.0 data distribution.

**Prevention:**
- Before retraining, diff the new `current_season_stats.parquet` against the proxy data on: column names, value ranges (mean/std for barthag, adj_o, adj_d), null count, row count.
- Run the backtest harness against 2022-2025 after retraining with the new data to confirm Brier score does not regress beyond 0.01 from v1.0 baseline (0.1692).
- If Brier degrades by more than 0.01, investigate the new data before deploying the retrained model.
- The ClippedCalibrator [0.05, 0.89] bounds were set empirically on the 2024-25 proxy distribution. Verify these bounds still make sense for the new data — if the 2025-26 season was unusually uncompetitive (all top teams dominant), optimal clip values may differ.

**Warning signs:**
- Retrain script runs without printing a data diff/validation summary
- Brier after retrain is not compared to pre-retrain Brier
- No test that checks for column schema consistency between proxy and real data

**Phase to address:** Model retraining phase. Must include a data validation gate before retraining triggers.

---

### Pitfall V1.1-C4: cbbdata 2025-26 Data Not Available by Tournament Tip-Off — No Fallback Plan

**What goes wrong:** The project plan assumes model retraining will happen once cbbdata indexes 2025-26 data. As of 2026-03-13, that data is confirmed unavailable. If it remains unavailable between now and 2026-03-19 (tournament start), the model retrain never happens, and the bracket is predicted using 2024-25 proxy data — without anyone verifying this is actually acceptable.

**Why it happens:** The fallback path exists in `fetch_torvik_ratings()` (archive fallback), but the decision of whether to deploy the proxy-data bracket has not been documented as a deliberate choice with known quality implications.

**Consequences:** Not necessarily a failure — the v1.0 model with 2024-25 proxy data already achieves Brier 0.1692. Using 2024-25 proxy data for 2026 predictions is a reasonable fallback if 2025-26 data is missing. The risk is going to the tournament without being explicit about which model is running, leading to confusion if results look unexpected.

**Prevention:**
- Formalize the decision tree: (a) if 2025-26 data available before Selection Sunday, retrain and deploy; (b) if not available by Selection Sunday, deploy v1.0 model explicitly labeled "2024-25 proxy data" with no further waiting.
- Set a hard cutoff: if data is not available by end of day 2026-03-15 (Selection Sunday), ship the v1.0 model. Do not delay bracket filling while waiting for data that may never arrive in time.
- Document in the UI sidebar whether the model was trained on proxy or real 2025-26 data.

**Warning signs:**
- No documented go/no-go decision point for data availability
- Bracket gets filled without knowing which season's data underpins the model

**Phase to address:** Data refresh planning (earliest phase); must be resolved before any other v1.1 work begins.

---

### Pitfall V1.1-C5: Bracket JSON Contract Breakage When Adding Pool Optimizer Output

**What goes wrong:** The pool optimizer generates a new bracket (the "contrarian bracket") and stores it in a new data structure. The UI is updated to show both the ML-predicted bracket and the pool-optimized bracket. But the existing bracket rendering pipeline (`bracket_schema.py`, `simulate_bracket()`, `bracket_svg.py`) uses a specific JSON contract for bracket slots. If the optimizer output uses a different slot naming convention or stores picks in a dict format that is not compatible with `render_bracket_svg_string()`, the UI silently shows wrong teams in wrong bracket positions.

**Why it happens:** Adding a new feature under time pressure often involves generating output in whatever format is convenient, then wiring it to the UI later. The slot addressing contract in the existing system uses slot IDs like `R1_W01`, `R2_W01` with parent-child relationships. Any optimizer output that uses a flat `{round: [team_list]}` representation will not be compatible.

**Consequences:** The pool optimizer bracket renders incorrectly, showing the wrong teams advancing or displaying bracket slots in the wrong order. This is a silent failure — no Python exception is raised, just incorrect display.

**Prevention:**
- The pool optimizer must output its bracket in the same slot-addressed JSON format that `simulate_bracket()` uses. The optimizer is not a separate bracket renderer — it produces a `picks_map` that replaces the deterministic picks output.
- Add a contract test: if the optimizer output can be passed directly to `render_bracket_svg_string()` and produce a valid bracket, the contract is satisfied.
- Review `src/simulator/bracket_schema.py` and `src/ui/bracket_svg.py` before building the optimizer to understand the exact slot contract.

**Warning signs:**
- Optimizer output is a flat list or round-keyed dict rather than slot-keyed dict
- No test that checks optimizer output is compatible with existing render functions

**Phase to address:** Pool optimizer implementation phase.

---

## Moderate Pitfalls (v1.1)

Mistakes that create technical debt, misleading outputs, or degraded UX but are recoverable.

---

### Pitfall V1.1-M1: Streamlit Cache Invalidation Bug When New Features Are Added

**What goes wrong:** The existing UI in `data_loader.py` uses `@st.cache_resource` and `@st.cache_data` extensively. Adding new cached functions (e.g., a cached `load_pool_optimizer()` or a cached `fetch_public_pick_percentages()`) with unhashable arguments requires the same `_underscore` naming convention that the existing code uses. If a new function takes a dict argument without the underscore prefix, Streamlit will attempt to hash the dict and either throw a hash error or produce incorrect cache keys.

**Why it happens:** The underscore-prefix convention for unhashable arguments in `@st.cache_data` is easy to forget when adding new functions, especially when copying an existing function signature and modifying it.

**Consequences:** Either the app raises an unhashable type error on startup, or cached data is not properly invalidated when inputs change (producing stale optimizer outputs when the override map changes).

**Prevention:**
- Follow the existing naming convention: any `dict`, `set`, `list`, or object argument to `@st.cache_data` functions must have an underscore prefix.
- When adding cached functions that depend on `override_map` (which changes with user picks), test that changing an override actually triggers a cache miss, not a cache hit.
- Read `src/ui/data_loader.py` before adding any new cached functions; the conventions are documented in the module docstring.

**Warning signs:**
- New cached function does not follow the underscore-prefix convention for dict arguments
- Changing override map doesn't update the pool optimizer output in the UI

**Phase to address:** UI integration phase for pool optimizer.

---

### Pitfall V1.1-M2: Pool Optimizer Ignores Scoring System — Wrong Strategy for Your Pool

**What goes wrong:** The optimizer is built for "generic large pool strategy" without configuring the scoring system of the actual pool being entered. Standard scoring is 1-2-4-8-16-32 (doubling each round). Some pools use 1-2-3-4-5-6 (upset bonus) or custom weightings. The contrarian strategy that maximizes expected value in a 1-2-4-8-16-32 pool — which heavily weights champion selection — is incorrect for a pool with an upset bonus that rewards early-round picks.

**Why it happens:** The specific pool's rules are not documented as a system input. The optimizer is built with one scoring model in mind.

**Consequences:** The optimizer recommends a contrarian champion when the pool weights early rounds nearly as much as the champion pick. This produces a suboptimal bracket entry.

**Prevention:**
- Make the scoring weights a first-class input to the optimizer: `optimize_bracket(scoring_weights=[1,2,4,8,16,32], pool_size=150)`.
- For the personal pool being entered, document the actual scoring system before building the optimizer.
- The standard ESPN/CBS scoring (1-2-4-8-16-32) is a reasonable default if the pool rules aren't known yet, but make it configurable.

**Warning signs:**
- Optimizer function signature has no scoring_weights or points_per_round parameter
- Optimizer documentation doesn't mention which scoring system it assumes

**Phase to address:** Pool optimizer design phase.

---

### Pitfall V1.1-M3: UI Enrichment Data Staleness — Stats Shown Don't Match What the Model Used

**What goes wrong:** The matchup context UI enrichment shows team stats (adjOE, adjDE, barthag, WAB, conference) alongside each game prediction. These are fetched from `current_season_stats.parquet` at display time. But the model was trained on features computed by `_compute_features_by_id()`, which uses the same data but computes differentials. If the current_season_stats data is the 2024-25 proxy (not 2025-26), the UI shows stats labeled as current-season that are actually last season's numbers.

**Why it happens:** Labeling in the UI ("2025-26 Season Stats") is written before it's confirmed whether the underlying data is proxy or real. The mismatch is a labeling problem, not a data pipeline problem.

**Consequences:** Misleading UI. Users (even just the one user) see "2025-26 stats" that are actually 2024-25 stats. Specific values like "Duke: adjOE 123.4" may be last year's number, which is wrong for 2026 bracket analysis.

**Prevention:**
- The UI should display the data vintage alongside stats: "Stats source: 2024-25 proxy (2025-26 not yet available)" vs. "Stats source: 2025-26 (cbbdata, indexed 2026-03-15)".
- This requires surfacing the `source_date` column from `current_season_stats.parquet` — already present in the archive fallback path (`cbbdata_client.py` sets `snapshot["source_date"]`).
- Add a `data_vintage` field to the UI sidebar alongside the existing model metadata.

**Warning signs:**
- UI shows season stats without displaying which season the data is from
- `source_date` column in `current_season_stats.parquet` is not surfaced anywhere in the UI

**Phase to address:** UI enrichment phase.

---

### Pitfall V1.1-M4: Adding UI Tabs Breaks Existing Streamlit Session State Keys

**What goes wrong:** Adding a new tab for pool optimizer or matchup context introduces new `st.session_state` keys for user interactions (e.g., selecting which game to view context for, toggling optimizer settings). If a new key name collides with an existing key (`season`, `override_map`), or if a new widget key matches an existing widget key, Streamlit raises a `DuplicateWidgetID` error at runtime.

**Why it happens:** The existing UI in `app.py` uses `tab_bracket`, `tab_advancement`, `tab_champion` with corresponding session state. Adding a fourth tab with interactive widgets requires unique key management.

**Consequences:** The app crashes with a `DuplicateWidgetID` error the first time a new widget is rendered, or session state for existing features is silently corrupted by a key name collision.

**Prevention:**
- Namespace new session state keys with a feature prefix: `pool_optimizer_*`, `matchup_context_*` rather than generic names.
- Audit the existing session state keys before adding any new widgets: `season`, `override_map` are the currently used keys.
- Test the app end-to-end after adding each new tab before proceeding to the next.

**Warning signs:**
- New widget keys are generic (`selected_team`, `show_stats`) rather than namespaced
- Session state is not audited before new feature development

**Phase to address:** UI integration phase (first test after adding any new tab).

---

### Pitfall V1.1-M5: Retraining Overwrites the Validated v1.0 Model Without Backup

**What goes wrong:** The retrain script writes a new `models/ensemble.joblib` and updates `models/selected.json`. If the retrained model unexpectedly underperforms (e.g., because 2025-26 data had schema issues, or the new data made the clipped calibrator inappropriate), the original validated model (Brier 0.1692) is overwritten and gone.

**Why it happens:** The retrain script was designed for initial training, not for incremental updates. There is no versioning or backup in the model artifact pipeline.

**Consequences:** If the retrained model has a problem discovered close to tip-off (2026-03-19), there is no way to revert to the known-good v1.0 model without re-running the full retrain pipeline from scratch, which may take significant time.

**Prevention:**
- Before retraining, copy `models/ensemble.joblib` to `models/ensemble_v1.0.joblib` (and `selected.json` to `selected_v1.0.json`).
- After retraining, run the backtest harness and compare Brier scores. Only update `selected.json` to point to the new model if Brier is equal to or better than 0.1692.
- If Brier degrades by more than 0.01, treat the retraining as failed and revert to v1.0.

**Warning signs:**
- No backup of model artifacts before retraining begins
- Retrain script doesn't compare new vs. old Brier before overwriting `selected.json`

**Phase to address:** Model retraining phase.

---

### Pitfall V1.1-M6: Contrarian Pick Logic Mistakes Pool Size Effect — Small Pool Needs Chalk

**What goes wrong:** The pool optimizer recommends a heavily contrarian bracket regardless of pool size. In a 10-person pool, contrarian picks reduce expected value — chalk wins in small pools because there are fewer entries to differentiate from, and being wrong on a contrarian pick costs more than the differentiation gained. The optimizer is tuned for 100+ person pools and the interface doesn't communicate that the strategy is wrong for smaller pools.

**Why it happens:** The optimizer is built for the personal use case (100+ person pool) and hardcodes pool-size-dependent logic without surfacing the dependency.

**Consequences:** If the tool is used for a different pool with fewer entrants, the contrarian recommendations actively hurt performance.

**Prevention:**
- Surface pool size as a required input, not an internal constant.
- Document the pool size threshold above which contrarian strategies improve expected value. Research consensus: contrarian picks generally improve expected value when pool size exceeds ~50 entries. Below 50, chalk is more often optimal.
- Add a warning in the UI if pool_size < 50: "In small pools, contrarian picks may reduce expected value. Consider the chalk bracket for pools under 50 entries."

**Warning signs:**
- Pool size is hardcoded or not exposed as a user input
- Optimizer documentation doesn't discuss pool size sensitivity

**Phase to address:** Pool optimizer design.

---

## Time-Pressure Pitfalls (Selection Sunday deadline)

Pitfalls specific to building under a 2-day deadline (2026-03-13 to 2026-03-15).

---

### Pitfall V1.1-T1: Building All Three Features in Parallel Creates an Untestable Integration

**What goes wrong:** Pool optimizer, UI enrichment, and model retraining are started simultaneously. Each component works independently but the integration is never tested before Selection Sunday. On Sunday night, wiring the three features together reveals that the optimizer output format is incompatible with the UI tab, or that the retrained model prediction function signature changed in a way that breaks the optimizer.

**Why it happens:** Time pressure encourages parallelizing work. Parallelizing three interdependent features is correct, but skipping integration tests until all three are "done" is the mistake.

**Consequences:** On Selection Sunday evening, when the bracket is available and all three features need to work simultaneously, integration failures surface for the first time. There is no time to fix them.

**Prevention:**
- Build in dependency order: model retraining first (if data available), then pool optimizer (depends on model output), then UI enrichment (no hard dependency on optimizer, can be parallel but should be integrated and tested independently).
- Each feature must have a smoke test that runs the feature end-to-end with the existing system before starting the next feature.
- Do not start UI enrichment until the pool optimizer output can be verified correct.

**Warning signs:**
- Three features are being built simultaneously with no integration checkpoints
- "Wire it all together at the end" is the integration plan

**Phase to address:** v1.1 planning; ordering of phases.

---

### Pitfall V1.1-T2: Bracket Fetch Pipeline Fails on Selection Sunday — No Rehearsal Run

**What goes wrong:** The bracket auto-fetch pipeline was built and tested in v1.0 but not run against real bracket data (the 2026 bracket did not exist at test time). On Selection Sunday, the ESPN API may return the 2026 bracket in a format that differs from what was tested. If the fetch fails or returns malformed data, there is no bracket to optimize or predict.

**Why it happens:** The ESPN bracket API is an undocumented unofficial endpoint. The v1.0 testing confirmed the endpoint was reachable and returned 0 teams (expected pre-announcement). Post-announcement behavior has not been confirmed against real 2026 data.

**Consequences:** Bracket is unavailable after Selection Sunday. The fallback (CSV) works, but requires manual entry of 68 teams and seeds, which takes time and introduces transcription errors.

**Prevention:**
- Have the manual CSV fallback (`data/seeds/bracket_manual.csv`) pre-populated with the projected bracket from bracketology sources (ESPN bracketology, CBS bracketology). If the auto-fetch fails, the CSV can be updated with actual seeds immediately after announcement.
- The bracketology CSV serves as both a fallback and a rehearsal test — confirm the existing pipeline loads it correctly before Selection Sunday.
- Check the ESPN endpoint format against the 2025 tournament bracket fetch records if available in the codebase.

**Warning signs:**
- No pre-populated bracket CSV prepared from bracketology projections
- Bracket fetch pipeline not run against any real data since v1.0 completion

**Phase to address:** First task in v1.1, before any feature work begins.

---

### Pitfall V1.1-T3: Model Retrain Takes Longer Than Expected and Blocks Bracket Filling

**What goes wrong:** On Selection Sunday, once the bracket is fetched, the model retrain (if 2025-26 data became available) is kicked off. Retraining the TwoTierEnsemble with 4-fold walk-forward validation across 22 seasons takes longer than anticipated — possibly 30-60 minutes depending on hyperparameter tuning settings. This delays the bracket prediction until after the user needs it.

**Why it happens:** Retrain timing was not measured during v1.0 development, or was measured but not budgeted into the Selection Sunday schedule.

**Consequences:** Bracket predictions are not available until after the user wanted to review them. In the worst case, the retrain is still running when it's time to submit bracket picks.

**Prevention:**
- Measure the current retrain time before Selection Sunday. Run `python -m src.models.ensemble` and time it.
- If retrain > 20 minutes, pre-warm: run the retrain as soon as 2025-26 data becomes available (even if that's Saturday night), before the bracket is announced.
- Model retrain and bracket fetch are independent; they can run in parallel. Retrain on the new data while manually reviewing bracketology projections. Once both are done, run predictions.
- Have a go/no-go time: if retrain is not complete 2 hours before bracket submission deadline, submit with the v1.0 model.

**Warning signs:**
- Retrain time not measured before Selection Sunday
- No plan for parallel retrain + bracket fetch
- No go/no-go time established

**Phase to address:** Model retraining planning.

---

### Pitfall V1.1-T4: Scope Creep on UI Enrichment Consumes Time Needed for Pool Optimizer

**What goes wrong:** UI enrichment (showing team stats, conference info, efficiency ratings alongside bracket games) is visually satisfying and generates many ideas: head-to-head records, historical seed matchup win rates, NET rankings, recent form charts. Each addition takes time. The pool optimizer — which requires math, architecture decisions, and data sourcing — gets compressed into the remaining hours before tip-off.

**Why it happens:** UI work produces immediate visible feedback. Algorithm work is harder and slower. Under time pressure, it's tempting to keep polishing the UI.

**Consequences:** Pool optimizer is either not built, or is built hastily in the last few hours without proper testing. The contrarian bracket is wrong or missing.

**Prevention:**
- Time-box UI enrichment explicitly: the minimum viable enrichment is showing the 6 existing FEATURE_COLS (adjoe_diff, adjde_diff, barthag_diff, seed_diff, adjt_diff, wab_diff) per game alongside win probability. This requires no new data fetching and minimal new code.
- Do not add new data sources (head-to-head, NET rankings, recent form) unless the pool optimizer is complete.
- Pool optimizer is higher priority than UI enrichment because it addresses the stated v1.1 goal of "large pool strategy."

**Warning signs:**
- UI enrichment has >3 features being built when pool optimizer is not yet started
- New data sources are being fetched for UI display before optimizer is working

**Phase to address:** v1.1 phase planning; explicit time allocation.

---

### Pitfall V1.1-T5: Not Having a Working Bracket Before Tournament Tips Off Is a Total Failure

**What goes wrong:** Feature development (pool optimizer, retraining, UI enrichment) runs long. On 2026-03-19 (Thursday, tournament starts), the app crashes or predicts incorrectly because a v1.1 feature is half-built. The v1.0 app — which worked — has been modified in ways that broke it.

**Why it happens:** Development against a working system under time pressure often involves making changes that are not fully tested before proceeding.

**Consequences:** The primary purpose of the project — having a working bracket predictor for the tournament — is not met.

**Prevention:**
- The v1.0 app is the baseline. Before starting any v1.1 feature, tag the current commit (`git tag v1.0-stable`) so it can be restored instantly.
- All v1.1 changes must leave the existing E2E flows working. After each new feature is added, run the app and verify: bracket renders, MC simulation runs, overrides work, champion is displayed.
- If any v1.1 feature breaks the existing app and cannot be fixed by the morning of 2026-03-19, revert to v1.0-stable.

**Warning signs:**
- v1.0 commit is not tagged before v1.1 work begins
- App is not run end-to-end after each significant change

**Phase to address:** Before any v1.1 development begins; first task.

---

## Part II: v1.0 Pitfalls (Preserved)

Original domain pitfalls from v1.0 research. Remain valid for any model retraining or new feature work that touches the core ML pipeline.

---

## Critical Pitfalls (v1.0)

### Pitfall 1: Data Leakage from Tournament Outcomes into Training Features

**What goes wrong:** Features computed using data that was not available at prediction time — specifically full-season statistics including post-Selection Sunday games, or raw seeds that encode committee bias.

**Prevention:** Enforce hard cutoff dates at conference tournament completion. Use efficiency-based metrics (Torvik) not raw seeds as primary features.

**Detection:** Training accuracy above ~78-80% is a red flag.

**Phase relevance for v1.1:** Applies to model retraining — verify cutoff dates are enforced when 2025-26 data is ingested.

---

### Pitfall 2: Treating Tournament Games as Independent Samples for Cross-Validation

**What goes wrong:** K-fold CV randomly mixes tournament years, creating temporal leakage. Model validates well but fails on held-out tournament years.

**Prevention:** Walk-forward temporal validation only. `walk_forward_splits()` already implements this in the codebase.

**Phase relevance for v1.1:** Retrain must use the same temporal split approach as v1.0.

---

### Pitfall 3: Models Default to "Chalk" — No Useful Variance

**What goes wrong:** Class imbalance (favorites win ~71%) causes models to predict favorites almost always. Looks accurate on aggregate but useless for capturing tournament outcomes.

**Prevention:** Brier score and log-loss as primary metrics. Monte Carlo calibration check: if <5% of 10K simulations include a 10+ seed in the Sweet 16, probabilities are miscalibrated.

**Phase relevance for v1.1:** Directly relevant to pool optimizer — the optimizer must work against the chalk bias, not reinforce it.

---

### Pitfall 4: Ignoring the Transfer Portal Era

**What goes wrong:** Year-over-year team identity features are unreliable since 2021. 53% of 2025 tournament rotation players previously played at another school.

**Prevention:** Season-bounded features only as primary inputs.

**Phase relevance for v1.1:** Applies to 2025-26 data ingest — the new season's teams may have significant roster changes versus 2024-25 proxy data.

---

### Pitfall 5: Backtesting Only on 2025 (Chalk Year)

**What goes wrong:** 2025 was all four #1 seeds in Final Four — historically unusual. A good 2025 backtest may be a chalk model.

**Prevention:** Multi-year backtest required: 2022-2025 covering different variance profiles.

**Phase relevance for v1.1:** After retraining, run the full multi-year backtest, not just 2025.

---

## Moderate Pitfalls (v1.0, selective)

### Pitfall 10: Bracket Filling Strategy Confusion — Win Probability vs. Expected Pool Score

**What goes wrong:** Bracket is filled by greedily picking the most probable winner. This is optimal for prediction accuracy but wrong for pool strategy.

**Prevention:** Separate win-probability computation from bracket optimization. This is the foundational point for the v1.1 pool optimizer.

**Phase relevance for v1.1:** The pool optimizer is the solution to this pitfall.

---

### Pitfall 11: Not Accounting for Injury and Roster Status

**What goes wrong:** Season-aggregate statistics don't reflect game-day player availability.

**Prevention:** Manual override mechanism before bracket submission. 2026 is the first year with official NCAA injury reports.

**Phase relevance for v1.1:** The manual override mechanism in the existing UI supports this. UI enrichment should surface where injury information might be most impactful (teams with known injury risk players).

---

## Phase-Specific Warnings (v1.1)

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|----------------|------------|
| Data refresh | cbbdata 2025-26 availability | Data not indexed — fallback to proxy | Formalize go/no-go decision by EOD 2026-03-14; deploy v1.0 model if unavailable |
| Model retraining | New season data ingest | Schema/distribution shift from proxy to real data | Diff new parquet against proxy before retraining; run backtest comparison |
| Model retraining | Artifact overwrite | Retrained model overwrites known-good v1.0 without comparison | Backup artifacts before retrain; compare Brier before updating selected.json |
| Pool optimizer | Algorithm design | Optimizing probability not expected pool score | Separate prediction and optimization code paths; ownership data required |
| Pool optimizer | Pick popularity data | No free API for actual public pick percentages | Use historically calibrated seed-based priors as baseline; scrape ESPN champion % after bracket announced |
| Pool optimizer | Pool size sensitivity | Contrarian logic inappropriate for small pools | Pool size as required input; warn if pool_size < 50 |
| Pool optimizer | Bracket JSON contract | Optimizer output incompatible with existing render functions | Output must use slot-addressed dict, not flat round list |
| UI enrichment | Data labeling | Stats shown labeled as current-season but may be proxy data | Surface source_date from parquet; show data vintage in sidebar |
| UI enrichment | Scope creep | UI polish consumes time for pool optimizer | Time-box enrichment to FEATURE_COLS display only; no new data sources until optimizer is complete |
| UI integration | Session state | New widget keys collide with existing keys | Namespace all new keys with feature prefix |
| UI integration | Cache invalidation | New cached functions break on unhashable dict args | Follow underscore-prefix convention from existing data_loader.py |
| Deployment | System stability | v1.1 changes break existing bracket pipeline | Tag v1.0-stable before any v1.1 work; test E2E after each feature addition |
| Deployment | Timeline | Feature development runs past tournament tip-off | If app broken on morning of 2026-03-19, revert to v1.0-stable |

---

## The Selection Sunday Constraint

**Hard deadline: 2026-03-15 (2 days away as of 2026-03-13)**

The tournament tips off 2026-03-19. Bracket challenge sites (ESPN, Yahoo) lock when the first game tips. The pool optimizer must produce a submitted bracket by then.

Prioritized build order given the constraint:

1. **Tag v1.0-stable** (30 minutes) — insurance policy; enables instant rollback
2. **Check cbbdata 2025-26 data availability** (15 minutes) — determines whether retraining is possible
3. **Prepare bracket_manual.csv from bracketology projections** (1 hour) — fallback for Selection Sunday bracket fetch
4. **Pool optimizer** (highest value; should be done before Selection Sunday so it can inform bracket picks)
5. **Model retraining** (if 2025-26 data available; run in parallel with optimizer development)
6. **UI enrichment** (lowest priority; FEATURE_COLS display is sufficient; no new data sources under time pressure)

If all three cannot be completed: ship pool optimizer and skip UI enrichment. The pool optimizer directly answers "which bracket do I submit to the pool." UI enrichment is nice-to-have.

---

## Sources

**v1.1 pitfalls:**
- [PoolGenius Bracket Strategy Guide](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/bracket-strategy-guide/) — champion pick value, contrarian methodology, pool size sensitivity (MEDIUM confidence)
- [PoolGenius FAQ](https://poolgenius.teamrankings.com/ncaa-bracket-picks/faq/) — common mistakes, optimizer failure modes, pick popularity data requirements (MEDIUM confidence)
- [FTN Fantasy: Advanced Bracket Strategies](https://ftnfantasy.com/cbb/advanced-bracket-strategies-how-to-win-any-size-tournament-pool) — backward-building, pool size thresholds (LOW confidence, access restricted)
- [Syracuse University Analytics Article](https://news.syr.edu/2026/03/11/how-to-win-your-march-madness-bracket-with-analytics-driven-strategies/) — current-year analytics-driven strategy confirmation (MEDIUM confidence)
- [Forecasting NCAA Basketball Outcomes with Deep Learning (arXiv 2508.02725)](https://arxiv.org/html/2508.02725v1) — temporal validation, small sample overfitting, retraining risks (MEDIUM confidence, peer-reviewed)
- [Streamlit session state best practices discussion](https://discuss.streamlit.io/t/seeking-advice-for-streamlit-app-state-management-and-best-practices/80025) — session state collision pitfalls (MEDIUM confidence)
- cbbdata_client.py inspection — confirmed archive fallback exists, source_date column documented, 2025-26 data unavailable as of 2026-03-13 (HIGH confidence, direct codebase inspection)
- v1.0-MILESTONE-AUDIT.md inspection — confirmed tech debt items, existing session state keys, slot contract details (HIGH confidence, direct codebase inspection)

**v1.0 pitfalls (original sources):**
- [adeshpande3: Applying ML to March Madness](https://adeshpande3.github.io/Applying-Machine-Learning-to-March-Madness) — chalk bias in gradient boosted models (MEDIUM confidence)
- [arXiv 2508.02725v1](https://arxiv.org/html/2508.02725v1) — temporal leakage, calibration (MEDIUM confidence, peer-reviewed)
- [PoolGenius: Historical Trends](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/madness-myths-your-bracket-should-match-historical-trends/) — seed distribution unreliability (MEDIUM confidence)
- [NCAA Transfer Portal Impact — CNBC](https://www.cnbc.com/2025/04/04/why-ncaa-transfer-portal-is-affecting-march-madness-.html) — 53% of 2025 rotation players from portal (HIGH confidence)
- [NCAA 2026 injury reports — Bleacher Report](https://bleacherreport.com/articles/25273019-ncaa-announces-march-madness-2026-will-feature-team-injury-reports-after-rule-change) — official injury reports for 2026 (HIGH confidence)
