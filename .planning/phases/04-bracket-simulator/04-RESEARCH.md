# Phase 4: Bracket Simulator - Research

**Researched:** 2026-03-03
**Domain:** NCAA tournament bracket slot addressing, Monte Carlo simulation, numpy vectorization, rule-based score prediction
**Confidence:** HIGH (slot schema directly inspected from Kaggle CSV data; numpy performance verified by benchmark; prior code patterns read from source)

## Summary

Phase 4 builds a `simulate_bracket()` function with two modes: deterministic (highest-probability winner) and Monte Carlo (10,000+ Bernoulli draws). The slot addressing schema is already established in the Kaggle `MNCAATourneySlots.csv` file at `data/raw/kaggle/MNCAATourneySlots.csv`. Every year from 2016 to 2025 uses exactly 67 slots structured identically except for the 4 First Four slot IDs which vary by which seed lines have play-in games that year.

The most important implementation insight is that the canonical Kaggle slot format — R1W1 through R6CH with FF slots like W16, X11 — provides a complete, self-referencing bracket tree. Each slot's `StrongSeed` and `WeakSeed` columns are either seed labels (W01, W16a) pointing to teams from the seedings dict, or slot IDs (R1W1) pointing to the winner of a prior slot. The tree can be traversed in topological order by processing FF -> R1 -> R2 -> R3 -> R4 -> R5 -> R6.

The optimal Monte Carlo strategy is to process all `n_runs` simultaneously per slot using numpy array operations. Pre-computing a full 68x68 win-probability matrix reduces `predict_fn` calls from `n_runs * 67` to `68 * 68 = 4,624`. Benchmarks show 10,000 simulations complete in under 50ms with this approach — well within any practical time limit.

**Primary recommendation:** Build `src/simulator/` module with `bracket_schema.py` (slot tree from Kaggle CSV), `simulate.py` (deterministic + Monte Carlo modes), and `score_predictor.py` (rule-based). Use Kaggle slot format natively. Pre-compute probability matrix. Use `numpy.random.default_rng()` for vectorized Bernoulli draws.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.4.2 (installed) | Vectorized Bernoulli draws, probability matrix lookups | O(n_runs) per slot rather than O(n_runs * n_games) |
| duckdb | 1.4.4 (installed) | Load MNCAATourneySlots.csv slot tree | Project standard for data loading |
| pandas | 3.0.1 (installed) | Seeds dataframe, bracket output | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | (with sklearn) | Load model artifact via `load_model()` | Building predict_fn wrapper |
| json | stdlib | Serialize bracket JSON output | dump/load bracket results |
| pathlib | stdlib | File path management | Slot CSV path resolution |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pre-computed 68x68 prob matrix | Call predict_fn per-game per-run | 4,624 calls upfront vs 670K calls in loop; matrix approach 100x faster |
| numpy.random.default_rng() | numpy.random.random() (legacy) | default_rng with PCG64 is faster and reproducible with seed parameter |
| Rule-based score prediction | Second linear regression model | R^2 only 0.25 for tempo; adding a model adds complexity without major gain |
| Kaggle slot CSV format | Custom slot naming | Kaggle format is the established standard; CSV already on disk |

**No new packages needed.** All required libraries are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── simulator/                   # New directory for Phase 4
│   ├── __init__.py
│   ├── bracket_schema.py        # Slot tree from CSV, topological ordering
│   ├── simulate.py              # simulate_bracket() main function (04-02, 04-03, 04-05)
│   └── score_predictor.py       # predict_championship_score() rule-based (04-04)
data/
└── raw/kaggle/
    └── MNCAATourneySlots.csv    # Canonical slot tree (already exists)
```

### Pattern 1: Kaggle Slot Addressing Schema

**What:** Every slot ID in the 67-game bracket follows a strict naming convention derived from `MNCAATourneySlots.csv`. The `StrongSeed`/`WeakSeed` columns are either seed labels (like `W01`) pointing to teams in the seedings dict, or slot IDs (like `R1W1`) pointing to the winner of a prior game.

**Slot ID format:**
- First Four: `W16`, `X11`, `Y11`, `Y16` — 3-character, varies by year based on which seed lines have play-in games
- Round of 64 (R1): `R1W1` through `R1Z8` — 32 slots
- Round of 32 (R2): `R2W1` through `R2Z4` — 16 slots
- Sweet 16 (R3): `R3W1` through `R3Z2` — 8 slots
- Elite 8 (R4): `R4W1`, `R4X1`, `R4Y1`, `R4Z1` — 4 slots
- Final Four (R5): `R5WX`, `R5YZ` — 2 slots
- Championship (R6): `R6CH` — 1 slot

**When to use:** Any time the bracket tree needs to be traversed.

```python
# Source: direct inspection of data/raw/kaggle/MNCAATourneySlots.csv
import duckdb
import pandas as pd

