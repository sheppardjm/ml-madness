"""
Feature engineering for NCAA tournament matchup prediction.

Provides functions to compute differential efficiency features for any team
pair in any historical season, and to assemble a flat matchup dataset suitable
for supervised learning models.

Feature computation is inline (dict-based lookup) rather than SQL for performance
when iterating over thousands of matchups in walk-forward cross-validation.

Exports:
    FEATURE_COLS          - Ordered list of 6 feature column names
    compute_features()    - Compute differential features for a single matchup
    build_stats_lookup()  - Load all team/season stats into a fast lookup dict
    build_matchup_dataset() - Assemble full training DataFrame from tournament games
"""

from __future__ import annotations

import pathlib
import warnings
from typing import Any

import duckdb
import pandas as pd

# Ordered list of feature column names used throughout the modeling pipeline.
# Team A is always the lower-seeded team (better seed = lower SeedNum).
# Each feature is team_a_stat - team_b_stat:
#   adjoe_diff  - Adjusted offensive efficiency differential
#   adjde_diff  - Adjusted defensive efficiency differential (positive = worse defense)
#   barthag_diff - Power rating differential (higher = better)
#   seed_diff   - Seed number differential (positive = team_a is higher seed number = worse seed)
#   adjt_diff   - Adjusted tempo differential
#   wab_diff    - Wins above bubble differential
FEATURE_COLS: list[str] = [
    "adjoe_diff",
    "adjde_diff",
    "barthag_diff",
    "seed_diff",
    "adjt_diff",
    "wab_diff",
]


def compute_features(
    season: int,
    team_a_id: int,
    team_b_id: int,
    stats_lookup: dict[tuple[int, int], dict[str, Any]],
) -> dict[str, float]:
    """Compute differential efficiency features for a single matchup.

    Computes team_a_stat - team_b_stat for each efficiency metric. The canonical
    ordering (team_a = lower SeedNum = better seed) is set by the caller; this
    function only performs the arithmetic.

    Note on adjde_diff: Lower adj_d means better defense (fewer points allowed).
    A positive adjde_diff means team_a has a *higher* (worse) defensive rating.
    The logistic regression model will learn the correct sign from the training data.

    Args:
        season: Tournament season year (e.g., 2023).
        team_a_id: Kaggle team ID for team A (canonical = lower SeedNum).
        team_b_id: Kaggle team ID for team B.
        stats_lookup: Dict keyed by (season, kaggle_team_id) containing stat dicts
            with keys: adj_o, adj_d, barthag, adj_t, wab, seed_num.

    Returns:
        Dict with keys matching FEATURE_COLS: adjoe_diff, adjde_diff, barthag_diff,
        seed_diff, adjt_diff, wab_diff.

    Raises:
        KeyError: If either team is missing from stats_lookup for the given season.
    """
    key_a = (season, team_a_id)
    key_b = (season, team_b_id)

    if key_a not in stats_lookup:
        raise KeyError(
            f"Team {team_a_id} not found in stats_lookup for season {season}. "
            f"Check that historical_torvik_ratings.parquet covers this team/season."
        )
    if key_b not in stats_lookup:
        raise KeyError(
            f"Team {team_b_id} not found in stats_lookup for season {season}. "
            f"Check that historical_torvik_ratings.parquet covers this team/season."
        )

    stats_a = stats_lookup[key_a]
    stats_b = stats_lookup[key_b]

    return {
        "adjoe_diff": stats_a["adj_o"] - stats_b["adj_o"],
        "adjde_diff": stats_a["adj_d"] - stats_b["adj_d"],
        "barthag_diff": stats_a["barthag"] - stats_b["barthag"],
        "seed_diff": stats_a["seed_num"] - stats_b["seed_num"],
        "adjt_diff": stats_a["adj_t"] - stats_b["adj_t"],
        "wab_diff": stats_a["wab"] - stats_b["wab"],
    }


