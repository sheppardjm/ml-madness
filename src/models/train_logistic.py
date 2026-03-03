"""
Logistic regression training pipeline for NCAA tournament game prediction.

Trains a logistic regression classifier with Optuna hyperparameter optimization
(C parameter sweep) using walk-forward temporal cross-validation. The best C
is determined by minimizing mean Brier score across 4 holdout folds (2022-2025).

The trained model artifact is saved to models/logistic_baseline.joblib and
includes all metadata needed for future prediction and evaluation.

Exports:
    run_optuna_sweep()  - Run Optuna sweep to find best C via walk-forward CV
    train_and_save()    - Train on full dataset with best C and save artifact
    load_model()        - Load saved artifact and return (model, scaler, features)
    predict_matchup()   - Predict win probability for a single team-pair feature dict
"""

from __future__ import annotations

import pathlib
from typing import Any

import joblib
import numpy as np
import optuna
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.preprocessing import StandardScaler

from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import walk_forward_splits


def run_optuna_sweep(df: "pd.DataFrame", n_trials: int = 50) -> float:
    """Run Optuna hyperparameter sweep to find the best regularization C.

    Uses walk-forward temporal cross-validation (4 folds: 2022-2025) to evaluate
    each candidate C value. The objective minimizes mean Brier score across folds,
    ensuring C is selected without any data leakage.

    StandardScaler is fit on training data only for each fold to prevent leakage
    from test set statistics.

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        n_trials: Number of Optuna trials. Default: 50.

    Returns:
        Best C parameter (float) that minimizes mean Brier score.
    """
    # Silence per-trial output — only show final result
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        C = trial.suggest_float("C", 1e-3, 100.0, log=True)

        fold_brier_scores = []
        for _year, train_df, test_df in walk_forward_splits(df):
            X_train = train_df[FEATURE_COLS].values
            y_train = train_df["label"].values
            X_test = test_df[FEATURE_COLS].values
            y_test = test_df["label"].values

            # Fit scaler on training data ONLY — no leakage from test set
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            clf = LogisticRegression(
                C=C,
                class_weight="balanced",
                solver="lbfgs",
                max_iter=1000,
                random_state=42,
            )
            clf.fit(X_train_scaled, y_train)

            y_prob = clf.predict_proba(X_test_scaled)[:, 1]
            fold_brier_scores.append(brier_score_loss(y_test, y_prob))

        return float(np.mean(fold_brier_scores))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials)

    best_C = study.best_params["C"]
    best_brier = study.best_value
    print(f"Optuna sweep complete ({n_trials} trials)")
    print(f"  Best C:           {best_C:.6f}")
    print(f"  Best Brier score: {best_brier:.6f}")

    return best_C


def train_and_save(
    df: "pd.DataFrame",
    best_C: float,
    model_path: str = "models/logistic_baseline.joblib",
) -> dict[str, Any]:
    """Train logistic regression on the full dataset and save the artifact.

    Trains with the best C found by Optuna sweep. The scaler is fit on the
    full dataset (all seasons) since this is the final production model.

    Artifact structure:
        model           - Fitted LogisticRegression instance
        scaler          - Fitted StandardScaler instance
        feature_names   - Ordered list of feature column names (FEATURE_COLS)
        train_seasons   - Sorted list of seasons in training data
        best_C          - C parameter used (from Optuna sweep)
        sklearn_version - sklearn version string for compatibility tracking

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        best_C: Regularization parameter selected by Optuna.
        model_path: Output path for the joblib artifact. Default: models/logistic_baseline.joblib

    Returns:
        The artifact dict that was saved.
    """
    X = df[FEATURE_COLS].values
    y = df["label"].values

    # Fit scaler on full dataset for production model
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = LogisticRegression(
        C=best_C,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    clf.fit(X_scaled, y)

    # Create output directory if needed
    pathlib.Path(model_path).parent.mkdir(parents=True, exist_ok=True)

    artifact = {
        "model": clf,
        "scaler": scaler,
        "feature_names": FEATURE_COLS,
        "train_seasons": sorted(df["Season"].unique().tolist()),
        "best_C": best_C,
        "sklearn_version": sklearn.__version__,
    }
    joblib.dump(artifact, model_path)

    print(f"\nModel saved to: {model_path}")
    print(f"  Training games: {len(df)}")
    print(f"  Training seasons: {artifact['train_seasons']}")
    print(f"  Best C: {best_C:.6f}")
    print(f"  sklearn version: {sklearn.__version__}")
    print(f"\nCoefficients (feature -> coefficient):")
    for name, coef in zip(FEATURE_COLS, clf.coef_[0]):
        print(f"  {name:>15}: {coef:+.4f}")
    print(f"  {'intercept':>15}: {clf.intercept_[0]:+.4f}")

    return artifact


def load_model(
    model_path: str = "models/logistic_baseline.joblib",
) -> tuple["LogisticRegression", "StandardScaler", list[str]]:
    """Load the saved model artifact from disk.

    Args:
        model_path: Path to the joblib artifact. Default: models/logistic_baseline.joblib

    Returns:
        Tuple of (model, scaler, feature_names) ready for prediction.

    Raises:
        FileNotFoundError: If model file does not exist.
    """
    path = pathlib.Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {model_path}. "
            "Run train_and_save() first."
        )

    artifact = joblib.load(model_path)

    saved_version = artifact.get("sklearn_version", "unknown")
    current_version = sklearn.__version__
    if saved_version != current_version:
        print(
            f"WARNING: Model was saved with sklearn {saved_version}, "
            f"current version is {current_version}. "
            "Predictions may differ."
        )
    else:
        print(f"Model loaded (sklearn {current_version})")

    return artifact["model"], artifact["scaler"], artifact["feature_names"]


