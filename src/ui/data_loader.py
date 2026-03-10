"""
Cached data loading functions for the Streamlit UI.

Provides model loading, ensemble predict_fn adapter, cached bracket simulations,
and team name lookup for the Phase 9 Bracket Visualization UI.

All functions use @st.cache_resource or @st.cache_data to ensure reruns are
instant. Unhashable arguments (joblib artifacts, closures, seedings dicts) use
underscore-prefix naming convention to prevent Streamlit from attempting to hash
them.

Exports:
    load_model               - Load ensemble artifact + metadata (cache_resource)
    build_ensemble_predict_fn - Build predict_fn closure for TwoTierEnsemble (cache_resource)
    run_deterministic        - Run deterministic bracket simulation (cache_data)
    run_monte_carlo          - Run Monte Carlo bracket simulation (cache_data)
    load_team_info           - Load team ID -> name/seed mappings (cache_data)
    load_seedings_cached     - Load seedings dict for a season (cache_data)
"""

from __future__ import annotations

import json
import pathlib

import duckdb
import joblib
import numpy as np
import streamlit as st

from src.eligibility import get_champion_ineligible_teams
from src.models.features import FEATURE_COLS, _compute_features_by_id, build_stats_lookup
from src.simulator.bracket_schema import load_seedings
from src.simulator.simulate import simulate_bracket


@st.cache_resource
def load_model() -> tuple[dict, dict]:
    """Load the selected ensemble model artifact and metadata.

    Reads models/selected.json to get the model metadata (selected_model,
    model_type, mean_brier, model_artifact_path) then loads the joblib artifact
    at model_artifact_path.

    The joblib artifact dict contains:
        'ensemble'       - TwoTierEnsemble instance
        'scaler'         - StandardScaler fitted on full training data
        'feature_names'  - FEATURE_COLS ordered list
        ... plus training metadata keys

    Returns:
        Tuple of (ensemble_artifact, meta) where:
            ensemble_artifact: Full joblib dict with 'ensemble', 'scaler', 'feature_names'
            meta: Selected.json metadata dict

    Raises:
        FileNotFoundError: If models/selected.json or the model_artifact_path do not exist.
    """
    selected_json_path = pathlib.Path("models/selected.json")
    if not selected_json_path.exists():
        raise FileNotFoundError(
            f"models/selected.json not found at {selected_json_path.resolve()}. "
            "Run Phase 7 model selection (src/dashboard/compare.py) first."
        )

    with open(selected_json_path) as f:
        meta = json.load(f)

    artifact_path = pathlib.Path(meta["model_artifact_path"])
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {artifact_path.resolve()}. "
            f"Expected path from selected.json: {meta['model_artifact_path']}"
        )

    ensemble_artifact = joblib.load(artifact_path)
    return ensemble_artifact, meta


@st.cache_resource
def build_ensemble_predict_fn(_artifact: dict, season: int = 2025):
    """Build a predict_fn closure wrapping TwoTierEnsemble for bracket simulation.

    Extracts the TwoTierEnsemble and StandardScaler from the artifact dict,
    builds the stats lookup, and returns a predict_fn(team_a_id, team_b_id) -> float
    closure suitable for passing to simulate_bracket().

    The scaler.transform() is applied inside this predict_fn. TwoTierEnsemble.predict_proba()
    expects ALREADY-SCALED features per decision [06-03] — the scaling happens here,
    NOT inside predict_proba(). This matches the canonical call pattern.

    Args:
        _artifact: Full joblib artifact dict (underscore-prefix prevents Streamlit hashing).
        season: Tournament season year for stats lookup. Default: 2025.

    Returns:
        predict_fn(team_a_id: int, team_b_id: int) -> float in (0, 1).
        Returns P(team_a beats team_b). team_a_id must be the lower-seed (better-ranked) team.
    """
    ensemble = _artifact["ensemble"]
    scaler = ensemble.scaler

    # Build stats lookup for the season
    stats_lookup = build_stats_lookup("data/processed")

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        """Predict win probability for team_a vs team_b.

        Args:
            team_a_id: Kaggle team ID for team A (lower seed number = better seed).
            team_b_id: Kaggle team ID for team B (higher seed number = worse seed).

        Returns:
            Float in (0, 1): probability that team_a wins.
            Returns 0.5 on KeyError (missing stats for First Four play-in teams).
        """
        try:
            features = _compute_features_by_id(season, team_a_id, team_b_id, stats_lookup)
        except KeyError:
            # First Four play-in teams may be absent from cbbdata stats snapshot
            return 0.5

        # Build feature vector in FEATURE_COLS canonical order
        x = np.array(
            [[features[col] for col in FEATURE_COLS]],
            dtype=np.float64,
        )  # shape (1, 6)

        # Scale features (caller responsibility per [06-03] canonical call pattern)
        x_scaled = scaler.transform(x)

        # TwoTierEnsemble.predict_proba() expects already-scaled input
        prob = ensemble.predict_proba(x_scaled)

        return float(np.clip(prob[0, 1], 0.0, 1.0))

    return predict_fn


@st.cache_data
def load_champion_ineligible(season: int = 2025) -> set[int]:
    """Load team IDs ineligible to win the championship for a season.

    Checks two historical conditions:
    1. Must have reached conference tournament semifinals
    2. Must not have lost more than 2 of last 4 regular season games

    Returns empty set if data is unavailable (graceful degradation).
    """
    return get_champion_ineligible_teams(season)


