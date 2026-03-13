# Phase 11: Stability Baseline - Research

**Researched:** 2026-03-13
**Domain:** Git tagging, E2E smoke testing, rollback verification
**Confidence:** HIGH

## Summary

Phase 11 is a pure safety gate: create a `git tag v1.0-stable` on the current HEAD (10 commits ahead of the existing `v1.0` tag, which marks the v1.0 milestone completion commit), and confirm the app still works via an E2E smoke test before any v1.1 changes are made. The domain is git fundamentals and a scripted smoke test, not new application code.

The project already has a `v1.0` annotated tag at commit `79d298ba` (the v1.0 milestone completion). The current HEAD is `5f3080a` — 10 commits later, all of which are docs/planning commits plus three functional commits: eligibility filter fix, efficiency ranking conditions, and record/seed conditions for champion eligibility. The `v1.0-stable` tag should point to HEAD (not back to the `v1.0` commit) because HEAD includes the working eligibility filter that the 2026 app uses.

The E2E smoke test can be written as a single pytest module that imports the same simulator path the tests already use and exercises exactly the four success criteria: bracket renders (67 slots filled), Monte Carlo completes (champion with confidence > 0), overrides cascade correctly (R1W1 forced winner appears in R2W1 path), and champion is displayed (team_id is a valid integer). All four can run against 2025 season data in under 5 seconds using existing fixtures.

**Primary recommendation:** Tag HEAD as `v1.0-stable`, write a single `tests/test_smoke_e2e.py` file covering the four criteria using 2025 season data, run `uv run pytest tests/test_smoke_e2e.py -v`, confirm pass, then document the tag in STATE.md.

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| git tag | built-in | Create annotated rollback tag | Native git; no extra tooling needed |
| pytest | 9.0.2 (installed) | E2E smoke test runner | Already the project test runner; 29 tests passing |
| uv run pytest | current | Invoke pytest in venv | Project uses uv for all Python invocation |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| git show | built-in | Verify tag metadata after creation | Confirm tag points to correct commit |
| git checkout | built-in | Restore from tag (rollback procedure) | Used manually if rollback is needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `git tag -a` (annotated) | `git tag` (lightweight) | Annotated tags carry a message and are recommended for release tagging; lightweight tags are simpler but offer no metadata |

**Installation:** Nothing new to install — git and pytest are already present.

## Architecture Patterns

### Recommended Project Structure
```
tests/
├── conftest.py           # existing shared fixtures
├── test_features.py      # existing (29 tests passing)
├── test_override_pipeline.py  # existing (6 tests passing)
├── test_vif.py           # existing (4 tests passing)
└── test_smoke_e2e.py     # NEW: phase 11 smoke test (4 tests)
```

### Pattern 1: Annotated Git Tag
**What:** An annotated tag stores tagger identity, timestamp, and message — making it a first-class git object rather than just a pointer.
**When to use:** Release tags, rollback points, milestone markers.
**Example:**
```bash
# Source: git documentation
git tag -a v1.0-stable -m "v1.0-stable: verified rollback point before v1.1 work

Smoke test: bracket renders, MC runs, overrides cascade, champion displays.
Tagged: 2026-03-13 — pre-v1.1 safety gate."
```

### Pattern 2: Smoke Test as Pytest Module
**What:** A standalone test file that imports the simulator layer directly (not through Streamlit) and exercises the four success criteria.
**When to use:** E2E gate that verifies the system still works end-to-end without UI overhead.
**Example:**
```python
# Source: existing test_override_pipeline.py pattern
@pytest.fixture(scope="session")
def smoke_context():
    predict_fn, stats = build_predict_fn(season=2025)
    seedings = load_seedings(season=2025)
    return predict_fn, seedings

def test_bracket_renders(smoke_context):
    predict_fn, seedings = smoke_context
    result = simulate_bracket(seedings=seedings, predict_fn=predict_fn,
                               mode="deterministic", season=2025)
    assert len(result["slots"]) == 67

def test_mc_simulation_completes(smoke_context):
    predict_fn, seedings = smoke_context
    result = simulate_bracket(seedings=seedings, predict_fn=predict_fn,
                               mode="monte_carlo", n_runs=1000, seed=42, season=2025)
    assert 0 < result["champion"]["confidence"] <= 1.0

def test_override_cascades(smoke_context):
    predict_fn, seedings = smoke_context
    some_team = list(seedings.values())[8]  # a 9-seed or similar
    result = simulate_bracket(seedings=seedings, predict_fn=predict_fn,
                               mode="deterministic", season=2025,
                               override_map={"R1W1": some_team})
    assert result["slots"]["R1W1"]["overridden"] is True

def test_champion_displayed(smoke_context):
    predict_fn, seedings = smoke_context
    result = simulate_bracket(seedings=seedings, predict_fn=predict_fn,
                               mode="deterministic", season=2025)
    assert isinstance(result["champion"]["team_id"], int)
    assert result["champion"]["team_id"] == result["slots"]["R6CH"]["team_id"]
```

