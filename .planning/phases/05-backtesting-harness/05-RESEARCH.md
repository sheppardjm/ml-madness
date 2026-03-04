# Phase 5: Backtesting Harness - Research

**Researched:** 2026-03-03
**Domain:** NCAA tournament bracket backtesting, ESPN bracket scoring, walk-forward evaluation pipeline
**Confidence:** HIGH (all data files inspected, key pipeline verified with live code execution)

## Summary

Phase 5 builds a `backtest()` function that replays the full feature-to-simulator pipeline against 2022–2025 tournament snapshots. The core challenge is connecting three existing systems: (1) the walk-forward model refitting from Phase 3, (2) the bracket simulation from Phase 4, and (3) the actual tournament results in `tournament_games.parquet`. All three are working independently; Phase 5 orchestrates them together.

The ESPN bracket score requires comparing the simulator's predicted slot winners against actual slot winners. The actual slot winners are derivable via `MNCAATourneySeedRoundSlots.csv` (maps seed labels to slots per round) joined to `tournament_games.parquet` (actual game outcomes). This join has been verified to produce exactly 67 slot winners per year (including 4 First Four games) for all four backtest years. The slot IDs produced by this join match the slot IDs used by `simulate_bracket()` in Phase 4.

The key architectural decision is that Phase 5 does NOT use the saved `models/logistic_baseline.joblib` model for predictions. It follows the same pattern as `evaluate_all_holdout_years()` in Phase 3: extract `best_C` from the saved artifact, then re-fit a new `StandardScaler` + `LogisticRegression` on training data (Season < test_year) for each backtest year. This ensures strict temporal isolation.

**Primary recommendation:** Build `src/backtest/backtest.py` as the orchestration entry point and `src/backtest/scoring.py` for ESPN scoring. Reuse `walk_forward_splits()`, `ClippedCalibrator`, `simulate_bracket()`, and `build_stats_lookup()` from Phases 3-4. Add a new `build_actual_slot_winners()` helper that uses `MNCAATourneySeedRoundSlots.csv` + `tournament_games.parquet`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.8.0 | LogisticRegression, StandardScaler per fold | Same as Phase 3; re-fit per backtest year |
| joblib | bundled with sklearn | Load model artifact to extract best_C | Established pattern from Phase 3 |
| numpy | 2.4.2 | Feature array operations | Already project standard |
| duckdb | 1.4.4 | Query tournament_games, seeds, SeedRoundSlots | Project standard for all data queries |
| pandas | 3.0.1 | DataFrames for results aggregation | Project standard |
| json | stdlib | Write backtest/results.json | Already used in evaluation_results.json |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sklearn.metrics.brier_score_loss | 1.8.0 | Per-year Brier computation | Same as evaluate.py |
| sklearn.metrics.log_loss | 1.8.0 | Per-year log-loss computation | Same as evaluate.py |
| pathlib | stdlib | backtest/results.json path management | Directory creation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Re-fitting model per backtest fold | Using saved models/logistic_baseline.joblib directly | Saved model trained on ALL seasons including 2025; re-fitting enforces temporal isolation |
| MNCAATourneySeedRoundSlots.csv for slot winners | Manually mapping games to slots | SeedRoundSlots is the canonical source; manual mapping would be fragile |
| Deterministic simulation for ESPN scoring | Monte Carlo simulation | Bracket scoring requires one deterministic bracket; Monte Carlo would need mode='deterministic' anyway |

**No new packages needed.** All required libraries are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── backtest/                    # New directory for Phase 5
│   ├── __init__.py
│   ├── backtest.py              # backtest() function, orchestration loop (05-02, 05-04, 05-05)
│   └── scoring.py               # ESPN score, per-round accuracy, game metrics (05-03)
backtest/                        # Output directory (created by backtest.py)
└── results.json                 # Written by backtest(); reproducible per run
```

### Pattern 1: Per-Year Walk-Forward Model Construction

**What:** For each backtest year Y, re-fit `StandardScaler` + `LogisticRegression(C=best_C)` + `ClippedCalibrator` on training data (Season < Y). Build a `predict_fn` closure that uses this fold-specific model and year-Y stats from `build_stats_lookup()`.

**When to use:** Every backtest year (2022, 2023, 2024, 2025).

**Example:**
```python
# Source: direct pattern from evaluate_all_holdout_years() in src/models/evaluate.py
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from src.models.features import FEATURE_COLS, build_matchup_dataset, build_stats_lookup, compute_features
from src.models.temporal_cv import walk_forward_splits
from src.models.train_logistic import ClippedCalibrator, CLIP_LO, CLIP_HI

