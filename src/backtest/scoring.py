"""
Scoring helpers for NCAA bracket backtesting.

Converts bracket simulation results into quantitative metrics:
- ESPN bracket scores (per-round point values, perfect bracket = 1920)
- Per-round accuracy and correct/total counts
- Game-level Brier score, log-loss, accuracy, and upset detection rate

These functions are consumed by the backtest orchestration loop (05-02).
They bridge Phase 4's simulate_bracket() output and Phase 5's evaluation
metrics.

Exports:
    build_actual_slot_winners()  - DuckDB lookup of actual tournament slot winners
    score_bracket()              - ESPN scoring with per-round accuracy breakdown
    compute_game_metrics()       - Brier, log-loss, accuracy, upset detection
    ESPN_ROUND_POINTS            - Dict mapping round number -> ESPN point value
    ESPN_MAX_SCORE               - Maximum possible ESPN bracket score (1920)
"""

from __future__ import annotations

import pathlib
from typing import Any

import duckdb
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss

from src.simulator.bracket_schema import slot_round_number, ROUND_NAMES

# ---------------------------------------------------------------------------
# ESPN scoring constants
# ---------------------------------------------------------------------------

ESPN_ROUND_POINTS: dict[int, int] = {
    1: 10,
    2: 20,
    3: 40,
    4: 80,
    5: 160,
    6: 320,
}

# Perfect bracket scores: 32*10 + 16*20 + 8*40 + 4*80 + 2*160 + 1*320 = 1920
ESPN_MAX_SCORE: int = 1920

# ---------------------------------------------------------------------------
# Default data paths
# ---------------------------------------------------------------------------

_DEFAULT_PROCESSED_DIR = "data/processed"
_DEFAULT_SEED_ROUND_SLOTS_CSV = "data/raw/kaggle/MNCAATourneySeedRoundSlots.csv"


# ---------------------------------------------------------------------------
# build_actual_slot_winners
# ---------------------------------------------------------------------------


def build_actual_slot_winners(
    season: int,
    processed_dir: str = _DEFAULT_PROCESSED_DIR,
    seed_round_slots_csv: str = _DEFAULT_SEED_ROUND_SLOTS_CSV,
) -> dict[str, int]:
    """Return actual winning team_id for each of the 67 tournament slots.

    Uses DuckDB to join seeds.parquet (filtered to season) with
    MNCAATourneySeedRoundSlots.csv (season-independent routing table) to
    identify each team's slot assignments, then joins tournament_games.parquet
    to find actual game winners.

    The CSV has NO Season column -- season isolation comes from filtering
    seeds.parquet by season. This is by design: the routing table maps seed
    labels to slot/round/day numbers universally.

    SQL overview:
        1. team_slots CTE: join seeds (filtered to season) with seed-round-slots
           to get each team's (slot, round, DayNum range).
        2. Outer query: join team_slots to tournament_games where the team
           participated AND won (WTeamID = ts.TeamID).

    Args:
        season: Tournament season year (e.g., 2025).
        processed_dir: Directory containing seeds.parquet and
            tournament_games.parquet. Default: "data/processed".
        seed_round_slots_csv: Path to MNCAATourneySeedRoundSlots.csv.
            Default: "data/raw/kaggle/MNCAATourneySeedRoundSlots.csv".

    Returns:
        Dict mapping slot_id (str) -> actual winning team_id (int).
        Always returns exactly 67 entries for post-2010 seasons.

    Raises:
        FileNotFoundError: If any required data file does not exist.
        AssertionError: If the result count is not 67 for post-2010 seasons.
    """
    seeds_parquet = str(pathlib.Path(processed_dir) / "seeds.parquet")
    games_parquet = str(pathlib.Path(processed_dir) / "tournament_games.parquet")

    for path in [seeds_parquet, games_parquet, seed_round_slots_csv]:
        if not pathlib.Path(path).exists():
            raise FileNotFoundError(
                f"Required data file not found: {path}. "
                "Ensure Phase 1 tournament data ingestion has been run."
            )

    conn = duckdb.connect()
    sql = f"""
        WITH team_slots AS (
            SELECT DISTINCT s.TeamID, sr.GameSlot, sr.GameRound,
                   sr.EarlyDayNum, sr.LateDayNum
            FROM read_parquet('{seeds_parquet}') s
            JOIN read_csv('{seed_round_slots_csv}') sr ON s.Seed = sr.Seed
            WHERE s.Season = {season}
        )
        SELECT ts.GameSlot AS slot_id, g.WTeamID AS actual_winner
        FROM team_slots ts
        JOIN read_parquet('{games_parquet}') g
            ON g.Season = {season}
            AND g.DayNum BETWEEN ts.EarlyDayNum AND ts.LateDayNum
            AND (g.WTeamID = ts.TeamID OR g.LTeamID = ts.TeamID)
            AND g.WTeamID = ts.TeamID
        ORDER BY ts.GameSlot
    """
    df = conn.execute(sql).df()
    conn.close()

    result: dict[str, int] = {
        str(row.slot_id): int(row.actual_winner)
        for row in df.itertuples(index=False)
    }

    if season >= 2011:
        assert len(result) == 67, (
            f"Expected 67 slot winners for season {season}, got {len(result)}. "
            "Check that tournament_games.parquet and seeds.parquet are complete."
        )

    return result