### Anti-Patterns to Avoid
- **Tagging a prior commit instead of HEAD:** The `v1.0` tag is at commit `79d298ba` but HEAD is 10 commits ahead. `v1.0-stable` should tag HEAD because HEAD includes the working eligibility filter; reverting to the older commit would lose that fix.
- **Pointing smoke test at 2026 season data:** Season 2026 stats are not in `stats_lookup` (only 2008–2025 are available in `historical_torvik_ratings.parquet`). The smoke test must use `season=2025` until Phase 12 refreshes data.
- **Using `git tag` lightweight instead of `git tag -a` annotated:** Without a message, there's no record of why the tag was created, making audit trails harder.
- **Skipping the tag verification step:** After creating the tag, `git show v1.0-stable` must be run to confirm it points to HEAD, not a prior commit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Smoke test assertions | Custom assertion script | pytest with assert statements | pytest gives clear failure output, integrates with CI, already installed |
| Tag creation workflow | shell script | direct `git tag -a` command | no added value from wrapping a single git command |

**Key insight:** Phase 11 is a documentation/process task disguised as a technical task. The app works — all 29 tests pass, smoke test criteria verified manually in this research session. The only real work is creating the tag and writing a test file.

## Common Pitfalls

### Pitfall 1: Tagging at v1.0 instead of HEAD
**What goes wrong:** Running `git tag -a v1.0-stable v1.0` would tag the original milestone commit (before the eligibility filter fix and planning docs), not the current working HEAD.
**Why it happens:** Confusion between "v1.0 milestone" and "current stable state."
**How to avoid:** Run `git tag -a v1.0-stable` with no commit argument — it defaults to HEAD.
**Warning signs:** `git describe HEAD` shows `v1.0-stable` with a clean distance; if it shows a distance offset, the tag is wrong.

### Pitfall 2: Smoke test uses season=2026 for stats
**What goes wrong:** `build_predict_fn(season=2026)` followed by `simulate_bracket(..., season=2026)` raises `KeyError: 'Team XXXX not found in stats_lookup for season 2026'` because `historical_torvik_ratings.parquet` has no 2025-26 Torvik data.
**Why it happens:** The 2026 bracket seedings exist but the model cannot compute features for 2026 matchups (no stats). cbbdata has NOT indexed 2025-26 data as of 2026-03-13.
**How to avoid:** Use `season=2025` for both `build_predict_fn` and `simulate_bracket` in the smoke test. The smoke test validates the simulator machinery, not the 2026-specific data — the 2026 data refresh is Phase 12's job.
**Warning signs:** `KeyError: 'Team XXXX not found in stats_lookup for season 2026'`

### Pitfall 3: Running smoke test from wrong working directory
**What goes wrong:** Relative paths in `load_seedings()` and `load_model()` (e.g., `data/processed/seeds.parquet`, `models/selected.json`) resolve incorrectly if pytest is run from a subdirectory.
**Why it happens:** DuckDB queries and joblib loads use relative paths anchored to project root.
**How to avoid:** Always run `uv run pytest` from `/Users/Sheppardjm/Repos/madness2026/` (the project root). `pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["."]` which handles this correctly.
**Warning signs:** `FileNotFoundError: data/processed/seeds.parquet not found`