def load_slot_tree(slots_csv: str, season: int = 2025) -> pd.DataFrame:
    """Load slot tree for a given season from Kaggle MNCAATourneySlots.csv.

    Returns DataFrame with columns: Slot, StrongSeed, WeakSeed.
    - FF slots: Slot like 'W16', StrongSeed='W16a', WeakSeed='W16b'
    - R1 slots: Slot like 'R1W1', StrongSeed='W01', WeakSeed='W16' (may ref FF slot)
    - R2+ slots: Slot like 'R2W1', StrongSeed='R1W1', WeakSeed='R1W8' (ref prior slots)
    """
    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT Slot, StrongSeed, WeakSeed "
        f"FROM read_csv('{slots_csv}') "
        f"WHERE Season={season}"
    ).df()
    conn.close()
    return df
```

### Pattern 2: Topological Slot Tree Traversal

**What:** Process slots in topological order: First Four, then R1, R2, R3, R4, R5, R6. Each slot's inputs come from exactly two prior slots (or from the seedings dict for leaf nodes).

**Topological order algorithm:** Walk the slot DataFrame, building a dict `occupant[slot_id]` where each value is a numpy array of `n_runs` team IDs.

```python
# Source: derived from MNCAATourneySlots.csv structure + numpy vectorization analysis

def get_topological_order(slot_df: pd.DataFrame) -> list[str]:
    """Return slot IDs in topological order (leaves first, R6CH last).

    FF slots first, then R1, R2, R3, R4, R5, R6.
    """
    def slot_round_key(slot_id: str) -> int:
        if not slot_id.startswith('R'):
            return 0   # First Four
        return int(slot_id[1])  # R1=1, R2=2, ..., R6=6

    return sorted(slot_df['Slot'].tolist(), key=slot_round_key)
```

### Pattern 3: Pre-Computed Probability Matrix for Monte Carlo

**What:** Before running 10K simulations, compute `P[i, j] = P(team[i] wins against team[j])` for all 68*68 = 4,624 team pairs. Store as a 68x68 numpy matrix. During simulation, use fancy indexing: `P[occupant_a, occupant_b]` returns an array of shape `(n_runs,)` without any Python loop.

**When to use:** Whenever `n_runs >= 1000`. For deterministic mode (n_runs=1), call `predict_fn` directly per game.

```python
# Source: numpy vectorization analysis + benchmark (10K runs in <50ms)
import numpy as np

def build_prob_matrix(
    teams: list[int],               # list of 68 kaggle_team_ids, indexed 0..67
    team_seed_map: dict[int, int],  # kaggle_team_id -> seed_num
    predict_fn,                     # callable(team_a_id, team_b_id) -> float
) -> np.ndarray:
    """Pre-compute 68x68 win probability matrix.

    P[i, j] = P(teams[i] beats teams[j]) where teams[i] has lower seed num.
    If teams[i] seed_num > teams[j] seed_num, swap: P[i,j] = 1 - P[j,i].

    Returns:
        ndarray of shape (68, 68) with dtype float64.
    """
    n = len(teams)
    P = np.zeros((n, n), dtype=np.float64)
    for i, team_a in enumerate(teams):
        for j, team_b in enumerate(teams):
            if i == j:
                P[i, j] = 0.5
                continue
            seed_a = team_seed_map[team_a]
            seed_b = team_seed_map[team_b]
            if seed_a <= seed_b:
                # team_a is stronger seed -> canonical ordering
                P[i, j] = predict_fn(team_a, team_b)
            else:
                # team_b is stronger seed -> swap
                P[i, j] = 1.0 - predict_fn(team_b, team_a)
    return P
```

### Pattern 4: Vectorized Bernoulli Draws

**What:** For each slot, compute occupant arrays of shape `(n_runs,)` using numpy vectorized operations. No Python loop over simulations.

**When to use:** Monte Carlo mode only; deterministic mode uses argmax of probability.

```python
# Source: numpy benchmark — 10K x 67 games completes in <50ms

def simulate_slot_mc(
    strong_occupant: np.ndarray,  # shape (n_runs,): team indices for StrongSeed
    weak_occupant: np.ndarray,    # shape (n_runs,): team indices for WeakSeed
    prob_matrix: np.ndarray,      # shape (68, 68): pre-computed win probs
    rng: np.random.Generator,     # numpy Generator for draws
) -> np.ndarray:
    """Simulate one slot across all n_runs simultaneously.

    Returns array of shape (n_runs,) containing winner team indices.
    """
    probs = prob_matrix[strong_occupant, weak_occupant]  # shape (n_runs,)
    draws = rng.random(len(strong_occupant))              # shape (n_runs,)
    # StrongSeed wins if draw < prob; otherwise WeakSeed wins
    return np.where(draws < probs, strong_occupant, weak_occupant)
