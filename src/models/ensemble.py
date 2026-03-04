"""
Stacking ensemble for NCAA tournament game prediction.

Combines XGBoost, LightGBM, and Logistic Regression base models into a
TwoTierEnsemble using manual out-of-fold (OOF) temporal stacking. The
meta-learner (LogisticRegression with C=1.0) is trained on OOF predictions
from all 4 walk-forward folds, then all 3 base models are re-fit on the full
dataset for production use.

Manual OOF stacking is used instead of sklearn's StackingClassifier because
walk_forward_splits() produces non-partition splits (each fold's training set
is a strict prefix of the data), which triggers a ValueError in sklearn's
internal cross_val_predict() partition check (GitHub #32614).

The final ensemble output is clipped to [CLIP_LO, CLIP_HI] for consistency
with the Phase 3 logistic regression baseline (ClippedCalibrator).

Exports:
    TwoTierEnsemble  - Stacking ensemble class with predict_proba() interface
    build_ensemble() - Factory function: OOF stacking + meta-learner training
"""

from __future__ import annotations

import json
import pathlib
import warnings
from typing import Any

import joblib
import lightgbm
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
import xgboost
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibrationDisplay, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.models.features import FEATURE_COLS, build_matchup_dataset
from src.models.temporal_cv import BACKTEST_YEARS, walk_forward_splits
from src.models.train_logistic import CLIP_HI, CLIP_LO, ClippedCalibrator


class TwoTierEnsemble:
    """Stacking ensemble: XGB + LGB + LR base models + LR meta-learner.

    Exposes predict_proba() compatible with ClippedCalibrator and backtest predict_fn.
    Does NOT auto-scale features -- caller must pass ALREADY-SCALED input.

    IMPORTANT: self.scaler is stored for REFERENCE ONLY (e.g., to allow
    callers to access the fitted scaler). predict_proba() must NOT call
    self.scaler.transform() internally -- the caller is responsible for
    scaling features before passing them to predict_proba(). This prevents
    double-scaling when callers also apply the scaler externally.

    Attributes:
        scaler: StandardScaler fitted on full training data (stored for
                caller convenience; NOT used inside predict_proba).
        xgb: Fitted XGBClassifier.
        lgb: Fitted LGBMClassifier.
        lr_base: Fitted LogisticRegression (base model).
        meta_lr: Fitted LogisticRegression (meta-learner on OOF predictions).
        clip_lo: Lower probability bound (default 0.05).
        clip_hi: Upper probability bound (default 0.89).
        classes_: np.array([0, 1]) for sklearn compatibility.
    """

    def __init__(
        self,
        scaler: StandardScaler,
        xgb: XGBClassifier,
        lgb: LGBMClassifier,
        lr_base: LogisticRegression,
        meta_lr: LogisticRegression,
        clip_lo: float = CLIP_LO,
        clip_hi: float = CLIP_HI,
    ) -> None:
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
            X: Scaled feature array (n_samples, 6). Must be pre-scaled by caller.

        Returns:
            (n_samples, 2) array. Column 0 = P(label=0), Column 1 = P(label=1).
            Probabilities are clipped to [clip_lo, clip_hi].
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p_xgb = self.xgb.predict_proba(X)[:, 1]
            p_lgb = self.lgb.predict_proba(X)[:, 1]
            # LR base model goes through ClippedCalibrator for consistency
            p_lr = ClippedCalibrator(self.lr_base).predict_proba(X)[:, 1]

        X_meta = np.column_stack([p_xgb, p_lgb, p_lr])
        p1 = self.meta_lr.predict_proba(X_meta)[:, 1]
        p1 = np.clip(p1, self.clip_lo, self.clip_hi)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])


