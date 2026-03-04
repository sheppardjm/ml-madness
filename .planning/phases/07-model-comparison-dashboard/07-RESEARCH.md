# Phase 7: Model Comparison Dashboard - Research

**Researched:** 2026-03-04
**Domain:** Data presentation (formatted tables, matplotlib bar charts/heatmaps), model selection logic, CLI entry points
**Confidence:** HIGH (all source data files inspected, existing code patterns verified by reading, visualization library availability confirmed)

## Summary

Phase 7 is primarily a data presentation and model selection phase, not a modeling phase. The heavy lifting is done: both `backtest/results.json` (baseline) and `backtest/ensemble_results.json` (ensemble) exist with identical JSON schemas containing per-year Brier, log-loss, accuracy, per-round accuracy, upset detection rates, and ESPN scores across 2022–2025.

The key data gap to resolve is that XGBoost and LightGBM appear in the success criteria as columns in the comparison table, but `backtest/` only contains baseline and ensemble result files. The `evaluate_xgb()` and `evaluate_lgb()` functions in `src/models/train_xgboost.py` and `src/models/train_lightgbm.py` return only `{year, brier, log_loss, n_games}` — no per-round accuracy or upset detection data. These functions operate at the temporal CV level (matchup-by-matchup Brier), not at the bracket simulation level. There is no `backtest/xgb_results.json` or `backtest/lgb_results.json`.

Two approaches exist for including XGB and LGB in the comparison table: (A) extend `backtest()` to support `model='xgb'` and `model='lgb'`, generating full per-round backtest data by running individual models through the bracket simulator; (B) report only the aggregate mean Brier scores for XGB/LGB (from the existing `evaluate_xgb`/`evaluate_lgb` results) in a simplified row without per-round accuracy. Approach B is significantly less work and the existing Brier numbers (XGB=0.1908, LGB=0.1931) are already verified.

Given that Phase 9 (Streamlit UI) consumes `models/selected.json`, the recommendation artifact from 07-03 is a real downstream dependency — not just documentation.

**Primary recommendation:** Use matplotlib (already installed, project standard) for all visualizations. For the table, format output via Python string formatting (same pattern as `_print_results_table()` in backtest.py). Create `src/dashboard/compare.py` as the entry point. For XGB/LGB rows, use the aggregate Brier data available from Phase 6 evaluations with N/A for per-round fields, OR run a simplified backtest-level evaluation — decide in plan 07-01.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| matplotlib | 3.10.8 (installed) | Bar chart and heatmap visualization | Already project standard; used in evaluate.py and ensemble.py |
| pandas | 3.0.1 (installed) | DataFrame pivoting for comparison table | Already project standard |
| numpy | installed | Aggregate computation | Already project standard |
| json | stdlib | Load backtest/results.json and ensemble_results.json | Already used throughout |
| pathlib | stdlib | File paths for artifacts | Already used throughout |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib.pyplot | 3.10.8 | Subplots, bar chart, imshow heatmap | Charts in 07-02 |
| matplotlib.colors | 3.10.8 | Colormap for heatmap (e.g., RdYlGn) | Heatmap in 07-02 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| matplotlib for charts | plotly | Plotly NOT in pyproject.toml or venv; would require `uv add plotly`; Phase 9 uses Plotly but Phase 7 is CLI-first; matplotlib is sufficient for static PNG output |
| matplotlib for charts | seaborn | seaborn NOT installed; matplotlib provides equivalent heatmap via `imshow` + `matshow`; no new dependency needed |
| Python f-string table formatting | tabulate | tabulate NOT installed; project uses manual string formatting (see `_print_results_table()` in backtest.py); no new dependency needed |

**No new packages are needed for Phase 7.** All required libraries are already in `pyproject.toml`.

Note on Plotly: The roadmap calls for "Plotly bar chart" in 07-02, but Plotly is not installed and Phase 7 is CLI-first (not Streamlit). Phase 9 is where Streamlit+Plotly live. Use matplotlib for Phase 7 visualizations (same pattern as calibration curves in evaluate.py and ensemble.py). If the planner wants Plotly, add `uv add plotly` as a prerequisite task.