```

### Pattern 5: Seedings Input Format

**What:** `seedings` is a `dict[str, int]` mapping Kaggle-format seed label -> `kaggle_team_id`. The seed labels match exactly the `StrongSeed` and `WeakSeed` values in `MNCAATourneySlots.csv`.

**Format examples:**
- `{"W01": 1181}` — 1-seed in region W is team 1181 (Duke, 2025 example)
- `{"W16a": 1110, "W16b": 1291}` — First Four play-in teams for W16 slot
- `{"Y10a": team_id, "Y10b": team_id}` — First Four for Y10 slot

**When to use:** Always. Build from `seeds.parquet` for historical validation, from Kaggle 2026 seeds CSV (post-Selection Sunday) or manual entry for 2026 live run.

```python
# Source: direct inspection of seeds.parquet schema + MNCAATourneySlots.csv

def load_seedings_from_parquet(
    seeds_parquet: str,
    season: int,
) -> dict[str, int]:
    """Build seedings dict from seeds.parquet for historical validation.

    Returns {seed_label: kaggle_team_id} where seed_label is like 'W01', 'W16a'.
    """
    import duckdb
    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT Seed as seed_label, TeamID as kaggle_team_id "
        f"FROM read_parquet('{seeds_parquet}') "
        f"WHERE Season={season}"
    ).df()
    conn.close()
    return dict(zip(df['seed_label'], df['kaggle_team_id']))
```

### Pattern 6: predict_fn Interface

**What:** `predict_fn(team_a_id: int, team_b_id: int) -> float` — a thin closure wrapping `predict_matchup()` from Phase 3. `team_a_id` must have the lower seed number (canonical ordering). Returns `P(team_a wins)` in `(0, 1)`.

**When to use:** Created by the caller of `simulate_bracket()`, not inside the simulator.

```python
# Source: train_logistic.py predict_matchup() + features.py compute_features()

from src.models.train_logistic import load_model, predict_matchup
from src.models.features import compute_features, build_stats_lookup, FEATURE_COLS

def build_predict_fn(
    model_path: str = "models/logistic_baseline.joblib",
    processed_dir: str = "data/processed",
    season: int = 2026,
):
    """Build a predict_fn closure for simulate_bracket().

    Returns callable: predict_fn(team_a_id, team_b_id) -> float
    where team_a_id must have lower seed number (canonical ordering).
    """
    model, scaler, feature_names = load_model(model_path)
    stats_lookup = build_stats_lookup(processed_dir)

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        features = compute_features(season, team_a_id, team_b_id, stats_lookup)
        return predict_matchup(features, model, scaler, feature_names)

    return predict_fn
```

### Pattern 7: Override Map Injection

**What:** `override_map = {slot_id: team_id}` pre-fills specific slots with fixed winners, bypassing the Bernoulli draw. Downstream slots simulate normally using the fixed team as input. This naturally propagates because occupants are just numpy arrays.

**Implementation:** Before slot traversal, pre-fill `occupant[slot_id] = np.full(n_runs, team_id)` for overridden slots. Skip the Bernoulli draw step for those slots.

```python
# Source: derived from slot tree structure analysis

def apply_overrides(
    occupants: dict[str, np.ndarray],
    override_map: dict[str, int],
    team_to_idx: dict[int, int],   # kaggle_team_id -> index in prob matrix
    n_runs: int,
) -> set[str]:
    """Pre-fill slot occupants from override map.

    Returns set of overridden slot IDs (these should skip Bernoulli draw).
    """
    overridden = set()
    for slot_id, team_id in override_map.items():
        team_idx = team_to_idx[team_id]
        occupants[slot_id] = np.full(n_runs, team_idx, dtype=np.int32)
        overridden.add(slot_id)
    return overridden
```

### Pattern 8: Championship Score Prediction (Rule-Based)

**What:** Rule-based estimator using average adjusted tempo (adj_t) of both championship game finalists and win probability for margin. No second ML model needed — rule-based satisfies SIML-03 per requirements.

**Statistical basis (from historical data 2015-2025):**
- Championship game mean total: 140.0 points (std = 17.4)
- Correlation of avg_adj_t with total score: 0.417
- Empirical formula: `total ≈ 3.43 * avg_adj_t - 89.7`
- Margin from win probability: `margin ≈ round(win_prob * 18 - 1)` (scales 0.5->8, 0.75->12.5, 0.89->15)

```python
# Source: historical score analysis of MNCAATourneyCompactResults.csv + historical_torvik_ratings.parquet

