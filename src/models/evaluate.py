"""
Evaluation pipeline for the logistic regression NCAA tournament baseline model.

Computes Brier score and log-loss per holdout year using walk-forward temporal
cross-validation, compares against the hard-chalk baseline (always pick the
higher seed), generates a calibration curve reliability diagram, and validates
that the model does not produce overconfident predictions for top-seed matchups.

This answers the critical question: "Does the baseline model beat naive seed-based
predictions?" The evaluation results (models/evaluation_results.json) become the
first row in the Phase 7 model comparison dashboard.

Exports:
    compute_chalk_brier()          - Hard-chalk Brier score (always pick higher seed)
    evaluate_all_holdout_years()   - Walk-forward per-year evaluation pipeline
    check_calibration()            - Reliability diagram generation and bin stats
    check_top_seed_overconfidence() - Validates no > 90% predictions for top-10 seeds
"""

from __future__ import annotations

import json
import pathlib
import warnings

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving to file
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, CalibrationDisplay, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

import joblib


def compute_chalk_brier(y_true: np.ndarray) -> float:
    """Compute the hard-chalk Brier score (always predict the higher seed wins with P=1.0).

    Since label=1 means the higher seed (team_a) won, the chalk prediction is
    always P=1.0. This gives the Brier score for a strategy that always picks the
    better seed with full confidence — a useful baseline to compare the model against.

    Args:
        y_true: Binary array of actual outcomes (1=higher seed won, 0=upset).

    Returns:
        Brier score for the all-chalk prediction (float).
    """
    chalk_prob = np.ones(len(y_true))
    return float(brier_score_loss(y_true, chalk_prob))


