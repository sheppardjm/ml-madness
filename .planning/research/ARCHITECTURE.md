# Architecture Patterns

**Domain:** NCAA Men's Basketball Bracket Prediction Engine
**Researched:** 2026-03-02
**Confidence:** MEDIUM-HIGH (verified against multiple open-source projects and academic papers)

---

## Recommended Architecture

A bracket predictor has five distinct layers. Each is independently testable and replaceable. The layers have a strict dependency direction: data flows forward only (left to right below), with the backtesting harness as a side-channel that replays the forward pipeline against historical tournament snapshots.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NCAA Bracket Predictor                            │
│                                                                             │
│  ┌───────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐           │
│  │   DATA    │───▶│  FEATURE   │───▶│  MODEL   │───▶│  BRACKET │           │
│  │ PIPELINE  │    │   STORE    │    │  LAYER   │    │ SIMULATOR│           │
│  └───────────┘    └────────────┘    └──────────┘    └──────────┘           │
│        │                                 ▲                 │               │
│        │         ┌───────────────────────┘                 │               │
│        │         │     (trained models)                    ▼               │
│        │    ┌────┴─────┐                            ┌──────────────┐       │
│        └───▶│BACKTEST  │                            │     WEB      │       │
│             │ HARNESS  │                            │      UI      │       │
│             └──────────┘                            └──────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-----------|---------------|--------|---------|-------------------|
| Data Pipeline | Fetch, clean, and persist raw game/team data | Public APIs, CSV files, scraped sources | Normalized game records (SQLite/Parquet) | Feature Store |
| Feature Store | Compute and cache derived metrics from raw records | Normalized game records | Feature vectors per team-season | Model Layer, Backtest Harness |
| Model Layer | Train, evaluate, and serve ensemble of game-level win-probability models | Feature vectors for two teams | Win probability P(team_a beats team_b) | Bracket Simulator, Backtest Harness |
| Bracket Simulator | Fill all 67 tournament games using win probabilities, propagating winners round-by-round | Current bracket seedings + model win probabilities | Completed bracket JSON | Web UI |
| Backtest Harness | Replay the Feature Store → Model → Simulator pipeline using historical tournament snapshots; compare predicted brackets to actual results | Historical snapshots, trained models | Accuracy metrics, Brier scores, bracket scores | Model Layer |
| Web UI | Display filled bracket, show per-game probabilities, allow manual overrides | Bracket JSON from Simulator | Rendered interactive bracket; override signals back to Simulator | Bracket Simulator |

---

## Data Flow: Raw Stats to Final Bracket

### Step 1: Ingest

```
External sources:
  - sports-reference.com / sportsreference Python package  → historical game logs
  - kenpompy (KenPom scraper, subscription required)       → efficiency ratings
  - barttorvik.com (T-Rank, free scraping)                 → adjusted stats
  - NCAA bracket API (automated fetch on Selection Sunday) → current bracket seedings

Stored as:
  - SQLite (simple, local, zero-infra) or Parquet files
  - Separate tables: games, teams, ratings, tournament_slots
```

### Step 2: Feature Engineering

Raw stats are not fed to models directly. The Feature Store computes derived metrics per team-season:

```
Per-team metrics (examples from validated research):
  - Adjusted Offensive Efficiency (ADJOE)
  - Adjusted Defensive Efficiency (ADJDE)
  - Effective FG%, Turnover Rate, Rebound Rate, Free Throw Rate
  - Elo rating (updated after every game, season-rolling)
  - Strength of schedule
  - Recent form (rolling 5-game window)
  - Seed and seed difference

Per-matchup feature vector (for model input):
  - team_a_metric - team_b_metric for every metric above
  - seed_diff
  - elo_diff
  - "Perspective flipping": store each game twice with labels swapped
    so the model is symmetric (important for calibration)
```

Feature importance from empirical research: Offensive Efficiency Difference is the single strongest predictor (~23% importance in Random Forest implementations). Seed difference is a strong secondary signal.

### Step 3: Model Training

