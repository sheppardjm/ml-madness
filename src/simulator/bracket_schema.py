"""
Bracket schema module for NCAA tournament simulation.

Loads the 67-slot tournament tree from Kaggle CSV data, provides seedings
loading, topological slot ordering, and a predict_fn builder that wraps the
Phase 3 trained model.

Purpose: Every other plan in Phase 4 depends on the slot tree structure,
seedings dict, and predict_fn callable. This foundational module defines
the data structures and interfaces that simulate.py and score_predictor.py
consume.

Exports:
    build_slot_tree()       - Load 67-slot tournament tree in topological order
    load_seedings()         - Load 68 seed-label -> team_id mappings for a season
    get_topological_order() - Return ordered slot list from slot tree
    build_predict_fn()      - Build predict_fn closure wrapping the Phase 3 model
    build_team_seed_map()   - Map team_id -> integer seed number
    slot_round_number()     - Return round number (0=FF, 1-6=R1-R6) for a slot
    ROUND_NAMES             - Dict mapping round number -> display name
"""

from __future__ import annotations

import pathlib
from typing import Any

import duckdb

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

SLOTS_CSV = "data/raw/kaggle/MNCAATourneySlots.csv"
SEEDS_PARQUET = "data/processed/seeds.parquet"

# ---------------------------------------------------------------------------
# Round name mapping
# ---------------------------------------------------------------------------

ROUND_NAMES: dict[int, str] = {
    0: "First Four",
    1: "Round of 64",
    2: "Round of 32",
    3: "Sweet 16",
    4: "Elite 8",
    5: "Final Four",
    6: "Championship",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def slot_round_number(slot_id: str) -> int:
    """Return the round number for a slot.

    First Four slots (not starting with 'R') get round 0.
    R1-R6 slots get rounds 1-6 respectively.

    Args:
        slot_id: Slot identifier string (e.g., 'R1W1', 'R6CH', 'W16').

    Returns:
        Integer round number: 0 for First Four, 1-6 for R1-R6.
    """
    if not slot_id.startswith("R"):
        return 0
    # slot_id[1] is the round digit: '1' through '6'
    return int(slot_id[1])


# ---------------------------------------------------------------------------
# Slot tree
# ---------------------------------------------------------------------------


def build_slot_tree(
    season: int = 2025,
    slots_csv: str = SLOTS_CSV,
) -> dict[str, Any]:
    """Load the 67-slot tournament tree from Kaggle's MNCAATourneySlots.csv.

    Returns a dict with:
        'slots'    - dict mapping slot_id -> {'StrongSeed': str, 'WeakSeed': str}
        'order'    - list of slot IDs in topological order (FF first, then R1->R6)
        'ff_slots' - set of First Four slot IDs (slots not starting with 'R')

    Topological ordering ensures that every slot's StrongSeed and WeakSeed
    references are resolved before the slot itself is processed during
    simulation. FF slots (round 0) come first, then R1 through R6.

    Args:
        season: Tournament season year. Default: 2025.
        slots_csv: Path to MNCAATourneySlots.csv. Default: SLOTS_CSV.

    Returns:
        Dict with 'slots', 'order', and 'ff_slots' keys.

    Raises:
        AssertionError: If the number of slots is not 67 for post-2010 seasons.
    """
    slots_path = pathlib.Path(slots_csv)
    if not slots_path.exists():
        raise FileNotFoundError(
            f"Slots CSV not found at {slots_csv}. "
            "Ensure Kaggle data is present at data/raw/kaggle/."
        )

    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT Slot, StrongSeed, WeakSeed "
        f"FROM read_csv('{slots_path}') "
        f"WHERE Season = {season}"
    ).df()
    conn.close()

    if season >= 2011:
        assert len(df) == 67, (
            f"Expected 67 slots for season {season}, got {len(df)}"
        )

    # Build slots dict: slot_id -> {StrongSeed, WeakSeed}
    slots_dict = df.set_index("Slot")[["StrongSeed", "WeakSeed"]].to_dict("index")

    # Identify First Four slots: those whose slot_id does NOT start with 'R'
    ff_slots = {sid for sid in slots_dict if not sid.startswith("R")}

    # Build topological order:
    # FF slots (round 0) first, then R1 (round 1) through R6 (round 6).
    # Within the same round, maintain stable order for reproducibility.
    ordered = sorted(slots_dict.keys(), key=slot_round_number)

    return {
        "slots": slots_dict,
        "order": ordered,
        "ff_slots": ff_slots,
    }


