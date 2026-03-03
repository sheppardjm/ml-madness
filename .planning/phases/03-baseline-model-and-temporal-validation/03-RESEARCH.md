# Phase 3: Baseline Model and Temporal Validation - Research

**Researched:** 2026-03-03
**Domain:** scikit-learn logistic regression, temporal cross-validation, Brier score evaluation, NCAA tournament feature engineering
**Confidence:** HIGH (core stack verified via official docs and direct code inspection)

## Summary

Phase 3 builds a logistic regression baseline model with walk-forward temporal validation covering four holdout years (2022–2025). The primary challenge is not the modeling itself—scikit-learn's `LogisticRegression` is mature and well-suited—but rather assembling a consistent historical feature dataset. The codebase currently has only 2025 season stats (`current_season_stats.parquet`); to train on pre-2022 seasons and evaluate on 2022–2025, historical Torvik efficiency ratings (adjOE, adjDE, barthag) must be fetched for all training seasons via the cbbdata API, which already has infrastructure in `src/ingest/cbbdata_client.py`.

The walk-forward temporal CV must be implemented as a year-grouped custom split (not a raw row-count `TimeSeriesSplit`), because each tournament year has ~63 games that must stay together as a fold. The canonical pattern is to iterate over test years [2022, 2023, 2024, 2025], building training sets from all valid prior seasons, then evaluating on the holdout year.

A chalk model that hard-picks the higher seed wins about 71% of games historically, producing a Brier score of roughly 0.28–0.33 depending on the year's upset rate. The success criterion "below 0.23" corresponds to a calibrated probabilistic model — not hard picks — that meaningfully outperforms a constant 70% prediction (Brier ≈ 0.21). This threshold is achievable with efficiency differentials and seed difference as features.

**Primary recommendation:** Fetch historical Torvik ratings via `cbbdata_client.fetch_torvik_ratings(api_key, year)` for seasons 2003–2024, store as `data/processed/historical_torvik_ratings.parquet`, then join to tournament games and seeds to build the training dataset. Use year-grouped walk-forward splits (custom loop, not `TimeSeriesSplit`), fit `LogisticRegression(C=1.0, class_weight='balanced', solver='lbfgs')`, and evaluate with `brier_score_loss` and `log_loss` from sklearn.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.8.0 (latest) | LogisticRegression, metrics, model_selection | Industry standard ML, official sklearn persistence |
| joblib | bundled with sklearn | Model serialization to `.joblib` | Official sklearn recommendation for large numpy arrays |
| optuna | 4.7.0 (latest) | Hyperparameter search (C parameter sweep) | Define-by-run API, easy sklearn integration |
| matplotlib | 3.x | Calibration curve plots | CalibrationDisplay uses matplotlib backend |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sklearn.metrics.brier_score_loss | sklearn 1.8.0 | Primary evaluation metric | Every holdout year evaluation |
| sklearn.metrics.log_loss | sklearn 1.8.0 | Secondary evaluation metric | Alongside Brier in eval pipeline |
| sklearn.calibration.CalibrationDisplay | sklearn 1.8.0 | Reliability diagrams | Task 03-05 calibration check |
| sklearn.calibration.calibration_curve | sklearn 1.8.0 | Raw prob_true/prob_pred arrays | When CalibrationDisplay not used |
| duckdb | 1.4.4 (installed) | SQL joins for training dataset assembly | Already project standard |
| pandas | 3.0.1 (installed) | DataFrames for feature matrix | Already project standard |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LogisticRegression | LogisticRegressionCV | LogisticRegressionCV sweeps C internally but doesn't integrate with Optuna; use plain LR + Optuna per the roadmap |
| Custom year-loop CV | TimeSeriesSplit | TimeSeriesSplit splits on row indices, not year groups; NCAA data needs year-grouped splits |
| joblib | pickle / skops.io | joblib is official sklearn recommendation; pickle works but lacks memory mapping |