```
Input:  Feature vector (difference metrics for team_a vs team_b)
Output: P(team_a wins) ∈ [0, 1]

Model ensemble (train all, compare on held-out tournament years):
  - Logistic Regression         (baseline, highly interpretable)
  - Random Forest               (strong empirical performer for this domain)
  - Gradient Boosting / XGBoost (typically best on tabular data)
  - LSTM / Transformer          (if sequential game-by-game features are used)

Training split:
  - Train on regular season + past tournament games, years T-1 through T-N
  - Hold out the most recent tournament year(s) for validation
  - Critical: do NOT use data from after the tournament start date in features
    (data leakage — rolling stats must be computed as of tip-off day)

Calibration:
  - Models must output calibrated probabilities, not just class labels
  - Use Brier Score and log-loss as primary metrics (not accuracy alone)
  - Platt scaling or isotonic regression for post-hoc calibration if needed

Persistence:
  - Save trained models with joblib/pickle per model type per season
  - Store metadata: training date, feature list, validation metrics
```

### Step 4: Bracket Simulation

The bracket is a single-elimination tournament with 64 (or 68 with play-in) teams. Simulation fills it deterministically or probabilistically.

```
Two modes:

MODE A — Deterministic (recommended for primary output):
  - For each matchup, pick the team with P(win) > 0.5
  - Produces one definitive bracket
  - Fast, reproducible

MODE B — Monte Carlo (recommended for confidence intervals):
  - For each matchup, draw Bernoulli(P(win)) to pick winner
  - Repeat N=10,000 times
  - Output: for each slot, the % of simulations each team won
  - Use to show "confidence" in each pick and to identify high-variance slots

Algorithm (rounds 1 through 6, 63 games + 4 play-in games):

  function simulate_bracket(seedings, predict_fn):
    active_teams = initialize_from_seedings(seedings)
    results = {}

    for round in [play_in, round_of_64, ..., championship]:
      matchups = get_matchups_for_round(round, active_teams)
      for matchup in matchups:
        p = predict_fn(matchup.team_a, matchup.team_b)
        winner = pick_winner(p)  # deterministic or stochastic
        results[matchup.slot] = winner
        active_teams.advance(winner)

    return results

Key invariant: the winner of slot X always becomes one of the teams
in the matchup for slot Y (the parent slot). Slot addressing must be
correct or brackets silently produce impossible results.
```

### Step 5: Backtesting

Backtesting answers: "How well would this model have done in past tournaments?"

```
For each historical tournament year Y:
  1. Reconstruct the feature store using only data available before Y's tournament
     (enforce the cutoff date strictly — no future data)
  2. Load the current tournament's actual bracket structure (seedings)
  3. Run the bracket simulator using the model trained on data < Y
  4. Compare predicted bracket to actual bracket

Metrics:
  - Round-by-round accuracy (% of games correct per round)
  - ESPN-style bracket scoring (10/20/40/80/160/320 points per round)
  - Brier Score per game (calibration quality)
  - Upset detection rate (did the model catch notable upsets?)
  - Spearman rank correlation of predicted finish vs actual finish

Output: A multi-year comparison table (one row per year, one column per model)
This is how you select which model(s) to use in the ensemble.
```

### Step 6: Web UI

```
Rendering:
  - React frontend with a bracket visualization library
    (react-tournament-brackets by G-Loot is the most actively maintained;
     supports both single and double elimination)
  - Each matchup cell shows: team names, seed, win probability, picked winner

Override mechanism:
  - Each matchup has an "override" toggle
  - When user clicks a different team than the model picked, the UI:
    a. Records the override in local state
    b. Re-runs the downstream bracket simulation from that round forward
       (all subsequent rounds must be re-derived, because who plays next
        depends on who won each game)
  - This is the critical complexity: overrides cascade forward

Data contract (bracket JSON):
  {
    "rounds": [
      {
        "round_name": "Round of 64",
        "matchups": [
          {
            "slot_id": "R1_W1",
            "team_a": { "name": "...", "seed": 1 },
            "team_b": { "name": "...", "seed": 16 },
            "p_a_wins": 0.94,
            "model_pick": "team_a",
            "user_override": null,
            "effective_pick": "team_a"
          }
        ]
      }
    ]
  }

Backend API (FastAPI, local):
  GET  /bracket/current       → returns current bracket seedings
  POST /bracket/simulate      → runs simulator, returns filled bracket JSON
  POST /bracket/override      → accepts {slot_id, picked_team}, returns
                                 re-simulated downstream bracket JSON
  GET  /models/compare        → returns backtesting summary table
  GET  /models/{id}/metrics   → returns metrics for a specific model
```

