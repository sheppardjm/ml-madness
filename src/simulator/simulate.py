"""
Bracket simulation module for NCAA tournament.

Provides simulate_bracket() which fills all 67 tournament slots by traversing
the slot tree in topological order and calling predict_fn for each matchup.

Currently supports:
    mode='deterministic'  -- always picks the team with higher win probability
    mode='monte_carlo'    -- not yet implemented (see plan 04-03)

Exports:
    simulate_bracket()    - Main entry point for all simulation modes
"""

from __future__ import annotations

from typing import Any, Callable

from src.simulator.bracket_schema import (
    ROUND_NAMES,
    SLOTS_CSV,
    build_slot_tree,
    build_team_seed_map,
    slot_round_number,
)


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
        mode:         'deterministic' or 'monte_carlo'. Only deterministic is
                      implemented in this plan (04-02).
        n_runs:       Number of Monte Carlo simulation runs. Ignored for
                      deterministic mode.
        seed:         Random seed for Monte Carlo sampling. Ignored for
                      deterministic mode.
        override_map: Dict mapping slot_id -> team_id overrides. Reserved for
                      plan 04-05 (bracket lock-in). Ignored in this plan.
        slots_csv:    Path to MNCAATourneySlots.csv. Defaults to
                      bracket_schema.SLOTS_CSV.
        season:       Tournament season year. Default: 2025.
        stats_lookup: Stats dict for score prediction (consumed by 04-04).
                      Accepted but not used in deterministic simulation.

    Returns:
        Dict with the following structure:
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

        All values are native Python types (int, float, str) for JSON
        serialization. Total of 67 slot entries for post-2010 seasons.

    Raises:
        NotImplementedError: If mode is 'monte_carlo' (implemented in 04-03).
        ValueError:          If mode is unrecognized, or if a team reference
                             cannot be resolved during slot traversal.
    """
    if mode == "monte_carlo":
        raise NotImplementedError(
            "Monte Carlo mode not yet implemented -- see 04-03"
        )
    if mode != "deterministic":
        raise ValueError(
            f"Unknown simulation mode: {mode!r}. "
            "Expected 'deterministic' or 'monte_carlo'."
        )

    return _simulate_deterministic(
        seedings=seedings,
        predict_fn=predict_fn,
        slots_csv=slots_csv or SLOTS_CSV,
        season=season,
    )


def _simulate_deterministic(
    seedings: dict[str, int],
    predict_fn: Callable[[int, int], float],
    slots_csv: str,
    season: int,
) -> dict[str, Any]:
    """Internal deterministic bracket simulation.

    Always picks the team with the higher win probability (>= 0.5 from
    predict_fn). Canonical seed ordering is enforced for every predict_fn
    call.

    Args:
        seedings:  Dict mapping seed_label -> kaggle_team_id.
        predict_fn: Callable(team_a_id, team_b_id) -> float.
                    Caller must ensure team_a has lower seed number.
        slots_csv: Path to MNCAATourneySlots.csv.
        season:    Tournament season year.

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

    return result


# ---------------------------------------------------------------------------
# Main block for smoke testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
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
    from collections import defaultdict
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
    print(f"\n[4] Champion:")
    print(f"  team_id  = {result['champion']['team_id']}")
    print(f"  win_prob = {result['champion']['win_prob']:.4f}")

    # Verification
    print("\n[5] Verification:")
    assert len(result["slots"]) == 67, (
        f"Expected 67 slots, got {len(result['slots'])}"
    )
    print(f"  Slot count: {len(result['slots'])} -- OK")

    assert "R6CH" in result["slots"], "Missing championship slot"
    print("  Championship slot present -- OK")

    assert result["champion"]["team_id"] is not None, "Champion is None"
    print(f"  Champion team_id: {result['champion']['team_id']} -- OK")

    for slot_id, slot_data in result["slots"].items():
        assert 0.0 < slot_data["win_prob"] <= 1.0, (
            f"Slot {slot_id} bad win_prob: {slot_data['win_prob']}"
        )
    print("  All win_probs in (0, 1] -- OK")

    # Test JSON serialization
    import json
    json_str = json.dumps(result)
    assert len(json_str) > 100, "JSON output suspiciously short"
    print(f"  JSON serialization: {len(json_str)} chars -- OK")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