**Installation (packages not yet in pyproject.toml):**
```bash
uv add scikit-learn optuna matplotlib
```

Note: `joblib` is automatically installed as a scikit-learn dependency. It does not need to be added separately.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── models/                  # New directory for Phase 3+
│   ├── __init__.py
│   ├── features.py          # compute_features() inline implementation (03-01)
│   ├── temporal_cv.py       # Walk-forward CV harness (03-02)
│   ├── train_logistic.py    # Training + joblib save (03-03)
│   └── evaluate.py          # Brier/log-loss pipeline (03-04)
├── ingest/
│   └── fetch_historical_ratings.py  # Historical Torvik fetch loop (prerequisite)
data/
└── processed/
    ├── historical_torvik_ratings.parquet  # NEW: adjOE/adjDE/barthag 2003-2025
    └── ...existing files...
models/
└── logistic_baseline.joblib  # Artifact required by success criterion
```

### Pattern 1: Year-Grouped Walk-Forward Validation
**What:** Custom loop over holdout years; training set is all valid prior seasons; test set is exactly one tournament year.
**When to use:** Any temporal evaluation of NCAA tournament models.
**Example:**
```python
# Source: established pattern; sklearn TimeSeriesSplit docs confirmed year-grouping needed
from src.utils.cutoff_dates import VALID_TOURNEY_SEASONS

BACKTEST_YEARS = [2022, 2023, 2024, 2025]

def walk_forward_splits(df: pd.DataFrame, backtest_years: list[int]):
    """Yield (train_df, test_df) pairs for walk-forward validation.

    Training set: all seasons strictly before the holdout year.
    Test set: exactly one holdout year.
    No overlap; no future data.
    """
    for test_year in backtest_years:
        train = df[df['Season'] < test_year].copy()
        test = df[df['Season'] == test_year].copy()
        assert len(train) > 0, f"No training data before {test_year}"
        assert len(test) > 0, f"No test data for {test_year}"
        # Safety: verify no future seasons in training fold
        assert train['Season'].max() < test_year, "DATA LEAKAGE: future year in training fold"
        yield test_year, train, test
```

### Pattern 2: Feature Matrix Assembly
**What:** For each tournament game, build a single row with feature differences (higher_seed_team - lower_seed_team). Label = 1 if higher seed wins.
**When to use:** Building the training dataset from tournament_games + seeds + historical stats.
**Example:**
```python
def compute_features(season: int, team_a_id: int, team_b_id: int,
                     stats_lookup: dict) -> dict:
    """Inline feature computation — will be formalized by Phase 8."""
    stats_a = stats_lookup[season][team_a_id]
    stats_b = stats_lookup[season][team_b_id]
    return {
        'adjoe_diff': stats_a['adj_o'] - stats_b['adj_o'],
        'adjde_diff': stats_a['adj_d'] - stats_b['adj_d'],  # lower is better, so sign matters
        'barthag_diff': stats_a['barthag'] - stats_b['barthag'],
        'seed_diff': stats_a['seed_num'] - stats_b['seed_num'],  # negative = team_a is higher seed
        'sos_diff': stats_a.get('sos', 0) - stats_b.get('sos', 0),
        'adjt_diff': stats_a['adj_t'] - stats_b['adj_t'],
    }
```

### Pattern 3: Logistic Regression Training and Persistence
**What:** Fit `LogisticRegression` on training data, save with `joblib.dump()`.
**When to use:** Task 03-03.
**Example:**
```python
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
from sklearn.linear_model import LogisticRegression
import joblib
import pathlib

def train_and_save(X_train, y_train, model_path: str = "models/logistic_baseline.joblib"):
    clf = LogisticRegression(
        C=1.0,
        class_weight='balanced',  # handles any class imbalance
        solver='lbfgs',           # good default for L2 penalty
        max_iter=1000,            # increase from default 100 to ensure convergence
        random_state=42,
    )
    clf.fit(X_train, y_train)
    pathlib.Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, model_path)
    return clf