def build_stats_lookup(
    processed_dir: str | pathlib.Path = "data/processed",
) -> dict[tuple[int, int], dict[str, Any]]:
    """Build a fast in-memory stats lookup dict from historical and current season data.

    Reads historical_torvik_ratings.parquet (2008-2025 seasons) and merges with
    seeds.parquet to add seed_num for tournament teams. For 2025, also merges
    current_season_stats.parquet (Phase 2 output) to get the freshest data.

    The lookup dict is keyed by (season, kaggle_team_id) and contains only teams
    with valid kaggle_team_id values. Non-tournament teams are included (they have
    no seed_num and will raise KeyError if queried in compute_features).

    Note: current_season_stats.parquet uses column name 'year' (not 'season').
    This function handles the rename transparently.

    Args:
        processed_dir: Directory containing the .parquet files. Default: data/processed

    Returns:
        Dict mapping (season, kaggle_team_id) -> {'adj_o', 'adj_d', 'barthag',
        'adj_t', 'wab', 'seed_num'} for all teams with valid stats.
    """
    processed_path = pathlib.Path(processed_dir)
    hist_parquet = processed_path / "historical_torvik_ratings.parquet"
    seeds_parquet = processed_path / "seeds.parquet"
    current_parquet = processed_path / "current_season_stats.parquet"

    if not hist_parquet.exists():
        raise FileNotFoundError(
            f"historical_torvik_ratings.parquet not found at {hist_parquet}. "
            "Run src/ingest/fetch_historical_ratings.py first."
        )
    if not seeds_parquet.exists():
        raise FileNotFoundError(
            f"seeds.parquet not found at {seeds_parquet}. "
            "Run Phase 1 tournament data ingestion first."
        )

    conn = duckdb.connect()

    # Load historical ratings — all seasons (2008-2025 typically)
    hist_df = conn.execute(
        f"SELECT kaggle_team_id, season, barthag, adj_o, adj_d, adj_t, wab "
        f"FROM read_parquet('{hist_parquet}') "
        f"WHERE kaggle_team_id IS NOT NULL"
    ).df()

    # Load seeds for seed_num lookup
    seeds_df = conn.execute(
        f"SELECT TeamID AS kaggle_team_id, Season AS season, SeedNum AS seed_num "
        f"FROM read_parquet('{seeds_parquet}')"
    ).df()

    conn.close()

    # For 2025: overlay current_season_stats.parquet for fresher stats.
    # current_season_stats may not cover all tournament teams (e.g., First Four
    # play-in teams like St. Francis PA may be absent from the cbbdata snapshot).
    # Use current stats as the primary source for teams it covers, but preserve
    # historical 2025 rows for teams NOT present in current_season_stats.
    if current_parquet.exists():
        conn2 = duckdb.connect()
        current_df = conn2.execute(
            f"SELECT kaggle_team_id, year AS season, barthag, adj_o, adj_d, adj_t, wab "
            f"FROM read_parquet('{current_parquet}') "
            f"WHERE kaggle_team_id IS NOT NULL"
        ).df()
        conn2.close()

        # Determine which teams are covered in current_season_stats for 2025
        current_2025_ids = set(current_df["kaggle_team_id"].dropna().astype(int).tolist())

        # Keep: (a) all non-2025 historical rows, and
        #        (b) 2025 historical rows for teams NOT in current_season_stats
        # Then add all current_season_stats rows (the freshest data for covered teams)
        hist_no_2025 = hist_df[hist_df["season"] != 2025]
        hist_2025_fallback = hist_df[
            (hist_df["season"] == 2025)
            & (~hist_df["kaggle_team_id"].isin(current_2025_ids))
        ]
        hist_df = pd.concat(
            [hist_no_2025, hist_2025_fallback, current_df], ignore_index=True
        )

    # Merge seeds to get seed_num for tournament teams
    # Non-tournament teams will have seed_num = NaN (excluded from matchup lookups)
    merged = hist_df.merge(seeds_df, on=["season", "kaggle_team_id"], how="left")

    # Build lookup dict
    lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for row in merged.itertuples(index=False):
        # Skip rows with NaN stats (shouldn't happen post-filter but be safe)
        if pd.isna(row.adj_o) or pd.isna(row.adj_d) or pd.isna(row.barthag):
            continue

        key = (int(row.season), int(row.kaggle_team_id))
        lookup[key] = {
            "adj_o": float(row.adj_o),
            "adj_d": float(row.adj_d),
            "barthag": float(row.barthag),
            "adj_t": float(row.adj_t) if not pd.isna(row.adj_t) else 0.0,
            "wab": float(row.wab) if not pd.isna(row.wab) else 0.0,
            "seed_num": int(row.seed_num) if not pd.isna(row.seed_num) else -1,
        }

    return lookup


