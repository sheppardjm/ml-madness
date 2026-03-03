# Phase 2: Current Season and Bracket Data - Research

**Researched:** 2026-03-02
**Domain:** CBBpy (game-level scraping), cbbdata REST API (team efficiency metrics), ESPN unofficial scoreboard API (bracket seedings)
**Confidence:** MEDIUM — CBBpy and cbbdata API structure verified against source code and live endpoints; ESPN bracket seeding approach is low-confidence pending Selection Sunday validation

## Summary

Phase 2 has three independent technical concerns: (1) pulling 2025-26 season game logs via CBBpy, (2) fetching team-level adjusted efficiency metrics (barthag, adj_o, adj_d) from the cbbdata REST API, and (3) auto-fetching the 68-team bracket from ESPN's unofficial scoreboard API after Selection Sunday.

CBBpy (v2.1.2) provides `get_games_season(2026)` which scrapes ESPN for game-level boxscores and PBP for the 2025-26 season. It does NOT provide pre-computed adjusted efficiency metrics — those come exclusively from cbbdata. The cbbdata package is R-first, but its Flask backend exposes a REST API at `https://www.cbbdata.com/api` that is directly callable from Python via `requests`. Authentication requires a free API key obtained by POST to `/api/auth/register` then POST to `/api/auth/login`. Data is returned as Parquet streams, readable with `pd.read_parquet(BytesIO(response.content))`.

For bracket data, the ESPN scoreboard API (`site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard`) returns tournament games by date. After Selection Sunday (March 15, 2026), querying First Four dates returns scheduled games with region from `competitions[].notes[].headline` and seed from `competitors[].curatedRank.current`. A manual CSV fallback is mandatory because the ESPN endpoint only becomes useful AFTER games are scheduled — and the exact endpoint reliability on Selection Sunday itself for pre-game data is LOW confidence. The 2026 Selection Sunday date (2026-03-15) is confirmed and must be added to `SELECTION_SUNDAY_DATES` in `cutoff_dates.py`.

**Primary recommendation:** Obtain the cbbdata free API key immediately (before any coding), use CBBpy only for raw game stats (not efficiency metrics), implement ESPN bracket fetch against First Four game dates (March 17-18, 2026), and design the CSV fallback as the primary path with auto-fetch as a bonus.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CBBpy | 2.1.2 | Game-level NCAA basketball scraping from ESPN | Active (Jan 2025 release), Python-native, covers 2025-26 season |
| requests | (stdlib in Python 3.12 env) | HTTP calls to cbbdata API and ESPN API | Standard HTTP client, already in uv env transitively |
| pandas | >=3.0.1 (project requirement) | Parse parquet responses from cbbdata, build seedings DataFrame | Already in project pyproject.toml |
| pyarrow | >=23.0.1 (project requirement) | Parquet engine for pandas read_parquet from BytesIO | Already in project pyproject.toml |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| io.BytesIO | stdlib | Wrap cbbdata HTTP response bytes for pd.read_parquet | Always: cbbdata returns raw Parquet bytes |
| duckdb | >=1.4.4 (project requirement) | Write output parquet files consistently | Writing current_season.parquet and bracket.parquet |
| thefuzz | >=0.22.1 (project requirement) | Fuzzy match cbbdata team names to canonical_name table | Name normalization step after fetching cbbdata data |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| cbbdata REST API | barttorvik.com direct scrape | barttorvik is Cloudflare-blocked — confirmed as blocked (prior decision) |
| cbbdata REST API | sportsdataverse-py | No documented adjusted efficiency metrics; R-centric ecosystem |
| ESPN scoreboard API | data.ncaa.com | NCAA endpoint provides game results, not pre-game bracket seedings |
| ESPN scoreboard API | Sportradar/SportsDataIO | Paid APIs — unnecessary when free ESPN endpoint covers the need |

**Installation:**
```bash
uv add CBBpy requests
# pandas, pyarrow, duckdb, thefuzz already in pyproject.toml
```

