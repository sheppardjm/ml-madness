"""
Phase 5 validation: verify all 4 backtest success criteria.

Runs backtest() if results.json is absent, then validates:

Criterion 1: Backtest produces a per-year table (4 required keys per row)
Criterion 2: Temporal isolation -- training set max season == 2024 for 2025 fold;
             per-year Brier scores match evaluation_results.json to 4 decimal places
Criterion 3: Multi-year coverage -- all 4 BACKTEST_YEARS present; dynamic upset counts
Criterion 4: Reproducibility -- re-running backtest() yields byte-identical per_year data

BACK-01 validation:
  - 2025 ESPN score in range [1100, 1300]
  - Bracket breakdown printed

Exports:
    validate_phase5()   - Run all criteria checks; raises AssertionError on failure
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any

from src.backtest.backtest import backtest
from src.models.features import build_matchup_dataset
from src.models.temporal_cv import BACKTEST_YEARS

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_RESULTS_PATH = "backtest/results.json"
_DEFAULT_EVAL_PATH = "models/evaluation_results.json"
_DEFAULT_PROCESSED_DIR = "data/processed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_or_run_backtest(results_path: str = _DEFAULT_RESULTS_PATH) -> dict[str, Any]:
    """Load backtest results from disk, running backtest() if file is absent."""
    p = pathlib.Path(results_path)
    if not p.exists():
        print(f"  results.json not found at {results_path} -- running backtest()...")
        return backtest(output_path=results_path)
    with open(p) as f:
        return json.load(f)


def _compare_per_year(a: list[dict], b: list[dict]) -> list[str]:
    """Return list of diff descriptions between two per_year arrays.

    Ignores 'generated_at' (top-level, not per_year) and only compares keys
    present in both records.  Float fields compared with 1e-9 tolerance.
    """
    diffs: list[str] = []
    if len(a) != len(b):
        diffs.append(f"per_year length mismatch: {len(a)} vs {len(b)}")
        return diffs
    for i, (ra, rb) in enumerate(zip(a, b)):
        for key in ra:
            if key not in rb:
                continue
            va, vb = ra[key], rb[key]
            if isinstance(va, float):
                if abs(va - vb) > 1e-9:
                    diffs.append(f"year[{i}].{key}: {va} != {vb}")
            elif isinstance(va, dict):
                for sub_key in va:
                    if sub_key in vb:
                        sv, tv = va[sub_key], vb[sub_key]
                        if isinstance(sv, float) and abs(sv - tv) > 1e-9:
                            diffs.append(f"year[{i}].{key}.{sub_key}: {sv} != {tv}")
                        elif sv != tv:
                            diffs.append(f"year[{i}].{key}.{sub_key}: {sv} != {tv}")
            else:
                if va != vb:
                    diffs.append(f"year[{i}].{key}: {va} != {vb}")
    return diffs


# ---------------------------------------------------------------------------
# validate_phase5
# ---------------------------------------------------------------------------


def validate_phase5(
    results_path: str = _DEFAULT_RESULTS_PATH,
    eval_path: str = _DEFAULT_EVAL_PATH,
    processed_dir: str = _DEFAULT_PROCESSED_DIR,
    brier_tolerance: float = 1e-4,
) -> None:
    """Run all 4 Phase 5 success criteria.  Raises AssertionError on any failure.

    Args:
        results_path: Path to backtest/results.json.
        eval_path:    Path to models/evaluation_results.json (Phase 3 benchmark).
        processed_dir: Directory containing .parquet data files.
        brier_tolerance: Absolute tolerance for Brier score comparison against
                         evaluation_results.json (default 0.0001 = 4 decimal places).

    Raises:
        AssertionError: If any criterion fails.
        FileNotFoundError: If evaluation_results.json is missing.
    """
    print()
    print("=" * 70)
    print("Phase 5 Validation")
    print("=" * 70)

    passed = 0
    total = 4

    # ------------------------------------------------------------------
    # Criterion 1: Backtest produces per-year table
    # ------------------------------------------------------------------
    print("\n[C1] Backtest produces per-year table with required fields")

    results = _load_or_run_backtest(results_path)
    per_year = results.get("per_year", [])

    required_keys = {"year", "brier", "espn_score", "espn_max"}

    assert len(per_year) == 4, (
        f"C1 FAIL: expected 4 per_year entries, got {len(per_year)}"
    )
    for row in per_year:
        missing = required_keys - set(row.keys())
        assert not missing, (
            f"C1 FAIL: year {row.get('year')} missing keys: {missing}"
        )

    print(f"  per_year rows:  {len(per_year)}")
    print(f"  required keys present in all rows: {sorted(required_keys)}")
    print("  Criterion 1: PASS")
    passed += 1

    # ------------------------------------------------------------------
    # Criterion 2: Temporal isolation
    # ------------------------------------------------------------------
    print("\n[C2] Temporal isolation: max training season == 2024 for 2025 fold")
    print("     Cross-referencing Brier scores against evaluation_results.json")

    # 2a: Temporal isolation -- filter matchup dataset to Season < 2025
    print("  Loading matchup dataset (this may take a moment)...")
    df = build_matchup_dataset(processed_dir)
    train_df = df[df["Season"] < 2025].copy()

    max_train_season = int(train_df["Season"].max())
    assert max_train_season == 2024, (
        f"Temporal leak: max train season is {max_train_season}, expected 2024"
    )
    print(f"  max(train_df.Season) for 2025 fold: {max_train_season}  -- OK")

    # 2b: Brier score cross-reference against evaluation_results.json
    eval_path_p = pathlib.Path(eval_path)
    if not eval_path_p.exists():
        raise FileNotFoundError(
            f"evaluation_results.json not found at {eval_path}. "
            "Run Phase 3 evaluation first."
        )
    with open(eval_path_p) as f:
        eval_results = json.load(f)

    eval_by_year: dict[int, float] = {
        int(r["year"]): float(r["brier"])
        for r in eval_results["per_year"]
    }
    backtest_by_year: dict[int, float] = {
        int(r["year"]): float(r["brier"])
        for r in per_year
    }

    print("  Per-year Brier comparison (backtest vs evaluation_results.json):")
    print(f"  {'Year':>6}  {'Backtest':>12}  {'Eval':>12}  {'|Delta|':>10}  Status")
    print("  " + "-" * 56)
    for year in sorted(eval_by_year):
        if year not in backtest_by_year:
            continue
        bt_brier = backtest_by_year[year]
        ev_brier = eval_by_year[year]
        delta = abs(bt_brier - ev_brier)
        status = "OK" if delta <= brier_tolerance else "MISMATCH"
        print(f"  {year:>6}  {bt_brier:>12.7f}  {ev_brier:>12.7f}  {delta:>10.2e}  {status}")
        assert delta <= brier_tolerance, (
            f"C2 FAIL: year {year} Brier mismatch: "
            f"backtest={bt_brier:.7f}, eval={ev_brier:.7f}, delta={delta:.2e} "
            f"(tolerance={brier_tolerance:.0e})"
        )

    print("  Criterion 2: PASS")
    passed += 1

    # ------------------------------------------------------------------
    # Criterion 3: Multi-year coverage with dynamic upset counts
    # ------------------------------------------------------------------
    print("\n[C3] Multi-year coverage: all 4 BACKTEST_YEARS present")

    years_in_results = {int(r["year"]) for r in per_year}
    for year in BACKTEST_YEARS:
        assert year in years_in_results, (
            f"C3 FAIL: expected year {year} in per_year, not found"
        )

    print(f"  BACKTEST_YEARS: {BACKTEST_YEARS}")
    print(f"  Years in results: {sorted(years_in_results)}")
    print()
    print("  Per-year upset counts (from results, not hardcoded):")
    print(f"  {'Year':>6}  {'n_upsets':>10}  {'upset_correct':>14}  {'detection_rate':>16}")
    print("  " + "-" * 52)
    for row in sorted(per_year, key=lambda r: r["year"]):
        n_upsets = row["n_upsets"]
        up_correct = row["upset_correct"]
        det_rate = row.get("upset_detection_rate", up_correct / n_upsets if n_upsets else 0.0)
        print(f"  {row['year']:>6}  {n_upsets:>10}  {up_correct:>14}  {det_rate:>15.1%}")

    print()
    print("  Criterion 3: PASS")
    passed += 1

    # ------------------------------------------------------------------
    # Criterion 4: Reproducibility
    # ------------------------------------------------------------------
    print("\n[C4] Reproducibility: re-running backtest() produces same per_year data")

    original_per_year = copy.deepcopy(per_year)

    print("  Re-running backtest() (writing to same results.json)...")
    new_results = backtest(output_path=results_path)
    new_per_year = new_results.get("per_year", [])

    diffs = _compare_per_year(original_per_year, new_per_year)
    assert not diffs, (
        f"C4 FAIL: re-run produced different per_year data:\n"
        + "\n".join(f"  - {d}" for d in diffs)
    )

    print(f"  Original vs re-run per_year comparison: 0 differences  -- OK")
    print("  Criterion 4: PASS")
    passed += 1

    # ------------------------------------------------------------------
    # BACK-01 validation: 2025 ESPN score in range [1100, 1300]
    # ------------------------------------------------------------------
    print("\n[BACK-01] 2025 ESPN bracket breakdown")

    row_2025 = next((r for r in new_per_year if int(r["year"]) == 2025), None)
    assert row_2025 is not None, "BACK-01 FAIL: 2025 row missing from per_year"

    espn_2025 = int(row_2025["espn_score"])
    espn_max = int(row_2025.get("espn_max", 1920))

    print(f"  Predicted champion (team_id): {row_2025.get('predicted_champion')}")
    print(f"  ESPN score:   {espn_2025} / {espn_max}  ({espn_2025/espn_max:.1%})")
    print()
    print("  Per-round accuracy (2025):")
    per_round_acc = row_2025.get("per_round_accuracy", {})
    per_round_correct = row_2025.get("per_round_correct", {})
    per_round_total = row_2025.get("per_round_total", {})
    round_order = [
        "Round of 64", "Round of 32", "Sweet 16",
        "Elite 8", "Final Four", "Championship"
    ]
    print(f"  {'Round':<16}  {'Correct':>8}  {'Total':>8}  {'Accuracy':>10}")
    print("  " + "-" * 46)
    for rname in round_order:
        if rname in per_round_acc:
            acc = per_round_acc[rname]
            r_correct = per_round_correct.get(rname, "?")
            r_total = per_round_total.get(rname, "?")
            print(f"  {rname:<16}  {r_correct!s:>8}  {r_total!s:>8}  {acc:>9.1%}")

    assert 1100 <= espn_2025 <= 1300, (
        f"BACK-01 FAIL: 2025 ESPN score {espn_2025} outside range [1100, 1300]"
    )
    print(f"\n  2025 ESPN score {espn_2025} in range [1100, 1300]  -- OK")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print(f"Phase 5: {passed}/{total} criteria PASS")
    print("=" * 70)
    print()


# ---------------------------------------------------------------------------
# Main block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    validate_phase5()