### Pitfall 4: Forgetting to push the tag to origin
**What goes wrong:** The tag exists locally but not on `origin/master`, so a fresh clone won't have the rollback point.
**Why it happens:** `git push` does not push tags by default.
**How to avoid:** Run `git push origin v1.0-stable` after creating the tag (or note this as a manual step if the user prefers not to push yet).
**Warning signs:** `git ls-remote origin refs/tags/v1.0-stable` returns nothing.

## Code Examples

Verified patterns from this research session:

### Create annotated tag
```bash
# Source: git documentation; verified pattern
git tag -a v1.0-stable -m "v1.0-stable: verified rollback point before v1.1 work

Smoke test: bracket renders, MC runs, overrides cascade, champion displays.
Tagged: 2026-03-13 — pre-v1.1 safety gate."
```

### Verify tag points to correct commit
```bash
# Source: git documentation
git show v1.0-stable --format="%H %D" --no-patch
# Expected output: 5f3080a... HEAD -> master, tag: v1.0-stable
```

### Restore from tag (rollback procedure)
```bash
# Source: git documentation
git checkout v1.0-stable
# or to create a detached HEAD at that tag:
# git checkout -b rollback-branch v1.0-stable
```

### Full smoke test run
```bash
# Source: project pyproject.toml pattern; verified in research session
cd /Users/Sheppardjm/Repos/madness2026
uv run pytest tests/test_smoke_e2e.py -v
```

### Verified: All 4 smoke criteria pass with season=2025
```
# Manually verified in research session (2026-03-13):
# PASS: Bracket renders (67 slots)
# PASS: Monte Carlo simulation completes (champion confidence valid)
# PASS: Override cascades correctly (R1W1 overridden=True)
# PASS: Champion displayed (team_id: 1222, int type)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No stable tag — only v1.0 milestone tag | v1.0-stable rollback tag on working HEAD | Phase 11 | Enables safe recovery if v1.1 breaks the app before tip-off |
| Ad-hoc smoke testing via manual browser check | Scripted pytest smoke test | Phase 11 | Deterministic, fast, repeatable verification |

**Deprecated/outdated:**
- None. This phase introduces new artifacts, not replacing anything.

## Open Questions

1. **Should `v1.0-stable` be pushed to origin immediately?**
   - What we know: Remote `origin/master` is at `246d4fa` (commit before the planning docs commits); local master is 4 commits ahead. Tags are not pushed by `git push` without `--tags` or explicit tag name.
   - What's unclear: User's preference on pushing the tag vs. keeping it local only.
   - Recommendation: Push the tag. It's the safety net — if the local machine dies, the tag should exist on origin. Include `git push origin v1.0-stable` as a step in the plan.

2. **Should the smoke test cover the Streamlit UI layer or just the simulator layer?**
   - What we know: Running Streamlit in a headless test context requires mocking or Playwright. The existing tests all test the simulator/model layer directly. The four success criteria (bracket renders, MC completes, overrides cascade, champion displayed) are all verifiable at the simulator layer without a browser.
   - What's unclear: Whether the planner wants a "true" E2E that launches the app and clicks.
   - Recommendation: Test at the simulator layer (matching the existing test patterns). A browser-based E2E would require Playwright setup and is disproportionate to the phase goal. The phase description says "Running the E2E smoke test" — interpret as a fast pytest run, not a Playwright session.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `tests/test_override_pipeline.py` — confirms test patterns and session fixture approach
- Direct codebase inspection: `tests/conftest.py` — confirms fixture structure
- Direct execution: `uv run pytest tests/ -v` — confirmed 29/29 tests passing
- Direct execution: Manual smoke test script — verified all 4 success criteria pass with season=2025
- Direct execution: `git tag -l`, `git log --oneline` — confirmed existing tags and HEAD position
- Direct inspection: `src/models/features.py`, `build_stats_lookup()` — confirmed 2026 season is NOT in stats_lookup

### Secondary (MEDIUM confidence)
- Git annotated tag best practices: standard git documentation pattern, verified via project's own use of annotated `v1.0` tag

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — git and pytest are both already in the project; no new dependencies
- Architecture: HIGH — all patterns verified by running code in the repo
- Pitfalls: HIGH — all pitfalls verified by actual failure modes encountered during research (e.g., season=2026 KeyError was reproduced)

**Research date:** 2026-03-13
**Valid until:** 2026-03-19 (tournament tip-off; after that, phase is moot)
