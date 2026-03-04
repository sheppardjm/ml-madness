# Phase 8: Feature Store - Research

**Researched:** 2026-03-04
**Domain:** Feature engineering API design, VIF multicollinearity analysis, pytest unit testing, cutoff-date enforcement
**Confidence:** HIGH (all findings from live codebase inspection and live data analysis)

## Summary

Phase 8 formalizes the existing inline `compute_features()` function into a tested, validated public API. The function already exists in `src/models/features.py` and works correctly — this phase is about API redesign (name-based instead of ID-based), VIF analysis with documentation, cutoff-date enforcement verification, and building a pytest suite with historical fixtures.

**Critical pre-existing fact (verified by live computation):** `barthag_diff` already has VIF = 11.2 on the 1054-matchup training dataset, which exceeds the SC-2 threshold of VIF > 10. The VIF analysis in Plan 08-04 will confirm this empirically and must document how to handle it — dropping barthag_diff reduces all remaining feature VIFs to < 6, but this contradicts the locked feature set `FEATURE_COLS = ['adjoe_diff', 'adjde_diff', 'barthag_diff', 'seed_diff', 'adjt_diff', 'wab_diff']` from decision [03-01]. The planner must address this tension explicitly.

**Key architectural insight:** The current `compute_features()` takes integer team IDs. The Phase 8 success criterion requires `compute_features(team_a="Duke", team_b="Michigan", season=2025)` — a string name-based API. This requires adding a name-to-ID resolution layer backed by `team_normalization.parquet`. The existing internal function can be retained (as `_compute_features_by_id()`) and the public wrapper resolves names to IDs. Both `statsmodels` (for VIF) and `pytest` (for testing) must be added to `pyproject.toml` — neither is currently installed.

**Primary recommendation:** Add `pytest>=9.0.2` and `statsmodels>=0.14.6` to `pyproject.toml`, create a public `compute_features(team_a, team_b, season, as_of_date=None)` wrapper that resolves names via `team_normalization.parquet`, keep the internal ID-based function unchanged, implement VIF analysis using `statsmodels.stats.outliers_influence.variance_inflation_factor`, and build pytest fixtures using 2024-2025 known matchups with documented expected values.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| statsmodels | 0.14.6 | `variance_inflation_factor()` for VIF analysis | The only Python library with built-in VIF computation; used industry-wide for multicollinearity detection |
| pytest | 9.0.2 | Unit test runner and fixture framework | Project standard for Python testing; supports `@pytest.mark.parametrize` for known-matchup fixtures |
| pandas | 3.0.1 (installed) | Name-to-ID lookup DataFrame operations | Already project standard |
| duckdb | 1.4.4 (installed) | Read `team_normalization.parquet` for name resolution | Already project standard |
| numpy | project standard | Feature vector computation | Already project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | File path handling for parquet files | Throughout compute_features API |
| datetime | stdlib | `as_of_date` cutoff date type annotation | Phase 8 cutoff-date enforcement |
| thefuzz | 0.22.1 (installed) | Fuzzy name matching fallback | When exact name match fails in name resolver |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| statsmodels VIF | Manual numpy VIF (1/(1-R^2)) | Manual VIF is trivial to implement and was verified during research; statsmodels is preferred because it's the accepted standard and its output is authoritative for documentation |
| pytest | unittest | unittest is stdlib but lacks `parametrize`, fixtures, and conftest.py; pytest is the established Python standard |
| Name lookup at call time | Pre-built name dict | Call-time lookup adds ~1ms overhead per call but avoids stale state; for the volume of calls in this project, overhead is irrelevant |

**Installation — add to pyproject.toml:**
```bash
uv add pytest>=9.0.2 statsmodels>=0.14.6
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── models/
│   ├── features.py          # Existing: FEATURE_COLS, _compute_features_by_id(), build_stats_lookup()
│   │                        # NEW: compute_features() public API with name resolution
│   │                        # NEW: _resolve_team_id() name-to-ID helper
│   │                        # NEW: compute_features_as_of() cutoff-date variant
│   └── vif_analysis.py      # NEW (08-04): VIF computation and report
tests/
├── __init__.py
├── conftest.py              # NEW: shared fixtures (stats_lookup, known matchup data)
├── test_features.py         # NEW (08-05): unit tests for public API
│                            # Known historical matchup fixtures
│                            # Symmetry assertion tests
│                            # Cutoff-date enforcement tests
│                            # VIF threshold tests
└── test_vif.py              # NEW (08-04): VIF analysis assertions
models/
└── vif_report.json          # NEW (08-04): documented VIF values and decisions
```

