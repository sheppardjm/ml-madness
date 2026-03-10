"""
Champion eligibility filter based on historical conditions.

Two conditions must be met for a team to be eligible to win the championship:
1. Reached at least the conference tournament semifinals
2. Lost no more than 2 of their last 4 regular season games

Every NCAA champion from 2003-2025 satisfied both conditions.

Exports:
    get_champion_ineligible_teams(season) -> set of team IDs ineligible for championship
"""

from __future__ import annotations

import pathlib

import duckdb

# Kaggle raw data paths
_KAGGLE_DIR = pathlib.Path("data/raw/kaggle")
_CONF_TOURNEY_CSV = _KAGGLE_DIR / "MConferenceTourneyGames.csv"
_REG_SEASON_CSV = _KAGGLE_DIR / "MRegularSeasonCompactResults.csv"
_TEAM_CONF_CSV = _KAGGLE_DIR / "MTeamConferences.csv"


def get_champion_ineligible_teams(
    season: int,
    conf_tourney_csv: str | pathlib.Path | None = None,
    reg_season_csv: str | pathlib.Path | None = None,
    team_conf_csv: str | pathlib.Path | None = None,
    tournament_team_ids: set[int] | None = None,
) -> set[int]:
    """Return team IDs ineligible to win the championship for a given season.

    A team is ineligible if it fails EITHER condition:
    1. Did not reach its conference tournament semifinals
    2. Lost more than 2 of its last 4 regular season games

    Args:
        season: Tournament season year.
        conf_tourney_csv: Path to MConferenceTourneyGames.csv. Defaults to Kaggle dir.
        reg_season_csv: Path to MRegularSeasonCompactResults.csv. Defaults to Kaggle dir.
        team_conf_csv: Path to MTeamConferences.csv. Defaults to Kaggle dir.
        tournament_team_ids: If provided, only evaluate these teams. Otherwise
            evaluates all teams that appear in the conference tournament data.

    Returns:
        Set of kaggle team IDs that are ineligible for the championship.
        Empty set if data files are missing (graceful degradation).
    """
    ct_path = pathlib.Path(conf_tourney_csv or _CONF_TOURNEY_CSV)
    rs_path = pathlib.Path(reg_season_csv or _REG_SEASON_CSV)
    tc_path = pathlib.Path(team_conf_csv or _TEAM_CONF_CSV)

    # Graceful degradation: if data files don't exist, return empty set
    for p in (ct_path, rs_path, tc_path):
        if not p.exists():
            return set()

    con = duckdb.connect()

    # Load tables
    con.execute(f"CREATE TABLE ct AS SELECT * FROM read_csv_auto('{ct_path}')")
    con.execute(f"CREATE TABLE rs AS SELECT * FROM read_csv_auto('{rs_path}')")
    con.execute(f"CREATE TABLE tc AS SELECT * FROM read_csv_auto('{tc_path}')")

    # Get all tournament team IDs for this season if not provided
    if tournament_team_ids is None:
        rows = con.execute("""
            SELECT DISTINCT TeamID FROM (
                SELECT WTeamID as TeamID FROM ct WHERE Season = ?
                UNION
                SELECT LTeamID as TeamID FROM ct WHERE Season = ?
            )
        """, [season, season]).fetchall()
        tournament_team_ids = {r[0] for r in rows}

    ineligible: set[int] = set()

    for tid in tournament_team_ids:
        # --- Condition 1: Reached conference tournament semifinals ---
        if not _reached_conf_semis(con, season, tid):
            ineligible.add(tid)
            continue

        # --- Condition 2: Lost ≤2 of last 4 regular season games ---
        if _last4_rs_losses(con, season, tid) > 2:
            ineligible.add(tid)

    con.close()
    return ineligible


def _reached_conf_semis(con: duckdb.DuckDBPyConnection, season: int, tid: int) -> bool:
    """Check if team reached at least the conference tournament semifinals."""
    # Get team's conference
    conf_row = con.execute(
        "SELECT ConfAbbrev FROM tc WHERE Season = ? AND TeamID = ?",
        [season, tid],
    ).fetchone()
    if not conf_row:
        return True  # no conference data = don't penalize
    conf = conf_row[0]

    # Get team's conf tourney games
    ct_games = con.execute("""
        SELECT DayNum FROM ct
        WHERE Season = ? AND (WTeamID = ? OR LTeamID = ?)
        ORDER BY DayNum
    """, [season, tid, tid]).fetchdf()

    if len(ct_games) == 0:
        return True  # no conf tourney games = don't penalize

    # Get distinct game days for this conference tournament
    distinct_days = con.execute("""
        SELECT DISTINCT DayNum FROM ct
        WHERE Season = ? AND ConfAbbrev = ?
        ORDER BY DayNum DESC
    """, [season, conf]).fetchdf()["DayNum"].tolist()

    if len(distinct_days) < 2:
        return True  # single-day conf tourney = everyone reached semis

    # Semifinal = 2nd-to-last distinct game day
    semi_day = distinct_days[1]
    last_game_day = ct_games["DayNum"].max()

    return last_game_day >= semi_day


def _last4_rs_losses(con: duckdb.DuckDBPyConnection, season: int, tid: int) -> int:
    """Count losses in last 4 regular season games."""
    last4 = con.execute("""
        WITH games AS (
            SELECT DayNum, 'W' as result FROM rs
            WHERE Season = ? AND WTeamID = ?
            UNION ALL
            SELECT DayNum, 'L' as result FROM rs
            WHERE Season = ? AND LTeamID = ?
        )
        SELECT result FROM games ORDER BY DayNum DESC LIMIT 4
    """, [season, tid, season, tid]).fetchdf()

    if len(last4) == 0:
        return 0  # no data = don't penalize

    return int((last4["result"] == "L").sum())
