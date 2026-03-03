---
phase: 02-current-season-and-bracket-data
verified: 2026-03-03T05:17:49Z
status: passed
score: 4/4 must-haves verified
gaps: []
human_verification:
  - test: "Run ESPN auto-fetch on or after Selection Sunday (2026-03-15)"
    expected: "fetch_espn_bracket() returns exactly 68 teams with team_espn_name, espn_team_id, seed, region; load_bracket() returns the ESPN data without falling through to CSV"
    why_human: "ESPN bracket data is only available post-Selection-Sunday; today is 2026-03-03 and the bracket hasn't been announced — no automated test can validate live ESPN return of 68 teams"
  - test: "Run verify_bracket_stats_coverage() with the real 68-team 2026 bracket after Selection Sunday"
    expected: "68/68 bracket teams resolve to kaggle_team_id and all have barthag, adj_o, adj_d in current_season_stats.parquet"
    why_human: "Can only confirm full 68-team coverage once real bracket teams are known; today's proxy test used 64 teams with espn_name populated"
---

# Phase 2: Current Season and Bracket Data — Verification Report

**Phase Goal:** 2025-26 season stats are available in the database via CBBpy and cbbdata, and an auto-fetch pipeline is ready to pull the 68-team bracket from ESPN on Selection Sunday with a tested manual CSV fallback.

**Verified:** 2026-03-03T05:17:49Z
**Status:** PASSED (4/4 automated must-haves verified; 2 items require human verification on/after Selection Sunday)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `get_cutoff(2026)` returns `'2026-03-15'` without raising ValueError | VERIFIED | Function executed, returned `'2026-03-15'`; `2026` present in `SELECTION_SUNDAY_DATES` dict |
| 2 | Running the cbbdata ingestion script populates per-team adjOE, adjDE, barthag for all D1 teams in `current_season_stats.parquet` | VERIFIED | `data/processed/current_season_stats.parquet` has 364 rows; 364/364 have barthag, adj_o, adj_d non-null; 364/364 match rate to normalization table |
| 3 | The bracket auto-fetch script returns a structured seedings DataFrame from ESPN (when available) and falls through to CSV with identical schema when not | VERIFIED | `fetch_espn_bracket()` returns empty DataFrame with correct schema pre-Selection-Sunday; `load_bracket(auto_fetch=True, csv_path=populated_csv)` returns 68 teams from CSV with schema `[team_espn_name, espn_team_id, seed, region]`; fallback chain tested end-to-end |
| 4 | `team_normalization.parquet` has `espn_slug` and `cbbdata_name` populated for the majority of D1 teams | VERIFIED | 360/381 teams have `espn_slug`; 362/381 teams have `cbbdata_name`; 64/381 have `espn_name`; 100% tournament team coverage maintained (273/273 teams) |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/utils/cutoff_dates.py` | `SELECTION_SUNDAY_DATES` dict includes 2026; `get_cutoff` raises ValueError with 2026 in valid range message | VERIFIED | 2026 entry present; error message reads "Valid seasons: 2003-2019, 2021-2026 (2020 cancelled)." |
| `src/ingest/cbbdata_client.py` | Exports `get_cbbdata_token`, `fetch_torvik_ratings`, `fetch_cbbdata_teams`, `ingest_current_season_stats`; uses requests with retry; reads Parquet bytes | VERIFIED | All 4 exports present and callable; HTTPAdapter with Retry(3) wired; `pd.read_parquet(BytesIO(response.content))` for data endpoints; 148 lines |
| `data/processed/current_season_stats.parquet` | 300+ D1 teams with barthag, adj_o, adj_d; all rows have kaggle_team_id | VERIFIED | 364 teams; 364/364 non-null barthag, adj_o, adj_d, adj_t, wab; 364/364 have kaggle_team_id (100% match rate); year=2025 (2024-25 proxy — known accepted limitation) |
| `data/processed/team_normalization.parquet` | `espn_slug` populated for 200+ teams; `cbbdata_name` populated for 200+ teams | VERIFIED | 360/381 with espn_slug; 362/381 with cbbdata_name; exceeds 200-team threshold; 100% tournament coverage maintained |
| `src/ingest/fetch_bracket.py` | Exports `fetch_espn_bracket`, `load_bracket_csv`, `load_bracket`, `resolve_bracket_teams`, `verify_bracket_stats_coverage` | VERIFIED | All 5 exports present and callable; 741 lines; no stub patterns |
| `data/seeds/bracket_manual.csv` | Header-only template with columns `team_espn_name,espn_team_id,seed,region` | VERIFIED | File exists; 1 line (header only); header matches expected schema |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ingest/cbbdata_client.py` | `data/processed/current_season_stats.parquet` | `fetch_torvik_ratings()` -> `ingest_current_season_stats()` -> DuckDB COPY TO parquet | WIRED | `ingest_current_season_stats()` calls `fetch_torvik_ratings()`, joins to normalization, writes via `duckdb COPY ... TO ... (FORMAT parquet, COMPRESSION zstd)` |
| `src/ingest/cbbdata_client.py` | `data/processed/team_normalization.parquet` | `fetch_cbbdata_teams()` -> `update_normalization_with_cbbdata()` in `build_team_table.py` | WIRED | `update_normalization_with_cbbdata()` calls `fetch_cbbdata_teams()`, extracts `torvik_team`, `espn_slug`, `espn_display`, merges and writes updated normalization |
| `data/processed/current_season_stats.parquet` | `data/processed/team_normalization.parquet` | `cbbdata_name` column join | WIRED | `ingest_current_season_stats()` uses 4-pass cascade matching (cbbdata_name, canonical_name, kaggle_name, fuzzy); 364/364 teams matched |
| `src/ingest/fetch_bracket.py` | ESPN scoreboard URL | `requests.Session.get` with `dates`, `groups=100`, `limit=200` | WIRED | `fetch_espn_bracket()` calls ESPN URL with correct params; gracefully returns empty DataFrame with correct schema when 0 events returned |
| `src/ingest/fetch_bracket.py` | `data/processed/team_normalization.parquet` | `resolve_bracket_teams()` loads parquet and maps via espn_name, canonical_name, espn_slug, fuzzy | WIRED | 4-pass resolution tested: 4/4 real ESPN names resolved; 64/64 in proxy end-to-end test |
| `src/ingest/fetch_bracket.py` | `data/processed/current_season_stats.parquet` | `verify_bracket_stats_coverage()` joins bracket `kaggle_team_id` to stats | WIRED | Function loads stats parquet, checks barthag/adj_o/adj_d non-null per bracket team; 64/64 proxy test passed |
| `load_bracket()` fallback chain | `load_bracket_csv()` | When `fetch_espn_bracket()` returns <68 rows, falls through to CSV | WIRED | Tested: ESPN returns 0 -> `load_bracket()` calls `load_bracket_csv()` -> returns 68 teams from CSV; identical schema `[team_espn_name, espn_team_id, seed, region]` |