---

## Build Order

Dependencies determine build order. Build what is depended upon first.

```
Phase 1: Data Pipeline
  - Must come first. Everything else is blocked without data.
  - Deliverable: SQLite database populated with historical games + ratings
  - Unblocks: Feature Store, Backtest Harness

Phase 2: Feature Store
  - Depends on: Data Pipeline
  - Deliverable: compute_features(team, season) function with tests
  - Unblocks: Model Layer, Backtest Harness

Phase 3: Model Layer (baseline)
  - Depends on: Feature Store
  - Start with Logistic Regression — it gives you a calibrated baseline fast
  - Deliverable: trained model, saved to disk, prediction API function
  - Unblocks: Bracket Simulator, Backtest Harness

Phase 4: Bracket Simulator
  - Depends on: Model Layer (any model, even baseline)
  - Deliverable: simulate_bracket() function, tested on historical brackets
  - Unblocks: Web UI

Phase 5: Backtesting Harness
  - Depends on: Feature Store, Model Layer, Bracket Simulator
  - Deliverable: backtest(year_range, models) → comparison table
  - Unblocks: Model comparison, ensemble selection

Phase 6: Ensemble / Advanced Models
  - Depends on: Backtest Harness (need metrics to guide model selection)
  - Deliverable: additional model types, ensemble weighting, calibration tuning
  - Informed by backtest results

Phase 7: Web UI
  - Depends on: Bracket Simulator (for data contract), FastAPI backend
  - Can be developed in parallel with Phase 5-6 once bracket JSON shape is stable
  - Deliverable: interactive bracket with override support
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Data Leakage in Backtesting

**What:** Using rating data computed from games played during or after the tournament when training/evaluating.
**Why bad:** Produces artificially inflated accuracy. The model appears to work but fails in production.
**Instead:** Enforce a hard cutoff date. For each backtest year, filter ALL data sources to `game_date < tournament_start_date[year]`. This includes ratings (KenPom, T-Rank), which are updated daily — use snapshots or reconstruct from raw game data.

### Anti-Pattern 2: Accuracy as Primary Metric

**What:** Optimizing and comparing models solely on "% games predicted correctly."
**Why bad:** A model that always picks the favorite will hit ~70% accuracy but produces terrible brackets and is not calibrated. You need calibrated probabilities (Brier Score) for realistic simulation.
**Instead:** Use Brier Score and log-loss as primary metrics. Report accuracy as secondary context.

### Anti-Pattern 3: Flat Bracket Representation

**What:** Storing bracket as a flat list of team names without slot addressing.
**Why bad:** When a user overrides a pick, you cannot determine which teams advance to which downstream slots. The bracket becomes corrupted.
**Instead:** Use a slot-based addressing scheme (e.g., `R1_W01`, `R2_W01`, where the round + region + position uniquely identifies each slot) and a parent-child relationship between slots.

### Anti-Pattern 4: One Model, One Bracket

**What:** Building around a single model architecture without comparison infrastructure.
**Why bad:** You cannot know which model is best without comparison. The best-performing model varies by tournament year.
**Instead:** Build model comparison into the pipeline from day one (Phase 3). The backtesting harness should output a table comparing all models.

### Anti-Pattern 5: Ignoring Round-Specific Calibration

**What:** Applying one model to all rounds equally.
**Why bad:** Round 1 upsets (12 over 5, 11 over 6) have historically different dynamics than Elite 8 games. Seed difference matters less in later rounds.
**Instead:** At minimum, analyze model performance by round during backtesting. Optionally train separate models per round or add round number as a feature.

### Anti-Pattern 6: Scraping Without Rate Limiting

**What:** Hitting sports-reference, KenPom, or BartTorvik aggressively during data ingestion.
**Why bad:** These sites block scrapers and ban IPs. KenPom requires a paid subscription.
**Instead:** Cache all scraped data locally on first fetch. Add delays (2-3 seconds) between requests. Store raw HTML alongside parsed data for re-parsing without re-fetching. Consider Kaggle historical datasets for bootstrap, with current-season scraping as incremental top-up.

---

## How the Override Feature Works Architecturally

Override is the hardest UI feature because it has cascading effects.

```
Without override:
  Round 1 picks → Round 2 matchups → Round 2 picks → ... → Champion

