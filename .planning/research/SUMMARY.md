# Project Research Summary

**Project:** madness2026
**Domain:** ML-powered NCAA Men's Basketball Tournament Bracket Predictor (personal use)
**Researched:** 2026-03-02
**Confidence:** HIGH (stack versions verified at PyPI; architecture patterns verified against open-source projects and academic papers; feature set verified against multiple published tools)

---

## Executive Summary

This is a Python-first ML pipeline with a Streamlit front end. The domain is well-understood: dozens of academic papers, Kaggle competitions, and open-source projects have tackled NCAA bracket prediction since 2003. The research consensus is clear — adjusted efficiency metrics (offensive and defensive, KenPom-style) are the strongest predictors, gradient boosted trees (XGBoost, LightGBM) perform best on tabular sports data, and stacking ensembles outperform single-model approaches. The practical accuracy ceiling for this problem is approximately 74–76% per-game accuracy, which is an empirical property of the domain, not a solvable engineering problem. The goal is a well-calibrated model that produces reliable win probabilities across both chalk years (2025) and high-chaos years (2022, 2023).

The recommended approach is a five-layer pipeline: data ingestion (CBBpy + cbbdata API + Kaggle historical dataset), feature engineering (efficiency differentials, tempo, strength of schedule, recent form), a stacking ensemble trained with temporal cross-validation, a Monte Carlo bracket simulator, and a Streamlit UI with programmatic SVG bracket rendering. The data storage split — DuckDB for analytical queries against Parquet files, SQLite for bracket state and run metadata — is the right choice for a single-user local project with 20 years of historical data. The entire stack stays in Python, which matters because the ML ecosystem has no viable alternative runtime.

The most dangerous risks are all correctness risks, not complexity risks: data leakage (using future information in features), temporal CV violations (treating tournament years as exchangeable), miscalibrated probabilities (a model that assigns 90% confidence to 65% outcomes), and over-reliance on 2025 for backtesting (a historically chalk year that flatters chalk-biased models). Every one of these is preventable with deliberate design choices enforced in Phase 1–3. There is one hard external dependency: the bracket releases on Selection Sunday 2026, and the auto-fetch pipeline must be ready before that date. Manual CSV fallback is required.

---

## Key Findings

### Recommended Stack

The entire stack is Python 3.12, with no JavaScript except optionally embedded via `st.components.v1.html()` for the bracket SVG. All library versions are verified at PyPI as of 2026-03-02. The data acquisition layer uses CBBpy 2.1.2 (ESPN-backed, actively maintained) for current-season data and the Kaggle March Machine Learning Mania dataset for historical backfill — this combination avoids building a custom scraper from scratch. The cbbdata API (barttorvik-backed, free key) provides KenPom-equivalent adjusted efficiency metrics without a paid subscription. Direct barttorvik.com scraping is explicitly blocked by Cloudflare and should not be attempted.

For ML, XGBoost 3.2.0 and LightGBM 4.6.0 are the primary models, confirmed against multiple Kaggle winning solutions. scikit-learn 1.8.0 handles the stacking ensemble, logistic regression baseline, and cross-validation. DuckDB 1.4.4 + Parquet handles analytical queries; SQLite handles bracket state. Streamlit 1.54.0 is the right UI choice for personal use — it eliminates a React+FastAPI build, keeps everything in Python, and ships fast ahead of Selection Sunday. The one trade-off is bracket visualization: Streamlit has no native bracket component, so programmatic SVG via `st.components.v1.html()` is required.

**Core technologies:**
- Python 3.12: runtime — minimum version required by pandas 3.0.1 (>=3.11) and scikit-learn 1.8.0 (>=3.11)
- CBBpy 2.1.2: current-season data acquisition — pure-Python, ESPN-backed, actively maintained Jan 2025
- cbbdata API: adjusted efficiency metrics (Torvik/barttorvik) — free key, REST API, KenPom equivalent without subscription
- Kaggle March Machine Learning Mania: historical backfill (2003-2025) — structured CSVs, avoids custom scraper
- pandas 3.0.1 + DuckDB 1.4.4: data manipulation and analytical storage — DuckDB queries Parquet 17x faster than pandas in-memory
- SQLite: bracket state, picks, simulation run logs — OLTP complement to DuckDB's OLAP
- XGBoost 3.2.0 + LightGBM 4.6.0: primary gradient boosted models — confirmed most-used in Kaggle March Mania winning entries
- scikit-learn 1.8.0: stacking ensemble, logistic regression baseline, StratifiedKFold — full ML pipeline support
- optuna: hyperparameter tuning — Bayesian optimization, preferred over GridSearchCV for this domain
- Streamlit 1.54.0: full web UI — single-process Python, no separate frontend build, ships fast
- Plotly: win probability charts — native Streamlit integration
- uv: package manager — faster than pip, modern Python standard as of 2025