## Architecture Patterns

### Recommended Project Structure

```
src/
└── dashboard/
    ├── __init__.py
    └── compare.py        # New: comparison table + charts + model selection

backtest/
├── results.json          # Existing: baseline per-year results
└── ensemble_results.json # Existing: ensemble per-year results

models/
└── selected.json         # New (07-03): model selection artifact for Phase 9
```

### Pattern 1: JSON Loading and Pivoting

**What:** Load both results files, pivot into a model-vs-metric matrix.
**When to use:** 07-01 plan.

```python
# Source: backtest/results.json and ensemble_results.json structure (confirmed by inspection)
import json
import pathlib

def load_comparison_data() -> dict:
    """Load backtest results for baseline and ensemble models.

    Returns a dict with model names as keys and their result dicts as values.
    XGB and LGB entries are constructed from aggregate Brier data (Phase 6 evaluations).
    """
    baseline = json.loads(pathlib.Path("backtest/results.json").read_text())
    ensemble = json.loads(pathlib.Path("backtest/ensemble_results.json").read_text())
    return {"baseline": baseline, "ensemble": ensemble}
```

**Known JSON schema** (both files identical structure):
```json
{
  "model": "baseline",
  "best_C": 2.3916,
  "years_evaluated": [2022, 2023, 2024, 2025],
  "per_year": [
    {
      "year": 2022,
      "predicted_champion": 1222,
      "espn_score": 570,
      "espn_max": 1920,
      "per_round_accuracy": {"Round of 64": 0.656, "Round of 32": 0.625, "Sweet 16": 0.25,
                              "Elite 8": 0.25, "Final Four": 0.0, "Championship": 0.0},
      "per_round_correct": {"Round of 64": 21, ...},
      "per_round_total": {"Round of 64": 32, ...},
      "brier": 0.2150,
      "log_loss": 0.6159,
      "accuracy": 0.6508,
      "n_games": 63,
      "n_upsets": 21,
      "upset_correct": 17,
      "upset_detection_rate": 0.8095
    }
    // ...2023, 2024, 2025 entries
  ],
  "mean_brier": 0.1900,
  "mean_log_loss": 0.5566,
  "mean_accuracy": 0.6901,
  "mean_espn_score": 912.5,
  "generated_at": "2026-03-04"
}
```

### Pattern 2: Formatted Comparison Table (existing codebase pattern)

**What:** Print a side-by-side model comparison table. Follow the exact pattern of `_print_results_table()` in `src/backtest/backtest.py`.
**When to use:** 07-01 plan.

```python
# Source: src/backtest/backtest.py _print_results_table() pattern (lines 627-701)
ROUND_NAMES = ["Round of 64", "Round of 32", "Sweet 16", "Elite 8", "Final Four", "Championship"]

def print_comparison_table(models_data: dict) -> None:
    """Print side-by-side comparison of all models.

    Models: baseline, xgb, lgb, ensemble (in that order).
    Columns: model name, mean Brier, mean accuracy, mean ESPN score, mean upset detection rate.
    Per-round section: rows are rounds, columns are models.
    """
    print()
    print("=" * 100)
    print("MODEL COMPARISON DASHBOARD (2022-2025 Holdout)")
    print("=" * 100)

    # Summary rows
    header = f"{'Model':<20} | {'Mean Brier':>10} | {'Mean Acc':>9} | {'Mean ESPN':>9} | {'Mean Upset Det':>14}"
    print(header)
    print("-" * 80)
    for model_name, data in models_data.items():
        brier = data["mean_brier"]
        acc = data.get("mean_accuracy", float("nan"))
        espn = data.get("mean_espn_score", float("nan"))
        upset = _compute_mean_upset_rate(data)
        row = f"{model_name:<20} | {brier:>10.4f} | {acc:>9.1%} | {espn:>9.1f} | {upset:>14.1%}"
        print(row)

    # Recommendation row
    best_model = min(models_data.items(), key=lambda x: x[1]["mean_brier"])[0]
    print("-" * 80)
    print(f"RECOMMENDED: {best_model} (lowest mean Brier score)")
    print("=" * 100)
```