With override at Round 1, Game 3:
  Round 1, Games 1-2: unchanged
  Round 1, Game 3: user picks team_b instead of model's team_a
  Round 1, Games 4-6: unchanged

  Round 2, Game 2 (which depended on Game 3): NOW CHANGES
    The matchup was (winner of G3) vs (winner of G4)
    With override: team_b vs (winner of G4) — different game entirely
    → Re-simulate this matchup with the new team
    → Re-simulate all downstream matchups in this bracket region

  The rest of the bracket (other regions) is unchanged.
```

Implementation approach (recommended): Store the override map `{slot_id: team_id}` and re-run `simulate_bracket()` from scratch each time an override is toggled, passing the override map as a second argument. The simulation function checks the override map before calling the model. This is simpler than trying to do surgical downstream propagation, and simulation is fast enough (milliseconds) that full re-simulation is not a performance problem.

---

## Scalability Considerations

This is a single-user local application. The considerations below are informational, not requirements.

| Concern | Single user (local) | Multi-user (if deployed) |
|---------|---------------------|--------------------------|
| Model serving | Load model from disk per request; fast | Preload model into memory in FastAPI startup |
| Data storage | SQLite is sufficient | Postgres for concurrent writes |
| Simulation | Synchronous, sub-second | Same; simulation is fast even at N=10,000 Monte Carlo runs |
| UI state | React local state or Zustand | Same; bracket state is user-specific |
| Scraping | Once per day, scheduled or manual | Same; external rate limits don't change |

---

## Sources

| Source | Confidence | URL |
|--------|-----------|-----|
| Marcu, J. — March Madness 2025 Prediction (Random Forest, AUC 0.753) | MEDIUM | https://jtmarcu.github.io/projects/march-madness.html |
| arxiv 2503.21790 — Mathematical Modeling NCAA Bracket (Logistic Regression + Monte Carlo) | HIGH | https://arxiv.org/html/2503.21790v1 |
| arxiv 2508.02725 — LSTM and Transformer for NCAA Forecasting | HIGH | https://arxiv.org/html/2508.02725v1 |
| pjmartinkus/College_Basketball — Five-stage pipeline, covariate shift analysis | MEDIUM | https://github.com/pjmartinkus/College_Basketball |
| g-loot/react-tournament-brackets — React bracket component | HIGH | https://github.com/g-loot/react-tournament-brackets |
| bracketology PyPI — Python bracket simulation library | MEDIUM | https://pypi.org/project/bracketology/ |
| kenpompy docs — KenPom Python scraper | HIGH | https://kenpompy.readthedocs.io/ |
| sportsreference/sportsipy — sports-reference Python API | HIGH | https://sportsreference.readthedocs.io/en/stable/ |
| Google Cloud Blog — NCAA data pipeline patterns | MEDIUM | https://cloud.google.com/blog/products/data-analytics/let-the-queries-begin-how-we-built-our-analytics-pipeline-for-ncaa-march-madness |
| FastAPI + Streamlit local ML deployment pattern | HIGH | https://testdriven.io/blog/fastapi-streamlit/ |
