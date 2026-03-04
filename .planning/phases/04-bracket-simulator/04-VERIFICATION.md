---
phase: 04-bracket-simulator
verified: 2026-03-04T03:51:41Z
status: passed
score: 5/5 must-haves verified
---

# Phase 4: Bracket Simulator Verification Report

**Phase Goal:** A `simulate_bracket()` function accepts team seedings, a predict function, and an optional override map, then fills all 67 tournament games using both deterministic (highest-probability winner) and Monte Carlo (10,000+ Bernoulli draws) modes, producing bracket JSON with full slot addressing.
**Verified:** 2026-03-04T03:51:41Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                                              | Status     | Evidence                                                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `simulate_bracket(..., mode="deterministic")` returns bracket JSON with all 67 slots filled with team_id and win_prob                             | VERIFIED   | Live run: 67 slots, no slots missing team_id or win_prob, full slot addressing (W16 through R6CH), champion at team_id=1222, win_prob=0.5425       |
| 2   | `simulate_bracket(..., mode="monte_carlo", n_runs=10000)` returns per-team advancement probs for each round and champion confidence              | VERIFIED   | Live run: 10,000 runs in <1s, 68 teams with advancement_probs, champion confidence=31.8%, round keys: Round of 64 through Championship + Champion   |
| 3   | Monte Carlo produces plausible upset rates: at least 5% of 10,000 simulations show a 10-or-higher seed reaching Sweet 16                         | VERIFIED   | check_upset_rate() returns 72.95% (threshold: 5%) — ClippedCalibrator [0.05, 0.89] allows realistic upset probabilities                          |
| 4   | Champion prediction includes predicted championship game score (total and margin)                                                                  | VERIFIED   | championship_game key in deterministic output: total=135, margin=9, winner_score=72, loser_score=63 — within [100, 180] range, winner > loser     |
| 5   | Passing an override map `{slot_id: team_id}` re-runs simulation from that slot forward, producing different downstream results                    | VERIFIED   | override_map={'R2W1': 1110} changes R3W1 from team 1181 to team 1112; MC override forces confidence=1.0; upstream slots unaffected               |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                               | Expected                                    | Status      | Details                                                                 |
| -------------------------------------- | ------------------------------------------- | ----------- | ----------------------------------------------------------------------- |
| `src/simulator/__init__.py`            | Package marker                              | VERIFIED    | Exists (empty file, correct package marker)                             |
| `src/simulator/bracket_schema.py`      | Slot tree, seedings, predict_fn builder     | VERIFIED    | 389 lines, substantive — exports build_slot_tree, load_seedings, build_predict_fn, build_team_seed_map, slot_round_number, ROUND_NAMES |
| `src/simulator/simulate.py`            | simulate_bracket() with both modes          | VERIFIED    | 881 lines, substantive — exports simulate_bracket(), _simulate_deterministic(), _simulate_monte_carlo(), _build_prob_matrix(), _compute_advancement_probs() |
| `src/simulator/score_predictor.py`     | predict_championship_score() rule model     | VERIFIED    | 228 lines, substantive — exports predict_championship_score(); integrated into simulate.py deterministic output |
| `src/simulator/validate.py`            | Phase 4 integration test                   | VERIFIED    | 402 lines, substantive — exports check_upset_rate() and validate_phase4(); 5/5 criteria PASS confirmed by live run |

### Key Link Verification

| From                          | To                                          | Via                                               | Status  | Details                                                                                       |
| ----------------------------- | ------------------------------------------- | ------------------------------------------------- | ------- | --------------------------------------------------------------------------------------------- |
| `simulate.py`                 | `bracket_schema.py`                         | `from src.simulator.bracket_schema import ...`    | WIRED   | Imports ROUND_NAMES, SLOTS_CSV, build_slot_tree, build_team_seed_map, slot_round_number      |
| `simulate.py`                 | `score_predictor.py`                        | `from src.simulator.score_predictor import predict_championship_score` | WIRED | Imported at module level, called in _simulate_deterministic() to populate championship_game key |
| `validate.py`                 | `bracket_schema.py`                         | `from src.simulator.bracket_schema import ...`    | WIRED   | Imports build_predict_fn, build_team_seed_map, load_seedings                                 |
| `validate.py`                 | `simulate.py`                               | `from src.simulator.simulate import simulate_bracket` | WIRED | Calls simulate_bracket() in deterministic and Monte Carlo modes                              |
| `bracket_schema.py`           | `data/raw/kaggle/MNCAATourneySlots.csv`     | DuckDB read_csv in build_slot_tree()              | WIRED   | 67 slots loaded and verified for season=2025                                                 |
| `bracket_schema.py`           | `data/processed/seeds.parquet`              | DuckDB read_parquet in load_seedings()            | WIRED   | 68 seedings loaded and verified for season=2025                                              |
| `bracket_schema.py`           | `src/models/train_logistic.py`              | `from src.models.train_logistic import load_model, predict_matchup` | WIRED | Loaded inside build_predict_fn() closure; predict_fn produces 1v16 prob=0.8900              |
| `bracket_schema.py`           | `src/models/features.py`                   | `from src.models.features import compute_features, build_stats_lookup` | WIRED | Called inside predict_fn closure; stats_lookup shared with score_predictor                 |

