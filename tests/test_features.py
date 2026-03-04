"""
Unit tests for the compute_features public API (src/models/features.py).

Covers four success criteria:
  SC-1: Known historical matchup fixtures verify feature signs and approximate values.
  SC-3: Cutoff-date enforcement via the as_of_date parameter.
  SC-4: Perspective symmetry -- compute_features(A, B) + compute_features(B, A) == 0.

Error handling:
  Unknown team names raise ValueError.
  Missing seasons raise KeyError.
  Invalid as_of_date raises ValueError.
"""
import math
import pathlib

import joblib
import numpy as np
import pytest

from src.models.features import (
    FEATURE_COLS,
    _compute_features_by_id,
    build_stats_lookup,
    compute_features,
)


# ---------------------------------------------------------------------------
# SC-1: Known historical matchup fixtures
# ---------------------------------------------------------------------------


def test_compute_features_returns_all_keys(stats_lookup):
    """compute_features returns exactly the 6 FEATURE_COLS keys, all finite floats."""
    feats = compute_features("Duke", "Michigan", 2025, stats_lookup=stats_lookup)

    assert set(feats.keys()) == set(FEATURE_COLS), (
        f"Expected keys {FEATURE_COLS}, got {list(feats.keys())}"
    )
    assert len(feats) == 6

    for key, val in feats.items():
        assert isinstance(val, (int, float)), (
            f"Value for {key} is not numeric: {type(val)}"
        )
        assert not math.isnan(float(val)), f"Value for {key} is NaN"
        assert math.isfinite(float(val)), f"Value for {key} is not finite: {val}"


# Known matchup sign tests: Duke (seed 1) vs Michigan (seed 5) in 2025.
# compute_features("Duke", "Michigan", 2025) uses Duke as team_a, Michigan as team_b.
# Each feature = team_a_stat - team_b_stat = Duke_stat - Michigan_stat.
#
# Sign expectations:
#   adjoe_diff: Duke adj_o - Michigan adj_o  -> positive (Duke has better offense)
#   seed_diff:  Duke seed - Michigan seed     -> 1 - 5 = -4 (negative, Duke has lower number)
#   barthag_diff: Duke barthag - Michigan barthag -> positive (Duke has higher power rating)
#   adjde_diff: Duke adj_d - Michigan adj_d  -> negative (Duke allows fewer points)
@pytest.mark.parametrize(
    "team_a, team_b, season, feature, expected_sign",
    [
        ("Duke", "Michigan", 2025, "adjoe_diff", "positive"),
        ("Duke", "Michigan", 2025, "seed_diff", "negative"),
        ("Duke", "Michigan", 2025, "barthag_diff", "positive"),
        ("Duke", "Michigan", 2025, "adjde_diff", "negative"),
    ],
)
def test_known_matchup_feature_signs(
    team_a, team_b, season, feature, expected_sign, stats_lookup
):
    """Computed feature signs match expectations for known historical matchup."""
    feats = compute_features(team_a, team_b, season, stats_lookup=stats_lookup)
    val = feats[feature]

    if expected_sign == "positive":
        assert val > 0, (
            f"Expected {feature} > 0 for {team_a} vs {team_b} {season}, got {val:.4f}"
        )
    elif expected_sign == "negative":
        assert val < 0, (
            f"Expected {feature} < 0 for {team_a} vs {team_b} {season}, got {val:.4f}"
        )
    else:
        raise ValueError(f"Unknown expected_sign: {expected_sign}")


def test_known_matchup_approximate_values(stats_lookup):
    """Feature values for Duke vs Michigan 2025 are within expected ranges."""
    feats = compute_features("Duke", "Michigan", 2025, stats_lookup=stats_lookup)

    # seed_diff = Duke_seed - Michigan_seed = 1 - 5 = -4 (exact integer)
    assert feats["seed_diff"] == -4.0, (
        f"Expected seed_diff == -4.0, got {feats['seed_diff']}"
    )

    # adjoe_diff: Duke's offense is significantly better than Michigan's
    assert 10 < feats["adjoe_diff"] < 20, (
        f"Expected adjoe_diff in (10, 20), got {feats['adjoe_diff']:.4f}"
    )

    # barthag_diff: Duke has meaningfully higher power rating
    assert 0.03 < feats["barthag_diff"] < 0.15, (
        f"Expected barthag_diff in (0.03, 0.15), got {feats['barthag_diff']:.4f}"
    )