### Expected Features

All four research files converge on the same feature dependency chain: data pipeline must come before feature engineering, which must come before modeling, which must come before simulation, which must come before the UI. This is not flexible — building in a different order creates rework.

**Must have (table stakes):**
- Win probability for all 63 (+ 4 First Four) tournament games — minimum viable output
- Round-by-round advancement probabilities for all 68 teams — every credible tool produces this
- Champion probability with confidence % — the headline output
- Full 68-team bracket display including First Four play-in games — missing this breaks the bracket
- Adjusted efficiency metrics as model inputs (adjOE, adjDE, barthag) — verified: 95.7% of champions since 2001 had top-22 offense and top-32 defense
- Backtesting against multiple prior tournaments — model credibility requires demonstrated historical performance
- Auto-fetch bracket seedings on Selection Sunday (with manual CSV fallback) — time-critical, must be ready before Selection Sunday 2026
- Team name normalization across sources — the hardest data engineering problem; Sports-Reference, ESPN, and cbbdata all use different name formats

**Should have (differentiators — add after MVP is validated):**
- Stacking ensemble (multiple rating systems: Torvik, NET, BPI alongside logistic regression) — demonstrably more accurate than single-model
- Monte Carlo simulation (10,000+ runs) for confidence intervals and upset detection — required for calibration validation
- Interactive bracket with manual override picks and downstream cascade recalculation — hardest UI feature; override in one round changes all downstream matchups
- Pool-strategy optimization (contrarian picks for large pools) — expected value analysis; PoolGenius documents 3.1x win rate improvement
- Predicted score/margin of victory — secondary model output, same feature set
- Injury adjustment flag — manual override before bracket submission; as of 2026, NCAA requires official injury reports

**Defer indefinitely:**
- Real-time tournament update mode — complex live data feed, marginal bracket value
- Multiple bracket flavors (optimal, contrarian, upset-heavy) — build one good bracket first
- Women's tournament — separate data, models, and bracket; doubles scope
- Multi-user/social features — out of scope for personal tool
- Real-money gambling integration — out of scope

### Architecture Approach

The architecture is five independently testable layers with strict left-to-right data flow: Data Pipeline → Feature Store → Model Layer → Bracket Simulator → Web UI, with the Backtest Harness as a side-channel that replays the pipeline against historical snapshots. No layer communicates backward — the Web UI can send override signals back to the Simulator, but the Simulator does not write back to the Model Layer. This separation is what makes model swapping and backtesting feasible without full rewrites.

The bracket simulator has two operating modes: deterministic (pick highest-probability team each round, produces one definitive bracket) and Monte Carlo (Bernoulli draws, 10,000 runs, produces confidence distributions). Both are required — deterministic for the primary bracket output, Monte Carlo for calibration validation and upset analysis. The override mechanism works by storing a `{slot_id: team_id}` map and re-running `simulate_bracket()` from scratch on each override — this is simpler than surgical downstream propagation and fast enough (milliseconds per simulation) to be imperceptible.

**Major components:**
1. Data Pipeline — fetch, clean, persist raw game and team data from ESPN/CBBpy, cbbdata API, and Kaggle; output normalized game records to SQLite and Parquet
2. Feature Store — compute derived metrics per team-season (adjOE, adjDE, barthag, tempo, SOS, recent form, Elo); output feature vectors for matchup pairs
3. Model Layer — train and serve stacking ensemble; output calibrated P(team_a beats team_b) for any matchup; save trained models with joblib
4. Bracket Simulator — fill all 67 tournament games using win probabilities; produce bracket JSON with slot addressing; support override map injection
5. Backtest Harness — replay Feature Store → Model → Simulator against historical tournament snapshots; output per-year, per-model accuracy and Brier score table
6. Web UI — Streamlit app displaying filled bracket as programmatic SVG, per-game probabilities, and override controls

### Critical Pitfalls

The five critical pitfalls all share a root cause: treating data carelessly during feature engineering and validation. All five are preventable by design choices made in Phases 1-3 before any model training.

