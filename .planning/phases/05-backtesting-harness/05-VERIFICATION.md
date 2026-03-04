---
phase: 05-backtesting-harness
verified: 2026-03-04T04:58:58Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 5: Backtesting Harness Verification Report

**Phase Goal:** A `backtest()` function replays the feature-to-simulator pipeline against 2022, 2023, 2024, and 2025 tournament snapshots with strict data cutoff enforcement, producing a per-year accuracy and calibration table for the baseline model.
**Verified:** 2026-03-04T04:58:58Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `backtest(year_range=[2022,2023,2024,2025], model="baseline")` produces a table with per-round accuracy, ESPN bracket score, Brier, log-loss, and upset-detection rate for each year without manual data prep | VERIFIED | `results.json` contains all 4 years; each row has `per_round_accuracy`, `espn_score`, `brier`, `log_loss`, `upset_detection_rate`. Function accepts exact args from success criterion. |
| 2 | The 2025 backtest uses only data available before 2025 Selection Sunday (training set max season = 2024) | VERIFIED | `backtest.py` line 175: `train_df = df[df["Season"] < test_year]`; line 182: hard `assert train_df["Season"].max() < test_year`. 2025 Brier (0.1473588) matches Phase 3 evaluation delta=0.00e+00, confirming identical temporal fold. |
| 3 | Multi-year backtest covers all 4 distinct variance profiles with individual-year scores | VERIFIED | All 4 years present in `results.json`. Distinct upset profiles: 2022 (21 upsets — Saint Peter's era), 2023 (19), 2024 (19 — NC State run), 2025 (11 — all-chalk). ESPN scores vary widely: 570, 1070, 810, 1200. |
| 4 | Results written to `backtest/results.json` and reproducible by re-running harness | VERIFIED | File exists with 4026 bytes. `validate.py` C4 criterion re-runs `backtest()` and confirms 0 differences in `per_year` data (deterministic via `random_state=42`). Brier delta=0 across both runs. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/backtest/__init__.py` | Package marker | VERIFIED | Exists (0 bytes — intentional empty package marker) |
| `src/backtest/scoring.py` | `build_actual_slot_winners`, `score_bracket`, `compute_game_metrics`, ESPN constants | VERIFIED | 415 lines, exports all 5 required symbols, no stubs, fully wired |
| `src/backtest/backtest.py` | `backtest()` orchestration, per-year refitting, JSON output | VERIFIED | 454 lines, exports `backtest`, full implementation wired to all dependencies |
| `src/backtest/validate.py` | `validate_phase5()` validation callable | VERIFIED | 298 lines, exports `validate_phase5`, wired to `backtest()` and `results.json` |
| `backtest/results.json` | Reproducible per-year and summary metrics | VERIFIED | Exists, valid JSON, 4 per-year entries with all required fields, mean_brier=0.1900, mean_espn=912.5 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/backtest/scoring.py` | `data/raw/kaggle/MNCAATourneySeedRoundSlots.csv` | DuckDB `read_csv()` join | WIRED | Line 114: `read_csv('{seed_round_slots_csv}')` in DuckDB CTE |
| `src/backtest/scoring.py` | `data/processed/tournament_games.parquet` | DuckDB `read_parquet()` join | WIRED | Line 119: `read_parquet('{games_parquet}')` in DuckDB outer query |
| `src/backtest/scoring.py` | `src/simulator/bracket_schema.py` | `slot_round_number()`, `ROUND_NAMES` | WIRED | Line 30: `from src.simulator.bracket_schema import slot_round_number, ROUND_NAMES` |
| `src/backtest/backtest.py` | `src/backtest/scoring.py` | `build_actual_slot_winners`, `score_bracket`, `compute_game_metrics` | WIRED | Lines 35-39: all three functions imported and called in loop |
| `src/backtest/backtest.py` | `src/simulator/simulate.py` | `simulate_bracket(mode='deterministic')` | WIRED | Line 49 import; line 250-257 call with `mode="deterministic"` |
| `src/backtest/backtest.py` | `src/models/features.py` | `FEATURE_COLS`, `build_matchup_dataset`, `build_stats_lookup`, `compute_features` | WIRED | Lines 40-45: all imported; all called in loop |
| `src/backtest/backtest.py` | `src/models/train_logistic.py` | `ClippedCalibrator`, `CLIP_LO`, `CLIP_HI` | WIRED | Line 47: imported; line 206: `ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)` |
| `src/backtest/backtest.py` | `src/simulator/bracket_schema.py` | `load_seedings()` for per-year seedings | WIRED | Line 48: imported; line 247: `load_seedings(season=test_year)` |
| `src/backtest/backtest.py` | `models/logistic_baseline.joblib` | `joblib.load()` for `best_C` only | WIRED | Lines 149-150: `artifact = joblib.load(model_path)`, `best_C = float(artifact["best_C"])` |
| `src/backtest/validate.py` | `src/backtest/backtest.py` | `backtest()` for C4 reproducibility | WIRED | Line 27: `from src.backtest.backtest import backtest`; called at line 234 |
| `src/backtest/validate.py` | `backtest/results.json` | Load and compare results | WIRED | Lines 51-52: `json.load` from results path |
| `src/backtest/validate.py` | `models/evaluation_results.json` | Cross-reference Phase 3 Brier scores | WIRED | Lines 166-168: loaded and compared per-year Brier with 1e-4 tolerance |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| BACK-01 (backtest model against 2025 tournament) | SATISFIED | 2025 entry in `results.json` with ESPN score 1200/1920 (62.5%); per-round breakdown: R64=68.8%, R32=43.8%, S16=62.5%, E8=100%, FF=100%, CH=0%. `validate.py` asserts 1100 ≤ espn_2025 ≤ 1300. |
| BACK-02 (multi-year holdout 2022–2025) | SATISFIED | All 4 years present with individual scores. Diverse variance: 2022 ESPN=570 (upset-heavy), 2023 ESPN=1070 (chalk leaning), 2024 ESPN=810 (NC State disrupted), 2025 ESPN=1200 (all-chalk FF). |

### Anti-Patterns Found

No stub patterns, TODO/FIXME comments, or placeholder content found across any backtest source files.

| File | Pattern | Finding |
|------|---------|---------|
| `src/backtest/scoring.py` | Stub check | No stubs. 415 lines of real implementation. |
| `src/backtest/backtest.py` | Stub check | No stubs. 454 lines. Loop refits model, calls simulator, computes metrics. |
| `src/backtest/validate.py` | Stub check | No stubs. 298 lines. Hard asserts on all 4 criteria. |

### Structural Notes (Non-Blocking)

Two minor structural deviations from the plan's exact JSON schema were found. Neither affects goal achievement:

1. **`year_range` vs `years_evaluated` key name**: The plan specified the returned dict should contain key `year_range`. The implementation stores it as `years_evaluated`. The function *accepts* `year_range` as a parameter (verified), and the internal storage key name does not affect any downstream consumer. `validate.py` does not reference this key.

2. **Flat summary keys vs nested `summary` dict**: The plan specified a nested `summary: {mean_brier: ..., ...}` dict. The implementation stores summary metrics (`mean_brier`, `mean_log_loss`, `mean_accuracy`, `mean_espn_score`) as flat top-level keys in the results dict. All 4 summary keys exist and carry correct values. `validate.py` C1 criterion checks for required per-year keys only and does not require a `summary` sub-object.

Both deviations were noted in the 05-02 SUMMARY "key-decisions" as intentional choices. Goal achievement is unaffected.

### Human Verification Required

None. All success criteria are verifiable programmatically and have been confirmed against actual file content and `results.json` output.

## Gaps Summary

No gaps found. All 4 observable truths are verified. All required artifacts exist, are substantive (415–454 lines of real implementation), and are wired to their dependencies. All key links are confirmed via import statements and call sites. `backtest/results.json` contains valid, reproducible results matching the Phase 3 benchmark exactly (delta=0.00e+00 per-year Brier).

---

_Verified: 2026-03-04T04:58:58Z_
_Verifier: Claude (gsd-verifier)_
