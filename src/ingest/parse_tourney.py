"""
Parse Kaggle NCAA tournament CSVs into cleaned Parquet files.

Produces:
  - data/processed/tournament_games.parquet  — game records with GameDate, Round, IsFirstFour
  - data/processed/seeds.parquet             — seedings with Region, SeedNum, IsFirstFour
"""

import pathlib

import duckdb

from src.utils.seasons import DAYNUM_ROUND_MAP

# The First Four (4-game expansion) started in 2011.
# Before 2011, a single play-in game existed at DayNum=134 — it is labeled differently.
FIRST_FOUR_START_SEASON = 2011


def ingest_tournament_games(
    raw_dir: str = "data/raw/kaggle",
    out_dir: str = "data/processed",
) -> int:
    """
    Read MNCAATourneyCompactResults.csv, join team names and game dates, write Parquet.

    First Four handling:
    - Season >= 2011, DayNum IN (134, 135): IsFirstFour=True, Round='First Four'
    - Season <  2011, DayNum = 134:         IsFirstFour=True, Round='Play-In Game'

    Returns:
        Number of rows written to tournament_games.parquet.
    """
    raw_path = pathlib.Path(raw_dir)
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    tourney_csv = raw_path / "MNCAATourneyCompactResults.csv"
    teams_csv = raw_path / "MTeams.csv"
    seasons_csv = raw_path / "MSeasons.csv"
    out_file = out_path / "tournament_games.parquet"

    # Build the CASE expression for Round from DAYNUM_ROUND_MAP.
    # For pre-2011 DayNum=134 games, override 'First Four' with 'Play-In Game'.
    round_case_parts = []
    for daynum, round_name in DAYNUM_ROUND_MAP.items():
        if daynum == 134:
            # Pre-2011: single play-in game; 2011+: First Four
            round_case_parts.append(
                f"WHEN r.DayNum = {daynum} AND r.Season < {FIRST_FOUR_START_SEASON} "
                f"THEN 'Play-In Game'"
            )
            round_case_parts.append(
                f"WHEN r.DayNum = {daynum} AND r.Season >= {FIRST_FOUR_START_SEASON} "
                f"THEN '{round_name}'"
            )
        elif daynum == 135:
            # DayNum=135 only appears 2011+, but be explicit about season
            round_case_parts.append(
                f"WHEN r.DayNum = {daynum} THEN '{round_name}'"
            )
        else:
            round_case_parts.append(f"WHEN r.DayNum = {daynum} THEN '{round_name}'")

    round_case = "CASE\n                " + "\n                ".join(round_case_parts) + "\n            END"

    conn = duckdb.connect()
    conn.execute(f"""
        COPY (
            SELECT
                r.Season,
                r.DayNum,
                (s.DayZero::DATE + CAST(r.DayNum AS INTEGER)) AS GameDate,
                r.WTeamID,
                wt.TeamName                             AS WTeamName,
                r.WScore,
                r.LTeamID,
                lt.TeamName                             AS LTeamName,
                r.LScore,
                r.NumOT,
                'N'                                     AS WLoc,
                CASE
                    WHEN r.DayNum IN (134, 135) THEN true
                    ELSE false
                END                                     AS IsFirstFour,
                {round_case}                             AS Round
            FROM read_csv('{tourney_csv}') r
            JOIN read_csv('{seasons_csv}') s  ON r.Season  = s.Season
            JOIN read_csv('{teams_csv}')   wt ON r.WTeamID = wt.TeamID
            JOIN read_csv('{teams_csv}')   lt ON r.LTeamID = lt.TeamID
            WHERE r.Season >= 2003
              AND r.Season != 2020
            ORDER BY r.Season, r.DayNum
        )
        TO '{out_file}'
        (FORMAT parquet, COMPRESSION zstd)
    """)

    row_count = conn.execute(
        f"SELECT COUNT(*) FROM read_parquet('{out_file}')"
    ).fetchone()[0]
    conn.close()
    return row_count


def ingest_tournament_seeds(
    raw_dir: str = "data/raw/kaggle",
    out_dir: str = "data/processed",
) -> int:
    """
    Read MNCAATourneySeeds.csv, parse the Seed string into structured fields, write Parquet.

    Seed format: 'W01', 'X16a', 'Z11b'
      - Region:     first character (W / X / Y / Z)
      - SeedNum:    next 2 digits as integer
      - IsFirstFour: True if seed ends with 'a' or 'b'

    Returns:
        Number of rows written to seeds.parquet.
    """
    raw_path = pathlib.Path(raw_dir)
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    seeds_csv = raw_path / "MNCAATourneySeeds.csv"
    teams_csv = raw_path / "MTeams.csv"
    out_file = out_path / "seeds.parquet"

    conn = duckdb.connect()
    conn.execute(f"""
        COPY (
            SELECT
                sd.Season,
                sd.TeamID,
                t.TeamName,
                sd.Seed,
                LEFT(sd.Seed, 1)                        AS Region,
                CAST(SUBSTRING(sd.Seed, 2, 2) AS INTEGER) AS SeedNum,
                CASE
                    WHEN RIGHT(sd.Seed, 1) IN ('a', 'b') THEN true
                    ELSE false
                END                                     AS IsFirstFour
            FROM read_csv('{seeds_csv}') sd
            JOIN read_csv('{teams_csv}') t ON sd.TeamID = t.TeamID
            WHERE sd.Season >= 2003
              AND sd.Season != 2020
            ORDER BY sd.Season, sd.Seed
        )
        TO '{out_file}'
        (FORMAT parquet, COMPRESSION zstd)
    """)

    row_count = conn.execute(
        f"SELECT COUNT(*) FROM read_parquet('{out_file}')"
    ).fetchone()[0]
    conn.close()
    return row_count
