"""
XGBoost training pipeline for NCAA tournament game prediction.

Trains an XGBoost gradient boosting classifier with Optuna hyperparameter
optimization using walk-forward temporal cross-validation. The best hyperparameters
are determined by minimizing mean Brier score across 4 holdout folds (2022-2025).

This is the first gradient boosting base model in the stacking ensemble, following
the same Optuna + temporal CV pattern as train_logistic.py but with XGBoost-specific
hyperparameters and class imbalance handling (scale_pos_weight computed per fold).

Key design choices:
- scale_pos_weight: XGBoost-native class imbalance handling (not class_weight)
  Computed per fold as (y_train==0).sum() / (y_train==1).sum()
- verbosity=0: Suppresses per-iteration output (XGBoost-specific; NOT verbose=-1)
- n_jobs=1: Prevents thread contention during Optuna parallel trials
- objective='binary:logistic': Output probabilities directly for Brier scoring
- random_state=42: Reproducibility across trials and evaluation
- StandardScaler fit on training data ONLY per fold: no test-set leakage

Best hyperparameters are saved to models/xgb_params.json for use in stacking ensemble.

Exports:
    run_optuna_sweep_xgb()  - Run 50-trial Optuna sweep to find best XGB hyperparameters
    evaluate_xgb()          - Evaluate XGB with given params using walk-forward CV
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import numpy as np
import optuna
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import walk_forward_splits
from src.models.train_logistic import CLIP_LO, CLIP_HI  # noqa: F401 -- for comparison reference

# Logistic regression baseline Brier score for comparison
LR_BASELINE_BRIER: float = 0.1900


def run_optuna_sweep_xgb(df: "pd.DataFrame", n_trials: int = 50) -> dict[str, Any]:
    """Run Optuna hyperparameter sweep to find best XGBoost parameters.

    Uses walk-forward temporal cross-validation (4 folds: 2022-2025) to evaluate
    each candidate hyperparameter set. The objective minimizes mean Brier score
    across folds, ensuring hyperparameters are selected without any data leakage.

    StandardScaler is fit on training data only for each fold to prevent leakage
    from test set statistics. scale_pos_weight is computed per fold from training
    labels to handle class imbalance (XGBoost does not support class_weight='balanced').

    Hyperparameter search space:
        n_estimators:      int [50, 300]       -- number of boosting rounds
        max_depth:         int [2, 6]          -- max tree depth, constrains complexity
        learning_rate:     float [0.01, 0.3]   -- log-uniform, controls step size
        subsample:         float [0.6, 1.0]    -- row subsampling per tree
        colsample_bytree:  float [0.5, 1.0]    -- column subsampling per tree
        min_child_weight:  int [1, 10]         -- min sum of instance weight in child
        reg_alpha:         float [1e-4, 1.0]   -- L1 regularization, log-uniform
        reg_lambda:        float [1.0, 10.0]   -- L2 regularization, log-uniform

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        n_trials: Number of Optuna trials. Default: 50.

    Returns:
        Dict of best hyperparameters that minimize mean Brier score.
    """
    # Silence per-trial output -- only show final result
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 10.0, log=True),
        }

        fold_brier_scores = []
        for _year, train_df, test_df in walk_forward_splits(df):
            X_train = train_df[FEATURE_COLS].values
            y_train = train_df["label"].values
            X_test = test_df[FEATURE_COLS].values
            y_test = test_df["label"].values

            # Fit scaler on training data ONLY -- no leakage from test set
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Compute scale_pos_weight per fold from training labels
            # XGBoost uses scale_pos_weight (NOT class_weight) for class imbalance
            # Formula: (n_negative / n_positive) = ((y==0).sum() / (y==1).sum())
            scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())

            clf = XGBClassifier(
                **params,
                scale_pos_weight=scale_pos_weight,
                objective="binary:logistic",
                random_state=42,
                n_jobs=1,      # avoid thread contention during Optuna parallel trials
                verbosity=0,   # suppress per-iteration output (XGBoost-specific)
            )
            clf.fit(X_train_scaled, y_train)
            y_prob = clf.predict_proba(X_test_scaled)[:, 1]
            fold_brier_scores.append(brier_score_loss(y_test, y_prob))

        return float(np.mean(fold_brier_scores))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials)

    best_params = study.best_params
    best_brier = study.best_value
    print(f"Optuna sweep complete ({n_trials} trials)")
    print(f"  Best hyperparameters: {best_params}")
    print(f"  Best Brier score:     {best_brier:.6f}")

    return best_params


def evaluate_xgb(
    df: "pd.DataFrame",
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate XGBoost with given params using walk-forward temporal CV.

    For each fold (2022-2025), fits a StandardScaler on training data only,
    computes scale_pos_weight from training labels, trains XGBClassifier, and
    computes per-year Brier score and log-loss. Prints a comparison table against
    the logistic regression baseline (0.1900).

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        params: Hyperparameter dict (typically from run_optuna_sweep_xgb()).

    Returns:
        List of per-year result dicts:
        [{'year': int, 'brier': float, 'log_loss': float, 'n_games': int}]
    """
    results = []

    for year, train_df, test_df in walk_forward_splits(df):
        X_train = train_df[FEATURE_COLS].values
        y_train = train_df["label"].values
        X_test = test_df[FEATURE_COLS].values
        y_test = test_df["label"].values

        # Fit scaler on training data ONLY -- no leakage from test set
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Compute scale_pos_weight per fold from training labels
        scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())

        clf = XGBClassifier(
            **params,
            scale_pos_weight=scale_pos_weight,
            objective="binary:logistic",
            random_state=42,
            n_jobs=1,     # consistent with sweep config
            verbosity=0,  # suppress per-iteration output (XGBoost-specific)
        )
        clf.fit(X_train_scaled, y_train)
        y_prob = clf.predict_proba(X_test_scaled)[:, 1]

        brier = float(brier_score_loss(y_test, y_prob))
        ll = float(log_loss(y_test, y_prob))
        n_games = len(test_df)

        results.append(
            {
                "year": year,
                "brier": brier,
                "log_loss": ll,
                "n_games": n_games,
            }
        )

    # Print per-year table
    print(f"\n{'Year':>6} | {'Brier':>8} | {'Log-Loss':>10} | {'N Games':>8}")
    print("-" * 44)
    for r in results:
        print(
            f"{r['year']:>6} | "
            f"{r['brier']:>8.4f} | "
            f"{r['log_loss']:>10.4f} | "
            f"{r['n_games']:>8}"
        )

    mean_brier = float(np.mean([r["brier"] for r in results]))
    mean_ll = float(np.mean([r["log_loss"] for r in results]))
    print("-" * 44)
    print(f"{'Mean':>6} | {mean_brier:>8.4f} | {mean_ll:>10.4f} |")

    # Comparison to baseline
    delta = mean_brier - LR_BASELINE_BRIER
    direction = "better" if delta < 0 else "worse"
    print(
        f"\nXGBoost mean Brier: {mean_brier:.4f} "
        f"vs baseline {LR_BASELINE_BRIER:.4f} "
        f"(delta={delta:+.4f}, {direction})"
    )

    return results


if __name__ == "__main__":
    print("Building matchup dataset...")
    df = build_matchup_dataset()
    print(f"\nDataset: {len(df)} matchups, {df['Season'].nunique()} seasons")

    print("\nRunning Optuna hyperparameter sweep (50 trials)...")
    best_params = run_optuna_sweep_xgb(df, n_trials=50)

    # Save best hyperparameters to JSON
    models_dir = pathlib.Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    params_path = models_dir / "xgb_params.json"
    params_path.write_text(json.dumps(best_params, indent=2))
    print(f"\nBest hyperparameters saved to: {params_path}")

    print("\nEvaluating XGBoost with best hyperparameters...")
    results = evaluate_xgb(df, best_params)

    mean_brier = sum(r["brier"] for r in results) / len(results)
    print(f"\nXGBoost mean Brier: {mean_brier:.4f} vs baseline {LR_BASELINE_BRIER:.4f}")