### Pattern 3: Matplotlib Bar Chart (per-round accuracy)

**What:** Grouped bar chart showing per-round accuracy for baseline vs. ensemble (the two models with full per-round data).
**When to use:** 07-02 plan.

```python
# Source: evaluate.py calibration plot pattern (lines 241-260) — adapted for bar chart
import matplotlib
matplotlib.use("Agg")  # required for headless/non-GUI environments (same as evaluate.py)
import matplotlib.pyplot as plt
import numpy as np

def plot_per_round_accuracy(baseline: dict, ensemble: dict,
                             save_path: str = "models/per_round_comparison.png") -> None:
    """Plot grouped bar chart: per-round accuracy baseline vs. ensemble (4-year avg)."""
    rounds = ["Round of 64", "Round of 32", "Sweet 16", "Elite 8", "Final Four", "Championship"]

    # Compute 4-year average per round for each model
    baseline_avgs = [
        sum(y["per_round_accuracy"].get(r, 0) for y in baseline["per_year"]) / 4
        for r in rounds
    ]
    ensemble_avgs = [
        sum(y["per_round_accuracy"].get(r, 0) for y in ensemble["per_year"]) / 4
        for r in rounds
    ]

    x = np.arange(len(rounds))
    width = 0.35
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - width/2, baseline_avgs, width, label="Baseline (LR)", color="steelblue")
    ax.bar(x + width/2, ensemble_avgs, width, label="Ensemble", color="darkorange")
    ax.set_xticks(x)
    ax.set_xticklabels(rounds, rotation=15, ha="right")
    ax.set_ylabel("Accuracy (4-year avg)")
    ax.set_title("Per-Round Accuracy: Baseline vs. Ensemble (2022-2025)")
    ax.legend()
    ax.set_ylim(0, 1.0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Per-round comparison chart saved to: {save_path}")
```

### Pattern 4: Matplotlib Heatmap (Brier score by model and year)

**What:** Heatmap with rows=models, columns=years, cells=Brier score. Lower is better (green=good, red=bad).
**When to use:** 07-02 plan.

```python
# Source: matplotlib imshow pattern — consistent with project's matplotlib usage in evaluate.py/ensemble.py
def plot_brier_heatmap(models_data: dict,
                       save_path: str = "models/brier_heatmap.png") -> None:
    """Plot heatmap of Brier score by model and year.

    Rows: models (baseline, xgb, lgb, ensemble).
    Columns: years (2022, 2023, 2024, 2025).
    Color: low Brier = green (good), high Brier = red (bad).
    """
    years = [2022, 2023, 2024, 2025]
    model_names = list(models_data.keys())

    # Build matrix: rows=models, cols=years
    matrix = []
    for model_name in model_names:
        data = models_data[model_name]
        row = []
        for yr in years:
            year_entry = next((y for y in data.get("per_year", []) if y["year"] == yr), None)
            if year_entry:
                row.append(year_entry["brier"])
            else:
                row.append(data.get("mean_brier", float("nan")))  # fallback for XGB/LGB
        matrix.append(row)

    import numpy as np
    mat = np.array(matrix)

    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(mat, cmap="RdYlGn_r", aspect="auto",
                   vmin=0.12, vmax=0.25)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years)
    ax.set_yticks(range(len(model_names)))
    ax.set_yticklabels(model_names)
    ax.set_title("Brier Score by Model and Year (lower is better)")

    # Annotate cells with values
    for i in range(len(model_names)):
        for j in range(len(years)):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.4f}", ha="center", va="center",
                        fontsize=9, color="black")

    plt.colorbar(im, ax=ax, label="Brier Score")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Brier heatmap saved to: {save_path}")
```

### Pattern 5: Model Recommendation Logic and selected.json