1. **Data leakage from post-tournament data into training features** — Enforce a hard cutoff date for all feature computation: data must be as-of Selection Sunday for each backtest year. Full-season stats scraped from season-end summaries include games played after the bracket was set. Flag for Phase 1-2. Detection: training accuracy above 78-80% is a red flag.

2. **K-fold cross-validation on tournament games** — Tournament years are not exchangeable samples. Use walk-forward temporal splits only: train on years T-N through T-1, evaluate on T. Never let future tournament outcomes appear in a training fold. Flag for Phase 3.

3. **Chalk-biased model from class imbalance** — The favorite wins ~71% of historical games; a model trained without imbalance handling learns to always pick the favorite. Evaluate with Brier score and log-loss, not accuracy. Apply class weights or resampling. Validate with Monte Carlo: if fewer than 5% of 10,000 simulations include even one 10+ seed in the Sweet 16, probabilities are miscalibrated. Flag for Phase 3-4.

4. **Backtesting only on 2025** — 2025 was historically chalk (all four #1 seeds in Final Four; second time in 38 years). A model that scores well on 2025 alone may simply be a chalk model. Multi-year backtest is mandatory: include 2022 (Saint Peter's Elite Eight), 2023 (FAU Final Four), 2024 (NC State run), and 2025. Flag for Phase 3.

5. **Transfer portal era breaks historical team identity assumptions** — Since 2021, 53% of tournament rotation players previously played at another D-I school. Multi-year team trend features (momentum, consistency, tournament experience) are unreliable for 2022+ seasons. Use season-bounded features only as primary inputs. Flag for Phase 2.

---

## Implications for Roadmap

Based on research, suggested phase structure (7 phases, matching architecture build order):

### Phase 1: Data Pipeline and Historical Backfill
**Rationale:** Everything is blocked without data. Team name normalization across sources (Sports-Reference, ESPN, cbbdata) is the hardest data problem and must be solved here, not retrofitted later. The Kaggle dataset gives 20+ years of structured tournament data immediately; CBBpy covers current-season games. These two together eliminate the need to build a full custom scraper.
**Delivers:** Normalized game records in SQLite and Parquet files; team name normalization table; data covering 2003-2025 seasons; verified data cutoff enforcement (stats as of Selection Sunday per year)
**Addresses features from FEATURES.md:** Historical data pipeline (2010-2025), team name normalization, auto-fetch bracket data (build fetcher with ESPN + NCAA.com + manual CSV fallback)
**Avoids pitfalls:** Data leakage (enforce cutoff dates here, in the ingestion layer); tournament format contamination (explicitly flag First Four games per year); scraping rate limits (cache all scraped data on first fetch)
**Research flag:** Standard patterns for CBBpy and Kaggle dataset; ESPN unofficial API endpoint format needs verification when 2026 bracket is published

### Phase 2: Feature Store and Feature Engineering
**Rationale:** Raw stats cannot be fed to models directly. This phase computes the derived metrics (adjOE, adjDE, barthag, tempo, SOS, recent form) that are the actual model inputs. This is where seed bias and multicollinearity are addressed — by choosing efficiency-based metrics over raw seeds as primary signals. Perspective flipping (storing each game twice with labels swapped) must be implemented here for model calibration.
**Delivers:** `compute_features(team_a, team_b, season)` function with tests; feature vectors for all historical matchup pairs; VIF analysis confirming no collinear features
**Addresses features from FEATURES.md:** Adjusted efficiency metrics as model inputs; strength of schedule; recent form
**Avoids pitfalls:** Seed bias (use Torvik/cbbdata efficiency metrics, not raw seeds, as primary strength signals); multicollinearity (run VIF analysis, exclude AdjEM if AdjO and AdjD are both included); transfer portal era (season-bounded features only, test multi-year trend features separately)
**Research flag:** Standard patterns well-documented in academic literature; no additional research needed

### Phase 3: Baseline Model and Temporal Validation Infrastructure
**Rationale:** Start with logistic regression — it gives calibrated probabilities fast and is highly interpretable. But more importantly, this phase builds the temporal validation infrastructure that all subsequent model comparison depends on. Walk-forward temporal splits must be established before adding more model types, or backtest results will be meaningless. Brier score and log-loss must be the primary metrics from day one.
**Delivers:** Trained logistic regression baseline model saved to disk; walk-forward temporal validation harness; Brier score and log-loss evaluation pipeline; first multi-year backtest results (2022-2025)
**Uses stack:** scikit-learn 1.8.0 (LogisticRegression, StratifiedKFold), joblib (model persistence), optuna (when hyperparameter tuning is needed in Phase 4)
**Avoids pitfalls:** K-fold CV on tournament years (temporal splits only); chalk bias (Brier score as primary metric); single-year backtesting (multi-year validation established here as the standard)
**Research flag:** Standard ML patterns; no additional research needed

### Phase 4: Bracket Simulator (Deterministic and Monte Carlo)
**Rationale:** Once a baseline model exists, the bracket simulator can be built and tested against historical brackets. The slot addressing scheme (e.g., R1_W01, R2_W01 with parent-child relationships) must be designed correctly here — a flat list representation cannot support override cascading and must be rebuilt if designed wrong. Both simulation modes (deterministic and Monte Carlo) should be built together since they share the same underlying algorithm.
**Delivers:** `simulate_bracket(seedings, predict_fn, override_map)` function; bracket JSON output with full slot addressing; Monte Carlo bracket runner (N=10,000); calibration validation (Monte Carlo distributions should show plausible upset rates)
**Addresses features from FEATURES.md:** Round-by-round advancement probabilities; champion probability; predicted score/margin (secondary output)
**Avoids pitfalls:** Flat bracket representation (slot-based addressing required from day one); miscalibrated probabilities (Monte Carlo calibration check: <5% simulations with no 10+ seeds in Sweet 16 is a failure signal); greedy bracket filling (optimize for expected score, not per-game probability)
**Research flag:** Standard simulation patterns; no additional research needed

### Phase 5: Backtesting Harness and Model Comparison
**Rationale:** The backtesting harness is what selects the ensemble. It must replay the Feature Store → Model → Simulator pipeline against historical tournament snapshots with strict data cutoff enforcement. Multi-year evaluation across variance profiles (2022 chaos, 2023 chaos, 2024 moderate, 2025 chalk) is what distinguishes a calibrated model from a chalk-biased one.
**Delivers:** `backtest(year_range, models)` → multi-year, multi-model comparison table with per-round accuracy, ESPN bracket score, Brier score, and upset detection rate; model selection recommendation
**Addresses features from FEATURES.md:** Backtesting against prior tournaments; performance benchmark vs. chalk and published models
**Avoids pitfalls:** Single-year backtesting; data leakage in historical replay; temporal CV violations
**Research flag:** Standard patterns well-documented; the specific Brier score targets by model type could use deeper research during planning if quantitative thresholds are needed

### Phase 6: Ensemble and Advanced Models
**Rationale:** Ensemble composition should be guided by backtest results, not assembled speculatively. Only after Phase 5 produces a comparison table is it clear which base models improve the ensemble and how to weight them. Adding XGBoost and LightGBM here — not in Phase 3 — prevents premature optimization on models whose relative value is unknown.
**Delivers:** XGBoost 3.2.0 and LightGBM 4.6.0 base models; scikit-learn StackingClassifier with logistic regression meta-learner; calibrated ensemble output (Platt scaling or isotonic regression applied if calibration curves show bias); updated backtest comparison table with ensemble vs. individual models
**Uses stack:** XGBoost 3.2.0, LightGBM 4.6.0, scikit-learn StackingClassifier, optuna (hyperparameter tuning)
**Avoids pitfalls:** One-model-one-bracket (comparison infrastructure already exists from Phase 5); round-specific calibration ignored (analyze per-round performance, optionally add round number as a feature)
**Research flag:** XGBoost and LightGBM hyperparameter tuning for this specific domain could benefit from research-phase review; Kaggle March Mania winning solutions are the best source

### Phase 7: Streamlit UI with Bracket Visualization and Override Support
**Rationale:** The UI is the last layer and depends on a stable bracket JSON contract from the Simulator. Building it before the model produces trusted outputs inverts priorities. The bracket SVG must be generated programmatically in Python using `st.components.v1.html()` — no JavaScript build tooling. Override support requires re-running the full simulation on each toggle (fast enough at milliseconds per run).
**Delivers:** Streamlit application displaying full 68-team bracket as programmatic SVG; per-game win probabilities; round-by-round advancement table; champion probability; manual override picks with downstream cascade recalculation; injury override mechanism (manual probability adjustment per team before bracket submission)
**Addresses features from FEATURES.md:** Full 68-team bracket display; interactive bracket with override picks; downstream cascade visualization; pool-strategy output
**Uses stack:** Streamlit 1.54.0, Plotly, `st.components.v1.html()`, `st.session_state` for bracket pick state
**Avoids pitfalls:** Premature UI polish before model validation (model is validated by the time this phase starts); flat bracket representation (slot-based JSON contract already established in Phase 4)
**Research flag:** Programmatic SVG bracket layout for 68 teams is non-trivial; may benefit from research-phase review during planning to identify existing Python SVG generation approaches or bracket layout algorithms

### Phase Ordering Rationale

- The 5-layer dependency chain (Data → Features → Model → Simulator → UI) is fixed by data flow: you cannot compute features without clean data, cannot train a model without features, cannot simulate without a model, cannot build a meaningful UI without simulation output. Any deviation creates rework.
- Backtesting (Phase 5) comes after the baseline model (Phase 3) and simulator (Phase 4) because it requires both as inputs — but before ensemble (Phase 6) because ensemble composition should be informed by backtest evidence.
- The ensemble (Phase 6) is deliberately separated from the baseline model (Phase 3) to prevent premature optimization. Adding XGBoost before logistic regression is validated and compared is a common time sink.
- The UI (Phase 7) is last because it depends on a stable bracket JSON contract. Building it earlier means rebuilding it as model outputs change shape — documented explicitly as an anti-pattern in FEATURES.md.
- The hard external dependency is Selection Sunday 2026 (mid-March). Phase 1 (data pipeline and auto-fetch) must be operational before that date. Phases 2-6 need to be complete before Selection Sunday to be useful. Phase 7 (UI) can be completed concurrently with Phases 5-6 once the bracket JSON contract is stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Data Pipeline):** ESPN unofficial API endpoint format for 2026 bracket needs verification when bracket is published. NCAA.com JSON endpoint format has historically been stable but is undocumented. Auto-fetch reliability on Selection Sunday is a one-shot operation with no retry window.
- **Phase 6 (Ensemble):** XGBoost and LightGBM hyperparameter ranges for this specific domain (tabular matchup prediction, ~10 features, ~20 years of tournament data) are not well-constrained by existing research. Kaggle March Mania solution notebooks are the best source; a research-phase review would improve optuna search space definition.
- **Phase 7 (UI/SVG Bracket):** Programmatic SVG layout for a 68-team single-elimination bracket with First Four games is non-trivial geometry. A research-phase review to identify existing Python SVG layout approaches or bracket coordinate generation algorithms would save implementation time.

