"""
Championship game score predictor for NCAA tournament simulation.

Provides a rule-based method to predict the final score of the championship
game using adjusted tempo and win probability. The formula is derived from
historical championship game analysis (2003-2025, excluding 2020).

R^2 for a full regression model on championship totals is only ~0.25, so the
added complexity of a second ML model is not justified. The rule-based approach
using adj_t is sufficient for the bracket prediction use case.

Exports:
    predict_championship_score() -- Rule-based score prediction for any matchup
"""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Constants (from historical championship game analysis 2003-2025 excl. 2020)
# ---------------------------------------------------------------------------

HISTORICAL_MEAN_TOTAL: float = 140.0   # mean total points in championship games
HISTORICAL_MEAN_TEMPO: float = 67.0    # fallback adj_t when team data unavailable
TEMPO_COEF: float = 3.43              # linear coefficient for avg_adj_t -> total
TEMPO_INTERCEPT: float = -89.7        # intercept for tempo -> total formula
TOTAL_MIN: int = 100                  # floor for predicted total
TOTAL_MAX: int = 180                  # ceiling for predicted total

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score prediction
# ---------------------------------------------------------------------------


def predict_championship_score(
    team_a_id: int,
    team_b_id: int,
    win_prob_a: float,
    stats_lookup: dict,
    season: int = 2025,
) -> dict:
    """Predict the final score of the championship game.

    Uses adjusted tempo (adj_t) from the stats_lookup to estimate total points,
    and the championship win probability to estimate the margin. Designed for
    the deterministic simulation output in plan 04-04.

    Tempo formula derived from historical championship games (2003-2025 excl. 2020):
        predicted_total = TEMPO_COEF * avg_adj_t + TEMPO_INTERCEPT

    Margin formula:
        predicted_margin = round((win_prob_a - 0.5) * 20 + 8)

    This scales naturally:
        win_prob 0.50 -> margin  8 (coin flip)
        win_prob 0.75 -> margin 13
        win_prob 0.89 -> margin 16 (near-certain favorite, ClippedCalibrator max)

    Args:
        team_a_id:    Kaggle team ID of the predicted winner (higher win probability).
        team_b_id:    Kaggle team ID of the predicted loser.
        win_prob_a:   Probability that team_a wins the championship (float in (0, 1)).
        stats_lookup: Dict keyed by (season, kaggle_team_id) from build_stats_lookup().
                      Expected to have 'adj_t' key per team entry.
        season:       Tournament year. Default: 2025.

    Returns:
        Dict with keys:
            predicted_total  (int): Estimated total points in the game.
            predicted_margin (int): Estimated winning margin (>= 1).
            winner_score     (int): Estimated score for the winner.
            loser_score      (int): Estimated score for the loser.
            winner_team_id   (int): Kaggle team ID of the predicted winner (= team_a_id).
            loser_team_id    (int): Kaggle team ID of the predicted loser (= team_b_id).
    """
    # Step 1: Look up adj_t for both teams; fall back to historical mean if missing.
    key_a = (season, int(team_a_id))
    key_b = (season, int(team_b_id))

    if key_a in stats_lookup and stats_lookup[key_a].get("adj_t") is not None:
        adj_t_a = float(stats_lookup[key_a]["adj_t"])
        # adj_t can be 0.0 as a sentinel for missing data (see features.py)
        if adj_t_a == 0.0:
            logger.warning(
                "adj_t is 0.0 (sentinel for missing) for team %d (season %d); "
                "falling back to historical mean tempo %.1f",
                team_a_id, season, HISTORICAL_MEAN_TEMPO,
            )
            adj_t_a = HISTORICAL_MEAN_TEMPO
    else:
        logger.warning(
            "Team %d not found in stats_lookup for season %d; "
            "falling back to historical mean tempo %.1f",
            team_a_id, season, HISTORICAL_MEAN_TEMPO,
        )
        adj_t_a = HISTORICAL_MEAN_TEMPO

    if key_b in stats_lookup and stats_lookup[key_b].get("adj_t") is not None:
        adj_t_b = float(stats_lookup[key_b]["adj_t"])
        if adj_t_b == 0.0:
            logger.warning(
                "adj_t is 0.0 (sentinel for missing) for team %d (season %d); "
                "falling back to historical mean tempo %.1f",
                team_b_id, season, HISTORICAL_MEAN_TEMPO,
            )
            adj_t_b = HISTORICAL_MEAN_TEMPO
    else:
        logger.warning(
            "Team %d not found in stats_lookup for season %d; "
            "falling back to historical mean tempo %.1f",
            team_b_id, season, HISTORICAL_MEAN_TEMPO,
        )
        adj_t_b = HISTORICAL_MEAN_TEMPO

    # Step 2: Compute average tempo of the two finalists.
    avg_tempo = (adj_t_a + adj_t_b) / 2.0

    # Step 3: Predict total points using linear tempo formula.
    predicted_total = round(TEMPO_COEF * avg_tempo + TEMPO_INTERCEPT)

    # Step 4: Clamp total to plausible range.
    predicted_total = max(TOTAL_MIN, min(TOTAL_MAX, predicted_total))

    # Step 5: Predict margin from win probability.
    #   win_prob=0.50 -> margin 8 (baseline margin for evenly matched teams)
    #   win_prob=0.75 -> margin 13
    #   win_prob=0.89 -> margin ~16 (near-certain favorite)
    predicted_margin = round((win_prob_a - 0.5) * 20 + 8)

    # Clamp margin: must be at least 1 (winner wins by at least 1 point),
    # and must be less than the total (can't have a margin >= total score).
    predicted_margin = max(1, predicted_margin)
    predicted_margin = min(predicted_margin, predicted_total - 1)

    # Step 6: Compute individual team scores from total and margin.
    #   winner_score + loser_score = predicted_total
    #   winner_score - loser_score = predicted_margin
    #   => winner_score = (total + margin) / 2
    winner_score = (predicted_total + predicted_margin) // 2
    loser_score = predicted_total - winner_score

    # Guard against rounding errors making winner_score <= loser_score.
    if winner_score <= loser_score:
        winner_score = loser_score + 1

    return {
        "predicted_total": int(predicted_total),
        "predicted_margin": int(predicted_margin),
        "winner_score": int(winner_score),
        "loser_score": int(loser_score),
        "winner_team_id": int(team_a_id),
        "loser_team_id": int(team_b_id),
    }