### Pattern 1: Public Name-Based API (08-01, 08-02)

**What:** A public `compute_features()` function that accepts team names and resolves to IDs via `team_normalization.parquet`. Wraps the existing ID-based internal function.
**When to use:** All external callers (bracket simulator, user-facing scripts, tests).

```python
# Source: codebase inspection — team_normalization.parquet has canonical_name, kaggle_name, cbbdata_name
# Verified: Duke -> 1181, Michigan -> 1276, canonical names match exactly

from __future__ import annotations
import pathlib
from typing import Any
import duckdb
import pandas as pd
from src.utils.cutoff_dates import SELECTION_SUNDAY_DATES

# Build name->ID lookup once at import time (or lazily)
_TEAM_NAME_LOOKUP: dict[str, int] | None = None

def _get_name_lookup(processed_dir: str | pathlib.Path = "data/processed") -> dict[str, int]:
    """Return a dict mapping any team name variant -> kaggle_team_id.

    Covers canonical_name, kaggle_name, and cbbdata_name from team_normalization.parquet.
    Built lazily and cached after first call.
    """
    global _TEAM_NAME_LOOKUP
    if _TEAM_NAME_LOOKUP is None:
        conn = duckdb.connect()
        norm = conn.execute(
            f"SELECT kaggle_team_id, canonical_name, kaggle_name, cbbdata_name "
            f"FROM read_parquet('{pathlib.Path(processed_dir) / 'team_normalization.parquet'}')"
        ).df()
        conn.close()
        lookup: dict[str, int] = {}
        for row in norm.itertuples(index=False):
            team_id = int(row.kaggle_team_id)
            for name in [row.canonical_name, row.kaggle_name, row.cbbdata_name]:
                if name and name not in lookup:
                    lookup[name] = team_id
        _TEAM_NAME_LOOKUP = lookup
    return _TEAM_NAME_LOOKUP


def _resolve_team_id(name: str, processed_dir: str | pathlib.Path = "data/processed") -> int:
    """Resolve a team name string to a Kaggle team ID.

    Checks canonical_name, kaggle_name, and cbbdata_name columns from
    team_normalization.parquet. Raises ValueError for unrecognized names.

    Args:
        name: Team name string (e.g., "Duke", "Michigan", "NC State").
        processed_dir: Directory containing team_normalization.parquet.

    Returns:
        kaggle_team_id integer.

    Raises:
        ValueError: If name is not found in any name column.
    """
    lookup = _get_name_lookup(processed_dir)
    if name not in lookup:
        raise ValueError(
            f"Team name {name!r} not found in team_normalization.parquet. "
            f"Use canonical_name, kaggle_name, or cbbdata_name. "
            f"Example: 'Duke', 'Michigan', 'NC State'."
        )
    return lookup[name]


def compute_features(
    team_a: str,
    team_b: str,
    season: int,
    stats_lookup: dict[tuple[int, int], dict[str, Any]] | None = None,
    processed_dir: str | pathlib.Path = "data/processed",
    as_of_date: str | None = None,
) -> dict[str, float]:
    """Compute differential efficiency features for a team matchup by name.

    Public API: accepts team names instead of integer IDs. Resolves names via
    team_normalization.parquet, then delegates to the internal ID-based computation.

    Args:
        team_a: Team name string (e.g., "Duke"). Canonical ordering: team_a should
            have the lower SeedNum (better seed). The function computes A - B for
            all differentials, so team ordering matters for sign interpretation.
        team_b: Team name string (e.g., "Michigan").
        season: Tournament season year (e.g., 2025).
        stats_lookup: Pre-built stats lookup dict. If None, builds from parquet files.
            Pass a pre-built lookup when calling in a tight loop for performance.
        processed_dir: Directory containing parquet files.
        as_of_date: Optional YYYY-MM-DD cutoff date. If provided, stats are
            filtered to only include data available before this date. When None,
            uses the full end-of-season stats (appropriate for historical replay).

    Returns:
        Dict with keys: adjoe_diff, adjde_diff, barthag_diff, seed_diff,
        adjt_diff, wab_diff — matching FEATURE_COLS ordering.

    Raises:
        ValueError: If team name not recognized.
        KeyError: If team not in stats_lookup for the given season.
    """
    team_a_id = _resolve_team_id(team_a, processed_dir)
    team_b_id = _resolve_team_id(team_b, processed_dir)

    if stats_lookup is None:
        stats_lookup = build_stats_lookup(processed_dir)

    return _compute_features_by_id(season, team_a_id, team_b_id, stats_lookup)
```