Phases with standard patterns (skip research-phase):
- **Phase 2 (Feature Store):** Efficiency metric computation is well-documented in academic literature and open-source projects. VIF analysis is standard scikit-learn.
- **Phase 3 (Baseline Model):** Logistic regression with temporal CV is a standard ML pattern. Brier score evaluation is fully documented.
- **Phase 4 (Bracket Simulator):** Single-elimination bracket traversal is a solved algorithm. Monte Carlo simulation is standard.
- **Phase 5 (Backtesting):** Walk-forward temporal validation is standard; replay pipeline structure is clear from architecture research.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified at PyPI as of 2026-03-02. CBBpy, XGBoost, LightGBM, pandas, DuckDB, Streamlit versions confirmed. ESPN unofficial API marked MEDIUM — no stability guarantee. |
| Features | HIGH | Multiple independent sources agree on table stakes (KenPom, Nate Silver, PoolGenius, NCAA.com, open-source projects). 2025 tournament data confirms efficiency-first approach. Feature dependency order is unambiguous. |
| Architecture | MEDIUM-HIGH | Five-layer pipeline pattern verified against academic papers (arXiv 2503.21790, 2508.02725) and open-source projects (pjmartinkus/College_Basketball). Override cascade mechanism is design-level, not empirically verified. |
| Pitfalls | MEDIUM | Pitfalls are practitioner-consensus and partially peer-reviewed (data leakage and temporal CV are well-documented; transfer portal impact is verified with 2025 data; chalk bias is documented in multiple sources). Committee seeding bias data is from 2013 and may not reflect current committee behavior. |