# ---------------------------------------------------------------------------
# Topological order convenience
# ---------------------------------------------------------------------------


def get_topological_order(slot_tree: dict[str, Any]) -> list[str]:
    """Return the topologically-ordered slot list from a slot tree.

    Convenience wrapper around slot_tree['order'].

    Args:
        slot_tree: Dict returned by build_slot_tree().

    Returns:
        List of slot IDs in topological order (FF first, R1 through R6 last).
    """
    return slot_tree["order"]


# ---------------------------------------------------------------------------
# Seedings
# ---------------------------------------------------------------------------


def load_seedings(
    season: int = 2025,
    seeds_parquet: str = SEEDS_PARQUET,
) -> dict[str, int]:
    """Load seed-label to team_id mappings for a tournament season.

    The Seed column in seeds.parquet contains labels like 'W01', 'W16a', 'X11b'
    which identify each team's region and seed position. First Four teams have
    trailing 'a' or 'b' suffixes.

    Args:
        season: Tournament season year. Default: 2025.
        seeds_parquet: Path to seeds.parquet. Default: SEEDS_PARQUET.

    Returns:
        Dict mapping seed_label (str) -> kaggle_team_id (int).
        E.g. {'W01': 1181, 'W16a': 1110, 'W16b': 1291, ...}

    Raises:
        AssertionError: If seedings count is not 68 for post-2010 seasons.
        FileNotFoundError: If seeds_parquet does not exist.
    """
    parquet_path = pathlib.Path(seeds_parquet)
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Seeds parquet not found at {seeds_parquet}. "
            "Run Phase 1 tournament data ingestion first."
        )

    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT Seed, TeamID "
        f"FROM read_parquet('{parquet_path}') "
        f"WHERE Season = {season}"
    ).df()
    conn.close()

    result: dict[str, int] = {
        str(row.Seed): int(row.TeamID)
        for row in df.itertuples(index=False)
    }

    if season >= 2011:
        assert len(result) == 68, (
            f"Expected 68 seedings for season {season}, got {len(result)}"
        )

    return result


# ---------------------------------------------------------------------------
# Team-seed map
# ---------------------------------------------------------------------------


def build_team_seed_map(seedings: dict[str, int]) -> dict[int, int]:
    """Build a mapping from team_id to integer seed number.

    Parses the seed number from each seed label by stripping the region prefix
    (first character) and any trailing 'a'/'b' First Four suffix.

    Examples:
        'W01' -> 1
        'X16a' -> 16
        'Y11b' -> 11
        'Z05' -> 5

    First Four teams (e.g., W16a, W16b) will both map to seed 16. Multiple
    teams can therefore share the same integer seed number.

    Args:
        seedings: Dict returned by load_seedings() mapping seed_label -> team_id.

    Returns:
        Dict mapping kaggle_team_id (int) -> integer seed number (int).
    """
    team_seed_map: dict[int, int] = {}
    for seed_label, team_id in seedings.items():
        # seed_label format: {region_letter}{two_digit_seed}[a|b]
        # Strip region prefix (first char) and optional trailing 'a' or 'b'
        seed_str = seed_label[1:]  # remove region letter
        if seed_str.endswith(("a", "b")):
            seed_str = seed_str[:-1]  # remove First Four suffix
        seed_num = int(seed_str)
        team_seed_map[team_id] = seed_num

    return team_seed_map


# ---------------------------------------------------------------------------
# Predict function builder
# ---------------------------------------------------------------------------