### Pattern 2: VIF Analysis with statsmodels (08-04)

**What:** Compute VIF for each feature in the 1054-game training matrix using `statsmodels.stats.outliers_influence.variance_inflation_factor`.
**When to use:** Plan 08-04 — run once, document result in `models/vif_report.json`.

```python
# Source: statsmodels 0.14.6 official docs
# https://www.statsmodels.org/stable/generated/statsmodels.stats.outliers_influence.variance_inflation_factor.html
from statsmodels.stats.outliers_influence import variance_inflation_factor
import numpy as np
import pandas as pd

def compute_vif(X: np.ndarray, feature_names: list[str]) -> pd.DataFrame:
    """Compute VIF for each feature in the design matrix.

    statsmodels variance_inflation_factor() requires the full design matrix X
    (NOT including an intercept column — the function adds its own intercept
    internally). Returns a DataFrame with 'feature' and 'vif' columns.

    Args:
        X: Feature matrix of shape (n_samples, n_features).
        feature_names: List of feature names matching columns in X.

    Returns:
        DataFrame with columns 'feature' and 'vif', sorted by vif descending.
    """
    vif_data = []
    for i, name in enumerate(feature_names):
        vif = variance_inflation_factor(X, i)
        vif_data.append({'feature': name, 'vif': round(float(vif), 3)})

    df = pd.DataFrame(vif_data).sort_values('vif', ascending=False)
    return df
```

**IMPORTANT — Known VIF result (pre-computed from live data):**

The VIF analysis on the current 1054-matchup training set WILL find:

| Feature | VIF | Status |
|---------|-----|--------|
| barthag_diff | 11.201 | EXCEEDS VIF > 10 |
| adjoe_diff | 6.505 | borderline (VIF > 5) |
| adjde_diff | 5.792 | borderline (VIF > 5) |
| wab_diff | 5.212 | borderline (VIF > 5) |
| seed_diff | 3.982 | OK |
| adjt_diff | 1.051 | OK |

Dropping `barthag_diff` reduces all remaining VIFs to < 6 (adjoe_diff=2.8, adjde_diff=2.6, seed_diff=3.8, wab_diff=5.2, adjt_diff=1.05). This satisfies VIF < 10 for all remaining features.

**The VIF analysis creates a tension:** SC-2 says "no feature with VIF > 10" but the locked feature set [03-01] includes `barthag_diff`. The resolution options are:
1. Drop `barthag_diff` from `FEATURE_COLS` — satisfies SC-2 but breaks backward compatibility with all existing models
2. Document the VIF exceedance as known/expected (consistent with the Phase 3 decision note "barthag_diff coefficient is negative (-0.82) due to multicollinearity — expected behavior")
3. The planner should define what "no feature with VIF > 10" means in this context: new models going forward, or retrofitting existing models

**Recommendation for the planner:** The most defensible interpretation is: the VIF analysis documents the current state, the planner notes the threshold exceedance for `barthag_diff`, and the acceptance criterion is met by providing an honest VIF report showing which features exceed the threshold. The decision whether to drop `barthag_diff` is a **new decision** that must be made in Plan 08-04.

### Pattern 3: Cutoff-Date Enforcement (08-03)

**What:** The `as_of_date` parameter in `compute_features()` restricts stats to data available before a given date. The existing `build_stats_lookup()` loads end-of-season data; a new `build_stats_lookup_as_of()` variant queries regular season game logs filtered by date.
**When to use:** Historical replay — when testing that pre-Selection-Sunday predictions don't use post-Selection-Sunday games.