### Requirements Coverage

| Requirement | Status      | Evidence                                                                                            |
| ----------- | ----------- | --------------------------------------------------------------------------------------------------- |
| SIML-01     | SATISFIED   | simulate_bracket() fills 67 slots in topological order, deterministic and monte_carlo modes both operational |
| SIML-02     | SATISFIED   | Monte Carlo: 10,000 runs, per-team advancement_probs with round names, champion confidence=31.8%    |
| SIML-03     | SATISFIED   | check_upset_rate() = 72.95% via complement formula — far above 5% threshold                        |
| SIML-04     | SATISFIED   | override_map validated, downstream slots cascade from forced winner, upstream slots unaffected; both modes tested |

### Anti-Patterns Found

No anti-patterns detected:
- Zero TODO/FIXME/placeholder occurrences across all 4 simulator source files
- No empty returns or stub implementations
- No console.log-only handlers
- One `NotImplementedError` for `mode='monte_carlo'` was present in plan 04-02 but was replaced with full implementation in plan 04-03 (confirmed by live run passing)

### Human Verification Required

None. All success criteria are programmatically verifiable and confirmed via live execution of `src/simulator/validate.py`.

### Gaps Summary

No gaps. All 5 observable truths are verified against the live codebase by running the integration test. The phase goal is fully achieved.

---

## Execution Evidence

All verification commands ran against the live codebase on 2026-03-04:

```
uv run python -m src.simulator.validate

==================================================
PHASE 4 SUCCESS CRITERIA CHECK
Season: 2025
==================================================

Loading seedings and predict_fn...
Model loaded (sklearn 1.8.0)
Using calibrated model (method=isotonic, clip=[0.05, 0.89])
  Seedings: 68 teams loaded

--- Criterion 1: Deterministic bracket fill ---
  Slots filled: 67/67
  Champion: team_id=1222, win_prob=0.5425
  [PASS] 1. Deterministic bracket: 67 slots filled, champion identified

--- Criterion 2: Monte Carlo advancement probabilities ---
  n_runs: 10,000
  Champion: team_id=1222, confidence=31.8%
  Teams with advancement probs: 68
  [PASS] 2. Monte Carlo: 10,000 runs, champion at 31.8% confidence, 68 teams with advancement probs

--- Criterion 3: Upset rate calibration ---
  [PASS] 3. Upset rate: 73.0% (threshold: >= 5%)

--- Criterion 4: Championship score prediction ---
  predicted_total:  135
  predicted_margin: 9
  winner_score:     72
  loser_score:      63
  [PASS] 4. Championship score: Total 135, Margin 9 (Winner 72 - Loser 63)

--- Criterion 5: Override map ---
  Using 16-seed team_id=1110 for override test
  Deterministic: champion=1110 (16-seed), R6CH overridden=True
  Monte Carlo: champion=1110 (16-seed), confidence=100%
  [PASS] 5. Override map: 16-seed forced as champion in both deterministic and Monte Carlo modes

==================================================
PHASE 4 RESULTS
==================================================
[PASS] 1. Deterministic bracket: 67 slots filled, champion identified
[PASS] 2. Monte Carlo: 10,000 runs, champion at 31.8% confidence, 68 teams with advancement probs
[PASS] 3. Upset rate: 73.0% (threshold: >= 5%)
[PASS] 4. Championship score: Total 135, Margin 9 (Winner 72 - Loser 63)
[PASS] 5. Override map: 16-seed forced as champion in both modes

Phase 4: 5/5 criteria PASS
==================================================
```

---

_Verified: 2026-03-04T03:51:41Z_
_Verifier: Claude (gsd-verifier)_