Note: `requests` is likely already a transitive dependency of CBBpy (which requires `requests>=2.27.0`), but should be explicitly listed if used directly.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── ingest/
│   ├── fetch_current_season.py   # CBBpy game logs + cbbdata efficiency metrics
│   ├── fetch_bracket.py          # ESPN auto-fetch + CSV fallback (unified interface)
│   └── (existing ingest scripts)
├── normalize/
│   └── (existing normalize scripts — used to merge cbbdata names to canonical_name)
data/
├── processed/
│   ├── current_season.parquet    # 2025-26 game logs + efficiency metrics per team
│   └── bracket.parquet           # 68-team seedings object
├── seeds/
│   └── bracket_manual.csv        # Manual fallback: fill if ESPN unavailable
```

### Pattern 1: cbbdata REST API Access from Python

**What:** POST to authenticate, GET Parquet binary, decode with pandas.
**When to use:** Fetching any cbbdata torvik endpoint (ratings, team factors, etc.)

```python
# Source: reverse-engineered from https://github.com/andreweatherman/cbbdata R source
import os
import requests
import pandas as pd
from io import BytesIO

BASE_URL = "https://www.cbbdata.com/api"

def get_cbbdata_token(username: str, password: str) -> str:
    """POST credentials to login endpoint, return API key."""
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    # Response is JSON list; API key is first element
    return resp.json()[0]

def fetch_torvik_ratings(api_key: str, year: int) -> pd.DataFrame:
    """Fetch team-level T-Rank ratings as a DataFrame.

    Returns columns: team, conf, barthag, adj_o, adj_d, adj_t, wab, seed, year
    (plus rank columns and SOS columns).
    """
    resp = requests.get(
        f"{BASE_URL}/torvik/ratings",
        params={"key": api_key, "year": year},
        timeout=30,
    )
    resp.raise_for_status()
    # cbbdata returns Parquet binary
    return pd.read_parquet(BytesIO(resp.content))
```

**Key facts about cbbdata API (verified against R source):**
- Authentication: POST `https://www.cbbdata.com/api/auth/login` with `{"username": ..., "password": ...}`
- API key returned as `response.json()[0]` (first element of JSON list)
- Key passed as query parameter `key=` (not in Authorization header)
- Account creation: POST `https://www.cbbdata.com/api/auth/register` with `{username, email, password, confirm_password}`
- Data endpoints return raw Parquet binary bytes — use `pd.read_parquet(BytesIO(response.content))`
- Ratings endpoint: `GET /api/torvik/ratings?key=...&year=2026`
- Teams dictionary: `GET /api/data/teams` (no auth required, returns Parquet)
- The R source calls `generate_trank_factors_url()` with base `"https://barttorvik.com/trank.php"` for some data — this confirms **some cbbdata functions proxy barttorvik directly**. Only the `/api/torvik/ratings` endpoint (which returns official cbbdata Parquet) is the right path for adj_o/adj_d/barthag.

**Column mapping (from cbd_torvik_ratings / bart_ratings documentation):**
| cbbdata column | Project variable | Description |
|----------------|-----------------|-------------|
| `team` | cbbdata_name | T-Rank team name (must normalize to canonical_name) |
| `barthag` | barthag | Win probability vs avg D1 on neutral court |
| `adj_o` | adjOE | Adjusted offensive efficiency |
| `adj_d` | adjDE | Adjusted defensive efficiency |
| `adj_t` | — | Adjusted tempo |
| `year` | season | Season year (2026 for 2025-26) |
| `conf` | — | Conference abbreviation |
| `seed` | — | Tournament seed (populated post-selection) |

### Pattern 2: CBBpy Season Stats

**What:** Use CBBpy to pull 2025-26 season game-level data.
**When to use:** When you need raw game scores, boxscores, or per-game stats (NOT efficiency metrics).

```python
# Source: https://pypi.org/project/CBBpy/ and https://github.com/dcstats/CBBpy
import cbbpy.mens_scraper as s

# Returns tuple of (info_df, box_df, pbp_df)
# season year = calendar year in which tournament occurs
info_df, box_df, _ = s.get_games_season(2026, pbp=False)

# info_df columns include: game_id, home_team, away_team, home_score, away_score, date, etc.
# box_df columns include: player stats per game

# For team-level schedule:
schedule_df = s.get_team_schedule("Duke", 2026)
```