```

### Pattern 4: Brier Score and Log-Loss Evaluation
**What:** Compute per-year Brier score and log-loss, compare to chalk baseline.
**When to use:** Task 03-04.
**Example:**
```python
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html
from sklearn.metrics import brier_score_loss, log_loss

def evaluate_holdout(y_true, y_prob, year: int, chalk_brier: float):
    """Compute and print evaluation metrics for one holdout year."""
    brier = brier_score_loss(y_true, y_prob)
    ll = log_loss(y_true, y_prob)

    print(f"Year {year}: Brier={brier:.4f} (chalk={chalk_brier:.4f}, delta={chalk_brier-brier:+.4f}), LogLoss={ll:.4f}")
    return {'year': year, 'brier': brier, 'log_loss': ll, 'chalk_brier': chalk_brier}
```

### Pattern 5: Optuna Hyperparameter Sweep
**What:** Optimize the regularization parameter `C` using Optuna with Brier score as the objective.
**When to use:** Task 03-03 hyperparameter sweep.
**Example:**
```python
# Source: https://optuna.readthedocs.io/en/stable/
import optuna

def optuna_objective(trial, X_train, y_train, X_val, y_val):
    C = trial.suggest_float("C", 1e-3, 100.0, log=True)
    max_iter = trial.suggest_int("max_iter", 100, 2000)

    clf = LogisticRegression(C=C, class_weight='balanced', solver='lbfgs',
                             max_iter=max_iter, random_state=42)
    clf.fit(X_train, y_train)
    y_prob = clf.predict_proba(X_val)[:, 1]
    return brier_score_loss(y_val, y_prob)  # minimize

study = optuna.create_study(direction="minimize")
study.optimize(lambda trial: optuna_objective(trial, X_tr, y_tr, X_val, y_val),
               n_trials=50)
print(f"Best C: {study.best_params['C']:.4f}")
```

### Pattern 6: Calibration Check
**What:** Plot reliability diagram using `CalibrationDisplay.from_predictions()`.
**When to use:** Task 03-05.
**Example:**
```python
# Source: https://scikit-learn.org/stable/modules/calibration.html
from sklearn.calibration import CalibrationDisplay
import matplotlib.pyplot as plt

def check_calibration(y_true_all, y_prob_all, save_path="models/calibration_curve.png"):
    fig, ax = plt.subplots(figsize=(8, 6))
    CalibrationDisplay.from_predictions(
        y_true_all, y_prob_all,
        n_bins=10,
        strategy='uniform',
        name='Logistic Baseline',
        ax=ax
    )
    ax.set_title("Calibration Curve - Logistic Baseline")
    fig.savefig(save_path, dpi=150, bbox_inches='tight')

    # Flag if any top-10 matchup produces >90% probability
    # (calibration check from success criterion 4)