def evaluate_all_holdout_years(
    model_path: str = "models/logistic_baseline.joblib",
    processed_dir: str = "data/processed",
) -> tuple[dict, pd.DataFrame, np.ndarray, np.ndarray]:
    """Run walk-forward evaluation on all holdout years (2022-2025).

    For honest evaluation, this function re-fits a NEW StandardScaler and
    LogisticRegression on each training fold using only data before the holdout
    year. The best_C from the saved artifact is used (it was selected without
    leakage in 03-02), but the model itself is not used for prediction — it is
    only used to retrieve the best_C.

    This is the correct walk-forward evaluation: model is re-fit per fold using
    only past data, so test-set statistics never influence the scaler.

    Args:
        model_path: Path to the saved joblib artifact.
        processed_dir: Directory containing processed parquet files.

    Returns:
        Tuple of (results_dict, matchup_df, y_true_all, y_prob_all) where:
            - results_dict: Per-year metrics + summary stats
            - matchup_df: Full matchup DataFrame
            - y_true_all: Concatenated true labels across all folds
            - y_prob_all: Concatenated predicted probabilities across all folds
    """
    from src.models.features import FEATURE_COLS, build_matchup_dataset
    from src.models.temporal_cv import BACKTEST_YEARS, walk_forward_splits
    from src.models.train_logistic import load_model

    # Load artifact to get best_C — we do NOT use the scaler/model for evaluation
    artifact = joblib.load(model_path)
    best_C = artifact["best_C"]
    print(f"Loaded artifact: best_C={best_C:.6f}")

    # Build matchup dataset (suppresses verbose output)
    print("\nBuilding matchup dataset...")
    df = build_matchup_dataset(processed_dir)
    print(f"Dataset: {len(df)} matchups across {df['Season'].nunique()} seasons")

    per_year_results = []
    y_true_all = []
    y_prob_all = []

    for test_year, train_df, test_df in walk_forward_splits(df):
        X_train = train_df[FEATURE_COLS].values
        y_train = train_df["label"].values
        X_test = test_df[FEATURE_COLS].values
        y_test = test_df["label"].values

        # Fit NEW scaler on training fold ONLY — prevents test-set leakage
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Fit NEW model with same C parameter (selected without leakage in 03-02)
        clf = LogisticRegression(
            C=best_C,
            class_weight="balanced",
            solver="lbfgs",
            max_iter=1000,
            random_state=42,
        )
        clf.fit(X_train_scaled, y_train)

        # Post-hoc isotonic calibration — compresses extreme probabilities
        calibrated_clf = CalibratedClassifierCV(clf, method="isotonic", cv="prefit")
        calibrated_clf.fit(X_train_scaled, y_train)

        # Predict calibrated probabilities on holdout test set
        y_prob = calibrated_clf.predict_proba(X_test_scaled)[:, 1]
        y_pred_class = (y_prob >= 0.5).astype(int)

        # Compute all metrics
        brier = float(brier_score_loss(y_test, y_prob))
        ll = float(log_loss(y_test, y_prob))
        chalk_brier = compute_chalk_brier(y_test)
        accuracy = float((y_pred_class == y_test).mean())
        n_test = int(len(y_test))
        n_upsets = int((y_test == 0).sum())
        upset_correct = int(((y_prob < 0.5) & (y_test == 0)).sum())

        per_year_results.append({
            "year": test_year,
            "n_games": n_test,
            "brier": brier,
            "chalk_brier": chalk_brier,
            "brier_delta": chalk_brier - brier,  # positive = model beats chalk
            "log_loss": ll,
            "accuracy": accuracy,
            "n_upsets": n_upsets,
            "upset_correct": upset_correct,
        })

        # Accumulate for calibration plot
        y_true_all.extend(y_test.tolist())
        y_prob_all.extend(y_prob.tolist())

    y_true_all = np.array(y_true_all)
    y_prob_all = np.array(y_prob_all)

    # Compute aggregate statistics
    mean_brier = float(np.mean([r["brier"] for r in per_year_results]))
    mean_chalk = float(np.mean([r["chalk_brier"] for r in per_year_results]))
    mean_ll = float(np.mean([r["log_loss"] for r in per_year_results]))
    mean_acc = float(np.mean([r["accuracy"] for r in per_year_results]))
    total_games = sum(r["n_games"] for r in per_year_results)
    total_upsets = sum(r["n_upsets"] for r in per_year_results)
    total_upset_correct = sum(r["upset_correct"] for r in per_year_results)
    beats_chalk_every_year = all(r["brier"] < r["chalk_brier"] for r in per_year_results)

    # Print formatted comparison table
    print("\n" + "=" * 70)
    print("=== BASELINE MODEL EVALUATION (Walk-Forward) ===")
    print("=" * 70)
    print()
    header = (
        f"{'Year':>4} | {'Games':>5} | {'Brier':>6} | {'Chalk':>6} | "
        f"{'Delta':>6} | {'LogLoss':>7} | {'Accuracy':>8} | {'Upsets':>6} | {'Upset Hit':>9}"
    )
    separator = "-" * len(header)
    print(header)
    print(separator)
    for r in per_year_results:
        delta_str = f"+{r['brier_delta']:.4f}" if r['brier_delta'] >= 0 else f"{r['brier_delta']:.4f}"
        print(
            f"{r['year']:>4} | {r['n_games']:>5} | {r['brier']:>6.4f} | "
            f"{r['chalk_brier']:>6.4f} | {delta_str:>6} | {r['log_loss']:>7.4f} | "
            f"{r['accuracy']:>7.1%} | {r['n_upsets']:>6} | {r['upset_correct']:>9}"
        )
    print(separator)
    mean_delta = mean_chalk - mean_brier
    mean_delta_str = f"+{mean_delta:.4f}" if mean_delta >= 0 else f"{mean_delta:.4f}"
    print(
        f"{'Mean':>4} | {total_games:>5} | {mean_brier:>6.4f} | "
        f"{mean_chalk:>6.4f} | {mean_delta_str:>6} | {mean_ll:>7.4f} | "
        f"{mean_acc:>7.1%} | {total_upsets:>6} | {total_upset_correct:>9}"
    )
    print()
    threshold_status = "PASS" if mean_brier < 0.23 else "FAIL"
    print(f"Threshold: Brier < 0.23 — {threshold_status} (mean={mean_brier:.4f})")
    chalk_status = "YES" if beats_chalk_every_year else "NO"
    print(f"Model beats chalk every year: {chalk_status}")
    print()

    results = {
        "model": "logistic_baseline",
        "best_C": float(best_C),
        "per_year": per_year_results,
        "mean_brier": mean_brier,
        "mean_log_loss": mean_ll,
        "mean_accuracy": mean_acc,
        "beats_chalk_every_year": beats_chalk_every_year,
        "below_023_threshold": mean_brier < 0.23,
        "no_overconfident_top_seed": None,  # placeholder — filled after overconfidence check
    }

    # Write initial results to JSON (will be updated after overconfidence check)
    out_path = pathlib.Path("models/evaluation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Results written to {out_path}")

    return results, df, y_true_all, y_prob_all