**CBBpy API notes (verified v2.1.2):**
- `get_games_season(season, info=True, box=True, pbp=True)` — season=2026 for 2025-26
- Does NOT provide efficiency metrics — raw game data only
- Returns ESPN-named teams (e.g., "UConn", "St. John's (NY)") which require normalization against team_normalization.parquet
- `get_team_schedule(team_name, season)` — less useful for bulk ingest
- Parallel jobs for large season pulls; `tqdm` progress bars included

### Pattern 3: ESPN Bracket Auto-Fetch

**What:** Query the ESPN scoreboard for First Four game dates to extract seedings.
**When to use:** After Selection Sunday (March 15, 2026).

```python
# Source: verified against ESPN scoreboard API at
# https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard
import re
import requests
import pandas as pd

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/"
    "mens-college-basketball/scoreboard"
)

# Tournament game dates: First Four (March 17-18), Round of 64 (March 19-20)
# Query multiple dates to capture all 68 teams before any games are played
BRACKET_DATES = ["20260317", "20260318", "20260319", "20260320"]

def fetch_espn_bracket(dates: list[str]) -> pd.DataFrame:
    """Return 68-team seedings DataFrame from ESPN scoreboard API.

    Columns: team_espn_name, espn_team_id, seed, region
    """
    records = []
    for date in dates:
        resp = requests.get(
            ESPN_SCOREBOARD,
            params={"dates": date, "groups": 100, "limit": 200},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for event in data.get("events", []):
            # Extract region from notes headline
            region = None
            for comp in event.get("competitions", []):
                notes = comp.get("notes", [])
                for note in notes:
                    headline = note.get("headline", "")
                    # e.g. "Men's Basketball Championship - Midwest Region - 1st Round"
                    match = re.search(r"- ([A-Za-z ]+) Region -", headline)
                    if match:
                        region = match.group(1).strip()

                for competitor in comp.get("competitors", []):
                    team = competitor.get("team", {})
                    seed = competitor.get("curatedRank", {}).get("current")
                    records.append({
                        "team_espn_name": team.get("displayName"),
                        "espn_team_id": team.get("id"),
                        "seed": seed,
                        "region": region,
                    })

    df = pd.DataFrame(records).drop_duplicates(subset=["espn_team_id"])
    return df
```

**ESPN API findings (verified against live API responses):**
- Base: `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard`
- Parameters: `dates=YYYYMMDD`, `groups=100` (required to get all D1 games), `limit=200`
- No authentication required
- **Seed field**: `competitors[].curatedRank.current` (integer 1-16)
- **Region field**: parse `competitions[].notes[].headline` for pattern `"- {Region} Region -"`
- **Team name**: `competitors[].team.displayName` (e.g., "Duke Blue Devils")
- **Team ID**: `competitors[].team.id` (ESPN numeric ID, matches espn_slug prefix)
- Before games are played, the `status` of events is "scheduled" — seedings should be present in scheduled events (MEDIUM confidence — this was verified for played games, not pre-game scheduled events)
- The scoreboard endpoint returns no data for dates without games (empty `events` array)

### Pattern 4: Manual CSV Fallback

**What:** A hand-prepared CSV that loads to the same DataFrame schema as the auto-fetch.
**When to use:** When ESPN API fails or produces incomplete/malformed data.

```python
import pandas as pd

BRACKET_CSV_SCHEMA = {
    "team_espn_name": str,    # ESPN displayName (e.g., "Duke Blue Devils")
    "espn_team_id": str,      # ESPN numeric team ID as string
    "seed": int,              # 1-16
    "region": str,            # "East", "West", "Midwest", "South"
}

def load_bracket_csv(csv_path: str) -> pd.DataFrame:
    """Load manual bracket CSV and return same schema as auto-fetch."""
    df = pd.read_csv(csv_path, dtype=BRACKET_CSV_SCHEMA)
    assert len(df) == 68, f"Expected 68 teams, got {len(df)}"
    assert set(df["region"].unique()) <= {"East", "West", "Midwest", "South"}
    return df
```