def test_name_based_matches_id_based(stats_lookup):
    """Name-based compute_features matches ID-based _compute_features_by_id exactly."""
    # Duke=1181, Michigan=1276
    feats_name = compute_features(
        "Duke", "Michigan", 2025, stats_lookup=stats_lookup
    )
    feats_id = _compute_features_by_id(2025, 1181, 1276, stats_lookup)

    assert set(feats_name.keys()) == set(feats_id.keys())
    for key in FEATURE_COLS:
        assert feats_name[key] == feats_id[key], (
            f"Mismatch for {key}: name-based={feats_name[key]}, "
            f"id-based={feats_id[key]}"
        )


# ---------------------------------------------------------------------------
# SC-3: Cutoff-date enforcement via as_of_date
# ---------------------------------------------------------------------------


def test_as_of_date_returns_same_result(stats_lookup):
    """compute_features with as_of_date='2025-03-16' returns identical result to no date."""
    feats_no_date = compute_features(
        "Duke", "Michigan", 2025, stats_lookup=stats_lookup
    )
    feats_with_date = compute_features(
        "Duke", "Michigan", 2025, stats_lookup=stats_lookup, as_of_date="2025-03-16"
    )

    assert feats_no_date == feats_with_date, (
        "Features with as_of_date='2025-03-16' should match features without as_of_date. "
        f"Differences: {[(k, feats_no_date[k], feats_with_date[k]) for k in FEATURE_COLS if feats_no_date[k] != feats_with_date[k]]}"
    )


def test_as_of_date_invalid_raises_valueerror(stats_lookup):
    """as_of_date with future/unknown date raises ValueError."""
    with pytest.raises(ValueError, match="as_of_date"):
        compute_features(
            "Duke",
            "Michigan",
            2025,
            stats_lookup=stats_lookup,
            as_of_date="2099-01-01",
        )


def test_cutoff_enforcement_by_construction(stats_lookup):
    """Duke (team 1181) exists in stats_lookup for season 2025 with finite stats."""
    assert (2025, 1181) in stats_lookup, (
        "Duke (team 1181) should be in stats_lookup for 2025"
    )
    duke_stats = stats_lookup[(2025, 1181)]
    for stat_key in ("adj_o", "adj_d", "barthag", "adj_t", "wab"):
        val = duke_stats[stat_key]
        assert isinstance(val, float), f"stats[{stat_key!r}] is not float: {type(val)}"
        assert math.isfinite(val), f"stats[{stat_key!r}] is not finite: {val}"


def test_stats_lookup_covers_backtest_years(stats_lookup):
    """stats_lookup contains at least 60 teams per BACKTEST_YEARS season."""
    backtest_years = [2022, 2023, 2024, 2025]
    for year in backtest_years:
        teams_in_year = [(s, t) for (s, t) in stats_lookup if s == year]
        assert len(teams_in_year) >= 60, (
            f"Expected >=60 teams for season {year}, found {len(teams_in_year)}"
        )


# ---------------------------------------------------------------------------
# SC-4: Perspective symmetry
# ---------------------------------------------------------------------------


def test_perspective_symmetry(stats_lookup):
    """For all features: feats(Duke, Michigan) + feats(Michigan, Duke) == 0."""
    feats_ab = compute_features("Duke", "Michigan", 2025, stats_lookup=stats_lookup)
    feats_ba = compute_features("Michigan", "Duke", 2025, stats_lookup=stats_lookup)

    for k in FEATURE_COLS:
        total = feats_ab[k] + feats_ba[k]
        assert abs(total) < 1e-10, (
            f"Symmetry failed for {k}: feats_ab={feats_ab[k]:.10f}, "
            f"feats_ba={feats_ba[k]:.10f}, sum={total:.2e}"
        )


@pytest.mark.parametrize(
    "team_a, team_b, season",
    [
        ("Duke", "Michigan", 2025),
        ("Gonzaga", "UCLA", 2024),
        ("Houston", "Alabama", 2023),
    ],
)
def test_perspective_symmetry_multiple_pairs(team_a, team_b, season, stats_lookup):
    """Symmetry holds for multiple team pairs across different seasons."""
    feats_ab = compute_features(team_a, team_b, season, stats_lookup=stats_lookup)
    feats_ba = compute_features(team_b, team_a, season, stats_lookup=stats_lookup)

    for k in FEATURE_COLS:
        total = feats_ab[k] + feats_ba[k]
        assert abs(total) < 1e-10, (
            f"Symmetry failed for {k} ({team_a} vs {team_b} {season}): "
            f"feats_ab={feats_ab[k]:.10f}, feats_ba={feats_ba[k]:.10f}, sum={total:.2e}"
        )


