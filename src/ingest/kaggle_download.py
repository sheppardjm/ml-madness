"""
Kaggle March Machine Learning Mania 2026 dataset download and verification.

Downloads the competition dataset to data/raw/kaggle/ using kagglehub.
Requires ~/.kaggle/kaggle.json with a valid API token and competition
rules accepted at https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data

Prerequisites:
    1. Create ~/.kaggle/kaggle.json with your API token:
       {"username":"YOUR_USERNAME","key":"YOUR_KEY"}
       Get this from: https://www.kaggle.com/settings -> API section -> Create New Token
    2. Accept competition rules at:
       https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data
       (click "I Understand and Accept")
"""

import pathlib
import shutil

import duckdb
import kagglehub

COMPETITION = "march-machine-learning-mania-2026"
RAW_DATA_DIR = pathlib.Path("data/raw/kaggle")

# Files required to be present after download.
REQUIRED_FILES = [
    "MTeams.csv",
    "MSeasons.csv",
    "MNCAATourneyCompactResults.csv",
    "MNCAATourneySeeds.csv",
    "MNCAATourneySlots.csv",
    "MRegularSeasonCompactResults.csv",
]


def download_kaggle_data() -> pathlib.Path:
    """Download the Kaggle competition dataset to data/raw/kaggle/.

    Uses kagglehub to download the competition files, then copies them
    to the project's raw data directory.

    Returns:
        Path to the raw data directory (data/raw/kaggle/).

    Raises:
        Exception: If kagglehub authentication fails or competition rules
            haven't been accepted.
    """
    print(f"Downloading Kaggle competition: {COMPETITION}")
    print("Note: Requires ~/.kaggle/kaggle.json and accepted competition rules.")

    try:
        path = kagglehub.competition_download(COMPETITION)
    except Exception as e:
        err_str = str(e).lower()
        if "401" in err_str or "403" in err_str or "authenticate" in err_str or "credential" in err_str or "api" in err_str:
            print("\nAuthentication error. To fix:")
            print("1. Go to https://www.kaggle.com/settings -> API section -> Create New Token")
            print("   This downloads kaggle.json")
            print("2. Move it to ~/.kaggle/kaggle.json")
            print("3. Set permissions: chmod 600 ~/.kaggle/kaggle.json")
            print("4. Accept competition rules at:")
            print("   https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data")
            print("   (click 'I Understand and Accept')")
            print(f"\nOriginal error: {e}")
            raise
        elif "rules" in err_str or "accept" in err_str or "terms" in err_str:
            print("\nCompetition rules not accepted. To fix:")
            print("  Go to https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data")
            print("  Click 'I Understand and Accept'")
            print(f"\nOriginal error: {e}")
            raise
        else:
            raise

    print(f"Downloaded to Kaggle cache: {path}")

    # Copy to project's raw data directory
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(path, RAW_DATA_DIR, dirs_exist_ok=True)
    print(f"Copied to: {RAW_DATA_DIR}")

    # List downloaded files
    files = sorted(RAW_DATA_DIR.glob("*.csv"))
    print(f"\nDownloaded {len(files)} CSV files:")
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name} ({size_mb:.2f} MB)")

    return RAW_DATA_DIR


def verify_kaggle_files() -> None:
    """Verify all required Kaggle CSV files are present.

    Checks that all files needed by downstream pipeline steps exist in
    data/raw/kaggle/.

    Raises:
        FileNotFoundError: If any required files are missing, with a list
            of the missing files.
    """
    missing = [
        fname
        for fname in REQUIRED_FILES
        if not (RAW_DATA_DIR / fname).exists()
    ]

    if missing:
        raise FileNotFoundError(
            f"Missing required Kaggle files in {RAW_DATA_DIR}:\n"
            + "\n".join(f"  - {f}" for f in missing)
            + f"\n\nRun: uv run python -m src.ingest.kaggle_download"
        )


if __name__ == "__main__":
    # Step 1: Download data
    raw_dir = download_kaggle_data()

    # Step 2: Verify required files
    print("\nVerifying required files...")
    verify_kaggle_files()
    print("All required files present.")

    # Step 3: Summary stats
    print("\n--- Dataset Summary ---")

    # File sizes
    print("\nFile inventory:")
    all_csvs = sorted(raw_dir.glob("*.csv"))
    total_files = len(all_csvs)
    for f in all_csvs:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.1f} KB")
    print(f"Total: {total_files} CSV files")

    # Max season in tournament results
    tourney_path = raw_dir / "MNCAATourneyCompactResults.csv"
    result = duckdb.sql(
        f"SELECT MIN(Season) as min_season, MAX(Season) as max_season, "
        f"COUNT(*) as total_games FROM read_csv('{tourney_path}')"
    ).df()
    print(f"\nTournament results coverage:")
    print(f"  Min season: {result['min_season'][0]}")
    print(f"  Max season: {result['max_season'][0]}")
    print(f"  Total games: {result['total_games'][0]}")

    if result["max_season"][0] < 2025:
        print(
            f"\nWARNING: Max season is {result['max_season'][0]}, expected 2025. "
            "The 2025 season may not be included in this dataset version."
        )
    else:
        print(f"\n2025 tournament data confirmed present.")