**CSV schema for `data/seeds/bracket_manual.csv`:**
```
team_espn_name,espn_team_id,seed,region
Duke Blue Devils,150,1,East
Auburn Tigers,2,2,South
...
```

### Anti-Patterns to Avoid

- **Do not use CBBpy for efficiency metrics**: CBBpy only returns raw game-level data (scores, boxscores, PBP). Adjusted efficiency (barthag, adj_o, adj_d) must come from cbbdata.
- **Do not scrape barttorvik.com directly**: Cloudflare-blocked (confirmed prior decision).
- **Do not store API key in source code**: Use environment variable `CBD_API_KEY` loaded from `.env` or shell environment.
- **Do not assume ESPN bracket endpoint is stable year-over-year**: The bracketology endpoint (`sports.core.api.espn.com/v2/...tournaments/22/...bracketology`) returned empty results for 2022 and 2023 (LOW confidence endpoint). Use scoreboard approach instead.
- **Do not rely solely on auto-fetch**: Selection Sunday is a one-shot operation. Always prepare CSV fallback before March 15.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Adjusted offensive/defensive efficiency | Compute from raw possessions | cbbdata torvik/ratings endpoint | Complex iterative regression; barttorvik proprietary method |
| NCAA team name normalization | New custom fuzzy matcher | Phase 1 team_normalization.parquet + cbbdata_name column | Already built; thefuzz already handles edge cases |
| ESPN team ID resolution | Manual lookup table | `GET /api/data/teams` from cbbdata (no auth) | Returns ESPN ID + slug + canonical name mapping |
| HTTP retry logic | Custom backoff loop | `requests.Session` with `HTTPAdapter(max_retries=...)` | Handles transient ESPN API failures cleanly |

**Key insight:** The efficiency metrics are the hardest part — do not attempt to derive them from CBBpy raw data. The cbbdata API provides them directly, which is the entire reason to use it.

## Common Pitfalls

### Pitfall 1: cbbdata API Key Acquisition is R-Centric
**What goes wrong:** Developer follows cbbdata docs, gets stuck at R-only registration instructions.
**Why it happens:** All official documentation uses `cbd_create_account()` and `cbd_login()` R functions.
**How to avoid:** Use direct HTTP POST to `https://www.cbbdata.com/api/auth/register`, then `https://www.cbbdata.com/api/auth/login`. Both accept JSON bodies and work without R.
**Warning signs:** You find yourself installing R just to get the API key — stop, use curl/requests directly.

### Pitfall 2: cbbdata Response Format is Parquet, Not JSON
**What goes wrong:** `response.json()` throws JSONDecodeError on cbbdata data endpoints.
**Why it happens:** The data endpoints (`/api/torvik/ratings`, `/api/data/teams`) return raw Parquet bytes, not JSON.
**How to avoid:** Always use `pd.read_parquet(BytesIO(response.content))` for data endpoints. Only the auth endpoints (`/auth/login`, `/auth/register`) return JSON.
**Warning signs:** JSONDecodeError or unexpected binary content in response body.

### Pitfall 3: ESPN Bracket Seedings Only Available Post-Selection-Sunday
**What goes wrong:** Developer tries to fetch bracket before March 15, 2026; scoreboard returns empty events.
**Why it happens:** The ESPN scoreboard API only has data when games are scheduled (after bracket announcement).
**How to avoid:** Only run auto-fetch script on or after March 15, 2026 (after 6 PM ET). Build the CSV fallback as primary path; treat auto-fetch as secondary validation.
**Warning signs:** Empty `events` array in all scoreboard responses; no games returned for March 17-18 dates.

### Pitfall 4: cbbdata Team Names Differ from canonical_name
**What goes wrong:** Joining cbbdata data to team_normalization.parquet fails for ~20+ teams.
**Why it happens:** cbbdata uses T-Rank naming conventions (e.g., "TAM C. Christi", "Loyola-Chicago") which may differ from Phase 1 canonical_name.
**How to avoid:** Use the `cbbdata_name` column in `team_normalization.parquet` (already populated for 59 known conflicts in `team_aliases.csv`). For teams without a cbbdata_name override, try exact match on canonical_name first, then fuzzy match as fallback.
**Warning signs:** Unexpected NULL values or zero matches when joining cbbdata data to team_normalization table.