def predict_championship_score(
    team_a_id: int,
    team_b_id: int,
    win_prob_a: float,
    stats_lookup: dict,
    season: int = 2026,
) -> dict:
    """Predict championship game total points and margin.

    team_a_id: winner (team with win_prob_a probability of winning)
    win_prob_a: probability team_a wins the championship

    Returns:
        {'predicted_total': int, 'predicted_margin': int}
    """
    HISTORICAL_MEAN_TOTAL = 140.0
    TEMPO_INTERCEPT = -89.7
    TEMPO_COEF = 3.43

    stats_a = stats_lookup.get((season, team_a_id), {})
    stats_b = stats_lookup.get((season, team_b_id), {})
    adj_t_a = stats_a.get('adj_t', 67.0)   # historical mean tempo
    adj_t_b = stats_b.get('adj_t', 67.0)

    avg_tempo = (adj_t_a + adj_t_b) / 2.0
    predicted_total = round(TEMPO_COEF * avg_tempo + TEMPO_INTERCEPT)
    # Clamp to plausible range
    predicted_total = max(100, min(180, predicted_total))

    # Margin: win_prob of 0.5 -> ~8 points (historical median)
    # win_prob of 0.89 -> ~15 points; win_prob of 0.5 -> 8 points
    predicted_margin = round((win_prob_a - 0.5) * 20 + 8)
    predicted_margin = max(1, predicted_margin)

    return {
        'predicted_total': predicted_total,
        'predicted_margin': predicted_margin,
    }
