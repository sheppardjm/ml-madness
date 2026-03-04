"""
Visualization functions for the model comparison dashboard.

Generates static PNG charts comparing baseline (logistic regression) and
ensemble (TwoTierEnsemble) models on per-round accuracy and Brier score.

Exports:
    plot_per_round_accuracy()  - Grouped bar chart of per-round accuracy
    plot_brier_heatmap()       - Heatmap of Brier score by model and year
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pathlib
from typing import Any

# Short round labels for x-axis
ROUND_SHORT_LABELS = ["R64", "R32", "S16", "E8", "FF", "CH"]
ROUND_FULL_NAMES = [
    "Round of 64",
    "Round of 32",
    "Sweet 16",
    "Elite 8",
    "Final Four",
    "Championship",
]


def _avg_round_accuracy(data: dict[str, Any], round_name: str) -> float:
    """Compute 4-year average accuracy for a given round.

    Args:
        data: Full result dict for one model from load_comparison_data().
        round_name: Full round name (e.g. "Round of 64").

    Returns:
        Mean per-round accuracy across all years.
    """
    years = data.get("per_year", [])
    if not years:
        return 0.0
    return sum(y.get("per_round_accuracy", {}).get(round_name, 0.0) for y in years) / len(years)


def plot_per_round_accuracy(
    models_data: dict[str, dict[str, Any]],
    save_path: str = "models/per_round_comparison.png",
) -> None:
    """Generate and save a grouped bar chart of per-round accuracy.

    Creates a grouped bar chart showing 4-year average (2022-2025) per-round
    accuracy for baseline and ensemble models, side-by-side for each of the
    6 tournament rounds.

    Args:
        models_data: Dict from load_comparison_data() with keys 'baseline'
            and 'ensemble'.
        save_path: Output path for the PNG file.
            Default: models/per_round_comparison.png.
    """
    baseline = models_data["baseline"]
    ensemble = models_data["ensemble"]

    baseline_vals = [_avg_round_accuracy(baseline, r) for r in ROUND_FULL_NAMES]
    ensemble_vals = [_avg_round_accuracy(ensemble, r) for r in ROUND_FULL_NAMES]

    x = np.arange(len(ROUND_SHORT_LABELS))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))

    bars_baseline = ax.bar(
        x - width / 2,
        baseline_vals,
        width,
        label="Baseline (LR)",
        color="steelblue",
    )
    bars_ensemble = ax.bar(
        x + width / 2,
        ensemble_vals,
        width,
        label="Ensemble",
        color="darkorange",
    )

    # Value labels on top of each bar
    for bar in bars_baseline:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 0.005,
            f"{height:.0%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    for bar in bars_ensemble:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 0.005,
            f"{height:.0%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xlabel("Round")
    ax.set_ylabel("Accuracy")
    ax.set_title("Per-Round Accuracy: Baseline vs. Ensemble (2022-2025 avg)")
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_SHORT_LABELS)
    ax.set_ylim(0.0, 1.0)
    ax.legend()

    plt.tight_layout()

    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Per-round comparison chart saved to: {save_path}")


def plot_brier_heatmap(
    models_data: dict[str, dict[str, Any]],
    save_path: str = "models/brier_heatmap.png",
) -> None:
    """Generate and save a heatmap of Brier score by model and year.

    Creates a heatmap with rows=models, columns=years (2022-2025), and cell
    values=Brier score. Uses RdYlGn_r colormap so green=low Brier (good) and
    red=high Brier (bad). Annotates each cell with the exact Brier value.

    Args:
        models_data: Dict from load_comparison_data() with keys 'baseline'
            and 'ensemble'.
        save_path: Output path for the PNG file.
            Default: models/brier_heatmap.png.
    """
    years = [2022, 2023, 2024, 2025]
    model_names = list(models_data.keys())  # ["baseline", "ensemble"]

    matrix = []
    for name in model_names:
        row = []
        for yr in years:
            year_entry = next(
                (y for y in models_data[name].get("per_year", []) if y["year"] == yr),
                None,
            )
            row.append(year_entry["brier"] if year_entry else float("nan"))
        matrix.append(row)

    matrix_np = np.array(matrix)

    fig, ax = plt.subplots(figsize=(8, 3))

    im = ax.imshow(
        matrix_np,
        cmap="RdYlGn_r",
        aspect="auto",
        vmin=0.12,
        vmax=0.25,
    )

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years])
    ax.set_yticks(range(len(model_names)))
    ax.set_yticklabels(model_names)
    ax.set_title("Brier Score by Model and Year (lower is better)")

    # Annotate each cell with the Brier value
    for i in range(len(model_names)):
        for j in range(len(years)):
            val = matrix_np[i, j]
            ax.text(
                j,
                i,
                f"{val:.4f}",
                ha="center",
                va="center",
                fontsize=10,
            )

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Brier Score")

    plt.tight_layout()

    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Brier heatmap saved to: {save_path}")