def build_yearly_predict_fn(
    test_year: int,
    df: pd.DataFrame,
    stats_lookup: dict,
    best_C: float,
) -> Callable[[int, int], float]:
    """Build predict_fn for test_year using only pre-year training data."""
    train_df = df[df['Season'] < test_year].copy()
    X_train = train_df[FEATURE_COLS].values
    y_train = train_df['label'].values

    # Re-fit scaler on training fold ONLY — no test-set leakage
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    clf = LogisticRegression(
        C=best_C,
        class_weight='balanced',
        solver='lbfgs',
        max_iter=1000,
        random_state=42,
    )
    clf.fit(X_train_scaled, y_train)
    calibrated_clf = ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        features = compute_features(test_year, team_a_id, team_b_id, stats_lookup)
        x = np.array([features[name] for name in FEATURE_COLS]).reshape(1, -1)
        x_scaled = scaler.transform(x)
        return float(calibrated_clf.predict_proba(x_scaled)[0, 1])

    return predict_fn
```

### Pattern 2: Actual Slot Winners from Tournament Data

**What:** Use `MNCAATourneySeedRoundSlots.csv` (maps seed labels to slot IDs per round) joined to `tournament_games.parquet` (actual game outcomes) to determine which team won each slot.

**Critical finding:** `MNCAATourneySeedRoundSlots.csv` is NOT filtered by season (no `Season` column). It defines the universal slot routing: seed W01 always goes through R1W1, R2W1, R3W1, R4W1, R5WX, R6CH. This is constant across all years (post-2011). The join to `tournament_games` uses `DayNum BETWEEN EarlyDayNum AND LateDayNum` and filters by winner (`WTeamID = ts.TeamID`).

**Verified:** Returns exactly 67 slot winners per year (4 FF + 63 bracket games) for 2022-2025.

```python
# Source: verified by direct execution against data/processed/ files
import duckdb
import pandas as pd

def build_actual_slot_winners(
    season: int,
    processed_dir: str = "data/processed",
    seed_round_slots_csv: str = "data/raw/kaggle/MNCAATourneySeedRoundSlots.csv",
) -> dict[str, int]:
    """Build actual slot winners from tournament results.

    Returns dict mapping slot_id -> winning_team_id for all 67 slots.
    Uses MNCAATourneySeedRoundSlots.csv to route seeds to slots,
    then joins tournament_games.parquet to find actual winners.

    Args:
        season: Tournament year (e.g., 2025).
        processed_dir: Directory containing seeds.parquet + tournament_games.parquet.
        seed_round_slots_csv: Path to MNCAATourneySeedRoundSlots.csv.

    Returns:
        dict: {slot_id: actual_winner_team_id} for all 67 slots.
    """
    conn = duckdb.connect()
    seeds_parquet = f"{processed_dir}/seeds.parquet"
    games_parquet = f"{processed_dir}/tournament_games.parquet"

    df = conn.execute(f"""
        WITH team_slots AS (
            SELECT DISTINCT s.TeamID, sr.GameSlot, sr.GameRound,
                   sr.EarlyDayNum, sr.LateDayNum
            FROM read_parquet('{seeds_parquet}') s
            JOIN read_csv('{seed_round_slots_csv}') sr ON s.Seed = sr.Seed
            WHERE s.Season = {season}
        )
        SELECT ts.GameSlot AS slot_id, g.WTeamID AS actual_winner, ts.GameRound
        FROM team_slots ts
        JOIN read_parquet('{games_parquet}') g
            ON g.Season = {season}
            AND g.DayNum BETWEEN ts.EarlyDayNum AND ts.LateDayNum
            AND (g.WTeamID = ts.TeamID OR g.LTeamID = ts.TeamID)
            AND g.WTeamID = ts.TeamID
        ORDER BY ts.GameSlot
    """).df()
    conn.close()

    return dict(zip(df['slot_id'], df['actual_winner']))
