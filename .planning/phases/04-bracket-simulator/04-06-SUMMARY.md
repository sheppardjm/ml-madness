---
phase: 04-bracket-simulator
plan: 06
subsystem: testing
tags: [simulation, monte-carlo, calibration, validation, integration-test, upset-rate]

# Dependency graph
requires:
  - phase: 04-05
    provides: override_map bracket lock-in for both deterministic and MC modes
  - phase: 04-04
    provides: championship score prediction in deterministic mode
  - phase: 04-03
    provides: Monte Carlo simulation with vectorized numpy runs
  - phase: 04-02
    provides: deterministic simulate_bracket() foundation
  - phase: 04-01
    provides: bracket_schema (seedings, predict_fn, slot tree)

provides:
  - Phase 4 integration test verifying all 5 success criteria
  - check_upset_rate() using complement formula for Monte Carlo calibration sanity check
  - validate_phase4() callable for automated regression testing of bracket simulator

affects:
  - phase-05-monte-carlo-calibration
  - phase-06-ensemble-model
  - phase-09-ui
  - phase-10-deployment

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Complement formula for P(at least one event): 1 - product(1 - p_i)"
    - "Integration test module that imports and exercises all Phase 4 components"
    - "WARN-not-FAIL pattern for calibration sanity checks that block progress only on hard assertion failures"

key-files:
  created:
    - src/simulator/validate.py
  modified: []

key-decisions:
  - "Upset rate 73.0% far exceeds 5% threshold -- ClippedCalibrator [0.05, 0.89] allows sufficient 10+ seed advancement probability; no model overconfidence issue"
  - "Complement formula used for upset rate (1 - product(1-p_i)) rather than simple sum -- mathematically correct for correlated events across 8 Sweet 16 slots"
  - "check_upset_rate() uses warnings.warn() not raise -- upset rate below threshold is a calibration WARN not a hard error"
  - "validate_phase4() passes stats_lookup to simulate_bracket() so championship_game key is populated and criterion 4 can assert plausible score values"

patterns-established:
  - "Phase validation module pattern: single function verifies all success criteria with structured PASS/WARN/FAIL output"
  - "Integration test combines shared setup (seedings, predict_fn) with criteria-specific assertions"

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 4 Plan 06: Phase 4 Integration Validation Summary

**Phase 4 integration test validating all 5 success criteria: 5/5 PASS with upset rate 73.0%, championship score 72-63 (total 135), and 16-seed override confirmed in both deterministic and Monte Carlo modes.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T03:46:46Z
- **Completed:** 2026-03-04T03:48:15Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `src/simulator/validate.py` with `check_upset_rate()` and `validate_phase4()` functions
- All 5 Phase 4 success criteria verified in single integration test
- Upset rate 73.0% (complement formula: P(at least one 10+ seed in Sweet 16) -- well above 5% threshold, confirming ClippedCalibrator allows realistic upsets)
- Phase 4 complete: bracket simulator fully validated and ready for Phase 5

## Task Commits

Each task was committed atomically:

1. **Task 1: Create validate.py with upset rate check and Phase 4 success criteria test** - `7f12d5b` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/simulator/validate.py` - Phase 4 integration test; check_upset_rate() + validate_phase4() exports

## Decisions Made

- Upset rate 73.0% far exceeds 5% threshold -- the complement formula correctly accounts for all 8 Sweet 16 slots (4 regions x 2 spots each); many 10+ seeds have non-trivial Sweet 16 probability after ClippedCalibrator
- Chose complement formula (1 - product(1 - p_i)) over simple sum to avoid double-counting; directionally conservative but more mathematically sound
- validate_phase4() passes stats_lookup to simulate_bracket() explicitly so championship_game is populated (criterion 4 requires it)
- check_upset_rate() issues warnings.warn() not a hard raise -- upset rate is a calibration sanity check, not a correctness requirement

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 4 is complete. All 6 plans executed successfully:
- 04-01: bracket_schema (seedings, predict_fn, slot tree)
- 04-02: deterministic simulate_bracket()
- 04-03: Monte Carlo simulate_bracket() (10K runs in 0.21s)
- 04-04: championship score prediction (tempo-based rule model)
- 04-05: override_map bracket lock-in (both modes)
- 04-06: Phase 4 integration validation (5/5 criteria PASS)

Ready for Phase 5 (Monte Carlo calibration / ensemble model).

Key output facts for downstream phases:
- Bracket JSON contract: deterministic has {mode, season, slots, champion, championship_game}; MC has {mode, season, n_runs, champion, advancement_probs}
- Champion team_id=1222, win_prob=0.5425 (deterministic), confidence=31.8% (MC)
- Championship game: 72-63 (total 135, margin 9)
- Upset rate: 73.0% P(10+ seed in Sweet 16) -- model well-calibrated for upsets

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-04*