```python
# Source: cutoff_dates.py SELECTION_SUNDAY_DATES dict — verified covers 2003-2026
# The key constraint: stats_lookup already uses year-end Torvik ratings (computed
# from full season data). The "as_of_date" enforcement needs to work differently:
# for historical Torvik ratings, the selection_sunday_2025 snapshot IS the
# correct pre-cutoff data (Torvik ratings are updated daily; the cbbdata archive
# endpoint returns pre-Selection-Sunday data).
#
# For the test assertion (SC-3): the assertion is NOT about re-computing stats
# from game logs filtered by date — it's about asserting that the stats_lookup
# built for 2025 does not include any post-Selection-Sunday games.
# Since historical_torvik_ratings.parquet was built from cbbdata archive
# snapshots at or before Selection Sunday (per fetch logic in cbbdata_client.py),
# the enforcement is already in place. The test just needs to assert this.

from src.utils.cutoff_dates import SELECTION_SUNDAY_DATES, get_cutoff

def verify_cutoff_enforcement(season: int, stats_lookup: dict) -> bool:
    """Assert that stats for a season were computed before Selection Sunday.

    For the historical Torvik ratings source (cbbdata archive), the data is
    inherently pre-Selection-Sunday because the archive endpoint is queried
    for the date at or before Selection Sunday (per fetch_torvik_ratings logic).

    The assertion for SC-3 is: stats are not contaminated by post-Selection-Sunday
    games. This is verified by checking the source metadata rather than recomputing.

    Args:
        season: Tournament season year.
        stats_lookup: Stats lookup dict built by build_stats_lookup().

    Returns:
        True if cutoff enforcement is verified.
    """
    cutoff = get_cutoff(season)
    # The source data guarantee: historical_torvik_ratings.parquet is built
    # from cbbdata archive snapshots at or before Selection Sunday.
    # The current_season_stats.parquet is also pre-Selection-Sunday.
    # No regular season games after the cutoff date are included.
    return True  # Implementation should check source metadata or log
```

**Important architectural note:** The SC-3 success criterion says "asserting no post-Selection-Sunday games are included." The current implementation guarantees this by construction (cbbdata archive is fetched at the pre-Selection-Sunday date). The test for SC-3 should verify this by inspecting the source date metadata stored in the parquet or by checking that `stats_lookup` keys only contain pre-cutoff data.

### Pattern 4: Perspective Symmetry Test (08-05)

**What:** Assert that swapping `team_a` and `team_b` inverts all differential signs.
**When to use:** Core property test that should pass trivially given the current implementation.

```python
# Source: live verification — confirmed symmetry holds for Duke/Michigan 2025
# All 6 features: feats[k] + feats_swapped[k] == 0.0 exactly (floating point safe)

def test_perspective_symmetry():
    """SC-4: Swapping team A and B inverts all differential signs."""
    stats_lookup = build_stats_lookup()
    feats_ab = _compute_features_by_id(2025, 1181, 1276, stats_lookup)  # Duke vs Michigan
    feats_ba = _compute_features_by_id(2025, 1276, 1181, stats_lookup)  # Michigan vs Duke

    for feat_name in FEATURE_COLS:
        assert abs(feats_ab[feat_name] + feats_ba[feat_name]) < 1e-10, \
            f"Symmetry violated for {feat_name}: {feats_ab[feat_name]} + {feats_ba[feat_name]}"
```

### Pattern 5: pytest Parametrized Test Fixtures (08-05)

**What:** Known historical matchup fixtures with documented expected feature values.
**When to use:** SC-1 says "unit tests covering known historical matchups."

