# Phase 6: Ensemble Models - Research

**Researched:** 2026-03-04
**Domain:** XGBoost, LightGBM, stacking ensemble, temporal cross-validation, probability calibration
**Confidence:** HIGH (live code execution, official docs, GitHub issue verification)

## Summary

Phase 6 adds XGBoost and LightGBM base models, stacks them with logistic regression as meta-learner, and calibrates the ensemble output. The goal is a lower multi-year Brier score than the logistic regression baseline (0.1900).

**Critical finding:** sklearn's `StackingClassifier` cannot be used directly with `walk_forward_splits()`. The `cross_val_predict` function inside `StackingClassifier.fit()` enforces a partition check — every row in X must appear in exactly one test fold. Our walk-forward splits leave 806 pre-2022 rows in no test fold, triggering `ValueError: cross_val_predict only works for partitions` (verified by live code execution; GitHub issue #32614, open as of November 2025, affects sklearn 1.4.x through 1.8.0). The correct approach is **manual OOF (out-of-fold) temporal stacking**: generate OOF predictions from each fold via `walk_forward_splits()`, train the meta-learner on those OOF predictions, then refit all base models on the full dataset. A thin wrapper class exposes `predict_proba()` for downstream use. This satisfies the spirit of the requirement (ensemble combining XGBoost, LightGBM, and logistic regression) without the incompatible sklearn API constraint.

**Key dataset facts:** 1054 total matchups, 17 seasons (2008–2025, no 2020). Walk-forward folds: 2022 (806 train, 63 test), 2023 (869/63), 2024 (932/62), 2025 (994/60). OOF meta-learner training set: 248 rows (sum of test folds). Label imbalance: 71.3% label=1 (favorites win), 28.7% label=0 (upsets). Per-fold scale_pos_weight for XGBoost: ~0.40 (consistent across folds).

**Primary recommendation:** Install `xgboost>=3.2.0` and `lightgbm>=4.6.0`, use manual OOF temporal stacking (not sklearn StackingClassifier), and apply ClippedCalibrator to ensemble output (consistent with Phase 3).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.2.0 | XGBClassifier base model | Current stable; sklearn-compatible API; predict_proba() |
| lightgbm | 4.6.0 | LGBMClassifier base model | Current stable; sklearn-compatible API; class_weight='balanced' |
| scikit-learn | 1.8.0 (installed) | LogisticRegression meta-learner; StandardScaler; brier_score_loss; calibration_curve | Already project standard |
| optuna | 4.7.0 (installed) | Hyperparameter search for XGB and LGB | Already project standard; same pattern as Phase 3 |
| joblib | bundled | Artifact serialization | Already project standard |
| matplotlib | 3.10.8 (installed) | Calibration curve plots | Already project standard |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sklearn.calibration.CalibrationDisplay | 1.8.0 | Calibration curve plot | Same as Phase 3 evaluate.py |
| sklearn.frozen.FrozenEstimator | 1.8.0 | Enable CalibratedClassifierCV on pre-fit model | Only if using sklearn calibration instead of ClippedCalibrator |
| numpy | project standard | Feature array operations | Throughout |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual OOF stacking | sklearn StackingClassifier | StackingClassifier raises ValueError with walk_forward_splits (partition check fails); manual OOF is correct and temporal |
| ClippedCalibrator on ensemble output | CalibratedClassifierCV(FrozenEstimator(ensemble)) | FrozenEstimator approach works in sklearn 1.8 but adds complexity; ClippedCalibrator is simpler and already established |
| Per-fold scale_pos_weight for XGBoost | Fixed class_weight | Scale_pos_weight varies slightly per fold (0.4066–0.4160); computing per fold is more accurate |
| LightGBM class_weight='balanced' | is_unbalance=True | Both work; class_weight='balanced' is more familiar from sklearn convention |

**Installation — add to pyproject.toml:**
```bash
uv add xgboost>=3.2.0 lightgbm>=4.6.0
```

## Architecture Patterns

### Recommended Project Structure

```
src/
├── models/
│   ├── train_logistic.py     # Existing: ClippedCalibrator, CLIP_LO, CLIP_HI
│   ├── train_xgboost.py      # New (06-01): run_optuna_sweep_xgb(), train_xgb_fold()
│   ├── train_lightgbm.py     # New (06-02): run_optuna_sweep_lgb(), train_lgb_fold()
│   └── ensemble.py           # New (06-03, 06-04): TwoTierEnsemble class, build_ensemble()
models/
├── logistic_baseline.joblib  # Existing
├── xgb_params.json           # New (06-01): best XGBoost hyperparams
├── lgb_params.json           # New (06-02): best LightGBM hyperparams
└── ensemble.joblib           # New (06-03): final ensemble artifact
```