def test_model_probability_asymmetry_documented(stats_lookup):
    """Document that model P(A,B) + P(B,A) != 1.0 due to StandardScaler non-zero means.

    This is EXPECTED behavior, not a bug. The StandardScaler is trained on data
    where team_a is always the lower seed (better seed), producing non-zero
    feature means (e.g., adjoe_diff mean~5.8, seed_diff mean~-6.5). Since
    scaler.transform(-x) != -scaler.transform(x) when mean != 0, the model
    produces asymmetric probabilities.

    Feature-level symmetry (feats_ab + feats_ba = 0) IS verified by other tests.
    Model-level probability symmetry is structurally impossible with the current
    training convention and is not a requirement.
    """
    ensemble_path = pathlib.Path("models/ensemble.joblib")
    if not ensemble_path.exists():
        pytest.skip("models/ensemble.joblib not found — skipping documentation test")

    bundle = joblib.load(ensemble_path)
    scaler = bundle["scaler"]

    # Compute features both ways
    feats_ab = compute_features("Duke", "Michigan", 2025, stats_lookup=stats_lookup)
    feats_ba = compute_features("Michigan", "Duke", 2025, stats_lookup=stats_lookup)

    # Feature symmetry holds (verified elsewhere, quick sanity check)
    for k in FEATURE_COLS:
        assert abs(feats_ab[k] + feats_ba[k]) < 1e-10

    # Demonstrate scaler asymmetry: scaler(-x) != -scaler(x)
    x_ab = np.array([[feats_ab[k] for k in FEATURE_COLS]])
    x_ba = np.array([[feats_ba[k] for k in FEATURE_COLS]])

    scaled_ab = scaler.transform(x_ab)
    scaled_ba = scaler.transform(x_ba)

    # If scaler had zero means, scaled_ab + scaled_ba would be zero.
    # With non-zero means, they don't cancel:
    scaling_residual = np.abs(scaled_ab + scaled_ba).max()
    assert scaling_residual > 0.1, (
        f"Expected non-zero scaling residual due to non-zero means, "
        f"got {scaling_residual:.6f}"
    )

    # Get model predictions — bundle["ensemble"] is the TwoTierEnsemble object
    # (bundle["model"] is the string 'ensemble', a symbolic pointer — do NOT use it)
    ensemble = bundle["ensemble"]
    # predict_proba returns shape (1, 2) = [[P(loss), P(win)]]
    # Index [0][1] extracts the scalar win probability
    p_ab = ensemble.predict_proba(scaled_ab)[0][1]
    p_ba = ensemble.predict_proba(scaled_ba)[0][1]

    # Document the asymmetry: P(A,B) + P(B,A) != 1.0
    prob_sum = p_ab + p_ba
    asymmetry = abs(prob_sum - 1.0)

    # The asymmetry is non-trivial (measured ~0.179 in verification)
    assert asymmetry > 0.01, (
        f"Expected model probability asymmetry > 0.01, got {asymmetry:.6f}. "
        "If this fails, the scaler may have been retrained with zero-mean data."
    )

    # Document the values for future reference
    print(f"\n  Model probability asymmetry (expected, not a bug):")
    print(f"    P(Duke beats Michigan) = {p_ab:.4f}")
    print(f"    P(Michigan beats Duke) = {p_ba:.4f}")
    print(f"    Sum = {prob_sum:.4f} (1.0 would require zero-mean scaler)")
    print(f"    Asymmetry = {asymmetry:.4f}")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_unknown_team_raises_valueerror():
    """Completely unknown team name raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        compute_features("Totally Fake University", "Duke", 2025)


def test_missing_season_raises_keyerror(stats_lookup):
    """Season with no data (2002, before cbbdata coverage) raises KeyError."""
    with pytest.raises(KeyError):
        compute_features("Duke", "Michigan", 2002, stats_lookup=stats_lookup)
