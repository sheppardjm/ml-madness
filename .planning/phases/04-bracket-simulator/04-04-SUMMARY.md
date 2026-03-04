---
phase: 04-bracket-simulator
plan: 04
subsystem: simulator
tags: [ncaa, bracket, score-prediction, tempo, python]

# Dependency graph
requires:
  - phase: 04-01
    provides: build_predict_fn() returning (predict_fn, stats_lookup) tuple; bracket_schema.py foundational module
  - phase: 04-02
    provides: simulate_bracket() deterministic mode with full slot traversal and champion output
  - phase: 03-01
    provides: build_stats_lookup() and adj_t field in stats dict keyed by (season, team_id)
provides:
  - predict_championship_score() rule-based function in src/simulator/score_predictor.py
  - championship_game key in simulate_bracket() deterministic output with predicted total, margin, winner_score, loser_score
  - Graceful fallback to historical mean tempo (67.0) when adj_t is missing or zero sentinel
affects:
  - 04-05 (bracket lock-in / export) will include championship_game in output JSON
  - 04-06 (bracket API) serves championship_game as part of bracket prediction endpoint
  - Phase 9/10 (UI) can display "We predict Team X wins 72-63"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Rule-based score prediction using historical tempo coefficient (not ML regression)
    - Graceful degradation pattern: optional stats_lookup, championship_game=None when absent
    - Fallback sentinel detection: adj_t==0.0 treated as missing (matches features.py convention)

key-files:
  created:
    - src/simulator/score_predictor.py
  modified:
    - src/simulator/simulate.py

key-decisions:
  - "Rule-based tempo formula sufficient (R^2~0.25 for full regression); TEMPO_COEF=3.43, TEMPO_INTERCEPT=-89.7 from historical championship game analysis"
  - "adj_t==0.0 is a sentinel for missing data (per features.py convention) -- treated as fallback trigger alongside key-not-found"
  - "championship_game key added only to deterministic mode (not monte_carlo) -- MC produces distribution, not a single game score"
  - "win_prob_a passed to predict_championship_score is the championship game win_prob from slot_prob['R6CH'] (not the full tournament win probability)"

patterns-established:
  - "Tempo formula: predicted_total = round(3.43 * avg_adj_t - 89.7), clamped [100, 180]"
  - "Margin formula: round((win_prob_a - 0.5) * 20 + 8), scales from 8 (coin flip) to ~16 (0.89 prob)"
  - "Score decomposition: winner_score = (total + margin) // 2; loser_score = total - winner_score"

# Metrics
duration: 5min
completed: 2026-03-03
---

# Phase 4 Plan 04: Score Predictor Summary

**Rule-based championship game score predictor using adj_t tempo formula (total = 3.43*avg_tempo - 89.7) and win probability margin scaling, integrated into simulate_bracket() deterministic output as championship_game key**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-04T03:36:40Z
- **Completed:** 2026-03-04T03:41:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Created `src/simulator/score_predictor.py` with `predict_championship_score()` producing plausible championship scores
- Integrated into `_simulate_deterministic()` -- deterministic output now includes `championship_game` key with `predicted_total`, `predicted_margin`, `winner_score`, `loser_score`, `winner_team_id`, `loser_team_id`
- Fallback to `HISTORICAL_MEAN_TEMPO=67.0` when `adj_t` is missing from stats_lookup or is the zero sentinel, with logging warning
- Graceful degradation: `championship_game=None` when `stats_lookup` not provided (backward compatible)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create score_predictor.py and integrate into simulate_bracket()** - `ac2c65d` (feat)

**Plan metadata:** _(to be committed with this SUMMARY.md)_

## Files Created/Modified

- `src/simulator/score_predictor.py` - Rule-based championship game score predictor; exports `predict_championship_score()`
- `src/simulator/simulate.py` - Added `predict_championship_score` import, `stats_lookup` param to `_simulate_deterministic()`, championship_game key in deterministic output

## Decisions Made

- **Rule-based not ML:** R^2 for tempo regression on championship totals is only ~0.25; adding a second ML model is not justified. Historical linear formula (TEMPO_COEF=3.43, TEMPO_INTERCEPT=-89.7) is sufficient.
- **adj_t==0.0 sentinel:** features.py stores `adj_t=0.0` when `adj_t` is NaN in the source data; score_predictor detects this and triggers the HISTORICAL_MEAN_TEMPO fallback, consistent with features.py convention.
- **championship_game in deterministic only:** Monte Carlo produces a distribution of outcomes, not a single game score. Adding score prediction to MC would require post-hoc computation from run occupants and is out of scope for this plan.
- **win_prob_a = slot_prob['R6CH']:** The win probability passed to predict_championship_score is the championship game win probability (probability of winning that specific game), not the overall tournament win probability.
- **Scores verified in 2025 run:** Deterministic simulation predicts team 1222 wins 72-63 over team 1196; plausible for a championship game.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - implementation was straightforward given the well-defined stats_lookup structure from Phase 3 and the clear slot topology from Phase 4 prior plans.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Score predictor complete; `championship_game` key ready for JSON export in plan 04-05
- `predict_championship_score` is importable and testable standalone
- Monte Carlo mode unchanged and still operational
- Ready for plan 04-05 (bracket lock-in and final JSON export)

---
*Phase: 04-bracket-simulator*
*Completed: 2026-03-03*
