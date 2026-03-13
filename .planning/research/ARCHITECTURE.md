# Architecture Patterns

**Domain:** NCAA Men's Basketball Bracket Predictor — v1.1 Integration Architecture
**Researched:** 2026-03-13
**Confidence:** HIGH (derived from direct codebase audit of 12,400 lines across 167 files)

---

## Existing Architecture (v1.0 Baseline)

The five-layer pipeline is already in production. This document maps how v1.1 features
— pool strategy optimizer, UI enrichment, and model retraining — integrate into those
layers.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           NCAA Bracket Predictor v1.0                               │
│                                                                                     │
│  ┌────────────┐    ┌─────────────┐    ┌──────────┐    ┌─────────────┐              │
│  │  LAYER 1   │───▶│   LAYER 2   │───▶│ LAYER 3  │───▶│   LAYER 4   │              │
│  │  Data      │    │  Feature    │    │  Model   │    │  Bracket    │              │
│  │  Pipeline  │    │  Store      │    │  Layer   │    │  Simulator  │              │
│  └────────────┘    └─────────────┘    └──────────┘    └─────────────┘              │
│       │                                    ▲                  │                     │
│       │            ┌───────────────────────┘                  ▼                     │
│       │            │  (trained models)                 ┌──────────────┐            │
│       └───────────▶│  Backtest Harness                 │   LAYER 5    │            │
│                    │  src/backtest/                    │   Web UI     │            │
│                    └───────────────────────────────────│   app.py     │            │
│                                                        └──────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Existing Component Inventory

| Component | Key Files | Output Contract |
|-----------|-----------|-----------------|
| Data Pipeline | `src/ingest/cbbdata_client.py`, `src/ingest/fetch_bracket.py`, `src/ingest/fetch_historical_ratings.py`, `src/ingest/kaggle_download.py` | `data/processed/*.parquet` |
| Feature Store | `src/models/features.py` | `compute_features(team_a, team_b, season)` → 6-feature dict; `build_stats_lookup()` → `{(season, team_id): stats}` |
| Model Layer | `src/models/ensemble.py`, `src/models/train_*.py` | `TwoTierEnsemble.predict_proba(X)` → probabilities; `models/ensemble.joblib` |
| Bracket Simulator | `src/simulator/simulate.py`, `src/simulator/bracket_schema.py` | `simulate_bracket(seedings, predict_fn, mode)` → result dict with `slots` / `advancement_probs` |
| Web UI | `app.py`, `src/ui/` | Streamlit app with SVG bracket, advancement table, override controls |
| Backtest Harness | `src/backtest/backtest.py` | `backtest/ensemble_results.json` |

---

## v1.1 Integration Map

Three new capabilities must integrate with this pipeline:

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           v1.1 Integration Points                                        │
│                                                                                          │
│  ┌────────────┐    ┌─────────────┐    ┌──────────┐    ┌─────────────┐                   │
│  │  LAYER 1   │    │   LAYER 2   │    │ LAYER 3  │    │   LAYER 4   │                   │
│  │  Data      │    │  Feature    │    │  Model   │    │  Bracket    │                   │
│  │  Pipeline  │    │  Store      │    │  Layer   │    │  Simulator  │                   │
│  └─────┬──────┘    └──────┬──────┘    └─────┬────┘    └──────┬──────┘                   │
│        │ [A] refresh      │                 │ [B] retrain    │                           │
│        │ current_season   │                 │ ensemble        │                           │
│        │ stats            │                 │                 │                           │
│        │                  │                 │                 │                 NEW       │
│        │                  │ [C] matchup     │                 │         ┌──────────────┐  │
│        │                  │ context query   │                 │         │  LAYER 5+    │  │
│        │                  │──────────────────────────────────────────▶ │  Pool        │  │
│        │                  │                 │                 │         │  Strategy    │  │
│        │                  │                 │                 │─────────│  Optimizer   │  │
│        │                  │                 │                 │  mc_    │              │  │
│        │                  │                 │                 │  result │  src/pool/   │  │
│        │                  │                 │                 │         └──────┬───────┘  │
│        │                  │                 │                 │                │          │
│        │                  │                 │                 │                ▼          │
│        │                  │                 │                 │         ┌──────────────┐  │
│        │                  │                 │                 │         │  LAYER 5     │  │
│        │                  │─────────────────────────────────────────▶  │  Web UI      │  │
│        │                  │ [C] team stats  │                 │  det +  │  (enriched)  │  │
│        │                  │ for hover cards │                 │  mc     │  app.py      │  │
│        │                  │                 │                 │         └──────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Integration points labeled [A], [B], [C] are described in detail below.**

