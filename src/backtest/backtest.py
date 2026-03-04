"""
Backtest orchestration for NCAA tournament bracket prediction.

Orchestrates the full feature-to-simulator-to-scoring pipeline across the
2022-2025 tournament seasons with strict temporal isolation.

Supports two models:
- 'baseline': LogisticRegression (ClippedCalibrator), per-fold re-fit.
- 'ensemble': TwoTierEnsemble (XGB + LGB + LR + meta-LR), per-fold rebuild
  with nested sub-fold OOF for the meta-learner. The full-dataset
  models/ensemble.joblib is NOT used -- each fold builds its own ensemble
  from scratch using only Season < test_year data.

Per-year protocol (baseline):
1. Re-fit StandardScaler + LogisticRegression(C=best_C) + ClippedCalibrator
   using only Season < test_year training data -- never uses the saved model
   artifact's scaler or model for predictions (only extracts best_C).
2. Build a per-year predict_fn closure that calls compute_features() with a
   try/except returning 0.5 for missing teams (First Four edge case).
3. Simulate the bracket deterministically via simulate_bracket(mode='deterministic').
4. Score against actual results via build_actual_slot_winners() + score_bracket().
5. Compute game-level metrics (Brier, log-loss, accuracy, upset detection) via
   compute_game_metrics() using the fold-specific scaler and calibrator.
6. Write backtest/results.json with per_year array and summary aggregates.

Per-year protocol (ensemble):
1. Call _build_fold_ensemble(train_df, xgb_params, lgb_params, best_C) to
   build a fold-specific TwoTierEnsemble using only Season < test_year data.
   The meta-learner is trained on OOF from the last 3 seasons in train_df.
2. Build predict_fn using fold_scaler.transform() + ensemble.predict_proba()
   (factory pattern prevents late-binding closure bug).
3. Steps 3-5 identical to baseline; compute_game_metrics receives fold_ensemble
   as calibrated_clf (satisfies predict_proba() interface).
4. Write backtest/ensemble_results.json (separate from baseline results.json).

Exports:
    backtest()    - Main orchestration function
"""

from __future__ import annotations

import json
import pathlib
import warnings
from datetime import date
from typing import Any

import joblib
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.backtest.scoring import (
    build_actual_slot_winners,
    compute_game_metrics,
    score_bracket,
)
from src.models.ensemble import TwoTierEnsemble
from src.models.features import (
    FEATURE_COLS,
    build_matchup_dataset,
    build_stats_lookup,
    compute_features,
)
from src.models.temporal_cv import BACKTEST_YEARS
from src.models.train_logistic import CLIP_HI, CLIP_LO, ClippedCalibrator
from src.simulator.bracket_schema import load_seedings
from src.simulator.simulate import simulate_bracket

# ---------------------------------------------------------------------------
# Default data paths
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_PATH = "models/logistic_baseline.joblib"
_DEFAULT_PROCESSED_DIR = "data/processed"
_DEFAULT_SEED_ROUND_SLOTS_CSV = "data/raw/kaggle/MNCAATourneySeedRoundSlots.csv"
_DEFAULT_SLOTS_CSV = "data/raw/kaggle/MNCAATourneySlots.csv"
_DEFAULT_OUTPUT_PATH = "backtest/results.json"
_DEFAULT_ENSEMBLE_OUTPUT_PATH = "backtest/ensemble_results.json"


# ---------------------------------------------------------------------------
# _build_fold_ensemble
# ---------------------------------------------------------------------------


