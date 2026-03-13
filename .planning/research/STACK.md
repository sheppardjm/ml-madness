# Technology Stack: NCAA Bracket Predictor — Milestone 2 Additions

**Project:** madness2026
**Researched:** 2026-03-13
**Research mode:** Stack dimension for milestone 2 (pool optimizer, UI enrichment, model retraining)
**Scope:** NEW additions only. Existing validated stack (Python 3.12, uv, Streamlit 1.55.0, DuckDB 1.4.4, XGBoost 3.2.0, LightGBM 4.6.0, scikit-learn 1.8.0, pandas 3.x, numpy 2.4.x, Optuna, Plotly) is not re-researched.

---

## TL;DR: No New Dependencies Required

The three milestone features can be built entirely on the existing stack. Every library needed is already installed. This section documents WHY each approach was chosen and what NOT to add.

---

## Feature 1: Pool Strategy Optimizer (Contrarian Picks)

### What It Needs

Pool optimization for large bracket pools (100+ entrants) requires:
1. **Expected Value (EV) calculation** — compare a team's win probability to its expected ownership percentage in the field, weighted by scoring round
2. **Contrarian leverage scoring** — identify teams whose win probability exceeds their pick share
3. **Bracket generation** — produce a single concrete bracket that maximizes expected finish position, not just probability of winning any individual game

### Stack Decision: Pure numpy + existing Monte Carlo

**Use:** `numpy` (already installed, 2.4.2) for vectorized EV math. No new optimization library.

**Why not scipy.optimize:** scipy.optimize (1.17.1, already installed) is designed for continuous function minimization. Pool bracket optimization is a discrete combinatorial problem — 63 binary pick decisions. `scipy.optimize.differential_evolution` or `minimize` adds complexity without benefit over a direct EV-greedy approach for this domain. The existing Monte Carlo simulator (10K runs) already produces per-team advancement probabilities per round; the optimizer just needs to compare those against ownership percentages.