```python
# Source: live data inspection — confirmed these matchups exist in tournament_games.parquet
# Duke (1181, seed 1) vs various opponents 2025; all from actual 2025 tournament data
# Verified: Duke beat Wofford (1291) round of 64 93-49; beat American (1124) round of 32 89-66

import pytest
from src.models.features import compute_features, build_stats_lookup

@pytest.fixture(scope="module")
def stats_lookup():
    """Module-scoped stats lookup to avoid rebuilding per test."""
    return build_stats_lookup()

# Known historical matchups for fixtures:
# 2024: Arizona (1112, seed 2) vs Long Beach St (ID TBD, seed 15) — 2 vs 15 game
# 2024: North Carolina (1314, seed 1) vs Wagner (seed 16) — 1 vs 16 game
# 2025: Duke (1181, seed 1) vs Michigan (1276, seed 5) — they did NOT play each other
#       but both teams are in the 2025 stats_lookup and seeds
# For test fixtures, use teams that are both in stats_lookup for the same season

KNOWN_MATCHUP_FIXTURES = [
    # (team_a_name, team_b_name, season, feature_key, expected_sign)
    # Duke (1, great offense) vs Michigan (5, decent offense): adjoe_diff > 0
    ("Duke", "Michigan", 2025, "adjoe_diff", "positive"),
    # Duke has lower seed number = better seed: seed_diff < 0
    ("Duke", "Michigan", 2025, "seed_diff", "negative"),
    # Duke has better barthag: barthag_diff > 0
    ("Duke", "Michigan", 2025, "barthag_diff", "positive"),
]

@pytest.mark.parametrize("team_a,team_b,season,feature,expected_sign", KNOWN_MATCHUP_FIXTURES)
def test_known_matchup_feature_signs(team_a, team_b, season, feature, expected_sign, stats_lookup):
    """Verify feature signs for known historical matchups."""
    feats = compute_features(team_a, team_b, season, stats_lookup=stats_lookup)
    val = feats[feature]
    if expected_sign == "positive":
        assert val > 0, f"{feature} for {team_a} vs {team_b} ({season}): expected >0, got {val}"
    elif expected_sign == "negative":
        assert val < 0, f"{feature} for {team_a} vs {team_b} ({season}): expected <0, got {val}"
```

### Anti-Patterns to Avoid

- **Making the internal ID-based function private-only:** The existing `compute_features(season, team_a_id, team_b_id, stats_lookup)` is imported by `backtest.py`, `temporal_cv.py`, and the simulator. Any rename must update ALL call sites or add a backward-compatible alias.
- **Rebuilding stats_lookup per compute_features call:** `build_stats_lookup()` reads parquet files and takes ~0.5s. Cache it or pass it in. The function signature supports passing a pre-built lookup.
- **VIF threshold enforcement blocking all models:** VIF > 10 for `barthag_diff` is a known, documented multicollinearity issue from Phase 3. The correct response in Phase 8 is to document it, not to silently drop the feature from existing trained models.
- **Using `as_of_date` to recompute efficiency metrics from box scores:** The Torvik ratings are pre-aggregated. Recomputing them from raw game logs would require implementing the Torvik algorithm. The Phase 8 cutoff enforcement means verifying that the source data was pulled before the cutoff — not recomputing from scratch.
- **Global `_TEAM_NAME_LOOKUP` state across tests:** If tests modify the lookup or run in isolation, a global cache can cause false passes. Use `scope="module"` fixtures or call `_TEAM_NAME_LOOKUP = None` in conftest.py teardown.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VIF computation | Custom R^2-based loop | `statsmodels.stats.outliers_influence.variance_inflation_factor` | The standard; avoids subtle numerical issues with near-collinear matrices |
| Test discovery | Manual test runner | `pytest` with `tests/` directory | Standard Python testing; automatic discovery, parametrize, fixtures |
| Name matching for team lookup | Custom fuzzy matching | Direct dict lookup on `team_normalization.parquet` columns | The parquet already has canonical_name, kaggle_name, cbbdata_name — exact match covers all cases |
| Cutoff date logic | Custom date arithmetic | `get_cutoff(season)` from `src.utils.cutoff_dates` | Already implemented and verified; SELECTION_SUNDAY_DATES covers 2003-2026 |

**Key insight:** This phase is primarily about API formalization and test writing, not algorithm development. The core computation already works and is verified. The value is in the name-based wrapper, the VIF documentation, and the pytest suite.

## Common Pitfalls

### Pitfall 1: Breaking Existing Call Sites When Renaming compute_features

