"""Shared pytest fixtures for the madness2026 test suite."""
import pytest
from src.models.features import build_stats_lookup


@pytest.fixture(scope="session")
def stats_lookup():
    """Session-scoped stats lookup dict. Built once, shared across all tests.

    Read-only dict keyed by (season, kaggle_team_id) -> stat dict.
    Safe to share because no test modifies it.
    """
    return build_stats_lookup()


@pytest.fixture(autouse=True)
def reset_name_cache():
    """Reset the module-level name lookup cache before each test."""
    import src.models.features as features_mod
    features_mod._TEAM_NAME_LOOKUP = None
    yield
    features_mod._TEAM_NAME_LOOKUP = None
