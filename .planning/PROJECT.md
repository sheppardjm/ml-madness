# March Madness 2026 Bracket Predictor

## What This Is

An interactive Streamlit web application that uses a stacking ensemble (XGBoost + LightGBM + logistic regression meta-learner) to predict every game in the 2026 NCAA Men's Basketball Tournament. Given the 68-team bracket, it produces win probabilities for each matchup across all rounds, simulates 10,000 Monte Carlo bracket outcomes, and predicts a champion with confidence percentage. The bracket is interactive — users can override individual picks and see how changes ripple through downstream rounds via real-time cascade recalculation.

## Core Value

Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — the model must produce better-than-seed-based predictions validated against historical tournament results.

## Requirements

### Validated

- ML ensemble trained on historical NCAA tournament data from public APIs/datasets — v1.0 (TwoTierEnsemble, Brier=0.1692)
- Auto-fetch of the 68-team bracket when announced on Selection Sunday — v1.0 (ESPN API + CSV fallback)
- Win probability predictions for every game in every round — v1.0 (67 slots filled)
- Champion prediction with confidence percentage and predicted championship game score — v1.0 (MC confidence; score in simulator, not UI)
- Interactive web bracket visualization — override picks and see downstream effects — v1.0 (Streamlit SVG + session persistence)
- Backtesting against the 2025 tournament using in-repo data and public sources — v1.0 (temporal isolation verified)
- Multiple model architectures compared (ensemble/experiment approach — pick the best performer) — v1.0 (LR vs XGB vs LGB vs ensemble)
- Historical team stats ingestion from public sources (KenPom-style efficiency, seed history, strength of schedule, etc.) — v1.0 (cbbdata Torvik ratings, 22 seasons)

### Active

#### Current Milestone: v1.1 Selection Sunday + Pool Strategy

**Goal:** Refresh model with real 2025-26 data, fetch live bracket, add pool-strategy optimizer for large pools, and enrich the UI with matchup context — all before tournament tips off.

**Target features:**
- Refresh current_season_stats with real 2025-26 Torvik data and retrain ensemble
- Fetch live 68-team bracket on Selection Sunday and generate predictions
- Pool strategy optimizer with contrarian pick analysis for large (100+) pools
- Richer matchup context in UI — team stats, historical performance, head-to-head analysis

### Out of Scope

- Score predictions for every game — only win probabilities (championship game is the exception)
- Multi-user support — this is a personal tool
- Mobile app — web-only; Streamlit handles responsive adequately
- Real-time game tracking or live updates during the tournament
- Explainability/feature importance — deferred to potential v2

## Context

- v1.0 MVP shipped 2026-03-10 with ~12,400 lines of Python across 167 files
- Tech stack: Python 3.12, uv, Streamlit, DuckDB, Parquet, XGBoost, LightGBM, scikit-learn, numpy, Optuna
- Selection Sunday is 2026-03-15 — bracket fetch pipeline ready, needs live data
- current_season_stats.parquet has 2024-25 data as proxy — cbbdata has NOT indexed 2025-26 as of 2026-03-13
- Ensemble Brier=0.1692 (11% better than logistic baseline 0.1900) on 2022-2025 holdout
- 5 tech debt items documented in milestone audit (none critical)
- Key 2026 contenders per rankings: Duke (#1), Michigan (#2), Arizona (#3), UConn (#4), Florida (#5)
- Entering at least one large bracket pool (100+ entrants) — need contrarian strategy, not just chalk picks

## Constraints

- **Data**: Public APIs/datasets only — no paid subscriptions (cbbdata/Bart Torvik as KenPom alternative)
- **Timeline**: Pool strategy and UI enhancements needed before tournament tips off (2026-03-19); data refresh + bracket fetch on Selection Sunday (2026-03-15)
- **Audience**: Single user (personal tool) — no auth, no deployment complexity needed
- **Tech stack**: Python 3.12, uv, Streamlit, DuckDB/Parquet, scikit-learn, XGBoost, LightGBM

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| TwoTierEnsemble (manual OOF stacking) | sklearn StackingClassifier incompatible with walk-forward splits | Good — Brier 0.1692, -11% vs baseline |
| ClippedCalibrator [0.05, 0.89] | Isotonic calibration worsened overconfidence; hard bounds eliminate it | Good — 0 overconfident predictions, +0.0004 Brier penalty |
| cbbdata over KenPom | Free API with equivalent Torvik efficiency metrics | Good — full pipeline works without paid subscriptions |
| DuckDB + Parquet storage | Fast analytical queries without database server | Good — subsecond queries on 22 seasons |
| Win probabilities over score predictions | Probabilities more useful for bracket decisions | Good — championship score exists but per-game scores out of scope |
| Backtest 2022-2025 first | Validates model quality with diverse tournament profiles | Good — chalk (2025) + upset-heavy (2022-2024) covered |
| Interactive bracket with overrides | "What if" scenarios add personal value beyond read-only bracket | Good — cascade recalculation works in real-time |
| Auto-fetch bracket from ESPN | Eliminates manual data entry on Selection Sunday | Good — pipeline ready, CSV fallback tested |

---
*Last updated: 2026-03-13 after v1.1 milestone start*