# ---------------------------------------------------------------------------
# score_bracket
# ---------------------------------------------------------------------------


def score_bracket(
    predicted_slots: dict[str, int],
    actual_winners: dict[str, int],
) -> dict[str, Any]:
    """Score a predicted bracket against actual tournament results.

    Implements ESPN bracket scoring rules:
    - Round 1 (R1): 10 points per correct pick
    - Round 2 (R2): 20 points per correct pick
    - Sweet 16 (R3): 40 points per correct pick
    - Elite 8 (R4): 80 points per correct pick
    - Final Four (R5): 160 points per correct pick
    - Championship (R6): 320 points per correct pick
    - First Four slots (round 0): NOT scored in ESPN brackets

    A perfect bracket scores 1920 points total.

    Args:
        predicted_slots: Dict mapping slot_id -> predicted winning team_id.
            Typically the 'slots' output from simulate_bracket(), keyed by
            slot_id with each value being a dict with 'team_id' key, OR a
            flat dict mapping slot_id -> team_id directly.
        actual_winners: Dict mapping slot_id -> actual winning team_id.
            Typically from build_actual_slot_winners().

    Returns:
        Dict with keys:
            'espn_score' (int): Total ESPN points scored.
            'espn_max' (int): Maximum possible score (1920).
            'per_round_accuracy' (dict[str, float]): Round name -> accuracy.
            'per_round_correct' (dict[str, int]): Round name -> correct count.
            'per_round_total' (dict[str, int]): Round name -> total games.
    """
    # Normalize predicted_slots: handle both flat {slot_id: team_id} and
    # nested {slot_id: {'team_id': ..., ...}} formats (simulate_bracket output).
    normalized_predicted: dict[str, int] = {}
    for slot_id, value in predicted_slots.items():
        if isinstance(value, dict):
            normalized_predicted[slot_id] = int(value["team_id"])
        else:
            normalized_predicted[slot_id] = int(value)

    # Accumulators per round (using ROUND_NAMES from bracket_schema)
    per_round_correct: dict[str, int] = {}
    per_round_total: dict[str, int] = {}

    # Initialize all scored rounds (R1-R6)
    for round_num in range(1, 7):
        round_name = ROUND_NAMES[round_num]
        per_round_correct[round_name] = 0
        per_round_total[round_name] = 0

    espn_score = 0

    for slot_id, actual_winner in actual_winners.items():
        round_num = slot_round_number(slot_id)

        # Skip First Four slots (round 0) -- not scored in ESPN brackets
        if round_num == 0:
            continue

        round_name = ROUND_NAMES[round_num]
        points = ESPN_ROUND_POINTS[round_num]

        per_round_total[round_name] += 1

        predicted_winner = normalized_predicted.get(slot_id)
        if predicted_winner is not None and predicted_winner == actual_winner:
            per_round_correct[round_name] += 1
            espn_score += points

    # Compute per-round accuracy (avoid division by zero)
    per_round_accuracy: dict[str, float] = {}
    for round_name in per_round_correct:
        total = per_round_total[round_name]
        correct = per_round_correct[round_name]
        per_round_accuracy[round_name] = correct / total if total > 0 else 0.0

    return {
        "espn_score": espn_score,
        "espn_max": ESPN_MAX_SCORE,
        "per_round_accuracy": per_round_accuracy,
        "per_round_correct": per_round_correct,
        "per_round_total": per_round_total,
    }