**What:** Select best model by mean Brier score and write `models/selected.json`.
**When to use:** 07-03 plan.

```python
# Source: analogous to models/logistic_baseline.joblib artifact pattern; Phase 9 consumes this
def select_best_model(models_data: dict, output_path: str = "models/selected.json") -> dict:
    """Select best model by lowest mean Brier score, write to models/selected.json.

    Phase 9 (Streamlit app scaffolding) loads models/selected.json to determine
    which model to use for the 2026 bracket.

    Args:
        models_data: Dict of {model_name: result_dict} from load_comparison_data().
        output_path: Path to write selection artifact.

    Returns:
        Selection artifact dict.
    """
    best_model = min(models_data.items(), key=lambda x: x[1]["mean_brier"])
    best_name, best_data = best_model

    artifact = {
        "selected_model": best_name,
        "selection_criterion": "lowest_mean_brier",
        "mean_brier": best_data["mean_brier"],
        "brier_scores": {
            name: data["mean_brier"]
            for name, data in models_data.items()
        },
        "evaluation_years": [2022, 2023, 2024, 2025],
        "generated_at": str(date.today()),
    }

    pathlib.Path(output_path).write_text(json.dumps(artifact, indent=2))
    print(f"\nSelected model: {best_name} (mean Brier = {best_data['mean_brier']:.4f})")
    print(f"Selection artifact written to: {output_path}")
    return artifact
```

**models/selected.json schema:**
```json
{
  "selected_model": "ensemble",
  "selection_criterion": "lowest_mean_brier",
  "mean_brier": 0.1692,
  "brier_scores": {
    "baseline": 0.1900,
    "xgb": 0.1908,
    "lgb": 0.1931,
    "ensemble": 0.1692
  },
  "evaluation_years": [2022, 2023, 2024, 2025],
  "generated_at": "2026-03-04"
}
```

### Pattern 6: CLI Entry Point

**What:** `python -m src.dashboard.compare` (or `uv run python -m src.dashboard.compare`) as the single command that prints the table, saves charts, and writes selected.json.
**When to use:** 07-01 plan (or split across 07-01/07-02/07-03 with the CLI calling all three).

```python
# Source: src/backtest/backtest.py __main__ block pattern (lines 708-725)
if __name__ == "__main__":
    data = load_comparison_data()
    print_comparison_table(data)
    plot_per_round_accuracy(data["baseline"], data["ensemble"])
    plot_brier_heatmap(data)
    select_best_model(data)
```

Run command: `uv run python -m src.dashboard.compare`

### Anti-Patterns to Avoid

- **Loading models/ensemble.joblib for the comparison:** The comparison table reads only JSON files — no model artifacts need to be loaded.
- **Re-running backtest() to generate the data:** The data already exists in backtest/results.json and ensemble_results.json. Phase 7 is read-only with respect to those files.
- **Using Streamlit in Phase 7:** Phase 9 is the Streamlit phase. Phase 7 is CLI-first (print table + save PNG charts).
- **Overwriting backtest/results.json:** Phase 7 is read-only — it must not modify any existing backtest result files.
- **Per-round data for XGB/LGB from bracket simulation:** The `evaluate_xgb()` and `evaluate_lgb()` functions evaluate at the matchup level (Brier), not at the bracket simulation level. They cannot produce per-round accuracy without running through `simulate_bracket()`. Approach the XGB/LGB columns as aggregate-Brier-only rows, or extend `backtest()` in a separate task.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Formatted table output | Custom table renderer | Python f-string formatting (same as `_print_results_table()` in backtest.py) | Established pattern; tabulate not installed; no new dependency needed |
| Bar chart | Custom SVG renderer | matplotlib bar chart | matplotlib already installed; `plt.bar()` is standard |
| Heatmap | Custom color matrix | matplotlib `imshow` with RdYlGn_r colormap | matplotlib already installed; `imshow` + `colorbar` is standard |
| JSON read/write | Custom serializer | stdlib `json` module | Already used in all backtest files |
| Model selection | Custom ranking logic | Simple `min()` over mean_brier | One-liner; no library needed |

