"""
Walk-forward temporal cross-validation harness for NCAA tournament prediction.

Provides year-grouped, strictly temporal train/test splits to prevent data leakage.
Each fold holds out a single tournament year; the training set contains only seasons
strictly before the holdout year.

This is the canonical evaluation framework used for all models in the pipeline.

Exports:
    BACKTEST_YEARS      - List of holdout years [2022, 2023, 2024, 2025]
    walk_forward_splits() - Generator yielding (year, train_df, test_df) tuples
    describe_splits()   - Print a split summary table for sanity-checking
"""

from __future__ import annotations

from typing import Generator

import pandas as pd

# The four holdout years used for temporal cross-validation.
# These cover the most recent four tournaments and give a stable estimate of
# out-of-sample performance across different competitive eras.
BACKTEST_YEARS: list[int] = [2022, 2023, 2024, 2025]


def walk_forward_splits(
    df: pd.DataFrame,
    backtest_years: list[int] | None = None,
) -> Generator[tuple[int, pd.DataFrame, pd.DataFrame], None, None]:
    """Generate walk-forward temporal train/test splits for year-grouped CV.

    For each holdout year T, the training set contains all seasons strictly
    before T and the test set contains only season T. Data leakage is prevented
    by asserting that no future year appears in any training fold.

    Args:
        df: Matchup DataFrame (from build_matchup_dataset()) containing a
            'Season' column and feature columns.
        backtest_years: List of holdout years to generate folds for.
            Defaults to BACKTEST_YEARS = [2022, 2023, 2024, 2025].

    Yields:
        Tuples of (test_year, train_df, test_df) where:
            - test_year: The holdout year (int)
            - train_df: All rows with Season < test_year
            - test_df:  All rows with Season == test_year

    Raises:
        AssertionError: If there is no training data before any holdout year,
            no test data for any holdout year, or if future data is detected
            in a training fold (data leakage guard).
    """
    if backtest_years is None:
        backtest_years = BACKTEST_YEARS

    for test_year in backtest_years:
        train_df = df[df["Season"] < test_year].copy()
        test_df = df[df["Season"] == test_year].copy()

        assert len(train_df) > 0, f"No training data before {test_year}"
        assert len(test_df) > 0, f"No test data for {test_year}"

        # DATA LEAKAGE GUARD: Ensure training fold contains no future data
        assert train_df["Season"].max() < test_year, (
            "DATA LEAKAGE: future year in training fold"
        )

        yield (test_year, train_df, test_df)


def describe_splits(
    df: pd.DataFrame,
    backtest_years: list[int] | None = None,
) -> None:
    """Print a summary table of all walk-forward cross-validation folds.

    Useful for sanity-checking the splits before training to confirm:
    - Training fold sizes are increasing (walk-forward property)
    - No data leakage (max train season < test year)
    - Reasonable label rates in each fold

    Args:
        df: Matchup DataFrame (from build_matchup_dataset()).
        backtest_years: List of holdout years. Defaults to BACKTEST_YEARS.
    """
    header = f"{'Year':>6} | {'Train Seasons':>15} | {'Train Games':>12} | {'Test Games':>11} | {'Train Label=1 Rate':>20}"
    print(header)
    print("-" * len(header))

    for test_year, train_df, test_df in walk_forward_splits(df, backtest_years):
        train_seasons = sorted(train_df["Season"].unique())
        train_season_str = f"{train_seasons[0]}-{train_seasons[-1]}" if train_seasons else "N/A"
        label_rate = train_df["label"].mean()

        print(
            f"{test_year:>6} | "
            f"{train_season_str:>15} | "
            f"{len(train_df):>12} | "
            f"{len(test_df):>11} | "
            f"{label_rate:>20.3f}"
        )

    print()


if __name__ == "__main__":
    from src.models.features import build_matchup_dataset

    print("Building matchup dataset...")
    df = build_matchup_dataset()

    print(f"\nDataset shape: {df.shape}")
    print(f"Season coverage: {sorted(df['Season'].unique())}")

    print("\nWalk-forward split summary:")
    describe_splits(df)

    print("Leakage check (max_train_season must be < test_year for each fold):")
    all_ok = True
    for year, train_df, test_df in walk_forward_splits(df):
        max_train = train_df["Season"].max()
        ok = max_train < year
        status = "OK" if ok else "LEAKAGE!"
        print(f"  {year}: max_train_season={max_train}, test_year={year} -> {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAll leakage checks passed.")
    else:
        print("\nERROR: Data leakage detected!")
