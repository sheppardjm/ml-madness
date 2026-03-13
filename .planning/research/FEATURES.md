# Feature Landscape: Pool Optimizer, UI Enrichment, Model Retraining

**Domain:** NCAA bracket pool strategy optimizer + matchup context UI + model update
**Researched:** 2026-03-13
**Milestone:** Subsequent — adds pool strategy, richer matchup display, and 2026 model retraining
**Overall confidence:** HIGH (pool optimizer domain), MEDIUM (scoring system variety), HIGH (retraining workflow)

---

## Research Methodology Note

The existing codebase was read directly (simulate.py, ensemble.py, features.py, cbbdata_client.py, app.py, advancement_table.py). Pool optimizer mechanics were researched via PoolGenius official docs (WebFetch), a Syracuse University analytics professor interview (WebFetch), WebSearch with current-year queries, and multiple verified secondary sources. Retraining workflow was cross-referenced against existing ensemble.py and cbbdata_client.py code patterns to ground claims in the actual codebase.

---

## Existing Foundation (What Is Already Built)

The following are already in production and are **dependencies** for new features — not things to rebuild:

- `simulate_bracket(mode="monte_carlo")` producing per-team advancement probabilities for all 7 rounds
- `TwoTierEnsemble` with XGBoost + LightGBM + Logistic Regression (Brier=0.1692, temporal walk-forward CV)
- `build_stats_lookup()` with Torvik adjOE, adjDE, barthag, adjT, wab, seed_num
- `cbbdata_client.py` with `ingest_current_season_stats()` fallback to archive endpoint
- Interactive bracket SVG with override picks and downstream cascade
- Advancement probability table with Streamlit ProgressColumn rendering

---

## Feature Area 1: Pool Strategy Optimizer

### How Pool Optimizers Work (Verified)

The mathematical framework, confirmed by PoolGenius documentation and academic sources:

**Core signal:** For any team in any round, compare:
- `win_prob`: model's probability of that team reaching that round (already produced by MC simulation)
- `pick_pct`: fraction of pool opponents who will pick that team to reach that round

**Value signal:** `value = win_prob - pick_pct`

- Positive value = team is under-picked relative to their actual odds (leverage opportunity)
- Negative value = team is over-picked (picking them hurts relative to field)
- For the champion slot specifically, this signal dominates pool outcomes

**Pool size modifies risk tolerance:**
- Small pool (< 20 entrants): chalk strategy is viable; uniqueness penalty is low
- Medium pool (20–100 entrants): champion differentiation becomes necessary
- Large pool (100+ entrants): must find contrarian champion AND at least one Final Four differentiator; pure chalk cannot win

The user's primary context is 100+ entrant pools. The optimizer must reflect this.

---

### Table Stakes — Pool Optimizer

Features this optimizer must have to be minimally useful.

| Feature | Why Expected | Complexity | Confidence | Dependencies |
|---------|--------------|------------|------------|--------------|
| Value score per team per round | Core of all contrarian analysis: `value = win_prob - pick_pct`. Without this there is no optimizer, only a prediction tool | Med | HIGH | MC advancement probs (already built); requires pick_pct input |
| Pick percentage input (manual entry) | Pool opponents' pick rates are not publicly available for private pools; user must enter them, or use ESPN/Yahoo public data as proxy | Low | HIGH | None beyond UI |
| Champion pick recommendation | Champion is the single highest-leverage pick in any pool; the optimizer must identify the highest-value champion choice | Low | HIGH | MC champion probs + pick_pct |
| Pool size input | Optimal risk tolerance changes dramatically between 10-person and 500-person pools; must be user-settable | Low | HIGH | None |
| Contrarian vs chalk mode toggle | In small pools, chalk is correct; the tool must support both strategies | Low | MEDIUM | Pool size input |
| Value table sorted by leverage | Show all 68 teams ranked by value score per round; the Sweet 16/Elite 8/Final Four columns are most relevant | Med | HIGH | MC advancement probs + pick_pct |