### Pattern 1: XGBClassifier Configuration for Binary Classification

**What:** XGBoost for binary win probability prediction with class imbalance handling.
**When to use:** Training XGBClassifier in any fold.

```python
# Source: xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html
from xgboost import XGBClassifier

def build_xgb(params: dict, scale_pos_weight: float) -> XGBClassifier:
    """Build XGBClassifier with given hyperparams and class weight."""
    return XGBClassifier(
        n_estimators=params['n_estimators'],
        max_depth=params['max_depth'],
        learning_rate=params['learning_rate'],
        subsample=params['subsample'],
        colsample_bytree=params['colsample_bytree'],
        min_child_weight=params['min_child_weight'],
        reg_alpha=params.get('reg_alpha', 0),
        reg_lambda=params.get('reg_lambda', 1),
        scale_pos_weight=scale_pos_weight,   # n_neg/n_pos per fold
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
        n_jobs=1,              # avoid thread contention in Optuna parallel trials
        verbosity=0,           # suppress per-iteration output
    )
```

**Key notes:**
- `scale_pos_weight` = `(train_label == 0).sum() / (train_label == 1).sum()` — approximately 0.40 per fold
- `eval_metric='logloss'` is needed only if using `eval_set` for early stopping; omit otherwise
- `n_jobs=1` prevents thread thrashing when Optuna runs parallel trials
- `verbosity=0` silences XGBoost's per-round output

### Pattern 2: LGBMClassifier Configuration for Binary Classification

**What:** LightGBM for binary win probability prediction with class imbalance handling.
**When to use:** Training LGBMClassifier in any fold.

```python
# Source: lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMClassifier.html
from lightgbm import LGBMClassifier

def build_lgb(params: dict) -> LGBMClassifier:
    """Build LGBMClassifier with given hyperparams and balanced class weighting."""
    return LGBMClassifier(
        num_leaves=params['num_leaves'],
        n_estimators=params['n_estimators'],
        learning_rate=params['learning_rate'],
        min_child_samples=params['min_child_samples'],
        subsample=params['subsample'],
        colsample_bytree=params['colsample_bytree'],
        reg_alpha=params.get('reg_alpha', 0),
        reg_lambda=params.get('reg_lambda', 0),
        class_weight='balanced',   # handles 71/29 imbalance
        objective='binary',
        random_state=42,
        n_jobs=1,                  # avoid thread contention
        verbose=-1,                # suppress per-iteration output
    )
```

**Key notes:**
- `verbose=-1` silences LightGBM's per-round output (different from XGBoost's `verbosity=0`)
- `min_child_samples` is critical for small datasets; values 10–30 prevent overfitting
- `num_leaves` controls model complexity more directly than `max_depth` in LightGBM
- LightGBM leaf-wise growth can overfit small datasets; use `num_leaves` <= 31 for safety

### Pattern 3: Optuna Sweep for XGBoost (Same Pattern as Phase 3)

**What:** Optuna hyperparameter sweep using walk-forward temporal CV to find best XGBoost params.
**When to use:** 06-01 plan.

```python
# Source: Phase 3 pattern in src/models/train_logistic.py run_optuna_sweep()
import optuna
from sklearn.metrics import brier_score_loss
import numpy as np

def run_optuna_sweep_xgb(df: pd.DataFrame, n_trials: int = 50) -> dict:
    """Run Optuna sweep for XGBoost hyperparameters.

    Uses walk_forward_splits() (2022-2025) as evaluation folds.
    Returns best params dict minimizing mean Brier score.
    """
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 50, 300),
            'max_depth': trial.suggest_int('max_depth', 2, 6),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-4, 1.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1.0, 10.0, log=True),
        }

        fold_brier_scores = []
        for _year, train_df, test_df in walk_forward_splits(df):
            X_train, y_train = train_df[FEATURE_COLS].values, train_df['label'].values
            X_test, y_test = test_df[FEATURE_COLS].values, test_df['label'].values

            # StandardScaler: fit on train only
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Compute scale_pos_weight from training data
            scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())

            xgb = XGBClassifier(
                **params,
                scale_pos_weight=scale_pos_weight,
                objective='binary:logistic',
                random_state=42, n_jobs=1, verbosity=0,
            )
            xgb.fit(X_train_scaled, y_train)

            y_prob = xgb.predict_proba(X_test_scaled)[:, 1]
            fold_brier_scores.append(brier_score_loss(y_test, y_prob))

        return float(np.mean(fold_brier_scores))

    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=n_trials)
    return study.best_params
```