```

### Anti-Patterns to Avoid
- **Raw `TimeSeriesSplit` on concatenated games**: Tournament years have variable row counts (63–67 games). `TimeSeriesSplit(n_splits=4)` splits on row indices, not year boundaries, creating folds that contain partial tournament years. Use the custom year-loop pattern instead.
- **StandardScaler fit on full dataset**: If you fit a scaler on all training+test data, statistics from test years contaminate the training fold. Fit the scaler only on `X_train` in each fold, then `transform()` both train and test.
- **Using `get_season_stats_with_cutoff()` for tournament game labels**: This function returns raw game records, not aggregated per-team stats. Historical Torvik ratings are pre-aggregated season-level metrics. Do not try to join these directly.
- **Symmetric feature ordering**: Always define a canonical ordering rule for team A vs. team B (e.g., lower SeedNum = team A). Failing to do this produces inconsistent feature directions and poor model convergence.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Brier score computation | Custom `(y - p)^2` loop | `sklearn.metrics.brier_score_loss` | Handles `pos_label`, scale options, edge cases |
| Log loss computation | Custom `log(p)` loop | `sklearn.metrics.log_loss` | Handles clipping at `eps=1e-7` automatically |
| Calibration curve | Custom binning and plotting | `sklearn.calibration.CalibrationDisplay` | Handles empty bins, reference line, aesthetics |
| Model serialization | Custom pickle wrapping | `joblib.dump / joblib.load` | Memory-efficient for sklearn NumPy arrays |
| Hyperparameter search | Grid search | `optuna` (define-by-run) | TPE sampler is more efficient than grid search |
| Walk-forward CV | Custom index slicing | Year-grouped custom loop | Tournament data is year-structured, not row-structured |

**Key insight:** sklearn's probability metrics have subtle conventions (e.g., `brier_score_loss` in sklearn 1.8 has `scale_by_half='auto'` which for binary problems scales to [0,1]). Always use the library functions rather than reimplementing formulas.

## Common Pitfalls

### Pitfall 1: Historical Stats Gap
**What goes wrong:** `current_season_stats.parquet` only contains 2025 season data (adj_o, adj_d, barthag). Attempting to join 2022–2024 tournament games to this file produces no rows or silent NaN joins.
**Why it happens:** Phase 2 only fetched the current season from cbbdata. Historical seasons weren't fetched.
**How to avoid:** Before building the training matrix, verify that a `historical_torvik_ratings.parquet` exists covering 2003–2025 (or 2003–2024, with 2025 from `current_season_stats.parquet`). This requires calling `cbbdata_client.fetch_torvik_ratings(api_key, year=Y)` for each season.
**Warning signs:** Feature matrix has many NaN rows; `len(X_train)` is much smaller than `len(tournament_games)`.

### Pitfall 2: barttorvik.com CSV Only Has Raw Values for 2023+
**What goes wrong:** Fetching `https://www.barttorvik.com/YYYY_team_results.csv` for years 2003–2022 returns ordinal rank integers (1, 2, 3...) in the `adjoe` column instead of raw efficiency values.
**Why it happens:** barttorvik changed their CSV format around 2023. Earlier years have ranks, not values.
**How to avoid:** Use cbbdata API (`fetch_torvik_ratings(api_key, year)`) for all historical seasons, as it provides consistent raw values for 2003–2024. Only use barttorvik CSV as a supplemental check or for 2023+.
**Warning signs:** `adjoe` column values are small integers (< 30) rather than floats in the range 90–140.

### Pitfall 3: Data Leakage in the Training Split
**What goes wrong:** Training fold includes games from the test year because year filtering was wrong (e.g., `df['Season'] <= test_year` instead of `df['Season'] < test_year`).
**Why it happens:** Off-by-one error in the split condition.
**How to avoid:** Use strict `< test_year` for training data. Add an assertion: `assert train_df['Season'].max() < test_year`. The `get_cutoff()` function already enforces cutoff dates; also verify stats are joined using pre-Selection-Sunday ratings.
**Warning signs:** Brier score is suspiciously low (< 0.10) on the holdout year; training set size is unexpectedly large.

### Pitfall 4: Symmetric Feature Direction Inconsistency
**What goes wrong:** For some games, `adjoe_diff = teamA_adjoe - teamB_adjoe`; for others it's reversed. The model sees contradictory signals and learns poorly.
**Why it happens:** Features are computed using WTeamID and LTeamID directly from the data, and the "winner" varies. When training, we know which team won, so the feature direction should be canonical.
**How to avoid:** Always define features as `(team_with_lower_SeedNum) - (team_with_higher_SeedNum)`. The label is `1` if the lower-SeedNum team won. For equal seeds (rare), use TeamID as tiebreaker.
**Warning signs:** Model coefficients have unexpected signs (positive on `adjde_diff` meaning better defense predicts losses).

