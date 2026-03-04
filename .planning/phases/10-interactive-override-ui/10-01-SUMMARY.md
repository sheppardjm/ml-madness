---
phase: 10-interactive-override-ui
plan: 01
subsystem: ui
tags: [streamlit, override_map, session_state, simulation, cache_data]

# Dependency graph
requires:
  - phase: 09-bracket-visualization-ui
    provides: "app.py with run_deterministic/run_monte_carlo calls and data_loader.py with cached simulation functions"
  - phase: 04-bracket-simulator
    provides: "simulate_bracket() with override_map parameter (plan 04-05)"
provides:
  - override_map flows from app.py session_state through data_loader cached functions to simulate_bracket()
  - Session state initialization for override_map as empty dict on first load
  - Cache invalidation via hash_funcs for override-aware cache keys
  - Sidebar override count display when overrides are active
affects:
  - 10-02-interactive-override-ui (needs override_map plumbing in place to wire UI controls)
  - future plans that add override controls, reset buttons, SVG visual feedback

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "hash_funcs={dict: lambda d: str(sorted(d.items()))} pattern for Streamlit cache with dict params"
    - "Empty dict normalized to None before simulator call (override_map or None) to skip validation"
    - "Non-underscore override_map param enables cache key inclusion; underscore params (_predict_fn, _seedings) excluded"

key-files:
  created: []
  modified:
    - src/ui/data_loader.py
    - app.py

key-decisions:
  - "override_map uses regular (non-underscore) parameter naming so Streamlit includes it in cache key"
  - "hash_funcs with str(sorted(d.items())) provides deterministic dict hashing for cache invalidation"
  - "Empty dict normalized to None via 'override_map or None' before passing to simulate_bracket() (avoids unnecessary validator overhead)"
  - "Sidebar override count display shows st.warning with count when override_map is non-empty"

patterns-established:
  - "Override plumbing pattern: session_state init -> extract + normalize -> pass to cached function -> forward to simulator"
  - "Cache invalidation for mutable params: use hash_funcs with deterministic string representation"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 10 Plan 01: Override Map Pipeline Wiring Summary

**override_map wired from app.py session_state through @st.cache_data functions into simulate_bracket() using hash_funcs cache invalidation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T16:52:04Z
- **Completed:** 2026-03-04T16:53:53Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Both run_deterministic() and run_monte_carlo() accept override_map with hash_funcs-based cache invalidation
- app.py initializes st.session_state["override_map"] = {} on first load and extracts/normalizes it before each simulation call
- Sidebar displays active override count as st.warning when override_map is non-empty
- Empty override_map normalized to None before simulator call to skip unnecessary validation

## Task Commits

Each task was committed atomically:

1. **Task 1: Add override_map parameter to cached simulation functions** - `de872aa` (feat)
2. **Task 2: Add session_state initialization and override-aware simulation calls in app.py** - `d6cf5f2` (feat)

**Plan metadata:** see final docs commit below

## Files Created/Modified
- `src/ui/data_loader.py` - Added override_map param + hash_funcs to run_deterministic() and run_monte_carlo(); updated docstrings
- `app.py` - Added session_state init for override_map, extraction/normalization, override-aware sim calls, sidebar override count

## Decisions Made
- override_map is a regular (non-underscore) parameter so Streamlit includes it in the cache key. _predict_fn and _seedings remain underscore-prefixed because they are unhashable.
- hash_funcs uses `str(sorted(d.items()))` for deterministic dict hashing — consistent with Python dict ordering guarantees while remaining simple and transparent.
- Empty dict normalized to None with `override_map or None` before passing to simulate_bracket() — avoids the validator path inside the simulator when no overrides exist (per research pitfall 4 in 10-RESEARCH.md).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Both tasks verified cleanly:
- `override_map` in both function signatures confirmed via inspect.signature()
- app.py parses without syntax errors (ast.parse())
- data_loader.py: 8 occurrences of override_map (meets >=8 requirement)
- app.py: 8 occurrences of override_map (meets >=5 requirement)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Override pipeline fully wired: session_state -> cache key -> simulate_bracket()
- Plan 10-02 can now add UI controls (match selectors, probability inputs) that write to st.session_state["override_map"] and the plumbing will propagate overrides into simulation results automatically
- No blockers for Plan 10-02

---
*Phase: 10-interactive-override-ui*
*Completed: 2026-03-04*
