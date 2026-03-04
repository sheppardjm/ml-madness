"""
Bracket simulation module for NCAA tournament.

Provides simulate_bracket() which fills all 67 tournament slots by traversing
the slot tree in topological order and calling predict_fn for each matchup.

Supports:
    mode='deterministic'  -- always picks the team with higher win probability
    mode='monte_carlo'    -- 10K+ vectorized runs with pre-computed prob matrix

Exports:
    simulate_bracket()    - Main entry point for all simulation modes
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from src.simulator.bracket_schema import (
    ROUND_NAMES,
    SLOTS_CSV,
    build_slot_tree,
    build_team_seed_map,
    slot_round_number,
)
from src.simulator.score_predictor import predict_championship_score


def simulate_bracket(
    seedings: dict[str, int],
    predict_fn: Callable[[int, int], float],
    mode: str = "deterministic",
    n_runs: int = 10000,
    seed: int | None = None,
    override_map: dict[str, int] | None = None,
    slots_csv: str | None = None,
    season: int = 2025,
    stats_lookup: dict | None = None,
) -> dict[str, Any]:
    """Simulate an NCAA tournament bracket.

    Fills all 67 tournament slots by traversing the slot tree in topological
    order (First Four first, then R1 through R6 Championship). For each
    matchup, resolves the two competing teams and calls predict_fn to obtain
    win probabilities.

    Canonical seed ordering is enforced: predict_fn is always called with the
    lower-seed (better-ranked) team as team_a. This matches the training
    convention from Phase 3 where team_a = lower SeedNum.

    Args:
        seedings:     Dict mapping seed_label -> kaggle_team_id.
                      Returned by load_seedings() in bracket_schema.
        predict_fn:   Callable(team_a_id, team_b_id) -> float in (0, 1).
                      team_a_id must have the lower seed number (better seed).
                      Returned by build_predict_fn() in bracket_schema.
        mode:         'deterministic' or 'monte_carlo'.
        n_runs:       Number of Monte Carlo simulation runs. Ignored for
                      deterministic mode.
        seed:         Random seed for Monte Carlo sampling. Ignored for
                      deterministic mode. Same seed produces identical output.
        override_map: Dict mapping slot_id -> team_id overrides. Reserved for
                      plan 04-05 (bracket lock-in). Ignored in this plan.
        slots_csv:    Path to MNCAATourneySlots.csv. Defaults to
                      bracket_schema.SLOTS_CSV.
        season:       Tournament season year. Default: 2025.
        stats_lookup: Stats dict for score prediction (consumed by 04-04).
                      Accepted but not used in deterministic simulation.

    Returns:
        For deterministic mode:
        {
            'mode': 'deterministic',
            'season': 2025,
            'slots': {
                'W16': {'team_id': int, 'win_prob': float, 'round': str},
                'R1W1': {'team_id': int, 'win_prob': float, 'round': str},
                ...
                'R6CH': {'team_id': int, 'win_prob': float, 'round': str},
            },
            'champion': {
                'team_id': int,   -- kaggle_team_id of tournament champion
                'win_prob': float -- championship game win probability
            },
        }

        For monte_carlo mode:
        {
            'mode': 'monte_carlo',
            'season': 2025,
            'n_runs': 10000,
            'champion': {
                'team_id': int,       -- most-frequent champion across all runs
                'confidence': float   -- fraction of runs won by champion
            },
            'advancement_probs': {
                team_id: {
                    'Round of 64': float,   -- fraction of runs team wins R1
                    'Round of 32': float,
                    ...
                    'Championship': float,
                    'Champion': float,      -- fraction of runs team wins R6CH
                },
                ...
            },
        }

        All values are native Python types (int, float, str) for JSON
        serialization. Total of 67 slot entries for post-2010 seasons.

    Raises:
        ValueError: If mode is unrecognized, or if a team reference cannot
                    be resolved during slot traversal.
    """
    if mode == "monte_carlo":
        return _simulate_monte_carlo(
            seedings=seedings,
            predict_fn=predict_fn,
            slots_csv=slots_csv or SLOTS_CSV,
            season=season,
            n_runs=n_runs,
            seed=seed,
        )
    if mode == "deterministic":
        return _simulate_deterministic(
            seedings=seedings,
            predict_fn=predict_fn,
            slots_csv=slots_csv or SLOTS_CSV,
            season=season,
            stats_lookup=stats_lookup,
        )
    raise ValueError(
        f"Unknown simulation mode: {mode!r}. "
        "Expected 'deterministic' or 'monte_carlo'."
    )


# ---------------------------------------------------------------------------
# Monte Carlo helpers
# ---------------------------------------------------------------------------


def _build_prob_matrix(
    teams: list[int],
    team_seed_map: dict[int, int],
    predict_fn: Callable[[int, int], float],
) -> tuple[np.ndarray, dict[int, int], dict[int, int]]:
    """Pre-compute win probability matrix for all team pairs.

    Builds an NxN matrix where prob_matrix[i, j] = P(teams[i] beats teams[j]).
    The matrix is symmetric in the sense that prob_matrix[i, j] + prob_matrix[j, i] = 1.

    Canonical ordering is enforced per pair: the team with the lower seed
    number (better seed) is passed as team_a to predict_fn. For same-seed
    matchups (First Four), team_id is used as a stable tiebreaker.

    Args:
        teams:         List of all unique team IDs in the tournament (68 teams).
        team_seed_map: Dict mapping team_id -> integer seed number.
        predict_fn:    Callable(team_a_id, team_b_id) -> float.

    Returns:
        Tuple of (prob_matrix, team_to_idx, idx_to_team) where:
            prob_matrix: np.ndarray shape (N, N), prob_matrix[i,j] = P(i beats j)
            team_to_idx: dict mapping team_id -> row/col index
            idx_to_team: dict mapping row/col index -> team_id
    """
    n = len(teams)
    team_to_idx: dict[int, int] = {team_id: idx for idx, team_id in enumerate(teams)}
    idx_to_team: dict[int, int] = {idx: team_id for team_id, idx in team_to_idx.items()}

    prob_matrix = np.zeros((n, n), dtype=np.float64)

    for i, team_i in enumerate(teams):
        for j, team_j in enumerate(teams):
            if i == j:
                prob_matrix[i, j] = 0.5  # self-match undefined; use 0.5
                continue

            seed_i = team_seed_map[team_i]
            seed_j = team_seed_map[team_j]

            # Canonical ordering: lower seed_num = team_a for predict_fn
            # Tiebreaker for same-seed matchups (First Four): lower team_id first
            if seed_i < seed_j or (seed_i == seed_j and team_i < team_j):
                # team_i is canonical team_a
                prob_matrix[i, j] = predict_fn(team_i, team_j)
            else:
                # team_j is canonical team_a; flip the probability
                prob_matrix[i, j] = 1.0 - predict_fn(team_j, team_i)

    return prob_matrix, team_to_idx, idx_to_team


def _compute_advancement_probs(
    occupants: dict[str, np.ndarray],
    slot_tree: dict[str, Any],
    idx_to_team: dict[int, int],
    team_seed_map: dict[int, int],
    n_runs: int,
) -> dict[int, dict[str, float]]:
    """Compute per-team advancement probabilities from Monte Carlo runs.

    For each team, counts how often (fraction of n_runs) they appear as
    the winner in each slot across all rounds. Uses ROUND_NAMES for
    human-readable round labels. Adds a 'Champion' key for R6CH winners.

    Args:
        occupants:    Dict mapping slot_id -> np.ndarray of shape (n_runs,)
                      containing team indices for each run.
        slot_tree:    Dict returned by build_slot_tree().
        idx_to_team:  Dict mapping team index -> team_id.
        team_seed_map: Dict mapping team_id -> seed number (for reference).
        n_runs:       Total number of simulation runs.

    Returns:
        Dict mapping team_id (int) -> dict of {round_name: float probability}.
        Only includes rounds where the team advanced at least once.
    """
    # Collect all team IDs
    all_team_ids = list(idx_to_team.values())
    team_to_idx_local = {v: k for k, v in idx_to_team.items()}

    # Initialize result: team_id -> round_name -> count
    adv_counts: dict[int, dict[str, int]] = {
        team_id: {} for team_id in all_team_ids
    }

    for slot_id in slot_tree["order"]:
        if slot_id not in occupants:
            continue

        slot_occ = occupants[slot_id]  # shape (n_runs,) of team indices
        round_num = slot_round_number(slot_id)
        round_name = ROUND_NAMES.get(round_num, f"Round {round_num}")

        # Count how many runs each team index appears in this slot
        counts = np.bincount(slot_occ, minlength=len(idx_to_team))
        for idx, cnt in enumerate(counts):
            if cnt > 0:
                team_id = idx_to_team[idx]
                adv_counts[team_id][round_name] = (
                    adv_counts[team_id].get(round_name, 0) + int(cnt)
                )

    # R6CH winners also get "Champion" entry
    if "R6CH" in occupants:
        champ_occ = occupants["R6CH"]
        counts = np.bincount(champ_occ, minlength=len(idx_to_team))
        for idx, cnt in enumerate(counts):
            if cnt > 0:
                team_id = idx_to_team[idx]
                adv_counts[team_id]["Champion"] = int(cnt)

    # Convert counts to probabilities; only include teams that advanced
    adv_probs: dict[int, dict[str, float]] = {}
    for team_id, round_counts in adv_counts.items():
        if round_counts:
            adv_probs[team_id] = {
                round_name: round_cnt / n_runs
                for round_name, round_cnt in round_counts.items()
            }

    return adv_probs


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------


def _simulate_monte_carlo(
    seedings: dict[str, int],
    predict_fn: Callable[[int, int], float],
    slots_csv: str,
    season: int,
    n_runs: int,
    seed: int | None,
) -> dict[str, Any]:
    """Internal Monte Carlo bracket simulation.

    Pre-computes a 68x68 win probability matrix (4,624 predict_fn calls),
    then runs n_runs simulations simultaneously using vectorized numpy
    Bernoulli draws. Returns per-team advancement probabilities and champion
    confidence.

    Args:
        seedings:   Dict mapping seed_label -> kaggle_team_id.
        predict_fn: Callable(team_a_id, team_b_id) -> float.
        slots_csv:  Path to MNCAATourneySlots.csv.
        season:     Tournament season year.
        n_runs:     Number of Monte Carlo runs.
        seed:       Random seed for reproducibility. None = non-deterministic.

    Returns:
        Monte Carlo result dict (see simulate_bracket docstring).
    """
    # Step 1: Build slot tree and team-seed map
    slot_tree = build_slot_tree(season, slots_csv)
    team_seed_map = build_team_seed_map(seedings)

    # Step 2: Get unique list of all teams (stable order for reproducibility)
    teams: list[int] = sorted(set(seedings.values()))

    # Step 3: Pre-compute 68x68 probability matrix (4,624 predict_fn calls)
    prob_matrix, team_to_idx, idx_to_team = _build_prob_matrix(
        teams, team_seed_map, predict_fn
    )

    # Step 4: Initialize RNG with seed for reproducibility
    rng = np.random.default_rng(seed)

    # Step 5: Initialize occupant arrays
    # occupants[slot_id] = np.ndarray shape (n_runs,) of team indices
    occupants: dict[str, np.ndarray] = {}

    # Seed-label slots: initialize directly from seedings
    # Each seedings entry (e.g., 'W01' -> team_id) provides a starting occupant
    for seed_label, team_id in seedings.items():
        team_idx = team_to_idx[team_id]
        occupants[seed_label] = np.full(n_runs, team_idx, dtype=np.int32)

    # Step 6: Traverse slots in topological order with vectorized Bernoulli draws
    for slot_id in slot_tree["order"]:
        slot_data = slot_tree["slots"][slot_id]
        strong_ref = slot_data["StrongSeed"]
        weak_ref = slot_data["WeakSeed"]

        # Resolve strong and weak seed references to occupant arrays
        if strong_ref not in occupants:
            raise ValueError(
                f"Cannot resolve StrongSeed reference {strong_ref!r} "
                f"for slot {slot_id!r}. "
                "Check that all prerequisite slots have been processed."
            )
        if weak_ref not in occupants:
            raise ValueError(
                f"Cannot resolve WeakSeed reference {weak_ref!r} "
                f"for slot {slot_id!r}. "
                "Check that all prerequisite slots have been processed."
            )

        strong_occ = occupants[strong_ref]  # shape (n_runs,) team indices
        weak_occ = occupants[weak_ref]      # shape (n_runs,) team indices

        # Look up win probability for each run's matchup
        # prob_matrix[strong_occ, weak_occ] = P(strong beats weak) per run
        probs = prob_matrix[strong_occ, weak_occ]  # shape (n_runs,)

        # Vectorized Bernoulli draw: draw < prob means strong seed wins
        draws = rng.random(n_runs)
        occupants[slot_id] = np.where(draws < probs, strong_occ, weak_occ).astype(
            np.int32
        )

    # Step 7: Determine champion (most frequent R6CH occupant)
    champ_occ = occupants["R6CH"]  # shape (n_runs,)
    champ_counts = np.bincount(champ_occ, minlength=len(teams))
    champ_idx = int(np.argmax(champ_counts))
    champ_team_id = int(idx_to_team[champ_idx])
    champ_confidence = float(champ_counts[champ_idx]) / n_runs

    # Step 8: Compute per-team advancement probabilities
    adv_probs = _compute_advancement_probs(
        occupants=occupants,
        slot_tree=slot_tree,
        idx_to_team=idx_to_team,
        team_seed_map=team_seed_map,
        n_runs=n_runs,
    )

    # Step 9: Convert all numpy types to native Python for JSON serialization
    # adv_probs already converted in _compute_advancement_probs
    adv_probs_native: dict[int, dict[str, float]] = {
        int(team_id): {rname: float(prob) for rname, prob in rprobs.items()}
        for team_id, rprobs in adv_probs.items()
    }

    return {
        "mode": "monte_carlo",
        "season": int(season),
        "n_runs": int(n_runs),
        "champion": {
            "team_id": champ_team_id,
            "confidence": champ_confidence,
        },
        "advancement_probs": adv_probs_native,
    }


# ---------------------------------------------------------------------------
# Deterministic simulation
# ---------------------------------------------------------------------------


def _simulate_deterministic(
    seedings: dict[str, int],
    predict_fn: Callable[[int, int], float],
    slots_csv: str,
    season: int,
    stats_lookup: dict | None = None,
) -> dict[str, Any]:
    """Internal deterministic bracket simulation.

    Always picks the team with the higher win probability (>= 0.5 from
    predict_fn). Canonical seed ordering is enforced for every predict_fn
    call.

    Args:
        seedings:     Dict mapping seed_label -> kaggle_team_id.
        predict_fn:   Callable(team_a_id, team_b_id) -> float.
                      Caller must ensure team_a has lower seed number.
        slots_csv:    Path to MNCAATourneySlots.csv.
        season:       Tournament season year.
        stats_lookup: Optional stats dict from build_stats_lookup(). If provided,
                      the championship_game key is populated with a predicted score.
                      If None, championship_game is set to None.

    Returns:
        Simulation result dict (see simulate_bracket docstring).
    """
    # Step 1: Build slot tree (67 slots in topological order)
    slot_tree = build_slot_tree(season, slots_csv)

    # Step 2: Build team-seed map for canonical ordering
    team_seed_map = build_team_seed_map(seedings)

    # Step 3: Track winners and win probabilities per slot
    slot_winner: dict[str, int] = {}   # slot_id -> kaggle_team_id of winner
    slot_prob: dict[str, float] = {}   # slot_id -> win probability of winner

    # Step 4: Traverse slots in topological order
    for slot_id in slot_tree["order"]:
        slot_data = slot_tree["slots"][slot_id]
        strong_ref = slot_data["StrongSeed"]
        weak_ref = slot_data["WeakSeed"]

        # Resolve StrongSeed reference to team ID
        if strong_ref in seedings:
            # Direct seed label reference (e.g., 'W01', 'X16a')
            team_a = seedings[strong_ref]
        elif strong_ref in slot_winner:
            # Prior slot reference (e.g., 'R1W1' -> winner of round 1 W region slot 1)
            team_a = slot_winner[strong_ref]
        else:
            raise ValueError(
                f"Cannot resolve StrongSeed reference {strong_ref!r} "
                f"for slot {slot_id!r}. "
                "Check that all prerequisite slots have been processed."
            )

        # Resolve WeakSeed reference to team ID
        if weak_ref in seedings:
            team_b = seedings[weak_ref]
        elif weak_ref in slot_winner:
            team_b = slot_winner[weak_ref]
        else:
            raise ValueError(
                f"Cannot resolve WeakSeed reference {weak_ref!r} "
                f"for slot {slot_id!r}. "
                "Check that all prerequisite slots have been processed."
            )

        if team_a is None:
            raise ValueError(
                f"Slot {slot_id!r}: StrongSeed {strong_ref!r} resolved to None."
            )
        if team_b is None:
            raise ValueError(
                f"Slot {slot_id!r}: WeakSeed {weak_ref!r} resolved to None."
            )

        # Step 4c: Enforce canonical seed ordering for predict_fn call
        # predict_fn must receive the lower-seed (better-ranked) team as team_a
        seed_a = team_seed_map[team_a]
        seed_b = team_seed_map[team_b]

        if seed_a <= seed_b:
            # team_a (StrongSeed) already has the lower seed number — correct order
            prob_a_wins = predict_fn(team_a, team_b)
        else:
            # team_b (WeakSeed) has the lower seed number — must swap for predict_fn
            prob_a_wins = 1.0 - predict_fn(team_b, team_a)

        # Step 4d: Pick winner deterministically (higher win probability wins)
        if prob_a_wins >= 0.5:
            slot_winner[slot_id] = team_a
            slot_prob[slot_id] = prob_a_wins
        else:
            slot_winner[slot_id] = team_b
            slot_prob[slot_id] = 1.0 - prob_a_wins

    # Step 5: Build output dict with all native Python types
    result: dict[str, Any] = {
        "mode": "deterministic",
        "season": season,
        "slots": {},
        "champion": {
            "team_id": int(slot_winner["R6CH"]),
            "win_prob": float(slot_prob["R6CH"]),
        },
    }

    for slot_id in slot_tree["order"]:
        round_num = slot_round_number(slot_id)
        result["slots"][slot_id] = {
            "team_id": int(slot_winner[slot_id]),
            "win_prob": float(slot_prob[slot_id]),
            "round": ROUND_NAMES.get(round_num, f"Round {round_num}"),
        }

    # Step 6: Add championship game predicted score if stats_lookup is provided.
    # The two finalists come from R5WX and R5YZ; the champion is R6CH winner.
    if stats_lookup is not None:
        finalist_wx = slot_winner["R5WX"]  # winner of Final Four game WX
        finalist_yz = slot_winner["R5YZ"]  # winner of Final Four game YZ
        champion_id = slot_winner["R6CH"]
        champion_prob = slot_prob["R6CH"]

        # Determine winner/loser ordering for score prediction
        if champion_id == finalist_wx:
            winner_id = finalist_wx
            loser_id = finalist_yz
        else:
            winner_id = finalist_yz
            loser_id = finalist_wx

        result["championship_game"] = predict_championship_score(
            team_a_id=winner_id,
            team_b_id=loser_id,
            win_prob_a=champion_prob,
            stats_lookup=stats_lookup,
            season=season,
        )
    else:
        # No stats_lookup provided: graceful degradation
        print(
            "Note: championship_game score prediction requires stats_lookup. "
            "Pass stats_lookup=stats to simulate_bracket() to enable score prediction."
        )
        result["championship_game"] = None

    return result


# ---------------------------------------------------------------------------
# Main block for smoke testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time
    from collections import defaultdict

    from src.simulator.bracket_schema import build_predict_fn, load_seedings

    print("=" * 60)
    print("simulate.py smoke test")
    print("=" * 60)

    # Load seedings and build predict_fn
    print("\n[1] Loading seedings and predict_fn for 2025...")
    seedings = load_seedings(season=2025)
    predict_fn, stats = build_predict_fn(season=2025)
    print(f"  Seedings loaded: {len(seedings)}")
    print(f"  predict_fn ready: {callable(predict_fn)}")

    # Run deterministic simulation
    print("\n[2] Running deterministic simulation...")
    result = simulate_bracket(seedings, predict_fn, mode="deterministic", season=2025)

    # Print bracket by round
    print("\n[3] Bracket results by round:")
    by_round: dict[str, list] = defaultdict(list)
    for slot_id, slot_data in result["slots"].items():
        by_round[slot_data["round"]].append((slot_id, slot_data))

    round_order = [
        "First Four",
        "Round of 64",
        "Round of 32",
        "Sweet 16",
        "Elite 8",
        "Final Four",
        "Championship",
    ]
    for round_name in round_order:
        slots_in_round = by_round.get(round_name, [])
        if slots_in_round:
            print(f"\n  {round_name} ({len(slots_in_round)} games):")
            for slot_id, slot_data in sorted(slots_in_round):
                print(
                    f"    {slot_id:8s}  team={slot_data['team_id']:5d}  "
                    f"P={slot_data['win_prob']:.4f}"
                )

    # Print champion
    print(f"\n[4] Deterministic Champion:")
    print(f"  team_id  = {result['champion']['team_id']}")
    print(f"  win_prob = {result['champion']['win_prob']:.4f}")

    # Run Monte Carlo simulation
    print("\n[5] Running Monte Carlo simulation (n_runs=10000, seed=42)...")
    mc_start = time.time()
    mc_result = simulate_bracket(
        seedings, predict_fn, mode="monte_carlo", n_runs=10000, seed=42, season=2025
    )
    mc_elapsed = time.time() - mc_start

    print(f"  Elapsed: {mc_elapsed:.3f}s")
    champ = mc_result["champion"]
    print(f"\n[6] Monte Carlo Champion:")
    print(f"  team_id    = {champ['team_id']}")
    print(f"  confidence = {champ['confidence']:.1%}")

    # Print top contenders (teams with highest Final Four advancement prob)
    print("\n[7] Top 10 contenders by Champion probability:")
    adv = mc_result["advancement_probs"]
    champ_probs = [
        (team_id, probs.get("Champion", 0.0))
        for team_id, probs in adv.items()
        if probs.get("Champion", 0.0) > 0
    ]
    champ_probs.sort(key=lambda x: x[1], reverse=True)
    for rank, (team_id, prob) in enumerate(champ_probs[:10], 1):
        print(f"  {rank:2d}. team={team_id:5d}  Champion={prob:.2%}")

    # Verification
    print("\n[8] Verification:")
    assert len(result["slots"]) == 67, (
        f"Expected 67 slots, got {len(result['slots'])}"
    )
    print(f"  Deterministic slot count: {len(result['slots'])} -- OK")

    assert mc_result["mode"] == "monte_carlo", "Wrong mode"
    assert mc_result["n_runs"] == 10000, "Wrong n_runs"
    assert 0.0 < mc_result["champion"]["confidence"] <= 1.0, "Bad confidence"
    print(f"  Monte Carlo mode, n_runs, confidence -- OK")

    # Test JSON serialization of MC result
    import json
    json_str = json.dumps(mc_result)
    assert len(json_str) > 100, "JSON output suspiciously short"
    print(f"  JSON serialization: {len(json_str)} chars -- OK")

    print(f"\n  Total MC elapsed: {mc_elapsed:.3f}s")
    assert mc_elapsed < 30.0, f"Monte Carlo too slow: {mc_elapsed:.3f}s"
    print("  Performance: OK")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