### Differentiators — Pool Optimizer

| Feature | Value Proposition | Complexity | Confidence | Dependencies |
|---------|-------------------|------------|------------|--------------|
| Scoring system customization | Most pools use standard scoring (R1=1pt, R2=2, S16=4, E8=8, FF=16, Ch=32) but many use weighted/upset-bonus variants. Optimal picks change based on scoring | Med | HIGH | Requires user to input scoring weights; changes value calculation |
| ESPN/Yahoo public pick scraping or paste | The public pick % for every team by round is publicly available on ESPN Tournament Challenge and Yahoo. Scraping or paste-import eliminates manual entry of 68 × 7 values | High | MEDIUM | Web scraping fragile; paste-from-table is more reliable |
| Expected score calculator | Given user's current bracket picks and a simulated field of opponents, compute expected point differential vs. field | High | MEDIUM | MC simulation + pick_pct + scoring system |
| Round-specific value highlight | Identify the two or three highest-leverage picks across all rounds in one summary; avoids overwhelming the user with 476 value cells | Low | HIGH | Value table (above) |
| "Chalk risk" warning | Warn when user's bracket is too correlated with public picks; flag overall uniqueness score | Med | MEDIUM | Pick_pct comparison across all picks |

### Anti-Features — Pool Optimizer

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Automated pick percentage fetching via scraping | ESPN/Yahoo HTML structure changes yearly; maintenance burden is high for marginal gain | Accept manual entry or paste-from-table; document the ESPN/Yahoo pick % URL for each platform |
| Generating a full "optimal bracket" automatically | Produces a bracket the user does not understand and will not trust; also the interdependence problem — picks are not independent (champion choice constrains Final Four choices) | Show value signals per pick point; let user make decisions |
| Optimizer for Calcutta / auction pools | Entirely different EV calculation; out of scope | Scope strictly to standard bracket format pools |
| Monte Carlo over the population of opponent brackets | Simulating a distribution of opponent brackets requires knowing the full opponent distribution; intractable without real data | Use a simplified expected-opponent model: each opponent picks independently with probability equal to pick_pct |
| Perfect-bracket optimization | Chasing the perfect bracket is not EV-maximizing; it maximizes peak outcome at the cost of average outcome | Optimize expected points, not perfect-bracket probability |

---

## Feature Area 2: UI Matchup Context / Stats Enrichment

### What Sophisticated Bracket Tools Show (Verified)

Based on barttorvik.com team sheets, KenPom matchup pages, and domain research:

The minimum matchup context users expect to see when hovering or clicking a game in the bracket is:
- Both teams' seeds and efficiency ratings side-by-side
- Win probability for each team
- One or two "reason this team wins/loses" indicators (offensive efficiency delta, defense delta)

More sophisticated tools (KenPom, Torvik) add:
- Four-factor comparison: eFG%, TO%, OR%, FTR for both offense and defense
- Tempo-adjusted context: whether the game pace favors a particular team
- Historical tournament performance for each team
- Color coding: green for advantage, red for disadvantage (KenPom uses this explicitly)

The existing app already has `build_stats_lookup()` returning adjOE, adjDE, barthag, adjT, wab per team. This is the data foundation.

---

### Table Stakes — UI Matchup Context

Features users expect when they click or hover a game in the bracket.

| Feature | Why Expected | Complexity | Confidence | Dependencies |
|---------|--------------|------------|------------|--------------|
| Side-by-side stat comparison for both teams in a matchup | Any serious bracket tool shows this; the data is already loaded in `stats_lookup` | Med | HIGH | `build_stats_lookup()` already returns adjOE, adjDE, barthag, adjT, wab |
| Win probability displayed as a number (not just bracket position) | Model probability is the key output; burying it in the SVG bracket only is insufficient | Low | HIGH | Win probability already computed per slot |
| Seed + team name clearly visible in matchup display | Basic orientation; users need to know who is playing | Low | HIGH | Already present in bracket SVG |
| Efficiency differential annotation | Show `adjOE_diff` and `adjDE_diff` so user can see why the model favors one team | Low | HIGH | Features already in `build_stats_lookup()` |
| Clickable/hoverable matchup panel | Static display forces users to mentally trace feature values; interactive panel prevents context switching | Med | MEDIUM | Streamlit supports expanders, popover, and sidebar patterns |