```

### Pattern 3: ESPN Bracket Scoring

**What:** Compare predicted slot winners (from `simulate_bracket()`) vs actual slot winners (from Pattern 2). Score R1-R6 slots using ESPN point values (R1=10, R2=20, R3=40, R4=80, R5=160, R6=320). First Four slots (round 0) are NOT scored.

**ESPN maximum score:** 1920 points (10×32 + 20×16 + 40×8 + 80×4 + 160×2 + 320×1).

```python
# Source: derived from slot_round_number() in bracket_schema.py + verified ESPN rules
from src.simulator.bracket_schema import ROUND_NAMES, slot_round_number

ESPN_ROUND_POINTS = {1: 10, 2: 20, 3: 40, 4: 80, 5: 160, 6: 320}

def score_bracket(
    predicted_slots: dict[str, int],  # slot_id -> team_id from simulate_bracket()
    actual_winners: dict[str, int],   # slot_id -> team_id from build_actual_slot_winners()
) -> dict:
    """Compute ESPN bracket score and per-round accuracy.

    Returns:
        {
            'espn_score': int,        # total ESPN points
            'espn_max': 1920,         # theoretical maximum
            'per_round_accuracy': {   # R1-R6 only (no First Four)
                'Round of 64': float,
                'Round of 32': float,
                'Sweet 16': float,
                'Elite 8': float,
                'Final Four': float,
                'Championship': float,
            },
            'per_round_correct': {round_name: int},   # raw correct counts
            'per_round_total': {round_name: int},      # total slots per round
        }
    """
    espn_score = 0
    per_round_correct = {}
    per_round_total = {}

    for slot_id, actual_winner in actual_winners.items():
        round_num = slot_round_number(slot_id)
        if round_num == 0:
            continue  # Skip First Four — not scored in ESPN bracket

        round_name = ROUND_NAMES.get(round_num, f"Round {round_num}")
        predicted_winner = predicted_slots.get(slot_id)
        is_correct = (predicted_winner == actual_winner)

        per_round_correct[round_name] = per_round_correct.get(round_name, 0) + (1 if is_correct else 0)
        per_round_total[round_name] = per_round_total.get(round_name, 0) + 1

        if is_correct:
            espn_score += ESPN_ROUND_POINTS.get(round_num, 0)

    per_round_accuracy = {
        rnd: per_round_correct.get(rnd, 0) / per_round_total.get(rnd, 1)
        for rnd in per_round_total
    }

    return {
        'espn_score': espn_score,
        'espn_max': 1920,
        'per_round_accuracy': per_round_accuracy,
        'per_round_correct': per_round_correct,
        'per_round_total': per_round_total,
    }
```

### Pattern 4: Game-Level Metrics (Reuse from evaluate.py)

**What:** Compute Brier score, log-loss, accuracy, and upset detection rate from game-level predictions. This is the same logic as `evaluate_all_holdout_years()` — iterate over actual tournament games (non-FF), compute `predict_fn(team_a, team_b)` for each, then compute metrics.

**Key:** The `predict_fn` for this computation must be the SAME per-fold model used for simulation (no reuse of the saved artifact's scaler).

```python
# Source: evaluate_all_holdout_years() in src/models/evaluate.py
from sklearn.metrics import brier_score_loss, log_loss
import numpy as np

def compute_game_metrics(
    test_year: int,
    test_df: pd.DataFrame,        # matchup DataFrame for the test year
    predict_fn: Callable[[int, int], float],
    stats_lookup: dict,
    feature_cols: list[str],
    scaler: StandardScaler,
    calibrated_clf: ClippedCalibrator,
) -> dict:
    """Compute per-game metrics for a backtest year.

    Returns:
        {
            'brier': float,
            'log_loss': float,
            'accuracy': float,
            'n_games': int,
            'n_upsets': int,
            'upset_correct': int,
            'upset_detection_rate': float,
        }
    """
    X_test = test_df[feature_cols].values
    y_test = test_df['label'].values
    X_test_scaled = scaler.transform(X_test)
    y_prob = calibrated_clf.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    n_upsets = int((y_test == 0).sum())
    upset_correct = int(((y_prob < 0.5) & (y_test == 0)).sum())

    return {
        'brier': float(brier_score_loss(y_test, y_prob)),
        'log_loss': float(log_loss(y_test, y_prob)),
        'accuracy': float((y_pred == y_test).mean()),
        'n_games': int(len(y_test)),
        'n_upsets': n_upsets,
        'upset_correct': upset_correct,
        'upset_detection_rate': float(upset_correct / n_upsets) if n_upsets > 0 else 0.0,
    }