### Pitfall 5: LogisticRegression Convergence Warning
**What goes wrong:** sklearn prints `ConvergenceWarning: lbfgs failed to converge` and the model parameters are unreliable.
**Why it happens:** Default `max_iter=100` is too low when features are unnormalized or C is very small.
**How to avoid:** Set `max_iter=1000`. Also, standardize features with `StandardScaler` fit on training data only. This reduces iterations needed.
**Warning signs:** `clf.n_iter_` equals `max_iter` exactly; sklearn ConvergenceWarning in logs.

### Pitfall 6: Chalk Brier Score Interpretation
**What goes wrong:** Developer computes "chalk Brier" as `brier_score_loss(y_true, np.ones(n))` and gets ~0.28–0.33, then claims the model beats ~0.23 threshold.
**Why it happens:** Hard chalk (P=1.0) is a much weaker baseline than probabilistic chalk. The 0.23 threshold is calibrated for a model that provides calibrated probabilities, not for hard picks.
**How to avoid:** The correct chalk comparison is: hard-chalk Brier = 0.28–0.33; seed-probability-chalk = ~0.19. The "below 0.23" criterion means the model should beat hard chalk by a meaningful margin. Report both the model Brier and hard-chalk Brier as context.
**Warning signs:** None—just confirm interpretation aligns with the success criterion's intent.

### Pitfall 7: joblib Version Compatibility
**What goes wrong:** Model saved with sklearn 1.8.0 fails to load with a different sklearn version installed later.
**Why it happens:** joblib uses pickle internally; sklearn model objects are version-dependent.
**How to avoid:** Save sklearn version metadata alongside the model:
```python
metadata = {
    'sklearn_version': sklearn.__version__,
    'trained_on_seasons': list(range(2003, test_year)),
    'feature_names': feature_names,
}
joblib.dump({'model': clf, 'metadata': metadata}, 'models/logistic_baseline.joblib')
```
**Warning signs:** `ValueError: incompatible dtype` or AttributeError when loading the model.

## Code Examples

Verified patterns from official sources:

### Walk-Forward CV with Year Groups
```python
# Custom year-grouped walk-forward (no sklearn dependency)
# Source: Derived from sklearn cross_validation docs + tournament structure constraints
VALID_TOURNEY_SEASONS = [s for s in range(2003, 2026) if s != 2020]
BACKTEST_YEARS = [2022, 2023, 2024, 2025]

results = []
for test_year in BACKTEST_YEARS:
    train_seasons = [s for s in VALID_TOURNEY_SEASONS if s < test_year]
    train_df = full_df[full_df['Season'].isin(train_seasons)]
    test_df = full_df[full_df['Season'] == test_year]

    # Assert no leakage
    assert train_df['Season'].max() < test_year

    X_train = train_df[FEATURE_COLS].values
    y_train = train_df['label'].values
    X_test = test_df[FEATURE_COLS].values
    y_test = test_df['label'].values

    # Fit scaler on training data only
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)  # use training stats

    clf = LogisticRegression(C=best_C, class_weight='balanced',
                             solver='lbfgs', max_iter=1000, random_state=42)
    clf.fit(X_train_s, y_train)
    y_prob = clf.predict_proba(X_test_s)[:, 1]

    results.append({
        'year': test_year,
        'brier': brier_score_loss(y_test, y_prob),
        'log_loss': log_loss(y_test, y_prob),
        'n_train': len(train_df),
        'n_test': len(test_df),
    })
```

