"""
Champion eligibility filter based on historical conditions.

Five conditions must ALL be met for a team to be eligible to win the championship:
1. Reached at least the conference tournament semifinals
2. Lost no more than 2 of their last 4 regular season games
3. Top 25 in adjusted efficiency margin (adj_o - adj_d)
4. Top 57 in adjusted offensive efficiency
5. Top 44 in adjusted defensive efficiency

Every NCAA champion from 2008-2025 satisfied all five conditions.
Conditions 1-2 also hold for 2003-2007 (ratings data unavailable for 3-5).

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

# Torvik ratings paths
_HIST_RATINGS = pathlib.Path("data/processed/historical_torvik_ratings.parquet")
_CURRENT_RATINGS = pathlib.Path("data/processed/current_season_stats.parquet")

# Rating rank thresholds (verified against all champions 2008-2025)
_MAX_EFF_MARGIN_RANK = 25   # adj_o - adj_d rank among all D1 teams
_MAX_ADJ_O_RANK = 57        # adj offensive efficiency rank
_MAX_ADJ_D_RANK = 44        # adj defensive efficiency rank (lower adj_d = better)


def get_champion_ineligible_teams(
    season: int,
    conf_tourney_csv: str | pathlib.Path | None = None,
    reg_season_csv: str | pathlib.Path | None = None,
    team_conf_csv: str | pathlib.Path | None = None,
    tournament_team_ids: set[int] | None = None,
) -> set[int]:
    """Return team IDs ineligible to win the championship for a given season.

    A team is ineligible if it fails ANY condition:
    1. Did not reach its conference tournament semifinals
    2. Lost more than 2 of its last 4 regular season games
    3. Not in top 25 of adjusted efficiency margin (adj_o - adj_d)
    4. Not in top 57 of adjusted offensive efficiency
    5. Not in top 44 of adjusted defensive efficiency

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

    # Pre-compute rating ranks for conditions 3-5
    rating_ineligible = _get_rating_ineligible(con, season)

    ineligible: set[int] = set()

    for tid in tournament_team_ids:
        # --- Condition 1: Reached conference tournament semifinals ---
        if not _reached_conf_semis(con, season, tid):
            ineligible.add(tid)
            continue

        # --- Condition 2: Lost ≤2 of last 4 regular season games ---
        if _last4_rs_losses(con, season, tid) > 2:
            ineligible.add(tid)
            continue

        # --- Conditions 3-5: Rating rank thresholds ---
        if tid in rating_ineligible:
            ineligible.add(tid)

    con.close()
    return ineligible


def _get_rating_ineligible(con: duckdb.DuckDBPyConnection, season: int) -> set[int]:
    """Return team IDs failing any of the three rating rank conditions.

    Loads Torvik ratings for the season (historical or current), computes
    efficiency margin, and checks each team's rank against thresholds.

    Returns empty set if no ratings data is available (graceful degradation).
    """
    # Try historical ratings first, then current season stats
    ratings_df = None
    for path in (_HIST_RATINGS, _CURRENT_RATINGS):
        if not path.exists():
            continue
        # historical uses 'season', current uses 'year'
        season_col = "season" if path == _HIST_RATINGS else "year"
        df = con.execute(f"""
            SELECT kaggle_team_id, adj_o, adj_d, (adj_o - adj_d) as eff_margin
            FROM read_parquet('{path}')
            WHERE {season_col} = ?
        """, [season]).fetchdf()
        if len(df) > 0:
            ratings_df = df
            break

    if ratings_df is None or len(ratings_df) == 0:
        return set()  # no ratings data = don't penalize

    # Compute ranks (1-based, higher is better for adj_o/eff_margin, lower is better for adj_d)
    ratings_df = ratings_df.copy()
    ratings_df["em_rank"] = ratings_df["eff_margin"].rank(ascending=False, method="min").astype(int)
    ratings_df["ao_rank"] = ratings_df["adj_o"].rank(ascending=False, method="min").astype(int)
    ratings_df["ad_rank"] = ratings_df["adj_d"].rank(ascending=True, method="min").astype(int)

    ineligible: set[int] = set()
    for _, row in ratings_df.iterrows():
        tid = int(row["kaggle_team_id"])
        if (
            row["em_rank"] > _MAX_EFF_MARGIN_RANK
            or row["ao_rank"] > _MAX_ADJ_O_RANK
            or row["ad_rank"] > _MAX_ADJ_D_RANK
        ):
            ineligible.add(tid)

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