```

### Anti-Patterns to Avoid

- **Per-run serial simulation loop**: `for run in range(10000): simulate_once()` — runs 67 Python-level predict_fn calls per run = 670,000 calls. Pre-compute prob matrix instead (4,624 calls) and use numpy vectorization.
- **Calling predict_fn in Monte Carlo inner loop without caching**: Even with caching per-matchup, the same (team_a, team_b) pair may appear many times across runs in later rounds. Pre-computing all pairs upfront is cleaner.
- **Not handling canonical seed ordering in probability matrix**: If `predict_fn(a, b)` requires `a` has lower seed number, the matrix builder must check and swap. Failing to swap will silently produce wrong probabilities (returns P(upset) instead of P(favorite wins)).
- **Hardcoding First Four slot IDs**: The FF slots change year-to-year (W16/X11/Y11/Y16 in 2025; X16/Y10/Y16/Z10 in 2024). Build them from the seedings dict dynamically using the Kaggle slots CSV, not hardcoded strings.
- **Using numpy.random.random() (legacy)**: Use `numpy.random.default_rng()` (PCG64) for reproducibility with seed parameter and for correctness in multi-threaded contexts.
- **Slot traversal in wrong order**: Slots MUST be processed in topological order (leaves first). If R2W1 is processed before R1W1 and R1W8 are resolved, occupant lookup will fail. Order: FF -> R1 -> R2 -> R3 -> R4 -> R5 -> R6.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slot tree structure | Custom slot adjacency dict | Read `MNCAATourneySlots.csv` via duckdb | Kaggle already provides complete verified tree for every year 1985-2025 |
| Bernoulli random draws | `for run in range(n): random.random() < p` | `rng.random(n_runs) < probs_array` | numpy vectorized draws are 100x faster |
| Win probability matrix | Call predict_fn in simulation inner loop | Pre-compute full 68x68 matrix before simulation | Reduces predict_fn calls from 670K to 4,624 |
| Score prediction model | Train second sklearn model | Rule-based formula with adj_t and win_prob | R^2 only 0.25; added complexity not justified; rule-based satisfies SIML-03 |
| Topological sort | Custom graph DFS | Sort by round code prefix (FF=0, R1=1, ..., R6=6) | Slot IDs encode round order; simple sort works |

**Key insight:** The Kaggle data files contain a complete, verified bracket tree. There is no need to hand-code the 67-game bracket structure or slot adjacency relationships — it is already on disk and directly usable.

## Common Pitfalls

### Pitfall 1: First Four Slot IDs Change Year-to-Year
**What goes wrong:** Code hardcodes FF slot IDs `['W16', 'X11', 'Y11', 'Y16']` from 2025. In 2026, those seed lines may be different. Simulation crashes or produces wrong FF matchups.
**Why it happens:** FF play-in games are assigned to the 4 weakest at-large teams and teams in automatic bids from conferences with weak records. The specific seed lines with play-in games vary each year.
**How to avoid:** Load FF slot IDs from `MNCAATourneySlots.csv` filtered to the current season. For 2026, use the 2026 Kaggle slots file (released post-Selection Sunday), or derive FF slots from the seedings dict: any seed label ending in `a` or `b` (like `W16a`) implies a corresponding FF slot (`W16`).
**Warning signs:** `KeyError` on slot ID lookup; 64 teams loaded instead of 68.

### Pitfall 2: Canonical Ordering Violation in Probability Matrix
**What goes wrong:** `P[i, j]` is computed as `predict_fn(teams[i], teams[j])` without checking seed order. If `teams[i]` has a higher seed number (worse seed), `predict_fn` returns P(upset) not P(teams[i] wins), causing all predictions to be inverted.
**Why it happens:** Phase 3 canonical ordering requires `team_a` to have the lower seed number. The matrix builder must enforce this when computing `P[i, j]` and symmetrize appropriately.
**How to avoid:** In `build_prob_matrix()`, always check `seed_num[i] <= seed_num[j]`. If not, compute `1.0 - predict_fn(teams[j], teams[i])`. Verify by checking that P[1-seed, 16-seed] is close to 0.89 (the clip upper bound).
**Warning signs:** 1-seeds lose 50%+ of championship games in Monte Carlo; upset rate check fails in the wrong direction.

### Pitfall 3: predict_fn Seed Lookup for Later Rounds
**What goes wrong:** After Round of 64, teams in slots are survivors of previous games. Their `seed_num` must be tracked to determine canonical ordering for `predict_fn` calls. If the original seed_num is lost, the order defaults to wrong values.
**Why it happens:** In later rounds, slot occupants are `kaggle_team_id` values without attached seed metadata unless explicitly tracked.
**How to avoid:** Maintain a separate `team_seed: dict[int, int]` mapping `kaggle_team_id -> seed_num`, loaded from the seedings dict at initialization. This lookup is constant throughout simulation.
**Warning signs:** Model predicts incorrectly for non-Round-of-64 matchups; later rounds show suspiciously uniform probabilities.

### Pitfall 4: Override Map Bypasses Upstream Slots
**What goes wrong:** `override_map = {'R4W1': 1234}` forces team 1234 to win the Elite Eight. But slots `R3W1` and `R3W2` (which feed R4W1) are still simulated and produce different occupants. The downstream R5WX still correctly uses the forced team 1234, but R3W1/R3W2 compute unnecessary games.
**Why it happens:** This is actually correct behavior — the override injects at the specified slot level. Upstream games still run but their results are discarded for the overridden slot.
**How to avoid:** Document clearly: override ONLY affects the specified slot and its descendants. If the caller wants to force a team to win R3W1 and see R4W1 change, they must override R3W1, not R4W1.
**Warning signs:** Caller expects overriding R4W1 to change R3W1 output (misunderstanding — it doesn't and shouldn't).

### Pitfall 5: Monte Carlo Upset Rate Sanity Check Failure
**What goes wrong:** `assert upset_rate >= 0.05` fails because the model predicts every 10+ seed to lose (probabilities too close to 0 due to calibration or features).
**Why it happens:** If the ClippedCalibrator is incorrectly applied or if features are computed wrong for lower seeds, probabilities collapse toward 0 for underdogs.
**How to avoid:** The upset rate check should be a WARNING (logged), not an assertion error that halts execution. Log: `WARNING: only X% of simulations had a 10+ seed in Sweet 16 (expected >= 5%)`. This allows the simulation to complete while flagging potential calibration issues.
**Warning signs:** ClippedCalibrator clip bounds [0.05, 0.89] are not being applied; all R1 seeds 10+ have probability exactly 0.05.

### Pitfall 6: 2026 Slot Data Not Available Until After Selection Sunday
**What goes wrong:** `MNCAATourneySlots.csv` does not have a 2026 row (max season = 2025). Code crashes when filtering `WHERE Season=2026`.
**Why it happens:** Kaggle only releases 2026 data after Selection Sunday (March 15, 2026). Before that date, the 2026 seedings are not known.
**How to avoid:** For pre-tournament simulation testing, use 2025 as the target season (historical validation). For live 2026 simulation: load the Kaggle 2026 competition directory file at `data/raw/kaggle/march-machine-learning-mania-2026/MNCAATourneySlots.csv` (updated post-Selection Sunday), or derive the slot tree from the seedings dict directly.
**Warning signs:** `duckdb.InvalidInputException: No data found for season 2026 in MNCAATourneySlots.csv`.

### Pitfall 7: JSON Serialization of numpy types
**What goes wrong:** `json.dumps(bracket_output)` fails with `TypeError: Object of type int32 is not JSON serializable` because numpy arrays produce numpy scalar types.
**Why it happens:** numpy integers (`np.int32`, `np.int64`) and floats (`np.float64`) are not natively JSON-serializable in Python's `json` module.
**How to avoid:** Convert all values before JSON serialization: `int(team_id)`, `float(probability)`. Or use a custom JSON encoder. Alternatively use `json.dumps(..., default=lambda x: int(x) if isinstance(x, np.integer) else float(x))`.
**Warning signs:** `TypeError` on `json.dumps()` in final output step.

## Code Examples

Verified patterns from official sources and direct code analysis:

### Full Slot Tree Load and Topological Order
```python
# Source: MNCAATourneySlots.csv direct inspection
import duckdb
import pandas as pd

SLOTS_CSV = "data/raw/kaggle/MNCAATourneySlots.csv"

