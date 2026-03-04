"""
LightGBM training pipeline for NCAA tournament game prediction.

Trains a LightGBM gradient boosting classifier with Optuna hyperparameter
optimization using walk-forward temporal cross-validation. The best hyperparameters
are determined by minimizing mean Brier score across 4 holdout folds (2022-2025).

This is the second gradient boosting base model in the stacking ensemble, following
the same Optuna + temporal CV pattern as train_xgboost.py but with LightGBM-specific
hyperparameters and native class imbalance handling (class_weight='balanced').

Key design choices:
- class_weight='balanced': LightGBM native support (unlike XGBoost, no scale_pos_weight needed)
- verbose=-1: Suppresses per-iteration output (LightGBM-specific; NOT verbosity=0)
- n_jobs=1: Prevents thread contention during Optuna parallel trials
- num_leaves <= 60: Constrains model complexity for ~1000-sample dataset
- min_child_samples >= 10: Prevents memorization of small training folds
- StandardScaler fit on training data ONLY per fold: no test-set leakage

Best hyperparameters are saved to models/lgb_params.json for use in stacking ensemble.

Exports:
    run_optuna_sweep_lgb()  - Run 50-trial Optuna sweep to find best LGB hyperparameters
    evaluate_lgb()          - Evaluate LGB with given params using walk-forward CV
"""

from __future__ import annotations

import json
import pathlib
import warnings
from typing import Any

import numpy as np
import optuna
from lightgbm import LGBMClassifier
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import walk_forward_splits

# Logistic regression baseline Brier score for comparison
LR_BASELINE_BRIER: float = 0.1900


def run_optuna_sweep_lgb(df: "pd.DataFrame", n_trials: int = 50) -> dict[str, Any]:
    """Run Optuna hyperparameter sweep to find best LightGBM parameters.

    Uses walk-forward temporal cross-validation (4 folds: 2022-2025) to evaluate
    each candidate hyperparameter set. The objective minimizes mean Brier score
    across folds, ensuring hyperparameters are selected without any data leakage.

    StandardScaler is fit on training data only for each fold to prevent leakage
    from test set statistics.

    Hyperparameter search space (constrained for ~1000-sample dataset):
        num_leaves:        int [10, 60]       -- max complexity, prevent overfitting
        n_estimators:      int [50, 300]      -- number of boosting rounds
        learning_rate:     float [0.01, 0.3]  -- log-uniform, controls step size
        min_child_samples: int [10, 30]       -- min >= 10 prevents small-leaf memorization
        subsample:         float [0.6, 1.0]   -- row subsampling per tree
        colsample_bytree:  float [0.5, 1.0]   -- column subsampling per tree
        reg_alpha:         float [1e-4, 1.0]  -- L1 regularization, log-uniform
        reg_lambda:        float [1e-4, 10.0] -- L2 regularization, log-uniform

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
            "num_leaves": trial.suggest_int("num_leaves", 10, 60),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 30),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
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

            clf = LGBMClassifier(
                **params,
                class_weight="balanced",  # native LightGBM support (not scale_pos_weight)
                objective="binary",
                random_state=42,
                n_jobs=1,       # avoid thread contention during Optuna parallel trials
                verbose=-1,     # suppress per-iteration output (LightGBM-specific)
            )
            clf.fit(X_train_scaled, y_train)

            # Suppress sklearn's feature-name warning: LightGBM sklearn API warns
            # when numpy arrays are passed after fitting (harmless; arrays are correct)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="X does not have valid feature names",
                    category=UserWarning,
                )
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


def evaluate_lgb(
    df: "pd.DataFrame",
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate LightGBM with given params using walk-forward temporal CV.

    For each fold (2022-2025), fits a StandardScaler on training data only,
    trains LGBMClassifier, and computes per-year Brier score and log-loss.
    Prints a comparison table against the logistic regression baseline (0.1900).

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        params: Hyperparameter dict (typically from run_optuna_sweep_lgb()).

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

        clf = LGBMClassifier(
            **params,
            class_weight="balanced",  # native LightGBM support (not scale_pos_weight)
            objective="binary",
            random_state=42,
            n_jobs=1,    # consistent with sweep config
            verbose=-1,  # suppress per-iteration output (LightGBM-specific)
        )
        clf.fit(X_train_scaled, y_train)

        # Suppress sklearn's feature-name warning: LightGBM sklearn API warns
        # when numpy arrays are passed after fitting (harmless; arrays are correct)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
                category=UserWarning,
            )
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
        f"\nLightGBM mean Brier: {mean_brier:.4f} "
        f"vs baseline {LR_BASELINE_BRIER:.4f} "
        f"(delta={delta:+.4f}, {direction})"
    )

    return results


if __name__ == "__main__":
    print("Building matchup dataset...")
    df = build_matchup_dataset()
    print(f"\nDataset: {len(df)} matchups, {df['Season'].nunique()} seasons")

    print("\nRunning Optuna hyperparameter sweep (50 trials)...")
    best_params = run_optuna_sweep_lgb(df, n_trials=50)

    # Save best hyperparameters to JSON
    models_dir = pathlib.Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    params_path = models_dir / "lgb_params.json"
    params_path.write_text(json.dumps(best_params, indent=2))
    print(f"\nBest hyperparameters saved to: {params_path}")

    print("\nEvaluating LightGBM with best hyperparameters...")
    results = evaluate_lgb(df, best_params)

    mean_brier = sum(r["brier"] for r in results) / len(results)
    print(f"\nLightGBM mean Brier: {mean_brier:.4f} vs baseline {LR_BASELINE_BRIER:.4f}")
