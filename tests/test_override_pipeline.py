"""
Override pipeline tests for NCAA tournament bracket simulator.

Verifies that override_map cascades correctly through downstream rounds,
does not affect unrelated bracket regions, and that empty override equals
no override. Also verifies that Monte Carlo advancement probabilities
respond correctly to forced winners.

All tests use the 2025 season. Tests 1-6 use deterministic mode (fast,
~0.01s each). Test 7 uses monte_carlo mode with n_runs=1000 (~0.02s).

Imports:
    - simulate_bracket() from src.simulator.simulate
    - build_predict_fn(), load_seedings(), build_slot_tree() from src.simulator.bracket_schema
"""

from __future__ import annotations

import pytest

from src.simulator.bracket_schema import (
    build_predict_fn,
    build_slot_tree,
    build_team_seed_map,
    load_seedings,
)
from src.simulator.simulate import simulate_bracket


# ---------------------------------------------------------------------------
# Session-scoped fixture: load model and seedings once for performance
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sim_context():
    """Build predict_fn and load seedings for 2025. Session-scoped for performance.

    Returns:
        Tuple of (predict_fn, seedings) where:
            predict_fn(team_a_id, team_b_id) -> float
            seedings: dict mapping seed_label -> team_id
    """
    predict_fn, _stats = build_predict_fn(season=2025)
    seedings = load_seedings(season=2025)
    return predict_fn, seedings


@pytest.fixture(scope="session")
def r1w1_context(sim_context):
    """Compute R1W1 baseline winner, loser (underdog), and slot tree.

    This fixture runs the baseline deterministic simulation once and resolves
    both teams that compete in R1W1 (using the slot tree for StrongSeed/WeakSeed
    references). Returns everything needed by R1W1-based tests.

    Returns:
        Dict with keys:
            baseline: full deterministic simulation result (no overrides)
            winner_id: team_id that wins R1W1 in baseline
            loser_id: team_id that LOSES R1W1 in baseline (the "underdog")
    """
    predict_fn, seedings = sim_context

    # Run baseline simulation
    baseline = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map=None,
    )

    # Resolve who competed in R1W1 using the slot tree
    slot_tree = build_slot_tree(season=2025)
    r1w1_data = slot_tree["slots"]["R1W1"]
    strong_ref = r1w1_data["StrongSeed"]  # e.g. 'W01'
    weak_ref = r1w1_data["WeakSeed"]      # e.g. 'W16' or 'W16a'/'W16b'

    # Resolve seed labels to team_ids
    # After First Four, the weak_ref might be an FF slot winner reference.
    # For R1W1 the StrongSeed is always a direct seed label (e.g. 'W01').
    # The WeakSeed may be a seed label or a FF slot ID.
    if strong_ref in seedings:
        strong_team = seedings[strong_ref]
    else:
        # It's an FF slot winner — look it up in baseline slots
        strong_team = baseline["slots"][strong_ref]["team_id"]

    if weak_ref in seedings:
        weak_team = seedings[weak_ref]
    else:
        # It's an FF slot winner — look it up in baseline slots
        weak_team = baseline["slots"][weak_ref]["team_id"]

    winner_id = baseline["slots"]["R1W1"]["team_id"]

    # The loser is whichever of the two competing teams is NOT the winner
    if winner_id == strong_team:
        loser_id = weak_team
    else:
        loser_id = strong_team

    return {
        "baseline": baseline,
        "winner_id": winner_id,
        "loser_id": loser_id,
    }


# ---------------------------------------------------------------------------
# Test 1: Baseline sanity check
# ---------------------------------------------------------------------------


def test_no_override_baseline(sim_context):
    """Baseline simulation: all 67 slots have team_id and win_prob, no overrides set."""
    predict_fn, seedings = sim_context

    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map=None,
    )

    assert result["mode"] == "deterministic"
    assert result["season"] == 2025
    assert "slots" in result
    assert "champion" in result

    # All 67 slots should be present
    assert len(result["slots"]) == 67, (
        f"Expected 67 slots, got {len(result['slots'])}"
    )

    # Every slot must have team_id, win_prob, and overridden=False
    for slot_id, slot_data in result["slots"].items():
        assert "team_id" in slot_data, f"Slot {slot_id} missing team_id"
        assert "win_prob" in slot_data, f"Slot {slot_id} missing win_prob"
        assert isinstance(slot_data["team_id"], int), (
            f"Slot {slot_id} team_id must be int"
        )
        assert 0.0 < slot_data["win_prob"] <= 1.0, (
            f"Slot {slot_id} win_prob={slot_data['win_prob']} out of range"
        )
        assert slot_data.get("overridden") is False, (
            f"Slot {slot_id} should have overridden=False in baseline"
        )

    # Champion must be a valid team_id appearing in some slot
    champ_id = result["champion"]["team_id"]
    assert isinstance(champ_id, int), "champion team_id must be int"
    assert result["champion"]["team_id"] == result["slots"]["R6CH"]["team_id"], (
        "champion team_id must match R6CH slot winner"
    )


