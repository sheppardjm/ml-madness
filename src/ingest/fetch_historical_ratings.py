"""
Fetch historical Torvik efficiency ratings for all valid tournament seasons.

Retrieves per-team efficiency metrics (adjOE, adjDE, barthag, tempo, WAB) from
the cbbdata API for every season in VALID_TOURNEY_SEASONS (2003-2025, excl. 2020).
Joins results to team_normalization.parquet and writes a consolidated parquet file.

Output: data/processed/historical_torvik_ratings.parquet

Usage:
    uv run python -m src.ingest.fetch_historical_ratings
"""

from __future__ import annotations

import pathlib
import time
import warnings

import duckdb
import pandas as pd

from src.ingest.cbbdata_client import fetch_torvik_ratings, get_cbbdata_token
from src.utils.seasons import VALID_TOURNEY_SEASONS

PROCESSED_DIR = pathlib.Path("data/processed")
OUTPUT_PARQUET = PROCESSED_DIR / "historical_torvik_ratings.parquet"
NORM_PARQUET = PROCESSED_DIR / "team_normalization.parquet"

# Hard-coded overrides for cbbdata API team names that fuzzy-match incorrectly.
# These are cases where the cbbdata name does not match the canonical_name or
# cbbdata_name in team_normalization.parquet AND fuzzy matching picks the wrong team.
# Format: {cbbdata_api_name: correct_canonical_name_in_normalization}
CBBDATA_NAME_OVERRIDES: dict[str, str] = {
    # NC State: cbbdata sends "North Carolina St." in some seasons — fuzzy incorrectly
    # picks "North Carolina". The cbbdata_name in normalization is "N.C. State" which
    # handles most seasons; this override handles the alternate API name.
    "North Carolina St.": "NC State",
    # NC A&T: cbbdata sends "North Carolina A&T" — fuzzy incorrectly picks "North Carolina"
    "North Carolina A&T": "NC A&T",
    # College of Charleston: cbbdata sends "Charleston" in some seasons.
    # "College of Charleston" direct-matches via cbbdata_name; "Charleston" alone
    # would fuzzy to "Charleston So" (wrong school).
    "Charleston": "Col Charleston",
    # Saint Francis: cbbdata sends "Saint Francis" in recent seasons and "St. Francis PA"
    # in older seasons — both should map to St Francis PA (1384).
    # "Saint Francis" is now the cbbdata_name for 1384 (direct match for recent seasons).
    # "St. Francis PA" fuzzy matches at 77 (below threshold), so we override it here.
    "St. Francis PA": "St Francis PA",
}

# Columns to include in the output
OUTPUT_COLS = [
    "kaggle_team_id",
    "canonical_name",
    "cbbdata_name",
    "season",
    "barthag",
    "adj_o",
    "adj_d",
    "adj_t",
    "wab",
    "conf",
]


def _build_norm_lookups(
    norm_df: pd.DataFrame,
) -> tuple[dict, dict, dict]:
    """Build name-to-row lookup dicts from the normalization DataFrame."""
    cbd_name_to_row = {
        row["cbbdata_name"]: row
        for _, row in norm_df.iterrows()
        if row["cbbdata_name"]
    }
    canonical_name_to_row = {
        row["canonical_name"]: row
        for _, row in norm_df.iterrows()
    }
    kaggle_name_to_row = {
        row["kaggle_name"]: row
        for _, row in norm_df.iterrows()
    }
    return cbd_name_to_row, canonical_name_to_row, kaggle_name_to_row


def _match_team(
    team_name: str,
    cbd_name_to_row: dict,
    canonical_name_to_row: dict,
    kaggle_name_to_row: dict,
    has_fuzzy: bool,
    fuzzy_threshold: int = 85,
) -> tuple[object | None, bool]:
    """Multi-pass team name matching. Returns (norm_row_or_None, was_fuzzy_match).

    Pre-pass: check hard-coded overrides for known bad fuzzy matches (teams where
    the cbbdata API name would otherwise be routed to the wrong canonical team).
    """
    # Pre-pass: hard-coded overrides for known ambiguous/incorrect fuzzy matches
    override_canonical = CBBDATA_NAME_OVERRIDES.get(team_name)
    if override_canonical is not None:
        norm_row = canonical_name_to_row.get(override_canonical)
        if norm_row is not None:
            return norm_row, False

    # Pass 1: cbbdata_name
    norm_row = cbd_name_to_row.get(team_name)
    if norm_row is not None:
        return norm_row, False

    # Pass 2: canonical_name
    norm_row = canonical_name_to_row.get(team_name)
    if norm_row is not None:
        return norm_row, False

    # Pass 3: kaggle_name
    norm_row = kaggle_name_to_row.get(team_name)
    if norm_row is not None:
        return norm_row, False

    # Pass 4: fuzzy match
    if has_fuzzy:
        from thefuzz import fuzz  # type: ignore[import-untyped]  # noqa: PLC0415

        best_score = 0
        best_row = None
        for name, row in canonical_name_to_row.items():
            score = fuzz.token_sort_ratio(team_name, name)
            if score > best_score:
                best_score = score
                best_row = row
        if best_score >= fuzzy_threshold and best_row is not None:
            print(
                f"    Fuzzy match ({best_score}): '{team_name}' -> '{best_row['canonical_name']}'"
            )
            return best_row, True

    return None, False