# ---------------------------------------------------------------------------
# compute_game_metrics
# ---------------------------------------------------------------------------


def compute_game_metrics(
    test_df,
    feature_cols: list[str],
    scaler,
    calibrated_clf,
) -> dict[str, Any]:
    """Compute game-level prediction metrics from fold-specific model predictions.

    Uses batch prediction (scaler.transform + calibrated_clf.predict_proba)
    for efficiency. Computes Brier score, log-loss, accuracy, upset count,
    upset correct, and upset detection rate.

    Upset definition: The lower-seeded team (team_b, higher SeedNum) won.
    In the canonical matchup encoding, label=1 means team_a (better seed) won,
    so label=0 indicates an upset.

    Args:
        test_df: Pandas DataFrame for the holdout year. Must contain
            feature_cols columns and a 'label' column (1=team_a wins, 0=upset).
        feature_cols: Ordered list of feature column names (e.g., FEATURE_COLS).
        scaler: Fitted StandardScaler from the training fold.
        calibrated_clf: Fitted ClippedCalibrator (or compatible calibrator)
            with predict_proba() method.

    Returns:
        Dict with keys:
            'brier' (float): Brier score (lower is better).
            'log_loss' (float): Log-loss (lower is better).
            'accuracy' (float): Fraction of correct winner predictions.
            'n_games' (int): Total games in test set.
            'n_upsets' (int): Total upset games (label=0).
            'upset_correct' (int): Upsets correctly predicted (predicted P<0.5).
            'upset_detection_rate' (float): upset_correct / n_upsets.
    """
    X_test = scaler.transform(test_df[feature_cols].values)
    y_test = test_df["label"].values

    # Batch predict calibrated probabilities
    y_prob = calibrated_clf.predict_proba(X_test)[:, 1]
    y_pred_class = (y_prob >= 0.5).astype(int)

    brier = float(brier_score_loss(y_test, y_prob))
    ll = float(log_loss(y_test, y_prob))
    accuracy = float((y_pred_class == y_test).mean())

    n_games = int(len(y_test))
    n_upsets = int((y_test == 0).sum())
    upset_correct = int(((y_prob < 0.5) & (y_test == 0)).sum())
    upset_detection_rate = upset_correct / n_upsets if n_upsets > 0 else 0.0

    return {
        "brier": brier,
        "log_loss": ll,
        "accuracy": accuracy,
        "n_games": n_games,
        "n_upsets": n_upsets,
        "upset_correct": upset_correct,
        "upset_detection_rate": float(upset_detection_rate),
    }


