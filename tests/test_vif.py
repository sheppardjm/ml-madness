"""
Unit tests for VIF (Variance Inflation Factor) analysis (src/models/vif_analysis.py).

Covers SC-2: VIF threshold verification.
  - barthag_diff VIF exceeds 10 (documented multicollinearity with adjoe/adjde).
  - All other 5 features are below VIF threshold of 10.
  - Removing barthag_diff brings all remaining features below VIF 6.
  - vif_report.json artifact exists and contains the correct structure/values.
"""
import json
import math
import pathlib

import numpy as np
import pytest

from src.models.vif_analysis import compute_vif


# ---------------------------------------------------------------------------
# Module-scoped fixture: build matchup dataset once per test module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def matchup_df():
    """Module-scoped matchup dataset. Built once and shared within this module."""
    from src.models.features import build_matchup_dataset
    return build_matchup_dataset()


# ---------------------------------------------------------------------------
# SC-2: VIF threshold tests
# ---------------------------------------------------------------------------


def test_compute_vif_returns_all_features(matchup_df):
    """compute_vif returns one row per FEATURE_COL, all with positive finite VIF values."""
    from src.models.features import FEATURE_COLS

    X = matchup_df[FEATURE_COLS].values
    vif_df = compute_vif(X, FEATURE_COLS)

    assert len(vif_df) == 6, (
        f"Expected 6 rows in VIF DataFrame (one per feature), got {len(vif_df)}"
    )
    assert list(vif_df.columns) == ["feature", "vif", "status"], (
        f"Unexpected columns: {list(vif_df.columns)}"
    )

    for _, row in vif_df.iterrows():
        vif_val = row["vif"]
        assert isinstance(vif_val, float), f"VIF for {row['feature']} is not float: {type(vif_val)}"
        assert vif_val > 0, f"VIF for {row['feature']} should be positive, got {vif_val}"
        assert math.isfinite(vif_val), f"VIF for {row['feature']} is not finite: {vif_val}"


def test_barthag_exceeds_threshold(matchup_df):
    """barthag_diff VIF exceeds the 10.0 threshold (documented multicollinearity)."""
    from src.models.features import FEATURE_COLS

    X = matchup_df[FEATURE_COLS].values
    vif_df = compute_vif(X, FEATURE_COLS)

    barthag_row = vif_df[vif_df["feature"] == "barthag_diff"]
    assert len(barthag_row) == 1, "barthag_diff should appear exactly once in VIF DataFrame"

    barthag_vif = barthag_row["vif"].iloc[0]
    assert barthag_vif > 10, (
        f"barthag_diff VIF should exceed 10 (expected ~11.2), got {barthag_vif:.4f}"
    )
    assert barthag_row["status"].iloc[0] == "EXCEEDS_THRESHOLD", (
        f"barthag_diff status should be EXCEEDS_THRESHOLD, got {barthag_row['status'].iloc[0]}"
    )


def test_all_except_barthag_below_threshold(matchup_df):
    """All 5 features except barthag_diff have VIF < 10."""
    from src.models.features import FEATURE_COLS

    X = matchup_df[FEATURE_COLS].values
    vif_df = compute_vif(X, FEATURE_COLS)

    other_features = vif_df[vif_df["feature"] != "barthag_diff"]
    assert len(other_features) == 5, (
        f"Expected 5 non-barthag features, got {len(other_features)}"
    )

    for _, row in other_features.iterrows():
        assert row["vif"] < 10, (
            f"Expected VIF < 10 for {row['feature']}, got {row['vif']:.4f}"
        )

    # adjt_diff is nearly independent of other features (VIF ~1.05)
    adjt_row = vif_df[vif_df["feature"] == "adjt_diff"]
    adjt_vif = adjt_row["vif"].iloc[0]
    assert adjt_vif < 2, (
        f"adjt_diff VIF should be < 2 (expected ~1.05), got {adjt_vif:.4f}"
    )


def test_vif_report_exists_and_valid():
    """models/vif_report.json exists and contains correct structure and values."""
    report_path = pathlib.Path("models/vif_report.json")
    assert report_path.exists(), (
        f"vif_report.json not found at {report_path.absolute()}. "
        "Run 'uv run python -m src.models.vif_analysis' first."
    )

    with open(report_path) as f:
        report = json.load(f)

    # Required top-level keys
    required_keys = {"features", "exceeds_threshold", "decision", "decision_rationale", "sc2_assessment"}
    missing = required_keys - set(report.keys())
    assert not missing, f"vif_report.json missing required keys: {missing}"

    # barthag_diff must be in the exceedance list
    assert "barthag_diff" in report["exceeds_threshold"], (
        f"Expected barthag_diff in exceeds_threshold, got: {report['exceeds_threshold']}"
    )

    # Decision must be KEEP_ALL
    assert report["decision"] == "KEEP_ALL", (
        f"Expected decision='KEEP_ALL', got {report['decision']!r}"
    )


def test_without_barthag_all_below_six(matchup_df):
    """Without barthag_diff, all remaining features have VIF < 6."""
    from src.models.features import FEATURE_COLS

    remaining_cols = [c for c in FEATURE_COLS if c != "barthag_diff"]
    assert len(remaining_cols) == 5, (
        f"Expected 5 remaining columns after removing barthag_diff, got {len(remaining_cols)}"
    )

    X_no_barthag = matchup_df[remaining_cols].values
    vif_df = compute_vif(X_no_barthag, remaining_cols)

    for _, row in vif_df.iterrows():
        assert row["vif"] < 6, (
            f"Expected VIF < 6 for {row['feature']} without barthag_diff, "
            f"got {row['vif']:.4f}"
        )