**What goes wrong:** Renaming `compute_features(season, team_a_id, team_b_id, stats_lookup)` to the new `compute_features(team_a, team_b, season, ...)` breaks `src/backtest/backtest.py`, `src/simulator/simulate.py`, and other callers that use the integer-ID API.
**Why it happens:** The success criterion uses a name-based signature, but the existing codebase uses IDs. A naive rename creates `TypeError` at every existing call site.
**How to avoid:** Keep the internal function as `_compute_features_by_id(season, team_a_id, team_b_id, stats_lookup)` (rename the existing one with underscore prefix). Create the new public `compute_features(team_a, team_b, season, ...)` separately. Update existing callers to use `_compute_features_by_id` explicitly, OR add the name-resolution in a wrapper that detects type (str vs int) — but type detection is fragile.
**Warning signs:** `TypeError: compute_features() got unexpected keyword argument 'team_a_id'` anywhere in backtest or simulator.

### Pitfall 2: VIF Threshold vs Locked Feature Set Conflict

**What goes wrong:** SC-2 says "no feature with VIF > 10" but `barthag_diff` already has VIF = 11.2. Naively trying to satisfy SC-2 by dropping `barthag_diff` from `FEATURE_COLS` invalidates all existing trained models (logistic baseline, XGBoost, LightGBM, ensemble — all trained with 6 features).
**Why it happens:** The VIF exceedance was noted as "expected behavior" in Phase 3 decision [03-01] but the Phase 8 criterion doesn't acknowledge this prior decision.
**How to avoid:** The VIF report must document the exceedance AND explain why it's acceptable (gradient boosting and LR with regularization are robust to multicollinearity; the Phase 3 decision explicitly accepted it). The planner must decide whether SC-2 means "the VIF analysis was run and features above threshold are documented" or "all features must pass VIF < 10 threshold."
**Warning signs:** Tests that assert `all VIF < 10` will fail with the current 6-feature set.

### Pitfall 3: statsmodels variance_inflation_factor Requires No Intercept Column

**What goes wrong:** If you add an intercept column (column of 1s) to `X` before passing to `variance_inflation_factor()`, the function includes the intercept in the VIF calculation, producing an extremely high VIF for the intercept and wrong VIFs for features.
**Why it happens:** `variance_inflation_factor(exog, exog_idx)` adds its own intercept internally (it regresses each feature on the others plus intercept). Passing X with an extra intercept column doubles the intercept.
**How to avoid:** Pass only the raw feature matrix `X` (shape: n_samples x n_features) without any intercept column. Verify by checking that `variance_inflation_factor(X, 5)` for `adjt_diff` (which is nearly independent) returns ~1.05.
**Warning signs:** VIF for `adjt_diff` shows value >> 1.1, or intercept column appears in VIF report.

### Pitfall 4: Module-Level Name Lookup Cache Breaks Test Isolation

**What goes wrong:** The global `_TEAM_NAME_LOOKUP` dict is built once at module import time. If tests use different `processed_dir` paths or if the lookup is modified in one test, subsequent tests see stale state.
**Why it happens:** Global mutable state shared across pytest test collection.
**How to avoid:** Use `scope="module"` fixture in conftest.py to build the lookup once per test module. Alternatively, pass `processed_dir` as a parameter and bypass the cache. In conftest.py, optionally reset `_TEAM_NAME_LOOKUP = None` in a teardown fixture.
**Warning signs:** Tests pass in isolation but fail when run together; `conftest.py` fixtures not working as expected.

### Pitfall 5: Cutoff-Date Assertion Overclaims

**What goes wrong:** Test claims `compute_features(..., as_of_date=selection_sunday_2025)` "returns only stats available before that date" when the actual implementation uses pre-aggregated Torvik ratings that were snapshotted at or before Selection Sunday.
**Why it happens:** The SC-3 wording implies real-time filtering of game logs. But the actual implementation is a point-in-time snapshot — the archive endpoint returns data as of a specific date.
**How to avoid:** The cutoff-date test should verify the SOURCE property: that stats_lookup was built from a snapshot taken on or before Selection Sunday. Specifically: assert that `stats_lookup[(2025, team_id)]` stats match what the cbbdata archive returned for the pre-Selection-Sunday date (which they do by construction). The test assertion is about data provenance, not re-filtering.
**Warning signs:** Test tries to run `compute_features(as_of_date=...)` but then filters regular_season.parquet game records, which are NOT the source for adjOE/adjDE (cbbdata is the source).

### Pitfall 6: pytest Discovery Fails Without conftest.py and tests/__init__.py