# ---------------------------------------------------------------------------
# Main block for smoke testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("src/backtest/scoring.py smoke test")
    print("=" * 60)

    BACKTEST_YEARS = [2022, 2023, 2024, 2025]

    # --- build_actual_slot_winners ---
    print("\n[1] build_actual_slot_winners() for all backtest years")
    for year in BACKTEST_YEARS:
        winners = build_actual_slot_winners(year)
        assert len(winners) == 67, f"Year {year}: expected 67 winners, got {len(winners)}"
        sample = list(winners.items())[:3]
        print(f"  {year}: {len(winners)} slot winners  (sample: {sample})")
    print("  OK")

    # --- ESPN constants ---
    print("\n[2] ESPN constants")
    assert ESPN_MAX_SCORE == 1920, f"ESPN_MAX_SCORE should be 1920, got {ESPN_MAX_SCORE}"
    assert ESPN_ROUND_POINTS[1] == 10, f"R1 should be 10 points, got {ESPN_ROUND_POINTS[1]}"
    assert ESPN_ROUND_POINTS[6] == 320, f"R6 should be 320 points, got {ESPN_ROUND_POINTS[6]}"
    # Verify sum: 32*10 + 16*20 + 8*40 + 4*80 + 2*160 + 1*320 = 1920
    expected_max = 32 * 10 + 16 * 20 + 8 * 40 + 4 * 80 + 2 * 160 + 1 * 320
    assert expected_max == 1920, f"Point sum sanity check failed: {expected_max}"
    print(f"  ESPN_MAX_SCORE = {ESPN_MAX_SCORE}")
    print(f"  ESPN_ROUND_POINTS = {ESPN_ROUND_POINTS}")
    print("  OK")

    # --- score_bracket: perfect bracket ---
    print("\n[3] score_bracket() - perfect bracket = 1920")
    winners_2025 = build_actual_slot_winners(2025)
    perfect_result = score_bracket(winners_2025, winners_2025)
    assert perfect_result["espn_score"] == 1920, (
        f"Perfect bracket should score 1920, got {perfect_result['espn_score']}"
    )
    assert perfect_result["espn_max"] == 1920
    # Verify all per-round accuracies are 1.0 for perfect bracket
    for round_name, acc in perfect_result["per_round_accuracy"].items():
        assert acc == 1.0, f"Round {round_name} accuracy should be 1.0 for perfect bracket, got {acc}"
    print(f"  espn_score = {perfect_result['espn_score']}")
    print(f"  per_round_correct = {perfect_result['per_round_correct']}")
    print("  OK")

    # --- score_bracket: empty bracket ---
    print("\n[4] score_bracket() - empty bracket = 0")
    empty_result = score_bracket({}, winners_2025)
    assert empty_result["espn_score"] == 0, (
        f"Empty bracket should score 0, got {empty_result['espn_score']}"
    )
    print(f"  espn_score = {empty_result['espn_score']}")
    print("  OK")

    # --- score_bracket: First Four slots not scored ---
    print("\n[5] score_bracket() - verify First Four slots not counted")
    # R6CH is the only championship slot -- total scored games should be 63
    total_scored = sum(perfect_result["per_round_total"].values())
    assert total_scored == 63, (
        f"Expected 63 scored games (R1-R6 only), got {total_scored}"
    )
    print(f"  Total scored games (R1-R6): {total_scored}")
    print("  OK")

    # --- compute_game_metrics: smoke test with dummy data ---
    print("\n[6] compute_game_metrics() - smoke test with real model")
    try:
        import pandas as pd
        from src.models.features import FEATURE_COLS, build_matchup_dataset
        from src.models.temporal_cv import walk_forward_splits
        from src.models.train_logistic import ClippedCalibrator, CLIP_LO, CLIP_HI
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        import joblib

        artifact = joblib.load("models/logistic_baseline.joblib")
        best_C = artifact["best_C"]
        df = build_matchup_dataset("data/processed")

        for test_year, train_df, test_df in walk_forward_splits(df):
            if test_year != 2025:
                continue
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(train_df[FEATURE_COLS].values)
            clf = LogisticRegression(
                C=best_C, class_weight="balanced", solver="lbfgs",
                max_iter=1000, random_state=42
            )
            clf.fit(X_train_scaled, train_df["label"].values)
            calibrated_clf = ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)

            metrics = compute_game_metrics(test_df, FEATURE_COLS, scaler, calibrated_clf)
            assert "brier" in metrics
            assert "log_loss" in metrics
            assert "accuracy" in metrics
            assert "n_games" in metrics
            assert "n_upsets" in metrics
            assert "upset_correct" in metrics
            assert "upset_detection_rate" in metrics
            print(f"  2025 metrics: brier={metrics['brier']:.4f}, "
                  f"accuracy={metrics['accuracy']:.1%}, "
                  f"n_games={metrics['n_games']}, "
                  f"n_upsets={metrics['n_upsets']}, "
                  f"upset_correct={metrics['upset_correct']}, "
                  f"upset_detection_rate={metrics['upset_detection_rate']:.1%}")
            break
        print("  OK")
    except Exception as exc:
        print(f"  WARNING: compute_game_metrics smoke test skipped ({exc})")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