def build_matchup_dataset(
    processed_dir: str | pathlib.Path = "data/processed",
) -> pd.DataFrame:
    """Assemble a flat matchup DataFrame for supervised tournament game prediction.

    Joins tournament_games.parquet with seeds.parquet to get seed numbers for
    both teams in each game. Excludes First Four games (play-in games not in the
    main bracket) and games between equal-seeded teams.

    Canonical ordering: team_a = team with lower SeedNum (better seed / higher rank).
    Label: 1 if team_a (lower-seeded / better team) won, 0 if team_b upset.

    Features are computed via compute_features() using the stats lookup built by
    build_stats_lookup(). Rows where either team is missing from the stats lookup
    are dropped with a warning.

    Args:
        processed_dir: Directory containing the .parquet files. Default: data/processed

    Returns:
        DataFrame with columns:
            Season, team_a_id, team_b_id, team_a_seed, team_b_seed, label,
            adjoe_diff, adjde_diff, barthag_diff, seed_diff, adjt_diff, wab_diff
    """
    processed_path = pathlib.Path(processed_dir)
    games_parquet = processed_path / "tournament_games.parquet"
    seeds_parquet = processed_path / "seeds.parquet"

    if not games_parquet.exists():
        raise FileNotFoundError(
            f"tournament_games.parquet not found at {games_parquet}."
        )
    if not seeds_parquet.exists():
        raise FileNotFoundError(f"seeds.parquet not found at {seeds_parquet}.")

    conn = duckdb.connect()

    # Join tournament games to seeds for winner and loser seed numbers.
    # Filter: exclude First Four games, exclude equal-seed matchups.
    games_df = conn.execute(
        f"""
        SELECT
            g.Season,
            g.WTeamID,
            g.LTeamID,
            ws.SeedNum AS winner_seed,
            ls.SeedNum AS loser_seed
        FROM read_parquet('{games_parquet}') g
        JOIN read_parquet('{seeds_parquet}') ws
            ON g.WTeamID = ws.TeamID AND g.Season = ws.Season
        JOIN read_parquet('{seeds_parquet}') ls
            ON g.LTeamID = ls.TeamID AND g.Season = ls.Season
        WHERE NOT g.IsFirstFour
          AND ws.SeedNum != ls.SeedNum
        ORDER BY g.Season, g.WTeamID
        """
    ).df()

    conn.close()

    # Build stats lookup once (expensive operation)
    stats_lookup = build_stats_lookup(processed_dir)

    rows = []
    nan_dropped = 0
    missing_stats = 0

    for game in games_df.itertuples(index=False):
        season = game.Season
        winner_id = game.WTeamID
        loser_id = game.LTeamID
        winner_seed = game.winner_seed
        loser_seed = game.loser_seed

        # Canonical ordering: team_a = lower SeedNum (better seed)
        if winner_seed < loser_seed:
            team_a_id = winner_id
            team_b_id = loser_id
            team_a_seed = winner_seed
            team_b_seed = loser_seed
            label = 1  # team_a (better seed) won
        elif loser_seed < winner_seed:
            team_a_id = loser_id
            team_b_id = winner_id
            team_a_seed = loser_seed
            team_b_seed = winner_seed
            label = 0  # team_a (better seed) lost = upset
        else:
            # Equal seeds (should be filtered out by WHERE clause, but defensive)
            continue

        # Compute features — skip if either team missing from stats lookup
        try:
            features = compute_features(season, team_a_id, team_b_id, stats_lookup)
        except KeyError:
            missing_stats += 1
            continue

        # Check for NaN in any feature value
        if any(pd.isna(v) for v in features.values()):
            nan_dropped += 1
            continue

        row = {
            "Season": season,
            "team_a_id": team_a_id,
            "team_b_id": team_b_id,
            "team_a_seed": team_a_seed,
            "team_b_seed": team_b_seed,
            "label": label,
        }
        row.update(features)
        rows.append(row)

    df = pd.DataFrame(rows)

    total = len(df) + nan_dropped + missing_stats
    print(f"\nMatchup dataset summary:")
    print(f"  Total candidate games: {total}")
    print(f"  Missing stats (dropped): {missing_stats}")
    print(f"  NaN features (dropped): {nan_dropped}")
    print(f"  Final matchups: {len(df)}")

    if missing_stats > 0:
        warnings.warn(
            f"{missing_stats} games dropped: teams not in stats_lookup "
            "(likely pre-2008 seasons where cbbdata has no coverage)",
            stacklevel=2,
        )
    if nan_dropped > 0:
        warnings.warn(
            f"{nan_dropped} games dropped due to NaN feature values",
            stacklevel=2,
        )

    if len(df) == 0:
        raise ValueError("No matchups assembled. Check data files and stats coverage.")

    # Print per-season summary
    season_counts = df.groupby("Season").size()
    print(f"\nMatchups per season:")
    print(season_counts.to_string())

    # Label distribution
    label_dist = df["label"].value_counts().sort_index()
    label_pct = label_dist / len(df) * 100
    print(f"\nLabel distribution:")
    print(f"  label=0 (upset / lower seed wins): {label_dist.get(0, 0)} ({label_pct.get(0, 0):.1f}%)")
    print(f"  label=1 (favorite / higher seed wins): {label_dist.get(1, 0)} ({label_pct.get(1, 0):.1f}%)")

    # Ensure column order: metadata first, then features
    col_order = ["Season", "team_a_id", "team_b_id", "team_a_seed", "team_b_seed", "label"] + FEATURE_COLS
    df = df[col_order]

    return df