def build_ensemble(
    df: pd.DataFrame,
    xgb_params: dict[str, Any],
    lgb_params: dict[str, Any],
    lr_best_C: float,
) -> tuple[TwoTierEnsemble, dict[str, Any]]:
    """Build stacking ensemble via manual OOF temporal stacking.

    Uses walk_forward_splits() to collect out-of-fold predictions from all 4
    holdout folds (2022-2025). These OOF predictions train the LogisticRegression
    meta-learner. After meta-learner training, all 3 base models are re-fit on
    the full dataset for production inference.

    Manual OOF stacking is used instead of sklearn's StackingClassifier because
    walk_forward_splits() produces non-partition (prefix) splits that trigger a
    ValueError in sklearn's internal cross_val_predict() partition check.

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        xgb_params: XGBoost hyperparameters (from xgb_params.json, tuned by 06-01).
        lgb_params: LightGBM hyperparameters (from lgb_params.json, tuned by 06-02).
        lr_best_C: Best regularization C for logistic regression base model.

    Returns:
        Tuple of (ensemble, metadata) where:
            ensemble: Fitted TwoTierEnsemble instance ready for predict_proba().
            metadata: Dict with OOF Brier scores, meta-learner params, and OOF data.
    """
    print("=" * 60)
    print("Phase 1: Collecting OOF predictions across 4 folds")
    print("=" * 60)

    oof_xgb: list[float] = []
    oof_lgb: list[float] = []
    oof_lr: list[float] = []
    oof_labels: list[int] = []
    oof_brier_per_year: dict[int, float] = {}
    fold_sizes: list[tuple[int, int]] = []

    for test_year, train_df, test_df in walk_forward_splits(df):
        X_train = train_df[FEATURE_COLS].values
        y_train = train_df["label"].values
        X_test = test_df[FEATURE_COLS].values
        y_test = test_df["label"].values

        # Fit scaler on training data ONLY (no leakage from test set)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # XGB base model (fold-specific)
        # XGBoost sklearn API uses scale_pos_weight (not class_weight='balanced')
        scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())
        xgb_fold = XGBClassifier(
            **xgb_params,
            scale_pos_weight=scale_pos_weight,
            objective="binary:logistic",
            random_state=42,
            n_jobs=1,
            verbosity=0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            xgb_fold.fit(X_train_scaled, y_train)

        # LGB base model (fold-specific)
        # LightGBM uses class_weight='balanced' (not scale_pos_weight)
        lgb_fold = LGBMClassifier(
            **lgb_params,
            class_weight="balanced",
            objective="binary",
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lgb_fold.fit(X_train_scaled, y_train)

        # LR base model (fold-specific)
        lr_fold = LogisticRegression(
            C=lr_best_C,
            class_weight="balanced",
            solver="lbfgs",
            max_iter=1000,
            random_state=42,
        )
        lr_fold.fit(X_train_scaled, y_train)

        # Collect OOF predictions
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p_xgb = xgb_fold.predict_proba(X_test_scaled)[:, 1]
            p_lgb = lgb_fold.predict_proba(X_test_scaled)[:, 1]
        # LR OOF predictions go through ClippedCalibrator for consistency
        # with how the base model will be used inside TwoTierEnsemble.predict_proba()
        p_lr = ClippedCalibrator(lr_fold).predict_proba(X_test_scaled)[:, 1]

        oof_xgb.extend(p_xgb.tolist())
        oof_lgb.extend(p_lgb.tolist())
        oof_lr.extend(p_lr.tolist())
        oof_labels.extend(y_test.tolist())
        fold_sizes.append((test_year, len(y_test)))

        # Per-base-model Brier for this fold (diagnostic)
        brier_xgb = brier_score_loss(y_test, p_xgb)
        brier_lgb = brier_score_loss(y_test, p_lgb)
        brier_lr = brier_score_loss(y_test, p_lr)
        print(
            f"  {test_year}: XGB={brier_xgb:.4f}, "
            f"LGB={brier_lgb:.4f}, "
            f"LR={brier_lr:.4f}"
        )

    total_oof = len(oof_labels)
    print(f"\nTotal OOF samples collected: {total_oof}")
    assert total_oof > 0, "No OOF predictions collected"

    # Phase 2: Train meta-learner on OOF predictions
    print("\n" + "=" * 60)
    print("Phase 2: Training meta-learner on OOF predictions")
    print("=" * 60)

    X_meta = np.column_stack([oof_xgb, oof_lgb, oof_lr])
    y_meta = np.array(oof_labels)

    # C=1.0 provides moderate regularization for 248 OOF samples with 3 features
    meta_lr = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    meta_lr.fit(X_meta, y_meta)

    meta_coefs = meta_lr.coef_[0].tolist()
    meta_intercept = float(meta_lr.intercept_[0])
    print(f"  Meta-learner coefficients: XGB={meta_coefs[0]:.4f}, LGB={meta_coefs[1]:.4f}, LR={meta_coefs[2]:.4f}")
    print(f"  Meta-learner intercept: {meta_intercept:.4f}")

    # Verify coefficients are reasonable (not extreme)
    for i, (name, coef) in enumerate(zip(["XGB", "LGB", "LR"], meta_coefs)):
        if abs(coef) > 10:
            print(f"  WARNING: {name} meta coefficient {coef:.4f} is extreme (|coef| > 10)")

    # Phase 3: Compute OOF ensemble Brier (meta output, clipped)
    print("\n" + "=" * 60)
    print("Phase 3: Computing OOF ensemble Brier score")
    print("=" * 60)

    p_meta_raw = meta_lr.predict_proba(X_meta)[:, 1]
    p_meta_clipped = np.clip(p_meta_raw, CLIP_LO, CLIP_HI)
    oof_ensemble_brier = float(brier_score_loss(y_meta, p_meta_clipped))

    print(f"\nOOF Ensemble Brier: {oof_ensemble_brier:.4f} vs baseline 0.1900")
    delta = oof_ensemble_brier - 0.1900
    direction = "improvement" if delta < 0 else "regression"
    print(f"  Delta vs baseline: {delta:+.4f} ({direction})")

    # Per-year OOF ensemble Brier
    offset = 0
    for year, n in fold_sizes:
        y_slice = y_meta[offset : offset + n]
        p_slice = p_meta_clipped[offset : offset + n]
        year_brier = float(brier_score_loss(y_slice, p_slice))
        oof_brier_per_year[year] = year_brier
        print(f"  OOF Ensemble Brier {year}: {year_brier:.4f}")
        offset += n

    # Phase 4: Refit all 3 base models on full dataset
    print("\n" + "=" * 60)
    print("Phase 4: Refitting all base models on full dataset")
    print("=" * 60)

    full_scaler = StandardScaler()
    X_full = full_scaler.fit_transform(df[FEATURE_COLS].values)
    y_full = df["label"].values

    full_scale_pos_weight = float((y_full == 0).sum() / (y_full == 1).sum())
    print(f"  Full dataset: {len(y_full)} samples, scale_pos_weight={full_scale_pos_weight:.4f}")

    xgb_final = XGBClassifier(
        **xgb_params,
        scale_pos_weight=full_scale_pos_weight,
        objective="binary:logistic",
        random_state=42,
        n_jobs=1,
        verbosity=0,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        xgb_final.fit(X_full, y_full)
    print("  XGBoost base model: fit on full dataset")

    lgb_final = LGBMClassifier(
        **lgb_params,
        class_weight="balanced",
        objective="binary",
        random_state=42,
        n_jobs=1,
        verbose=-1,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lgb_final.fit(X_full, y_full)
    print("  LightGBM base model: fit on full dataset")

    lr_final = LogisticRegression(
        C=lr_best_C,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    lr_final.fit(X_full, y_full)
    print("  Logistic Regression base model: fit on full dataset")

    # Phase 5: Create TwoTierEnsemble
    print("\n" + "=" * 60)
    print("Phase 5: Creating TwoTierEnsemble")
    print("=" * 60)

    ensemble = TwoTierEnsemble(
        scaler=full_scaler,
        xgb=xgb_final,
        lgb=lgb_final,
        lr_base=lr_final,
        meta_lr=meta_lr,
    )

    metadata: dict[str, Any] = {
        "oof_ensemble_brier": oof_ensemble_brier,
        "oof_brier_per_year": oof_brier_per_year,
        "meta_coefficients": meta_coefs,
        "meta_intercept": meta_intercept,
        "n_oof_samples": int(total_oof),
        "oof_labels_raw": [int(x) for x in oof_labels],
        "oof_meta_raw": p_meta_raw.tolist(),
        "oof_meta_clipped": p_meta_clipped.tolist(),
    }

    print(f"  TwoTierEnsemble created successfully")
    print(f"  OOF samples: {total_oof}")
    print(f"  OOF Ensemble Brier: {oof_ensemble_brier:.4f}")

    return ensemble, metadata


def plot_calibration(
    y_true: list[int] | np.ndarray,
    y_prob_before: list[float] | np.ndarray,
    y_prob_after: list[float] | np.ndarray,
    save_path: str = "models/ensemble_calibration_curve.png",
) -> None:
    """Plot calibration curves before and after probability clipping.

    Args:
        y_true: True binary labels (0 or 1).
        y_prob_before: Predicted probabilities before clipping.
        y_prob_after: Predicted probabilities after clipping.
        save_path: Path to save the PNG figure.
    """
    y_true = np.array(y_true)
    y_prob_before = np.array(y_prob_before)
    y_prob_after = np.array(y_prob_after)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Ensemble Calibration Curves (OOF Predictions)", fontsize=14)

    # Panel 1: Before clipping
    ax1 = axes[0]
    fraction_of_positives_before, mean_predicted_before = calibration_curve(
        y_true, y_prob_before, n_bins=10, strategy="uniform"
    )
    ax1.plot(
        mean_predicted_before,
        fraction_of_positives_before,
        "s-",
        label="Ensemble (raw)",
        color="tab:blue",
    )
    ax1.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax1.axvline(x=CLIP_LO, color="gray", linestyle=":", alpha=0.7, label=f"Clip bounds ({CLIP_LO}, {CLIP_HI})")
    ax1.axvline(x=CLIP_HI, color="gray", linestyle=":", alpha=0.7)
    ax1.set_xlabel("Mean Predicted Probability")
    ax1.set_ylabel("Fraction of Positives")
    ax1.set_title("Before Clipping")
    ax1.legend(fontsize=9)
    ax1.set_xlim([0, 1])
    ax1.set_ylim([0, 1])

    max_dev_before = float(
        np.max(np.abs(fraction_of_positives_before - mean_predicted_before))
    )
    ax1.text(
        0.05, 0.95,
        f"Max deviation: {max_dev_before:.4f}",
        transform=ax1.transAxes,
        va="top",
        fontsize=10,
    )

    # Panel 2: After clipping
    ax2 = axes[1]
    fraction_of_positives_after, mean_predicted_after = calibration_curve(
        y_true, y_prob_after, n_bins=10, strategy="uniform"
    )
    ax2.plot(
        mean_predicted_after,
        fraction_of_positives_after,
        "s-",
        label="Ensemble (clipped)",
        color="tab:orange",
    )
    ax2.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax2.axvline(x=CLIP_LO, color="gray", linestyle=":", alpha=0.7, label=f"Clip bounds ({CLIP_LO}, {CLIP_HI})")
    ax2.axvline(x=CLIP_HI, color="gray", linestyle=":", alpha=0.7)
    ax2.set_xlabel("Mean Predicted Probability")
    ax2.set_ylabel("Fraction of Positives")
    ax2.set_title("After Clipping")
    ax2.legend(fontsize=9)
    ax2.set_xlim([0, 1])
    ax2.set_ylim([0, 1])

    max_dev_after = float(
        np.max(np.abs(fraction_of_positives_after - mean_predicted_after))
    )
    ax2.text(
        0.05, 0.95,
        f"Max deviation: {max_dev_after:.4f}",
        transform=ax2.transAxes,
        va="top",
        fontsize=10,
    )

    plt.tight_layout()

    # Save figure
    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"\nCalibration curve saved to: {save_path}")
    print(f"  Before clipping -- max deviation: {max_dev_before:.4f}")
    print(f"  After clipping  -- max deviation: {max_dev_after:.4f}")

    # Per-bin deviation table
    print("\nCalibration deviation per bin (after clipping):")
    print(f"  {'Mean Predicted':>16} | {'Fraction Positive':>18} | {'Deviation':>10}")
    print(f"  {'-' * 16} | {'-' * 18} | {'-' * 10}")
    for mp, fp in zip(mean_predicted_after, fraction_of_positives_after):
        dev = fp - mp
        print(f"  {mp:>16.4f} | {fp:>18.4f} | {dev:>+10.4f}")

    quality = "SUCCESS" if max_dev_after < 0.05 else ("MODERATE" if max_dev_after < 0.10 else "POOR")
    print(f"\nCalibration quality (after clipping): {quality} (max_dev={max_dev_after:.4f})")


def save_artifact(
    artifact: dict[str, Any],
    save_path: str = "models/ensemble.joblib",
) -> None:
    """Save ensemble artifact with proper module path for pickle compatibility.

    When called from __main__, Python pickles TwoTierEnsemble as '__main__.TwoTierEnsemble'.
    This helper re-imports the class from src.models.ensemble to ensure the artifact
    uses the stable module path 'src.models.ensemble.TwoTierEnsemble', which allows
    loading from any context (e.g., `python -c "import joblib; joblib.load(...)"`)
    without needing src.models.ensemble to be imported first.

    This mirrors the technique used in train_logistic.py for ClippedCalibrator,
    where the calibrator is stored as a plain dict spec to avoid the same issue.

    Note: TwoTierEnsemble is stored as an object (not a spec) because downstream
    callers (backtest, bracket simulator) call ensemble.predict_proba() directly.
    The module-path fix is done by re-importing and re-instantiating from the
    stable module path.

    Args:
        artifact: Dict containing 'ensemble' (TwoTierEnsemble) and all metadata.
        save_path: Output path. Default: models/ensemble.joblib.
    """
    import importlib
    import sys

    # Ensure src.models.ensemble is loaded under its stable module path
    # This overwrites the __main__ registration so pickle uses the correct path
    if "src.models.ensemble" not in sys.modules:
        mod = importlib.import_module("src.models.ensemble")
        sys.modules["src.models.ensemble"] = mod

    # Re-bind TwoTierEnsemble to the module-path version
    # The ensemble object's class is __main__.TwoTierEnsemble; we need it to be
    # src.models.ensemble.TwoTierEnsemble for portability
    StableTwoTierEnsemble = sys.modules["src.models.ensemble"].TwoTierEnsemble

    old_ens = artifact["ensemble"]
    stable_ens = StableTwoTierEnsemble(
        scaler=old_ens.scaler,
        xgb=old_ens.xgb,
        lgb=old_ens.lgb,
        lr_base=old_ens.lr_base,
        meta_lr=old_ens.meta_lr,
        clip_lo=old_ens.clip_lo,
        clip_hi=old_ens.clip_hi,
    )

    artifact_out = {**artifact, "ensemble": stable_ens}
    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact_out, save_path)
    print(f"  Artifact saved to: {save_path}")
    print(f"  TwoTierEnsemble pickle path: {StableTwoTierEnsemble.__module__}.{StableTwoTierEnsemble.__name__}")


if __name__ == "__main__":
    import pathlib

    print("Building matchup dataset...")
    df = build_matchup_dataset()
    print(f"\nDataset: {len(df)} matchups across {df['Season'].nunique()} seasons")
    print(f"Season range: {df['Season'].min()} - {df['Season'].max()}")

    # Load hyperparameters from Phase 06-01 and 06-02 artifacts
    print("\nLoading hyperparameters from model artifacts...")
    with open("models/xgb_params.json") as f:
        xgb_params = json.load(f)
    print(f"  XGB params: n_estimators={xgb_params['n_estimators']}, "
          f"max_depth={xgb_params['max_depth']}, "
          f"lr={xgb_params['learning_rate']:.4f}")

    with open("models/lgb_params.json") as f:
        lgb_params = json.load(f)
    print(f"  LGB params: num_leaves={lgb_params['num_leaves']}, "
          f"n_estimators={lgb_params['n_estimators']}, "
          f"lr={lgb_params['learning_rate']:.4f}")

    lr_artifact = joblib.load("models/logistic_baseline.joblib")
    lr_best_C = float(lr_artifact["best_C"])
    print(f"  LR best_C: {lr_best_C:.4f}")

    # Build ensemble via manual OOF temporal stacking
    print("\n")
    ensemble, metadata = build_ensemble(df, xgb_params, lgb_params, lr_best_C)

    # Plot calibration curves
    print("\n")
    plot_calibration(
        y_true=metadata["oof_labels_raw"],
        y_prob_before=metadata["oof_meta_raw"],
        y_prob_after=metadata["oof_meta_clipped"],
        save_path="models/ensemble_calibration_curve.png",
    )

    # Save ensemble artifact
    print("\n" + "=" * 60)
    print("Saving ensemble artifact to models/ensemble.joblib")
    print("=" * 60)

    artifact = {
        "model": "ensemble",
        "xgb_params": xgb_params,
        "lgb_params": lgb_params,
        "lr_best_C": lr_best_C,
        "ensemble": ensemble,
        "scaler": ensemble.scaler,
        "feature_names": FEATURE_COLS,
        "clip_lo": float(CLIP_LO),
        "clip_hi": float(CLIP_HI),
        "train_seasons": sorted(df["Season"].unique().tolist()),
        "oof_brier": metadata["oof_ensemble_brier"],
        "oof_brier_per_year": metadata["oof_brier_per_year"],
        "meta_coefficients": metadata["meta_coefficients"],
        # OOF data stored for downstream verification and calibration plots
        "oof_labels_raw": metadata["oof_labels_raw"],
        "oof_meta_clipped": metadata["oof_meta_clipped"],
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "lightgbm_version": lightgbm.__version__,
    }

    # Use save_artifact() to ensure TwoTierEnsemble is pickled under the stable
    # module path (src.models.ensemble.TwoTierEnsemble), not __main__.TwoTierEnsemble
    save_artifact(artifact, "models/ensemble.joblib")

    print(f"\nArtifact saved successfully")
    print(f"  OOF Ensemble Brier: {metadata['oof_ensemble_brier']:.4f} (baseline: 0.1900)")
    print(f"  OOF samples: {metadata['n_oof_samples']}")
    print(f"  Meta-learner coefficients: {[f'{c:.4f}' for c in metadata['meta_coefficients']]}")
    print(f"  Train seasons: {artifact['train_seasons']}")
    print(f"  sklearn: {sklearn.__version__}")
    print(f"  xgboost: {xgboost.__version__}")
    print(f"  lightgbm: {lightgbm.__version__}")

    # Quick smoke test
    print("\n--- Smoke test ---")
    loaded = joblib.load("models/ensemble.joblib")
    assert loaded["model"] == "ensemble"
    ens = loaded["ensemble"]
    X_smoke = np.random.default_rng(42).standard_normal((5, 6))
    probs = ens.predict_proba(X_smoke)
    assert probs.shape == (5, 2), f"Wrong shape: {probs.shape}"
    assert np.all(probs[:, 1] >= CLIP_LO), f"Below clip_lo"
    assert np.all(probs[:, 1] <= CLIP_HI), f"Above clip_hi"
    assert np.allclose(probs.sum(axis=1), 1.0), f"Rows don't sum to 1"
    print(f"Smoke test PASSED -- predict_proba() shape={probs.shape}, "
          f"probs[:, 1] in [{probs[:, 1].min():.4f}, {probs[:, 1].max():.4f}]")

    print("\nAll checks passed. Ensemble artifact ready for Phase 06-04 (backtest).")
