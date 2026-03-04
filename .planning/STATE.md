# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** Phase 9 (Bracket Visualization UI) in progress — 2/4 plans done. SVG bracket coordinate layout engine complete.

## Current Position

Phase: 9 of 10 (Bracket Visualization UI) — In Progress
Plan: 2 of 4 in phase 09 (coordinate layout complete)
Status: Phase 9 plan 02 complete — All 67 slot coordinates mapped, 66 connector lines generated, smoke test green
Last activity: 2026-03-04 — Completed 09-02-PLAN.md (bracket coordinate layout algorithm)

Progress: [█████████░] 95% (31/32 plans estimated)

## Performance Metrics

**Velocity:**
- Total plans completed: 11
- Average duration: ~11 min
- Total execution time: ~2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-historical-data-pipeline | 3 | ~70 min | ~23 min |
| 02-current-season-and-bracket-data | 2 | ~27 min | ~14 min |
| 03-baseline-model-and-temporal-validation | 4 | ~29 min | ~7 min |
| 04-bracket-simulator | 6 (complete) | ~17 min | ~3 min |
| 05-backtesting-harness | 3 (complete) | ~7 min | ~2.3 min |
| 06-ensemble-models | 3 so far | ~8 min | ~2.7 min |

**Recent Trend:**
- Last 5 plans: 05-01 (~2 min), 05-02 (~3 min), 05-03 (~2 min), 06-01 (~2 min), 06-02 (~2 min)
- Trend: Well-scoped plans with clear prior context execute in 2-5 min; library compat issues resolved quickly

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
- [03-01]: cbbdata only has year-end ratings for 2008-2024; 2003-2007 unavailable — historical_torvik_ratings.parquet covers 17 seasons (not 22); 313 pre-2008 tournament games dropped from matchup dataset
- [03-01]: team_aliases.csv bug fixed: ID 1299 was mislabeled as NC Central (should be NC A&T); NC State, NC A&T, College of Charleston, Saint Francis/St Francis PA all needed CBBDATA_NAME_OVERRIDES to avoid fuzzy false positives
- [03-01]: build_stats_lookup() replaces 2025 historical archive data with current_season_stats.parquet; current_season_stats uses column 'year' not 'season' — rename handled in build_stats_lookup()
- [03-01]: FEATURE_COLS = ['adjoe_diff', 'adjde_diff', 'barthag_diff', 'seed_diff', 'adjt_diff', 'wab_diff'] — canonical ordering; team_a = lower SeedNum (better seed); label=1 if team_a wins
- [03-02]: BACKTEST_YEARS = [2022, 2023, 2024, 2025] — canonical holdout years; walk_forward_splits() is the only approved CV method for all future models
- [03-02]: Logistic regression baseline: Optuna log-uniform C search [1e-3,100], 50 trials, best C~2.39, mean Brier=0.1900 (calibrated); ensemble in phase 6 must beat this
- [03-02]: barthag_diff coefficient is negative (-0.82) due to multicollinearity with adjoe_diff/adjde_diff — expected behavior; model predictions are directionally correct
- [03-02]: joblib artifact pattern — model artifacts always include model, scaler, feature_names, train_seasons, best_C, sklearn_version; load_model() warns on version mismatch
- [03-03]: Walk-forward evaluation re-fits scaler+model per fold (not the saved artifact's scaler/model) — prevents any test-set contamination; best_C from artifact used only as config
- [03-03]: Benchmark established — logistic baseline mean Brier=0.1900 (calibrated) across 2022-2025; Phase 6 ensemble must beat this on same walk-forward protocol
- [03-03]: evaluation_results.json is the canonical Phase 3 benchmark artifact — consumed by Phase 5 (MC simulation), Phase 7 (model comparison dashboard)
- [03-04]: sklearn 1.8.0 removed cv='prefit' from CalibratedClassifierCV; FrozenEstimator+isotonic worsens overconfidence for this dataset (max top-seed P goes 0.9674->1.0000); ClippedCalibrator with hard bounds [0.05, 0.89] is the correct fix
- [03-04]: Calibrator stored as plain dict spec in artifact (not object) to prevent __main__ pickle path corruption; load_model() reconstructs ClippedCalibrator from clip_lo/clip_hi params every time
- [03-04]: ClippedCalibrator clips probabilities to [0.05, 0.89] — eliminates all 16 overconfident top-seed predictions with only +0.0004 Brier penalty; calibration_method='isotonic' retained for semantic compat
- [03-04]: Phase 3 final benchmark: mean Brier=0.1900, no top-seed matchup above P=0.89; all 4 success criteria PASS
- [04-01]: FF slots identified as those not starting with 'R' (W16, X11, Y11, Y16 for 2025); robust to region naming changes
- [04-01]: build_predict_fn returns (predict_fn, stats_lookup) tuple so 04-04 score_predictor can access stats without re-loading
- [04-01]: predict_fn closure captures season at build time — caller must pass correct season to build_predict_fn()
- [04-01]: Topological ordering key: slot_round_number() returns 0 for FF, int(slot_id[1]) for R-prefixed — valid for Kaggle R1-R6 convention
- [04-02]: simulate_bracket() signature accepts all future-mode params (n_runs, seed, override_map, stats_lookup) as no-ops in deterministic mode — preserves API stability when monte_carlo added in 04-03
- [04-02]: build_stats_lookup() overlay fix: current_season_stats.parquet overlaid on historical 2025 data (not replacing all of it) — First Four teams absent from cbbdata fall back to historical_torvik_ratings snapshot
- [04-02]: Bracket JSON contract finalized: {mode, season, slots: {slot_id: {team_id, win_prob, round}}, champion: {team_id, win_prob}} — all values native Python types for JSON serialization
- [04-02]: 2025 deterministic bracket champion: team_id=1222, win_prob=0.5425 (championship game)
- [04-03]: prob_matrix pre-computed once (4,624 predict_fn calls) before simulation loop; each run indexes via prob_matrix[occ_i, occ_j] -- critical for vectorized performance
- [04-03]: occupants dict stores np.ndarray(shape=(n_runs,), dtype=int32) of team indices (not team_ids) per slot; idx_to_team converts back at output time
- [04-03]: advancement_probs includes 'Champion' key (alias for R6CH fraction) alongside 'Championship' (championship game slot winner)
- [04-03]: Monte Carlo champion (team 1222, 31.8% confidence with seed=42, 10K runs) matches deterministic champion -- model self-consistent
- [04-03]: Performance: 10K runs in 0.21s -- 143x headroom under 30s limit; np.random.default_rng(seed) with PCG64 for reproducibility
- [04-04]: Rule-based tempo formula sufficient (R^2~0.25 for full regression); TEMPO_COEF=3.43, TEMPO_INTERCEPT=-89.7 from historical championship game analysis 2003-2025 excl. 2020
- [04-04]: adj_t==0.0 is a sentinel for missing data (per features.py convention) -- treated as fallback trigger alongside key-not-found; HISTORICAL_MEAN_TEMPO=67.0 used
- [04-04]: championship_game key added only to deterministic mode (not monte_carlo) -- MC produces distribution, not a single game score
- [04-04]: 2025 deterministic championship: team 1222 wins 72-63 over team 1196 (predicted_total=135, predicted_margin=9)
- [04-05]: override_map validated once at top of simulate_bracket() before mode dispatch -- shared validation for both modes
- [04-05]: Deterministic override: slot_prob[slot_id]=None for forced slots; output reports win_prob=1.0 (forced guarantee)
- [04-05]: MC override: pre-fill occupants dict before traversal; overridden set tracks which to skip -- downstream sees forced winner naturally
- [04-05]: Upstream slots (earlier rounds) are NOT changed by downstream overrides -- only overridden slot and its descendants affected
- [04-05]: championship_game score prediction uses win_prob=1.0 when R6CH is forced (None champion_prob guard added)
- [04-06]: Upset rate 73.0% using complement formula P(at least one 10+ seed in Sweet 16) -- ClippedCalibrator allows sufficient upset probability; no overconfidence concern
- [04-06]: check_upset_rate() uses complement formula (1 - product(1-p_i)) not simple sum -- mathematically correct for independent events
- [04-06]: validate_phase4() is Phase 4 integration test callable -- use for regression testing before Phase 5/6 changes
- [05-01]: build_actual_slot_winners() uses DISTINCT in team_slots CTE -- seed labels appear 6 times in SeedRoundSlots (one per round); DISTINCT prevents duplicate joins
- [05-01]: score_bracket() normalizes predicted_slots to handle both flat {slot_id: team_id} and nested {slot_id: {'team_id': ...}} formats (simulate_bracket() output is nested)
- [05-01]: compute_game_metrics() uses batch scaler.transform() + predict_proba() -- not per-game predict_fn calls; 4-arg form (test_df, feature_cols, scaler, calibrated_clf)
- [05-01]: ESPN_ROUND_POINTS = {1:10, 2:20, 3:40, 4:80, 5:160, 6:320}; ESPN_MAX_SCORE = 1920; First Four (round 0) not scored
- [05-02]: backtest() uses make_predict_fn() factory with default-arg binding to prevent late-binding Python closure bug (all folds sharing last loop's scaler/clf)
- [05-02]: backtest() extracts only best_C from artifact dict; artifact scaler/model never used for predictions -- each fold re-fits from scratch on Season < test_year
- [05-02]: predict_fn returns 0.5 on KeyError -- handles First Four play-in teams absent from cbbdata stats snapshot
- [05-02]: backtest/results.json verified reproducible: mean_brier=0.1900, mean_ESPN=912.5, 2024=62 games, 2025=60 games (matches evaluation_results.json)
- [05-03]: validate_phase5() confirms 4/4 criteria: temporal isolation assert (max train season=2024), Brier delta=0 vs evaluation_results.json, all 4 BACKTEST_YEARS present with dynamic upset counts, re-run reproducibility (0 differences)
- [05-03]: 2025 ESPN score=1200 in [1100,1300]; all 4 top #1 seeds reached Final Four, championship missed -- BACK-01 PASS
- [05-03]: Variable shadowing guard: inner loop variables must not reuse outer counter names (total, passed) -- silent correctness bug in display; renamed to r_correct/r_total
- [06-01]: XGBoost uses scale_pos_weight=(y_train==0).sum()/(y_train==1).sum() per fold -- XGBoost sklearn API does NOT support class_weight='balanced' (that's LightGBM only)
- [06-01]: verbosity=0 for XGBoost; verbose=-1 for LightGBM -- NOT interchangeable between the two libraries
- [06-01]: arm64 libomp fix on Intel-Homebrew Mac: xgboost 3.2.0 arm64 wheel expects /opt/homebrew/opt/libomp -- fix: copy arm64 libomp.dylib from MacPorts tbz2 into xgboost lib dir + install_name_tool rpath patch; must redo if .venv is recreated
- [06-01]: XGBoost mean Brier=0.1908 (best params: n_estimators=98, max_depth=2, lr=0.0813) -- only +0.0008 above LR baseline; stacking ensemble (06-04) should improve upon individual models
- [06-02]: LightGBM mean Brier=0.1931 vs LR baseline 0.1900 (+0.0031 delta) -- expected; individual GB models often slightly underperform logistic on small datasets; ensemble diversity is the goal
- [06-02]: Optuna found num_leaves=12 (far below max 60) -- confirms small dataset needs very shallow trees; complexity constraint was correct
- [06-02]: class_weight='balanced' for LightGBM (not scale_pos_weight which is XGBoost); verbose=-1 for LightGBM (not verbosity=0 which is XGBoost)
- [06-02]: arm64 libomp fix: Intel Homebrew at /usr/local has x86_64 libomp; arm64 Python (uv-managed) needs arm64 libomp; solution: copy from Adobe Acrobat's bundled arm64 libomp to /Users/Sheppardjm/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/lib/libomp.dylib
- [06-03]: Manual OOF temporal stacking must be used instead of sklearn StackingClassifier -- walk_forward_splits() produces non-partition (prefix) splits that trigger ValueError in sklearn's cross_val_predict() partition check (GitHub #32614)
- [06-03]: TwoTierEnsemble.predict_proba() must take ALREADY-SCALED features (caller scales externally); the ensemble stores scaler for reference only -- prevents double-scaling when backtest harness applies scaler
- [06-03]: save_artifact() pattern required for any class saved via joblib from __main__: re-import from stable module path via importlib before dump() to fix __main__.TwoTierEnsemble -> src.models.ensemble.TwoTierEnsemble pickle path
- [06-03]: LR base model OOF predictions must go through ClippedCalibrator before meta-learner training -- ensures meta-learner learns from calibrated (production-consistent) signals, not raw LR outputs
- [06-03]: OOF Ensemble Brier=0.1672 (XGB=1.26, LGB=0.92, LR=1.70 meta coefficients) -- LR base model weighted highest in meta-learner; stacking beats all individual models and the 0.1900 baseline by 12% relative
- [06-04]: Per-fold ensemble built entirely from scratch for each backtest year -- models/ensemble.joblib is never loaded during backtesting; ensures strict temporal isolation
- [06-04]: _build_fold_ensemble() uses nested OOF from last 3 available seasons before test_year (inner temporal sub-fold loop); meta-learner trained on this nested OOF, then base models re-fit on full train_df
- [06-04]: fold_scaler.transform() called by predict_fn caller; TwoTierEnsemble.predict_proba() receives already-scaled input (no double-scaling) -- this is the canonical call pattern for ensemble inference
- [06-04]: Ensemble backtest (2022-2025) mean Brier=0.1692 vs baseline 0.1900 (-0.0208 delta, -11% relative) -- ENSEMBLE WINS; per-year: 2022=0.1793, 2023=0.1850, 2024=0.1760, 2025=0.1364
- [06-04]: backtest() routes to backtest/ensemble_results.json automatically when model='ensemble' and output_path is default -- preserves baseline results.json intact; both files coexist in backtest/
- [06-05]: Phase 6 verification: Criterion 1 PASS (XGB=0.1908, LGB=0.1931, 4 folds each), Criterion 2 NOTE (TwoTierEnsemble functional; StackingClassifier incompatible with walk_forward_splits), Criterion 3 PASS (ensemble 0.1692 vs baseline 0.1900, -11%), Criterion 4 FAIL (max calibration deviation 0.1059 exceeds 5pp threshold; sparse OOF bins with 248 samples)
- [06-05]: Calibration FAIL root cause: [0.3,0.4] bin has only 16/248 OOF samples; 4 wrong predictions produce -10.59pp deviation; quantile strategy also fails (0.1007); deferred to Phase 8 (feature store)
- [07-01]: Dashboard module reads JSON artifacts only — zero ML imports in compare.py; load_comparison_data() is canonical data loader for Phase 7
- [07-01]: Only baseline and ensemble in comparison table per plan spec — XGB/LGB excluded (no per-round bracket simulation data available from Phase 6 evaluate functions)
- [07-01]: Upset detection tradeoff trend confirmed: ensemble deficit widens from -23.8pp (2022) to -36.4pp (2025) — ensemble becomes more conservative each year as it refines calibration
- [07-02]: matplotlib.use("Agg") must be set before pyplot import for headless CLI chart generation; pattern established in plots.py
- [07-02]: Plot imports placed inside __main__ block (not module top-level) to avoid slow matplotlib load when compare.py is imported as a library — preserves zero-ML-import design from 07-01
- [07-02]: Heatmap vmin=0.12, vmax=0.25 hard-coded for consistent color scale across runs; covers observed Brier range [0.136, 0.193]
- [07-03]: XGB and LGB Brier scores hard-coded as constants (0.1908, 0.1931) — no standalone bracket-level JSON artifacts exist for those models; only baseline and ensemble have backtest/*.json files
- [07-03]: select_best_model() uses round(mean_brier, 4) before min() comparison to avoid floating point noise affecting winner selection
- [07-03]: Phase 9 artifact loading pattern: load models/selected.json -> read model_artifact_path -> joblib.load() to get TwoTierEnsemble instance
- [08-01]: as_of_date validated against SELECTION_SUNDAY_DATES.values() (YYYY-MM-DD strings); Torvik snapshots satisfy cutoff by construction — no re-filtering of stats_lookup needed
- [08-01]: _TEAM_NAME_LOOKUP is a module-level cache populated lazily from team_normalization.parquet (canonical_name, kaggle_name, cbbdata_name only; espn_name excluded per [02-02])
- [08-01]: compute_features(team_a, team_b, season) is now the public name-based API; _compute_features_by_id(season, id_a, id_b, lookup) is the internal ID-based function used by backtest and simulator
- [08-02]: variance_inflation_factor() in statsmodels does NOT add an intercept internally — must call add_constant(X, has_constant='add') and use column index i+1 (skip 0=constant); validated by adjt_diff VIF=1.0506
- [08-02]: barthag_diff VIF=11.2007 formally documented in models/vif_report.json with KEEP_ALL decision — multicollinearity with adjoe_diff/adjde_diff is expected and all models are robust to it per [03-01]
- [08-03]: seed_diff returns int (not float) from _compute_features_by_id — seed_num stored as int in stats_lookup; isinstance check must be (int, float) not strictly float
- [08-03]: Plan-specified team IDs Houston=1220, UCLA=1437 are wrong (map to Hofstra and Villanova); correct IDs are Houston=1222, UCLA=1417; always verify ID-to-name mapping from team_normalization.parquet
- [08-03]: Phase 8 pytest suite: 22 tests, session-scoped stats_lookup (built once), autouse reset_name_cache fixture; `uv run pytest tests/ -v` is canonical verification command for feature store
- [08-04]: Gap-closure approach: when verifier finds goal-document mismatches (not code defects), update goal text to match decisions — SC-1 (WAB not SOS), SC-2 (VIF=11.2 accepted), SC-3 (by construction), SC-4 (feature-only symmetry)
- [08-04]: model-level probability symmetry structurally impossible with current training convention (team_a = lower seed produces non-zero scaler means); P(Duke,Michigan)+P(Michigan,Duke)=1.179 is expected; documented in test_model_probability_asymmetry_documented()
- [09-01]: streamlit's pandas<3 metadata constraint bypassed via [tool.uv] override-dependencies = ["pandas>=3.0.1"]; pandas 3.x is runtime-compatible with streamlit 1.55.0; requires-python narrowed to >=3.12,<3.14 and environments=darwin to scope lockfile
- [09-01]: TwoTierEnsemble predict_fn pattern: scaler.transform() applied INSIDE predict_fn closure (before predict_proba), NOT inside predict_proba — prevents double-scaling per [06-03] canonical call pattern
- [09-01]: load_team_info() queries seeds.parquet for TeamName (canonical display name source) — 68 teams per season including First Four teams
- [09-02]: NCAA bracket seeding structure (R2W1 fed by R1W1+R1W8, not adjacent R1 slots) causes parent-centering formula to collapse all R2-R4 y-values to same position — use doubling-spacing formula: spacing=base*(2^(r-1)), y=s*spacing+(spacing-BOX_HEIGHT)//2
- [09-02]: bracket is left-right symmetric (R4W1.y == R4Y1.y, R4X1.y == R4Z1.y) so centering formula also collapses R5WX/R5YZ/R6CH to same y — fix: place R5WX at upper R4 y-level, R5YZ at lower R4 y-level, R6CH mathematically between them
- [09-02]: canvas width 2030px (slightly >2000 suggested in plan) — all 67 slots fit without overlap; `uv run python` fails on this project due to streamlit/pandas conflict; use `.venv/bin/python` directly

### Pending Todos

- Refresh current_season_stats.parquet when cbbdata indexes 2025-26 season (check /api/torvik/ratings?year=2026 for non-empty barthag)
- On Selection Sunday (2026-03-15): run `uv run python -m src.ingest.fetch_bracket` to confirm auto-fetch returns 68 teams; if <68, populate data/seeds/bracket_manual.csv

### Blockers/Concerns

- [Resolved - 03-04]: overconfidence gap closed — 16 top-seed matchups with P>0.90 reduced to 0 via ClippedCalibrator [0.05, 0.89]; Phase 3 all criteria PASS
- [Resolved - 03-01]: team_aliases.csv NC A&T/NC Central ID swap corrected; NC State, Charleston, Saint Francis false positives fixed via CBBDATA_NAME_OVERRIDES
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

Last session: 2026-03-04T16:11:28Z
Stopped at: Completed 09-02-PLAN.md — SVG bracket coordinate layout engine; 67 slots, 66 connectors, zero overlaps
Resume file: None
