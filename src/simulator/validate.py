"""
Phase 4 integration test and upset rate calibration check.

Validates all 5 Phase 4 success criteria in a single integration test:
  1. Deterministic bracket fills all 67 slots with teams and win probabilities.
  2. Monte Carlo produces advancement probabilities for all 68 teams.
  3. Upset rate calibration: >= 5% of 10K runs show a 10+ seed in Sweet 16.
  4. Championship score prediction is plausible (total 100-180, winner > loser).
  5. Override map changes downstream results in both modes.

The upset rate check (criterion 3) is a calibration sanity check. If it fails,
a warning is issued but the check does NOT block Phase 4 completion.

Exports:
    check_upset_rate()   -- Compute probability of 10+ seed reaching Sweet 16
    validate_phase4()    -- Run all 5 Phase 4 success criteria checks
"""

from __future__ import annotations

import warnings
from typing import Any

from src.simulator.bracket_schema import (
    build_predict_fn,
    build_team_seed_map,
    load_seedings,
)
from src.simulator.simulate import simulate_bracket

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWEET_16_SLOTS = [
    "R3W1", "R3W2",
    "R3X1", "R3X2",
    "R3Y1", "R3Y2",
    "R3Z1", "R3Z2",
]
MIN_UPSET_RATE = 0.05  # At least 5% of simulations have a 10+ seed in Sweet 16


# ---------------------------------------------------------------------------
# Upset rate check
# ---------------------------------------------------------------------------


def check_upset_rate(
    mc_result: dict[str, Any],
    seedings: dict[str, int],
    team_seed_map: dict[int, int],
) -> float:
    """Compute the Monte Carlo upset rate: P(at least one 10+ seed in Sweet 16).

    Uses the complement formula over per-team Sweet 16 advancement probabilities
    from the Monte Carlo result. For each team with seed >= 10, extracts their
    Sweet 16 probability from advancement_probs and computes:

        P(at least one 10+ seed in Sweet 16)
            = 1 - product(1 - P_sweet16_i) for all 10+ seeds

    This assumes independence across teams (conservative approximation).

    Args:
        mc_result:     Monte Carlo result dict from simulate_bracket(mode='monte_carlo').
                       Must have 'advancement_probs' key.
        seedings:      Dict mapping seed_label -> team_id (from load_seedings()).
        team_seed_map: Dict mapping team_id -> integer seed number (from
                       build_team_seed_map()).

    Returns:
        Float: P(at least one 10+ seed in Sweet 16). In range [0, 1].
        Emits warnings.warn() if result is below MIN_UPSET_RATE.
    """
    advancement_probs = mc_result.get("advancement_probs", {})

    # Product of (1 - P_sweet16) for all teams with seed >= 10
    no_upset_prob = 1.0

    for team_id, round_probs in advancement_probs.items():
        team_id_int = int(team_id)
        seed_num = team_seed_map.get(team_id_int, 0)

        if seed_num >= 10:
            # "Sweet 16" is the round name used in ROUND_NAMES[3]
            p_sweet_16 = round_probs.get("Sweet 16", 0.0)
            no_upset_prob *= (1.0 - p_sweet_16)

    upset_rate = 1.0 - no_upset_prob

    if upset_rate < MIN_UPSET_RATE:
        warnings.warn(
            f"Monte Carlo upset rate is {upset_rate:.1%} "
            f"(expected >= {MIN_UPSET_RATE:.0%}). "
            "Model may be overconfident -- check ClippedCalibrator application.",
            stacklevel=2,
        )

    return float(upset_rate)


# ---------------------------------------------------------------------------
# Phase 4 validation
# ---------------------------------------------------------------------------