### Differentiators — UI Matchup Context

| Feature | Value Proposition | Complexity | Confidence | Dependencies |
|---------|-------------------|------------|------------|--------------|
| Color-coded stat comparison (green=advantage, red=disadvantage) | KenPom uses this; it lets users instantly identify mismatches without reading numbers | Med | HIGH | Side-by-side table (above) |
| Historical tournament record for each team | NCAA tournament success is seeded into user intuitions; showing "Duke: 9 Elite 8s" adds context models can't provide | Med | MEDIUM | Requires ingesting historical tournament results by team (already available in `tournament_games.parquet`) |
| Barthag displayed as "projected win % vs. average team" | barthag is interpretable as a win probability against an average D1 team on a neutral court; showing it this way instead of raw decimal makes it readable | Low | HIGH | `barthag` already in stats_lookup |
| Model feature importance callout | Show which of the 6 FEATURE_COLS drove the win probability for this specific matchup (e.g., "Duke wins primarily because of defensive efficiency advantage") | High | MEDIUM | Would require SHAP values per matchup — adds dependency |
| Advancement probability sparkline per team | Show a small row: "R64: 78%, R32: 52%, S16: 28%..." next to each team in the matchup panel | Med | HIGH | MC advancement probs already built in `advancement_probs` output |

### Anti-Features — UI Matchup Context

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| KenPom raw number display without explanation | adjOE of 118.3 is meaningless to most users; raw numbers without context reduce trust | Show differentials with direction labels ("Duke offense +4.2 pts/100 over opponent") |
| More than 6–8 stats in the matchup panel | Cognitive overload; users stop reading after 4–5 metrics | Pick the 4 most predictive: barthag differential, adjOE diff, adjDE diff, wab diff |
| Live stat update during tournament | Pulling live game stats during games is a different product | Matchup context is pre-game only; computed once from Selection Sunday snapshot |
| Recruiting rankings or player bios | Out of scope; adds no bracket prediction value | Keep display to team-level efficiency metrics only |
| Interactive visualization rebuilt from scratch | SVG bracket is already working; adding a matchup panel is an augmentation, not a rebuild | Augment with Streamlit expander/popover or a right-panel component |

---

## Feature Area 3: Model Retraining with 2025-26 Season Data

### Expected Retraining Workflow (Grounded in Existing Codebase)

The existing retraining workflow is fully defined in `ensemble.py` and `features.py`. The retraining process for a new season follows this pattern:

**Step 1: Data availability trigger**
cbbdata updates every 15 minutes during the season. The year-end ratings endpoint (`/torvik/ratings?year=2026`) will have complete data with `barthag` populated once the season ends (early March 2026). `cbbdata_client.py` already handles the fallback to the archive endpoint when year-end ratings are incomplete (as was the case for year=2025 per the code comments).

**Step 2: Ingest 2025-26 season stats**
`ingest_current_season_stats(api_key, year=2026)` already exists and produces `current_season_stats.parquet`. This is the only new ingestion step needed.

**Step 3: Tournament results ingestion (post-tournament)**
After the 2026 tournament, `tournament_games.parquet` and `seeds.parquet` must be updated with 2026 results. These come from the Kaggle MarchMadnessMen dataset (updated annually after the tournament).

**Step 4: Re-run `build_matchup_dataset()`**
This automatically incorporates 2025-26 data via `current_season_stats.parquet` overlay logic already in `build_stats_lookup()`. No code changes needed.

**Step 5: Retrain ensemble**
Run `python -m src.models.ensemble` (already defined as `__main__`). This re-runs OOF temporal stacking, fits meta-learner, and saves `models/ensemble.joblib`. The `BACKTEST_YEARS` list in `temporal_cv.py` must be extended to include 2026.