def _build_fold_ensemble(
    train_df: "pd.DataFrame",
    xgb_params: dict,
    lgb_params: dict,
    lr_best_C: float,
) -> tuple[TwoTierEnsemble, StandardScaler]:
    """Build a temporally isolated ensemble for one backtest fold.

    The meta-learner is trained on sub-fold OOF predictions collected from
    the last 3 available seasons in train_df (nested temporal isolation).
    All 3 base models are then re-fit on the full train_df before creating
    the TwoTierEnsemble.

    This function does NOT use models/ensemble.joblib -- the fold ensemble
    is built entirely from scratch using only pre-test_year data.

    Args:
        train_df: Training data with Season < test_year (temporal isolation).
        xgb_params: XGBoost hyperparameters (from models/xgb_params.json).
        lgb_params: LightGBM hyperparameters (from models/lgb_params.json).
        lr_best_C: Best regularization C for the LR base model.

    Returns:
        Tuple of (fold_ensemble, fold_scaler) where:
            fold_ensemble: TwoTierEnsemble fitted on train_df.
            fold_scaler: StandardScaler fitted on train_df (for predict_fn scaling).
    """
    import pandas as pd  # noqa: F401 (type annotation only)

    available_seasons = sorted(train_df["Season"].unique())
    meta_sub_years = available_seasons[-3:]

    oof_xgb: list[float] = []
    oof_lgb: list[float] = []
    oof_lr: list[float] = []
    oof_labels: list[int] = []

    # --- Sub-fold OOF collection for meta-learner training ---
    for sub_year in meta_sub_years:
        sub_train = train_df[train_df["Season"] < sub_year]
        sub_test = train_df[train_df["Season"] == sub_year]

        if len(sub_train) == 0 or len(sub_test) == 0:
            continue

        sub_scaler = StandardScaler()
        X_sub_train = sub_scaler.fit_transform(sub_train[FEATURE_COLS].values)
        X_sub_test = sub_scaler.transform(sub_test[FEATURE_COLS].values)
        y_sub_train = sub_train["label"].values
        y_sub_test = sub_test["label"].values

        spw = float((y_sub_train == 0).sum() / (y_sub_train == 1).sum())

        xgb_sub = XGBClassifier(
            **xgb_params,
            scale_pos_weight=spw,
            objective="binary:logistic",
            random_state=42,
            n_jobs=1,
            verbosity=0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            xgb_sub.fit(X_sub_train, y_sub_train)

        lgb_sub = LGBMClassifier(
            **lgb_params,
            class_weight="balanced",
            objective="binary",
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lgb_sub.fit(X_sub_train, y_sub_train)

        lr_sub = LogisticRegression(
            C=lr_best_C,
            class_weight="balanced",
            solver="lbfgs",
            max_iter=1000,
            random_state=42,
        )
        lr_sub.fit(X_sub_train, y_sub_train)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            oof_xgb.extend(xgb_sub.predict_proba(X_sub_test)[:, 1].tolist())
            oof_lgb.extend(lgb_sub.predict_proba(X_sub_test)[:, 1].tolist())
        oof_lr.extend(
            ClippedCalibrator(lr_sub).predict_proba(X_sub_test)[:, 1].tolist()
        )
        oof_labels.extend(y_sub_test.tolist())

    # --- Train meta-learner on sub-fold OOF ---
    X_meta = np.column_stack([oof_xgb, oof_lgb, oof_lr])
    y_meta = np.array(oof_labels)
    meta_lr = LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=1000, random_state=42
    )
    meta_lr.fit(X_meta, y_meta)

    # --- Refit all 3 base models on the full train_df ---
    fold_scaler = StandardScaler()
    X_train_scaled = fold_scaler.fit_transform(train_df[FEATURE_COLS].values)
    y_train = train_df["label"].values
    spw_full = float((y_train == 0).sum() / (y_train == 1).sum())

    xgb_final = XGBClassifier(
        **xgb_params,
        scale_pos_weight=spw_full,
        objective="binary:logistic",
        random_state=42,
        n_jobs=1,
        verbosity=0,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        xgb_final.fit(X_train_scaled, y_train)

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
        lgb_final.fit(X_train_scaled, y_train)

    lr_final = LogisticRegression(
        C=lr_best_C,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    lr_final.fit(X_train_scaled, y_train)

    fold_ensemble = TwoTierEnsemble(
        scaler=fold_scaler,
        xgb=xgb_final,
        lgb=lgb_final,
        lr_base=lr_final,
        meta_lr=meta_lr,
    )
    return fold_ensemble, fold_scaler


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------


def backtest(
    year_range: list[int] | None = None,
    model: str = "baseline",
    model_path: str = _DEFAULT_MODEL_PATH,
    processed_dir: str = _DEFAULT_PROCESSED_DIR,
    seed_round_slots_csv: str = _DEFAULT_SEED_ROUND_SLOTS_CSV,
    slots_csv: str = _DEFAULT_SLOTS_CSV,
    output_path: str = _DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Run the full backtest across historical tournament seasons.

    For each backtest year, re-fits a fold-specific model using ONLY data
    from seasons strictly before that year (temporal isolation). Simulates
    the bracket deterministically and scores against actual tournament results.

    Baseline model:
        Re-fits StandardScaler + LogisticRegression(C=best_C) + ClippedCalibrator.
        The saved artifact is used ONLY to extract best_C.

    Ensemble model:
        Calls _build_fold_ensemble() to build a TwoTierEnsemble per fold.
        The meta-learner is trained on OOF from the last 3 available seasons
        before test_year (nested temporal isolation). The full-dataset
        models/ensemble.joblib is NOT used for backtesting.

    Args:
        year_range: List of tournament years to evaluate. Defaults to
            BACKTEST_YEARS = [2022, 2023, 2024, 2025].
        model: Model identifier: 'baseline' or 'ensemble'.
        model_path: Path to the saved model artifact (for extracting best_C).
            Default: models/logistic_baseline.joblib.
        processed_dir: Directory containing .parquet files used by
            build_matchup_dataset() and build_stats_lookup().
            Default: data/processed.
        seed_round_slots_csv: Path to MNCAATourneySeedRoundSlots.csv used by
            build_actual_slot_winners().
            Default: data/raw/kaggle/MNCAATourneySeedRoundSlots.csv.
        slots_csv: Path to MNCAATourneySlots.csv used by simulate_bracket().
            Default: data/raw/kaggle/MNCAATourneySlots.csv.
        output_path: Destination for JSON results. Defaults to
            'backtest/results.json' for baseline; ensemble automatically
            uses 'backtest/ensemble_results.json' unless output_path is
            explicitly overridden.

    Returns:
        Dict with keys:
            'model' (str): Model identifier.
            'best_C' (float): Regularization parameter extracted from artifact.
            'years_evaluated' (list[int]): Years that were backtested.
            'per_year' (list[dict]): Per-year metrics dicts.
            'mean_brier' (float): Mean Brier score across all years.
            'mean_log_loss' (float): Mean log-loss across all years.
            'mean_accuracy' (float): Mean game-level accuracy across all years.
            'mean_espn_score' (float): Mean ESPN bracket score across all years.
            'generated_at' (str): ISO date string.

    Raises:
        ValueError: If model is not 'baseline' or 'ensemble'.
        FileNotFoundError: If model artifact or data files are missing.
    """
    # ------------------------------------------------------------------
    # Step 1: Validate inputs
    # ------------------------------------------------------------------
    if model not in ("baseline", "ensemble"):
        raise ValueError(
            f"Unsupported model: {model!r}. "
            "Supported: 'baseline', 'ensemble'."
        )

    # Ensemble uses a separate output file by default to preserve baseline results
    if model == "ensemble" and output_path == _DEFAULT_OUTPUT_PATH:
        output_path = _DEFAULT_ENSEMBLE_OUTPUT_PATH

    if year_range is None:
        year_range = BACKTEST_YEARS

    print("=" * 70)
    print("NCAA Tournament Bracket Backtest")
    print(f"  Model:  {model}")
    print(f"  Years:  {year_range}")
    print(f"  Output: {output_path}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Step 2: Load best_C from artifact ONLY (not the scaler or model)
    # ------------------------------------------------------------------
    artifact_path = pathlib.Path(model_path)
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {model_path}. "
            "Run src/models/train_logistic.py first."
        )

    artifact = joblib.load(model_path)
    best_C = float(artifact["best_C"])
    print(f"\nLoaded best_C={best_C:.6f} from {model_path}")
    print("  (Model/scaler from artifact NOT used for predictions -- per-fold refitting)")

    # ------------------------------------------------------------------
    # Step 2b: Load ensemble-specific params (if model == 'ensemble')
    # ------------------------------------------------------------------
    xgb_params: dict | None = None
    lgb_params: dict | None = None
    if model == "ensemble":
        xgb_params = json.loads(pathlib.Path("models/xgb_params.json").read_text())
        lgb_params = json.loads(pathlib.Path("models/lgb_params.json").read_text())
        print(f"  XGBoost params loaded from models/xgb_params.json")
        print(f"  LightGBM params loaded from models/lgb_params.json")

    # ------------------------------------------------------------------
    # Step 3: Build shared data structures (loaded once, used across all years)
    # ------------------------------------------------------------------
    print(f"\nBuilding matchup dataset from {processed_dir}...")
    df = build_matchup_dataset(processed_dir)

    print(f"\nBuilding stats lookup from {processed_dir}...")
    stats_lookup = build_stats_lookup(processed_dir)
    print(f"  Stats lookup: {len(stats_lookup)} (season, team_id) entries")

    # ------------------------------------------------------------------
    # Step 4: Per-year evaluation loop
    # ------------------------------------------------------------------
    per_year_results: list[dict[str, Any]] = []

    for test_year in year_range:
        print(f"\n{'─' * 70}")
        print(f"  Year: {test_year}")
        print(f"{'─' * 70}")

        # Step 4a: Temporal isolation -- training data is Season < test_year ONLY
        train_df = df[df["Season"] < test_year].copy()
        test_df = df[df["Season"] == test_year].copy()

        assert len(train_df) > 0, (
            f"No training data before {test_year}. "
            "Check that matchup dataset covers pre-2022 seasons."
        )
        assert train_df["Season"].max() < test_year, (
            f"DATA LEAKAGE: training data for {test_year} contains future seasons!"
        )

        print(f"  Training seasons: {sorted(train_df['Season'].unique())}")
        print(f"  Training games:   {len(train_df)}")
        print(f"  Test games:       {len(test_df)}")

        # -------------------------------------------------------------------
        # BASELINE branch: re-fit LR + ClippedCalibrator
        # -------------------------------------------------------------------
        if model == "baseline":
            # Step 4a (continued): Re-fit StandardScaler on training data ONLY
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(train_df[FEATURE_COLS].values)
            y_train = train_df["label"].values

            # Step 4a (continued): Re-fit LogisticRegression with best_C
            clf = LogisticRegression(
                C=best_C,
                class_weight="balanced",
                solver="lbfgs",
                max_iter=1000,
                random_state=42,
            )
            clf.fit(X_train_scaled, y_train)

            # Step 4a (continued): Wrap in ClippedCalibrator (no re-fit needed -- prefit)
            calibrated_clf = ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)

            print(
                f"  Model re-fit: C={best_C:.4f}, "
                f"clip=[{CLIP_LO}, {CLIP_HI}]"
            )

            # Step 4b: Build predict_fn closure (captures year-specific scaler/model)
            # Default args pattern binds current-loop variables at definition time,
            # preventing late-binding closure bugs.
            def make_predict_fn(
                _year: int = test_year,
                _scaler: StandardScaler = scaler,
                _clf: ClippedCalibrator = calibrated_clf,
            ):
                def predict_fn(team_a_id: int, team_b_id: int) -> float:
                    """Predict P(team_a beats team_b) using fold-specific model.

                    team_a_id must have the lower seed number (better seed).
                    Returns 0.5 for KeyError (missing teams -- First Four edge case).
                    """
                    try:
                        features = compute_features(
                            _year, team_a_id, team_b_id, stats_lookup
                        )
                    except KeyError:
                        # First Four teams or teams absent from stats_lookup
                        # (e.g., some small-school play-in participants)
                        return 0.5

                    x = np.array(
                        [features[col] for col in FEATURE_COLS], dtype=float
                    ).reshape(1, -1)
                    x_scaled = _scaler.transform(x)
                    return float(_clf.predict_proba(x_scaled)[0, 1])

                return predict_fn

            predict_fn = make_predict_fn()

        # -------------------------------------------------------------------
        # ENSEMBLE branch: build per-fold TwoTierEnsemble
        # -------------------------------------------------------------------
        elif model == "ensemble":
            print(f"  Building fold-specific ensemble (nested sub-fold OOF)...")
            fold_ensemble, fold_scaler = _build_fold_ensemble(
                train_df, xgb_params, lgb_params, best_C
            )
            calibrated_clf = fold_ensemble  # satisfies predict_proba() interface
            scaler = fold_scaler

            print(f"  Fold ensemble built successfully")

            # Factory pattern: binds fold_ensemble and fold_scaler at definition time
            # to prevent late-binding Python closure bug (all folds sharing last iteration)
            def make_ensemble_predict_fn(
                _year: int = test_year,
                _ensemble: TwoTierEnsemble = fold_ensemble,
                _scaler: StandardScaler = fold_scaler,
            ):
                """Create predict_fn for one ensemble backtest fold.

                IMPORTANT: _scaler.transform() is called by THIS function.
                TwoTierEnsemble.predict_proba() expects ALREADY-SCALED input
                (the ensemble stores self.scaler for reference only and does NOT
                call transform() internally). Do NOT add scaler.transform() inside
                predict_proba() or you will get double-scaling.
                """
                def predict_fn(team_a_id: int, team_b_id: int) -> float:
                    try:
                        features = compute_features(
                            _year, team_a_id, team_b_id, stats_lookup
                        )
                        x = np.array(
                            [features[col] for col in FEATURE_COLS], dtype=float
                        ).reshape(1, -1)
                        x_scaled = _scaler.transform(x)
                        return float(_ensemble.predict_proba(x_scaled)[0, 1])
                    except KeyError:
                        return 0.5

                return predict_fn

            predict_fn = make_ensemble_predict_fn()

        # Step 4c: Load year-specific seedings and simulate bracket
        seedings = load_seedings(season=test_year)
        print(f"  Seedings loaded: {len(seedings)} teams")

        bracket_result = simulate_bracket(
            seedings=seedings,
            predict_fn=predict_fn,
            mode="deterministic",
            season=test_year,
            slots_csv=slots_csv,
            stats_lookup=stats_lookup,
        )

        champion_id = bracket_result["champion"]["team_id"]
        print(f"  Predicted champion: team_id={champion_id}")

        # Step 4d: Build actual slot winners and score the bracket
        actual_winners = build_actual_slot_winners(
            season=test_year,
            processed_dir=processed_dir,
            seed_round_slots_csv=seed_round_slots_csv,
        )

        bracket_scores = score_bracket(
            predicted_slots=bracket_result["slots"],
            actual_winners=actual_winners,
        )

        espn_score = bracket_scores["espn_score"]
        per_round_acc = bracket_scores["per_round_accuracy"]
        print(
            f"  ESPN score: {espn_score} / {bracket_scores['espn_max']} "
            f"({espn_score / bracket_scores['espn_max']:.1%})"
        )

        # Step 4e: Compute game-level metrics using fold-specific scaler/model
        # TwoTierEnsemble satisfies the calibrated_clf interface (predict_proba(X))
        game_metrics = compute_game_metrics(
            test_df=test_df,
            feature_cols=FEATURE_COLS,
            scaler=scaler,
            calibrated_clf=calibrated_clf,
        )

        print(
            f"  Game-level -- Brier: {game_metrics['brier']:.4f}, "
            f"LogLoss: {game_metrics['log_loss']:.4f}, "
            f"Acc: {game_metrics['accuracy']:.1%}"
        )
        print(
            f"  Upsets -- detected {game_metrics['upset_correct']}/"
            f"{game_metrics['n_upsets']} "
            f"({game_metrics['upset_detection_rate']:.1%})"
        )

        # Step 4f: Combine year result
        year_result: dict[str, Any] = {
            "year": test_year,
            "predicted_champion": champion_id,
            # Bracket-level metrics
            "espn_score": espn_score,
            "espn_max": bracket_scores["espn_max"],
            "per_round_accuracy": per_round_acc,
            "per_round_correct": bracket_scores["per_round_correct"],
            "per_round_total": bracket_scores["per_round_total"],
            # Game-level metrics
            "brier": game_metrics["brier"],
            "log_loss": game_metrics["log_loss"],
            "accuracy": game_metrics["accuracy"],
            "n_games": game_metrics["n_games"],
            "n_upsets": game_metrics["n_upsets"],
            "upset_correct": game_metrics["upset_correct"],
            "upset_detection_rate": game_metrics["upset_detection_rate"],
        }

        per_year_results.append(year_result)

    # ------------------------------------------------------------------
    # Step 5: Summary aggregates
    # ------------------------------------------------------------------
    mean_brier = float(np.mean([r["brier"] for r in per_year_results]))
    mean_log_loss = float(np.mean([r["log_loss"] for r in per_year_results]))
    mean_accuracy = float(np.mean([r["accuracy"] for r in per_year_results]))
    mean_espn_score = float(np.mean([r["espn_score"] for r in per_year_results]))

    results: dict[str, Any] = {
        "model": model,
        "best_C": best_C,
        "years_evaluated": list(year_range),
        "per_year": per_year_results,
        "mean_brier": mean_brier,
        "mean_log_loss": mean_log_loss,
        "mean_accuracy": mean_accuracy,
        "mean_espn_score": mean_espn_score,
        "generated_at": date.today().isoformat(),
    }

    # ------------------------------------------------------------------
    # Step 6: Write JSON output
    # ------------------------------------------------------------------
    output_file = pathlib.Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to: {output_path}")

    # ------------------------------------------------------------------
    # Step 7: Print formatted comparison table
    # ------------------------------------------------------------------
    _print_results_table(per_year_results, mean_brier, mean_log_loss, mean_accuracy, mean_espn_score)

    # ------------------------------------------------------------------
    # Step 8: Print comparison vs baseline (ensemble only)
    # ------------------------------------------------------------------
    if model == "ensemble":
        baseline_brier = 0.1900  # Phase 3 / Phase 5 benchmark
        delta = mean_brier - baseline_brier
        direction = "IMPROVEMENT" if delta < 0 else "REGRESSION"
        print(f"\nEnsemble vs Baseline Comparison:")
        print(f"  Ensemble mean Brier:  {mean_brier:.4f}")
        print(f"  Baseline mean Brier:  {baseline_brier:.4f}")
        print(f"  Delta:                {delta:+.4f} ({direction})")

    return results


# ---------------------------------------------------------------------------
# Formatted output helper
# ---------------------------------------------------------------------------


def _print_results_table(
    per_year: list[dict[str, Any]],
    mean_brier: float,
    mean_log_loss: float,
    mean_accuracy: float,
    mean_espn_score: float,
) -> None:
    """Print a formatted per-year comparison table to stdout."""
    print()
    print("=" * 90)
    print("BACKTEST RESULTS")
    print("=" * 90)

    # Header
    header = (
        f"{'Year':>6} | "
        f"{'Brier':>8} | "
        f"{'LogLoss':>8} | "
        f"{'Acc':>7} | "
        f"{'Upsets':>9} | "
        f"{'ESPN':>6} | "
        f"{'Champion':>10}"
    )
    print(header)
    print("-" * 90)

    for r in per_year:
        upset_str = f"{r['upset_correct']}/{r['n_upsets']}"
        espn_str = f"{r['espn_score']}"
        row = (
            f"{r['year']:>6} | "
            f"{r['brier']:>8.4f} | "
            f"{r['log_loss']:>8.4f} | "
            f"{r['accuracy']:>7.1%} | "
            f"{upset_str:>9} | "
            f"{espn_str:>6} | "
            f"{r['predicted_champion']:>10}"
        )
        print(row)

    print("-" * 90)
    print(
        f"{'Mean':>6} | "
        f"{mean_brier:>8.4f} | "
        f"{mean_log_loss:>8.4f} | "
        f"{mean_accuracy:>7.1%} | "
        f"{'':>9} | "
        f"{mean_espn_score:>6.1f} | "
        f"{'':>10}"
    )
    print("=" * 90)

    # Per-round accuracy breakdown
    print()
    print("Per-Round Accuracy Breakdown:")
    round_names = [
        "Round of 64",
        "Round of 32",
        "Sweet 16",
        "Elite 8",
        "Final Four",
        "Championship",
    ]
    round_header = f"  {'Round':<16} " + " ".join(f"{y:>6}" for y in [r["year"] for r in per_year])
    print(round_header)
    print("  " + "-" * (16 + 7 * len(per_year)))

    for rname in round_names:
        vals = []
        for r in per_year:
            acc = r["per_round_accuracy"].get(rname, 0.0)
            vals.append(f"{acc:>6.1%}")
        print(f"  {rname:<16} " + " ".join(vals))

    print()


# ---------------------------------------------------------------------------
# Main block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    model_arg = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    results = backtest(model=model_arg)

    print("\nSummary:")
    print(f"  Model:            {results['model']}")
    print(f"  Years evaluated:  {results['years_evaluated']}")
    print(f"  Mean Brier:       {results['mean_brier']:.4f}")
    print(f"  Mean Log-loss:    {results['mean_log_loss']:.4f}")
    print(f"  Mean Accuracy:    {results['mean_accuracy']:.1%}")
    print(f"  Mean ESPN Score:  {results['mean_espn_score']:.1f}")

    if model_arg == "baseline":
        print(f"\nResults saved to: backtest/results.json")
    else:
        print(f"\nResults saved to: backtest/ensemble_results.json")