def validate_phase4(season: int = 2025) -> None:
    """Run all 5 Phase 4 success criteria checks.

    Loads seedings and builds predict_fn for the specified season, then runs
    deterministic and Monte Carlo simulations to verify that the bracket
    simulator meets all Phase 4 success criteria.

    Success criteria:
        1. Deterministic bracket fills all 67 slots with team_id and win_prob.
        2. Monte Carlo produces champion confidence + advancement probs for 68 teams.
        3. Upset rate calibration: >= 5% upset rate (WARN, not FAIL if below).
        4. Championship score: total 100-180, margin >= 1, winner > loser.
        5. Override map: changes champion in both deterministic and MC modes.

    Args:
        season: Tournament season year. Default: 2025.

    Prints formatted results to stdout. Does not raise on criterion 3 failure
    (upset rate WARN only). Raises AssertionError on criteria 1, 2, 4, 5 failure.
    """
    print()
    print("=" * 50)
    print("PHASE 4 SUCCESS CRITERIA CHECK")
    print(f"Season: {season}")
    print("=" * 50)

    # -------------------------------------------------------------------
    # Load shared setup: seedings, predict_fn, stats_lookup
    # -------------------------------------------------------------------
    print("\nLoading seedings and predict_fn...")
    seedings = load_seedings(season=season)
    predict_fn, stats_lookup = build_predict_fn(season=season)
    team_seed_map = build_team_seed_map(seedings)
    print(f"  Seedings: {len(seedings)} teams loaded")

    passes = 0
    warns = 0

    # ===================================================================
    # CRITERION 1: Deterministic bracket fill
    # ===================================================================
    print("\n--- Criterion 1: Deterministic bracket fill ---")
    det_result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=season,
        stats_lookup=stats_lookup,
    )

    slot_count = len(det_result["slots"])
    champion = det_result["champion"]

    # Assertions
    assert slot_count == 67, (
        f"Expected 67 slots, got {slot_count}"
    )
    assert champion is not None, "Champion not found in deterministic result"
    assert champion.get("team_id") is not None, "Champion team_id is None"
    assert champion.get("win_prob") is not None, "Champion win_prob is None"

    # All slots must have team_id and win_prob
    invalid_slots = [
        sid for sid, sdata in det_result["slots"].items()
        if sdata.get("team_id") is None or sdata.get("win_prob") is None
    ]
    assert not invalid_slots, (
        f"Slots missing team_id or win_prob: {invalid_slots[:5]}"
    )

    champ_id = champion["team_id"]
    champ_prob = champion["win_prob"]
    print(f"  Slots filled: {slot_count}/67")
    print(f"  Champion: team_id={champ_id}, win_prob={champ_prob:.4f}")
    print(f"  [PASS] 1. Deterministic bracket: {slot_count} slots filled, champion identified")
    passes += 1

    # ===================================================================
    # CRITERION 2: Monte Carlo advancement probabilities
    # ===================================================================
    print("\n--- Criterion 2: Monte Carlo advancement probabilities ---")
    mc_result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="monte_carlo",
        n_runs=10000,
        seed=42,
        season=season,
    )

    mc_champion = mc_result["champion"]
    n_runs = mc_result["n_runs"]
    adv_probs = mc_result["advancement_probs"]
    n_teams_with_probs = len(adv_probs)

    assert n_runs == 10000, f"Expected 10000 runs, got {n_runs}"
    assert mc_champion is not None, "MC champion is None"
    assert 0.0 < mc_champion["confidence"] <= 1.0, (
        f"MC champion confidence {mc_champion['confidence']} not in (0, 1]"
    )

    # All 68 teams should have advancement probabilities (they all start in Round of 64)
    # Note: Some teams may not advance at all in some runs, but they should appear
    # with at least Round of 64 probability
    assert n_teams_with_probs == 68, (
        f"Expected 68 teams with advancement probs, got {n_teams_with_probs}"
    )

    mc_champ_conf = mc_champion["confidence"]
    print(f"  n_runs: {n_runs:,}")
    print(f"  Champion: team_id={mc_champion['team_id']}, confidence={mc_champ_conf:.1%}")
    print(f"  Teams with advancement probs: {n_teams_with_probs}")
    print(
        f"  [PASS] 2. Monte Carlo: {n_runs:,} runs, "
        f"champion at {mc_champ_conf:.1%} confidence, "
        f"{n_teams_with_probs} teams with advancement probs"
    )
    passes += 1

    # ===================================================================
    # CRITERION 3: Upset rate calibration
    # ===================================================================
    print("\n--- Criterion 3: Upset rate calibration ---")
    upset_rate = check_upset_rate(mc_result, seedings, team_seed_map)

    if upset_rate >= MIN_UPSET_RATE:
        print(
            f"  [PASS] 3. Upset rate: {upset_rate:.1%} "
            f"(threshold: >= {MIN_UPSET_RATE:.0%})"
        )
        passes += 1
    else:
        print(
            f"  [WARN] 3. Upset rate: {upset_rate:.1%} "
            f"(below threshold {MIN_UPSET_RATE:.0%}) -- "
            "model may be overconfident, but not blocking Phase 4"
        )
        warns += 1

    # ===================================================================
    # CRITERION 4: Championship score prediction
    # ===================================================================
    print("\n--- Criterion 4: Championship score prediction ---")
    champ_game = det_result.get("championship_game")

    assert champ_game is not None, (
        "championship_game key missing from deterministic result. "
        "Did you pass stats_lookup to simulate_bracket()?"
    )

    predicted_total = champ_game["predicted_total"]
    predicted_margin = champ_game["predicted_margin"]
    winner_score = champ_game["winner_score"]
    loser_score = champ_game["loser_score"]

    assert 100 <= predicted_total <= 180, (
        f"predicted_total {predicted_total} not in [100, 180]"
    )
    assert predicted_margin >= 1, (
        f"predicted_margin {predicted_margin} < 1"
    )
    assert winner_score > loser_score, (
        f"winner_score {winner_score} not > loser_score {loser_score}"
    )

    print(f"  predicted_total:  {predicted_total}")
    print(f"  predicted_margin: {predicted_margin}")
    print(f"  winner_score:     {winner_score}")
    print(f"  loser_score:      {loser_score}")
    print(
        f"  [PASS] 4. Championship score: "
        f"Total {predicted_total}, Margin {predicted_margin} "
        f"(Winner {winner_score} - Loser {loser_score})"
    )
    passes += 1

    # ===================================================================
    # CRITERION 5: Override map
    # ===================================================================
    print("\n--- Criterion 5: Override map ---")

    # Find a 16-seed team to force as champion (cinderella scenario)
    sixteen_seed_id = None
    for label, tid in seedings.items():
        if team_seed_map.get(tid) == 16:
            sixteen_seed_id = tid
            break

    assert sixteen_seed_id is not None, (
        "Could not find a 16-seed team in seedings for override test"
    )
    print(f"  Using 16-seed team_id={sixteen_seed_id} for override test")

    # Criterion 5a: Deterministic override
    det_override_result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=season,
        override_map={"R6CH": sixteen_seed_id},
        stats_lookup=stats_lookup,
    )
    det_override_champ = det_override_result["champion"]["team_id"]
    assert det_override_champ == sixteen_seed_id, (
        f"Deterministic override: expected champion={sixteen_seed_id}, "
        f"got {det_override_champ}"
    )

    # Verify slot is marked overridden
    r6ch_slot = det_override_result["slots"]["R6CH"]
    assert r6ch_slot.get("overridden") is True, "R6CH slot should be overridden=True"
    print(f"  Deterministic: champion={det_override_champ} (16-seed), R6CH overridden=True")

    # Criterion 5b: Monte Carlo override
    mc_override_result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="monte_carlo",
        n_runs=1000,
        seed=42,
        season=season,
        override_map={"R6CH": sixteen_seed_id},
    )
    mc_override_champ = mc_override_result["champion"]["team_id"]
    mc_override_conf = mc_override_result["champion"]["confidence"]

    assert mc_override_champ == sixteen_seed_id, (
        f"MC override: expected champion={sixteen_seed_id}, "
        f"got {mc_override_champ}"
    )
    assert mc_override_conf == 1.0, (
        f"MC override: expected confidence=1.0 (all runs forced), "
        f"got {mc_override_conf}"
    )
    print(
        f"  Monte Carlo: champion={mc_override_champ} (16-seed), "
        f"confidence={mc_override_conf:.0%}"
    )
    print(
        f"  [PASS] 5. Override map: "
        f"16-seed forced as champion in both deterministic and Monte Carlo modes"
    )
    passes += 1

    # ===================================================================
    # Final summary
    # ===================================================================
    print()
    print("=" * 50)
    print("PHASE 4 RESULTS")
    print("=" * 50)
    print(f"[PASS] 1. Deterministic bracket: {slot_count} slots filled, champion identified")
    print(
        f"[PASS] 2. Monte Carlo: {n_runs:,} runs, "
        f"champion at {mc_champ_conf:.1%} confidence, "
        f"{n_teams_with_probs} teams with advancement probs"
    )
    if upset_rate >= MIN_UPSET_RATE:
        print(
            f"[PASS] 3. Upset rate: {upset_rate:.1%} "
            f"(threshold: >= {MIN_UPSET_RATE:.0%})"
        )
    else:
        print(
            f"[WARN] 3. Upset rate: {upset_rate:.1%} "
            f"(below threshold {MIN_UPSET_RATE:.0%})"
        )
    print(
        f"[PASS] 4. Championship score: "
        f"Total {predicted_total}, Margin {predicted_margin} "
        f"(Winner {winner_score} - Loser {loser_score})"
    )
    print(
        f"[PASS] 5. Override map: "
        f"16-seed forced as champion in both modes"
    )
    print()

    total_criteria = 5
    if warns > 0:
        print(
            f"Phase 4: {passes}/{total_criteria} criteria PASS "
            f"({warns} WARN -- see criterion 3)"
        )
    else:
        print(f"Phase 4: {passes}/{total_criteria} criteria PASS")
    print("=" * 50)


# ---------------------------------------------------------------------------
# Main block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    validate_phase4(season=2025)