**Step 6: Evaluate and compare**
Compare new OOF Brier score against the current 0.1692 baseline. If regression, investigate.

---

### Table Stakes — Model Retraining

Features required for retraining to be safe and trustworthy.

| Feature | Why Expected | Complexity | Confidence | Dependencies |
|---------|--------------|------------|------------|--------------|
| `BACKTEST_YEARS` updated to include 2026 | Without 2026 in the holdout set, the model is validated only through 2025; a model claiming to predict 2026 that wasn't backtested on 2026 is misleading | Low | HIGH | `temporal_cv.py`: add 2026 to `BACKTEST_YEARS` |
| Data availability gate before retraining | Do not retrain until both current_season_stats AND tournament results exist for 2026; premature retraining produces a model without ground truth for 2026 | Low | HIGH | `ingest_current_season_stats()` already exists; add a check before running `build_matchup_dataset()` |
| Pre/post Brier score comparison logged | The artifact already stores `oof_brier`; retraining should compare new vs. previous to confirm no regression | Low | HIGH | `ensemble.py` already logs this; just needs human review |
| Selection Sunday snapshot cutoff respected | `as_of_date` validation already exists in `compute_features()`; ensure the 2026 retraining uses stats as of 2026 Selection Sunday, not end-of-tournament | Low | HIGH | `SELECTION_SUNDAY_DATES` dict in `cutoff_dates.py` needs 2026 date added |
| Walk-forward property preserved | Training data for 2026 holdout must include only seasons through 2025; the existing `walk_forward_splits()` guarantees this | Low | HIGH | Already enforced by leakage guard in `temporal_cv.py` |

### Differentiators — Model Retraining

| Feature | Value Proposition | Complexity | Confidence | Dependencies |
|---------|-------------------|------------|------------|--------------|
| Feature importance drift check | After retraining, compare which of the 6 FEATURE_COLS have changed weight most; if `seed_diff` weight collapses or `barthag_diff` flips sign, something is wrong | Med | MEDIUM | `vif_analysis.py` already exists; add a post-train feature importance delta report |
| Calibration curve comparison (before/after) | `plot_calibration()` already exists in `ensemble.py`; running it for the old vs. new model quantifies whether calibration improved or degraded | Low | HIGH | Trivially extends existing `plot_calibration()` |
| Hyperparameter re-tuning flag | XGBoost and LightGBM params were tuned on the 2022–2025 data distribution; with 2026 added, re-tuning may improve performance; this is optional but noted | High | MEDIUM | `train_xgboost.py`, `train_lightgbm.py` already exist; re-running them is the re-tune path |
| Per-year Brier breakdown for 2026 | The artifact stores `oof_brier_per_year`; the 2026 holdout Brier should be compared to the 2022–2025 range to detect if 2026 is an outlier year (similar to how 2025 was very chalk-heavy) | Low | HIGH | Already stored in artifact; just needs display |
| `current_season_stats.parquet` freshness check | The cbbdata archive endpoint returns a `source_date` column; log this date in the artifact to make the data lineage explicit | Low | MEDIUM | `ingest_current_season_stats()` could write source_date to parquet |

### Anti-Features — Model Retraining

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Incremental/online learning (updating only on 2026 data) | The dataset is small (≈248 OOF samples across 4 years); incremental updates on a small dataset can degrade calibration; the full retrain takes seconds | Full retrain from scratch on all seasons |
| Retraining before 2026 Selection Sunday | cbbdata year-end ratings for 2026 are not final until after the regular season ends; premature ingestion produces stale stats for tournament teams | Gate retraining to post-Selection-Sunday |
| Changing model architecture during retraining | Adding new base models or changing ensemble structure while also updating data conflates two changes; impossible to attribute Brier improvement or regression | Separate data update (retraining) from architecture changes (new features or models) |
| Retraining on post-tournament stats | Tournament games happen after Selection Sunday; stats must be frozen at the Selection Sunday snapshot to match prediction-time data, not end-of-tournament data | Enforce `as_of_date` cutoff; `cbbdata_client.py` already does this via archive snapshot |
| Automated retraining pipeline / CI | This is a personal tool used once per year; automated retraining infrastructure would cost more engineering time than it saves | Manual one-command retrain; document the exact command |