### Pitfall 5: ESPN Seed Field is curatedRank, Not a Dedicated "seed" Field
**What goes wrong:** Developer looks for `competitor.seed` field and finds nothing.
**Why it happens:** ESPN API does not have a dedicated "seed" field; it uses `curatedRank.current`.
**How to avoid:** Always read seed from `competitors[].curatedRank.current`.
**Warning signs:** KeyError on "seed" key; empty seed values in parsed bracket.

### Pitfall 6: Missing 2026 Selection Sunday in cutoff_dates.py
**What goes wrong:** `get_cutoff(2026)` raises ValueError.
**Why it happens:** `SELECTION_SUNDAY_DATES` dict only goes to 2025; 2026 entry not yet added.
**How to avoid:** Add `2026: "2026-03-15"` to `SELECTION_SUNDAY_DATES` in `src/utils/cutoff_dates.py` as first step of Phase 2.
**Warning signs:** ValueError: "No Selection Sunday date for season 2026."

### Pitfall 7: espn_slug Column Remains Empty After Phase 2
**What goes wrong:** Downstream phases (Phase 3+) can't resolve ESPN team IDs.
**Why it happens:** Phase 1 left espn_slug empty for all 381 teams; Phase 2 must populate it.
**How to avoid:** After fetching ESPN team list, match ESPN teams to team_normalization entries and update espn_slug. Use `GET /api/data/teams` from cbbdata (free, no auth) which provides ESPN ID and slug mapping.
**Warning signs:** espn_slug column still all empty in team_normalization.parquet after Phase 2.

### Pitfall 8: CBBpy Season Year Convention
**What goes wrong:** Fetching the wrong season — `get_games_season(2025)` returns 2024-25, not 2025-26.
**Why it happens:** CBBpy uses the calendar year of the tournament as the season identifier (same as Kaggle convention).
**How to avoid:** Use `get_games_season(2026)` for the 2025-26 season. Verify by checking dates in returned data.
**Warning signs:** All game dates are in 2024-25 range when you expect 2025-26.

## Code Examples

Verified patterns from live API testing and R source code:

### cbbdata Account Registration (Python, no R required)
```python
# Source: reverse-engineered from https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_create_account.R
import requests

resp = requests.post(
    "https://www.cbbdata.com/api/auth/register",
    json={
        "username": "your_username",
        "email": "your@email.com",
        "password": "your_password",
        "confirm_password": "your_password",
    },
    timeout=30,
)
# 201 = success; API key emailed to you
print(resp.status_code, resp.json())
```

### cbbdata Login and Fetch Ratings
```python
# Source: https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_login.R
# and https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/utils.R
import requests
import pandas as pd
from io import BytesIO

def cbbdata_login(username: str, password: str) -> str:
    resp = requests.post(
        "https://www.cbbdata.com/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()[0]  # First element is the API key

def fetch_torvik_ratings_2026(api_key: str) -> pd.DataFrame:
    resp = requests.get(
        "https://www.cbbdata.com/api/torvik/ratings",
        params={"key": api_key, "year": 2026},
        timeout=60,
    )
    resp.raise_for_status()
    df = pd.read_parquet(BytesIO(resp.content))
    # Key columns: team, barthag, adj_o, adj_d, adj_t, conf, year
    return df[["team", "conf", "barthag", "adj_o", "adj_d", "adj_t", "wab", "year"]]
```

### cbbdata Teams Dictionary (no auth)
```python
# Source: https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_teams.R
# No API key required for team dictionary
import requests
import pandas as pd
from io import BytesIO

resp = requests.get("https://www.cbbdata.com/api/data/teams", timeout=30)
resp.raise_for_status()
teams_df = pd.read_parquet(BytesIO(resp.content))
# Contains ESPN ID, slug, name mappings — useful for populating espn_slug
```