### Pattern 4: Optuna Sweep for LightGBM

**What:** Same structure as Pattern 3 but with LightGBM-specific hyperparameters.
**When to use:** 06-02 plan.

```python
# Source: Phase 3 pattern adapted for LightGBM
def run_optuna_sweep_lgb(df: pd.DataFrame, n_trials: int = 50) -> dict:
    """Run Optuna sweep for LightGBM hyperparameters."""
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            'num_leaves': trial.suggest_int('num_leaves', 10, 60),
            'n_estimators': trial.suggest_int('n_estimators', 50, 300),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'min_child_samples': trial.suggest_int('min_child_samples', 10, 30),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-4, 1.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-4, 10.0, log=True),
        }

        fold_brier_scores = []
        for _year, train_df, test_df in walk_forward_splits(df):
            X_train, y_train = train_df[FEATURE_COLS].values, train_df['label'].values
            X_test, y_test = test_df[FEATURE_COLS].values, test_df['label'].values

            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            lgb = LGBMClassifier(
                **params,
                class_weight='balanced',
                objective='binary',
                random_state=42, n_jobs=1, verbose=-1,
            )
            lgb.fit(X_train_scaled, y_train)

            y_prob = lgb.predict_proba(X_test_scaled)[:, 1]
            fold_brier_scores.append(brier_score_loss(y_test, y_prob))

        return float(np.mean(fold_brier_scores))

    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=n_trials)
    return study.best_params
```

### Pattern 5: Manual OOF Temporal Stacking

**What:** Generate OOF predictions from all 4 folds for each base model, train meta-learner on OOF, refit base models on full data.
**When to use:** 06-03 plan (replaces sklearn StackingClassifier).

```python
# Source: required because StackingClassifier raises ValueError with walk_forward_splits
from src.models.temporal_cv import walk_forward_splits, BACKTEST_YEARS

def build_ensemble(
    df: pd.DataFrame,
    xgb_params: dict,
    lgb_params: dict,
    lr_best_C: float,      # from Phase 3 artifact
) -> 'TwoTierEnsemble':
    """Build stacking ensemble via manual OOF temporal approach.

    Step 1: For each fold in walk_forward_splits, train XGB + LGB + LR on train_df,
            collect predict_proba() on test_df -> OOF predictions shape (248, 3).
    Step 2: Train LogisticRegression meta-learner on OOF predictions.
    Step 3: Refit all 3 base models on full df (all 1054 rows).
    Step 4: Return TwoTierEnsemble holding base models + meta-learner.
    """
    oof_xgb, oof_lgb, oof_lr, oof_labels = [], [], [], []

    for _year, train_df, test_df in walk_forward_splits(df):
        X_train, y_train = train_df[FEATURE_COLS].values, train_df['label'].values
        X_test = test_df[FEATURE_COLS].values
        y_test = test_df['label'].values

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # XGB base model (fold-specific)
        scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())
        xgb_fold = XGBClassifier(**xgb_params, scale_pos_weight=scale_pos_weight,
                                  objective='binary:logistic', random_state=42,
                                  n_jobs=1, verbosity=0)
        xgb_fold.fit(X_train_scaled, y_train)

        # LGB base model (fold-specific)
        lgb_fold = LGBMClassifier(**lgb_params, class_weight='balanced',
                                   objective='binary', random_state=42,
                                   n_jobs=1, verbose=-1)
        lgb_fold.fit(X_train_scaled, y_train)

        # LR base model (fold-specific)
        lr_fold = LogisticRegression(C=lr_best_C, class_weight='balanced',
                                      solver='lbfgs', max_iter=1000, random_state=42)
        lr_fold.fit(X_train_scaled, y_train)

        # Collect OOF predictions (class-1 probability for each base model)
        oof_xgb.extend(xgb_fold.predict_proba(X_test_scaled)[:, 1].tolist())
        oof_lgb.extend(lgb_fold.predict_proba(X_test_scaled)[:, 1].tolist())
        oof_lr.extend(ClippedCalibrator(lr_fold).predict_proba(X_test_scaled)[:, 1].tolist())
        oof_labels.extend(y_test.tolist())

    # Step 2: Meta-learner training on OOF predictions
    X_meta = np.column_stack([oof_xgb, oof_lgb, oof_lr])   # shape (248, 3)
    y_meta = np.array(oof_labels)
    meta_lr = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000, random_state=42)
    meta_lr.fit(X_meta, y_meta)

    # Step 3: Refit base models on FULL dataset
    full_scaler = StandardScaler()
    X_full = full_scaler.fit_transform(df[FEATURE_COLS].values)
    y_full = df['label'].values

    # ... fit xgb_final, lgb_final, lr_final on X_full, y_full ...

    # Step 4: Return ensemble
    return TwoTierEnsemble(
        scaler=full_scaler,
        xgb=xgb_final,
        lgb=lgb_final,
        lr_base=lr_final,
        meta_lr=meta_lr,
    )
```