---

## Feature Dependencies (All Three Areas)

```
Existing: MC advancement_probs (per team per round, 10K runs)
  → Pool optimizer value table (win_prob - pick_pct per team per round)
    → Champion value recommendation (highest-value champion pick)
    → Round-specific value highlights (top-3 leverage plays)
    → Expected score calculator (optional, higher complexity)

Existing: build_stats_lookup() [adjOE, adjDE, barthag, adjT, wab]
  → Side-by-side stat comparison panel (matchup context)
    → Color-coded advantage display
    → Advancement probability sparkline per team (from MC probs)
    → Historical tournament record (from tournament_games.parquet)

Existing: cbbdata_client.ingest_current_season_stats() + tournament_games.parquet
  → 2026 season data in current_season_stats.parquet
    → build_matchup_dataset() incorporates 2026 via overlay
      → Updated walk-forward splits (BACKTEST_YEARS += [2026])
        → Full ensemble retrain (build_ensemble())
          → New ensemble.joblib artifact
            → All UI features use retrained model automatically
```

### Critical Dependency Notes

- **Pool optimizer requires win_prob AND pick_pct.** The MC simulation already produces win_prob. The missing ingredient is pick_pct, which must come from user input (manual entry or paste from ESPN/Yahoo). The feature cannot work without this user input.
- **Matchup context panel requires no new data.** All stats needed are already in `stats_lookup`. The work is UI-only.
- **Model retraining cannot happen until after Selection Sunday 2026.** The bracket must be set (seedings known) and cbbdata must have indexed 2025-26 season-end Torvik ratings. The cbbdata client already handles the archive fallback for incomplete year-end data.
- **Adding 2026 to BACKTEST_YEARS changes the OOF sample count.** The meta-learner is trained on OOF predictions; adding 2026's ~63 games increases sample size. Expect Brier to be more stable post-retrain.
- **Scoring system input is a blocker for pool optimizer EV calculation.** Without knowing the pool's scoring weights, the optimizer can only show raw `win_prob - pick_pct` differentials, not point-adjusted EV. Document this limitation and default to standard scoring (1-2-4-8-16-32).

---

## MVP Recommendation Per Feature Area

### Pool Optimizer MVP (minimum useful version)

1. Pick percentage input: text fields or table for user to enter ESPN/Yahoo pick_pct for champion and Final Four candidates (the highest-leverage rounds)
2. Value score table: show `win_prob - pick_pct` for all 68 teams in Final Four, Championship, Champion columns
3. Champion recommendation callout: highlight the top-2 value champion candidates with a plain-language explanation
4. Pool size dropdown (small / medium / large) that adjusts the recommendation threshold

Defer to post-MVP:
- Full per-round value for all 7 rounds (add after champion/FF proven useful)
- Scoring system customization (default to standard; add custom weights later)
- Expected score calculator (requires simulating opponent field; higher complexity)

### Matchup Context MVP (minimum useful version)

1. Clickable matchup panel in the bracket: clicking a game slot opens an expander showing both teams' key stats side-by-side
2. Stats shown: seed, team name, win_prob, barthag (as % vs. average D1 team), adjOE rank, adjDE rank, wab
3. Direction indicator: which team has the advantage in each metric (+/-  with simple color)

Defer to post-MVP:
- Full four-factor comparison (eFG%, TO%, OR%, FTR) — requires additional data ingestion
- Historical tournament record — useful but adds data complexity
- SHAP feature importance per matchup — adds ML dependency

### Model Retraining MVP (minimum reliable version)