def build_predict_fn(
    model_path: str = "models/logistic_baseline.joblib",
    processed_dir: str = "data/processed",
    season: int = 2025,
) -> tuple[Any, dict]:
    """Build a predict_fn closure wrapping the Phase 3 trained model.

    Loads the trained logistic regression model artifact, builds the stats
    lookup from processed data, and returns a callable predict_fn plus the
    stats_lookup dict (needed by score_predictor.py in plan 04-04).

    The predict_fn uses the canonical ordering: team_a_id must be the team
    with the lower seed number (better seed / higher rank). This is the
    caller's responsibility to ensure correct feature sign conventions.

    Args:
        model_path: Path to the joblib model artifact. Default: models/logistic_baseline.joblib
        processed_dir: Directory containing parquet files. Default: data/processed
        season: Season for which predictions are being made. Default: 2025

    Returns:
        Tuple of (predict_fn, stats_lookup) where:
            predict_fn(team_a_id, team_b_id) -> float probability in (0, 1)
            stats_lookup: dict keyed by (season, team_id) from build_stats_lookup()

    Raises:
        FileNotFoundError: If model artifact does not exist.
    """
    from src.models.train_logistic import load_model, predict_matchup
    from src.models.features import _compute_features_by_id, build_stats_lookup

    # Load model artifact — returns (calibrator, scaler, feature_names)
    model, scaler, feature_names = load_model(model_path)

    # Build stats lookup for the season
    stats_lookup = build_stats_lookup(processed_dir)

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        """Predict win probability for team_a vs team_b.

        team_a_id must be the lower-seed (better-seed) team for correct
        feature sign conventions (same as training canonical ordering).

        Args:
            team_a_id: Kaggle team ID for team A (lower seed number = better seed).
            team_b_id: Kaggle team ID for team B (higher seed number = worse seed).

        Returns:
            Float in (0, 1): probability that team_a wins.
        """
        features = _compute_features_by_id(season, team_a_id, team_b_id, stats_lookup)
        return predict_matchup(features, model, scaler, feature_names)

    return predict_fn, stats_lookup


# ---------------------------------------------------------------------------
# Main block for smoke testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("bracket_schema.py smoke test")
    print("=" * 60)

    # --- Slot tree ---
    print("\n[1] build_slot_tree(season=2025)")
    tree = build_slot_tree(season=2025)
    print(f"  Total slots:  {len(tree['slots'])}")
    print(f"  FF slots:     {sorted(tree['ff_slots'])}")
    print(f"  First 5 in order: {tree['order'][:5]}")
    print(f"  Last 3 in order:  {tree['order'][-3:]}")
    assert len(tree["slots"]) == 67, "Expected 67 slots"
    assert tree["order"][-1] == "R6CH", f"Last slot should be R6CH, got {tree['order'][-1]}"
    print("  OK")

    # --- Seedings ---
    print("\n[2] load_seedings(season=2025)")
    seedings = load_seedings(season=2025)
    print(f"  Total seedings: {len(seedings)}")
    sample = list(seedings.items())[:5]
    for label, tid in sample:
        print(f"    {label} -> {tid}")
    assert len(seedings) == 68, "Expected 68 seedings"
    print("  OK")

    # --- Team-seed map ---
    print("\n[3] build_team_seed_map(seedings)")
    tsm = build_team_seed_map(seedings)
    print(f"  Team-seed map entries: {len(tsm)}")
    # Show a 1-seed and a 16-seed
    w01_team = seedings.get("W01")
    if w01_team:
        print(f"    W01 team {w01_team} -> seed {tsm[w01_team]}")
    w16a_team = seedings.get("W16a")
    if w16a_team:
        print(f"    W16a team {w16a_team} -> seed {tsm[w16a_team]}")
    seed_vals = set(tsm.values())
    assert 1 in seed_vals and 16 in seed_vals, "Missing seed 1 or 16"
    print(f"  Seeds present: {min(seed_vals)}-{max(seed_vals)}")
    print("  OK")

    # --- predict_fn ---
    print("\n[4] build_predict_fn(season=2025)")
    predict_fn, stats = build_predict_fn(season=2025)

    # Find a 1-seed and a 16-seed for a 1v16 test
    one_seed_team = None
    sixteen_seed_team = None
    for label, tid in seedings.items():
        seed_num = tsm[tid]
        if seed_num == 1 and one_seed_team is None:
            one_seed_team = tid
        if seed_num == 16 and not label.endswith(("a", "b")) and sixteen_seed_team is None:
            sixteen_seed_team = tid

    if one_seed_team and sixteen_seed_team:
        prob = predict_fn(one_seed_team, sixteen_seed_team)
        print(f"  1-seed (team {one_seed_team}) vs 16-seed (team {sixteen_seed_team}): P(1-seed wins) = {prob:.4f}")
        assert 0.5 < prob < 0.95, (
            f"1v16 probability {prob:.4f} outside expected range (0.5, 0.95)"
        )
        print("  OK")
    else:
        print("  WARNING: Could not find suitable 1-seed/16-seed pair for test")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