---

## Integration Point A: Model Retraining

**Capability:** Refresh `current_season_stats.parquet` with real 2025-26 Torvik data and retrain the ensemble.

### What already exists

`src/ingest/cbbdata_client.py` has `ingest_current_season_stats(api_key, year=2026)` which:
- Fetches Torvik ratings from cbbdata API with archive fallback
- Matches team names via `team_normalization.parquet`
- Writes to `data/processed/current_season_stats.parquet`

`src/models/features.py` has `build_stats_lookup()` which:
- Reads `historical_torvik_ratings.parquet` (2008-2025)
- Overlays `current_season_stats.parquet` for the current season
- Returns `{(season, team_id): stats}` used by the entire feature pipeline

`src/models/ensemble.py` has `build_ensemble()` which trains `TwoTierEnsemble` via manual OOF temporal stacking using `walk_forward_splits()`.

### What needs to change

Nothing needs to be modified in existing code. The retraining flow is:

```
Step 1: cbbdata_client.ingest_current_season_stats(key, year=2026)
        → overwrites data/processed/current_season_stats.parquet

Step 2: build_stats_lookup() picks up the new parquet automatically
        (no cache to invalidate — it reads at call time)

Step 3: build_matchup_dataset() uses the updated stats_lookup
        → 2026 season data is now included in training set

Step 4: Run src/models/train_xgboost.py, train_lightgbm.py, train_logistic.py
        → refresh hyperparameter JSON files if Optuna re-tuning desired,
           or skip re-tuning and use existing params for speed

Step 5: Run src/models/ensemble.py __main__
        → overwrites models/ensemble.joblib with retrained artifact

Step 6: Run src/dashboard/compare.py
        → updates models/selected.json with new best model

Step 7: Restart Streamlit app
        → @st.cache_resource on load_model() picks up new artifact
```

### New component needed

A single orchestration script: `scripts/retrain.py` (or `src/ingest/retrain_pipeline.py`).

This script strings together steps 1-6 with error handling and a dryrun flag. It is NOT a Streamlit page — it is a CLI script run manually or on a cron schedule.

```python
# Interface sketch
def retrain_pipeline(
    api_key: str,
    year: int = 2026,
    skip_fetch: bool = False,    # use existing current_season_stats.parquet
    skip_optuna: bool = True,    # reuse existing xgb/lgb hyperparams
    dry_run: bool = False,       # validate but don't overwrite models/
) -> dict[str, Any]:
    """Returns dict with before/after Brier scores for comparison."""
```

### Modification to existing files

`src/models/temporal_cv.py` currently defines `BACKTEST_YEARS = [2022, 2023, 2024, 2025]`.
When retraining on 2026 data, the backtest window may need updating to include 2026 if
tournament results become available. This is a one-line constant change, not an architectural
change.

`src/models/features.py` line ~360: The `build_stats_lookup()` overlay logic currently
hard-codes `season == 2025`. This must be parameterized or made dynamic (detect current
season from data) to support 2026 retraining.

---

## Integration Point B: Pool Strategy Optimizer

**Capability:** Contrarian pick analysis for large (100+) bracket pools.

### Data dependency

The pool strategy optimizer's only input is the Monte Carlo output from `simulate_bracket()`:

```python
mc_result = simulate_bracket(seedings, predict_fn, mode="monte_carlo", n_runs=10000)
# mc_result["advancement_probs"] = {
#     team_id: {
#         "Round of 64": 0.97,
#         "Round of 32": 0.83,
#         ...
#         "Champion": 0.28,
#     },
#     ...
# }
```

This dict is already computed and cached in the UI via `run_monte_carlo()` in `src/ui/data_loader.py`. The optimizer does not need to re-run any simulation — it reads `mc_result["advancement_probs"]` directly.

### New component: `src/pool/optimizer.py`

This is a pure-computation module with no Streamlit dependency.

```python
def compute_pool_strategy(
    mc_result: dict,
    field_size: int = 100,
    scoring_system: str = "espn",  # or "standard", "upset_multiplier"
    n_strategy_runs: int = 10000,
) -> dict:
    """
    Returns:
      {
        "recommended_bracket": {slot_id: team_id, ...},
        "contrarian_picks": [
          {
            "slot": "R6CH",
            "model_pick": {"team_id": 1234, "name": "Duke", "prob": 0.28},
            "contrarian_pick": {"team_id": 5678, "name": "Arizona", "prob": 0.14},
            "expected_value_gain": 0.043,
            "rationale": "14% win probability but likely <8% of field picks them",
          }
        ],
        "expected_score": 142.3,
        "field_coverage": {team_id: estimated_pick_pct, ...},
      }
    ```
    """
```

### Algorithm approach

Pool strategy requires estimating what the rest of the field will pick, then finding
picks that are both likely enough to win AND underrepresented in the field.

**Field pick percentage estimation:** The standard approximation is that public pick
percentages correlate strongly with win probability. A calibration curve from historical
ESPN bracket data suggests roughly `pick_pct ≈ win_prob^0.6` for chalk teams and a
power-law tail for upsets. This is a LOW-confidence approximation — actual field data
from ESPN's bracket challenge would be better if available.

**Expected value calculation:** For a pick in round R at slot S:
```
EV(pick S = team T) = P(T advances to S) * points_for_round_R * (1 / estimated_field_pct_who_picked_T_at_S)
```

The EV gain from picking contrarian = EV(contrarian) - EV(consensus chalk pick).

**Recommended implementation:** Start with a simple approach — rank all possible picks by
`P(team wins slot) / estimated_field_pick_pct(team, slot)`. High ratio = high contrarian
value. More sophisticated expected value calculations can be added in a follow-on task.

### UI integration point

The optimizer output surfaces in the Web UI as a new tab in `app.py`:

```python
tab_bracket, tab_advancement, tab_champion, tab_pool = st.tabs(
    ["Bracket", "Advancement Probabilities", "Champion", "Pool Strategy"]
)
```

The pool tab takes `mc_result` (already computed) and `field_size` (sidebar input) as
its only inputs. No new simulation runs are needed.

### Caching note

`compute_pool_strategy()` is deterministic given `mc_result` and parameters. It should
be wrapped in `@st.cache_data` in a new `src/ui/pool_loader.py` module (following the
pattern of `src/ui/data_loader.py`).

---

## Integration Point C: UI Enrichment (Matchup Context)

**Capability:** Show team stats, historical performance, and head-to-head analysis in the
bracket UI.

### Data already available

`src/models/features.py:build_stats_lookup()` returns `{(season, team_id): stats}` where
`stats` contains:
```python
{
    "adj_o": float,     # Adjusted offensive efficiency
    "adj_d": float,     # Adjusted defensive efficiency (lower = better)
    "barthag": float,   # Power rating
    "adj_t": float,     # Adjusted tempo
    "wab": float,       # Wins above bubble
    "seed_num": int,    # Tournament seed number
}
```

This is already loaded by `build_ensemble_predict_fn()` in `src/ui/data_loader.py`.
The stats lookup is already in memory — it just isn't exposed to the UI layer.

`data/processed/historical_torvik_ratings.parquet` has 18 seasons of data and can answer
questions like "How often does a #3 seed lose to a #14 seed historically?"

`data/raw/kaggle/MNCAATourneySeeds.csv` and `tournament_games.parquet` have historical
matchup results for head-to-head seed analysis.

### What needs to change

**1. Expose stats_lookup to UI** — `build_ensemble_predict_fn()` in `src/ui/data_loader.py`
currently builds `stats_lookup` internally but does not return it. Two options:

- Option A (recommended): Add a new cached function `load_stats_lookup_cached(season)` to
  `src/ui/data_loader.py` that calls `build_stats_lookup()` with `@st.cache_data`.
- Option B: Modify `build_ensemble_predict_fn()` to return `(predict_fn, stats_lookup)`.
  This is a breaking change to the caller in `app.py` — less preferable.

**2. New module: `src/ui/matchup_context.py`** — Computes the per-matchup context cards.

```python
def build_matchup_context(
    team_a_id: int,
    team_b_id: int,
    season: int,
    stats_lookup: dict,
    historical_games_parquet: str = "data/processed/tournament_games.parquet",
    seeds_parquet: str = "data/processed/seeds.parquet",
) -> dict:
    """
    Returns:
      {
        "team_a": {
            "name": "Duke", "seed": 1,
            "adj_o": 123.4, "adj_d": 91.2,
            "barthag": 0.971, "wab": 8.2,
            "adj_o_rank": 2, "adj_d_rank": 3,
        },
        "team_b": {...},
        "head_to_head_seed": {
            "seed_a": 1, "seed_b": 16,
            "historical_wins_a": 140, "historical_games": 140,
            "upset_rate": 0.0,
        },
        "feature_diffs": {
            "adjoe_diff": 25.3,
            "barthag_diff": 0.412,
            ...
        },
      }
    """
```

**3. Integration with override controls** — Matchup context should appear when a user
opens an override expander. The current `_render_slot_override()` in
`src/ui/override_controls.py` resolves `strong_id, weak_id` via `_resolve_slot_teams()`.
That same team ID pair can be passed to `build_matchup_context()` to render stats inline.

The modification to `override_controls.py` is additive — add a `st.expander("Team stats")`
inside the existing slot expander, after the selectbox, that shows a condensed version of
the matchup context.

### Historical seed analysis module

`src/ui/seed_history.py` (new, small) handles the historical seed-matchup query:

```python
@st.cache_data
def load_seed_matchup_history(
    seed_a: int,
    seed_b: int,
    historical_games_parquet: str = "data/processed/tournament_games.parquet",
    seeds_parquet: str = "data/processed/seeds.parquet",
) -> dict:
    """Query historical win rates for (seed_a vs seed_b) matchups across all seasons."""
```

This runs a DuckDB join query on the two parquet files — already a pattern used throughout
the codebase.

---

## New Component Boundaries

| Component | Location | New / Modified | Dependencies |
|-----------|----------|---------------|--------------|
| Retrain pipeline script | `scripts/retrain.py` | NEW | `cbbdata_client`, `features.py`, `ensemble.py`, `compare.py` |
| Pool strategy optimizer | `src/pool/optimizer.py` | NEW | `mc_result` dict only (no external I/O) |
| Pool UI loader | `src/ui/pool_loader.py` | NEW | `optimizer.py`, `@st.cache_data` |
| Matchup context builder | `src/ui/matchup_context.py` | NEW | `stats_lookup`, `tournament_games.parquet`, `seeds.parquet` |
| Seed history query | `src/ui/seed_history.py` | NEW | DuckDB + `tournament_games.parquet` + `seeds.parquet` |
| `data_loader.py` | `src/ui/data_loader.py` | MODIFIED | Add `load_stats_lookup_cached()` function |
| `override_controls.py` | `src/ui/override_controls.py` | MODIFIED | Add matchup context display inside slot expanders |
| `features.py` | `src/models/features.py` | MODIFIED | Parameterize current-season year in `build_stats_lookup()` |
| `temporal_cv.py` | `src/models/temporal_cv.py` | MODIFIED | Update `BACKTEST_YEARS` constant if 2026 results available |
| `app.py` | `app.py` | MODIFIED | Add Pool Strategy tab; load stats_lookup; pass to matchup context |

---

## Data Flow Changes

### Existing flow (unchanged)

```
cbbdata API → current_season_stats.parquet
historical_torvik_ratings.parquet → build_stats_lookup() → predict_fn → simulate_bracket()
                                                                            ├─ det_result
                                                                            └─ mc_result → app.py
```

### New flow additions

```
[A] RETRAINING:
cbbdata API (2026) → current_season_stats.parquet (refreshed)
                   → build_stats_lookup() (picks up 2026 data automatically)
                   → build_matchup_dataset() → build_ensemble() → ensemble.joblib (retrained)

[B] POOL OPTIMIZER:
mc_result["advancement_probs"] → compute_pool_strategy(field_size) → pool strategy dict
                                                                     → Pool Strategy tab

[C] UI ENRICHMENT:
build_stats_lookup() ─────────────────────────────────────────────┐
                                                                    ▼
tournament_games.parquet + seeds.parquet → build_matchup_context(team_a, team_b) → override expanders
                                        → load_seed_matchup_history(seed_a, seed_b) → hover cards
```

---

## Suggested Build Order

Build order is determined by what unblocks what. The three v1.1 capabilities are
largely independent of each other after the data refresh.

```
STEP 1 (unblocks everything): Data Refresh
  - Run cbbdata ingest for 2026 season
  - Verify current_season_stats.parquet has 2025-26 data
  - No code changes required — existing pipeline handles this
  - DEPENDENCY: cbbdata must have 2025-26 Torvik data indexed
    (as of 2026-03-13, this is uncertain — fallback to archive endpoint exists)

STEP 2 (parallel after Step 1):

  2A — Model Retraining
    - Fix features.py current-season year parameterization
    - Write scripts/retrain.py orchestration script
    - Run full retrain pipeline
    - Verify Brier score didn't regress
    - RISK: cbbdata 2026 data unavailability forces using 2024-25 proxy again

  2B — Pool Strategy Optimizer
    - Write src/pool/__init__.py + src/pool/optimizer.py
    - No data dependencies — reads mc_result which is already computed
    - Write src/ui/pool_loader.py with @st.cache_data wrapper
    - Add Pool Strategy tab to app.py
    - LOWEST RISK: pure computation on existing data

  2C — UI Enrichment
    - Add load_stats_lookup_cached() to data_loader.py
    - Write src/ui/matchup_context.py
    - Write src/ui/seed_history.py
    - Modify override_controls.py to add stats display
    - MEDIUM RISK: requires careful Streamlit caching (stats_lookup is large dict)

STEP 3: Bracket Fetch (Selection Sunday, 2026-03-15)
  - Run fetch_bracket.py — ESPN auto-fetch pipeline is already ready
  - Verify seeds.parquet covers 2026 season
  - Restart app with live bracket data
  - All UI enrichment and pool optimizer read from the refreshed bracket automatically
```

---

## Caching Architecture in Streamlit

The existing caching strategy in `src/ui/data_loader.py` must be extended carefully.
Streamlit has two cache types with different semantics:

| Cache Type | Use Case | How to Hash | Existing Uses |
|------------|----------|-------------|---------------|
| `@st.cache_resource` | Objects that are expensive to create and should be shared across sessions (models, DB connections) | Not hashed — one copy per worker | `load_model()`, `build_ensemble_predict_fn()` |
| `@st.cache_data` | Pure functions with serializable inputs/outputs | Hashed by args | `run_deterministic()`, `run_monte_carlo()`, `load_team_info()` |

**New caching decisions:**

- `load_stats_lookup_cached(season)`: Use `@st.cache_data`. The stats lookup is a large
  dict but is fully serializable. Season is the only cache key dimension needed.

- `compute_pool_strategy_cached(mc_result_hash, field_size)`: Use `@st.cache_data` with
  a custom `hash_funcs` for the mc_result dict (same pattern as `run_monte_carlo()` which
  uses `hash_funcs={dict: lambda d: str(sorted(d.items()))}`).

- `load_seed_matchup_history(seed_a, seed_b)`: Use `@st.cache_data`. Both args are
  integers — simple to cache without hash_funcs.

- `build_matchup_context(team_a_id, team_b_id, season, stats_lookup)`: The `stats_lookup`
  argument is an unhashable large dict. Use underscore-prefix convention
  (`_stats_lookup`) to exclude it from hashing, same as `_artifact` in
  `build_ensemble_predict_fn()`.

---

## Session State Extensions

The existing `st.session_state` has two keys:
- `"season"` — current season year (int)
- `"override_map"` — `{slot_id: team_id}` dict

v1.1 adds no required new session state keys. The pool optimizer parameters
(field_size, scoring system) can live as local widget state or be added to session_state
if persistence across reruns is desired. Recommend starting with local state and promoting
to session_state if user feedback requests it.

---

## Architecture Anti-Patterns to Avoid in v1.1

### Anti-Pattern 1: Re-running simulation inside the pool optimizer

The pool optimizer must consume `mc_result["advancement_probs"]` that is already cached
from `run_monte_carlo()`. It must NOT call `simulate_bracket()` internally. The 10K run
Monte Carlo takes ~0.2s — running it a second time per page load would be wasted work and
would produce different random seeds unless coordinated.

### Anti-Pattern 2: Loading stats_lookup twice

`build_stats_lookup()` reads Parquet files and iterates over merged DataFrames — it takes
~100-200ms. It is currently loaded once inside `build_ensemble_predict_fn()` (via
`@st.cache_resource`) and once potentially in `matchup_context.py`. The solution is to use
`load_stats_lookup_cached()` as the single call site and pass it everywhere. Do NOT call
`build_stats_lookup()` from inside matchup rendering callbacks.

### Anti-Pattern 3: Direct DuckDB calls in Streamlit widget callbacks

Override callbacks (`_make_override_callback()`) run synchronously on every interaction.
Historical seed queries via DuckDB must be pre-cached with `@st.cache_data` and called
at render time, not inside callbacks. Callbacks should only update `session_state`.

### Anti-Pattern 4: Retraining in the Streamlit process

Model retraining (`build_ensemble()`) takes 30-120 seconds and modifies disk artifacts.
This must never be triggered from the Streamlit app. Keep retraining as a separate CLI
script (`scripts/retrain.py`). The app reads `models/ensemble.joblib` via
`@st.cache_resource` — clearing that cache on app restart picks up the new artifact.

### Anti-Pattern 5: Breaking the predict_fn interface

`predict_fn(team_a_id: int, team_b_id: int) -> float` is the boundary between the Feature
Store and Bracket Simulator layers. Every downstream component (simulate_bracket, backtest,
app.py) depends on this single callable interface. Model retraining must produce an artifact
that wraps into this same interface. Do not add new arguments to predict_fn.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Integration points | HIGH | Derived from direct code audit — no assumptions |
| Pool optimizer algorithm | MEDIUM | EV calculation approach is standard; field pick pct estimation is approximate |
| Caching strategy | HIGH | Follows existing patterns in data_loader.py precisely |
| Build order | HIGH | Dependency graph is clear from code imports |
| Data availability for retraining | LOW | cbbdata 2025-26 data not yet indexed as of 2026-03-13; archive fallback behavior is a known limitation documented in cbbdata_client.py |

---

## Sources

- Direct codebase audit: all files in `src/`, `app.py` (HIGH confidence, first-party)
- `src/ui/data_loader.py` — Streamlit caching patterns (HIGH)
- `src/simulator/simulate.py` — mc_result output contract (HIGH)
- `src/models/features.py` — stats_lookup structure (HIGH)
- `src/models/ensemble.py` — TwoTierEnsemble retraining flow (HIGH)
- `src/ingest/cbbdata_client.py` — data availability constraints for 2025-26 season (HIGH)