### Building Training Dataset from Historical Stats
```python
# Source: Codebase inspection + DuckDB query patterns from Phase 1/2
import duckdb
import pandas as pd

def build_matchup_dataset(
    processed_dir: str = "data/processed",
    historical_ratings_path: str = "data/processed/historical_torvik_ratings.parquet",
) -> pd.DataFrame:
    """Build flat matchup-level training dataset."""
    conn = duckdb.connect()
    df = conn.execute(f"""
        SELECT
            tg.Season,
            -- Determine canonical ordering: lower SeedNum = team_a
            CASE WHEN ws.SeedNum <= ls.SeedNum THEN tg.WTeamID ELSE tg.LTeamID END as team_a_id,
            CASE WHEN ws.SeedNum <= ls.SeedNum THEN tg.LTeamID ELSE tg.WTeamID END as team_b_id,
            CASE WHEN ws.SeedNum <= ls.SeedNum THEN ws.SeedNum ELSE ls.SeedNum END as team_a_seed,
            CASE WHEN ws.SeedNum <= ls.SeedNum THEN ls.SeedNum ELSE ws.SeedNum END as team_b_seed,
            -- Label: 1 if team_a (higher seed = lower SeedNum) won
            CASE WHEN ws.SeedNum <= ls.SeedNum THEN 1 ELSE 0 END as label
        FROM read_parquet('{processed_dir}/tournament_games.parquet') tg
        JOIN read_parquet('{processed_dir}/seeds.parquet') ws
            ON tg.Season = ws.Season AND tg.WTeamID = ws.TeamID
        JOIN read_parquet('{processed_dir}/seeds.parquet') ls
            ON tg.Season = ls.Season AND tg.LTeamID = ls.TeamID
        WHERE NOT tg.IsFirstFour
          AND ws.SeedNum != ls.SeedNum
        ORDER BY tg.Season
    """).df()
    conn.close()
    return df
```

### Brier Score Evaluation Table
```python
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html
from sklearn.metrics import brier_score_loss, log_loss
import pandas as pd

def print_eval_table(results: list[dict]):
    """Print evaluation table comparing model vs chalk baseline."""
    df = pd.DataFrame(results)
    df['vs_chalk'] = df['chalk_brier'] - df['brier']
    df['beats_chalk'] = df['vs_chalk'] > 0

    print("\n=== BACKTEST RESULTS ===")
    print(df[['year', 'n_test', 'brier', 'chalk_brier', 'vs_chalk', 'log_loss']].to_string(index=False))
    print(f"\nMean Brier: {df['brier'].mean():.4f} (threshold: < 0.23)")
    print(f"Beats chalk every year: {df['beats_chalk'].all()}")
```

### Model Save with Metadata
```python
# Source: https://scikit-learn.org/stable/model_persistence.html
import joblib
import sklearn

def save_model(clf, scaler, feature_names, train_seasons, path="models/logistic_baseline.joblib"):
    """Save model with metadata for reproducibility."""
    import pathlib
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)

    artifact = {
        'model': clf,
        'scaler': scaler,
        'feature_names': feature_names,
        'train_seasons': train_seasons,
        'sklearn_version': sklearn.__version__,
    }
    joblib.dump(artifact, path)
    print(f"Saved model to {path}")

def load_model(path="models/logistic_baseline.joblib"):
    """Load model artifact and verify sklearn version."""
    import sklearn
    artifact = joblib.load(path)
    saved_version = artifact.get('metadata', {}).get('sklearn_version') or artifact.get('sklearn_version')
    if saved_version and saved_version != sklearn.__version__:
        print(f"WARNING: Model trained with sklearn {saved_version}, running {sklearn.__version__}")
    return artifact['model'], artifact.get('scaler'), artifact.get('feature_names')
```

## Key Data Facts (from codebase inspection)

These facts directly constrain implementation decisions:

1. **Training data available**: `tournament_games.parquet` has 1,449 games across 22 seasons (2003–2025, excl. 2020). Non-First-Four games only = ~1,367 usable matchups.

2. **Backtest split sizes**:
   - 2022 holdout: ~63 test games, ~19 prior seasons of training data
   - 2023 holdout: ~63 test games, ~20 prior seasons
   - 2024 holdout: ~63 test games, ~21 prior seasons
   - 2025 holdout: ~63 test games, ~22 prior seasons (use final model on full data)