---

### Requirements Coverage

| Requirement | Status | Notes |
|-------------|--------|-------|
| DATA-02: Current 2025-26 season stats pulled from cbbdata APIs | SATISFIED | `current_season_stats.parquet` has 364 D1 teams with barthag, adj_o, adj_d, adj_t, wab. Note: data is 2024-25 season proxy (year=2025) because cbbdata has not indexed 2025-26 as of 2026-03-03 — known accepted limitation |
| DATA-04: Auto-fetch 68-team bracket from ESPN unofficial API with manual CSV fallback | SATISFIED (infrastructure) | ESPN auto-fetch pipeline built and tested; returns 0 teams before Selection Sunday (expected); CSV fallback validated end-to-end; full 68-team ESPN path requires human verification post-March-15 |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/normalize/build_team_table.py` | 121 | `# espn_slug and ncaa_name are not in the seed CSV yet — add as empty placeholders` — comment uses word "placeholder" | Info | Not a stub — it's a code comment explaining intent. `espn_slug` is now populated (360 teams) by Phase 2; the comment is accurate but slightly stale. No functional impact. |

No blocker or warning anti-patterns found. The single match is an informational comment, not a stub implementation.

---

### Human Verification Required

#### 1. ESPN Auto-Fetch with Real 2026 Bracket

**Test:** On or after Selection Sunday (2026-03-15), run:
```
uv run python -c "
from src.ingest.fetch_bracket import fetch_espn_bracket
df = fetch_espn_bracket()
print(f'ESPN returned {len(df)} teams')
assert len(df) == 68, f'Expected 68 teams, got {len(df)}'
print(df.to_string(index=False))
"
```
**Expected:** Returns exactly 68 rows with `team_espn_name`, `espn_team_id` (real ESPN IDs), `seed` (1-16), `region` (East/West/Midwest/South).

**Why human:** ESPN bracket data is only available post-Selection-Sunday. Today is 2026-03-03 — the bracket has not been announced. No automated test can validate live 68-team ESPN return before that date.

#### 2. Full 68-Team Stats Coverage with Real 2026 Bracket

**Test:** After ESPN auto-fetch succeeds, run:
```
uv run python -c "
from src.ingest.fetch_bracket import load_bracket, resolve_bracket_teams, verify_bracket_stats_coverage
bracket = load_bracket()
assert len(bracket) == 68
resolved = resolve_bracket_teams(bracket)
total, with_stats, missing = verify_bracket_stats_coverage(resolved)
assert len(missing) == 0, f'Missing stats: {missing}'
print(f'Phase 2 Success Criteria 2, 3, 4: ALL PASS ({with_stats}/{total})')
"
```
**Expected:** All 68 real 2026 bracket teams resolve to `kaggle_team_id` and all have `barthag`, `adj_o`, `adj_d` in `current_season_stats.parquet`.

**Why human:** Requires real bracket teams to be known (post-Selection-Sunday). Today's proxy test used 64 teams with `espn_name` populated — close proxy but not the actual 2026 bracket teams.

---

### Important Context Notes

**Known Accepted Limitation — 2024-25 proxy data:**
`current_season_stats.parquet` contains year=2025 data (2024-25 season end snapshot from 2025-03-16). This is because cbbdata has not indexed 2025-26 season ratings as of 2026-03-03. The archive fallback in `fetch_torvik_ratings()` is correctly implemented and documented. This limitation was acknowledged in the project brief and does not block downstream phases. When cbbdata indexes 2025-26 data, re-running `ingest_current_season_stats()` will refresh the file.

**Known Accepted Limitation — ESPN bracket pre-Selection-Sunday:**
`fetch_espn_bracket()` returns 0 teams today (expected, not an error). The full 68-team auto-fetch can only be validated on/after 2026-03-15. The infrastructure is verified structurally; the live test is a human verification item.

---

### Gaps Summary

No gaps. All four automated must-haves are verified. Two items are flagged for human verification on/after Selection Sunday, which was known and accepted at plan time.

The phase delivers exactly what was promised:
- Efficiency metrics (barthag, adjOE, adjDE) for 364 D1 teams at 100% normalization match rate
- ESPN auto-fetch pipeline ready for Selection Sunday
- CSV fallback with identical schema, validated end-to-end
- Team resolution and stats coverage verification functions wired and tested

---

_Verified: 2026-03-03T05:17:49Z_
_Verifier: Claude (gsd-verifier)_