```

### Pattern 5: backtest() Function Signature

**What:** The main entry point that orchestrates the full pipeline.

```python
# Source: success criterion requirements + design analysis
import pathlib
import json
from datetime import date

def backtest(
    year_range: list[int] = None,
    model: str = "baseline",
    model_path: str = "models/logistic_baseline.joblib",
    processed_dir: str = "data/processed",
    seed_round_slots_csv: str = "data/raw/kaggle/MNCAATourneySeedRoundSlots.csv",
    slots_csv: str = "data/raw/kaggle/MNCAATourneySlots.csv",
    output_path: str = "backtest/results.json",
) -> dict:
    """Replay the feature-to-simulator pipeline against historical tournament snapshots.

    For each year in year_range:
    1. Load seedings for that year
    2. Re-fit scaler + model on data before that year (walk-forward temporal isolation)
    3. Build predict_fn using year-specific stats
    4. Run simulate_bracket(seedings, predict_fn, mode='deterministic', season=year)
    5. Load actual slot winners from tournament_games.parquet + MNCAATourneySeedRoundSlots.csv
    6. Score bracket: ESPN score, per-round accuracy
    7. Compute game-level metrics: Brier, log-loss, accuracy, upset detection

    Args:
        year_range: List of tournament years to backtest. Default: [2022, 2023, 2024, 2025].
        model: Model to backtest. Currently only 'baseline' is supported.
        model_path: Path to joblib artifact (provides best_C parameter only).
        processed_dir: Directory containing processed parquet files.
        seed_round_slots_csv: Path to MNCAATourneySeedRoundSlots.csv.
        slots_csv: Path to MNCAATourneySlots.csv.
        output_path: Output path for results JSON.

    Returns:
        Dict with keys: 'model', 'year_range', 'per_year', 'summary', 'generated_at'.
        Written identically to output_path.

    Raises:
        FileNotFoundError: If required data files are missing.
        ValueError: If model is not 'baseline'.
    """
