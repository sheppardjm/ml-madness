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


def update_normalization_with_cbbdata(
    processed_dir: str = "data/processed",
    seeds_dir: str = "data/seeds",
) -> tuple[int, int]:
    """Update team_normalization.parquet with cbbdata names and ESPN slugs.

    Fetches the cbbdata teams dictionary (no auth required) and matches it to
    the existing normalization table. For matched teams, populates:
      - cbbdata_name (if currently empty)
      - espn_slug (from cbbdata's ESPN column)

    Matching strategy (in priority order):
      1. Exact match: canonical_name == cbbdata torvik_team
      2. Seed match: existing cbbdata_name == cbbdata torvik_team (59 known aliases)
      3. Exact match: kaggle_name == cbbdata torvik_team
      4. Fuzzy match (thefuzz token_sort_ratio, threshold >= 85) — logs candidates

    Args:
        processed_dir: Path to directory containing team_normalization.parquet.
        seeds_dir: Path to seeds directory (for logging fuzzy match candidates).

    Returns:
        Tuple of (total_matched, total_unmatched).
    """
    from src.ingest.cbbdata_client import fetch_cbbdata_teams  # noqa: PLC0415

    processed_path = pathlib.Path(processed_dir)
    norm_parquet = processed_path / "team_normalization.parquet"

    if not norm_parquet.exists():
        raise FileNotFoundError(f"team_normalization.parquet not found at {norm_parquet}")

    # Load existing normalization table
    conn = duckdb.connect()
    norm_df: pd.DataFrame = conn.execute(
        f"SELECT * FROM read_parquet('{norm_parquet}')"
    ).df()
    conn.close()

    # Fetch cbbdata teams dictionary
    cbb_teams = fetch_cbbdata_teams()
    # Key columns: torvik_team (name), espn_slug, espn_display
    cbb_teams = cbb_teams[["torvik_team", "espn_slug", "espn_display"]].copy()

    # Build lookup dict: torvik_team -> (espn_slug, espn_display)
    torvik_lookup: dict[str, dict] = {
        row["torvik_team"]: {"espn_slug": row["espn_slug"], "espn_display": row["espn_display"]}
        for _, row in cbb_teams.iterrows()
    }

    # Fuzzy matching fallback
    try:
        from thefuzz import fuzz  # type: ignore[import-untyped]
        has_fuzzy = True
    except ImportError:
        has_fuzzy = False
        print("WARNING: thefuzz not installed — fuzzy matching disabled")

    torvik_names = list(torvik_lookup.keys())

    def _is_ambiguous_match(canonical: str, torvik: str) -> bool:
        """Return True if this fuzzy match is likely a false positive.

        Guards against:
        1. Abbreviated Kaggle names like 'E Illinois' matching 'Illinois' when
           'Eastern Illinois' is a separate cbbdata entry.
        2. Directional variants like 'West Georgia' matching 'Georgia St.' —
           the first significant word differs, so it's not the same program.
        """
        c_tokens = canonical.strip().split()
        t_tokens = torvik.rstrip(".").strip().split()

        if not c_tokens or not t_tokens:
            return False

        # Guard 1: directional prefix abbreviation (single letter + rest = torvik)
        directional = {"E", "N", "S", "W", "C", "NE", "SE", "SW", "NW"}
        if len(c_tokens) > 1 and c_tokens[0] in directional:
            remainder = c_tokens[1:]
            if remainder == t_tokens or remainder == [t.rstrip(".") for t in t_tokens]:
                return True

        # Guard 2: leading word completely differs (not just abbreviation)
        # e.g. "West Georgia" vs "Georgia St." — first nouns are "West" vs "Georgia"
        # If canonical has a directional word like West/East as first token and torvik
        # doesn't have that word at all, they're different schools
        directional_words = {"west", "east", "north", "south", "central", "northern",
                             "southern", "eastern", "western"}
        c_first = c_tokens[0].lower()
        t_all_lower = {tok.lower().rstrip(".") for tok in t_tokens}
        if c_first in directional_words and c_first not in t_all_lower:
            # The canonical name starts with a direction that torvik doesn't have
            # This is likely a different school
            return True

        return False

    def fuzzy_find(name: str) -> tuple[str | None, int]:
        """Find best fuzzy match in torvik_names, returns (match, score).

        Uses token_sort_ratio as primary, but filters out ambiguous matches
        where a short Kaggle name (e.g. 'E Illinois') would match a shorter cbbdata name
        (e.g. 'Illinois'), or where a directional variant (e.g. 'West Georgia') would
        match the wrong school (e.g. 'Georgia St.').
        """
        best_score = 0
        best_name = None
        for tname in torvik_names:
            score = fuzz.token_sort_ratio(name, tname)
            if score > best_score:
                # Guard: skip if this looks like an ambiguous false positive
                if _is_ambiguous_match(name, tname):
                    continue
                best_score = score
                best_name = tname
        return best_name, best_score

    matched = 0
    unmatched = 0
    fuzzy_candidates = []

    for idx, row in norm_df.iterrows():
        canonical = row["canonical_name"]
        kaggle = row["kaggle_name"]
        existing_cbbname = row["cbbdata_name"] if row["cbbdata_name"] else ""

        # Pass 1: canonical_name exact match
        cbb_entry = torvik_lookup.get(canonical)

        # Pass 2: existing cbbdata_name match
        if cbb_entry is None and existing_cbbname:
            cbb_entry = torvik_lookup.get(existing_cbbname)

        # Pass 3: kaggle_name exact match
        if cbb_entry is None:
            cbb_entry = torvik_lookup.get(kaggle)

        # Pass 4: fuzzy match
        if cbb_entry is None and has_fuzzy:
            best_name, best_score = fuzzy_find(canonical)
            if best_score >= 85 and best_name:
                cbb_entry = torvik_lookup[best_name]
                print(
                    f"  Fuzzy match ({best_score}): canonical='{canonical}' -> torvik='{best_name}'"
                )
                fuzzy_candidates.append({
                    "canonical_name": canonical,
                    "matched_torvik": best_name,
                    "score": best_score,
                })
            elif best_name and best_score >= 70:
                # Below threshold — log for human review but don't apply
                print(
                    f"  LOW fuzzy ({best_score}): '{canonical}' -> '{best_name}' [skipped, below 85]"
                )

        if cbb_entry is not None:
            # Update cbbdata_name if currently empty
            if not existing_cbbname:
                # Find which torvik name matched
                # Re-run matching to get the key
                matched_key = None
                if canonical in torvik_lookup:
                    matched_key = canonical
                elif existing_cbbname and existing_cbbname in torvik_lookup:
                    matched_key = existing_cbbname
                elif kaggle in torvik_lookup:
                    matched_key = kaggle
                else:
                    # Fuzzy — find it again
                    for tname, entry in torvik_lookup.items():
                        if entry is cbb_entry:
                            matched_key = tname
                            break
                if matched_key:
                    norm_df.at[idx, "cbbdata_name"] = matched_key

            # Always populate espn_slug if empty
            if not row["espn_slug"]:
                norm_df.at[idx, "espn_slug"] = cbb_entry["espn_slug"]

            matched += 1
        else:
            unmatched += 1

    # Write updated normalization table back to Parquet
    conn = duckdb.connect()
    conn.register("norm_updated", norm_df)
    conn.execute(
        f"""
        COPY norm_updated
        TO '{norm_parquet}'
        (FORMAT parquet, COMPRESSION zstd)
        """
    )
    conn.close()

    print(f"\nNormalization update complete:")
    print(f"  Matched:   {matched}")
    print(f"  Unmatched: {unmatched}")
    if fuzzy_candidates:
        print(f"  Fuzzy matches applied ({len(fuzzy_candidates)}):")
        for fc in fuzzy_candidates:
            print(f"    '{fc['canonical_name']}' -> '{fc['matched_torvik']}' (score={fc['score']})")

    return matched, unmatched


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

    print("\n=== Updating normalization with cbbdata names and ESPN slugs ===")
    cbd_matched, cbd_unmatched = update_normalization_with_cbbdata()
    print(f"cbbdata update: {cbd_matched} matched, {cbd_unmatched} unmatched")

    print("\n=== Coverage after cbbdata update ===")
    coverage = _duckdb.sql(
        """
        SELECT
            COUNT(*) FILTER (WHERE espn_slug != '') as has_espn_slug,
            COUNT(*) FILTER (WHERE cbbdata_name != '') as has_cbbdata_name,
            COUNT(*) as total
        FROM read_parquet('data/processed/team_normalization.parquet')
        """
    ).df()
    print(coverage.to_string(index=False))

    print("\n=== First 20 entries ===")
    preview = _duckdb.sql(
        """
        SELECT kaggle_team_id, canonical_name, kaggle_name, cbbdata_name, espn_slug
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
