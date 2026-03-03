"""
Build the canonical team name normalization table.

This module reads all teams from Kaggle's MTeams.csv and overlays hand-curated
alias overrides from data/seeds/team_aliases.csv to produce a single Parquet
file (team_normalization.parquet) that serves as the authoritative cross-source
team lookup table.

The normalization table columns:
    kaggle_team_id  - Kaggle's internal TeamID integer (primary key)
    canonical_name  - Authoritative human-readable name (used everywhere downstream)
    kaggle_name     - Raw name from MTeams.csv TeamName field
    espn_name       - ESPN display name (populated for known conflicts, blank otherwise)
    espn_slug       - ESPN URL slug (populated for known conflicts, blank otherwise)
    sr_slug         - Sports-Reference URL slug (populated for known conflicts, blank otherwise)
    cbbdata_name    - cbbdata/barttorvik name (populated for known conflicts, blank otherwise)
    ncaa_name       - Official NCAA name (blank — reserved for Phase 2 population)
    first_d1_season - First D1 season from MTeams.csv
    last_d1_season  - Last D1 season from MTeams.csv

Phase 2 will populate espn_name, espn_slug, sr_slug, cbbdata_name, and ncaa_name for
all remaining teams once those data sources are integrated.

Usage:
    uv run python -m src.normalize.build_team_table
"""

from __future__ import annotations

import pathlib

import duckdb
import pandas as pd


def build_normalization_table(
    raw_dir: str = "data/raw/kaggle",
    seeds_dir: str = "data/seeds",
    out_dir: str = "data/processed",
) -> int:
    """Build the canonical team name normalization table and write to Parquet.

    Reads all teams from MTeams.csv (Kaggle's master team reference), sets
    canonical_name = TeamName as the default, then overlays hand-curated
    overrides from team_aliases.csv. Writes the result to team_normalization.parquet.

    The alias columns (espn_name, espn_slug, sr_slug, cbbdata_name, ncaa_name) are
    empty strings for teams not in team_aliases.csv — they will be populated in
    Phase 2 when cross-source data is integrated.

    Args:
        raw_dir: Path to directory containing MTeams.csv. Default: data/raw/kaggle
        seeds_dir: Path to directory containing team_aliases.csv. Default: data/seeds
        out_dir: Path to directory for output Parquet file. Default: data/processed

    Returns:
        Number of rows written to team_normalization.parquet.

    Raises:
        FileNotFoundError: If MTeams.csv or team_aliases.csv is not found.
    """
    raw_path = pathlib.Path(raw_dir)
    seeds_path = pathlib.Path(seeds_dir)
    out_path = pathlib.Path(out_dir)

    mteams_csv = raw_path / "MTeams.csv"
    aliases_csv = seeds_path / "team_aliases.csv"
    out_parquet = out_path / "team_normalization.parquet"

    if not mteams_csv.exists():
        raise FileNotFoundError(f"MTeams.csv not found at {mteams_csv}")
    if not aliases_csv.exists():
        raise FileNotFoundError(f"team_aliases.csv not found at {aliases_csv}")

    out_path.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()

    # Step 1: Load MTeams.csv as the base — all teams get canonical_name = TeamName
    all_teams: pd.DataFrame = conn.execute(
        f"""
        SELECT
            TeamID          AS kaggle_team_id,
            TeamName        AS kaggle_name,
            FirstD1Season   AS first_d1_season,
            LastD1Season    AS last_d1_season
        FROM read_csv('{mteams_csv}')
        ORDER BY TeamID
        """
    ).df()

    # Step 2: Load hand-curated aliases (overrides for known conflicts)
    aliases: pd.DataFrame = conn.execute(
        f"""
        SELECT
            CAST(kaggle_team_id AS INTEGER) AS kaggle_team_id,
            canonical_name,
            kaggle_name         AS alias_kaggle_name,
            espn_name,
            sr_slug,
            cbbdata_name
        FROM read_csv('{aliases_csv}')
        """
    ).df()

    # Step 3: Merge — start with all teams, overlay alias data where present
    merged = all_teams.merge(aliases, on="kaggle_team_id", how="left")

    # canonical_name: use alias override if present, else default to kaggle_name from MTeams
    merged["canonical_name"] = merged["canonical_name"].where(
        merged["canonical_name"].notna() & (merged["canonical_name"] != ""),
        other=merged["kaggle_name"],
    )

    # Fill empty string for alias columns where no override was provided
    for col in ["espn_name", "sr_slug", "cbbdata_name"]:
        merged[col] = merged[col].fillna("").astype(str)
        # Replace "nan" string just in case
        merged[col] = merged[col].replace("nan", "")

    # espn_slug and ncaa_name are not in the seed CSV yet — add as empty placeholders
    merged["espn_slug"] = ""
    merged["ncaa_name"] = ""

    # Step 4: Select and order final columns
    result = merged[
        [
            "kaggle_team_id",
            "canonical_name",
            "kaggle_name",
            "espn_name",
            "espn_slug",
            "sr_slug",
            "cbbdata_name",
            "ncaa_name",
            "first_d1_season",
            "last_d1_season",
        ]
    ].copy()

    # Ensure correct dtypes
    result["kaggle_team_id"] = result["kaggle_team_id"].astype(int)
    result["first_d1_season"] = result["first_d1_season"].astype(int)
    result["last_d1_season"] = result["last_d1_season"].astype(int)

    # Step 5: Write to Parquet via DuckDB for consistency with rest of pipeline
    conn.register("normalization_df", result)
    conn.execute(
        f"""
        COPY normalization_df
        TO '{out_parquet}'
        (FORMAT parquet, COMPRESSION zstd)
        """
    )
    conn.close()

    row_count = len(result)
    return row_count


