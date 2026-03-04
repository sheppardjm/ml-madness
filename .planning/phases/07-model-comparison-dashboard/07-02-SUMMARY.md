---
phase: 07-model-comparison-dashboard
plan: 02
subsystem: ui
tags: [matplotlib, visualization, bar-chart, heatmap, dashboard, png]

# Dependency graph
requires:
  - phase: 07-01
    provides: load_comparison_data(), compare.py module, backtest JSON artifacts
  - phase: 06-04
    provides: backtest/ensemble_results.json with per_year Brier and per_round_accuracy
  - phase: 05-02
    provides: backtest/results.json with per_year Brier and per_round_accuracy
provides:
  - src/dashboard/plots.py with plot_per_round_accuracy() and plot_brier_heatmap()
  - models/per_round_comparison.png (grouped bar chart, regenerated on each run)
  - models/brier_heatmap.png (Brier heatmap, regenerated on each run)
  - compare.py __main__ block now calls both plot functions after printing table
affects:
  - 07-03-model-selection (final phase of dashboard; no direct plots dependency)
  - Any future dashboard expansion using matplotlib chart functions

# Tech tracking
tech-stack:
  added: [matplotlib (Agg backend), numpy]
  patterns:
    - matplotlib.use("Agg") set before pyplot import for headless/CLI compatibility
    - plot imports inside __main__ block to avoid slow matplotlib load on module import
    - pathlib.Path.parent.mkdir(parents=True, exist_ok=True) before savefig for safe directory creation
    - plt.close() after savefig to free memory

key-files:
  created:
    - src/dashboard/plots.py
    - models/per_round_comparison.png
    - models/brier_heatmap.png
  modified:
    - src/dashboard/compare.py

key-decisions:
  - "matplotlib imports placed inside __main__ block (not module top-level) to avoid slow import cost when compare.py is imported as a library"
  - "vmin=0.12, vmax=0.25 for heatmap colormap — covers observed Brier range [0.136, 0.193]; hard-coded for visual consistency across runs"
  - "Only baseline and ensemble plotted — XGB/LGB excluded as they lack per-round bracket-simulation data"

patterns-established:
  - "Agg backend pattern: matplotlib.use('Agg') before pyplot for any headless chart generation in this project"
  - "Lazy matplotlib import: keep plotting imports inside __main__ to preserve module import speed"

# Metrics
duration: ~2min
completed: 2026-03-04
---

# Phase 7 Plan 02: Visualization Charts Summary

**matplotlib grouped bar chart (per-round accuracy) and RdYlGn_r heatmap (Brier by model/year) saved as 150 DPI PNGs, wired into the CLI dashboard command**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T06:37:47Z
- **Completed:** 2026-03-04T06:38:46Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified counting generated PNGs)

## Accomplishments

- Created `src/dashboard/plots.py` with two chart functions using matplotlib Agg backend
- Grouped bar chart (steelblue/darkorange, 6 rounds, value labels) saved to `models/per_round_comparison.png` at 150 DPI — 44 KB
- Brier heatmap (RdYlGn_r, 2 models x 4 years, annotated cells) saved to `models/brier_heatmap.png` at 150 DPI — 41 KB
- `uv run python -m src.dashboard.compare` now prints full comparison table then generates both charts in a single command

## Task Commits

Each task was committed atomically:

1. **Task 1: Create visualization module with bar chart and heatmap** - `2d5cb00` (feat)
2. **Task 2: Wire plot functions into the CLI entry point** - `92aa88d` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/dashboard/plots.py` - Two matplotlib chart functions (plot_per_round_accuracy, plot_brier_heatmap)
- `src/dashboard/compare.py` - __main__ block updated to call plot functions after printing table
- `models/per_round_comparison.png` - Grouped bar chart output (44 KB, 150 DPI)
- `models/brier_heatmap.png` - Brier score heatmap output (41 KB, 150 DPI)

## Decisions Made

- **matplotlib lazy import:** Imports placed inside `__main__` block rather than module top-level so `from src.dashboard.compare import load_comparison_data` doesn't trigger slow matplotlib initialization. This preserves the "zero ML imports" design established in 07-01.
- **Heatmap vmin/vmax:** Fixed at 0.12–0.25 to cover the observed Brier range; hard-coded values ensure consistent color scale across repeated runs even if scores change slightly.
- **Only baseline and ensemble:** XGB and LGB are excluded from charts — they have no per-round bracket simulation data, only aggregate Brier from evaluate.py.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Both chart functions worked correctly on first execution. matplotlib Agg backend set per plan instructions — no display required in CLI context.

## User Setup Required

None - no external service configuration required. Both PNG files are generated automatically by running `uv run python -m src.dashboard.compare`.

## Next Phase Readiness

- 07-03 (model selection) can proceed immediately — it reads from `load_comparison_data()` and writes `models/selected.json`; no dependency on the chart files
- Both PNG charts are committed as generated artifacts and will be regenerated on each CLI run
- The dashboard command is now complete for all visual output: table + charts in one command

---
*Phase: 07-model-comparison-dashboard*
*Completed: 2026-03-04*
