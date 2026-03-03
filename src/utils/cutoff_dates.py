"""
Selection Sunday cutoff dates for NCAA tournament seasons 2003-2025.

Used to gate regular season stat queries — only include data available
before Selection Sunday to prevent data leakage in predictions.

Source: Verified against interbasket.net historical table + Wikipedia tournament
articles + web searches. 2003-2006 derived from confirmed first-round start dates.
2020 excluded: NCAA tournament cancelled due to COVID-19.
"""

# DayNum value corresponding to Selection Sunday in Kaggle's data.
# Kaggle encodes dates as an offset from DayZero in MSeasons.csv.
DAYNUM_SELECTION_SUNDAY: int = 132

# Selection Sunday dates per season (YYYY-MM-DD format, inclusive).
# These are the dates used as cutoffs for stat queries — only include
# regular season data on or before this date.
SELECTION_SUNDAY_DATES: dict[int, str] = {
    2003: "2003-03-16",
    2004: "2004-03-14",
    2005: "2005-03-13",
    2006: "2006-03-12",
    2007: "2007-03-11",
    2008: "2008-03-16",
    2009: "2009-03-15",
    2010: "2010-03-14",
    2011: "2011-03-13",
    2012: "2012-03-11",
    2013: "2013-03-17",
    2014: "2014-03-16",
    2015: "2015-03-15",
    2016: "2016-03-13",
    2017: "2017-03-12",
    2018: "2018-03-11",
    2019: "2019-03-17",
    # 2020: tournament cancelled (COVID-19) — no entry
    2021: "2021-03-14",
    2022: "2022-03-13",
    2023: "2023-03-12",
    2024: "2024-03-17",
    2025: "2025-03-16",
    2026: "2026-03-15",
}


def get_cutoff(season: int) -> str:
    """Return the Selection Sunday date string (inclusive cutoff) for a season.

    Args:
        season: NCAA tournament season year (e.g., 2025).

    Returns:
        Date string in YYYY-MM-DD format.

    Raises:
        ValueError: If season is not a valid tournament season (e.g., 2020 which
            was cancelled, or any year outside 2003-2025).
    """
    if season not in SELECTION_SUNDAY_DATES:
        if season == 2020:
            raise ValueError(
                f"Season 2020 has no cutoff date: NCAA tournament was cancelled due to COVID-19."
            )
        raise ValueError(
            f"No Selection Sunday date for season {season}. "
            f"Valid seasons: 2003-2019, 2021-2026 (2020 cancelled)."
        )
    return SELECTION_SUNDAY_DATES[season]
