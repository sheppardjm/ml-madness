---
phase: 07-model-comparison-dashboard
plan: 01
subsystem: ui
tags: [dashboard, comparison-table, json, formatted-output, cli]

# Dependency graph
requires:
  - phase: 05-backtesting-harness
    provides: backtest/results.json (baseline per-year metrics 2022-2025)
  - phase: 06-ensemble-models
    provides: backtest/ensemble_results.json (ensemble per-year metrics 2022-2025)
provides:
  - src/dashboard/__init__.py — dashboard package init
  - src/dashboard/compare.py — data loading + formatted comparison table CLI
  - load_comparison_data() — reads both JSON result files into keyed dict
  - print_comparison_table() — four-section stdout table (summary, per-year Brier, per-round accuracy, upset detection)
affects: [07-02, 07-03, 09-streamlit-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dashboard data loading via json.loads() from JSON artifacts (no model imports)"
    - "Four-section comparison table following _print_results_table() f-string pattern from backtest.py"
    - "Helper functions for metric aggregation: _compute_mean_upset_rate(), _compute_mean_per_round_accuracy()"

key-files:
  created:
    - src/dashboard/__init__.py
    - src/dashboard/compare.py
  modified: []

key-decisions:
  - "07-01: Only baseline and ensemble included per plan spec — no XGB/LGB rows (those models lack per-round bracket data)"
  - "07-01: print_comparison_table() split into 4 sections: summary table, per-year Brier, per-round accuracy, upset tradeoff note"
  - "07-01: Delta row added to summary and per-year sections showing ensemble - baseline direction"
  - "07-01: Winner indicators (<< / >>) added to per-year Brier and per-round accuracy rows for at-a-glance comparison"

patterns-established:
  - "Pattern: load_comparison_data() is the canonical data loader for Phase 7 — subsequent plans (07-02, 07-03) import from here"
  - "Pattern: Dashboard module reads JSON only — no model artifacts loaded (compare.py has zero ML imports)"

# Metrics
duration: 1min
completed: 2026-03-04
---

# Phase 7 Plan 01: Dashboard Module with Comparison Table Summary

**Formatted stdout comparison table printing baseline vs. ensemble across 4 metrics, 4 years, and 6 rounds — with upset detection tradeoff narrative**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-04T06:34:01Z
- **Completed:** 2026-03-04T06:35:28Z
- **Tasks:** 1
- **Files modified:** 2 (created)

## Accomplishments

- Created `src/dashboard/` package with `__init__.py` and `compare.py`
- `load_comparison_data()` reads `backtest/results.json` and `backtest/ensemble_results.json` with clear FileNotFoundError messages if files are missing
- `print_comparison_table()` prints four clean sections: summary table with delta row, per-year Brier with delta and winner indicators, per-round accuracy 4-year means, and upset detection tradeoff note
- Runnable via `uv run python -m src.dashboard.compare` (exit 0, no external dependencies beyond stdlib json/pathlib)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create dashboard module with data loading** - `16d3569` (feat)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `src/dashboard/__init__.py` — Empty package init (same pattern as other src subpackages)
- `src/dashboard/compare.py` — Data loading + four-section comparison table; exports `load_comparison_data`, `print_comparison_table`

## Decisions Made

- Only baseline and ensemble included per plan spec — XGB/LGB have no per-round bracket data (they were evaluated at matchup level only in Phase 6); those models may be added in a future plan if needed
- Delta row included in summary table and per-year section to make directional improvement immediately visible
- Winner indicators (`<<` for ensemble wins, `>>` for baseline wins) added to per-round and per-year rows for at-a-glance scanning
- Tradeoff note formats upset detection per year (not just aggregate mean) to show the widening gap trend (2022: -23.8pp -> 2025: -36.4pp)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Both JSON result files exist from Phase 5 and Phase 6.

## Next Phase Readiness

- `load_comparison_data()` is ready for 07-02 to import and use for chart generation
- `src/dashboard/compare.py` is the stable entry point; 07-02 will add `plot_per_round_accuracy()` and `plot_brier_heatmap()` to this module
- 07-03 will add `select_best_model()` which writes `models/selected.json` (consumed by Phase 9)
- No blockers for 07-02 or 07-03

---
*Phase: 07-model-comparison-dashboard*
*Completed: 2026-03-04*