# ---------------------------------------------------------------------------
# Test 2: Override cascades downstream
# ---------------------------------------------------------------------------


def test_r1_override_cascades_downstream(sim_context, r1w1_context):
    """Forcing the R1W1 loser to win changes R2W1 and further downstream slots."""
    predict_fn, seedings = sim_context
    baseline = r1w1_context["baseline"]
    loser_id = r1w1_context["loser_id"]

    # Run with override: force the baseline loser to win R1W1
    overridden = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map={"R1W1": loser_id},
    )

    # R1W1 must now report the loser_id as winner
    assert overridden["slots"]["R1W1"]["team_id"] == loser_id, (
        f"R1W1 should show loser_id={loser_id} after override, "
        f"got {overridden['slots']['R1W1']['team_id']}"
    )

    # R1W1 must be flagged as overridden
    assert overridden["slots"]["R1W1"]["overridden"] is True, (
        "R1W1 must have overridden=True after being forced"
    )

    # R2W1 feeds from R1W1 — its winner must differ from baseline because
    # one of its feeders (R1W1) now has a different team
    baseline_r2w1_winner = baseline["slots"]["R2W1"]["team_id"]
    overridden_r2w1_winner = overridden["slots"]["R2W1"]["team_id"]
    assert baseline_r2w1_winner != overridden_r2w1_winner, (
        f"R2W1 winner should change when R1W1 is overridden. "
        f"Baseline={baseline_r2w1_winner}, Override={overridden_r2w1_winner}"
    )
    assert overridden["slots"]["R2W1"].get("overridden") is False, (
        "R2W1 is NOT directly overridden; it just received a different input"
    )

    # The cascade must propagate at least to R3W1 or higher (R4W1, R5WX, R6CH)
    cascade_slots = ["R3W1", "R4W1", "R5WX", "R6CH"]
    cascade_changed = any(
        overridden["slots"][s]["team_id"] != baseline["slots"][s]["team_id"]
        for s in cascade_slots
        if s in overridden["slots"] and s in baseline["slots"]
    )
    assert cascade_changed, (
        "Override should cascade: at least one of R3W1/R4W1/R5WX/R6CH should differ "
        "from baseline after forcing R1W1 to an upset winner"
    )


# ---------------------------------------------------------------------------
# Test 3: Override does not affect other regions
# ---------------------------------------------------------------------------


def test_override_does_not_affect_other_regions(sim_context, r1w1_context):
    """Overriding R1W1 (West region) must not change X, Y, or Z region slots."""
    predict_fn, seedings = sim_context
    baseline = r1w1_context["baseline"]
    loser_id = r1w1_context["loser_id"]

    overridden = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map={"R1W1": loser_id},
    )

    # All R1X, R1Y, R1Z slots must be identical to baseline
    other_r1_slots = [
        s for s in overridden["slots"]
        if s.startswith("R1") and not s.startswith("R1W")
    ]
    assert len(other_r1_slots) > 0, "Must have non-W R1 slots to check"

    for slot_id in other_r1_slots:
        assert overridden["slots"][slot_id]["team_id"] == baseline["slots"][slot_id]["team_id"], (
            f"Slot {slot_id} (other region) changed unexpectedly: "
            f"baseline={baseline['slots'][slot_id]['team_id']}, "
            f"override={overridden['slots'][slot_id]['team_id']}"
        )
        assert overridden["slots"][slot_id]["overridden"] is False, (
            f"Slot {slot_id} should not be flagged overridden"
        )

    # Regional final and Elite 8 slots in other regions must be unchanged
    for slot_id in ["R4X1", "R4Y1", "R4Z1"]:
        if slot_id in overridden["slots"] and slot_id in baseline["slots"]:
            assert (
                overridden["slots"][slot_id]["team_id"]
                == baseline["slots"][slot_id]["team_id"]
            ), (
                f"{slot_id} (other region) should be unchanged by West R1W1 override"
            )


# ---------------------------------------------------------------------------
# Test 4: Empty override equals no override
# ---------------------------------------------------------------------------