def check_calibration(
    y_true_all: np.ndarray,
    y_prob_all: np.ndarray,
    save_path: str = "models/calibration_curve.png",
) -> None:
    """Generate and save a calibration reliability diagram.

    Plots predicted probabilities vs. actual win rates across 10 uniform bins
    to visualize how well the model's probabilities are calibrated. A perfectly
    calibrated model would lie exactly on the diagonal.

    Args:
        y_true_all: Concatenated true labels across all holdout folds.
        y_prob_all: Concatenated predicted probabilities across all holdout folds.
        save_path: Output path for the PNG file.
    """
    fig, ax = plt.subplots(figsize=(8, 6))

    disp = CalibrationDisplay.from_predictions(
        y_true_all,
        y_prob_all,
        n_bins=10,
        strategy="uniform",
        name="Logistic Baseline",
        ax=ax,
    )

    ax.set_title("Calibration Curve - Logistic Baseline (2022-2025 Holdout)", fontsize=13)
    ax.set_xlabel("Mean Predicted Probability", fontsize=11)
    ax.set_ylabel("Fraction of Positives (Actual Win Rate)", fontsize=11)
    ax.grid(True, alpha=0.3)

    save_path_obj = pathlib.Path(save_path)
    save_path_obj.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path_obj, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Calibration curve saved to {save_path_obj}")

    # Print bin-level summary
    prob_true, prob_pred = calibration_curve(
        y_true_all, y_prob_all, n_bins=10, strategy="uniform"
    )
    print("\nCalibration bin summary (predicted vs. actual win rate):")
    print(f"{'Bin':>4} | {'Predicted':>10} | {'Actual':>8} | {'Deviation':>10}")
    print("-" * 42)
    for i, (pred, actual) in enumerate(zip(prob_pred, prob_true)):
        deviation = pred - actual
        print(f"{i+1:>4} | {pred:>10.4f} | {actual:>8.4f} | {deviation:>+10.4f}")

    max_deviation = float(np.max(np.abs(prob_pred - prob_true)))
    print(f"\nMax deviation from perfect calibration: {max_deviation:.4f}")
    if max_deviation < 0.05:
        print("Calibration quality: EXCELLENT (max deviation < 0.05)")
    elif max_deviation < 0.10:
        print("Calibration quality: GOOD (max deviation < 0.10)")
    else:
        print(f"Calibration quality: MODERATE (max deviation = {max_deviation:.4f})")


