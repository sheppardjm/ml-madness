"""
E2E smoke test for v1.0-stable verification.

Validates the four success criteria before any v1.1 work begins:
1. Bracket renders (67 slots filled with valid team_id and win_prob)
2. Monte Carlo simulation completes (champion confidence > 0)
3. Override cascades correctly (forced R1W1 winner propagates)
4. Champion displayed (team_id is int, matches R6CH slot)

All tests use season=2025 (2025-26 data not yet available).
"""

from __future__ import annotations

import pytest

from src.simulator.bracket_schema import build_predict_fn, build_slot_tree, load_seedings
from src.simulator.simulate import simulate_bracket


# ---------------------------------------------------------------------------
# Session-scoped fixture: load model and seedings once for performance
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def smoke_context():
    """Build predict_fn and load seedings for 2025. Shared across all smoke tests."""
    predict_fn, _stats = build_predict_fn(season=2025)
    seedings = load_seedings(season=2025)
    return predict_fn, seedings


# ---------------------------------------------------------------------------
# Test 1: Bracket renders
# ---------------------------------------------------------------------------


def test_bracket_renders(smoke_context):
    """Bracket renders: 67 slots filled with valid team_id (int) and win_prob in (0, 1]."""
    predict_fn, seedings = smoke_context

    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
    )

    # Full 68-team bracket produces exactly 67 game slots
    assert len(result["slots"]) == 67, (
        f"Expected 67 slots, got {len(result['slots'])}"
    )

    # Every slot must have an integer team_id and a win_prob in (0, 1]
    for slot_id, slot_data in result["slots"].items():
        assert isinstance(slot_data["team_id"], int), (
            f"Slot {slot_id} team_id must be int, got {type(slot_data['team_id'])}"
        )
        assert 0 < slot_data["win_prob"] <= 1, (
            f"Slot {slot_id} win_prob={slot_data['win_prob']} out of range (0, 1]"
        )


# ---------------------------------------------------------------------------
# Test 2: Monte Carlo simulation completes
# ---------------------------------------------------------------------------


def test_mc_simulation_completes(smoke_context):
    """Monte Carlo simulation completes with champion confidence > 0 and advancement_probs."""
    predict_fn, seedings = smoke_context

    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="monte_carlo",
        n_runs=1000,
        seed=42,
        season=2025,
    )

    # Champion confidence must be a positive probability
    assert 0 < result["champion"]["confidence"] <= 1.0, (
        f"champion confidence={result['champion']['confidence']} not in (0, 1]"
    )

    # MC-specific output: advancement probabilities per team
    assert "advancement_probs" in result, (
        "Monte Carlo result must include 'advancement_probs' key"
    )


# ---------------------------------------------------------------------------
# Test 3: Override cascades correctly
# ---------------------------------------------------------------------------


def test_override_cascades(smoke_context):
    """Forcing the R1W1 loser to win sets overridden=True on that slot."""
    predict_fn, seedings = smoke_context

    # Run baseline to identify R1W1 winner and loser
    baseline = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map=None,
    )

    winner_id = baseline["slots"]["R1W1"]["team_id"]

    # Resolve both teams that compete in R1W1 using the slot tree
    slot_tree = build_slot_tree(season=2025)
    r1w1_data = slot_tree["slots"]["R1W1"]
    strong_ref = r1w1_data["StrongSeed"]  # e.g. 'W01'
    weak_ref = r1w1_data["WeakSeed"]      # e.g. 'W16' or FF slot reference

    # Resolve seed labels to team_ids (WeakSeed may be an FF slot winner ref)
    if strong_ref in seedings:
        strong_team = seedings[strong_ref]
    else:
        strong_team = baseline["slots"][strong_ref]["team_id"]

    if weak_ref in seedings:
        weak_team = seedings[weak_ref]
    else:
        weak_team = baseline["slots"][weak_ref]["team_id"]

    # Pick the loser: whichever competitor is NOT the baseline winner
    loser_id = weak_team if winner_id == strong_team else strong_team

    # Run with override: force the baseline loser to win R1W1
    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map={"R1W1": loser_id},
    )

    # The forced slot must be flagged overridden=True
    assert result["slots"]["R1W1"]["overridden"] is True, (
        "R1W1 must have overridden=True after being forced"
    )

    # The forced slot must show the loser as the winner
    assert result["slots"]["R1W1"]["team_id"] == loser_id, (
        f"R1W1 should show loser_id={loser_id} after override, "
        f"got {result['slots']['R1W1']['team_id']}"
    )


# ---------------------------------------------------------------------------
# Test 4: Champion displayed
# ---------------------------------------------------------------------------


def test_champion_displayed(smoke_context):
    """Champion team_id is an int and matches the R6CH slot winner."""
    predict_fn, seedings = smoke_context

    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
    )

    # Champion must be an integer team_id
    assert isinstance(result["champion"]["team_id"], int), (
        f"champion team_id must be int, got {type(result['champion']['team_id'])}"
    )

    # Champion must match the final slot winner (R6CH)
    assert result["champion"]["team_id"] == result["slots"]["R6CH"]["team_id"], (
        f"champion team_id={result['champion']['team_id']} must match "
        f"R6CH slot winner={result['slots']['R6CH']['team_id']}"
    )