**Overall confidence: HIGH**

### Gaps to Address

- **ESPN unofficial API stability on Selection Sunday 2026:** The auto-fetch bracket pipeline must be built with fallback to manual CSV entry. This is a one-time operation with no retry window if the API changes format. Verify endpoint behavior when the 2026 bracket is published; do not assume the 2025 endpoint format is stable.
- **cbbdata API key acquisition:** Free key requires registration at cbbdata.aweatherman.com. Must be obtained before Phase 1 begins. Verify the REST API is accessible from Python (documentation is R-centric).
- **Kaggle dataset update timing:** The March Machine Learning Mania 2026 dataset is likely not yet published (tournament hasn't happened). Historical data (2003-2025) should be available. Confirm whether 2025 season data is included in the current Kaggle dataset version.
- **First Four bracket representation:** The tournament has 68 teams with 4 play-in games producing the 64-team field. The data contract (bracket JSON) and simulator must handle First Four games explicitly. Kaggle datasets have historically treated this inconsistently; resolve during Phase 1.
- **Accuracy ceiling expectation-setting:** The empirically verified accuracy ceiling is 74-76% per-game. This should be documented as a success criterion in project documentation so that a well-calibrated 74% model is recognized as a success, not a failure. Beating this ceiling is not a design goal.
- **2026 injury report integration:** NCAA announced official pre-game injury reports for 2026 (rule change). These reports are available the night before and 2 hours before each game. The override mechanism in Phase 7 should explicitly support manual probability adjustment based on injury reports — this is a new data source not available in historical seasons.

---

## Sources

### Primary (HIGH confidence)
- https://pypi.org/project/xgboost/ — XGBoost 3.2.0 version verification
- https://pypi.org/project/scikit-learn/ — scikit-learn 1.8.0, Python >=3.11 requirement
- https://pypi.org/project/lightgbm/ — LightGBM 4.6.0 version verification
- https://pypi.org/project/pandas/ — pandas 3.0.1, Python >=3.11 requirement
- https://pypi.org/project/duckdb/ — DuckDB 1.4.4 version verification
- https://pypi.org/project/streamlit/ — Streamlit 1.54.0, Python >=3.10
- https://pypi.org/project/CBBpy/ — CBBpy 2.1.2, ESPN-backed, actively maintained
- https://www.kaggle.com/competitions/march-machine-learning-mania-2025/ — Kaggle March Machine Learning Mania dataset (2003-2025)
- https://arxiv.org/html/2503.21790v1 — Mathematical Modeling NCAA Bracket (Logistic Regression + Monte Carlo), academic
- https://arxiv.org/html/2508.02725v1 — LSTM/Transformer for NCAA Forecasting, temporal validation, calibration vs. discrimination tradeoff
- https://github.com/pjmartinkus/College_Basketball — Five-stage pipeline, covariate shift analysis (open-source, verified)
- https://kenpom.substack.com/p/2025-ncaa-tournament-probabilities — KenPom 2025 methodology
- https://www.natesilver.net/p/2025-march-madness-ncaa-tournament-predictions — Nate Silver 2025 methodology (6-system ensemble, injury recalibration)
- https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/bracket-strategy-guide/ — PoolGenius bracket strategy (contrarian picks, 3.1x win rate improvement documented)
- sports.yahoo.com — 2025 all four #1 seeds in Final Four confirmed fact
- CNBC.com — 53% of 2025 tournament rotation players previously at another D-I school (transfer portal data)

### Secondary (MEDIUM confidence)
- https://cbbdata.aweatherman.com/articles/release.html — cbbdata API is free, barttorvik-backed REST API
- https://github.com/pseudo-r/Public-ESPN-API — ESPN unofficial API endpoints
- https://poolgenius.teamrankings.com — Contrarian value picks methodology, upset rate analysis
- https://jtmarcu.github.io/projects/march-madness.html — Random Forest implementation, AUC 0.753
- https://blog.collegefootballdata.com/talking-tech-march-madness-xgboost/ — XGBoost for bracket prediction practitioner analysis
- https://www.kaggle.com/code/sadettinamilverdil/ncaa-basketball-predictions-with-xgboost — XGBoost Kaggle notebook
- https://www.researchgate.net/publication/257749099 — Academic confirmation of ~75% accuracy ceiling
- https://adeshpande3.github.io/Applying-Machine-Learning-to-March-Madness — Chalk bias in gradient boosted models (practitioner)
- https://www.ncaa.com/news/basketball-men/bracketiq/2026-02-24/5-ncaa-bracket-tips-learned-studying-every-bracket-challenge-game-winner-2015 — NCAA bracket challenge winner analysis

### Tertiary (LOW confidence)
- https://data.ncaa.com/casablanca/scoreboard/ — NCAA JSON bracket endpoint (developer community reports; verify when 2026 bracket is published)
- https://keepingscore.blogs.time.com/2013/03/15/ — Committee seeding bias toward major conferences (2013 data; may not reflect current committee)
- barttorvik.com — Cloudflare bot protection confirmed; direct scraping is not viable; use cbbdata API instead

---
*Research completed: 2026-03-02*
*Ready for roadmap: yes*