### Pattern 6: TwoTierEnsemble Wrapper Class

**What:** sklearn-compatible wrapper with `predict_proba()` for ensemble inference.
**When to use:** All downstream consumers (backtest predict_fn, calibration).

```python
class TwoTierEnsemble:
    """Stacking ensemble: XGB + LGB + LR base models + LR meta-learner.

    Exposes predict_proba() compatible with ClippedCalibrator and backtest predict_fn.
    Holds its own scaler (fitted on full training data).

    Usage:
        p = ensemble.predict_proba(X_scaled)[:, 1]
        # or with built-in scaling:
        p = ensemble.predict_proba_raw(X_unscaled)[:, 1]
    """

    def __init__(self, scaler, xgb, lgb, lr_base, meta_lr,
                 clip_lo=CLIP_LO, clip_hi=CLIP_HI):
        self.scaler = scaler
        self.xgb = xgb
        self.lgb = lgb
        self.lr_base = lr_base
        self.meta_lr = meta_lr
        self.clip_lo = clip_lo
        self.clip_hi = clip_hi
        self.classes_ = np.array([0, 1])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict ensemble probabilities given ALREADY-SCALED feature array.

        Args:
            X: Scaled feature array (n_samples, 6).

        Returns:
            (n_samples, 2) array, column 1 = P(label=1).
        """
        p_xgb = self.xgb.predict_proba(X)[:, 1]
        p_lgb = self.lgb.predict_proba(X)[:, 1]
        # LR through ClippedCalibrator
        p_lr = ClippedCalibrator(self.lr_base).predict_proba(X)[:, 1]

        X_meta = np.column_stack([p_xgb, p_lgb, p_lr])
        p1 = self.meta_lr.predict_proba(X_meta)[:, 1]
        p1 = np.clip(p1, self.clip_lo, self.clip_hi)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])
```

### Pattern 7: Calibration (06-04)

**What:** Plot calibration curves before/after calibration, verify ensemble probabilities.
**When to use:** After building the ensemble, before backtest.

```python
# Source: same approach as evaluate.py check_calibration()
from sklearn.calibration import CalibrationDisplay, calibration_curve

def plot_calibration_curves(
    y_true: np.ndarray,
    y_prob_before: np.ndarray,
    y_prob_after: np.ndarray,
    save_path: str = 'models/ensemble_calibration_curve.png',
) -> None:
    """Plot before/after calibration curves for ensemble output.

    y_prob_before: raw OOF predictions from ensemble (unclipped meta-learner)
    y_prob_after:  clipped predictions from TwoTierEnsemble.predict_proba()
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    CalibrationDisplay.from_predictions(y_true, y_prob_before, n_bins=10,
                                         name='Before calibration', ax=axes[0])
    CalibrationDisplay.from_predictions(y_true, y_prob_after, n_bins=10,
                                         name='After calibration', ax=axes[1])
    # ... save figure ...
```

**Calibration strategy for Phase 6:**
- The meta-learner's outputs are inherently better calibrated than raw base model outputs (meta-LR squishes toward valid probabilities)
- Apply ClippedCalibrator [0.05, 0.89] to ensemble output (same as Phase 3) for consistency
- Plot calibration curves using OOF predictions (before = raw meta-LR output, after = clipped)
- Check max deviation per decile bin (success criterion: within 5pp of actual win rates)

### Pattern 8: Backtest Extension (06-05) — Per-Fold Ensemble

**What:** Extend `backtest()` to support `model='ensemble'` with full temporal isolation including meta-learner.
**When to use:** 06-05 plan.