**Why not PuLP / OR-Tools / integer programming:** The bracket structure imposes sequential dependencies (you can't pick a team to win the Elite 8 without picking them to win the Sweet 16). This makes the problem a tree-structured decision, not a flat ILP. An EV-greedy tree traversal (pick the highest EV team per slot, propagating forward) is both correct and fast, and requires no new dependency.

**The core math (no new library needed):**
```
For each slot, EV of picking team T =
    P(T wins this slot) * round_points / (ownership(T, slot) * n_entrants)

where:
    P(T wins slot)    = from existing Monte Carlo advancement_probs
    round_points      = scoring table (standard ESPN: 1/2/4/8/16/32 or user-configurable)
    ownership(T, slot) = user-supplied estimate of field pick percentage
    n_entrants        = pool size parameter (default 150)
```

**Ownership percentage input:** User-entered via Streamlit sliders or numeric inputs. No external data source needed for MVP. The app already has team-level advancement probabilities from Monte Carlo; ownership percentages are the only new user input.

**Confidence: HIGH** — Verified that scipy 1.17.1 and numpy 2.4.2 are already installed in the project venv. The EV formula is well-established in bracket pool literature (PoolGenius, ActionNetwork, FTN Fantasy all use this framework). No novel math required.

### What NOT to Add

| Library | Why Not |
|---------|---------|
| scipy.optimize solvers | Already installed; continuous solvers are wrong tool for discrete bracket picks |
| PuLP / OR-Tools | Adds a new dependency for a problem that doesn't need ILP; sequential bracket constraints fit greedy tree traversal better |
| cvxpy | Overkill for this domain; adds compile dependency for C extension |
| Any "bracket optimizer" PyPI package | None exist that integrate with the existing Monte Carlo output |

---

## Feature 2: Richer Matchup Context in Streamlit UI

### What It Needs

When a user clicks a matchup in the bracket, show:
- Head-to-head comparison: adjOE, adjDE, barthag, tempo, wab (all already in `current_season_stats.parquet`)
- Historical seed vs seed performance (already in `tournament_games.parquet`)
- Win probability bar/gauge
- Optionally: conference, record if available

### Stack Decision: st.dialog (already in Streamlit 1.55.0)

**Use:** `st.dialog` (Streamlit 1.55.0, already installed) for click-to-expand matchup detail panels.

**Why st.dialog over alternatives:**

| Approach | Assessment |
|----------|-----------|
| `st.dialog` | Confirmed available in Streamlit 1.55.0. Modal overlay, supports dataframes, charts, and metric widgets inside. Width parameter: "small"/"medium"/"large". Dismissible by default. One dialog open at a time — fine for single-user personal tool. **Recommended.** |
| `st.popover` | Also available in 1.55.0 (with `on_change` and `key` params for programmatic open/close). Better for non-modal inline detail. Works for "hover info" style UX. Alternative approach. |
| Custom Streamlit component | Not needed; st.dialog provides sufficient capability |
| st.expander | Already used for override controls; reusing would be cluttered |

**Recommendation:** Use `st.dialog` for the primary matchup detail panel (modal, focused, can show a full stats table). Use `st.popover` as a lighter-weight hover alternative for quick probability context inline with the bracket.

**Stat display:** `st.dataframe` with `st.column_config` (already used in the advancement table) can render a side-by-side comparison table for the two teams. `st.plotly_chart` (Plotly 6.6.0, already installed) for a bar chart comparing efficiency metrics.

**Data source for stats:** `data/processed/current_season_stats.parquet` (already populated by `cbbdata_client.py`). Contains barthag, adj_o, adj_d, adj_t, wab for all D1 teams. Already loaded in the UI via `src/ui/data_loader.py`.

**Historical seed performance:** `data/processed/tournament_games.parquet` already has full game history (2008-2025). A DuckDB query against this file for "seed X vs seed Y historically" is sub-millisecond. DuckDB (1.4.4) is already the storage layer.

**Confidence: HIGH** — st.dialog and st.popover confirmed present in installed Streamlit 1.55.0. All required data already exists in processed Parquet files.

### What NOT to Add

| Library | Why Not |
|---------|---------|
| streamlit-extras / third-party components | Not needed; native Streamlit containers (st.dialog, st.popover, st.dataframe, st.metric) cover the requirement |
| Altair | Plotly is already installed; adding Altair adds a dependency for chart parity |
| CBBpy (for live game stats) | The tournament hasn't started; in-season game stats aren't relevant until first round begins (March 20) |
| Pandas Styler | st.column_config covers color-coding and progress bars without Styler compatibility issues |

---

## Feature 3: Model Retraining Workflow

### What It Needs

When cbbdata indexes 2025-26 season data (expected: after Selection Sunday 2026-03-15 or post-tournament 2026-04), the user needs to:
1. **Ingest new season:** Fetch Torvik ratings for year=2026 via existing `cbbdata_client.py` (already handles the archive fallback)
2. **Append training data:** Add 2026 tournament results to `tournament_games.parquet` and `historical_torvik_ratings.parquet`
3. **Retrain ensemble:** Re-run `src/models/ensemble.py` `build_ensemble()` with updated data (already parameterized by `train_seasons`)
4. **Validate:** Re-run backtesting harness to confirm Brier score didn't regress
5. **Swap artifact:** Replace `models/ensemble.joblib` with new artifact

### Stack Decision: Existing joblib + existing training pipeline

**Use:** `joblib` (1.5.3, already installed) for serialization. No new retraining framework.

**Why not MLflow / DVC / Weights & Biases:** This is a personal project retrained once per year. MLflow/DVC add experiment tracking server setup, config files, and conceptual overhead for a problem that's solved with a shell script and the existing `build_ensemble()` function. Overkill.

**Why not skops.io:** The existing artifact already stores sklearn/xgboost/lightgbm version metadata in the `.joblib` dict (`m['sklearn_version']`, `m['xgboost_version']`, `m['lightgbm_version']`). skops.io is for security-sensitive model sharing; unnecessary here.

**The retraining workflow is already mostly built:**
- `src/models/ensemble.py` `build_ensemble()` trains from scratch given a dataset
- `src/models/features.py` `build_matchup_dataset()` assembles training data from Parquet
- `src/ingest/cbbdata_client.py` handles year=2026 data fetch with archive fallback
- `models/selected.json` acts as the model registry (stores Brier, train seasons, generated_at)
- The existing artifact stores all version metadata needed to detect drift

**What needs to be added (code, not new libraries):**
1. A `scripts/retrain.py` CLI script that orchestrates: ingest → build features → train → validate → write artifact
2. A version bump check: compare new Brier against `selected.json` `mean_brier` before overwriting

**The cbbdata data availability constraint (already documented in codebase):**
The `cbbdata_client.py` comment at line 113 notes: "As of 2026-03, cbbdata's ratings endpoint only has complete year-end data through year=2024. Year=2025 returns rows without barthag populated. Year=2026 (2025-26 season) returns empty." The archive fallback handles this. After the tournament ends (early April 2026), cbbdata typically indexes the final season ratings within days to weeks — the fallback will resolve automatically when that data appears.

**Confidence: HIGH** — Verified by reading `src/ingest/cbbdata_client.py` directly. The data pipeline for retraining is implemented; only an orchestration script is missing.

### What NOT to Add

| Library | Why Not |
|---------|---------|
| MLflow | Experiment tracking server for a once-per-year personal retrain is architectural overkill |
| DVC | Data versioning adds `.dvc` metadata files and remote storage config; the Parquet files are small enough to version with git-lfs or just leave local |
| Weights & Biases | Requires account, API key, cloud dependency; wrong fit for local personal project |
| ONNX | ONNX serialization loses the Python predict_fn integration that drives the bracket simulator; adds a runtime dependency for no portability benefit |
| Prefect / Airflow | Workflow orchestration tools for multi-step pipelines; a 50-line Python script is sufficient |
| skops.io | Security-focused serialization for model sharing; this model is never shared externally |

---

## Confirmed Installed Versions (Verified 2026-03-13)

These packages are already present in the project `.venv` and satisfy all milestone 2 requirements:

| Package | Installed Version | Relevant For |
|---------|------------------|--------------|
| streamlit | 1.55.0 | UI enrichment (st.dialog, st.popover, st.dataframe) |
| scipy | 1.17.1 | Pool optimizer (already installed, not needed for MVP approach) |
| numpy | 2.4.2 | Pool EV math (vectorized advancement prob comparison) |
| joblib | 1.5.3 | Model retraining persistence |
| plotly | 6.6.0 | Matchup stats visualization |
| duckdb | 1.4.4 | Historical seed performance queries |
| pandas | 3.0.1+ | Data manipulation throughout |

**scipy** is already installed as a transitive dependency. It is not needed for pool optimization (the EV-greedy approach doesn't use scipy.optimize), but it's available if the approach needs to evolve.

---

## pyproject.toml Changes Required

**None.** All dependencies are already present. The milestone 2 features are pure code additions using the existing stack.

If the retraining workflow needs a CLI entry point, add to `pyproject.toml`:
```toml
[project.scripts]
retrain = "scripts.retrain:main"
```
This requires no new `dependencies` entry.

---

## Integration Points Summary

| Feature | Reads From | Writes To | Key Existing Code |
|---------|-----------|----------|-------------------|
| Pool optimizer | `mc_result["advancement_probs"]` (in-memory) | session state (suggested brackets) | `src/simulator/simulate.py` MC output |
| Matchup UI | `data/processed/current_season_stats.parquet`, `data/processed/tournament_games.parquet` | none | `src/ui/data_loader.py`, `app.py` |
| Model retraining | `data/processed/*.parquet`, cbbdata API | `models/ensemble.joblib`, `models/selected.json` | `src/models/ensemble.py`, `src/ingest/cbbdata_client.py` |

---

## Sources

| Claim | Source | Confidence |
|-------|--------|------------|
| Streamlit 1.55.0 installed, st.dialog available | `python -c "import streamlit"` in project venv | HIGH |
| scipy 1.17.1 installed | `python -c "import scipy"` in project venv | HIGH |
| numpy 2.4.2 installed | `python -c "import numpy"` in project venv | HIGH |
| joblib 1.5.3 installed | `python -c "import joblib"` in project venv | HIGH |
| Streamlit 1.55.0 release notes (st.dialog, st.popover, on_change) | https://docs.streamlit.io/develop/quick-reference/release-notes/2026 | HIGH |
| st.dialog supports dataframes/charts/metrics as container | https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog | HIGH |
| st.popover parameters (on_change, key, width) | https://docs.streamlit.io/develop/api-reference/layout/st.popover | HIGH |
| scipy 1.17.1 current latest version | https://pypi.org/project/SciPy/ | HIGH |
| joblib 1.5.3 current latest stable | WebSearch pypi.org/project/joblib | MEDIUM |
| sklearn persistence: no cross-version loading guarantee | https://scikit-learn.org/stable/model_persistence.html | HIGH |
| Pool optimizer EV formula (advancement_prob * points / ownership * N) | Establish The Run 2025 pool strategy, ActionNetwork contrarian bracket guide | MEDIUM — industry-standard formulation, not a citable spec |
| cbbdata year=2026 returns empty, archive fallback works | Direct code read: `src/ingest/cbbdata_client.py` line 113 comment + archive logic | HIGH |
| Ensemble artifact stores version metadata | Direct inspection: `joblib.load('models/ensemble.joblib').keys()` | HIGH |
| Kaggle March Machine Learning Mania 2026 dataset available | https://www.kaggle.com/competitions/march-machine-learning-mania-2026 | HIGH |