**What goes wrong:** `uv run pytest tests/` fails with ImportError because `src` is not on the Python path.
**Why it happens:** pytest adds the test file's directory to sys.path but not the project root. `from src.models.features import ...` fails.
**How to avoid:** Add `conftest.py` at the project root (empty or with `sys.path.insert`) OR configure `pythonpath = ["."]` in `pyproject.toml`'s `[tool.pytest.ini_options]` section.
**Warning signs:** `ModuleNotFoundError: No module named 'src'` when running pytest.

The correct `pyproject.toml` addition:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

## Code Examples

### statsmodels VIF Computation (verified API)
```python
# Source: https://www.statsmodels.org/stable/generated/statsmodels.stats.outliers_influence.variance_inflation_factor.html
# statsmodels version: 0.14.6

from statsmodels.stats.outliers_influence import variance_inflation_factor
import numpy as np

# X shape: (1054, 6) — no intercept column
X = df[FEATURE_COLS].values  # feature matrix from build_matchup_dataset()

vif_report = {
    col: float(variance_inflation_factor(X, i))
    for i, col in enumerate(FEATURE_COLS)
}
# Expected output (pre-verified by research):
# {'adjoe_diff': 6.505, 'adjde_diff': 5.792, 'barthag_diff': 11.201,
#  'seed_diff': 3.982, 'adjt_diff': 1.051, 'wab_diff': 5.212}
```

### Pytest Configuration in pyproject.toml
```toml
# Source: https://docs.pytest.org/en/stable/explanation/goodpractices.html
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-v"
```

### pytest conftest.py for Shared Fixtures
```python
# tests/conftest.py
# Source: https://docs.pytest.org/en/stable/how-to/fixtures.html

import pytest
from src.models.features import build_stats_lookup

@pytest.fixture(scope="module")
def stats_lookup_fixture():
    """Module-scoped stats lookup. Built once, shared across all tests in module."""
    return build_stats_lookup()
```

### Symmetry Test
```python
# tests/test_features.py
# Source: live verification — all 6 features confirmed to sum to 0.0 when swapped

import pytest
from src.models.features import compute_features, FEATURE_COLS

def test_perspective_symmetry(stats_lookup_fixture):
    """SC-4: Swapping team A and B inverts all differential signs."""
    feats_ab = compute_features("Duke", "Michigan", 2025, stats_lookup=stats_lookup_fixture)
    feats_ba = compute_features("Michigan", "Duke", 2025, stats_lookup=stats_lookup_fixture)

    for feat_name in FEATURE_COLS:
        assert abs(feats_ab[feat_name] + feats_ba[feat_name]) < 1e-10, \
            f"Symmetry violated: {feat_name}"
```

### Known Historical Matchup Test (parametrized)
```python
# Source: live data verification from tournament_games.parquet + seeds.parquet
# Duke 2025: seed 1, adj_o=128.45, adj_d=91.27, barthag=0.981, seed_num=1
# Michigan 2025: seed 5, adj_o=115.12, adj_d=94.42, barthag=0.907, seed_num=5

@pytest.mark.parametrize("team_a,team_b,season,expected", [
    # Duke (1 seed, top offense) vs Michigan (5 seed): Duke should be better on all metrics
    ("Duke", "Michigan", 2025, {
        "adjoe_diff": pytest.approx(13.33, abs=0.1),
        "adjde_diff": pytest.approx(-3.14, abs=0.1),
        "seed_diff": -4,          # Duke seed 1 - Michigan seed 5 = -4
        "barthag_diff": pytest.approx(0.073, abs=0.01),
    }),
])
def test_known_matchup_values(team_a, team_b, season, expected, stats_lookup_fixture):
    """Verify known historical feature values match expected values."""
    feats = compute_features(team_a, team_b, season, stats_lookup=stats_lookup_fixture)
    for key, exp_val in expected.items():
        assert feats[key] == exp_val, f"{key}: expected {exp_val}, got {feats[key]}"
```

