---
phase: 07-model-comparison-dashboard
verified: 2026-03-04T06:46:04Z
status: gaps_found
score: 4/6 must-haves verified
gaps:
  - truth: "The table includes a recommended model row identifying the best performer by multi-year Brier score"
    status: failed
    reason: "The printed comparison table has no Status column or BEST/RECOMMENDED marker on any model row. The 07-01 PLAN specified a 'BEST Brier' Status column but it was not implemented. The selection is announced post-table via 'Selected model: ensemble (mean Brier = 0.1692)' but that is a CLI footer line, not a row in the formatted table."
    artifacts:
      - path: "src/dashboard/compare.py"
        issue: "print_comparison_table() header is 'Model | Mean Brier | Mean Acc | Mean ESPN | Upset Det Rate' — no Status column. Ensemble row is not marked as RECOMMENDED or BEST. The 07-01 PLAN.md format specified 'BEST Brier' in Status column."
    missing:
      - "Status column in summary table header"
      - "BEST Brier (or RECOMMENDED) marker on the ensemble row in the table body"

  - truth: "Running a single command prints a formatted table comparing logistic regression baseline vs. XGBoost vs. LightGBM vs. ensemble across the 2022-2025 holdout years with per-round accuracy, overall Brier score, and upset detection rate"
    status: partial
    reason: "The table only prints two model rows (baseline and ensemble). XGBoost and LightGBM are not shown as table rows — they appear only as hardcoded constants in select_best_model()'s brier_scores dict and are not rendered in the printed table at all. ROADMAP success criterion 1 explicitly names all four models as required in the table."
    artifacts:
      - path: "src/dashboard/compare.py"
        issue: "print_comparison_table() iterates model_order = ['baseline', 'ensemble'] only. XGB (0.1908) and LGB (0.1931) Brier scores exist as _XGB_MEAN_BRIER and _LGB_MEAN_BRIER constants but are never printed in the table. The select_best_model() post-table output does include all 4 in brier_scores JSON but not in the displayed table."
    missing:
      - "XGB and LGB rows in the printed comparison table (even if limited to Brier score only, noting they lack per-round data)"
      - "Note in table that XGB/LGB rows show Brier only (no per-round accuracy) so the table is not misleading"
---

# Phase 7: Model Comparison Dashboard Verification Report

**Phase Goal:** A side-by-side comparison table shows baseline vs. ensemble performance across all backtest years, per round, and on upset detection rate — making it clear which model to use for the 2026 bracket.
**Verified:** 2026-03-04T06:46:04Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `uv run python -m src.dashboard.compare` prints formatted comparison table | VERIFIED | Command runs, exits 0, prints formatted 4-section table |
| 2 | Table shows per-model rows with Brier, accuracy, ESPN, and upset detection rate | VERIFIED | Verified: baseline row (0.1900, 69.0%, 912.5, 64.1%) and ensemble row (0.1692, 74.3%, 1037.5, 34.6%) both print correctly |
| 3 | Table shows per-year Brier scores for 2022-2025 with deltas | VERIFIED | All 4 years printed with delta column and winner indicator (<<) |
| 4 | Table shows per-round accuracy averages across 6 rounds for both models | VERIFIED | All 6 rounds (R64 through Championship) printed with 4-year means and deltas |
| 5 | Upset detection tradeoff note is printed | VERIFIED | Full UPSET DETECTION TRADEOFF section prints with per-year breakdown and narrative |
| 6 | Table compares all 4 models: baseline, XGBoost, LightGBM, and ensemble | FAILED | Table only shows 2 rows (baseline and ensemble). XGB and LGB are absent from printed table. ROADMAP criterion 1 explicitly requires all 4. |
| 7 | Table includes a recommended model row identifying best performer by Brier | FAILED | No RECOMMENDED/BEST row or Status column exists in the table. Post-table CLI output says "Selected model: ensemble" but this is not a table row. |
| 8 | Bar chart visualizes per-round accuracy differences between models | VERIFIED | models/per_round_comparison.png generated at 44,801 bytes (150 DPI), 6 grouped bars with steelblue/darkorange, value labels |
| 9 | Heatmap shows Brier score by model and year | VERIFIED | models/brier_heatmap.png generated at 42,368 bytes (150 DPI), RdYlGn_r colormap, annotated cells |
| 10 | models/selected.json written with ensemble as winner | VERIFIED | selected_model=ensemble, model_artifact_path=models/ensemble.joblib, model_type=TwoTierEnsemble, all 4 brier_scores present |

