"""
Fuzzy matching helpers for generating team name alias candidates.

This module provides a BOOTSTRAP tool to generate candidate name mappings
between Kaggle team names and names from other sources (ESPN, Sports-Reference,
cbbdata). The output is candidates for human review — not final truth.

The actual normalization table uses hand-curated values from team_aliases.csv.

Usage:
    from src.normalize.fuzzy_match import generate_alias_candidates
    candidates = generate_alias_candidates(kaggle_names, espn_names, "espn")
    # Review candidates with needs_review=True manually
"""

from __future__ import annotations

import pandas as pd
from thefuzz import fuzz, process


def generate_alias_candidates(
    kaggle_names: list[str],
    target_names: list[str],
    source_label: str = "target",
) -> pd.DataFrame:
    """Generate fuzzy-matched alias candidates between Kaggle names and target source names.

    For each Kaggle team name, finds the best matching name from the target source
    using token_sort_ratio scoring (handles word reordering like "Connecticut" vs
    "UConn Connecticut"). Returns a DataFrame with confidence scores so low-confidence
    matches can be flagged for human review.

    This is a BOOTSTRAP tool only. The generated candidates must be reviewed manually
    and curated into team_aliases.csv before being used in the normalization table.
    High-confidence matches (score >= 90) are likely correct but should be spot-checked;
    low-confidence matches (score < 90) require human judgment.

    Args:
        kaggle_names: List of team name strings from Kaggle's MTeams.csv.
        target_names: List of team name strings from the target data source.
        source_label: Label for the target source (e.g., "espn", "sr", "cbbdata").
            Used as a column name prefix in the output DataFrame.

    Returns:
        DataFrame with columns:
            - kaggle_name: The input Kaggle team name
            - {source_label}_candidate: Best matching name from target_names
            - confidence_score: Fuzzy match score (0-100, higher is better)
            - needs_review: True if confidence_score < 90 (flag for human review)

    Example:
        >>> candidates = generate_alias_candidates(
        ...     ["Connecticut", "St John's"],
        ...     ["UConn", "St. John's (NY)", "Duke"],
        ...     source_label="espn"
        ... )
        >>> candidates[candidates.needs_review]
        # Shows rows where manual review is recommended
    """
    rows = []
    for kaggle_name in kaggle_names:
        result = process.extractOne(
            kaggle_name,
            target_names,
            scorer=fuzz.token_sort_ratio,
        )
        if result is None:
            rows.append(
                {
                    "kaggle_name": kaggle_name,
                    f"{source_label}_candidate": None,
                    "confidence_score": 0,
                    "needs_review": True,
                }
            )
        else:
            match, score = result[0], result[1]
            rows.append(
                {
                    "kaggle_name": kaggle_name,
                    f"{source_label}_candidate": match,
                    "confidence_score": score,
                    "needs_review": score < 90,
                }
            )

    return pd.DataFrame(rows)
