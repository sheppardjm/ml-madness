"""Main ingestion script: verifies Kaggle data and writes all Parquet files."""

from src.ingest.kaggle_download import verify_kaggle_files
from src.ingest.parse_tourney import ingest_tournament_games, ingest_tournament_seeds
from src.ingest.parse_regular_season import ingest_regular_season


def run_full_ingestion() -> None:
    """Run the complete ingestion pipeline."""
    print("Step 1: Verifying Kaggle data...")
    verify_kaggle_files()

    print("Step 2: Ingesting tournament games...")
    games = ingest_tournament_games()
    print(f"  -> {games} tournament games written")

    print("Step 3: Ingesting tournament seeds...")
    seeds = ingest_tournament_seeds()
    print(f"  -> {seeds} seed entries written")

    print("Step 4: Ingesting regular season games...")
    reg = ingest_regular_season()
    print(f"  -> {reg} regular season games written")

    print("Done! All Parquet files written to data/processed/")


if __name__ == "__main__":
    run_full_ingestion()