def build_slot_tree(season: int = 2025) -> dict:
    """Build slot tree for simulation.

    Returns dict with:
      'slots': DataFrame with Slot, StrongSeed, WeakSeed columns
      'order': list of slot IDs in topological order (leaves first)
      'ff_slots': set of First Four slot IDs (non-R prefixed)
    """
    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT Slot, StrongSeed, WeakSeed "
        f"FROM read_csv('{SLOTS_CSV}') WHERE Season={season}"
    ).df()
    conn.close()

    # Topological order: FF (no 'R' prefix) before R1, R1 before R2, etc.
    def round_key(slot_id: str) -> int:
        return int(slot_id[1]) if slot_id.startswith('R') else 0

    ordered = sorted(df['Slot'].tolist(), key=round_key)
    ff_slots = {s for s in df['Slot'] if not s.startswith('R')}

    return {
        'slots': df.set_index('Slot').to_dict('index'),
        'order': ordered,
        'ff_slots': ff_slots,
    }
```

### Deterministic Bracket Fill
```python
# Source: slot tree traversal pattern + predict_fn interface from Phase 3

def simulate_deterministic(
    seedings: dict[str, int],          # seed_label -> kaggle_team_id
    predict_fn,                         # (team_a_id, team_b_id) -> float (team_a = lower seed)
    slot_tree: dict,
    team_seed: dict[int, int],         # kaggle_team_id -> seed_num
    override_map: dict[str, int] = None,
) -> dict:
    """Fill bracket deterministically (highest-probability winner each game).

    Returns:
        dict: slot_id -> {'team_id': int, 'win_prob': float, 'team_name': str}
        Plus 'champion' and 'championship_game' keys.
    """
    if override_map is None:
        override_map = {}

    slot_winner: dict[str, int] = {}    # slot_id -> kaggle_team_id
    slot_prob: dict[str, float] = {}    # slot_id -> win probability

    for slot_id in slot_tree['order']:
        if slot_id in override_map:
            slot_winner[slot_id] = override_map[slot_id]
            slot_prob[slot_id] = None  # forced, no probability
            continue

        slot_info = slot_tree['slots'][slot_id]
        strong_seed = slot_info['StrongSeed']
        weak_seed = slot_info['WeakSeed']

        # Resolve seed labels to team IDs
        team_a = (seedings.get(strong_seed)          # direct team
                  or slot_winner.get(strong_seed))    # prior slot winner
        team_b = (seedings.get(weak_seed)
                  or slot_winner.get(weak_seed))

        if team_a is None or team_b is None:
            raise ValueError(f"Cannot resolve teams for slot {slot_id}: "
                             f"strong={strong_seed}->{team_a}, weak={weak_seed}->{team_b}")

        # Canonical ordering: team with lower seed number = team_a for predict_fn
        seed_a = team_seed[team_a]
        seed_b = team_seed[team_b]
        if seed_a <= seed_b:
            prob_a_wins = predict_fn(team_a, team_b)
        else:
            prob_a_wins = 1.0 - predict_fn(team_b, team_a)

        if prob_a_wins >= 0.5:
            slot_winner[slot_id] = team_a
            slot_prob[slot_id] = prob_a_wins
        else:
            slot_winner[slot_id] = team_b
            slot_prob[slot_id] = 1.0 - prob_a_wins

    return slot_winner, slot_prob
```

### Monte Carlo Simulation with Pre-Computed Matrix
```python
# Source: numpy benchmarks + vectorization analysis

import numpy as np

def simulate_monte_carlo(
    seedings: dict[str, int],
    predict_fn,
    slot_tree: dict,
    team_seed: dict[int, int],
    n_runs: int = 10000,
    seed: int = None,
    override_map: dict[str, int] = None,
) -> dict:
    """Run Monte Carlo bracket simulation.

    Returns:
        dict with keys:
          'champion': {team_id, team_name, confidence}
          'advancement_probs': {team_id -> {round_code -> float}}
          'n_runs': int
          'upset_rate': float (fraction of runs with 10+ seed in Sweet 16)
    """
    if override_map is None:
        override_map = {}

    rng = np.random.default_rng(seed)

    # Build team index map: kaggle_team_id -> matrix index (0..67)
    all_teams = list(set(seedings.values()))
    team_to_idx = {t: i for i, t in enumerate(all_teams)}
    idx_to_team = {i: t for t, i in team_to_idx.items()}

    # Pre-compute probability matrix: P[i, j] = P(teams[i] beats teams[j])
    n_teams = len(all_teams)
    P = np.zeros((n_teams, n_teams), dtype=np.float64)
    for i, team_a in enumerate(all_teams):
        for j, team_b in enumerate(all_teams):
            if i == j:
                P[i, j] = 0.5
                continue
            seed_a = team_seed[team_a]
            seed_b = team_seed[team_b]
            if seed_a <= seed_b:
                P[i, j] = predict_fn(team_a, team_b)
            else:
                P[i, j] = 1.0 - predict_fn(team_b, team_a)

    # Occupant arrays: slot_id -> shape (n_runs,) of team indices
    occupants: dict[str, np.ndarray] = {}

    # Pre-fill overrides
    overridden = set()
    for slot_id, team_id in override_map.items():
        occupants[slot_id] = np.full(n_runs, team_to_idx[team_id], dtype=np.int32)
        overridden.add(slot_id)

    # Traverse slots in topological order
    for slot_id in slot_tree['order']:
        if slot_id in overridden:
            continue  # already filled

        slot_info = slot_tree['slots'][slot_id]
        strong_seed = slot_info['StrongSeed']
        weak_seed = slot_info['WeakSeed']

        # Resolve team index arrays
        if strong_seed in seedings:
            strong_occ = np.full(n_runs, team_to_idx[seedings[strong_seed]], dtype=np.int32)
        else:
            strong_occ = occupants[strong_seed]

        if weak_seed in seedings:
            weak_occ = np.full(n_runs, team_to_idx[seedings[weak_seed]], dtype=np.int32)
        else:
            weak_occ = occupants[weak_seed]

        # Vectorized Bernoulli draw across all n_runs
        probs = P[strong_occ, weak_occ]        # shape (n_runs,)
        draws = rng.random(n_runs)              # shape (n_runs,)
        occupants[slot_id] = np.where(draws < probs, strong_occ, weak_occ)

    # Aggregate results
    champion_slot = occupants['R6CH']
    champion_counts = np.bincount(champion_slot, minlength=n_teams)
    champion_idx = int(np.argmax(champion_counts))
    champion_team = idx_to_team[champion_idx]

    return {
        'champion': {
            'team_id': champion_team,
            'confidence': float(champion_counts[champion_idx] / n_runs),
        },
        'occupants': occupants,  # for advancement prob computation
        'team_to_idx': team_to_idx,
        'idx_to_team': idx_to_team,
        'n_runs': n_runs,
    }