@st.cache_data(hash_funcs={dict: lambda d: str(sorted(d.items()))})
def run_deterministic(
    _predict_fn,
    _seedings: dict,
    season: int = 2025,
    override_map: dict | None = None,
    champion_ineligible: frozenset[int] | None = None,
) -> dict:
    """Run deterministic bracket simulation with caching.

    Calls simulate_bracket() with mode='deterministic'. The result is cached
    so reruns are instant. stats_lookup is NOT passed (championship_game will
    be None; acceptable for bracket display).

    The override_map parameter is included in the cache key via hash_funcs
    so that different override configurations produce different cached results.
    Empty dict is normalized to None before passing to simulate_bracket() to
    avoid unnecessary validation overhead in the simulator when no overrides
    exist (per research pitfall 4).

    Args:
        _predict_fn: predict_fn callable (underscore-prefix prevents Streamlit hashing).
        _seedings: Seedings dict from load_seedings() (underscore-prefix prevents hashing).
        season: Tournament season year. Default: 2025.
        override_map: Dict mapping slot_id -> team_id for forced winners, or None.
            Must be a regular (non-underscore) parameter so Streamlit includes it in
            the cache key. hash_funcs on the decorator handles dict hashing.
            Example: {'R6CH': 1234} forces team 1234 to be champion.
            None or empty dict = no overrides (normal simulation).

    Returns:
        Deterministic simulation result dict with 'mode', 'season', 'slots', 'champion',
        'championship_game' keys per simulate_bracket() contract.
    """
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="deterministic",
        season=season,
        override_map=override_map or None,
        champion_ineligible=set(champion_ineligible) if champion_ineligible else None,
    )


@st.cache_data(hash_funcs={dict: lambda d: str(sorted(d.items()))})
def run_monte_carlo(
    _predict_fn,
    _seedings: dict,
    season: int = 2025,
    n_runs: int = 10000,
    seed: int = 42,
    override_map: dict | None = None,
    champion_ineligible: frozenset[int] | None = None,
) -> dict:
    """Run Monte Carlo bracket simulation with caching.

    Calls simulate_bracket() with mode='monte_carlo'. The result is cached
    so reruns are instant (10K runs takes ~0.2s but only happens once per session).

    The override_map parameter is included in the cache key via hash_funcs
    so that different override configurations produce different cached results.
    Empty dict is normalized to None before passing to simulate_bracket() to
    avoid unnecessary validation overhead in the simulator when no overrides
    exist (per research pitfall 4).

    Args:
        _predict_fn: predict_fn callable (underscore-prefix prevents Streamlit hashing).
        _seedings: Seedings dict from load_seedings() (underscore-prefix prevents hashing).
        season: Tournament season year. Default: 2025.
        n_runs: Number of Monte Carlo simulation runs. Default: 10000.
        seed: Random seed for reproducibility. Default: 42.
        override_map: Dict mapping slot_id -> team_id for forced winners, or None.
            Must be a regular (non-underscore) parameter so Streamlit includes it in
            the cache key. hash_funcs on the decorator handles dict hashing.
            Example: {'R6CH': 1234} forces team 1234 to be champion.
            None or empty dict = no overrides (normal simulation).

    Returns:
        Monte Carlo simulation result dict with 'mode', 'season', 'n_runs', 'champion',
        'advancement_probs' keys per simulate_bracket() contract.
    """
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="monte_carlo",
        n_runs=n_runs,
        seed=seed,
        season=season,
        override_map=override_map or None,
        champion_ineligible=set(champion_ineligible) if champion_ineligible else None,
    )


@st.cache_data
def load_team_info(
    season: int = 2025,
) -> tuple[dict[int, str], dict[int, str], dict[int, int]]:
    """Load team ID to name, seed label, and seed number mappings.

    Queries data/processed/seeds.parquet for the given season using DuckDB.
    This is the canonical team display name source per research pitfall 5.

    Args:
        season: Tournament season year. Default: 2025.

    Returns:
        Tuple of three dicts:
            team_id_to_name:    TeamID -> TeamName (e.g., {1181: "Duke"})
            team_id_to_seed:    TeamID -> Seed label (e.g., {1181: "W01"})
            team_id_to_seednum: TeamID -> SeedNum integer (e.g., {1181: 1})

    Raises:
        FileNotFoundError: If data/processed/seeds.parquet does not exist.
    """
    seeds_parquet = pathlib.Path("data/processed/seeds.parquet")
    if not seeds_parquet.exists():
        raise FileNotFoundError(
            f"seeds.parquet not found at {seeds_parquet.resolve()}. "
            "Run Phase 1 tournament data ingestion first."
        )

    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT TeamID, TeamName, Seed, SeedNum "
        f"FROM read_parquet('{seeds_parquet}') "
        f"WHERE Season = {season}"
    ).df()
    conn.close()

    team_id_to_name: dict[int, str] = {}
    team_id_to_seed: dict[int, str] = {}
    team_id_to_seednum: dict[int, int] = {}

    for row in df.itertuples(index=False):
        team_id = int(row.TeamID)
        team_id_to_name[team_id] = str(row.TeamName)
        team_id_to_seed[team_id] = str(row.Seed)
        team_id_to_seednum[team_id] = int(row.SeedNum)

    return team_id_to_name, team_id_to_seed, team_id_to_seednum


@st.cache_data
def load_seedings_cached(season: int = 2025) -> dict[str, int]:
    """Load seed-label to team_id mappings for a tournament season with caching.

    Wraps load_seedings() from src.simulator.bracket_schema with @st.cache_data
    so repeated Streamlit reruns do not re-read parquet files.

    Args:
        season: Tournament season year. Default: 2025.

    Returns:
        Dict mapping seed_label -> kaggle_team_id.
        E.g. {'W01': 1181, 'W16a': 1110, 'W16b': 1291, ...}
    """
    return load_seedings(season)