# ---------------------------------------------------------------------------
# Main block for smoke testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    from src.simulator.bracket_schema import build_predict_fn, load_seedings, build_team_seed_map

    print("=" * 60)
    print("score_predictor.py smoke test")
    print("=" * 60)

    # Load seedings and build stats_lookup
    print("\n[1] Loading seedings and stats_lookup for 2025...")
    seedings = load_seedings(season=2025)
    predict_fn, stats = build_predict_fn(season=2025)
    print(f"  Seedings loaded: {len(seedings)}")
    print(f"  Stats lookup entries: {len(stats)}")

    # Pick a 1-seed and 2-seed for the test
    tsm = build_team_seed_map(seedings)
    team_1 = None
    team_2 = None
    for label, tid in seedings.items():
        if tsm[tid] == 1 and team_1 is None and not label.endswith(("a", "b")):
            team_1 = tid
        if tsm[tid] == 2 and team_2 is None and not label.endswith(("a", "b")):
            team_2 = tid
        if team_1 and team_2:
            break

    print(f"\n[2] Predicting championship score: team {team_1} vs team {team_2}")
    win_prob = 0.65
    score = predict_championship_score(team_1, team_2, win_prob, stats, season=2025)
    print(f"  win_prob_a = {win_prob}")
    print(f"  predicted_total  = {score['predicted_total']}")
    print(f"  predicted_margin = {score['predicted_margin']}")
    print(f"  winner_score     = {score['winner_score']} (team {score['winner_team_id']})")
    print(f"  loser_score      = {score['loser_score']} (team {score['loser_team_id']})")

    # Verification
    print("\n[3] Verification:")
    assert 100 <= score["predicted_total"] <= 180, (
        f"Total {score['predicted_total']} outside [100, 180]"
    )
    print(f"  Total in [100, 180]: {score['predicted_total']} -- OK")

    assert score["predicted_margin"] >= 1, (
        f"Margin {score['predicted_margin']} < 1"
    )
    print(f"  Margin >= 1: {score['predicted_margin']} -- OK")

    assert score["winner_score"] > score["loser_score"], (
        f"Winner {score['winner_score']} not > loser {score['loser_score']}"
    )
    print(f"  Winner > Loser: {score['winner_score']} > {score['loser_score']} -- OK")

    # Test fallback with missing team
    print("\n[4] Testing fallback with missing team ID (99999)...")
    score_fallback = predict_championship_score(99999, team_2, 0.60, stats, season=2025)
    print(f"  Score with fallback: {score_fallback}")
    assert 100 <= score_fallback["predicted_total"] <= 180, "Fallback score out of range"
    print("  Fallback: OK")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