```python
# Source: Phase 5 backtest.py + Phase 6 ensemble architecture
def build_fold_ensemble(
    test_year: int,
    df: pd.DataFrame,
    xgb_params: dict,
    lgb_params: dict,
    lr_best_C: float,
) -> tuple['TwoTierEnsemble', 'StandardScaler']:
    """Build a temporally isolated ensemble for one backtest year.

    Meta-learner is trained on OOF predictions from sub-folds within pre-year data.
    Sub-folds: last 3 available seasons before test_year.

    Args:
        test_year: The holdout year (2022-2025).
        df: Full matchup DataFrame.
        xgb_params: Best XGBoost params from Optuna sweep.
        lgb_params: Best LightGBM params from Optuna sweep.
        lr_best_C: Best C for logistic regression (from Phase 3 artifact).

    Returns:
        (ensemble, scaler) where ensemble has predict_proba() interface.
    """
    train_df = df[df['Season'] < test_year].copy()

    # Sub-years for meta-learner OOF: last 3 seasons in training data
    available_seasons = sorted(train_df['Season'].unique())
    meta_sub_years = available_seasons[-3:]   # e.g., [2018, 2019, 2021] for test_year=2022

    # Generate OOF predictions within pre-year data
    oof_xgb, oof_lgb, oof_lr, oof_labels = [], [], [], []
    for sub_year in meta_sub_years:
        sub_train = train_df[train_df['Season'] < sub_year]
        sub_test = train_df[train_df['Season'] == sub_year]
        # ... fit base models on sub_train, collect OOF on sub_test ...

    # Train meta-learner on sub-fold OOF predictions
    meta_lr = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000, random_state=42)
    meta_lr.fit(np.column_stack([oof_xgb, oof_lgb, oof_lr]), np.array(oof_labels))

    # Fit final base models on FULL pre-year training data
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(train_df[FEATURE_COLS].values)
    y_train = train_df['label'].values
    # ... fit xgb_final, lgb_final, lr_final ...

    ensemble = TwoTierEnsemble(scaler, xgb_final, lgb_final, lr_final, meta_lr)
    return ensemble, scaler
```

**Sub-years per test_year:**
- test_year=2022: sub-years=[2018, 2019, 2021] → ~186 OOF samples for meta-learner
- test_year=2023: sub-years=[2019, 2021, 2022] → ~187 OOF samples
- test_year=2024: sub-years=[2021, 2022, 2023] → ~187 OOF samples
- test_year=2025: sub-years=[2022, 2023, 2024] → ~188 OOF samples

### Pattern 9: Ensemble predict_fn for Backtest

**What:** Build a predict_fn closure from the fold-specific ensemble for use in bracket simulation.
**When to use:** 06-05 within the backtest year loop.

```python
# Source: Phase 5 backtest.py predict_fn pattern (extended for ensemble)
def make_ensemble_predict_fn(
    test_year: int,
    ensemble: 'TwoTierEnsemble',
    stats_lookup: dict,
) -> Callable[[int, int], float]:
    """Build predict_fn using fold-specific ensemble."""

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        try:
            features = compute_features(test_year, team_a_id, team_b_id, stats_lookup)
        except KeyError:
            return 0.5   # First Four missing team fallback

        x = np.array([features[col] for col in FEATURE_COLS]).reshape(1, -1)
        x_scaled = ensemble.scaler.transform(x)
        return float(ensemble.predict_proba(x_scaled)[0, 1])

    return predict_fn
```

### Pattern 10: Artifact Structure for Ensemble

**What:** What gets saved to `models/ensemble.joblib` for reproducibility and downstream use.

```python
# Source: analogous to models/logistic_baseline.joblib structure from Phase 3
artifact = {
    'model': 'ensemble',
    'xgb_params': xgb_params,                # best hyperparams from Optuna
    'lgb_params': lgb_params,                 # best hyperparams from Optuna
    'lr_best_C': lr_best_C,                   # from Phase 3 artifact
    'ensemble': ensemble,                      # TwoTierEnsemble object
    'scaler': full_scaler,                     # StandardScaler fitted on full data
    'feature_names': FEATURE_COLS,
    'clip_lo': CLIP_LO,                        # 0.05
    'clip_hi': CLIP_HI,                        # 0.89
    'train_seasons': sorted(df['Season'].unique().tolist()),
    'oof_brier_per_year': oof_brier_results,   # per-year Brier from OOF
    'sklearn_version': sklearn.__version__,
    'xgboost_version': xgboost.__version__,
    'lightgbm_version': lightgbm.__version__,
}
joblib.dump(artifact, 'models/ensemble.joblib')
```

### Anti-Patterns to Avoid