def verify_normalization_coverage(
    processed_dir: str = "data/processed",
) -> tuple[int, int, list[str]]:
    """Verify that every tournament team (2003-2025) has a normalization entry.

    Loads tournament_games.parquet to get all unique team IDs that appeared in
    2003-2025 tournament games, then checks that every ID is present in
    team_normalization.parquet.

    Args:
        processed_dir: Path to directory containing both Parquet files.
            Default: data/processed

    Returns:
        Tuple of (total_tournament_teams, matched_teams, list_of_unmatched_team_ids).
        total_tournament_teams: Count of unique TeamIDs in tournament games.
        matched_teams: Count that have a normalization entry.
        list_of_unmatched_team_ids: Team IDs missing from normalization table (empty = 100% coverage).

    Raises:
        FileNotFoundError: If tournament_games.parquet or team_normalization.parquet not found.
    """
    processed_path = pathlib.Path(processed_dir)
    tourney_parquet = processed_path / "tournament_games.parquet"
    norm_parquet = processed_path / "team_normalization.parquet"

    if not tourney_parquet.exists():
        raise FileNotFoundError(f"tournament_games.parquet not found at {tourney_parquet}")
    if not norm_parquet.exists():
        raise FileNotFoundError(f"team_normalization.parquet not found at {norm_parquet}")

    conn = duckdb.connect()

    # All unique team IDs that appeared as winner or loser in any tournament game
    tourney_teams: pd.DataFrame = conn.execute(
        f"""
        SELECT DISTINCT tid
        FROM (
            SELECT WTeamID AS tid
            FROM read_parquet('{tourney_parquet}')
            UNION
            SELECT LTeamID AS tid
            FROM read_parquet('{tourney_parquet}')
        )
        ORDER BY tid
        """
    ).df()

    total_tournament_teams = len(tourney_teams)

    # Find teams with no normalization entry
    unmatched: pd.DataFrame = conn.execute(
        f"""
        SELECT DISTINCT t.tid
        FROM (
            SELECT WTeamID AS tid FROM read_parquet('{tourney_parquet}')
            UNION
            SELECT LTeamID AS tid FROM read_parquet('{tourney_parquet}')
        ) t
        LEFT JOIN read_parquet('{norm_parquet}') n
            ON t.tid = n.kaggle_team_id
        WHERE n.kaggle_team_id IS NULL
        ORDER BY t.tid
        """
    ).df()

    conn.close()

    unmatched_ids = [str(tid) for tid in unmatched["tid"].tolist()]
    matched_count = total_tournament_teams - len(unmatched_ids)

    if unmatched_ids:
        print(
            f"WARNING: {len(unmatched_ids)} tournament team(s) have no normalization entry: "
            f"{unmatched_ids}"
        )

    return total_tournament_teams, matched_count, unmatched_ids


if __name__ == "__main__":
    import duckdb as _duckdb

    print("=== Building team normalization table ===")
    count = build_normalization_table()
    print(f"Written {count} teams to data/processed/team_normalization.parquet")

    print("\n=== Verifying normalization coverage ===")
    total, matched, unmatched = verify_normalization_coverage()
    print(f"Tournament teams: {total}")
    print(f"Matched:          {matched}")
    print(f"Unmatched:        {len(unmatched)}")

    if unmatched:
        print(f"FAIL — unmatched team IDs: {unmatched}")
    else:
        print("100% coverage!")

    print("\n=== First 20 entries ===")
    preview = _duckdb.sql(
        """
        SELECT kaggle_team_id, canonical_name, kaggle_name, espn_name, sr_slug
        FROM read_parquet('data/processed/team_normalization.parquet')
        ORDER BY kaggle_team_id
        LIMIT 20
        """
    ).df()
    print(preview.to_string())

    print("\n=== Teams with espn_name populated ===")
    has_espn = _duckdb.sql(
        """
        SELECT kaggle_team_id, canonical_name, kaggle_name, espn_name, sr_slug, cbbdata_name
        FROM read_parquet('data/processed/team_normalization.parquet')
        WHERE espn_name IS NOT NULL AND espn_name != ''
        ORDER BY canonical_name
        """
    ).df()
    print(f"Teams with espn_name: {len(has_espn)}")
    print(has_espn.to_string())