**Key insight:** Phase 7 is thin transformation and presentation code over existing JSON data. The pipeline produces static outputs (console table + 2 PNG files + models/selected.json). No new ML code.

## Common Pitfalls

### Pitfall 1: XGB/LGB Per-Round Data Gap

**What goes wrong:** The comparison table success criterion says "XGBoost vs. LightGBM vs. ensemble" in the same table — but only aggregate mean Brier (0.1908 / 0.1931) exists for XGB/LGB from Phase 6 evaluate functions. No per-round accuracy or upset detection data exists for XGB/LGB.
**Why it happens:** Phase 6 evaluate_xgb/evaluate_lgb only run temporal CV at the matchup level — they do not run through simulate_bracket() to get per-round bracket scores.
**How to avoid:** Two options:
  1. (Simpler) Include XGB/LGB as summary-only rows in the comparison table with per-round columns showing "N/A" and only Brier filled in.
  2. (More complete) Add `model='xgb'` and `model='lgb'` support to `backtest()` — each fold trains a single model (no meta-learner), runs through bracket simulation, and writes `backtest/xgb_results.json` / `backtest/lgb_results.json`. This adds ~20 lines to backtest.py but produces full per-round data.
**Recommendation:** Option 2 gives a complete comparison. The planner should decide in 07-01 whether to include this backtest extension task.
**Warning signs:** If the plan only reads existing JSON files and constructs the table, per-round rows for XGB/LGB will be empty/N/A, which looks incomplete.

### Pitfall 2: matplotlib "Agg" Backend

**What goes wrong:** `plt.savefig()` fails with `RuntimeError: Invalid DISPLAY variable` in headless environments (CI, remote session).
**Why it happens:** matplotlib defaults to a GUI backend; without a display, `import matplotlib.pyplot` can fail or `savefig` can raise.
**How to avoid:** Always call `matplotlib.use("Agg")` before `import matplotlib.pyplot as plt`. This is already done in `evaluate.py` (line 26) and `ensemble.py` (line 32). Use the same pattern.
**Warning signs:** `RuntimeError: Invalid DISPLAY variable` or `_tkinter.TclError: no display name and no $DISPLAY environment variable`.

### Pitfall 3: models/selected.json Schema Mismatch

**What goes wrong:** Phase 9 loads `models/selected.json` and fails because the `selected_model` key doesn't match the expected model identifiers.
**Why it happens:** If the schema isn't designed with Phase 9 consumption in mind, Phase 9 will need to work around it.
**How to avoid:** The `selected_model` field must be one of `{'baseline', 'ensemble'}` (the two models with full backtest results). It should map to a model artifact that Phase 9 can actually load (e.g., `models/ensemble.joblib`). Include a `model_artifact_path` field in the schema so Phase 9 knows where to find the artifact.
**Warning signs:** Phase 9 plan needs to re-parse or transform the selected.json format.

### Pitfall 4: Heatmap Missing Per-Round Data for XGB/LGB

**What goes wrong:** The heatmap has rows for XGB/LGB but no per-year Brier data in the JSON format because `evaluate_xgb` doesn't store results to a file.
**Why it happens:** `evaluate_xgb()` and `evaluate_lgb()` return their results but don't write JSON files.
**How to avoid:** Either (a) run evaluate_xgb/evaluate_lgb at dashboard generation time to get the per-year data (not saved to disk previously) or (b) add XGB/LGB to the backtest via Option 2 in Pitfall 1 (preferred — more consistent, produces persisted JSON files).
**Warning signs:** XGB/LGB rows in the heatmap show only one value (mean_brier used as fallback for all years) instead of per-year values.

### Pitfall 5: File Path Assumptions

**What goes wrong:** `compare.py` uses relative paths that break when called from different working directories.
**Why it happens:** `open("backtest/results.json")` fails if cwd is not the project root.
**How to avoid:** Use the same pattern as backtest.py: accept paths as parameters with sensible defaults, or compute relative to `pathlib.Path(__file__).parents[2]` (project root). The existing project uses relative paths consistently (e.g., `models/logistic_baseline.joblib`) and assumes cwd = project root. Follow the same convention.
**Warning signs:** `FileNotFoundError: backtest/results.json` when running from `src/dashboard/`.