- **sklearn StackingClassifier with walk_forward_splits:** Raises `ValueError: cross_val_predict only works for partitions` because pre-2022 data (806 rows) never appears in any test fold. Verified by live code execution.
- **CalibratedClassifierCV with cv='prefit':** Removed in sklearn 1.8.0. Use `FrozenEstimator` wrapper instead if needed (verified by live code execution: `InvalidParameterError`).
- **XGBClassifier with class_weight='balanced':** XGBoost does NOT support `class_weight` like sklearn. Use `scale_pos_weight` instead (computed per fold as `n_neg/n_pos`).
- **Reusing the same scaler across folds:** Must fit StandardScaler on training data ONLY for each fold (same rule as Phase 3).
- **Early stopping without eval_set in Optuna:** If using early stopping, you must pass `eval_set` to `.fit()`. Without `eval_set`, `early_stopping_rounds` has no effect and XGBoost will warn. Simpler to optimize `n_estimators` as a hyperparameter instead.
- **Sharing one ensemble across all backtest folds:** The meta-learner must be re-trained per fold using only sub-fold OOF predictions from pre-year data. Using the full OOF meta-learner (trained on 2022-2025) for 2022 evaluation leaks future data.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Partition check bypass | Skip the check in cross_val_predict source | Manual OOF stacking (Pattern 5) | Source modification breaks upgrades; manual OOF is the correct pattern for temporal stacking |
| Calibration curves | Custom matplotlib calibration plot | `CalibrationDisplay.from_predictions()` from sklearn | Already used in evaluate.py; consistent output |
| Brier score computation | Custom loss function | `sklearn.metrics.brier_score_loss()` | Established pattern throughout codebase |
| Hyperparameter search | Grid search or random search | Optuna `create_study()` with `trial.suggest_*` | Already in pyproject.toml; same pattern as Phase 3 LR sweep |
| Temporal splits | Custom year-splitting logic | `walk_forward_splits()` from temporal_cv.py | Leakage-safe; consistent fold boundaries; already tested |

**Key insight:** Phase 6 is primarily a new model training layer over the existing Phase 3/5 infrastructure. The `walk_forward_splits()`, `ClippedCalibrator`, `build_matchup_dataset()`, and `backtest()` interfaces are unchanged. New code is the two Optuna sweeps, OOF stacking assembly, and the `TwoTierEnsemble` wrapper.

## Common Pitfalls

### Pitfall 1: sklearn StackingClassifier Partition Check Failure
**What goes wrong:** `StackingClassifier(cv=walk_forward_splits_object).fit(X, y)` raises `ValueError: cross_val_predict only works for partitions`.
**Why it happens:** `cross_val_predict` (called internally by `StackingClassifier.fit()`) checks `_check_is_permutation(test_indices, len(X))`. Our walk_forward_splits produce test folds for only 248 of 1054 rows; the remaining 806 pre-2022 rows are never in any test fold.
**How to avoid:** Use manual OOF temporal stacking (Pattern 5). Do not pass `walk_forward_splits` to `StackingClassifier`.
**Warning signs:** `ValueError: cross_val_predict only works for partitions` — confirmed by live execution.
**GitHub issue:** #32614 (open as of November 2025, affects sklearn 1.4.x–1.8.0).

### Pitfall 2: XGBoost class_weight Parameter
**What goes wrong:** `XGBClassifier(class_weight='balanced')` raises an error or silently ignores the parameter.
**Why it happens:** XGBoost uses `scale_pos_weight` (not `class_weight`) for class imbalance.
**How to avoid:** Compute `scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()` per fold (~0.40) and pass to `XGBClassifier`.
**Warning signs:** No error raised but class imbalance not handled; model predicts near 1.0 for all samples.

### Pitfall 3: LightGBM Overfitting on Small Dataset
**What goes wrong:** LightGBM achieves near-perfect training accuracy but poor test Brier score.
**Why it happens:** LightGBM's leaf-wise tree growth can memorize small training sets. The largest training fold has 994 games — manageable, but num_leaves=127 (default) is too expressive.
**How to avoid:** Constrain `num_leaves` to the range 10–60 in the Optuna search space. Set `min_child_samples` >= 10. Monitor train vs. test Brier gap during Optuna trials.
**Warning signs:** Optuna finds n_estimators=300 and num_leaves=60 as best params; training Brier << test Brier.

### Pitfall 4: Meta-Learner Training Data Size
**What goes wrong:** Meta-learner has only 248 OOF samples (4 years × ~62 games). LogisticRegression with default C=1.0 may need tuning.
**Why it happens:** Walk-forward yields only 4 test folds of ~60 games each.
**How to avoid:** Use C=1.0 for meta-learner (strong-ish regularization for small dataset). Optionally tune C with a nested Optuna sweep or just use the fixed value. The 3-feature meta input (XGB_prob, LGB_prob, LR_prob) is well-conditioned; C=1.0 is appropriate.
**Warning signs:** Meta-learner coefficients are extreme (>10 or <-10); sign indicates overfitting.