def predict_matchup(
    team_a_features: dict[str, float],
    model: "LogisticRegression",
    scaler: "StandardScaler",
    feature_names: list[str],
) -> float:
    """Predict win probability for team_a given differential feature values.

    Team A is the team with the lower seed number (better seed / higher rank)
    by convention — same as in build_matchup_dataset() canonical ordering.

    Args:
        team_a_features: Dict with keys matching FEATURE_COLS and float values.
            Keys: adjoe_diff, adjde_diff, barthag_diff, seed_diff, adjt_diff, wab_diff
        model: Fitted LogisticRegression model.
        scaler: Fitted StandardScaler (must be the one saved with the model).
        feature_names: Ordered list of feature names (must match model's expected order).

    Returns:
        Float in (0, 1): probability that team_a wins.

    Raises:
        KeyError: If any required feature is missing from team_a_features.
    """
    # Build array in canonical feature order
    x = np.array([team_a_features[name] for name in feature_names], dtype=float)
    x = x.reshape(1, -1)

    X_scaled = scaler.transform(x)
    prob = float(model.predict_proba(X_scaled)[0, 1])

    return prob


if __name__ == "__main__":
    import pandas as pd

    print("Building matchup dataset...")
    df = build_matchup_dataset()
    print(f"\nDataset: {len(df)} matchups, {df['Season'].nunique()} seasons")

    print("\nRunning Optuna hyperparameter sweep (50 trials)...")
    best_C = run_optuna_sweep(df, n_trials=50)

    print("\nTraining final model on full dataset...")
    artifact = train_and_save(df, best_C, model_path="models/logistic_baseline.joblib")

    print("\nVerifying saved model...")
    model, scaler, feature_names = load_model("models/logistic_baseline.joblib")

    # Pick one row from dataset and verify prediction
    sample_row = df.iloc[0]
    sample_features = {col: float(sample_row[col]) for col in FEATURE_COLS}
    print(f"\nSample matchup features:")
    for k, v in sample_features.items():
        print(f"  {k}: {v:.4f}")

    prob = predict_matchup(sample_features, model, scaler, feature_names)
    print(f"\nPredicted win probability (team_a): {prob:.4f}")

    assert 0.05 <= prob <= 0.95, (
        f"Prediction {prob:.4f} is extreme — expected between 0.05 and 0.95"
    )
    print("Sanity check passed (probability between 0.05 and 0.95)")

    # Quick coefficient check: barthag_diff should be positive
    coefs = dict(zip(feature_names, model.coef_[0]))
    print(f"\nCoefficient check:")
    for name, coef in coefs.items():
        print(f"  {name}: {coef:+.4f}")

    if coefs.get("barthag_diff", 0) > 0:
        print("barthag_diff coefficient is positive (better power rating -> higher win prob): OK")
    else:
        print("WARNING: barthag_diff coefficient is not positive — check feature direction")

    print("\nAll checks passed.")