## Code Examples

### Complete Data Available (Verified by Inspection)

```
Baseline (backtest/results.json):
  Model: baseline
  Mean Brier: 0.1900, Mean ESPN: 912.5, Mean Accuracy: 69.0%
  Per-year Brier: 2022=0.2150, 2023=0.2199, 2024=0.1778, 2025=0.1474
  Per-round avg accuracy: R64=68.0%, R32=57.8%, S16=34.4%, E8=50.0%, FF=50.0%, CH=25.0%
  Mean upset detection: varies per year (see below)

Ensemble (backtest/ensemble_results.json):
  Model: ensemble
  Mean Brier: 0.1692, Mean ESPN: 1037.5, Mean Accuracy: 74.3%
  Per-year Brier: 2022=0.1793, 2023=0.1850, 2024=0.1760, 2025=0.1364
  Per-round avg accuracy: R64=71.1%, R32=75.0%, S16=53.1%, E8=50.0%, FF=25.0%, CH=50.0%
  Mean upset detection: significantly lower than baseline (ensemble trades upset detection for Brier)

XGB (from evaluate_xgb in Phase 6):
  Mean Brier: 0.1908
  Per-year Brier: 2022=0.1898, 2023=0.2112, 2024=0.1837, 2025=0.1787
  Per-round accuracy: NOT AVAILABLE (not in any JSON file)

LGB (from evaluate_lgb in Phase 6):
  Mean Brier: 0.1931
  Per-year Brier: not in a JSON file (only printed to stdout during 06-02)
  Per-round accuracy: NOT AVAILABLE

Key metric comparison:
  Brier:             LGB=0.1931 > XGB=0.1908 > Baseline=0.1900 > Ensemble=0.1692
  Accuracy:          Baseline=69.0% < Ensemble=74.3%
  ESPN Score:        Baseline=912.5 < Ensemble=1037.5
  Upset Detection:   Ensemble << Baseline (ensemble trades upset detection for calibration)
```

### Upset Detection Rate Analysis

An important narrative finding: the ensemble beats the baseline on Brier score and ESPN score but is substantially worse on upset detection rate. This is worth highlighting in the comparison table.

```
Upset Detection Rate by Year:
Year  Baseline   Ensemble  Delta
2022   81.0%      57.1%   -23.8pp
2023   63.2%      36.8%   -26.3pp
2024   57.9%      26.3%   -31.6pp
2025   54.5%      18.2%   -36.4pp
```

The comparison table should note this tradeoff prominently. The ensemble is better calibrated (lower Brier) but more conservative (assigns high probability to favorites, misses upsets). For bracket challenges, this tradeoff may matter — include both metrics in the recommended model row.

### matplotlib Agg Pattern (from project codebase)

```python
# Source: src/models/evaluate.py lines 26-28 (verified by inspection)
import matplotlib
matplotlib.use("Agg")  # Must be called BEFORE importing pyplot
import matplotlib.pyplot as plt
```

### JSON Write Pattern (from project codebase)