1. Add 2026 to `SELECTION_SUNDAY_DATES` in `cutoff_dates.py` (2026-03-15 is Selection Sunday)
2. Run `ingest_current_season_stats(api_key, year=2026)` once cbbdata indexes 2025-26 season-end ratings
3. Add 2026 to `BACKTEST_YEARS` in `temporal_cv.py`
4. Run `python -m src.models.ensemble` and compare new OOF Brier against 0.1692
5. After 2026 tournament, ingest 2026 tournament results into `tournament_games.parquet` and `seeds.parquet`

Defer to post-retrain:
- Hyperparameter re-tuning (re-run only if Brier regresses)
- Feature importance drift analysis (informative but not blocking)

---

## Complexity Summary

| Feature | Complexity | Blocker / Dependency |
|---------|------------|---------------------|
| Pick percentage input (manual) | Low | None |
| Value score table | Low-Med | MC probs (done) + pick_pct input |
| Champion value recommendation | Low | Value score table |
| Scoring system customization | Med | Scoring rules input |
| Expected score calculator | High | Simulated opponent field |
| Side-by-side stat panel | Med | stats_lookup (done) |
| Color-coded advantage display | Low | Stat panel |
| Advancement sparkline | Low | MC probs (done) |
| Historical tournament record | Med | tournament_games.parquet parse by team |
| SHAP feature importance | High | shap library, per-matchup inference |
| BACKTEST_YEARS + Selection Sunday date update | Low | cbbdata 2026 indexing |
| Ingest 2026 season stats | Low | cbbdata availability |
| Full ensemble retrain | Low | 2026 stats + 2026 tournament results |
| Hyperparameter re-tuning | High | Retrain complete, Brier regression seen |

---

## Sources

- [PoolGenius Bracket Picks FAQ](https://poolgenius.teamrankings.com/ncaa-bracket-picks/faq/) — MEDIUM confidence (WebFetch verified; methodology described but not fully quantified)
- [PoolGenius Risk-Value Framework](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/balancing-risk-and-value-in-your-bracket/) — MEDIUM confidence (WebFetch verified; core `win_prob - pick_pct` framework confirmed)
- [Syracuse University Analytics Professor on Pool Strategy](https://news.syr.edu/2026/03/11/how-to-win-your-march-madness-bracket-with-analytics-driven-strategies/) — HIGH confidence (WebFetch verified; pool size thresholds confirmed by academic source)
- [Establish The Run 2025 Bracket Pool Strategy](https://establishtherun.com/march-madness-bracket-pool-strategy-2/) — MEDIUM confidence (page content partially available; ownership % framework confirmed via search summary)
- [FTN Fantasy Advanced Bracket Strategies](https://ftnfantasy.com/cbb/advanced-bracket-strategies-how-to-win-any-size-tournament-pool) — LOW confidence (403 on WebFetch; findings corroborated by other sources)
- [cbbdata Package Documentation](https://cbbdata.aweatherman.com/) — HIGH confidence (WebFetch verified; 15-minute update frequency confirmed)
- [Barttorvik T-Rank](https://barttorvik.com/trank.php) — HIGH confidence (primary source; adjOE/adjDE/barthag/adjT/wab confirmed as current metrics)
- [PoolGenius 2026 Bracket Strategy Guide](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/bracket-strategy-guide/) — MEDIUM confidence (WebFetch verified)
- [VSiN 2025 March Madness Winning Strategies](https://vsin.com/college-basketball/march-madness-2025-winning-strategies-for-brackets-survivor-pools-and-calcuttas/) — MEDIUM confidence (WebSearch verified)
- [TeamRankings Scoring Systems Article](https://www.teamrankings.com/blog/ncaa-tournament/bracket-pool-scoring) — MEDIUM confidence (WebSearch verified; 500+ unique scoring systems confirmed)
- Existing codebase: `src/models/ensemble.py`, `src/models/features.py`, `src/models/temporal_cv.py`, `src/ingest/cbbdata_client.py`, `src/simulator/simulate.py`, `src/ui/advancement_table.py`, `app.py` — HIGH confidence (direct code read)
