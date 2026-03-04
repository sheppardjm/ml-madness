---
phase: 04-bracket-simulator
plan: "05"
subsystem: simulator
tags: [numpy, override, bracket, monte-carlo, deterministic]

# Dependency graph
requires:
  - phase: 04-03
    provides: vectorized Monte Carlo simulation with occupants dict and prob_matrix
  - phase: 04-02
    provides: deterministic simulate_bracket() with slot tree traversal
provides:
  - simulate_bracket() with override_map={slot_id: team_id} support in both modes
  - Validation of override_map entries (slot_ids and team_ids) before dispatch
  - Deterministic: overridden slots marked with overridden=True in slot output
  - Monte Carlo: overridden slots pre-filled in occupant arrays, skipped in traversal
  - Upstream slots not contaminated by downstream overrides
affects:
  - 04-06 (final bracket output/serialization - override_map flows through)
  - UI phases (bracket lock-in feature uses override_map API)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pre-fill-and-skip pattern for MC overrides (pre-fill occupants, skip in traversal loop)
    - Deterministic override: continue-in-loop pattern (check override before resolving refs)
    - win_prob=1.0 sentinel for forced-winner slots (None in internal slot_prob dict)

key-files:
  created: []
  modified:
    - src/simulator/simulate.py

key-decisions:
  - "override_map validated once at top of simulate_bracket() before mode dispatch -- shared validation for both modes"
  - "Deterministic override: slot_prob[slot_id]=None for forced slots; output reports win_prob=1.0 (forced guarantee)"
  - "MC override: pre-fill occupants dict before traversal; overridden set tracks which to skip -- downstream sees forced winner naturally"
  - "Upstream slots (earlier rounds) are NOT changed by downstream overrides -- only overridden slot and its descendants affected"
  - "championship_game score prediction uses win_prob=1.0 when R6CH is forced (None champion_prob guard)"

patterns-established:
  - "Pre-fill-then-skip pattern: for MC overrides, fill occupants[slot_id] before traversal, then skip in loop"
  - "None sentinel in slot_prob signals forced winner; convert to 1.0 at output boundary"

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 4 Plan 5: Override Map Support Summary

**override_map={slot_id: team_id} parameter activates in both deterministic and Monte Carlo modes, forcing specified team to win slot with downstream cascade and zero upstream contamination**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-04T03:40:54Z
- **Completed:** 2026-03-04T03:44:08Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added shared override_map validation at top of simulate_bracket() covering both invalid slot_ids and invalid team_ids
- Deterministic mode: overridden slots skip predict_fn call, forced winner placed directly, slot output includes overridden=True flag
- Monte Carlo mode: overridden slots pre-filled as np.full(n_runs, forced_team_idx) before traversal, then skipped in traversal loop
- Upstream slots verified unaffected by downstream overrides (R6CH override leaves R1W1-R4W1 winners unchanged)
- MC champion confidence=1.0 when R6CH overridden (all runs force the same winner)

## Task Commits

1. **Task 1: Add override_map support to both simulation modes** - `c894622` (feat)

**Plan metadata:** (committed with SUMMARY.md)

## Files Created/Modified

- `src/simulator/simulate.py` - override_map support in simulate_bracket(), _simulate_deterministic(), _simulate_monte_carlo(); updated __main__ with 6 override test cases

## Decisions Made

- override_map validated once at top of simulate_bracket() before mode dispatch -- shared validation for both modes avoids code duplication
- Deterministic override: slot_prob[slot_id]=None for forced slots; output reports win_prob=1.0 (the team is guaranteed to occupy that slot)
- MC override: pre-fill occupants dict before traversal; overridden set tracks which to skip -- downstream slots see the forced winner naturally flowing through the occupants dict
- Upstream slots are NOT changed by downstream overrides -- the traversal still executes R1, R2, etc. in topological order; only slots in override_map are skipped
- championship_game score prediction uses win_prob=1.0 when R6CH is forced (None champion_prob guard added)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- override_map fully operational for both modes; ready for plan 04-06 (final bracket output / serialization)
- API contract is stable: simulate_bracket(seedings, predict_fn, mode, ..., override_map={slot_id: team_id})
- The override_map parameter was already in the function signature (from 04-02 for API stability) -- this plan implemented the actual behavior

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-04*
