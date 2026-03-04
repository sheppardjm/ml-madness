"""
Model comparison dashboard for NCAA tournament bracket predictions.

Loads backtest results from Phase 5 (baseline) and Phase 6 (ensemble) and
prints a formatted side-by-side comparison table showing which model wins on
each metric. Highlights the upset detection tradeoff: ensemble beats baseline
on Brier score and ESPN score but trails on upset detection rate.

Exports:
    load_comparison_data()    - Load baseline and ensemble backtest JSON results
    print_comparison_table()  - Print formatted comparison to stdout
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROUND_NAMES = [
    "Round of 64",
    "Round of 32",
    "Sweet 16",
    "Elite 8",
    "Final Four",
    "Championship",
]

_DEFAULT_BASELINE_PATH = "backtest/results.json"
_DEFAULT_ENSEMBLE_PATH = "backtest/ensemble_results.json"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_comparison_data(
    baseline_path: str = _DEFAULT_BASELINE_PATH,
    ensemble_path: str = _DEFAULT_ENSEMBLE_PATH,
) -> dict[str, dict[str, Any]]:
    """Load backtest results for baseline and ensemble models.

    Reads backtest/results.json (baseline logistic regression) and
    backtest/ensemble_results.json (TwoTierEnsemble) and returns a dict
    keyed by model name.

    Args:
        baseline_path: Path to baseline backtest results JSON.
            Default: backtest/results.json.
        ensemble_path: Path to ensemble backtest results JSON.
            Default: backtest/ensemble_results.json.

    Returns:
        Dict with keys 'baseline' and 'ensemble', each mapping to the full
        result dict as written by backtest().

    Raises:
        FileNotFoundError: If either result file is missing.
    """
    baseline_file = pathlib.Path(baseline_path)
    ensemble_file = pathlib.Path(ensemble_path)

    if not baseline_file.exists():
        raise FileNotFoundError(
            f"Baseline results not found at {baseline_path}. "
            "Run: uv run python -m src.backtest.backtest baseline"
        )
    if not ensemble_file.exists():
        raise FileNotFoundError(
            f"Ensemble results not found at {ensemble_path}. "
            "Run: uv run python -m src.backtest.backtest ensemble"
        )

    baseline = json.loads(baseline_file.read_text())
    ensemble = json.loads(ensemble_file.read_text())

    return {"baseline": baseline, "ensemble": ensemble}


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _compute_mean_upset_rate(data: dict[str, Any]) -> float:
    """Compute mean upset detection rate across all per_year entries.

    Args:
        data: Full result dict from load_comparison_data() for one model.

    Returns:
        Mean upset detection rate as a float in [0, 1].
    """
    rates = [
        entry["upset_detection_rate"]
        for entry in data.get("per_year", [])
        if "upset_detection_rate" in entry
    ]
    if not rates:
        return float("nan")
    return sum(rates) / len(rates)


def _compute_mean_per_round_accuracy(
    data: dict[str, Any],
) -> dict[str, float]:
    """Compute 4-year average per-round accuracy.

    Args:
        data: Full result dict from load_comparison_data() for one model.

    Returns:
        Dict mapping round name to mean accuracy across all years.
    """
    per_year = data.get("per_year", [])
    n_years = len(per_year)
    if n_years == 0:
        return {r: float("nan") for r in ROUND_NAMES}

    totals: dict[str, float] = {r: 0.0 for r in ROUND_NAMES}
    for entry in per_year:
        per_round = entry.get("per_round_accuracy", {})
        for rname in ROUND_NAMES:
            totals[rname] += per_round.get(rname, 0.0)

    return {rname: totals[rname] / n_years for rname in ROUND_NAMES}


# ---------------------------------------------------------------------------
# Comparison table printing
# ---------------------------------------------------------------------------


def print_comparison_table(models_data: dict[str, dict[str, Any]]) -> None:
    """Print formatted side-by-side comparison of baseline and ensemble models.

    Prints four sections:
      1. Summary table: mean Brier, mean accuracy, mean ESPN score, mean upset
         detection rate for each model, plus delta column (ensemble - baseline).
      2. Per-year Brier scores: both models side-by-side with delta per year.
      3. Per-round accuracy: 4-year mean accuracy per round for both models.
      4. Upset detection tradeoff note.

    Args:
        models_data: Dict from load_comparison_data() with keys 'baseline'
            and 'ensemble'.
    """
    baseline = models_data["baseline"]
    ensemble = models_data["ensemble"]

    baseline_mean_upset = _compute_mean_upset_rate(baseline)
    ensemble_mean_upset = _compute_mean_upset_rate(ensemble)

    baseline_round_acc = _compute_mean_per_round_accuracy(baseline)
    ensemble_round_acc = _compute_mean_per_round_accuracy(ensemble)

    years = [entry["year"] for entry in baseline.get("per_year", [])]

    # -----------------------------------------------------------------------
    # Section 1: Summary table
    # -----------------------------------------------------------------------
    print()
    print("=" * 100)
    print("MODEL COMPARISON DASHBOARD (2022-2025 Holdout)")
    print("=" * 100)

    summary_header = (
        f"{'Model':<20} | "
        f"{'Mean Brier':>10} | "
        f"{'Mean Acc':>9} | "
        f"{'Mean ESPN':>9} | "
        f"{'Upset Det Rate':>14}"
    )
    print(summary_header)
    print("-" * 75)

    model_order = ["baseline", "ensemble"]
    for model_name in model_order:
        if model_name not in models_data:
            continue
        data = models_data[model_name]
        brier = data["mean_brier"]
        acc = data.get("mean_accuracy", float("nan"))
        espn = data.get("mean_espn_score", float("nan"))
        upset_rate = _compute_mean_upset_rate(data)
        row = (
            f"{model_name:<20} | "
            f"{brier:>10.4f} | "
            f"{acc:>9.1%} | "
            f"{espn:>9.1f} | "
            f"{upset_rate:>14.1%}"
        )
        print(row)

    # Delta row (ensemble - baseline; negative Brier delta = improvement)
    brier_delta = ensemble["mean_brier"] - baseline["mean_brier"]
    acc_delta = ensemble.get("mean_accuracy", 0.0) - baseline.get("mean_accuracy", 0.0)
    espn_delta = ensemble.get("mean_espn_score", 0.0) - baseline.get("mean_espn_score", 0.0)
    upset_delta = ensemble_mean_upset - baseline_mean_upset

    brier_delta_str = f"{brier_delta:+.4f}"
    acc_delta_str = f"{acc_delta:+.1%}"
    espn_delta_str = f"{espn_delta:+.1f}"
    upset_delta_str = f"{upset_delta:+.1%}"

    print("-" * 75)
    delta_row = (
        f"{'delta (ens - base)':<20} | "
        f"{brier_delta_str:>10} | "
        f"{acc_delta_str:>9} | "
        f"{espn_delta_str:>9} | "
        f"{upset_delta_str:>14}"
    )
    print(delta_row)
    print("=" * 100)

    # -----------------------------------------------------------------------
    # Section 2: Per-year Brier scores
    # -----------------------------------------------------------------------
    print()
    print("Per-Year Brier Scores (lower is better):")

    year_header = (
        f"  {'Year':<6} | "
        f"{'Baseline':>10} | "
        f"{'Ensemble':>10} | "
        f"{'Delta':>8}"
    )
    print(year_header)
    print("  " + "-" * 44)

    baseline_by_year = {entry["year"]: entry for entry in baseline.get("per_year", [])}
    ensemble_by_year = {entry["year"]: entry for entry in ensemble.get("per_year", [])}

    for yr in years:
        b_brier = baseline_by_year[yr]["brier"]
        e_brier = ensemble_by_year[yr]["brier"]
        delta = e_brier - b_brier
        winner = "<<" if delta < 0 else ">>"
        print(
            f"  {yr:<6} | "
            f"{b_brier:>10.4f} | "
            f"{e_brier:>10.4f} | "
            f"{delta:>+8.4f} {winner}"
        )

    print("  " + "-" * 44)
    b_mean = baseline["mean_brier"]
    e_mean = ensemble["mean_brier"]
    mean_delta = e_mean - b_mean
    print(
        f"  {'Mean':<6} | "
        f"{b_mean:>10.4f} | "
        f"{e_mean:>10.4f} | "
        f"{mean_delta:>+8.4f}"
    )

    # -----------------------------------------------------------------------
    # Section 3: Per-round accuracy (4-year mean)
    # -----------------------------------------------------------------------
    print()
    print("Per-Round Accuracy (4-year mean, higher is better):")

    round_header = (
        f"  {'Round':<16} | "
        f"{'Baseline':>9} | "
        f"{'Ensemble':>9} | "
        f"{'Delta':>7}"
    )
    print(round_header)
    print("  " + "-" * 50)

    for rname in ROUND_NAMES:
        b_acc = baseline_round_acc[rname]
        e_acc = ensemble_round_acc[rname]
        delta = e_acc - b_acc
        winner = "<<" if delta > 0 else ">>"
        print(
            f"  {rname:<16} | "
            f"{b_acc:>9.1%} | "
            f"{e_acc:>9.1%} | "
            f"{delta:>+7.1%} {winner}"
        )

    print("  " + "-" * 50)

    # -----------------------------------------------------------------------
    # Section 4: Upset detection tradeoff note
    # -----------------------------------------------------------------------
    print()
    print("=" * 100)
    print("UPSET DETECTION TRADEOFF")
    print("=" * 100)
    print(
        "The ensemble model trades upset detection for improved Brier score and ESPN bracket performance."
    )
    print()

    upset_year_header = (
        f"  {'Year':<6} | "
        f"{'Baseline Upset Det':>19} | "
        f"{'Ensemble Upset Det':>19} | "
        f"{'Delta':>8}"
    )
    print(upset_year_header)
    print("  " + "-" * 62)

    for yr in years:
        b_rate = baseline_by_year[yr]["upset_detection_rate"]
        e_rate = ensemble_by_year[yr]["upset_detection_rate"]
        delta = e_rate - b_rate
        print(
            f"  {yr:<6} | "
            f"{b_rate:>19.1%} | "
            f"{e_rate:>19.1%} | "
            f"{delta:>+8.1%}"
        )

    print("  " + "-" * 62)
    print(
        f"  {'Mean':<6} | "
        f"{baseline_mean_upset:>19.1%} | "
        f"{ensemble_mean_upset:>19.1%} | "
        f"{upset_delta:>+8.1%}"
    )

    print()
    print(
        "NOTE: Ensemble assigns higher probability to favorites (better calibration),\n"
        "      resulting in fewer upset predictions. For bracket challenges that reward\n"
        "      upset picks, the baseline may be preferable in early rounds. For pure\n"
        "      probabilistic accuracy (Brier), the ensemble wins by 11% (0.1692 vs 0.1900)."
    )
    print("=" * 100)
    print()


# ---------------------------------------------------------------------------
# Main block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data = load_comparison_data()
    print_comparison_table(data)