def ingest_historical_ratings(
    api_key: str,
    output_path: str | pathlib.Path = OUTPUT_PARQUET,
    processed_dir: str | pathlib.Path = PROCESSED_DIR,
) -> pd.DataFrame:
    """Fetch historical Torvik ratings for all tournament seasons and write parquet.

    Loops over every season in VALID_TOURNEY_SEASONS, calls fetch_torvik_ratings()
    with archive_year_override=season (ensures correct archive year for historical
    data), and joins results to team_normalization for kaggle_team_id resolution.

    Args:
        api_key: API key from get_cbbdata_token().
        output_path: Destination parquet file path.
        processed_dir: Directory containing team_normalization.parquet.

    Returns:
        Consolidated DataFrame written to output_path.

    Raises:
        FileNotFoundError: If team_normalization.parquet is not found.
    """
    processed_path = pathlib.Path(processed_dir)
    output_path = pathlib.Path(output_path)
    norm_parquet = processed_path / "team_normalization.parquet"

    if not norm_parquet.exists():
        raise FileNotFoundError(f"team_normalization.parquet not found at {norm_parquet}")

    # Load normalization table
    conn = duckdb.connect()
    norm_df = conn.execute(f"SELECT * FROM read_parquet('{norm_parquet}')").df()
    conn.close()

    cbd_name_to_row, canonical_name_to_row, kaggle_name_to_row = _build_norm_lookups(norm_df)

    try:
        from thefuzz import fuzz as _fuzz  # type: ignore[import-untyped]  # noqa: PLC0415, F401
        has_fuzzy = True
    except ImportError:
        has_fuzzy = False
        warnings.warn("thefuzz not installed — fuzzy matching disabled", stacklevel=2)

    all_season_dfs: list[pd.DataFrame] = []
    succeeded_seasons: list[int] = []
    skipped_seasons: list[int] = []

    print(f"Fetching historical Torvik ratings for {len(VALID_TOURNEY_SEASONS)} seasons...")
    print(f"Seasons: {VALID_TOURNEY_SEASONS[0]}-{VALID_TOURNEY_SEASONS[-1]} (excl. 2020)\n")

    for i, season in enumerate(VALID_TOURNEY_SEASONS):
        print(f"[{i+1}/{len(VALID_TOURNEY_SEASONS)}] Fetching season {season}...")

        try:
            # Use archive_year_override=season for historical years so the archive
            # fallback queries the correct year (not season-1).
            ratings = fetch_torvik_ratings(api_key, year=season, archive_year_override=season)

            if ratings is None or len(ratings) == 0:
                warnings.warn(f"  Season {season}: returned empty DataFrame — skipping", stacklevel=2)
                skipped_seasons.append(season)
                continue

            # Normalize column names (archive may use different names)
            if "adj_tempo" in ratings.columns and "adj_t" not in ratings.columns:
                ratings = ratings.rename(columns={"adj_tempo": "adj_t"})
            if "wins_above_bubble" in ratings.columns and "wab" not in ratings.columns:
                ratings = ratings.rename(columns={"wins_above_bubble": "wab"})

            # Add season column
            ratings = ratings.copy()
            ratings["season"] = season

            all_season_dfs.append(ratings)
            succeeded_seasons.append(season)
            print(f"  Season {season}: {len(ratings)} teams")

        except Exception as exc:
            warnings.warn(f"  Season {season}: failed with {type(exc).__name__}: {exc} — skipping", stacklevel=2)
            skipped_seasons.append(season)
            continue

        # Rate limiting: 1 second between API calls
        if i < len(VALID_TOURNEY_SEASONS) - 1:
            time.sleep(1)

    if not all_season_dfs:
        raise ValueError("No season data was successfully fetched. Check API credentials and connectivity.")

    print(f"\nSuccessfully fetched: {len(succeeded_seasons)} seasons ({succeeded_seasons[0]}-{succeeded_seasons[-1]})")
    if skipped_seasons:
        print(f"Skipped seasons: {skipped_seasons}")

    # Concatenate all seasons
    combined = pd.concat(all_season_dfs, ignore_index=True)
    print(f"Total rows before matching: {len(combined)}")

    # --- Join to team_normalization for kaggle_team_id ---
    output_rows = []
    unmatched_names: set[str] = set()
    matched_count = 0

    for _, r in combined.iterrows():
        team_name = str(r.get("team", ""))

        norm_row, _ = _match_team(
            team_name,
            cbd_name_to_row,
            canonical_name_to_row,
            kaggle_name_to_row,
            has_fuzzy,
        )

        if norm_row is None:
            unmatched_names.add(team_name)

        output_row = {
            "kaggle_team_id": int(norm_row["kaggle_team_id"]) if norm_row is not None else None,
            "canonical_name": norm_row["canonical_name"] if norm_row is not None else team_name,
            "cbbdata_name": team_name,
            "season": int(r["season"]),
            "barthag": float(r["barthag"]) if pd.notna(r.get("barthag")) else None,
            "adj_o": float(r["adj_o"]) if pd.notna(r.get("adj_o")) else None,
            "adj_d": float(r["adj_d"]) if pd.notna(r.get("adj_d")) else None,
            "adj_t": float(r.get("adj_t", None)) if pd.notna(r.get("adj_t")) else None,
            "wab": float(r.get("wab", None)) if pd.notna(r.get("wab")) else None,
            "conf": str(r.get("conf", "")) if r.get("conf") is not None else "",
        }
        output_rows.append(output_row)

        if norm_row is not None:
            matched_count += 1

    out_df = pd.DataFrame(output_rows)

    total = len(out_df)
    unmatched_count = total - matched_count
    match_pct = 100 * matched_count / total if total > 0 else 0
    print(f"\nMatching: {matched_count}/{total} teams matched ({match_pct:.1f}%)")
    if unmatched_names:
        print(f"Unmatched teams (sample): {list(unmatched_names)[:20]}")

    # Ensure output columns are present
    for col in OUTPUT_COLS:
        if col not in out_df.columns:
            out_df[col] = None

    out_df = out_df[OUTPUT_COLS]

    # Write to parquet via DuckDB
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_conn = duckdb.connect()
    write_conn.register("hist_df", out_df)
    write_conn.execute(
        f"COPY hist_df TO '{output_path}' (FORMAT parquet, COMPRESSION zstd)"
    )
    write_conn.close()

    # --- Summary ---
    print(f"\nWrote {len(out_df)} rows to {output_path}")
    print(f"Seasons covered: {sorted(out_df['season'].unique())}")

    # Print per-season summary
    summary_conn = duckdb.connect()
    summary = summary_conn.execute(
        f"""
        SELECT season,
               COUNT(*) AS teams,
               ROUND(AVG(barthag), 3) AS avg_barthag,
               SUM(CASE WHEN kaggle_team_id IS NULL THEN 1 ELSE 0 END) AS null_ids
        FROM read_parquet('{output_path}')
        GROUP BY season
        ORDER BY season
        """
    ).df()
    summary_conn.close()
    print("\nPer-season summary:")
    print(summary.to_string(index=False))

    return out_df


if __name__ == "__main__":
    api_key = get_cbbdata_token()
    print("Authenticated successfully.\n")

    result = ingest_historical_ratings(api_key)

    print(f"\nFinal shape: {result.shape}")
    print(f"Columns: {result.columns.tolist()}")

    # Verify the output
    verify_conn = duckdb.connect()
    df_check = verify_conn.execute(
        """
        SELECT season,
               COUNT(*) AS n,
               ROUND(AVG(barthag), 3) AS avg_b,
               SUM(CASE WHEN kaggle_team_id IS NULL THEN 1 ELSE 0 END) AS null_ids
        FROM read_parquet('data/processed/historical_torvik_ratings.parquet')
        GROUP BY season
        ORDER BY season
        """
    ).df()
    verify_conn.close()

    print("\nVerification query:")
    print(df_check)
    assert len(df_check) >= 10, f"Only {len(df_check)} seasons — expected 10+"
    print("\nVerification passed.")