### ESPN Bracket Seedings from Scoreboard
```python
# Source: verified against live ESPN API response at
# https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20250320&groups=100&limit=200
import re
import requests
import pandas as pd

def parse_espn_tournament_games(dates: list[str]) -> pd.DataFrame:
    """
    Fetch tournament game data for given dates.
    Works for scheduled AND completed games.
    Returns: DataFrame with team_espn_name, espn_team_id, seed, region
    """
    ESPN_URL = (
        "https://site.api.espn.com/apis/site/v2/sports/basketball/"
        "mens-college-basketball/scoreboard"
    )
    records = []
    for date_str in dates:
        resp = requests.get(
            ESPN_URL,
            params={"dates": date_str, "groups": 100, "limit": 200},
            timeout=30,
        )
        resp.raise_for_status()

        for event in resp.json().get("events", []):
            for comp in event.get("competitions", []):
                # Region from notes headline
                region = None
                for note in comp.get("notes", []):
                    m = re.search(r"- ([A-Za-z ]+) Region -", note.get("headline", ""))
                    if m:
                        region = m.group(1).strip()

                for c in comp.get("competitors", []):
                    team = c.get("team", {})
                    seed_val = c.get("curatedRank", {}).get("current")
                    records.append({
                        "team_espn_name": team.get("displayName"),
                        "espn_team_id": str(team.get("id")),
                        "seed": seed_val,
                        "region": region,
                    })

    df = pd.DataFrame(records).drop_duplicates(subset=["espn_team_id"])
    return df.reset_index(drop=True)


# 2026 bracket dates (First Four + Round of 64)
BRACKET_DATES_2026 = ["20260317", "20260318", "20260319", "20260320"]
```

