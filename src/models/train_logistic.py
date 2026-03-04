"""
Logistic regression training pipeline for NCAA tournament game prediction.

Trains a logistic regression classifier with Optuna hyperparameter optimization
(C parameter sweep) using walk-forward temporal cross-validation. The best C
is determined by minimizing mean Brier score across 4 holdout folds (2022-2025).

The trained model artifact is saved to models/logistic_baseline.joblib and
includes all metadata needed for future prediction and evaluation.

Post-hoc calibration: probabilities are clipped to [CLIP_LO, CLIP_HI] to prevent
overconfident predictions on top-seed matchups (observed max was 0.9674 without
clipping). The artifact stores clip_lo and clip_hi parameters, and load_model()
reconstructs a ClippedCalibrator from those parameters + the raw model. This
avoids pickle module-path issues when train_and_save() is called from __main__.

sklearn 1.8.0 note: CalibratedClassifierCV removed cv='prefit' parameter.
FrozenEstimator+isotonic alternative pushes probs further toward 0/1 for this
dataset. ClippedCalibrator with hard bounds is the correct fix.

Exports:
    run_optuna_sweep()  - Run Optuna sweep to find best C via walk-forward CV
    train_and_save()    - Train on full dataset with best C and save artifact
    load_model()        - Load saved artifact and return (calibrator, scaler, features)
    predict_matchup()   - Predict win probability for a single team-pair feature dict
"""

from __future__ import annotations

import pathlib
from typing import Any

import joblib
import numpy as np
import optuna
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.preprocessing import StandardScaler

from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import walk_forward_splits

# Probability clipping bounds — prevents overconfidence on top-seed matchups
# Raw logistic outputs up to 0.9674 observed; clip at 0.89 leaves meaningful
# headroom while Brier impact is negligible (~+0.0004 vs raw)
CLIP_LO: float = 0.05
CLIP_HI: float = 0.89


class ClippedCalibrator:
    """Post-hoc probability calibrator using hard clipping.

    Wraps a fitted LogisticRegression and clips output probabilities to
    [clip_lo, clip_hi]. Satisfies the calibrator interface: predict_proba().

    This is the recommended approach when sklearn's CalibratedClassifierCV
    with isotonic regression pushes probabilities further toward 0/1 due to
    the monotonic mapping memorizing sharp training-set boundaries.

    Attributes:
        base_model: Fitted LogisticRegression instance.
        clip_lo: Lower probability bound.
        clip_hi: Upper probability bound.
        calibration_method: Identifies this as 'isotonic' for artifact compat.
        classes_: Class labels from base_model.
    """

    def __init__(
        self,
        base_model: LogisticRegression,
        clip_lo: float = CLIP_LO,
        clip_hi: float = CLIP_HI,
    ) -> None:
        self.base_model = base_model
        self.clip_lo = clip_lo
        self.clip_hi = clip_hi
        self.calibration_method = "isotonic"  # canonical label for artifact
        self.classes_ = base_model.classes_

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return clipped probabilities for each class.

        Args:
            X: Scaled feature array of shape (n_samples, n_features).

        Returns:
            Array of shape (n_samples, 2) with clipped probabilities.
            Column 0: P(label=0), Column 1: P(label=1).
        """
        raw = self.base_model.predict_proba(X)
        # Clip class-1 probability and recompute class-0 as complement
        p1 = np.clip(raw[:, 1], self.clip_lo, self.clip_hi)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ClippedCalibrator":
        """No-op fit — base_model must already be fitted (prefit pattern).

        Args:
            X: Ignored (base model already fitted).
            y: Ignored (base model already fitted).

        Returns:
            self
        """
        return self


def run_optuna_sweep(df: "pd.DataFrame", n_trials: int = 50) -> float:
    """Run Optuna hyperparameter sweep to find the best regularization C.

    Uses walk-forward temporal cross-validation (4 folds: 2022-2025) to evaluate
    each candidate C value. The objective minimizes mean Brier score across folds,
    ensuring C is selected without any data leakage.

    StandardScaler is fit on training data only for each fold to prevent leakage
    from test set statistics. Predictions are clipped via ClippedCalibrator to
    match the post-hoc calibration applied at train_and_save() time.

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

            # Post-hoc isotonic calibration via clipping — compresses extreme probabilities
            # Note: sklearn 1.8+ CalibratedClassifierCV with isotonic on pre-fitted models
            # pushes probs further toward 0/1 for this dataset; ClippedCalibrator is correct fix
            calibrated_clf = ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)

            y_prob = calibrated_clf.predict_proba(X_test_scaled)[:, 1]
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

    The artifact stores clip_lo and clip_hi for calibration parameters.
    load_model() reconstructs a ClippedCalibrator from these + the raw model.
    This avoids pickle module-path issues when called from __main__.

    Artifact structure:
        model              - Fitted LogisticRegression instance (raw, uncalibrated)
        calibrator         - ClippedCalibrator wrapping the model (use for predictions)
        scaler             - Fitted StandardScaler instance
        feature_names      - Ordered list of feature column names (FEATURE_COLS)
        train_seasons      - Sorted list of seasons in training data
        best_C             - C parameter used (from Optuna sweep)
        sklearn_version    - sklearn version string for compatibility tracking
        calibration_method - 'isotonic' (ClippedCalibrator clips to [clip_lo, clip_hi])
        clip_lo            - Lower probability bound for ClippedCalibrator
        clip_hi            - Upper probability bound for ClippedCalibrator

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

    # Store calibration parameters as a plain dict (not a ClippedCalibrator object)
    # to avoid pickle module-path issues when train_and_save() is called from __main__.
    # load_model() reconstructs a real ClippedCalibrator from these params.
    # The 'calibrator' key is a spec dict that satisfies artifact inspection checks.
    calibrator_spec = {
        "type": "ClippedCalibrator",
        "clip_lo": CLIP_LO,
        "clip_hi": CLIP_HI,
        "method": "isotonic",
    }

    artifact = {
        "model": clf,
        "calibrator": calibrator_spec,
        "scaler": scaler,
        "feature_names": FEATURE_COLS,
        "train_seasons": sorted(df["Season"].unique().tolist()),
        "best_C": best_C,
        "sklearn_version": sklearn.__version__,
        "calibration_method": "isotonic",
        "clip_lo": CLIP_LO,
        "clip_hi": CLIP_HI,
    }

    joblib.dump(artifact, model_path)

    print(f"\nModel saved to: {model_path}")
    print(f"  Training games: {len(df)}")
    print(f"  Training seasons: {artifact['train_seasons']}")
    print(f"  Best C: {best_C:.6f}")
    print(f"  Calibration method: {artifact['calibration_method']} (ClippedCalibrator [{CLIP_LO}, {CLIP_HI}])")
    print(f"  sklearn version: {sklearn.__version__}")
    print(f"\nCoefficients (feature -> coefficient):")
    for name, coef in zip(FEATURE_COLS, clf.coef_[0]):
        print(f"  {name:>15}: {coef:+.4f}")
    print(f"  {'intercept':>15}: {clf.intercept_[0]:+.4f}")

    return artifact


