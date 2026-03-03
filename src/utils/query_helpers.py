"""
Convenience query functions for the Phase 1 processed Parquet files.

These helpers provide:
- Selection Sunday cutoff enforcement (no post-cutoff data leaked into predictions)
- Simple tournament game and team name lookups
- A consistent interface for all downstream phases to query the pipeline data

All functions operate on the Parquet files in data/processed/ and return pandas
DataFrames. DuckDB is used for efficient in-process SQL filtering.

Usage:
    from src.utils.query_helpers import get_tourney_games, get_season_stats_with_cutoff, get_team_name

    # Get 2025 tournament games, excluding First Four
    games = get_tourney_games(2025, include_first_four=False)

    # Get 2025 regular season stats, cutoff-enforced (Selection Sunday inclusive)
    stats = get_season_stats_with_cutoff(2025)

    # Look up canonical name for Kansas (TeamID 1242)
    name = get_team_name(1242)  # returns "Kansas"
"""

from __future__ import annotations

import pathlib

import duckdb
import pandas as pd

from src.utils.cutoff_dates import get_cutoff

# Default locations for processed Parquet files
_PROCESSED_DIR = pathlib.Path("data/processed")
_TOURNEY_PARQUET = _PROCESSED_DIR / "tournament_games.parquet"
_REGULAR_SEASON_PARQUET = _PROCESSED_DIR / "regular_season.parquet"
_TEAM_NORM_PARQUET = _PROCESSED_DIR / "team_normalization.parquet"


def get_tourney_games(
    season: int,
    include_first_four: bool = False,
    processed_dir: str = "data/processed",
) -> pd.DataFrame:
    """Load tournament game records for a given season.

    Reads from tournament_games.parquet and filters to the specified season.
    Optionally includes First Four play-in games (excluded by default so callers
    work with the 64-team bracket without special-casing).

    Args:
        season: NCAA tournament season year (e.g., 2025).
        include_first_four: If True, include DayNum 134-135 play-in games.
            Default False (returns only bracket games from Round of 64 onward).
        processed_dir: Path to directory containing tournament_games.parquet.
            Default: data/processed

    Returns:
        DataFrame with all tournament game columns (Season, DayNum, GameDate,
        WTeamID, WTeamName, WScore, LTeamID, LTeamName, LScore, NumOT, WLoc,
        IsFirstFour, Round), ordered by DayNum.

    Example:
        >>> games_2025 = get_tourney_games(2025)
        >>> print(len(games_2025))  # 63 (Full bracket, no First Four)
        >>> games_with_ff = get_tourney_games(2025, include_first_four=True)
        >>> print(len(games_with_ff))  # 67 (63 + 4 First Four games)
    """
    parquet = pathlib.Path(processed_dir) / "tournament_games.parquet"
    first_four_clause = "" if include_first_four else "AND NOT IsFirstFour"
    return duckdb.sql(
        f"""
        SELECT *
        FROM read_parquet('{parquet}')
        WHERE Season = {season}
        {first_four_clause}
        ORDER BY DayNum
        """
    ).df()


def get_season_stats_with_cutoff(
    season: int,
    processed_dir: str = "data/processed",
) -> pd.DataFrame:
    """Load regular season games up to and including the Selection Sunday cutoff.

    CRITICAL: This function enforces the data-leakage guard. It only returns
    games with GameDate <= Selection Sunday for the specified season. This
    ensures no post-Selection-Sunday data is used when computing team stats
    for bracket predictions — exactly replicating what would be available
    on Selection Sunday.

    Args:
        season: NCAA tournament season year (e.g., 2025).
            Must be a valid tournament season (2003-2019, 2021-2025).
            Raises ValueError for 2020 (cancelled) or out-of-range seasons.
        processed_dir: Path to directory containing regular_season.parquet.
            Default: data/processed

    Returns:
        DataFrame with all regular season game columns (Season, DayNum, WTeamID,
        WTeamName, WScore, LTeamID, LTeamName, LScore, WLoc, NumOT, GameDate),
        filtered to GameDate <= Selection Sunday for the given season.

    Raises:
        ValueError: If season has no Selection Sunday date (e.g., 2020 or out-of-range).

    Example:
        >>> stats_2025 = get_season_stats_with_cutoff(2025)
        >>> print(stats_2025['GameDate'].max())  # Should be <= 2025-03-16
    """
    cutoff = get_cutoff(season)  # Raises ValueError if invalid season
    parquet = pathlib.Path(processed_dir) / "regular_season.parquet"
    return duckdb.sql(
        f"""
        SELECT *
        FROM read_parquet('{parquet}')
        WHERE Season = {season}
          AND GameDate <= '{cutoff}'
        ORDER BY DayNum
        """
    ).df()


def get_team_name(
    team_id: int,
    processed_dir: str = "data/processed",
) -> str:
    """Look up the canonical team name for a Kaggle TeamID.

    Reads from team_normalization.parquet to find the authoritative canonical
    name for a given team ID. The canonical_name is the primary cross-source
    identifier used throughout the pipeline.

    Args:
        team_id: Kaggle TeamID integer (e.g., 1242 for Kansas).
        processed_dir: Path to directory containing team_normalization.parquet.
            Default: data/processed

    Returns:
        Canonical team name string (e.g., "Kansas").

    Raises:
        KeyError: If team_id is not found in the normalization table.

    Example:
        >>> get_team_name(1242)
        'Kansas'
        >>> get_team_name(1163)
        'Connecticut'
    """
    parquet = pathlib.Path(processed_dir) / "team_normalization.parquet"
    result = duckdb.sql(
        f"""
        SELECT canonical_name
        FROM read_parquet('{parquet}')
        WHERE kaggle_team_id = {team_id}
        LIMIT 1
        """
    ).fetchone()
    if result is None:
        raise KeyError(f"TeamID {team_id} not found in team_normalization.parquet")
    return result[0]