```

### Pattern 6: Output JSON Structure

**What:** `backtest/results.json` structure (reproducible; same output on every run).

```python
# Source: success criterion requirements + per_year results design
{
    "model": "baseline",
    "year_range": [2022, 2023, 2024, 2025],
    "generated_at": "2026-03-03",
    "per_year": [
        {
            "year": 2025,
            "brier": 0.1474,
            "log_loss": 0.4522,
            "accuracy": 0.733,
            "espn_score": 1200,
            "espn_max": 1920,
            "per_round_accuracy": {
                "Round of 64": 0.688,
                "Round of 32": 0.438,
                "Sweet 16": 0.625,
                "Elite 8": 1.0,
                "Final Four": 1.0,
                "Championship": 0.0
            },
            "per_round_correct": {
                "Round of 64": 22, "Round of 32": 7, "Sweet 16": 5,
                "Elite 8": 4, "Final Four": 2, "Championship": 0
            },
            "per_round_total": {
                "Round of 64": 32, "Round of 32": 16, "Sweet 16": 8,
                "Elite 8": 4, "Final Four": 2, "Championship": 1
            },
            "n_games": 63,
            "n_upsets": 11,
            "upset_correct": 6,
            "upset_detection_rate": 0.545
        },
        ... (2022, 2023, 2024 similar)
    ],
    "summary": {
        "mean_brier": 0.190,
        "mean_log_loss": 0.557,
        "mean_accuracy": 0.690,
        "mean_espn_score": 1100
    }
}
```

### Anti-Patterns to Avoid

- **Using the saved model artifact for predictions**: `models/logistic_baseline.joblib` was trained on ALL seasons (2008–2025). Using it for a 2022 backtest would include 2022–2025 training data — data leakage. Extract `best_C` from the artifact but re-fit the model per fold.
- **Computing game-level metrics from individual `predict_fn()` calls**: The test games must be scored using the fold-specific `scaler.transform()` on the full test feature matrix, not one-by-one `predict_fn()` calls (which is slower and slightly more error-prone for batch metrics).
- **Using `build_predict_fn()` from `bracket_schema.py` for backtests**: `build_predict_fn()` loads the saved model (trained on all data) and uses the current 2025 stats. This has two problems: (1) wrong training data temporal scope, (2) wrong stats year for historical backtests.
- **Scoring First Four slots (round 0) in ESPN scoring**: Standard ESPN bracket scoring covers 63 games (R1-R6), not 67. Do not add points for First Four slot predictions.
- **Round name normalization**: `tournament_games.parquet` uses `Sweet Sixteen` and `Elite Eight`. `ROUND_NAMES` from `bracket_schema.py` uses `Sweet 16` and `Elite 8`. Use `ROUND_NAMES` consistently for output; normalize when comparing if needed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Walk-forward model fitting | Custom train/test split | `walk_forward_splits()` + Pattern 1 above | Already leakage-safe; maintains consistent fold boundaries |
| Actual slot winner lookup | DayNum-based game matching | `MNCAATourneySeedRoundSlots.csv` join pattern | CSV handles all seed routing without manual bracket knowledge |
| Bracket simulation | Custom forward-pass bracket fill | `simulate_bracket(mode='deterministic')` from Phase 4 | Already handles FF, canonical ordering, all 67 slots |
| Per-game Brier/log-loss | Custom loops | `sklearn.metrics.brier_score_loss`, `log_loss` | Handles edge cases, efficient |
| JSON output | Custom serialization | `json.dumps()` with Python-native types | All numpy types must be converted to Python-native first |

**Key insight:** Phase 5 is primarily an orchestration layer. All heavy lifting is done by Phases 3 and 4 components. The new code is ~200-300 lines of coordination, not new algorithms.

## Common Pitfalls

### Pitfall 1: Saved Model Used for Predictions Instead of best_C Extraction
**What goes wrong:** `load_model("models/logistic_baseline.joblib")` returns a model trained on 2008–2025. Using it directly for a 2022 backtest includes future training data (2022–2025 seasons) in the model.
**Why it happens:** The saved artifact is the "production" model; it's natural to load it directly.
**How to avoid:** Load the artifact only to extract `best_C = artifact["best_C"]`. Then re-fit a new `LogisticRegression(C=best_C)` + `StandardScaler` using only `train_df` (Season < test_year). This matches `evaluate_all_holdout_years()` in `evaluate.py`.
**Warning signs:** Backtest metrics suspiciously better than Phase 3 evaluation results; 2025 metrics significantly different from `evaluation_results.json`.

### Pitfall 2: MNCAATourneySeedRoundSlots.csv Has No Season Column
**What goes wrong:** Developer adds `WHERE Season = year` filter to the SeedRoundSlots query and gets empty results or a BinderException.
**Why it happens:** The file structure looks like tournament-season data, but it's actually a static routing table that applies to all years.
**How to avoid:** Query the CSV without any season filter. Season isolation is handled by filtering `seeds.parquet` to the target season (which provides the right team IDs) and filtering `tournament_games.parquet` by season.
**Warning signs:** `duckdb.BinderException: Referenced column "Season" not found`.

### Pitfall 3: stats_lookup Year Cross-Contamination
**What goes wrong:** Developer calls `build_stats_lookup()` once (outside the year loop) and passes the same lookup to all year-specific `predict_fn` closures. This is actually FINE, because each year's `compute_features(year, team_a, team_b, stats_lookup)` call uses the `(year, team_id)` key — each year's features pull from that year's ratings.
**Why it seems like a problem:** The lookup contains ALL years simultaneously.
**Why it's not a problem:** The year parameter passed to `compute_features()` ensures only that year's stats are accessed. No cross-year contamination.
**Recommendation:** Call `build_stats_lookup()` once before the year loop for efficiency (it reads parquet files).

### Pitfall 4: Round Name Mismatch Between Systems
**What goes wrong:** When comparing round names from `tournament_games.parquet` to slot round names from `ROUND_NAMES`, there's a mismatch: the parquet uses `Sweet Sixteen` and `Elite Eight`, while `ROUND_NAMES` uses `Sweet 16` and `Elite 8`.
**How to avoid:** Use `slot_round_number(slot_id)` to get the numeric round (0-6), then use `ROUND_NAMES[round_num]` for all output. Do not mix round names from different sources. If per-game metrics are needed by round, use DayNum ranges (136-137 = R1, etc.) rather than the Round string column.
**Warning signs:** KeyError on round name lookup; per-round accuracy dict has unexpected keys.

### Pitfall 5: Bracket Accuracy vs Independent Game Accuracy
**What goes wrong:** Developer computes "per-round accuracy" as "fraction of actual games the model correctly predicted" (independent scoring), which would be the same as the accuracy metric in Phase 3. This is different from bracket accuracy.
**Why it happens:** Both metrics are "correct picks per round" — ambiguous.
**How to avoid:** Phase 5 per-round accuracy is bracket-based: "for each slot in this round, does the predicted team match the actual winner?" Since errors compound (wrong R1 winner = wrong R2 prediction), bracket accuracy is typically LOWER than independent game accuracy in later rounds.
**Concrete example:** In the 2025 backtest (verified by execution), R2 bracket accuracy was 7/16 = 44%, but the independent game accuracy for 2025 was 73.3%. These are different metrics measuring different things.

### Pitfall 6: First Four Teams in stats_lookup
**What goes wrong:** First Four teams (e.g., St. Francis PA 2025) may not be in `historical_torvik_ratings.parquet`. If a First Four team advances to R1 (as a seeded team after winning their FF game) and appears in a bracket slot, `compute_features()` raises `KeyError`.
**Why it happens:** The cbbdata API doesn't always cover First Four teams; they may be in the fallback archive or missing entirely.
**How to avoid:** The simulator handles FF in the seedings dict — after the FF game, the winner appears in downstream slots. If the winner's team_id is missing from `stats_lookup`, `compute_features()` will raise `KeyError`. Add a `try/except` in the predict_fn closure that returns `0.5` (no information) for missing teams. This matches the behavior in `build_matchup_dataset()` which drops missing teams.
**Warning signs:** `KeyError: Team XXXX not found in stats_lookup for season YYYY`.

### Pitfall 7: simulate_bracket() Requires stats_lookup for Score Prediction
**What goes wrong:** `simulate_bracket()` prints a warning and sets `championship_game = None` when `stats_lookup` is not passed. This doesn't affect bracket scoring (ESPN points) but may be confusing.
**How to avoid:** Pass `stats_lookup=stats_lookup` to `simulate_bracket()` to enable championship score prediction. The score prediction is a bonus feature (from Phase 4) not required for Phase 5 metrics, but it's free to include.

## Code Examples

Verified patterns from direct code execution:

### End-to-End 2025 Backtest (Verified by Execution)
```python
# Source: verified by running against actual data in madness2026 repo
# ESPN Score computed: 1200 / 1920 max (62.5%)
# Per-round: R1=22/32 (69%), R2=7/16 (44%), R3=5/8 (63%), R4=4/4 (100%), R5=2/2 (100%), R6=0/1 (0%)
# Championship prediction: Houston (wrong), actual: Florida 65-63