```python
# Source: src/backtest/backtest.py lines 608-620 (verified by inspection)
import json, pathlib
output_path = pathlib.Path("models/selected.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(artifact, indent=2))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-model backtest not separated | Two separate JSON files (results.json, ensemble_results.json) | Phase 6 (06-04) | Phase 7 loads two files independently; no parsing complexity |
| matplotlib inline plots | matplotlib Agg backend + savefig | Phase 3 (evaluate.py) | Always use `matplotlib.use("Agg")` before pyplot import |

**Deprecated/outdated:**
- None for this phase.

## Open Questions

1. **XGB/LGB per-round accuracy: N/A columns vs. extended backtest**
   - What we know: `evaluate_xgb()`/`evaluate_lgb()` produce only `{year, brier, log_loss, n_games}`. No bracket-simulation-level data exists for individual XGB/LGB models.
   - What's unclear: Whether the planner will treat XGB/LGB as aggregate-only rows (simpler) or add `model='xgb'` / `model='lgb'` to `backtest()` (20-30 lines, full per-round data).
   - Recommendation: Add `model='xgb'` and `model='lgb'` support to `backtest()` in 07-01. The extension is minimal (single-model inference through bracket simulation, no meta-learner) and produces a complete comparison table. Without it, the XGB/LGB rows are meaningfully incomplete relative to the success criteria.

2. **models/selected.json schema for Phase 9 consumption**
   - What we know: Phase 9 plan 09-01 says "model loading from models/selected.json". Phase 9 needs to know which artifact to load (ensemble.joblib vs logistic_baseline.joblib) and how to instantiate the predict_fn.
   - What's unclear: Exactly what format Phase 9 expects. Phase 9 is not designed yet.
   - Recommendation: Include `model_artifact_path` and `model_type` fields in selected.json so Phase 9 has unambiguous loading instructions. At minimum: `{"selected_model": "ensemble", "model_artifact_path": "models/ensemble.joblib", "model_type": "TwoTierEnsemble", ...}`.

3. **Plotly vs. matplotlib for 07-02**
   - What we know: Roadmap calls for "Plotly bar chart"; Plotly is not installed; Phase 7 is CLI-first.
   - What's unclear: Whether the planner will add Plotly now (Phase 9 will need it) or defer to Phase 9.
   - Recommendation: Use matplotlib for Phase 7 (no new dependency, same pattern as rest of codebase, CLI-appropriate static PNG). Add Plotly in Phase 9 when Streamlit is also being added. Note in the plan that if the user wants interactive charts in the Streamlit UI later, the 07-02 visualization can be re-implemented with Plotly in Phase 9.

## Sources

### Primary (HIGH confidence)

- Live inspection of `backtest/results.json` and `backtest/ensemble_results.json` — schema confirmed; all field names and values verified; comparison deltas computed
- Live inspection of `src/backtest/backtest.py` — `_print_results_table()` at lines 627-701; `backtest()` signature at line 246; supported models: 'baseline' and 'ensemble' only (lines 309, 316)
- Live inspection of `src/models/train_xgboost.py` — `evaluate_xgb()` at line 134; returns `{year, brier, log_loss, n_games}` only (no per-round data)
- Live inspection of `src/models/evaluate.py` — `matplotlib.use("Agg")` pattern at lines 26-28; `plt.savefig()` pattern at lines 259-260
- Live inspection of `src/models/ensemble.py` — same matplotlib pattern at lines 32-35
- Live inspection of `pyproject.toml` — matplotlib 3.10.8 installed; plotly and seaborn NOT installed; tabulate NOT installed
- Phase 6 summaries `06-01-SUMMARY.md`, `06-02-SUMMARY.md` — XGB mean Brier=0.1908 (per-year: 2022=0.1898, 2023=0.2112, 2024=0.1837, 2025=0.1787); LGB mean Brier=0.1931
- `.planning/ROADMAP.md` — Phase 9 uses `models/selected.json` (line 242); 07-03 plan spec confirmed

### Secondary (MEDIUM confidence)

- `matplotlib.imshow` heatmap pattern — verified as standard matplotlib usage; RdYlGn_r colormap is standard for "lower is better" metrics

### Tertiary (LOW confidence)

- None for this phase.

## Metadata

**Confidence breakdown:**
- Data availability and schema: HIGH — all JSON files inspected directly
- Standard stack (no new deps): HIGH — all libraries verified installed via uv run
- Architecture patterns: HIGH — all patterns derived from existing codebase patterns
- XGB/LGB per-round data gap: HIGH — confirmed by reading evaluate_xgb/evaluate_lgb source
- models/selected.json Phase 9 schema: MEDIUM — Phase 9 not yet designed; schema recommendation is forward-looking

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable — no library changes expected; JSON schemas will not change)