### Pitfall 5: LightGBM verbose=-1 vs. XGBoost verbosity=0
**What goes wrong:** LightGBM prints per-iteration output cluttering Optuna logs.
**Why it happens:** LightGBM uses `verbose` parameter (not `verbosity`), and default verbose=1 prints lots of output.
**How to avoid:** Always set `verbose=-1` for LGBMClassifier. Set `verbosity=0` for XGBClassifier. These are DIFFERENT parameter names.
**Warning signs:** Optuna trial output is drowned out by LightGBM/XGBoost per-iteration logs.

### Pitfall 6: Backtest Ensemble Not Temporally Isolated
**What goes wrong:** The same ensemble (trained on 2022-2025 OOF) is used to evaluate all backtest years.
**Why it happens:** It's simpler to train one ensemble and reuse it.
**How to avoid:** For each backtest year T, use `build_fold_ensemble(T, df, xgb_params, lgb_params, lr_C)` which trains the meta-learner only on sub-fold OOF from seasons < T.
**Warning signs:** 2025 backtest Brier score suspiciously matches 06-03 OOF Brier (should differ; 2025 data was in the meta-learner training set for the full ensemble but not the 2025-fold ensemble).

### Pitfall 7: TwoTierEnsemble.predict_proba Receives Unscaled Features
**What goes wrong:** `predict_proba(X_raw)` gives nonsense predictions because XGB/LGB received unscaled features.
**Why it happens:** XGB and LGB technically don't need scaling, but StandardScaler is fit on training data; the scaler transforms the same features that the models were trained on.
**Note:** Actually, tree models (XGB, LGB) are scale-invariant. Only the LR base model needs scaling. However, since all three models are trained on the same scaled features (for consistency with the LR baseline), scaling must be applied uniformly.
**How to avoid:** Always scale X before calling `ensemble.predict_proba(X)`. The `TwoTierEnsemble` should NOT auto-scale internally to avoid double-scaling in `predict_fn` closures. Document clearly: predict_proba() expects ALREADY-SCALED input.

### Pitfall 8: results.json Clobbered by Ensemble Backtest
**What goes wrong:** 06-05 backtest run overwrites `backtest/results.json` with ensemble results, losing the baseline record.
**Why it happens:** Default output_path='backtest/results.json' is shared between baseline and ensemble.
**How to avoid:** Use a separate output path for ensemble: `backtest/ensemble_results.json`. The success criterion says "update backtest/results.json with ensemble row" — interpret this as appending/updating, not overwriting. Design the results file to hold multiple model entries, or use a separate file.

## Code Examples

### Import Pattern for Phase 6 Modules

```python
# New imports needed
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

# Existing imports (unchanged from Phase 3/5)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.calibration import CalibrationDisplay, calibration_curve
from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import walk_forward_splits, BACKTEST_YEARS
from src.models.train_logistic import ClippedCalibrator, CLIP_LO, CLIP_HI
import optuna
import joblib
import numpy as np
import pandas as pd
```

### Per-Fold Brier Score Logging (Same as Phase 3 Pattern)

```python
# Source: evaluate.py evaluate_all_holdout_years() pattern
# Reuse for XGB and LGB individual evaluation in 06-01 and 06-02
per_year_results = []
for test_year, train_df, test_df in walk_forward_splits(df):
    # ... train model, get y_prob ...
    brier = brier_score_loss(test_df['label'].values, y_prob)
    ll = log_loss(test_df['label'].values, y_prob)
    per_year_results.append({
        'year': test_year,
        'brier': brier,
        'log_loss': ll,
        'n_games': len(test_df),
    })
    print(f'  {test_year}: Brier={brier:.4f}, LogLoss={ll:.4f}')

mean_brier = np.mean([r['brier'] for r in per_year_results])
print(f'Mean Brier: {mean_brier:.4f} (baseline: 0.1900)')
```

### Calibration Decile Check