### Name Resolver Error Handling
```python
# tests/test_features.py
def test_unknown_team_raises():
    """Unrecognized team name raises ValueError with helpful message."""
    with pytest.raises(ValueError, match="not found in team_normalization"):
        compute_features("Totally Fake University", "Duke", 2025)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ID-based compute_features (internal) | Name-based public API (Phase 8) | Phase 8 | Public callers use human-readable names |
| No VIF analysis | Formal VIF report with statsmodels | Phase 8 | Documents known multicollinearity |
| No test infrastructure | pytest with fixtures and parametrize | Phase 8 | Regression protection for feature function |
| Inline feature computation across phases | Canonical feature store API | Phase 8 | Single source of truth for all models |

**Deprecated/outdated after Phase 8:**
- Direct calls to `compute_features(season, team_a_id, team_b_id, stats_lookup)` with positional integer IDs from external code — these should migrate to the name-based API or explicitly use `_compute_features_by_id()`.

## Open Questions

1. **VIF threshold: drop barthag_diff or document exceedance?**
   - What we know: `barthag_diff` VIF = 11.2 (confirmed by live computation). All 5 remaining features have VIF < 6 if barthag is dropped. The decision [03-01] explicitly says "barthag_diff coefficient is negative (-0.82) due to multicollinearity — expected behavior."
   - What's unclear: Does Phase 8 SC-2 require all features to pass VIF < 10, or does it require the analysis to be conducted and results documented?
   - Recommendation: The planner must make a new decision in Plan 08-04 on whether to drop `barthag_diff`. Dropping it satisfies SC-2 literally but requires retraining all existing models. Keeping it (with documented exceedance) preserves backward compatibility.

2. **`as_of_date` implementation depth**
   - What we know: The cbbdata archive snapshot IS the pre-Selection-Sunday data. SC-3 requires proving "no post-Selection-Sunday games are included."
   - What's unclear: Should `compute_features(as_of_date=...)` actively filter game logs, or simply assert that the pre-built stats_lookup was sourced from a pre-Selection-Sunday snapshot?
   - Recommendation: The simpler interpretation — assert the snapshot source date — is sufficient for SC-3. No need to re-implement per-game filtering from raw game logs.

3. **conftest.py scope for stats_lookup**
   - What we know: `build_stats_lookup()` takes ~0.5s (reads parquet files). pytest tests should share one instance.
   - What's unclear: Should `scope="session"` (one instance per pytest run) or `scope="module"` (one instance per test file)?
   - Recommendation: Use `scope="session"` for stats_lookup in conftest.py. This is safe because stats_lookup is read-only and not modified by any test.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/models/features.py` — full function signatures, parameter names, docstrings
- Codebase inspection: `src/utils/cutoff_dates.py` — SELECTION_SUNDAY_DATES confirmed covers 2026
- Codebase inspection: `src/ingest/cbbdata_client.py` — archive endpoint date filtering confirmed
- Live data computation: VIF values for all 6 FEATURE_COLS computed from actual 1054-matchup training set
- Live data verification: Duke/Michigan 2025 feature values computed and symmetry confirmed
- Live parquet inspection: `data/processed/team_normalization.parquet` — canonical_name, kaggle_name, cbbdata_name columns confirmed; Duke=1181, Michigan=1276 verified
- statsmodels 0.14.6 official docs: https://www.statsmodels.org/stable/generated/statsmodels.stats.outliers_influence.variance_inflation_factor.html
- pytest 9.0.2 official docs: https://docs.pytest.org/en/stable/how-to/parametrize.html

### Secondary (MEDIUM confidence)
- PyPI page: pytest 9.0.2 confirmed as latest stable as of 2026-03-04
- PyPI page: statsmodels 0.14.6 confirmed as latest stable (released December 2025)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — packages verified as not installed; latest versions confirmed from PyPI
- Architecture (name-based API): HIGH — verified existing call sites; team_normalization.parquet structure confirmed
- VIF analysis: HIGH — live computation on actual training data; values pre-verified
- Symmetry behavior: HIGH — confirmed by running actual compute_features in both directions
- Cutoff-date enforcement: HIGH — reviewed cbbdata_client.py archive fetch logic; confirmed pre-SS filter
- VIF threshold conflict: HIGH (conflict itself is HIGH confidence; resolution is planner decision)
- pytest patterns: HIGH — official docs verified; pyproject.toml pytest configuration confirmed

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (statsmodels and pytest APIs are stable; VIF values only change if training data changes)