from src.models.features import FEATURE_COLS, build_matchup_dataset, build_stats_lookup, compute_features
from src.models.temporal_cv import BACKTEST_YEARS
from src.models.train_logistic import ClippedCalibrator, CLIP_LO, CLIP_HI
from src.simulator.bracket_schema import load_seedings, build_predict_fn, ROUND_NAMES, slot_round_number
from src.simulator.simulate import simulate_bracket
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import joblib, numpy as np

# Load only best_C from artifact (don't use artifact's model/scaler)
artifact = joblib.load("models/logistic_baseline.joblib")
best_C = artifact["best_C"]  # 2.3916

# Build full matchup dataset and stats lookup (once, outside loop)
df = build_matchup_dataset()
stats_lookup = build_stats_lookup()

for test_year in BACKTEST_YEARS:
    # Step 1: Re-fit model on pre-year training data
    train_df = df[df['Season'] < test_year].copy()
    X_train = train_df[FEATURE_COLS].values
    y_train = train_df['label'].values

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    clf = LogisticRegression(C=best_C, class_weight='balanced',
                             solver='lbfgs', max_iter=1000, random_state=42)
    clf.fit(X_train_scaled, y_train)
    calibrated_clf = ClippedCalibrator(clf, clip_lo=CLIP_LO, clip_hi=CLIP_HI)

    # Step 2: Build predict_fn using year-specific stats
    def predict_fn(team_a_id: int, team_b_id: int, year=test_year) -> float:
        features = compute_features(year, team_a_id, team_b_id, stats_lookup)
        x = np.array([features[name] for name in FEATURE_COLS]).reshape(1, -1)
        return float(calibrated_clf.predict_proba(scaler.transform(x))[0, 1])

    # Step 3: Load seedings and simulate
    seedings = load_seedings(season=test_year)
    sim_result = simulate_bracket(seedings, predict_fn, mode='deterministic',
                                  season=test_year, stats_lookup=stats_lookup)
    predicted_slots = {sid: data['team_id'] for sid, data in sim_result['slots'].items()}

    # Step 4: Get actual slot winners
    actual_winners = build_actual_slot_winners(test_year)  # see Pattern 2

    # Step 5: Compute ESPN score
    bracket_metrics = score_bracket(predicted_slots, actual_winners)  # see Pattern 3

    # Step 6: Compute game-level metrics
    test_df = df[df['Season'] == test_year].copy()
    X_test_scaled = scaler.transform(test_df[FEATURE_COLS].values)
    y_test = test_df['label'].values
    y_prob = calibrated_clf.predict_proba(X_test_scaled)[:, 1]
    # ... brier_score_loss, log_loss, etc.