```python
# Source: evaluate.py check_calibration() pattern
from sklearn.calibration import calibration_curve
prob_true, prob_pred = calibration_curve(y_true_all, y_prob_all, n_bins=10, strategy='uniform')
max_deviation = float(np.max(np.abs(prob_pred - prob_true)))
print(f'Max deviation from perfect calibration: {max_deviation:.4f}')
# Success criterion: max_deviation < 0.05
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sklearn StackingClassifier with cv=TimeSeriesSplit | Manual OOF stacking (verified broken) | sklearn ~1.4.x | Temporal stacking requires manual implementation |
| CalibratedClassifierCV(cv='prefit') | FrozenEstimator + CalibratedClassifierCV OR ClippedCalibrator | sklearn 1.8.0 | cv='prefit' removed (verified); Phase 3 already fixed with ClippedCalibrator |
| XGBoost class_weight | scale_pos_weight | Always XGBoost-specific | Different parameter name from sklearn convention |

**Deprecated/outdated:**
- `cv='prefit'` in CalibratedClassifierCV: Removed in sklearn 1.8.0. Use `FrozenEstimator` or ClippedCalibrator.
- `use_label_encoder` in XGBClassifier: Removed in recent XGBoost versions. Not needed for binary classification.

## Open Questions

1. **Whether the success criterion's "sklearn StackingClassifier" can be satisfied**
   - What we know: sklearn StackingClassifier raises ValueError with walk_forward_splits (confirmed live).
   - What's unclear: Whether the planner will relax this to "sklearn-compatible wrapper" or require finding a workaround.
   - Recommendation: Use manual OOF stacking wrapped in `TwoTierEnsemble` class with `predict_proba()`. This satisfies the spirit of the requirement. Document the StackingClassifier incompatibility clearly in the plan.

2. **Whether the ensemble can realistically beat the LR baseline**
   - What we know: LR baseline Brier = 0.1900. Dataset has 6 features, ~250 OOF test samples.
   - What's uncertain: Gradient boosting may not outperform LR on this small, low-dimensional dataset. LR is already near-optimal for linear separability of these 6 features.
   - Recommendation: Run both XGB and LGB Optuna sweeps to see individual Brier scores. If both are worse than 0.1900, the stacked ensemble is unlikely to improve. The success criterion "produces win probabilities that outperform" should be treated as aspirational — log results honestly regardless.

3. **Meta-learner C parameter**
   - What we know: Only 248 OOF samples for meta-learner training; meta input is 3 features (XGB_prob, LGB_prob, LR_prob).
   - What's unclear: Whether C=1.0 is optimal or needs tuning.
   - Recommendation: Use C=1.0 as default. Optionally add a small inner Optuna sweep over C in [0.1, 10.0] during 06-03.

4. **Ensemble results.json format**
   - What we know: Phase 5 produces `backtest/results.json` with `model='baseline'` row.
   - What's unclear: Whether to overwrite or append for ensemble results.
   - Recommendation: Write `backtest/ensemble_results.json` separately. The plan for 06-05 should clarify this.

## Sources

### Primary (HIGH confidence)
- Live code execution in madness2026 venv — `cross_val_predict` partition check confirmed raises `ValueError` with walk_forward splits; `cv='prefit'` confirmed removed from sklearn 1.8.0; `FrozenEstimator` confirmed works; `StackingClassifier.fit()` source inspected
- GitHub scikit-learn issue #32614 (WebFetch, Nov 2025) — confirms partition check affects StackingClassifier with TimeSeriesSplit-style splitters; draft PR #33110 exists but unmerged
- [XGBoost sklearn estimator docs](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html) — XGBClassifier API, early stopping, n_jobs behavior
- [LightGBM LGBMClassifier docs](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMClassifier.html) — LGBMClassifier API, class_weight='balanced', verbose=-1
- [sklearn StackingClassifier docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingClassifier.html) — cv parameter, predict_proba behavior, cross_val_predict internal usage
- Live data analysis — confirmed 1054 matchups, 17 seasons, per-fold sizes, scale_pos_weight ~0.40
- Phase 3 codebase (`src/models/train_logistic.py`, `evaluate.py`) — ClippedCalibrator pattern, Optuna sweep structure, confirmed compatible with Phase 6 extension

### Secondary (MEDIUM confidence)
- [XGBoost parameter docs](https://xgboost.readthedocs.io/en/stable/parameter.html) — max_depth, min_child_weight, gamma, scale_pos_weight descriptions
- [LightGBM parameter tuning guide](https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html) — num_leaves, min_child_samples recommendations for small data
- PyPI version checks (Python urllib + json) — xgboost 3.2.0 and lightgbm 4.6.0 confirmed as latest stable

### Tertiary (LOW confidence)
- WebSearch finding: LightGBM is "sensitive with small data" — consistent with documentation but not verified with exact parameter thresholds for this dataset size

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — packages verified by PyPI query; versions confirmed; all sklearn APIs live-tested
- Architecture (manual OOF stacking): HIGH — StackingClassifier failure confirmed by live code execution; manual OOF is the established correct alternative
- Pitfalls: HIGH — most pitfalls confirmed by live code execution or official docs; StackingClassifier partition check is a definitive finding
- Hyperparameter search spaces: MEDIUM — ranges informed by documentation and small-dataset best practices; exact optimal ranges will emerge from Optuna sweeps
- Whether ensemble outperforms baseline: LOW — depends on data; 6 features, linear separability may already be near-optimal for LR

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable; library APIs unlikely to change; sklearn issue #32614 open but fix not yet merged)
