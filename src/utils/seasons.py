"""
Valid tournament season list and DayNum-to-round mapping for NCAA tournament data.

Covers seasons 2003-2025, excluding 2020 (tournament cancelled due to COVID-19).
Intended for use with the Kaggle March Machine Learning Mania dataset.
"""

# All seasons with valid NCAA tournament data in the Kaggle dataset.
# 2020 is intentionally excluded — tournament was cancelled due to COVID-19.
# Total: 22 seasons (2003-2019 = 17 seasons, 2021-2025 = 5 seasons).
VALID_TOURNEY_SEASONS: list[int] = [
    2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018,
    2019,
    # 2020 excluded: tournament cancelled (COVID-19)
    2021, 2022, 2023, 2024, 2025,
]

# Mapping from Kaggle DayNum values to round names.
# DayNum is an offset from DayZero (in MSeasons.csv) for each season.
# Source: Research verification — DayNum 132=Selection Sunday, 134-135=First Four,
# 136-137=Round of 64, etc.
#
# Note: DayNum 134-135 maps to "First Four" for 2011-present (4 games).
# For 2003-2010, DayNum 134 represents a single play-in game predating the
# "First Four" branding. Both are labeled "First Four" here for simplicity;
# code consuming this map should check Season to distinguish.
DAYNUM_ROUND_MAP: dict[int, str] = {
    134: "First Four",
    135: "First Four",
    136: "Round of 64",
    137: "Round of 64",
    138: "Round of 32",
    139: "Round of 32",
    143: "Sweet Sixteen",
    144: "Sweet Sixteen",
    145: "Elite Eight",
    146: "Elite Eight",
    152: "Final Four",
    154: "Championship",
}