**Score:** 4/6 ROADMAP success criteria verified (truths 1-5 and 8-10 pass; truths 6 and 7 fail)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/dashboard/__init__.py` | Package init | VERIFIED | Exists, 0 bytes (empty init as intended) |
| `src/dashboard/compare.py` | Data loading + table printing | VERIFIED | 460 lines, real implementation, exports load_comparison_data, print_comparison_table, select_best_model |
| `src/dashboard/plots.py` | Bar chart + heatmap functions | VERIFIED | 200 lines, real matplotlib implementation, exports plot_per_round_accuracy, plot_brier_heatmap |
| `models/selected.json` | Model selection artifact | VERIFIED | 633 bytes, valid JSON, correct schema for Phase 9 |
| `models/per_round_comparison.png` | Grouped bar chart PNG | VERIFIED | 44,801 bytes (44 KB), non-empty, generated at 150 DPI |
| `models/brier_heatmap.png` | Brier score heatmap PNG | VERIFIED | 42,368 bytes (42 KB), non-empty, generated at 150 DPI |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/dashboard/compare.py` | `backtest/results.json` | `json.loads(baseline_file.read_text())` | WIRED | File existence checked, loaded with FileNotFoundError on missing |
| `src/dashboard/compare.py` | `backtest/ensemble_results.json` | `json.loads(ensemble_file.read_text())` | WIRED | File existence checked, loaded with FileNotFoundError on missing |
| `src/dashboard/compare.py` | `src/dashboard/plots.py` | `from src.dashboard.plots import plot_per_round_accuracy, plot_brier_heatmap` in `__main__` | WIRED | Import in __main__ block; both functions called and confirmed printing save confirmation |
| `src/dashboard/plots.py` | `models/per_round_comparison.png` | `plt.savefig(save_path, dpi=150)` | WIRED | File written at 44,801 bytes; pathlib.mkdir guard ensures models/ exists |
| `src/dashboard/plots.py` | `models/brier_heatmap.png` | `plt.savefig(save_path, dpi=150)` | WIRED | File written at 42,368 bytes |
| `src/dashboard/compare.py` | `models/selected.json` | `output_path.write_text(json.dumps(artifact, indent=2))` | WIRED | 633 bytes written, correct schema validated |
| `models/selected.json` | `models/ensemble.joblib` | `model_artifact_path` field | WIRED | ensemble.joblib exists at 364,386 bytes; path is correct for Phase 9 loading |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| BACK-03: Model comparison dashboard showing baseline vs ensemble performance | PARTIAL | Core table exists and runs. XGB/LGB rows missing from table. No RECOMMENDED row in table. The dashboard goal ("clear which model to use") is partially met — selection is communicated post-table — but ROADMAP criteria 1 and 2 are not fully satisfied. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/dashboard/compare.py` | 361-363 | XGB/LGB `model_artifact_path` points to `models/logistic_baseline.joblib` (placeholder) | Warning | These models cannot win the selection (ensemble wins at 0.1692), so this path is never used in practice. If ensemble were to lose in a future re-run, Phase 9 would load the wrong artifact. |

### Human Verification Required

None — all key behaviors are verifiable programmatically. The CLI runs headlessly and generates all artifacts. Visual inspection of chart quality (colors, labels, readability) is optional but not blocking for goal assessment.

### Gaps Summary

Two ROADMAP success criteria are unmet:

**Gap 1 — Missing XGB/LGB rows in comparison table (ROADMAP criterion 1):**
The table shows only baseline and ensemble as rows. ROADMAP criterion 1 explicitly says the table must compare "logistic regression baseline vs. XGBoost vs. LightGBM vs. ensemble." XGB (mean Brier 0.1908) and LGB (0.1931) are known values (hardcoded in compare.py as constants) but are never rendered in the printed table. The plan acknowledged they lack per-round data but did not add Brier-only rows to the table. This is a concrete omission relative to the ROADMAP specification.

**Gap 2 — No RECOMMENDED row in the comparison table (ROADMAP criterion 2):**
ROADMAP criterion 2 says "The table includes a recommended model row identifying the best performer by multi-year Brier score." The 07-01 PLAN.md also specified a Status column with "BEST Brier" marking. Neither was implemented. The ensemble is identified as the winner, but only via a post-table CLI line ("Selected model: ensemble (mean Brier = 0.1692)") rather than as a labeled row or column in the formatted table itself. The information is present, but not in the form the ROADMAP specified.

Everything else is complete and substantive: the comparison table runs correctly, per-year Brier, per-round accuracy, and upset detection sections all work, both charts generate correctly, and models/selected.json is a valid Phase 9 artifact. These two gaps are presentation-level — the analytical work is done, but the table format does not match the ROADMAP specification.

---

_Verified: 2026-03-04T06:46:04Z_
_Verifier: Claude (gsd-verifier)_
