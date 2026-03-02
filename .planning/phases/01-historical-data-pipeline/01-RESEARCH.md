# Phase 1: Historical Data Pipeline - Research

**Researched:** 2026-03-02
**Domain:** Sports data ingestion — Kaggle NCAA dataset, DuckDB/Parquet storage, team name normalization
**Confidence:** MEDIUM-HIGH (Kaggle dataset structure verified via multiple sources; team name conflicts partially verified; DuckDB API verified via official docs)

---

## Summary

This phase ingests the Kaggle March Machine Learning Mania dataset (covering 2003–2025 seasons) into DuckDB/Parquet, builds a canonical team name normalization table across ESPN, Kaggle, Sports-Reference, and cbbdata, enforces Selection Sunday cutoff dates per season, and tags First Four play-in games correctly.

The Kaggle dataset uses **integer team IDs** (men's: 1101–1499 range), not team names, for all game records. Team names live only in `MTeams.csv`. This is the correct design — the normalization challenge is mapping Kaggle's internal team names (e.g., "Connecticut") to the names used by other data sources (ESPN uses "UConn", Sports-Reference uses slug "connecticut"). The 2020 season has no tournament data (cancelled due to COVID-19); the dataset jumps from 2019 to 2021.

**First Four identification** is reliable: DayNum 134–135 in `MNCAATourneyCompactResults.csv` identifies play-in games (First Four began 2011; before 2011, a single play-in game existed but was not named "First Four"). Seed strings with a trailing `a` or `b` suffix (e.g., `W16a`, `Z11b`) in `MNCAATourneySeeds.csv` also identify First Four participants.

**Primary recommendation:** Use DuckDB as the query engine, store data as Parquet files per data type, and build the team normalization table as a handcrafted CSV seed file that is loaded into DuckDB on first run — fuzzy matching is a bootstrap assist, not the final answer.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.2.x (latest stable as of March 2026) | Analytical SQL engine, reads/writes Parquet and CSV natively | Zero-config, embedded, no server, fast columnar queries |
| pandas | 2.x | DataFrame manipulation for ingestion transforms | Standard Python data tool; DuckDB queries pandas DataFrames directly |
| pyarrow | 18.x | Parquet read/write backend | Required by DuckDB Parquet operations |
| kagglehub | latest | Download Kaggle competition data programmatically | Official Kaggle Python library, replaces older kaggle CLI |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| thefuzz | 0.22.x | Fuzzy string matching (Levenshtein) | Bootstrap-phase team name matching for generating alias candidates |
| python-Levenshtein | 0.25.x | Speed dependency for thefuzz | Install alongside thefuzz to get 4–10x speedup |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| kagglehub | kaggle CLI (`kaggle competitions download`) | CLI also works but kagglehub integrates better into Python scripts |
| thefuzz | rapidfuzz | rapidfuzz is faster and better-maintained but either works for this one-time normalization task |
| DuckDB persistent DB | Parquet-only files | For this project, using DuckDB to query Parquet files directly is fine; a persistent .duckdb file is optional |

**Installation:**
```bash
uv add duckdb pandas pyarrow kagglehub thefuzz python-Levenshtein
```

---

## Architecture Patterns

### Recommended Project Structure

```
madness2026/
├── data/
│   ├── raw/
│   │   └── kaggle/                  # Downloaded CSV files from Kaggle
│   │       ├── MTeams.csv
│   │       ├── MSeasons.csv
│   │       ├── MNCAATourneyCompactResults.csv
│   │       ├── MNCAATourneyDetailedResults.csv
│   │       ├── MNCAATourneySeeds.csv
│   │       ├── MNCAATourneySlots.csv
│   │       ├── MRegularSeasonCompactResults.csv
│   │       └── MRegularSeasonDetailedResults.csv
│   ├── processed/
│   │   ├── tournament_games.parquet  # Cleaned tourney records 2003-2025
│   │   ├── regular_season.parquet    # Regular season records
│   │   └── team_normalization.parquet # Canonical name table
│   └── seeds/
│       └── team_aliases.csv          # Hand-curated alias overrides
├── src/
│   ├── ingest/
│   │   ├── kaggle_download.py        # Download from Kaggle
│   │   ├── parse_tourney.py          # Parse tournament CSVs
│   │   └── write_parquet.py          # Write processed Parquet files
│   ├── normalize/
│   │   ├── build_team_table.py       # Build normalization table
│   │   └── fuzzy_match.py            # Fuzzy matching helpers
│   └── utils/
│       └── cutoff_dates.py           # Selection Sunday date constants
└── pyproject.toml
```

### Pattern 1: DuckDB-Based CSV-to-Parquet Ingestion

**What:** Read Kaggle CSVs directly with DuckDB SQL, transform, write to Parquet.
**When to use:** Initial data load and any re-ingestion from raw Kaggle data.

```python
# Source: https://duckdb.org/docs/stable/clients/python/data_ingestion
import duckdb

conn = duckdb.connect()

# Read raw CSV and write to Parquet in one SQL statement
conn.execute("""
    COPY (
        SELECT
            r.Season,
            r.DayNum,
            r.WTeamID,
            wt.TeamName AS WTeamName,
            r.WScore,
            r.LTeamID,
            lt.TeamName AS LTeamName,
            r.LScore,
            r.NumOT,
            -- Flag First Four games: DayNum 134 or 135
            CASE WHEN r.DayNum <= 135 THEN true ELSE false END AS is_first_four
        FROM read_csv('data/raw/kaggle/MNCAATourneyCompactResults.csv') r
        JOIN read_csv('data/raw/kaggle/MTeams.csv') wt ON r.WTeamID = wt.TeamID
        JOIN read_csv('data/raw/kaggle/MTeams.csv') lt ON r.LTeamID = lt.TeamID
        WHERE r.Season >= 2003
    )
    TO 'data/processed/tournament_games.parquet'
    (FORMAT parquet, COMPRESSION zstd)
""")
```

### Pattern 2: Kaggle Dataset Download via kagglehub

**What:** Programmatically download the latest competition data.
**When to use:** Task 01-02 environment setup and data download step.

```python
# Source: https://github.com/Kaggle/kagglehub
import kagglehub
import shutil
import pathlib

# Downloads to Kaggle cache directory, returns path
path = kagglehub.competition_download(
    'march-machine-learning-mania-2026',
    path=None,              # None = download all files
)
# Copy to project's raw data directory
shutil.copytree(path, 'data/raw/kaggle/', dirs_exist_ok=True)
```

**Note:** Requires `~/.kaggle/kaggle.json` with API token. The user must accept competition rules on kaggle.com before the API token will work for downloads.

### Pattern 3: Selection Sunday Cutoff Enforcement

**What:** Gate all stat queries to only include data available before each season's Selection Sunday.
**When to use:** Any query that loads per-team stats for prediction; prevents data leakage.

```python
# Source: verified against Wikipedia tournament articles
SELECTION_SUNDAY_DATES = {
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
}

def get_cutoff(season: int) -> str:
    """Return Selection Sunday date string (inclusive cutoff) for a season."""
    if season not in SELECTION_SUNDAY_DATES:
        raise ValueError(f"No Selection Sunday date for season {season}")
    return SELECTION_SUNDAY_DATES[season]
```

**Kaggle DayNum cross-reference:** In Kaggle's data, `DayNum=132` corresponds to Selection Sunday for each season. DayNum is an offset from the `DayzeroDate` in `MSeasons.csv`. To convert: `game_date = dayzero_date + timedelta(days=daynum)`.

### Pattern 4: Team Normalization Table Schema

**What:** A canonical team table mapping Kaggle TeamID to a canonical name, with aliases from each source.
**When to use:** All cross-source lookups.

```sql
-- DuckDB table definition
CREATE TABLE team_normalization (
    kaggle_team_id  INTEGER PRIMARY KEY,   -- MTeams.csv TeamID (e.g., 1242)
    canonical_name  VARCHAR NOT NULL,       -- Authoritative name (e.g., "Connecticut")
    kaggle_name     VARCHAR,               -- From MTeams.csv TeamName
    espn_name       VARCHAR,               -- ESPN display name (e.g., "UConn")
    espn_slug       VARCHAR,               -- ESPN URL slug (e.g., "uconn-huskies")
    sr_slug         VARCHAR,               -- Sports-Reference URL slug (e.g., "connecticut")
    cbbdata_name    VARCHAR,               -- cbbdata/barttorvik name
    ncaa_name       VARCHAR,               -- Official NCAA name
    first_d1_season INTEGER,              -- From MTeams.csv
    last_d1_season  INTEGER               -- From MTeams.csv
);
```

### Pattern 5: First Four Identification

**What:** Two reliable signals for First Four games in Kaggle data.
**When to use:** Tagging game records for Round classification.

```python
import pandas as pd

def tag_first_four(tourney_df: pd.DataFrame) -> pd.DataFrame:
    """
    First Four games have DayNum == 134 or 135 in MNCAATourneyCompactResults.
    Confirmed: DayNum 132 = Selection Sunday, 134-135 = First Four,
    136-137 = Round of 64, 138-139 = Round of 32, etc.
    Championship game is always DayNum 154.
    First Four existed 2011-present (4 games).
    Pre-2011: single play-in game at DayNum 134 (1 game, 2001-2010).
    """
    tourney_df = tourney_df.copy()
    tourney_df['is_first_four'] = tourney_df['DayNum'].isin([134, 135])
    tourney_df['round'] = tourney_df['DayNum'].map({
        134: 'First Four',
        135: 'First Four',
        136: 'Round of 64',
        137: 'Round of 64',
        138: 'Round of 32',
        139: 'Round of 32',
        143: 'Sweet Sixteen',
        144: 'Sweet Sixteen',
        145: 'Elite Eight',
        146: 'Elite Eight',
        152: 'Final Four',
        154: 'Championship',
    })
    return tourney_df
```

**Seed-based signal:** In `MNCAATourneySeeds.csv`, First Four participants have seeds with trailing `a` or `b` suffix: `W16a`, `W16b`, `Z11a`, `Z11b`. A team with seed ending in `a` or `b` played in the First Four.

### Anti-Patterns to Avoid

- **Joining on team name strings:** Never join game records using team name text — always use `TeamID` (integer) as the join key within the Kaggle dataset.
- **Assuming team names are consistent across sources:** Kaggle uses "Connecticut", ESPN uses "UConn", Sports-Reference slug is "connecticut". These must be manually mapped.
- **Including 2020 season:** The 2020 NCAA tournament was cancelled due to COVID-19. The Kaggle dataset has no tournament data for Season=2020. The regular season data for 2020 may exist but truncates early. Treat 2020 as a gap.
- **Treating all DayNum 134-135 pre-2011 as First Four:** Before 2011, there was a single play-in game. The "First Four" (4 games) officially started in 2011. Pre-2011 DayNum 134 records should be labeled "Play-In Game" not "First Four".

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Kaggle data download | Custom HTTP scraper or wget | `kagglehub.competition_download()` | Handles auth, caching, versioning |
| CSV-to-Parquet conversion | Custom pandas write loop | DuckDB `COPY ... TO ... (FORMAT parquet)` | Vectorized, streaming, no memory issues |
| Fuzzy team name matching | Custom edit-distance function | `thefuzz.process.extractOne()` | Handles token reordering, partial matches |
| Date arithmetic from DayNum | Custom calendar logic | `dayzero_date + timedelta(days=daynum)` with pandas | Kaggle's `MSeasons.csv` provides the dayzero date |
| Duplicate game detection | Manual deduplication | DuckDB `SELECT DISTINCT` or `QUALIFY ROW_NUMBER()` | SQL handles this cleanly |

**Key insight:** The team name normalization table should be built once as a seed CSV, reviewed manually for known conflicts, then loaded. Don't try to automate the final normalization — use fuzzy matching only to generate *candidates* for human review.

---

## Common Pitfalls

### Pitfall 1: Kaggle Competition Requires Account Acceptance

**What goes wrong:** `kagglehub.competition_download()` fails with 403 or permission error even with valid API token.
**Why it happens:** Kaggle competition datasets require explicit acceptance of competition rules via the web interface before the API will serve them.
**How to avoid:** Navigate to `https://www.kaggle.com/competitions/march-machine-learning-mania-2026/data`, accept rules, then try API.
**Warning signs:** HTTP 403 error from kagglehub, or error message mentioning "accept rules".

### Pitfall 2: 2020 Season Gap

**What goes wrong:** Code that assumes continuous season IDs 2003–2025 will fail or silently skip data.
**Why it happens:** 2020 NCAA tournament was cancelled. Kaggle dataset has no `Season=2020` tournament records.
**How to avoid:** Use explicit season lists, not `range(2003, 2026)`. The valid tournament seasons are: `2003–2019, 2021–2025` (17 total with tournament data for 2021 played in bubble).
**Warning signs:** Any code that calls `range(2003, 2026)` over tournament data.

### Pitfall 3: Team Name Inconsistency Across Sources

**What goes wrong:** Joining ESPN data to Kaggle data by team name matches zero or wrong rows.
**Why it happens:** Each source uses its own naming convention:
  - Kaggle: `"Connecticut"` (full state name, no "UConn" branding)
  - ESPN: `"UConn"` or `"Connecticut Huskies"`
  - Sports-Reference: URL slug `connecticut` (team page), displayed as `Connecticut`
  - cbbdata/barttorvik: typically uses ESPN-style names
**How to avoid:** Build `team_normalization` table as the single source of truth. Never join cross-source by raw name string.
**Known conflicts (MEDIUM confidence — from training data + community sources):**
  - UConn: Kaggle="Connecticut", ESPN="UConn"
  - St. John's: various "Saint John's" vs "St. John's (NY)" variants
  - Loyola Chicago: "Loyola Chicago" vs "Loyola-Chicago" vs "Loyola (IL)"
  - Cal State schools: multiple "Cal State Fullerton" vs "CS Fullerton" variants
  - Miami: "Miami FL" vs "Miami (FL)" to disambiguate from Miami (OH)
  - Arkansas-Pine Bluff: hyphenation varies by source
  - Gardner-Webb: hyphen vs space variants
  - Texas A&M Corpus Christi: ampersand handling differs

### Pitfall 4: First Four DayNum Threshold is 135, Not 133

**What goes wrong:** Code that uses `DayNum < 136` but hard-codes wrong threshold.
**Why it happens:** Selection Sunday is DayNum=132, First Four is DayNum=134–135 (Tuesday-Wednesday), Round of 64 is DayNum=136–137 (Thursday-Friday).
**How to avoid:** Use `DayNum.isin([134, 135])` explicitly rather than a range comparison.

### Pitfall 5: Kaggle API Token Requires `~/.kaggle/kaggle.json`

**What goes wrong:** kagglehub can't authenticate in a fresh environment.
**Why it happens:** API token must be at `~/.kaggle/kaggle.json` with permissions 600.
**How to avoid:** Document this as a prerequisite. The file format is `{"username":"...", "key":"..."}`. Download from `https://www.kaggle.com/settings` under the API section.

### Pitfall 6: MNCAATourneyDetailedResults Doesn't Cover All Years

**What goes wrong:** Detailed results (FGA, rebounds, etc.) have fewer years than compact results.
**Why it happens:** Detailed box score data was not collected for older seasons.
**How to avoid:** Use `MNCAATourneyCompactResults.csv` for game outcomes (all years); use `MNCAATourneyDetailedResults.csv` only for advanced stats (verify year coverage).

### Pitfall 7: WLoc Column Absent in Tournament Results

**What goes wrong:** Code that expects `WLoc` column in tournament data fails.
**Why it happens:** `MNCAATourneyCompactResults.csv` does NOT include the `WLoc` column (all tournament games are neutral-site). `WLoc` only exists in `MRegularSeasonCompactResults.csv`.
**How to avoid:** Add `WLoc = 'N'` (neutral) as a constant when building the tournament games table.

---

## Code Examples

### Complete Kaggle Dataset Ingestion

```python
# Source: https://duckdb.org/docs/stable/clients/python/data_ingestion + kagglehub docs
import duckdb
import kagglehub
import pathlib
import shutil

DATA_DIR = pathlib.Path("data")
RAW_DIR = DATA_DIR / "raw" / "kaggle"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Step 1: Download from Kaggle
print("Downloading Kaggle dataset...")
kaggle_path = kagglehub.competition_download('march-machine-learning-mania-2026')
shutil.copytree(kaggle_path, RAW_DIR, dirs_exist_ok=True)

# Step 2: Ingest into DuckDB and write Parquet
conn = duckdb.connect()

# Register the CSV files as views for easy querying
conn.execute(f"CREATE VIEW teams AS SELECT * FROM read_csv('{RAW_DIR}/MTeams.csv')")
conn.execute(f"CREATE VIEW seasons AS SELECT * FROM read_csv('{RAW_DIR}/MSeasons.csv')")
conn.execute(f"CREATE VIEW tourney_results AS SELECT * FROM read_csv('{RAW_DIR}/MNCAATourneyCompactResults.csv')")
conn.execute(f"CREATE VIEW tourney_seeds AS SELECT * FROM read_csv('{RAW_DIR}/MNCAATourneySeeds.csv')")

# Step 3: Write processed tournament games with First Four flag
conn.execute(f"""
    COPY (
        SELECT
            r.Season,
            r.DayNum,
            -- Compute actual game date from dayzero
            (s.DayZero::DATE + r.DayNum) AS GameDate,
            r.WTeamID,
            wt.TeamName AS WTeamName,
            r.WScore,
            r.LTeamID,
            lt.TeamName AS LTeamName,
            r.LScore,
            r.NumOT,
            'N' AS WLoc,  -- All tournament games are neutral site
            CASE WHEN r.DayNum <= 135 THEN true ELSE false END AS IsFirstFour,
            CASE
                WHEN r.DayNum IN (134, 135) THEN 'First Four'
                WHEN r.DayNum IN (136, 137) THEN 'Round of 64'
                WHEN r.DayNum IN (138, 139) THEN 'Round of 32'
                WHEN r.DayNum IN (143, 144) THEN 'Sweet Sixteen'
                WHEN r.DayNum IN (145, 146) THEN 'Elite Eight'
                WHEN r.DayNum IN (152) THEN 'Final Four'
                WHEN r.DayNum IN (154) THEN 'Championship'
            END AS Round
        FROM tourney_results r
        JOIN seasons s ON r.Season = s.Season
        JOIN teams wt ON r.WTeamID = wt.TeamID
        JOIN teams lt ON r.LTeamID = lt.TeamID
        WHERE r.Season >= 2003
          AND r.Season != 2020  -- Tournament cancelled
        ORDER BY r.Season, r.DayNum
    )
    TO '{PROCESSED_DIR}/tournament_games.parquet'
    (FORMAT parquet, COMPRESSION zstd)
""")
print(f"Tournament games written to {PROCESSED_DIR}/tournament_games.parquet")
```

### Team Name Normalization Bootstrap

```python
# Source: thefuzz library docs + training knowledge
from thefuzz import process, fuzz
import pandas as pd

def generate_alias_candidates(kaggle_names: list[str], espn_names: list[str]) -> pd.DataFrame:
    """
    Generate fuzzy-matched alias candidates between Kaggle and ESPN names.
    Output is candidates for HUMAN REVIEW — not final truth.
    """
    rows = []
    for kaggle_name in kaggle_names:
        match, score = process.extractOne(
            kaggle_name,
            espn_names,
            scorer=fuzz.token_sort_ratio
        )
        rows.append({
            'kaggle_name': kaggle_name,
            'espn_candidate': match,
            'confidence_score': score,
            'needs_review': score < 90,
        })
    return pd.DataFrame(rows)
```

### Reading Processed Parquet with DuckDB

```python
# Source: https://duckdb.org/docs/stable/data/parquet/overview
import duckdb

def get_tourney_games(season: int, include_first_four: bool = False) -> pd.DataFrame:
    """Load tournament game records for a given season."""
    first_four_filter = "" if include_first_four else "AND NOT IsFirstFour"
    return duckdb.sql(f"""
        SELECT *
        FROM read_parquet('data/processed/tournament_games.parquet')
        WHERE Season = {season}
        {first_four_filter}
        ORDER BY DayNum
    """).df()
```

### Date-Gated Stats Query (Cutoff Enforcement)

```python
# Pattern: enforce Selection Sunday cutoff on any stats query
import duckdb
from utils.cutoff_dates import SELECTION_SUNDAY_DATES

def get_season_stats_with_cutoff(season: int) -> pd.DataFrame:
    """
    Return regular season stats up to and including Selection Sunday.
    Prevents using post-Selection-Sunday data that wouldn't be available for predictions.
    """
    cutoff = SELECTION_SUNDAY_DATES[season]
    return duckdb.sql(f"""
        SELECT *
        FROM read_parquet('data/processed/regular_season.parquet')
        WHERE Season = {season}
          AND GameDate <= '{cutoff}'
    """).df()
```

---

## Kaggle Dataset File Reference

Complete list of files in the Kaggle March Machine Learning Mania dataset (men's prefix = `M`):

| File | Key Columns | Notes |
|------|-------------|-------|
| `MTeams.csv` | `TeamID, TeamName, FirstD1Season, LastD1Season` | Master team reference; men's TeamID range 1101–1499 |
| `MSeasons.csv` | `Season, DayZero, RegionW, RegionX, RegionY, RegionZ` | DayZero is the date for DayNum=0 each season |
| `MNCAATourneyCompactResults.csv` | `Season, DayNum, WTeamID, WScore, LTeamID, LScore, NumOT` | No WLoc column (all neutral site) |
| `MNCAATourneyDetailedResults.csv` | All compact columns + box score stats | May not cover all years back to 2003 |
| `MNCAATourneySeeds.csv` | `Season, Seed, TeamID` | Seed format: `W01`–`W16`, with `a/b` suffix for First Four |
| `MNCAATourneySlots.csv` | `Season, Slot, StrongSeed, WeakSeed` | Bracket structure |
| `MRegularSeasonCompactResults.csv` | `Season, DayNum, WTeamID, WScore, LTeamID, LScore, WLoc, NumOT` | WLoc: H/A/N |
| `MRegularSeasonDetailedResults.csv` | All compact + box score stats | Used in later phases for team stats |
| `MMasseyOrdinals.csv` | `Season, RankingDayNum, SystemName, TeamID, OrdinalRank` | Aggregated ranking systems |

## Key DayNum Values (Verified)

| DayNum | Event | Notes |
|--------|-------|-------|
| 132 | Selection Sunday | Bracket announced |
| 134 | First Four Game Night 1 | Tuesday |
| 135 | First Four Game Night 2 | Wednesday |
| 136–137 | Round of 64 | Thursday–Friday |
| 138–139 | Round of 32 | Saturday–Sunday |
| 143–144 | Sweet Sixteen | Thursday–Friday |
| 145–146 | Elite Eight | Saturday–Sunday |
| 152 | Final Four | Saturday |
| 154 | Championship | Monday |

## Selection Sunday Dates (2003–2025)

| Season | Selection Sunday | Source |
|--------|-----------------|--------|
| 2003 | 2003-03-16 | Derived: first round began 2003-03-18 |
| 2004 | 2004-03-14 | Derived: first round began 2004-03-16 |
| 2005 | 2005-03-13 | Derived: first round began 2005-03-17 |
| 2006 | 2006-03-12 | Derived: first round began 2006-03-16 |
| 2007 | 2007-03-11 | Verified: interbasket.net historical table |
| 2008 | 2008-03-16 | Verified: interbasket.net historical table |
| 2009 | 2009-03-15 | Verified: interbasket.net historical table |
| 2010 | 2010-03-14 | Verified: interbasket.net historical table |
| 2011 | 2011-03-13 | Verified: Wikipedia 2011 tournament + interbasket.net |
| 2012 | 2012-03-11 | Verified: interbasket.net historical table |
| 2013 | 2013-03-17 | Verified: interbasket.net historical table |
| 2014 | 2014-03-16 | Verified: interbasket.net historical table |
| 2015 | 2015-03-15 | Verified: interbasket.net historical table |
| 2016 | 2016-03-13 | Verified: interbasket.net historical table |
| 2017 | 2017-03-12 | Verified: interbasket.net + WebSearch |
| 2018 | 2018-03-11 | Verified: interbasket.net historical table |
| 2019 | 2019-03-17 | Verified: Wikipedia 2019 + WebSearch |
| 2020 | N/A (cancelled) | Tournament cancelled due to COVID-19 |
| 2021 | 2021-03-14 | Verified: WebSearch (bubble tournament in Indianapolis) |
| 2022 | 2022-03-13 | Verified: WebSearch (NCAA.com announcement) |
| 2023 | 2023-03-12 | Verified: WebSearch multiple sources |
| 2024 | 2024-03-17 | Verified: WebSearch (CBS Sports, ESPN confirm March 17) |
| 2025 | 2025-03-16 | Verified: WebSearch multiple sources |

**Note:** 2003–2006 dates are derived by working backward from confirmed first-round start dates. The rule is: Selection Sunday is always 2 days before the first First Four / play-in game, which is the Tuesday of tournament week. Verify the 2003–2006 dates against Kaggle's `MSeasons.csv` `DayZero` field + `DayNum=132` before hardcoding.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `kaggle` CLI package | `kagglehub` Python library | 2023–2024 | kagglehub is the preferred programmatic method; both still work |
| `fuzzywuzzy` | `thefuzz` | 2021 | Same API, renamed for licensing; use `thefuzz` |
| DuckDB 0.x | DuckDB 1.x LTS | DuckDB 1.0 released January 2024 | Stable API guarantees, persistent database format now stable |

**Deprecated/outdated:**
- `fuzzywuzzy`: renamed to `thefuzz`; don't install `fuzzywuzzy` directly
- `python-Levenshtein` is the speed backend for `thefuzz`; `levenshtein` (newer package) is also a valid backend

---

## Open Questions

1. **2025 Season Data Availability in Kaggle 2026 Competition**
   - What we know: The 2026 competition is live as of March 2026. Historical data through 2024 is certain. The 2025 tournament completed in April 2025.
   - What's unclear: Whether the 2026 competition dataset was updated post-2025-tournament to include 2025 tournament results.
   - Recommendation: After downloading, check `SELECT MAX(Season) FROM read_csv('MNCAATourneyCompactResults.csv')` to verify 2025 is present. If absent, contact Kaggle or use a supplemental source.

2. **Exact Kaggle Team Names for Known Conflict Cases**
   - What we know: Team names in Kaggle use full institutional names (e.g., "Connecticut" not "UConn"). Men's TeamIDs are integers in 1101–1499 range.
   - What's unclear: Exact string representations for ambiguous schools like "St. John's", "Miami FL", "Texas A&M CC". These must be verified from the actual downloaded `MTeams.csv`.
   - Recommendation: After download, run `SELECT TeamName FROM MTeams ORDER BY TeamName` and hand-compare to ESPN's team list for the known conflict cases.

3. **MNCAATourneyDetailedResults Year Coverage**
   - What we know: Detailed results exist for recent years; compact results go back to 1985.
   - What's unclear: Exact first year that detailed stats are available (likely around 2003 based on competition history, but not verified).
   - Recommendation: After download, check `SELECT MIN(Season), MAX(Season) FROM MNCAATourneyDetailedResults` to establish actual range.

4. **Pre-2011 Play-In Game Treatment**
   - What we know: A single play-in game existed 2001–2010 (before the First Four expansion). Kaggle data likely includes it at DayNum 134.
   - What's unclear: Whether pre-2011 DayNum=134 games are in the Kaggle dataset and labeled consistently. The 2003+ scope means 8 years of single-game play-in data must be correctly tagged.
   - Recommendation: Query `SELECT Season, DayNum, COUNT(*) FROM MNCAATourneyCompactResults WHERE DayNum < 136 GROUP BY Season, DayNum ORDER BY Season` to see the play-in game history across seasons.

5. **cbbdata API Team Name Format**
   - What we know: cbbdata is an R package backed by a Python/Flask API. It pulls from barttorvik.com data. The cbbplotR companion has an "extensive matching dictionary."
   - What's unclear: Whether there is a Python-accessible endpoint for cbbdata, or whether CBBpy (which scrapes ESPN) is the correct Python tool for ESPN-format data. The project notes "cbbdata API" as a source — this needs validation before Phase 2.
   - Recommendation: Before Phase 2, confirm with a test call whether cbbdata has a direct Python API or requires the R package. CBBpy is confirmed to be a Python tool but scrapes ESPN.

---

## Sources

### Primary (HIGH confidence)
- `https://duckdb.org/docs/stable/clients/python/data_ingestion` — DuckDB Python CSV/Parquet ingestion
- `https://duckdb.org/docs/stable/data/parquet/overview` — DuckDB Parquet write options and COPY syntax
- `https://duckdb.org/docs/stable/data/parquet/tips` — Parquet optimization (row groups, compression)
- `https://pypi.org/project/CBBpy/` — CBBpy package documentation (ESPN scraper)
- `https://pypi.org/project/kagglehub/` — kagglehub download API

### Secondary (MEDIUM confidence)
- `http://rstudio-pubs-static.s3.amazonaws.com/16076_73afbc93c1184e62a7cc3dc934dce968.html` — Kaggle dataset DayNum documentation (older version of dataset, schema is stable)
- `https://www.interbasket.net/brackets/ncaa-tournament/selection-sunday/` — Selection Sunday historical dates 2007–2022
- `https://github.com/lbenz720/ncaahoopR` — ncaahoopR team name crosswalk dictionary structure (R package, but confirms naming conventions)
- `https://github.com/KianaVega/March-Madness-MLM-Project-Forecasting-the-2025-NCAA-Basketball-Tournaments` — Kaggle 2025 dataset file and schema inventory
- WebSearch results for 2023, 2024, 2025 Selection Sunday dates (confirmed by multiple sources)

### Tertiary (LOW confidence)
- Team name conflict list (UConn, St. John's, Miami FL, etc.) — from training knowledge; must be verified against downloaded `MTeams.csv`
- 2003–2006 Selection Sunday dates — derived from first-round start dates, not directly verified against primary source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — DuckDB, pandas, pyarrow, kagglehub all verified via official docs/PyPI
- Kaggle dataset schema: MEDIUM-HIGH — Schema verified via multiple independent GitHub projects and archived documentation; actual file contents not directly inspected
- DayNum mapping: MEDIUM-HIGH — Core mapping (DayNum 132=Selection Sunday, 134-135=First Four) verified via two independent sources
- Architecture: MEDIUM — Pattern is well-established for this type of data pipeline; specifics tuned to this project
- Selection Sunday dates: MEDIUM — 2007–2025 verified via web sources; 2003–2006 derived/inferred
- Team name conflicts: LOW-MEDIUM — Known conflicts from training data and community sources; must verify against actual downloaded files
- Pitfalls: MEDIUM — Most verified; COVID cancellation (2020) confirmed; WLoc absence in tourney file confirmed

**Research date:** 2026-03-02
**Valid until:** 2026-04-01 (stable domain; DuckDB API stable in 1.x LTS; Kaggle dataset schema very stable across years)