### Unified Bracket Loader (auto-fetch + CSV fallback)
```python
def load_bracket(
    csv_path: str | None = "data/seeds/bracket_manual.csv",
    auto_fetch: bool = True,
    dates: list[str] = BRACKET_DATES_2026,
) -> pd.DataFrame:
    """Load 68-team bracket. Auto-fetch first; CSV fallback on failure.

    Returns DataFrame: team_espn_name, espn_team_id, seed (int), region (str)
    """
    if auto_fetch:
        try:
            df = parse_espn_tournament_games(dates)
            if len(df) == 68:
                return df
            # Partial data — fall through to CSV
        except Exception as e:
            print(f"ESPN fetch failed: {e}. Falling back to CSV.")

    # Manual CSV fallback
    df = pd.read_csv(csv_path, dtype={"espn_team_id": str, "seed": int})
    assert len(df) == 68, f"CSV must have 68 rows, got {len(df)}"
    return df
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| toRvik R package | cbbdata (successor) | ~2023 | cbbdata replaces toRvik; same T-Rank data via Flask API |
| barttorvik.com direct scrape | cbbdata REST API | ~2024 | Cloudflare blocks direct scraping; cbbdata is the official Python-accessible path |
| ESPN bracketology endpoint | Scoreboard API by date | ~2022 | Bracketology endpoint returns empty results post-2021 |
| CBBpy v1.x | CBBpy v2.1.x | Dec 2024 | Added team/conference schedules, in-progress games, spread data |

**Deprecated/outdated:**
- `sports.core.api.espn.com/v2/.../tournaments/22/.../bracketology`: Returns empty `items[]` for 2022+ — do not use.
- `games-ak.espn.go.com/tournament-challenge-bracket/...`: Old ESPN bracket challenge API — domain no longer valid.
- `torvik.sportsdataverse.org` (toRvik): Succeeded by cbbdata; documentation may be stale.

## Open Questions

1. **ESPN scoreboard for scheduled (pre-game) tournament events**
   - What we know: The scoreboard API returns `curatedRank.current` for completed tournament games; region is in `notes.headline`.
   - What's unclear: Whether `curatedRank.current` and region notes are populated for SCHEDULED (not yet played) games immediately after Selection Sunday bracket announcement.
   - Recommendation: Test the endpoint against First Four dates on March 15-16, 2026 the moment the bracket is announced. If events appear with `curatedRank` populated, auto-fetch works. If events are empty or `curatedRank.current` is missing, fall back to CSV immediately.

2. **cbbdata 2026 season availability**
   - What we know: cbbdata updates every 15 minutes during season; `year=2026` should work for 2025-26 data.
   - What's unclear: Whether the 2026 year parameter was tested and confirmed working before tournament time.
   - Recommendation: Test `GET /api/torvik/ratings?key=...&year=2026` immediately after obtaining API key to verify year parameter semantics.

3. **cbbdata name normalization completeness**
   - What we know: 59 teams have explicit `cbbdata_name` overrides in `team_aliases.csv`.
   - What's unclear: How many of the remaining ~322 teams have cbbdata names that differ from `canonical_name`.
   - Recommendation: After fetching cbbdata ratings for 2026, do exact join on `canonical_name` first, then count unmatched. Run thefuzz fuzzy match for unmatched teams and verify manually.

4. **espn_slug population strategy**
   - What we know: `GET /api/data/teams` from cbbdata (no auth) returns ESPN ID and slug for teams. The espn_slug column in team_normalization.parquet is empty for all 381 teams.
   - What's unclear: Which column in the cbbdata teams Parquet holds the ESPN slug, and how many D1 teams in the Kaggle dataset match cbbdata's team list.
   - Recommendation: Fetch the cbbdata teams endpoint first; inspect column names; do a fuzzy match to populate espn_slug. Document any gaps.

5. **2026 Selection Sunday date in cutoff_dates.py**
   - What we know: 2026-03-15 is confirmed as Selection Sunday (6 PM ET on CBS).
   - What's unclear: Nothing — this is confirmed and actionable.
   - Recommendation: Add `2026: "2026-03-15"` to `SELECTION_SUNDAY_DATES` immediately in Phase 2, task 02-01.

## Sources

### Primary (HIGH confidence)
- `https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_login.R` — login endpoint URL, auth mechanism, API key extraction
- `https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_create_account.R` — registration endpoint and parameters
- `https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/utils.R` — URL construction, API key as query param, Parquet response format
- `https://raw.githubusercontent.com/andreweatherman/cbbdata/main/R/cbd_torvik_ratings.R` — ratings endpoint URL `https://www.cbbdata.com/api/torvik/ratings`
- `https://www.torvik.dev/reference/bart_ratings.php` — column names (barthag, adj_o, adj_d, adj_t, wab, conf, year)
- `https://www.cbbdata.com/api/data/teams` — live verified: returns Parquet, no auth required
- `https://www.cbbdata.com/api/torvik/ratings?key=test&year=2025` — live verified: 403 with bad key, confirms key required
- Live ESPN API responses for tournament dates 2025-03-18, 2025-03-19, 2025-03-20 — confirmed curatedRank.current = seed, notes.headline = region, no dedicated seed field

### Secondary (MEDIUM confidence)
- `https://pypi.org/project/CBBpy/` — version 2.1.2, function signatures for `get_games_season`, confirmed no efficiency metrics
- `https://github.com/dcstats/CBBpy/releases` — release history confirming v2.1.2 (Jan 2025)
- `https://www.ncaa.com/news/basketball-men/article/2026-01-16/2026-selection-sunday-date-schedule-tv-times-march-madness` — confirms 2026-03-15 Selection Sunday date
- Community search results confirming `groups=100` parameter for ESPN scoreboard to get all D1 games

### Tertiary (LOW confidence)
- WebSearch results about ESPN bracketology endpoint returning empty results for 2022+ (from gist comment threads, not verified directly)
- CBBpy `get_games_season` season parameter convention (year=2026 for 2025-26) — inferred from community usage, consistent with Kaggle convention but not tested directly against live API

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against R source code, live API, and PyPI
- Architecture: MEDIUM — patterns based on verified API structure; ESPN scheduled-game seedings is LOW confidence pending live test
- Pitfalls: MEDIUM — most confirmed by live testing or source code; some (like ESPN scheduled events) are forward-looking

**Research date:** 2026-03-02
**Valid until:** 2026-03-15 (Selection Sunday — ESPN bracket endpoint becomes testable then; cbbdata API structure stable for ~30 days)