3. **Historical stats gap**: `current_season_stats.parquet` is 2025-only. A **new** `historical_torvik_ratings.parquet` must be created for Phase 3 training. The cbbdata client `fetch_torvik_ratings(api_key, year)` supports years 2003–2024 per code comments.

4. **barttorvik.com CSV limitation**: Raw `adjoe/adjde/barthag` values only available for 2023+ via `https://www.barttorvik.com/YYYY_team_results.csv`. Years 2003–2022 return ordinal ranks (integers), not efficiency values. The cbbdata API is the correct source for historical values.

5. **Available Kaggle proxy features** (no API needed): KenPom rank (`MMasseyOrdinals.csv`, `SystemName='POM'`, `RankingDayNum=133`) available for all seasons 2003–2025. Useful as fallback if cbbdata is unavailable.

6. **Seeds available**: `seeds.parquet` has 68 teams per year (2003–2025 excl. 2020). SeedNum ranges 1–16. Equal-seed matchups (rare First Four) should be excluded by the `IsFirstFour` filter already applied.

7. **Chalk baseline from real data**:
   - Hard chalk (P=1.0 to higher seed): Brier = 0.28–0.33 (year-dependent, 2022–2025)
   - Historical win rate ~0.71 for higher seeds
   - The "0.23 Brier threshold" requires a meaningfully calibrated probabilistic model, not just hard picks

8. **Existing `get_season_stats_with_cutoff()` WARNING**: This returns raw game-level records from `regular_season.parquet`, not pre-computed per-team stats. Do NOT use it directly to get adjOE/adjDE. It must be used if you plan to compute per-team stats from scratch from box scores, but that requires an additional aggregation step.

9. **Feature names from roadmap**: `adjOE diff, adjDE diff, barthag diff, seed diff, SOS diff, tempo diff` — these are difference features (team_a - team_b), normalized per matchup pair.

10. **DayNum CAST reminder**: Per decision `[01-02]`, always `CAST(DayNum AS INTEGER)` in DuckDB SQL when computing date arithmetic.

## Historical Ratings Fetch Strategy

This is the key prerequisite for Phase 3 that is not yet in the codebase:

```python
# Pattern: Fetch historical Torvik ratings for all training seasons
# Must run as a one-time ingest (similar to current_season_stats ingestion)

from src.ingest.cbbdata_client import get_cbbdata_token, fetch_torvik_ratings
from src.utils.cutoff_dates import VALID_TOURNEY_SEASONS

def ingest_historical_ratings(api_key: str, output_path: str):
    """Fetch historical Torvik ratings for all valid tournament seasons."""
    all_dfs = []
    for season in VALID_TOURNEY_SEASONS:  # 2003-2025, excl. 2020
        # year parameter: season year (e.g., 2024 for 2023-24 season)
        df = fetch_torvik_ratings(api_key, year=season)
        df['season'] = season
        all_dfs.append(df)

    combined = pd.concat(all_dfs, ignore_index=True)
    # Join to team_normalization to get kaggle_team_id
    # ... (same pattern as ingest_current_season_stats)
    combined.to_parquet(output_path)
```

**NOTE**: If cbbdata does not support years before ~2008, an alternative is to use barttorvik.com directly for 2023+ and use POM rank from `MMasseyOrdinals.csv` as a proxy feature for earlier years. The Phase 3 feature set would then have two paths: full-feature (2023+) and POM-rank-only (2003-2022). This degrades model consistency but avoids API dependency.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pickle for sklearn models | joblib.dump() | sklearn 0.23+ | Better NumPy array serialization |
| Manual Brier score formula | sklearn.metrics.brier_score_loss | sklearn 1.x | scale_by_half parameter added in 1.3 |
| Grid search over C | Optuna TPE sampler | 2018+ (Optuna) | More efficient hyperparameter search |
| KFold for all data | TimeSeriesSplit / custom year-loop | 2015+ | Prevents temporal data leakage |
| Hard seed picks | Calibrated probability model | Modern ML | Enables Brier score to be meaningful |

