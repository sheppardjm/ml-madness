"""
Parse Kaggle NCAA regular season CSV into a cleaned Parquet file.

Produces:
  - data/processed/regular_season.parquet — regular season game records with GameDate and WLoc
"""

import pathlib

import duckdb


def ingest_regular_season(
    raw_dir: str = "data/raw/kaggle",
    out_dir: str = "data/processed",
) -> int:
    """
    Read MRegularSeasonCompactResults.csv, join team names and game dates, write Parquet.

    Notes:
    - Includes Season 2020 (regular season data exists even though tournament was cancelled;
      useful for computing team stats as context for 2021 predictions).
    - WLoc column IS present in regular season data (H=home win, A=away win, N=neutral).
    - GameDate computed as DayZero + DayNum (DayNum cast to INTEGER).

    Returns:
        Number of rows written to regular_season.parquet.
    """
    raw_path = pathlib.Path(raw_dir)
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    reg_season_csv = raw_path / "MRegularSeasonCompactResults.csv"
    teams_csv = raw_path / "MTeams.csv"
    seasons_csv = raw_path / "MSeasons.csv"
    out_file = out_path / "regular_season.parquet"

    conn = duckdb.connect()
    conn.execute(f"""
        COPY (
            SELECT
                r.Season,
                r.DayNum,
                (s.DayZero::DATE + CAST(r.DayNum AS INTEGER)) AS GameDate,
                r.WTeamID,
                wt.TeamName                                    AS WTeamName,
                r.WScore,
                r.LTeamID,
                lt.TeamName                                    AS LTeamName,
                r.LScore,
                r.WLoc,
                r.NumOT
            FROM read_csv('{reg_season_csv}') r
            JOIN read_csv('{seasons_csv}') s  ON r.Season  = s.Season
            JOIN read_csv('{teams_csv}')   wt ON r.WTeamID = wt.TeamID
            JOIN read_csv('{teams_csv}')   lt ON r.LTeamID = lt.TeamID
            WHERE r.Season >= 2003
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
