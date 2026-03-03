"""
cbbdata REST API client for fetching college basketball efficiency metrics.

Provides authenticated access to the cbbdata API (cbbdata.com) to fetch:
  - Torvik ratings (adjOE, adjDE, barthag) for efficiency-based team metrics
  - Teams dictionary with ESPN IDs and slugs for cross-source name matching

Auth: Register at https://www.cbbdata.com/api/auth/register
      Set CBD_USERNAME and CBD_PASSWORD environment variables before using.

Usage:
    uv run python -m src.ingest.cbbdata_client
"""

from __future__ import annotations

import os
import pathlib
from io import BytesIO

import duckdb
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CBD_BASE_URL = "https://www.cbbdata.com/api"


def _make_session() -> requests.Session:
    """Create a requests Session with retry logic for transient failures."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_cbbdata_token(
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Authenticate with the cbbdata API and return an API key.

    If username/password are not provided, reads from CBD_USERNAME and
    CBD_PASSWORD environment variables.

    Args:
        username: cbbdata account username. Falls back to CBD_USERNAME env var.
        password: cbbdata account password. Falls back to CBD_PASSWORD env var.

    Returns:
        API key string for use in subsequent requests.

    Raises:
        ValueError: If credentials are not provided and env vars are not set.
        requests.HTTPError: If authentication fails (invalid credentials).
    """
    if username is None:
        username = os.environ.get("CBD_USERNAME")
    if password is None:
        password = os.environ.get("CBD_PASSWORD")

    if not username or not password:
        raise ValueError(
            "cbbdata credentials not found. Provide username/password arguments or "
            "set CBD_USERNAME and CBD_PASSWORD environment variables. "
            "Register at: https://www.cbbdata.com/api/auth/register"
        )

    session = _make_session()
    response = session.post(
        f"{CBD_BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()

    # Response is a JSON dict with "api_key" key (current API format).
    # Earlier documentation described a list format; handle both for robustness.
    data = response.json()
    if isinstance(data, dict):
        api_key = data.get("api_key") or data.get("key") or data.get("token")
        if not api_key:
            raise ValueError(f"Unexpected login response format: {list(data.keys())}")
    elif isinstance(data, list):
        api_key = data[0]
    else:
        raise ValueError(f"Unexpected login response type: {type(data)}")
    return api_key


def fetch_torvik_ratings(
    api_key: str,
    year: int = 2026,
    archive_year_override: int | None = None,
) -> pd.DataFrame:
    """Fetch Torvik adjusted efficiency ratings from the cbbdata API.

    Attempts the year-end ratings endpoint first. If that endpoint returns no
    valid data (e.g., the current season is not yet indexed), falls back to
    the daily ratings archive for the most recent available pre-Selection-Sunday
    snapshot of the preceding season.

    Note: As of 2026-03, cbbdata's ratings endpoint only has complete year-end
    data through year=2024. Year=2025 returns rows without barthag populated.
    Year=2026 (2025-26 season) returns empty. The archive endpoint is used as
    a fallback to get the best available data.

    Args:
        api_key: API key from get_cbbdata_token().
        year: Season year (e.g., 2026 for the 2025-26 season). Default: 2026.
        archive_year_override: When provided, use this value as the archive
            fallback year instead of ``year - 1``. This is useful for historical
            seasons (2003–2024) where the archive should be queried with the
            season year itself, not the preceding year. Default: None (uses
            ``year - 1`` as the archive year, correct for the current season).

    Returns:
        DataFrame with columns: team, conf, barthag, adj_o, adj_d, adj_t,
        wab, year, and various rank columns. When using archive fallback,
        also includes a 'source_date' column indicating the snapshot date.

    Raises:
        requests.HTTPError: If the API request fails.
        ValueError: If no data can be found for the given year or any fallback.
    """
    import datetime as _dt  # noqa: PLC0415

    session = _make_session()

    # --- Primary: try year-end ratings endpoint ---
    response = session.get(
        f"{CBD_BASE_URL}/torvik/ratings",
        params={"key": api_key, "year": year},
        timeout=60,
    )
    response.raise_for_status()
    df = pd.read_parquet(BytesIO(response.content))

    # Check if data has valid barthag values (not all-null)
    if len(df) > 0 and df["barthag"].notna().any():
        print(f"  Fetched {len(df)} teams from year-end ratings (year={year})")
        return df

    # --- Fallback: daily archive for most recent pre-Selection-Sunday snapshot ---
    # The archive tracks day-by-day ratings during the season.
    # For a given year, find the latest date at or before Selection Sunday.
    # For historical seasons, archive_year_override allows using the season year
    # itself (not year-1) since the tournament-end archive exists for that year.
    if archive_year_override is not None:
        fallback_year = archive_year_override
    else:
        fallback_year = year - 1  # E.g., 2025 for 2025-26 season missing
    print(
        f"  Year-end ratings unavailable for year={year} (empty or no barthag). "
        f"Falling back to archive for year={fallback_year}..."
    )

    archive_response = session.get(
        f"{CBD_BASE_URL}/torvik/ratings/archive",
        params={"key": api_key, "year": fallback_year},
        timeout=60,
    )
    archive_response.raise_for_status()
    archive_df = pd.read_parquet(BytesIO(archive_response.content))

    if len(archive_df) == 0:
        raise ValueError(
            f"No ratings data available for year={year} or archive year={fallback_year}. "
            "cbbdata may not have current season data yet."
        )

    # Pick the latest available date (ideally at or before Selection Sunday)
    # Selection Sunday for fallback_year
    from src.utils.cutoff_dates import SELECTION_SUNDAY_DATES  # noqa: PLC0415
    selection_sunday_str = SELECTION_SUNDAY_DATES.get(fallback_year)
    if selection_sunday_str:
        ss_date = _dt.date.fromisoformat(selection_sunday_str)
        available_dates = sorted(archive_df["date"].unique())
        # Find latest date at or before Selection Sunday
        pre_ss_dates = [d for d in available_dates if d <= ss_date]
        target_date = max(pre_ss_dates) if pre_ss_dates else max(available_dates)
    else:
        target_date = archive_df["date"].max()

    snapshot = archive_df[archive_df["date"] == target_date].copy()
    snapshot["source_date"] = str(target_date)
    # Rename archive columns to match year-end ratings schema where needed
    if "adj_tempo" in snapshot.columns and "adj_t" not in snapshot.columns:
        snapshot = snapshot.rename(columns={"adj_tempo": "adj_t"})
    if "wins_above_bubble" in snapshot.columns and "wab" not in snapshot.columns:
        snapshot = snapshot.rename(columns={"wins_above_bubble": "wab"})

    print(
        f"  Using archive snapshot for {fallback_year} on {target_date}: "
        f"{len(snapshot)} teams (NOTE: this is previous-season data, not {year})"
    )
    return snapshot


def fetch_cbbdata_teams() -> pd.DataFrame:
    """Fetch the cbbdata teams dictionary (no authentication required).

    Returns team metadata including ESPN IDs, slugs, and display names
    useful for cross-source name matching.

    Returns:
        DataFrame with ESPN-related columns and team identifiers.

    Raises:
        requests.HTTPError: If the API request fails.
    """
    session = _make_session()
    response = session.get(
        f"{CBD_BASE_URL}/data/teams",
        timeout=30,
    )
    response.raise_for_status()

    # Response is raw Parquet bytes, NOT JSON
    df = pd.read_parquet(BytesIO(response.content))
    return df


def ingest_current_season_stats(
    api_key: str,
    year: int = 2026,
    processed_dir: str = "data/processed",
) -> int:
    """Fetch 2025-26 Torvik efficiency ratings and write to current_season_stats.parquet.

    Joins cbbdata ratings to the team normalization table (by cbbdata_name or
    canonical_name) so every output row carries a kaggle_team_id where possible.
    All D1 teams with ratings are included — downstream phases filter to
    tournament teams when building features.

    Args:
        api_key: API key from get_cbbdata_token().
        year: Season year. Default: 2026.
        processed_dir: Directory containing team_normalization.parquet and
            where current_season_stats.parquet will be written. Default: data/processed.

    Returns:
        Number of rows written to current_season_stats.parquet.

    Raises:
        FileNotFoundError: If team_normalization.parquet does not exist.
    """
    processed_path = pathlib.Path(processed_dir)
    norm_parquet = processed_path / "team_normalization.parquet"
    out_parquet = processed_path / "current_season_stats.parquet"

    if not norm_parquet.exists():
        raise FileNotFoundError(f"team_normalization.parquet not found at {norm_parquet}")

    # Fetch ratings from cbbdata API
    print(f"Fetching Torvik ratings for year={year}...")
    ratings = fetch_torvik_ratings(api_key, year)
    print(f"Fetched {len(ratings)} team ratings. Columns: {ratings.columns.tolist()}")

    # Load normalization table
    conn = duckdb.connect()
    norm_df = conn.execute(
        f"SELECT * FROM read_parquet('{norm_parquet}')"
    ).df()
    conn.close()

    # --- Name matching: join ratings to normalization table ---
    # Build lookup dicts for fast matching
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

    # Third-pass: fuzzy matching for remaining teams
    try:
        from thefuzz import fuzz  # type: ignore[import-untyped]
        has_fuzzy = True
    except ImportError:
        has_fuzzy = False
        print("WARNING: thefuzz not installed — fuzzy matching disabled")

    output_rows = []
    matched = 0
    unmatched_names = []

    for _, r in ratings.iterrows():
        team_name = r["team"]

        # Primary: match via cbbdata_name column in normalization
        norm_row = cbd_name_to_row.get(team_name)

        # Secondary: match via canonical_name
        if norm_row is None:
            norm_row = canonical_name_to_row.get(team_name)

        # Tertiary: match via kaggle_name
        if norm_row is None:
            norm_row = kaggle_name_to_row.get(team_name)

        # Fourth: fuzzy match
        if norm_row is None and has_fuzzy:
            best_score = 0
            best_row = None
            for name, row in canonical_name_to_row.items():
                score = fuzz.token_sort_ratio(team_name, name)
                if score > best_score:
                    best_score = score
                    best_row = row
            if best_score >= 85 and best_row is not None:
                norm_row = best_row
                print(
                    f"  Fuzzy match ({best_score}): cbbdata='{team_name}' -> canonical='{best_row['canonical_name']}'"
                )
            else:
                if best_row is not None:
                    print(
                        f"  WARNING: No match for '{team_name}' (best fuzzy: '{best_row['canonical_name']}' at {best_score})"
                    )
                else:
                    print(f"  WARNING: No match found for '{team_name}'")
                unmatched_names.append(team_name)

        if norm_row is None:
            unmatched_names.append(team_name)

        # Build output row — always include, kaggle_team_id = None if unmatched
        output_row = {
            "kaggle_team_id": int(norm_row["kaggle_team_id"]) if norm_row is not None else None,
            "canonical_name": norm_row["canonical_name"] if norm_row is not None else team_name,
            "cbbdata_name": team_name,
            "conf": r.get("conf", ""),
            "barthag": float(r["barthag"]) if pd.notna(r.get("barthag")) else None,
            "adj_o": float(r["adj_o"]) if pd.notna(r.get("adj_o")) else None,
            "adj_d": float(r["adj_d"]) if pd.notna(r.get("adj_d")) else None,
            "adj_t": float(r["adj_t"]) if pd.notna(r.get("adj_t")) else None,
            "wab": float(r["wab"]) if pd.notna(r.get("wab")) else None,
            "year": int(r["year"]) if pd.notna(r.get("year")) else year,
        }
        output_rows.append(output_row)

        if norm_row is not None:
            matched += 1

    total = len(output_rows)
    print(f"\nMatching summary: {matched}/{total} teams matched to normalization table")
    if unmatched_names:
        print(f"Unmatched teams ({len(unmatched_names)}): {unmatched_names}")

    # Build output DataFrame
    out_df = pd.DataFrame(output_rows)

    # Write to Parquet via DuckDB
    processed_path.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect()
    conn.register("stats_df", out_df)
    conn.execute(
        f"""
        COPY stats_df
        TO '{out_parquet}'
        (FORMAT parquet, COMPRESSION zstd)
        """
    )
    conn.close()

    # Print summary stats
    print(f"\nWrote {len(out_df)} rows to {out_parquet}")
    if "barthag" in out_df.columns and out_df["barthag"].notna().any():
        print(f"barthag: mean={out_df['barthag'].mean():.4f}, std={out_df['barthag'].std():.4f}")
        top10 = out_df.dropna(subset=["barthag", "kaggle_team_id"]).nlargest(10, "barthag")[
            ["canonical_name", "barthag", "adj_o", "adj_d"]
        ]
        print("\nTop 10 teams by barthag:")
        print(top10.to_string(index=False))

    return len(out_df)


if __name__ == "__main__":
    key = get_cbbdata_token()
    print(f"Authenticated successfully.")

    # Quick validation
    ratings = fetch_torvik_ratings(key, 2026)
    print(f"Ratings shape: {ratings.shape}")
    print(ratings.head(5))

    teams = fetch_cbbdata_teams()
    print(f"\nTeams shape: {teams.shape}")
    print(f"Columns: {teams.columns.tolist()}")

    # Full ingest
    count = ingest_current_season_stats(key)
    print(f"\nIngested {count} team stats to current_season_stats.parquet")
