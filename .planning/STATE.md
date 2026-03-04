# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — model must produce better-than-seed-based predictions validated against historical tournament results.
**Current focus:** Phase 4 IN PROGRESS — bracket simulation infrastructure; 04-02 complete (simulate_bracket deterministic mode)

## Current Position

Phase: 4 of 10 (Bracket Simulator) — In progress
Plan: 2 of 6 in phase 04
Status: 04-02 complete — simulate_bracket() with deterministic mode, all 67 slots filled
Last activity: 2026-03-04 — Completed 04-02-PLAN.md (simulate_bracket deterministic mode)

Progress: [█████░░░░░] 40% (12/30 plans estimated)

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: ~12 min
- Total execution time: ~2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-historical-data-pipeline | 3 | ~70 min | ~23 min |
| 02-current-season-and-bracket-data | 2 | ~27 min | ~14 min |
| 03-baseline-model-and-temporal-validation | 4 | ~29 min | ~7 min |
| 04-bracket-simulator | 2 (in progress) | ~5 min | ~3 min |

**Recent Trend:**
- Last 5 plans: 03-02 (~3 min), 03-03 (~6 min), 03-04 (~12 min), 04-01 (~2 min), 04-02 (~3 min)
- Trend: Well-scoped plans with clear prior context execute in 5-15 min; API/library compat issues add 5-10 min

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

Last session: 2026-03-04T03:30:00Z
Stopped at: Completed 04-02-PLAN.md — simulate_bracket() deterministic mode
Resume file: None