```

### Actual Slot Winners Build (Verified for 2022-2025)
```python
# Source: verified by running against data files — returns 67 winners per year
# All four years produce: {0: 4 FF slots, 1: 32, 2: 16, 3: 8, 4: 4, 5: 2, 6: 1}
import duckdb

def build_actual_slot_winners(season: int) -> dict[str, int]:
    conn = duckdb.connect()
    df = conn.execute(f"""
        WITH team_slots AS (
            SELECT DISTINCT s.TeamID, sr.GameSlot, sr.GameRound,
                   sr.EarlyDayNum, sr.LateDayNum
            FROM read_parquet('data/processed/seeds.parquet') s
            JOIN read_csv('data/raw/kaggle/MNCAATourneySeedRoundSlots.csv') sr
                ON s.Seed = sr.Seed
            WHERE s.Season = {season}
        )
        SELECT ts.GameSlot AS slot_id, g.WTeamID AS actual_winner
        FROM team_slots ts
        JOIN read_parquet('data/processed/tournament_games.parquet') g
            ON g.Season = {season}
            AND g.DayNum BETWEEN ts.EarlyDayNum AND ts.LateDayNum
            AND (g.WTeamID = ts.TeamID OR g.LTeamID = ts.TeamID)
            AND g.WTeamID = ts.TeamID
        ORDER BY ts.GameSlot
    """).df()
    conn.close()
    return dict(zip(df['slot_id'], df['actual_winner']))