def check_top_seed_overconfidence(
    df: pd.DataFrame,
    artifact: dict,
    processed_dir: str = "data/processed",
) -> bool:
    """Check that no top-10-seeded matchup receives a win probability > 90%.

    Filters the matchup dataset to games where both teams are seeded 1-10
    (i.e., late-round games between strong teams). For each such game, computes
    the model's predicted probability and flags any predictions above 0.90.

    The model is re-fit on ALL available data (consistent with evaluate_all_holdout_years
    fold approach, here we use the full dataset to check production-like behavior).

    Args:
        df: Full matchup DataFrame from build_matchup_dataset().
        artifact: The joblib artifact dict (used for best_C).
        processed_dir: Directory containing processed parquet files.

    Returns:
        True if all top-seed matchup probabilities are < 0.90, False if any exceed it.
    """
    from src.models.features import FEATURE_COLS

    best_C = artifact["best_C"]

    # Filter to top-10 vs top-10 matchups only
    top_seed_mask = (df["team_a_seed"] <= 10) & (df["team_b_seed"] <= 10)
    top_seed_df = df[top_seed_mask].copy()

    if len(top_seed_df) == 0:
        print("WARNING: No top-10 seed matchups found in dataset")
        return True

    print(f"\nChecking overconfidence for top-10 seed matchups...")
    print(f"Total top-10 seed matchups in dataset: {len(top_seed_df)}")

    # Fit model on full dataset (production-like behavior check)
    X_all = df[FEATURE_COLS].values
    y_all = df["label"].values

    scaler = StandardScaler()
    X_all_scaled = scaler.fit_transform(X_all)

    clf = LogisticRegression(
        C=best_C,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    clf.fit(X_all_scaled, y_all)

    # Post-hoc isotonic calibration — compresses extreme probabilities
    calibrated_clf = CalibratedClassifierCV(clf, method="isotonic", cv="prefit")
    calibrated_clf.fit(X_all_scaled, y_all)

    # Predict calibrated probabilities for top-seed matchups
    X_top = top_seed_df[FEATURE_COLS].values
    X_top_scaled = scaler.transform(X_top)
    y_prob_top = calibrated_clf.predict_proba(X_top_scaled)[:, 1]

    max_prob = float(y_prob_top.max())
    min_prob = float(y_prob_top.min())
    n_overconfident = int((y_prob_top > 0.90).sum())

    print(f"Max predicted probability:  {max_prob:.4f}")
    print(f"Min predicted probability:  {min_prob:.4f}")
    print(f"Games with P > 0.90:        {n_overconfident}")

    if n_overconfident > 0:
        print(f"\nWARNING: {n_overconfident} top-10-seed matchup(s) have P > 0.90!")
        # Print the offending matchups
        overconf_mask = y_prob_top > 0.90
        overconf_df = top_seed_df[overconf_mask].copy()
        overconf_df["predicted_prob"] = y_prob_top[overconf_mask]
        print("Overconfident predictions:")
        for _, row in overconf_df.iterrows():
            print(
                f"  Season={row['Season']}, "
                f"team_a_seed={row['team_a_seed']}, "
                f"team_b_seed={row['team_b_seed']}, "
                f"P={row['predicted_prob']:.4f}"
            )
        return False

    print(f"PASS: No top-10-seed matchup has P > 0.90")
    return True


if __name__ == "__main__":
    import sys

    # ===== STEP 1: Walk-forward evaluation =====
    results, df, y_true_all, y_prob_all = evaluate_all_holdout_years()

    # ===== STEP 2: Calibration curve =====
    check_calibration(y_true_all, y_prob_all)

    # ===== STEP 3: Overconfidence check =====
    artifact = joblib.load("models/logistic_baseline.joblib")
    overconfidence_passed = check_top_seed_overconfidence(df, artifact)

    # ===== STEP 4: Update JSON with overconfidence result =====
    results["no_overconfident_top_seed"] = overconfidence_passed
    out_path = pathlib.Path("models/evaluation_results.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nUpdated {out_path} with overconfidence check result")

    # ===== STEP 5: Phase 3 success criteria check =====
    print("\n" + "=" * 50)
    print("=== PHASE 3 SUCCESS CRITERIA CHECK ===")
    print("=" * 50)

    # Criterion 1: Model file exists
    model_exists = pathlib.Path("models/logistic_baseline.joblib").exists()
    crit1 = "PASS" if model_exists else "FAIL"
    print(f"[{crit1}] 1. Model file exists at models/logistic_baseline.joblib")

    # Criterion 2: Walk-forward CV with 4 distinct non-overlapping holdout years
    n_years = len(results["per_year"])
    crit2 = "PASS" if n_years == 4 else "FAIL"
    print(f"[{crit2}] 2. Walk-forward CV: {n_years} distinct non-overlapping holdout years")

    # Criterion 3: Mean Brier < 0.23
    crit3 = "PASS" if results["below_023_threshold"] else "FAIL"
    print(f"[{crit3}] 3. Mean Brier score < 0.23 (actual: {results['mean_brier']:.4f})")

    # Criterion 4: No top-seed overconfidence
    crit4 = "PASS" if results["no_overconfident_top_seed"] else "FAIL"
    print(f"[{crit4}] 4. No top-seed matchup has > 90% win probability")

    all_pass = all([model_exists, n_years == 4, results["below_023_threshold"], results["no_overconfident_top_seed"]])
    print()
    if all_pass:
        print("All Phase 3 success criteria: PASS")
    else:
        print("Some Phase 3 criteria: FAIL — see details above")
        # Don't exit with error; caller decides what to do