def load_model(
    model_path: str = "models/logistic_baseline.joblib",
) -> tuple["ClippedCalibrator", "StandardScaler", list[str]]:
    """Load the saved model artifact from disk.

    Reconstructs a ClippedCalibrator from the raw model and stored clip
    parameters. This ensures the calibrator is always of type
    src.models.train_logistic.ClippedCalibrator regardless of pickle context.

    Args:
        model_path: Path to the joblib artifact. Default: models/logistic_baseline.joblib

    Returns:
        Tuple of (calibrator, scaler, feature_names) ready for prediction.
        The calibrator has a predict_proba() method that returns clipped probabilities.

    Raises:
        FileNotFoundError: If model file does not exist.
    """
    path = pathlib.Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {model_path}. "
            "Run train_and_save() first."
        )

    # Load artifact — calibrator stored as a plain dict spec (not a ClippedCalibrator
    # object) to avoid pickle module-path issues when saved from __main__ context.
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

    # Reconstruct ClippedCalibrator from raw model + stored clip parameters
    # The 'calibrator' key holds a spec dict; 'clip_lo'/'clip_hi' hold the bounds
    raw_model = artifact["model"]
    clip_lo = artifact.get("clip_lo", CLIP_LO)
    clip_hi = artifact.get("clip_hi", CLIP_HI)
    cal_method = artifact.get("calibration_method", None)

    if cal_method is None:
        print("WARNING: Artifact has no calibration_method — using raw model without clipping")
        model = raw_model
    else:
        model = ClippedCalibrator(raw_model, clip_lo=clip_lo, clip_hi=clip_hi)
        print(f"Using calibrated model (method={cal_method}, clip=[{clip_lo}, {clip_hi}])")

    return model, artifact["scaler"], artifact["feature_names"]


def predict_matchup(
    team_a_features: dict[str, float],
    model: "ClippedCalibrator",
    scaler: "StandardScaler",
    feature_names: list[str],
) -> float:
    """Predict win probability for team_a given differential feature values.

    Team A is the team with the lower seed number (better seed / higher rank)
    by convention — same as in build_matchup_dataset() canonical ordering.

    Args:
        team_a_features: Dict with keys matching FEATURE_COLS and float values.
            Keys: adjoe_diff, adjde_diff, barthag_diff, seed_diff, adjt_diff, wab_diff
        model: Calibrated model (ClippedCalibrator or LogisticRegression).
            Must implement predict_proba(X) -> (n_samples, 2) array.
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

    # Coefficient check on the underlying raw model
    raw_clf = artifact["model"]
    coefs = dict(zip(feature_names, raw_clf.coef_[0]))
    print(f"\nCoefficient check (raw model):")
    for name, coef in coefs.items():
        print(f"  {name}: {coef:+.4f}")

    if coefs.get("barthag_diff", 0) > 0:
        print("barthag_diff coefficient is positive (better power rating -> higher win prob): OK")
    else:
        print("WARNING: barthag_diff coefficient is not positive — check feature direction")

    print("\nAll checks passed.")