```

### ESPN Scoring Constants and Maximum
```python
# Source: ESPN bracket challenge official scoring rules (well-known standard)
ESPN_ROUND_POINTS = {
    1: 10,   # Round of 64  (32 games × 10 = 320 pts)
    2: 20,   # Round of 32  (16 games × 20 = 320 pts)
    3: 40,   # Sweet 16     ( 8 games × 40 = 320 pts)
    4: 80,   # Elite 8      ( 4 games × 80 = 320 pts)
    5: 160,  # Final Four   ( 2 games × 160 = 320 pts)
    6: 320,  # Championship ( 1 game × 320 = 320 pts)
}
ESPN_MAX_SCORE = 1920  # 6 × 320 = 1920 points maximum
```

## Key Data Facts (from Direct Inspection)

1. **MNCAATourneySeedRoundSlots.csv has NO season column.** It is a universal routing table (W01 always goes to R1W1, etc.). Season isolation comes entirely from `seeds.parquet` filtering.

2. **Slot ID consistency verified:** FF slot IDs from the simulator (`build_slot_tree()`) exactly match the `GameSlot` values from `MNCAATourneySeedRoundSlots.csv` for all four backtest years (2022: W12/X11/Y16/Z16; different years have different FF slots).

3. **All 67 actual slot winners are available** for 2022, 2023, 2024, 2025 in `tournament_games.parquet`. The join returns exactly 4 FF + 63 bracket games per year.

4. **Historical ratings coverage for backtest years:**
   - 2022: 355/358 teams matched (Kaggle IDs)
   - 2023: 362/363 teams matched
   - 2024: 362/362 teams matched
   - 2025: 364/364 teams matched
   - Tournament teams with ratings (all 4 backtest years): ~60 out of 64 non-FF teams

5. **2025 stats are identical** between `historical_torvik_ratings.parquet` (season=2025) and `current_season_stats.parquet` (year=2025). Only 4 teams differ by < 0.1 (rounding). No leakage concern either way.

6. **2025 ESPN score verified:** Using model re-fit on 2008-2024 data, the 2025 backtest produced ESPN score of 1200/1920. Model correctly predicted all 4 #1 seeds to Final Four but missed the Championship (predicted Houston, actual Florida).

7. **Upset profile by year:**
   - 2022: 21 upsets (33% upset rate) — Saint Peter's 15-seed to Elite Eight, beat 2/3/7-seeds
   - 2023: 19 upsets (30% upset rate) — FAU 9-seed to Final Four
   - 2024: 20 upsets (32% upset rate) — NC State 11-seed to Final Four
   - 2025: 14 upsets (22% upset rate) — all-chalk Final Four (all 4 #1 seeds)

8. **Round naming convention to use:** Always use `ROUND_NAMES` from `bracket_schema.py` for output (`Sweet 16`, `Elite 8`). Do not mix with tournament data round strings (`Sweet Sixteen`, `Elite Eight`).

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Manual bracket scoring (count by hand) | Automated via slot ID join to tournament results | Reproducible and extensible to any year |
| Using production model for backtests | Re-fit per fold (walk-forward) | Correct temporal isolation; matches Phase 3 evaluation pattern |
| Game-level accuracy only | Both game-level (Brier/accuracy) and bracket-level (ESPN/per-round) | Full picture: probabilistic quality + bracket prediction quality |

## Open Questions

1. **Brier/log-loss in backtest vs evaluation_results.json**
   - What we know: Phase 3 `evaluation_results.json` has per-year Brier/log-loss. Phase 5 will recompute them.
   - What's unclear: Should Phase 5 assert that recomputed values match evaluation_results.json (to verify reproducibility)?
   - Recommendation: Yes, add an assertion or at least a comparison print. Values should match to 4 decimal places since same random_state=42 and same best_C.

2. **First Four winner edge cases in features**
   - What we know: Some First Four teams (e.g., St. Francis PA 2025) may be in `historical_torvik_ratings.parquet` with missing stats or not at all.
   - What's unclear: Exactly which FF teams are missing from the stats lookup for each year.
   - Recommendation: In `predict_fn` closure, wrap `compute_features()` in a try/except that returns `0.5` for any missing team (equivalent to "no information"). Document this fallback in the function.

3. **Multiple-year seedings for `build_stats_lookup()`**
   - What we know: `build_stats_lookup()` blends historical_torvik and current_season_stats for 2025. For backtest years 2022-2024, all data comes from historical_torvik.
   - What's unclear: Should backtest call `build_stats_lookup()` once (current behavior, returning all years) or year-specifically (filtering to only the target year's stats)?
   - Recommendation: Call once outside the loop (efficient). The `(year, team_id)` key structure ensures only the correct year's stats are used per backtest fold. No code change needed.

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `src/models/evaluate.py` — `evaluate_all_holdout_years()` pattern confirmed; provides exact blueprint for per-fold model re-fitting
- Direct code inspection: `src/simulator/simulate.py`, `src/simulator/bracket_schema.py` — `simulate_bracket()` API, `slot_round_number()`, `ROUND_NAMES` confirmed
- Direct code inspection: `src/models/features.py` — `build_stats_lookup()`, `compute_features()`, `FEATURE_COLS` confirmed
- Direct code inspection: `src/models/train_logistic.py` — `ClippedCalibrator`, `CLIP_LO=0.05`, `CLIP_HI=0.89`, `best_C=2.3916` confirmed from evaluation_results.json
- Live execution against actual data files — 2025 ESPN score (1200), per-round breakdown, actual slot winner query (67 per year) all verified
- `data/raw/kaggle/MNCAATourneySeedRoundSlots.csv` — direct inspection: no Season column, GameRound 0-6, exact slot IDs verified against bracket_schema.py output
- `data/processed/tournament_games.parquet` — verified 2022-2025 results, 67 games per year (63 bracket + 4 FF)

### Secondary (MEDIUM confidence)
- ESPN bracket scoring rules: 10/20/40/80/160/320 per round — standard well-known ESPN challenge scoring; not verified against current ESPN docs but universally documented
- 2025 tournament narrative (Wikipedia article in repo) — confirmed all-chalk Final Four (Florida, Houston, Duke, Auburn all #1 seeds)

### Tertiary (LOW confidence)
- None — all findings verified against actual data or code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml and working in prior phases
- Architecture patterns: HIGH — end-to-end execution verified for 2025 backtest year
- Data pipeline: HIGH — all data files verified, join query tested for 2022-2025
- ESPN scoring: HIGH — point values are established standard; implementation verified by code execution
- Pitfalls: HIGH — most discovered by actual execution (round name mismatch, SeedRoundSlots no-season-column)

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable; data files static; library versions pinned in pyproject.toml)