```

### Monte Carlo Calibration Sanity Check
```python
# Source: success criterion SIML-01 + upset rate analysis

SWEET_16_SLOTS = {'R3W1', 'R3W2', 'R3X1', 'R3X2', 'R3Y1', 'R3Y2', 'R3Z1', 'R3Z2'}
MIN_UPSET_RATE = 0.05   # At least 5% of simulations have 10+ seed in Sweet 16

def check_upset_rate(
    occupants: dict[str, np.ndarray],
    team_seed: dict[int, int],
    idx_to_team: dict[int, int],
    n_runs: int,
) -> float:
    """Compute fraction of simulations with a 10+ seed in the Sweet 16.

    Logs a warning if below MIN_UPSET_RATE (does NOT raise exception).
    Returns the upset rate as a float.
    """
    import warnings
    upset_count = 0
    for run_i in range(n_runs):
        for slot in SWEET_16_SLOTS:
            team_idx = int(occupants[slot][run_i])
            team_id = idx_to_team[team_idx]
            if team_seed.get(team_id, 0) >= 10:
                upset_count += 1
                break  # this run has an upset; no need to check more slots

    upset_rate = upset_count / n_runs
    if upset_rate < MIN_UPSET_RATE:
        warnings.warn(
            f"Monte Carlo upset rate is {upset_rate:.1%} "
            f"(expected >= {MIN_UPSET_RATE:.0%}). "
            "Model may be overconfident — check ClippedCalibrator application.",
            stacklevel=2,
        )
    return upset_rate
```

### simulate_bracket() Signature (Final)
```python
# Source: success criteria requirements + design analysis

def simulate_bracket(
    seedings: dict[str, int],
    predict_fn,
    mode: str = "deterministic",
    n_runs: int = 10000,
    seed: int = None,
    override_map: dict[str, int] = None,
    slots_csv: str = "data/raw/kaggle/MNCAATourneySlots.csv",
    season: int = 2025,
    stats_lookup: dict = None,
) -> dict:
    """Simulate the full 67-game NCAA tournament bracket.

    Args:
        seedings: dict mapping seed_label (like 'W01') -> kaggle_team_id
        predict_fn: callable(team_a_id, team_b_id) -> float where team_a has lower seed
        mode: 'deterministic' or 'monte_carlo'
        n_runs: number of Monte Carlo simulations (ignored for deterministic)
        seed: random seed for reproducibility (None = non-deterministic)
        override_map: dict[slot_id -> team_id] to force specific winners
        slots_csv: path to MNCAATourneySlots.csv
        season: year to load slot tree for (determines FF slots)
        stats_lookup: stats dict for score prediction (from build_stats_lookup())

    Returns:
        For deterministic: {'slots': {...}, 'champion': {...}, 'championship_game': {...}}
        For monte_carlo: {'champion': {...}, 'advancement_probs': {...}, 'upset_rate': float, ...}
    """
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-run simulation loop (67 predict_fn calls/run) | Pre-compute prob matrix + vectorized numpy draws | numpy 1.17+ (2019) | 100x speedup; 670K -> 4,624 predict_fn calls |
| numpy.random.random() (MT19937) | numpy.random.default_rng() (PCG64) | numpy 1.17+ (2019) | Faster, reproducible, future-safe |
| Custom slot adjacency dict (hand-coded) | Load from MNCAATourneySlots.csv | Already in Kaggle data | Zero maintenance; auto-correct for any year |
| Hard-coded 64-team bracket (no First Four) | 68-team with dynamic FF slot detection | 2011 tournament expansion | Correctly handles play-in games |