def test_empty_override_equals_no_override(sim_context):
    """override_map={} and override_map=None must produce identical results."""
    predict_fn, seedings = sim_context

    result_none = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map=None,
    )
    result_empty = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map={},
    )

    # Champion must be the same
    assert result_none["champion"]["team_id"] == result_empty["champion"]["team_id"], (
        "Champion should be identical for override_map=None vs {}"
    )

    # All slot winners must match
    for slot_id in result_none["slots"]:
        assert (
            result_none["slots"][slot_id]["team_id"]
            == result_empty["slots"][slot_id]["team_id"]
        ), (
            f"Slot {slot_id} winner differs between None and empty override_map"
        )


# ---------------------------------------------------------------------------
# Test 5: Overridden flag is set correctly
# ---------------------------------------------------------------------------


def test_override_marks_slot_overridden(sim_context, r1w1_context):
    """The overridden=True flag is set only on the explicitly forced slot."""
    predict_fn, seedings = sim_context
    loser_id = r1w1_context["loser_id"]

    result = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="deterministic",
        season=2025,
        override_map={"R1W1": loser_id},
    )

    # R1W1 must be marked overridden=True
    assert result["slots"]["R1W1"]["overridden"] is True, (
        "R1W1 must be marked overridden=True after being forced"
    )

    # R1W2 is in the same round but NOT overridden — must remain False
    assert result["slots"]["R1W2"]["overridden"] is False, (
        "R1W2 is not in override_map; must have overridden=False"
    )

    # Count how many slots are flagged overridden — should be exactly 1
    overridden_count = sum(
        1 for s in result["slots"].values() if s.get("overridden") is True
    )
    assert overridden_count == 1, (
        f"Expected exactly 1 overridden slot, found {overridden_count}"
    )


# ---------------------------------------------------------------------------
# Test 6: Monte Carlo advancement probs change with override
# ---------------------------------------------------------------------------


def test_mc_override_changes_advancement_probs(sim_context, r1w1_context):
    """Forcing the R1W1 underdog raises its Round of 32 advancement prob to 1.0."""
    predict_fn, seedings = sim_context
    loser_id = r1w1_context["loser_id"]   # the underdog forced to win R1W1

    N_RUNS = 1000
    SEED = 42

    # Baseline MC (no overrides)
    mc_baseline = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="monte_carlo",
        n_runs=N_RUNS,
        seed=SEED,
        season=2025,
        override_map=None,
    )

    # Override MC: force underdog to win R1W1
    mc_override = simulate_bracket(
        seedings=seedings,
        predict_fn=predict_fn,
        mode="monte_carlo",
        n_runs=N_RUNS,
        seed=SEED,
        season=2025,
        override_map={"R1W1": loser_id},
    )

    adv_baseline = mc_baseline["advancement_probs"]
    adv_override = mc_override["advancement_probs"]

    # ROUND_NAMES[1] = "Round of 64" (winning a first-round game).
    # Winning R1W1 gives credit for "Round of 64" advancement.
    # The underdog is forced to win R1W1 in every run, so probability must be 1.0.
    r64_prob_override = adv_override.get(loser_id, {}).get("Round of 64", 0.0)
    assert r64_prob_override == 1.0, (
        f"Underdog (team {loser_id}) Round of 64 probability should be 1.0 "
        f"when forced to win R1W1, got {r64_prob_override:.4f}"
    )

    # The underdog's Round of 64 prob must be higher in override than baseline
    # (baseline underdog rarely or never wins R1W1 in MC).
    r64_prob_baseline = adv_baseline.get(loser_id, {}).get("Round of 64", 0.0)
    assert r64_prob_override > r64_prob_baseline, (
        f"Underdog Round of 64 prob should increase with override: "
        f"baseline={r64_prob_baseline:.4f}, override={r64_prob_override:.4f}"
    )

    # The overridden underdog's further advancement (Round of 32 = winning R2W1)
    # should also be nonzero (they at least have a chance now that they're in R2).
    r32_prob_override = adv_override.get(loser_id, {}).get("Round of 32", 0.0)
    r32_prob_baseline = adv_baseline.get(loser_id, {}).get("Round of 32", 0.0)
    assert r32_prob_override >= r32_prob_baseline, (
        f"Underdog Round of 32 prob should be >= baseline with override: "
        f"baseline={r32_prob_baseline:.4f}, override={r32_prob_override:.4f}"
    )

    # Champion confidence may differ (not guaranteed to change, but MC results differ)
    # Just assert both results have valid confidence values
    assert 0.0 < mc_baseline["champion"]["confidence"] <= 1.0
    assert 0.0 < mc_override["champion"]["confidence"] <= 1.0