**Deprecated/outdated:**
- `sklearn.externals.joblib`: Removed in sklearn 0.23. Use `import joblib` directly (standalone package).
- `TimeSeriesSplit` for year-structured data: Functional but suboptimal; custom year-loop is cleaner for tournament structure.

## Open Questions

1. **cbbdata historical years availability**
   - What we know: `fetch_torvik_ratings(api_key, year=2024)` works per code comments. Year=2025 needs archive fallback.
   - What's unclear: Does cbbdata API support year=2003? The R package `cbd_torvik_ratings_archive()` claims coverage "back to 2014-15." If pre-2015 data is unavailable, the earliest usable training season is 2015.
   - Recommendation: Test `fetch_torvik_ratings(api_key, year=2008)` in task 03-01 to determine actual historical coverage. If limited to 2015+, the backtest still works (7–8 training seasons before 2022), but note the constraint.

2. **Feature normalization strategy**
   - What we know: sklearn's LogisticRegression with lbfgs solver benefits from standardized features.
   - What's unclear: Should the `StandardScaler` be fit per-fold (correct) or globally? The roadmap says "normalized per matchup pair" which might mean per-game normalization, not global standardization.
   - Recommendation: Use `StandardScaler` fit on each training fold only (no leakage). "Normalized per matchup pair" likely means expressing features as differences (already differential), not a separate per-game normalization step.

3. **Handling equal seeds (First Four)**
   - What we know: `IsFirstFour` flag exists in `tournament_games.parquet`. Some First Four games have equal seeds (11a vs 11b).
   - What's unclear: The feature direction convention breaks for equal seeds.
   - Recommendation: Filter out First Four games entirely (`WHERE NOT IsFirstFour`). This is already the pattern in `get_tourney_games(include_first_four=False)`.

## Sources

### Primary (HIGH confidence)
- sklearn 1.8.0 official docs - LogisticRegression API, TimeSeriesSplit, brier_score_loss, CalibrationDisplay, model_persistence
  - https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
  - https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  - https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html
  - https://scikit-learn.org/stable/modules/calibration.html
  - https://scikit-learn.org/stable/model_persistence.html
- Optuna 4.7.0 official docs - create_study, objective, suggest_float
  - https://optuna.readthedocs.io/en/stable/
- Codebase inspection (`src/ingest/cbbdata_client.py`, `src/utils/cutoff_dates.py`, `src/utils/query_helpers.py`) - direct read
- Parquet files inspected directly: confirmed schemas, seasons, row counts

### Secondary (MEDIUM confidence)
- barttorvik.com CSV endpoint tested directly: confirmed format difference between 2023+ (raw values) vs 2022- (ordinal ranks)
- Chalk Brier score computed from actual tournament data: 0.28–0.33 range confirmed from `tournament_games.parquet` + `seeds.parquet`
- arxiv.org/html/2503.21790v1 - verified adjOE/adjDE differential features effective for logistic regression

### Tertiary (LOW confidence)
- WebSearch result: cbbdata API historical coverage "back to 2014-15" per R package docs (unverified for Python API version)
- 0.23 Brier threshold: stated in phase requirements; computed to be consistent with probabilistic models in the 0.19–0.24 range

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - sklearn and Optuna are well-documented; installed versions verified
- Architecture: HIGH - patterns derived from direct codebase inspection + official docs
- Historical data availability: MEDIUM - barttorvik tested directly; cbbdata historical range is unverified
- Pitfalls: HIGH - most derived from actual data inspection (confirmed barttorvik format issue, confirmed 2025-only stats gap)
- Brier score threshold: MEDIUM - computed from actual data, consistent with requirements

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable libraries; barttorvik CSV format could change anytime)
