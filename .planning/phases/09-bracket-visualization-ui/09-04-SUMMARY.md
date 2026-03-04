---
phase: 09-bracket-visualization-ui
plan: 04
subsystem: ui
tags: [streamlit, pandas, ProgressColumn, dataframe, advancement-table, monte-carlo]

# Dependency graph
requires:
  - phase: 09-01
    provides: "load_team_info(), run_monte_carlo(), seedings dict"
  - phase: 04-03
    provides: "mc_result['advancement_probs'] with Champion key per team_id"
provides:
  - "build_advancement_df() — 68-team DataFrame with per-round advancement probabilities"
  - "get_round_column_config() — Streamlit ProgressColumn config hiding SeedNum"
  - "Advancement Probabilities tab fully wired in app.py"
affects: ["phase 10 (future UI enhancements), any future export/share features"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LEFT JOIN pattern: iterate all_team_ids (not advancement_probs.keys()) so First Four losers show as 0.0% rows"
    - "SeedNum hidden via column_config[SeedNum] = None (stays in DataFrame for sort, hidden from display)"
    - "get_round_column_config() deferred import of streamlit — safe to import module at non-Streamlit runtime"

key-files:
  created:
    - src/ui/advancement_table.py
  modified:
    - app.py

key-decisions:
  - "all_team_ids = list(seedings.values()) as outer loop in build_advancement_df — LEFT JOIN ensures First Four losers included with 0.0 probabilities"
  - "_parse_seed_num() strips region prefix and play-in suffix (a/b) before int conversion; falls back to 99 for malformed labels"
  - "get_round_column_config() uses deferred 'import streamlit as st' inside function body — prevents import-time failure when module loaded outside Streamlit context"
  - "column_config['SeedNum'] = None hides SeedNum from user display while keeping it in DataFrame for default sort order"
  - "height=800 for st.dataframe — shows approximately 25 rows without excessive scrolling in typical browser viewport"

patterns-established:
  - "ProgressColumn pattern: format='%.1f%%', min_value=0.0, max_value=1.0 for probability columns"
  - "Deferred st import inside config-builder functions that must not run at module import time"

# Metrics
duration: 1min
completed: 2026-03-04
---

# Phase 9 Plan 04: Advancement Table Summary

**68-team sortable advancement probability table with ProgressColumn visual bars wired into Streamlit Advancement Probabilities tab**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-04T16:21:03Z
- **Completed:** 2026-03-04T16:22:26Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created `src/ui/advancement_table.py` with `build_advancement_df()` (LEFT JOIN pattern ensures all 68 teams including First Four losers appear) and `get_round_column_config()` (ProgressColumn for 7 round columns, SeedNum hidden)
- Replaced placeholder `st.info()` in Advancement tab with full `st.dataframe` using ProgressColumn visual bars, sortable by any column header
- Summary metrics row below table shows teams with Final Four/Champion chances and top champion probability

## Task Commits

Each task was committed atomically:

1. **Task 1: Create src/ui/advancement_table.py DataFrame builder** - `c465ff7` (feat)
2. **Task 2: Wire advancement table into app.py Advancement tab** - `7ff6012` (feat)

**Plan metadata:** (to be committed with this SUMMARY)

## Files Created/Modified
- `src/ui/advancement_table.py` — `build_advancement_df()` and `get_round_column_config()`; ROUND_COLS list; `_parse_seed_num()` helper
- `app.py` — Advancement tab replaced from placeholder to full table; import added for advancement_table module

## Decisions Made
- `all_team_ids = list(seedings.values())` as the outer loop (not `advancement_probs.keys()`) — guarantees First Four losers appear in table with 0.0% values, per research pitfall 4
- `_parse_seed_num()` strips leading region letter and trailing `a`/`b` play-in suffix before parsing integer seed; falls back to 99 for malformed labels so they sort to bottom
- `get_round_column_config()` uses a deferred `import streamlit as st` inside the function body — module can be imported safely during unit tests or non-Streamlit CLI contexts
- `column_config["SeedNum"] = None` is the Streamlit idiom for hiding a column from display while keeping it in the backing DataFrame (for pre-sort ordering)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- Phase 9 complete: Bracket tab (SVG), Advancement Probabilities tab (sortable table), and Champion tab are all wired
- Phase 10 (if applicable) can build on the existing tab structure and data pipeline without changes
- Advancement table is ready for any future filtering, search, or export enhancements

---
*Phase: 09-bracket-visualization-ui*
*Completed: 2026-03-04*