if __name__ == "__main__":
    print("Building matchup dataset...")
    df = build_matchup_dataset()

    print(f"\nDataset shape: {df.shape}")
    print(f"\nFirst 5 rows:")
    print(df.head(5).to_string(index=False))

    print(f"\nSeason coverage: {sorted(df['Season'].unique())}")

    # Verification checks
    nan_count = df[FEATURE_COLS].isna().sum().sum()
    assert nan_count == 0, f"ERROR: {nan_count} NaN values in feature columns"
    print(f"\nNaN in feature columns: {nan_count} (OK)")

    label_vals = set(df["label"].unique())
    assert label_vals == {0, 1}, f"ERROR: Bad label values {label_vals}"
    print(f"Label values: {sorted(label_vals)} (OK)")

    assert len(df) >= 1000, f"ERROR: Only {len(df)} matchups — expected 1000+"
    print(f"Total matchups: {len(df)} (OK)")

    n_seasons = df["Season"].nunique()
    assert n_seasons >= 5, f"ERROR: Only {n_seasons} seasons — expected 5+"
    print(f"Seasons: {n_seasons} (OK)")

    print("\nFeature means (team_a = better seed = lower SeedNum):")
    print("  adjoe_diff/barthag_diff/wab_diff should be POSITIVE (better seeds have better stats)")
    print("  seed_diff should be NEGATIVE (team_a has lower seed number = better seed)")
    print("  adjde_diff should be NEGATIVE (better seeds give up fewer points = lower adj_d)")
    print(df[FEATURE_COLS].mean().round(4).to_string())

    print("\nAll verification checks passed.")
