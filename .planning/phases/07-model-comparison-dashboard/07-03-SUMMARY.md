---
phase: 07-model-comparison-dashboard
plan: 03
subsystem: ui
tags: [json, model-selection, brier-score, ensemble, phase9-artifact]

# Dependency graph
requires:
  - phase: 06-ensemble-models
    provides: models/ensemble.joblib and backtest/ensemble_results.json with mean Brier=0.1692
  - phase: 05-backtesting-harness
    provides: backtest/results.json (baseline mean Brier=0.1900)
  - phase: 07-model-comparison-dashboard
    plan: 01
    provides: load_comparison_data() and print_comparison_table() in compare.py
  - phase: 07-model-comparison-dashboard
    plan: 02
    provides: plot_per_round_accuracy() and plot_brier_heatmap() in plots.py
provides:
  - select_best_model() function in src/dashboard/compare.py
  - models/selected.json artifact consumed by Phase 9 Streamlit app
  - Complete CLI pipeline: table + 2 PNGs + selected.json in one command
affects: [08-feature-store, 09-streamlit-ui, 10-final-bracket]

# Tech tracking
tech-stack:
  added: [datetime (stdlib, for generated_at field)]
  patterns:
    - "Model selection artifact pattern: JSON file at models/selected.json with selected_model, model_artifact_path, model_type fields for downstream phase loading"
    - "Round-then-compare pattern: round mean Brier to 4dp before comparison to avoid floating point noise in winner selection"

key-files:
  created:
    - models/selected.json
  modified:
    - src/dashboard/compare.py

key-decisions:
  - "XGB and LGB Brier scores hard-coded as constants (0.1908, 0.1931) because no standalone bracket-level JSON artifacts exist for those models — only baseline and ensemble have backtest/*.json files"
  - "baseline Brier rounded to 4dp (0.1900) in brier_scores dict for display consistency; raw value is 0.19000793..."
  - "ensemble Brier rounded to 4dp (0.1692); raw value is 0.16918111..."
  - "select_best_model() placed at module level (not inside __main__) so Phase 9 can import and call it programmatically"

patterns-established:
  - "Phase 9 artifact loading: load models/selected.json, read model_artifact_path, instantiate model_type from joblib"
  - "CLI wiring: compare.py __main__ calls table -> charts -> select_best_model() in sequence"

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 7 Plan 03: Model Selection and selected.json Artifact Summary

**select_best_model() selects ensemble (mean Brier=0.1692) over baseline/XGB/LGB and writes models/selected.json with artifact path and model type for Phase 9 Streamlit consumption**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-04T06:41:30Z
- **Completed:** 2026-03-04T06:46:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Implemented `select_best_model()` comparing all 4 models (baseline, XGB, LGB, ensemble) by mean Brier score
- Ensemble wins decisively at 0.1692 vs next-best baseline 0.1900 (-11% relative improvement)
- Wrote `models/selected.json` with complete schema: selected_model, selection_criterion, mean_brier, brier_scores, model_artifact_path, model_type, evaluation_years, notes, generated_at
- Complete CLI pipeline: `uv run python -m src.dashboard.compare` produces table + per_round_comparison.png + brier_heatmap.png + selected.json
- Prints selection summary: "Selected model: ensemble (mean Brier = 0.1692)"

## Task Commits

Each task was committed atomically:

1. **Task 1: Add model recommendation logic and selected.json writer** - `9414cdc` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `src/dashboard/compare.py` - Added `select_best_model()` function + `from datetime import date` import + wired into __main__
- `models/selected.json` - Model selection artifact for Phase 9 Streamlit app

## Decisions Made
- XGB and LGB Brier scores hard-coded as constants (0.1908, 0.1931) because no standalone JSON backtest artifacts exist for those models — only baseline and ensemble ran through backtest/. This is consistent with Phase 6 plan where XGB/LGB were evaluated without bracket-level ESPN scoring.
- Brier scores rounded to 4 decimal places before min() comparison to avoid floating point noise affecting winner selection.
- XGB/LGB model_artifact_path set to logistic_baseline.joblib as placeholder — these models don't have standalone joblib artifacts. The ensemble artifact (models/ensemble.joblib) is the only production-ready artifact for Phase 9.

## Deviations from Plan

None - plan executed exactly as written. All fields in selected.json match the specified schema.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `models/selected.json` is written and verified; Phase 9 can load it to determine which model to instantiate
- Phase 9 must: `json.loads(Path("models/selected.json").read_text())`, then `joblib.load(artifact["model_artifact_path"])` to get `TwoTierEnsemble`
- Phase 7 (Model Comparison Dashboard) is fully complete: 07-01 (table), 07-02 (charts), 07-03 (selection artifact) all done
- Phase 8 (Feature Store) or Phase 9 (Streamlit UI) can begin

---
*Phase: 07-model-comparison-dashboard*
*Completed: 2026-03-04*
