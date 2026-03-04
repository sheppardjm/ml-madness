"""
advancement_table.py

Builds a sortable DataFrame of round-by-round advancement probabilities
for all 68 tournament teams based on Monte Carlo simulation results.

Exports:
    build_advancement_df(mc_result, team_id_to_name, team_id_to_seed, all_team_ids) -> pd.DataFrame
    get_round_column_config() -> dict  (must be called inside Streamlit context)
"""

import pandas as pd

ROUND_COLS = [
    "Round of 64",
    "Round of 32",
    "Sweet 16",
    "Elite 8",
    "Final Four",
    "Championship",
    "Champion",
]


def _parse_seed_num(seed_label: str) -> int:
    """Extract integer seed number from a seed label like 'W01', 'X16a', 'Y11b'.

    Strips the leading region letter and trailing play-in suffix (a/b), then
    returns the numeric seed as an integer (1-16).  Falls back to 99 if the
    label cannot be parsed so that malformed seeds sort to the bottom.
    """
    if not seed_label or len(seed_label) < 2:
        return 99
    # Strip leading region letter
    numeric_part = seed_label[1:]
    # Strip trailing play-in suffix (a or b)
    if numeric_part and numeric_part[-1] in ("a", "b"):
        numeric_part = numeric_part[:-1]
    try:
        return int(numeric_part)
    except ValueError:
        return 99


def build_advancement_df(
    mc_result: dict,
    team_id_to_name: dict,
    team_id_to_seed: dict,
    all_team_ids: list,
) -> pd.DataFrame:
    """Build advancement probability DataFrame for all 68 tournament teams.

    Parameters
    ----------
    mc_result:
        Dict returned by simulate_bracket(mode="monte_carlo").
        Must contain an "advancement_probs" key mapping team_id -> {round_name: float}.
    team_id_to_name:
        Dict mapping team_id -> display name string.
    team_id_to_seed:
        Dict mapping team_id -> seed label (e.g. "W01", "X16a").
    all_team_ids:
        List of all 68 team IDs in the tournament (from seedings.values()).
        Iterating over this list (rather than advancement_probs.keys()) ensures
        First Four losers with zero advancement probability are included --
        this is the LEFT JOIN pattern from research pitfall 4.

    Returns
    -------
    pd.DataFrame with columns:
        Team (str), Seed (str), SeedNum (int),
        Round of 64, Round of 32, Sweet 16, Elite 8,
        Final Four, Championship, Champion (all float 0.0–1.0).

    Sorted by Champion descending, then SeedNum ascending.
    """
    advancement_probs: dict = mc_result.get("advancement_probs", {})

    rows = []
    for team_id in all_team_ids:
        probs = advancement_probs.get(team_id, {})
        seed_label = team_id_to_seed.get(team_id, "")
        row = {
            "Team": team_id_to_name.get(team_id, str(team_id)),
            "Seed": seed_label,
            "SeedNum": _parse_seed_num(seed_label),
        }
        for col in ROUND_COLS:
            row[col] = float(probs.get(col, 0.0))
        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort: Champion descending (primary), SeedNum ascending (secondary tie-break)
    df = df.sort_values(
        by=["Champion", "SeedNum"],
        ascending=[False, True],
    ).reset_index(drop=True)

    return df


def get_round_column_config() -> dict:
    """Return st.dataframe column_config dict for advancement probability columns.

    Configures ProgressColumn for each round column so Streamlit renders
    visual probability bars.  Sets SeedNum to None to hide it from the
    displayed table (it is used only for pre-sort ordering).

    IMPORTANT: Must be called at runtime within a Streamlit context because
    st.column_config is only available when Streamlit is running.
    Do NOT call this function at module import time.
    """
    import streamlit as st  # noqa: PLC0415 -- intentionally deferred import

    config = {
        col: st.column_config.ProgressColumn(
            col,
            format="%.1f%%",
            min_value=0.0,
            max_value=1.0,
        )
        for col in ROUND_COLS
    }
    # Hide SeedNum -- used for sorting only, not for user display.
    # Setting a column to None in column_config hides it from st.dataframe.
    config["SeedNum"] = None
    return config