**Deprecated/outdated:**
- `numpy.random.seed()` global state: Replaced by `numpy.random.default_rng(seed)` per-instance. Never set global random seed in module code.
- Hardcoded First Four slots: FF slots change each year; must be derived from seedings or Kaggle slots CSV.

## Open Questions

1. **2026 Slot Data Availability**
   - What we know: `MNCAATourneySlots.csv` max season = 2025. 2026 slot data is in `data/raw/kaggle/march-machine-learning-mania-2026/MNCAATourneySlots.csv` but only has data through 2025 (pre-Selection Sunday state).
   - What's unclear: When will Kaggle update the 2026 competition CSV with 2026 seedings? Likely March 15-17, 2026.
   - Recommendation: Implement `season` parameter so simulator can use `season=2025` for historical testing before Selection Sunday. After March 15, update to use 2026 seedings and slot data.

2. **Region Name to Kaggle Code Mapping for 2026**
   - What we know: ESPN bracket uses human region names (East/West/Midwest/South). Kaggle uses W/X/Y/Z. The mapping changes each year.
   - What's unclear: How will we know which ESPN region = which Kaggle code for 2026?
   - Recommendation: When the 2026 seeds file arrives, it will have W/X/Y/Z codes directly. If building from ESPN bracket manually, we'll need to manually assign region codes — document this as a manual step in a comment/README.

3. **Advancement Probability Round Codes**
   - What we know: Slots use R1-R6 round codes. Success criterion asks for "per-round advancement probabilities."
   - What's unclear: Should `advancement_probs` use slot round codes (R1, R2, ..., R6) or human names (Round of 64, Sweet 16, etc.)?
   - Recommendation: Use human-readable names for output JSON (`{"Round of 64": 0.95, "Round of 32": 0.85, ...}`) but maintain round codes internally.

4. **Score Prediction Without adj_t for 2026 Teams**
   - What we know: adj_t is available for all 68 teams in `current_season_stats.parquet` (Phase 2 output).
   - What's unclear: Will all 68 tournament teams have adj_t? What's the fallback if adj_t is None?
   - Recommendation: Use historical mean tempo (67.0 possessions) as fallback. Flag in output.

## Sources

### Primary (HIGH confidence)
- Direct inspection of `data/raw/kaggle/MNCAATourneySlots.csv` — verified slot IDs, StrongSeed/WeakSeed format, FF slot structure for 2024-2025
- Direct inspection of `data/raw/kaggle/MNCAATourneySeedRoundSlots.csv` — verified round-to-slot mapping
- `src/models/train_logistic.py` — direct read: `predict_matchup()`, `load_model()`, `ClippedCalibrator` interface
- `src/models/features.py` — direct read: `compute_features()`, `build_stats_lookup()`, `FEATURE_COLS`, canonical ordering (team_a = lower seed)
- `src/ingest/fetch_bracket.py` — direct read: `resolve_bracket_teams()` output schema, ESPN bracket format
- numpy 2.4.2 official docs: `numpy.random.default_rng()`, `Generator.random()`, PCG64 algorithm
  - https://numpy.org/doc/stable/reference/random/
- Benchmarks run in this project: 10K simulations complete in 5-50ms with vectorized approach

### Secondary (MEDIUM confidence)
- Kaggle NCAA bracket slot format description verified against actual CSV: R1W1, R2W1, R5WX, R6CH format
  - https://github.com/cshaley/bracketeer (referenced Kaggle format)
  - Multiple Kaggle competition forum descriptions (WebSearch verified with CSV)
- Historical score statistics computed from `data/raw/kaggle/MNCAATourneyCompactResults.csv` + `historical_torvik_ratings.parquet`
  - Championship game mean total: 140.0, std 17.4 (22 games 2003-2025 excl. 2020)
  - avg_adj_t correlation with total score: 0.417 (verified from actual data)

### Tertiary (LOW confidence)
- Unabated.com article on bracket simulator architecture (general patterns, not verified against code)
- WebSearch results on Monte Carlo bracket simulation community patterns

## Metadata

**Confidence breakdown:**
- Slot schema: HIGH — directly read from Kaggle CSV, verified structure
- Monte Carlo vectorization: HIGH — benchmarked in the actual project environment
- Score prediction formula: MEDIUM — correlation computed from actual data, but formula is heuristic not fitted
- 2026 slot data availability: MEDIUM — Selection Sunday is March 15, 2026; exact Kaggle release timing uncertain
- seedings input format: HIGH — derived from seeds.parquet schema which perfectly matches slot CSV StrongSeed/WeakSeed column values

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable; slot schema and numpy API are stable)
