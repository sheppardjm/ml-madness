# Project Research Summary

**Project:** madness2026 — NCAA Bracket Predictor v1.1
**Domain:** NCAA tournament bracket prediction + pool strategy optimization
**Researched:** 2026-03-13
**Milestone:** v1.1 — pool strategy optimizer, UI matchup enrichment, model retraining
**Confidence:** HIGH (stack verified against live venv; architecture derived from direct codebase audit of 12,400+ lines; pitfalls grounded in both code inspection and practitioner sources)

> **Note:** This file supersedes the 2026-03-02 v1.0 SUMMARY.md. The v1.0 summary's phase structure and findings remain valid for the foundational pipeline. This document covers only the v1.1 additions. For v1.0 context, see git history.

---

## Executive Summary

The v1.1 milestone adds three capabilities to an already-working bracket predictor: a pool strategy optimizer for large (100+) entrant pools, richer matchup context in the Streamlit UI, and a model retraining workflow for 2025-26 season data. The critical finding across all four research dimensions is that **no new dependencies are required** — the entire milestone can be delivered using the installed stack (numpy 2.4.2, Streamlit 1.55.0, DuckDB 1.4.4, joblib 1.5.3, Plotly 6.6.0). The data needed for all three features already exists in the processed Parquet files; the work is pure code addition on top of a validated foundation.

The most important architectural insight is that the three features are largely decoupled: the pool optimizer reads `mc_result["advancement_probs"]` already cached in the UI; matchup context reads `stats_lookup` already loaded in memory; model retraining is a CLI script that runs independently of the Streamlit app. This decoupling makes it possible to build and smoke-test each feature in isolation — which is essential given the Selection Sunday deadline of 2026-03-15 (2 days from research date) and tournament tip-off on 2026-03-19.

The dominant risk is not technical but temporal and conceptual. The pool optimizer is the highest-value feature and must not conflate win probability with expected pool score — this is a known conceptual failure mode documented across multiple practitioner sources. Under the deadline, UI enrichment (visually satisfying but lower priority) must be time-boxed to prevent consuming hours that belong to the optimizer. A hard go/no-go decision on cbbdata 2025-26 data availability must be made by EOD 2026-03-14 — the data is confirmed unavailable as of 2026-03-13, and the fallback (v1.0 model with 2024-25 proxy data, Brier 0.1692) is a fully valid deployment path. The v1.0-stable tag must be created before any v1.1 development begins.

---

## Key Findings

### Recommended Stack

No new dependencies required. Every capability needed for v1.1 is provided by already-installed packages. The relevant confirmed versions are Streamlit 1.55.0 (`st.dialog` and `st.popover` available), numpy 2.4.2 (vectorized EV math), DuckDB 1.4.4 (historical seed queries), joblib 1.5.3 (model artifact serialization), and Plotly 6.6.0 (efficiency metric charts). scipy 1.17.1 is installed as a transitive dependency but is not needed — the pool optimizer's EV-greedy tree traversal fits the bracket's sequential constraint structure better than continuous optimization solvers.

**Core technologies (existing — no changes to pyproject.toml):**

| Package | Version | Role in v1.1 |
|---------|---------|--------------|
| numpy | 2.4.2 | Pool optimizer EV calculation (`win_prob / pick_pct` vectorized across 68 teams x 7 rounds) |
| Streamlit | 1.55.0 | `st.dialog` for matchup detail panels; `st.popover` for inline hover context; new Pool Strategy tab |
| DuckDB | 1.4.4 | Historical seed win-rate queries (`tournament_games.parquet` joined against `seeds.parquet`) |
| joblib | 1.5.3 | Model artifact read/write during retraining |
| Plotly | 6.6.0 | Efficiency metric bar charts inside matchup panels |

**Only new artifact needed:** `scripts/retrain.py` (~50 lines) and an optional `pyproject.toml` entry point (`retrain = "scripts.retrain:main"`). No new `dependencies` entries.

### Expected Features

**Pool Strategy Optimizer — must have (table stakes):**
- Value score per team per round: `value = win_prob - pick_pct` for all 68 teams, surfaced for Final Four and Championship slots (highest-leverage rounds)
- Pick percentage input (manual): text fields for user to enter ESPN/Yahoo public pick percentages — no free structured API exists; manual entry is correct for MVP
- Champion recommendation callout: top-2 value champion candidates with plain-language explanation
- Pool size input: required user input, not a hardcoded constant; strategy is materially different below 50 entrants vs. above 100

**Pool Strategy Optimizer — should have (differentiators):**
- Scoring system configuration: round weights change optimal strategy; default standard ESPN (1-2-4-8-16-32) but expose as configurable input
- Round-specific value highlight: top 3 leverage plays across all rounds in one summary row
- Chalk risk warning: flag when user's picks correlate too strongly with public pick percentages

**Pool Strategy Optimizer — defer to post-MVP:**
- Automated ESPN/Yahoo pick percentage scraping (fragile; changes yearly; manual entry is more reliable for MVP)
- Auto-generated "optimal bracket" (users distrust what they can't inspect; show value signals and let user decide)
- Expected score calculator against simulated opponent field (requires MC over opponent distribution; materially higher complexity)

**UI Matchup Context — must have:**
- Side-by-side stat comparison for any bracket game: seed, team name, win probability, barthag (shown as "% chance vs. average D1 team"), adjOE rank, adjDE rank, wab
- Direction indicator per metric (advantage annotation with +/- and color)
- Clickable panel integrated with existing override expanders (additive — not a rebuild of the bracket SVG)

**UI Matchup Context — should have:**
- Advancement probability sparkline per team (MC probs already computed; low-cost addition)
- Color-coded advantage display (green/red per metric, KenPom pattern)
- Historical seed matchup win rate (DuckDB query against `tournament_games.parquet`)

**UI Matchup Context — defer:**
- SHAP feature importance per matchup (adds shap library dependency)
- Four-factor breakdown (eFG%, TO%, OR%, FTR) requiring additional data ingestion
- Live stat updates during tournament (different product category)

**Model Retraining — must have:**
- Add 2026-03-15 to `SELECTION_SUNDAY_DATES` in `cutoff_dates.py`
- Add 2026 to `BACKTEST_YEARS` in `temporal_cv.py` (one-line constant change)
- Parameterize current-season year in `build_stats_lookup()` (currently hard-coded to 2025)
- Data availability gate: do not retrain until cbbdata has 2025-26 barthag populated
- Pre/post Brier comparison before overwriting `models/selected.json`
- Artifact backup before any retrain (`ensemble_v1.0.joblib`)

**Model Retraining — defer:**
- Hyperparameter re-tuning (only if Brier regresses post-retrain)
- Feature importance drift analysis (informative, not blocking)
- Automated retraining pipeline/CI (once-per-year personal tool; 50-line script is sufficient)

### Architecture Approach

The v1.1 architecture is purely additive to the existing five-layer pipeline (Data Pipeline → Feature Store → Model Layer → Bracket Simulator → Web UI). Three new components slot in cleanly: `src/pool/optimizer.py` reads `mc_result["advancement_probs"]` already cached by the UI; `src/ui/matchup_context.py` reads `stats_lookup` already in memory and renders inside the existing override expanders; `scripts/retrain.py` orchestrates the existing ingest → features → train → compare flow via CLI, never inside Streamlit. The existing `predict_fn(team_a_id, team_b_id) -> float` interface must not be modified — every downstream component depends on this boundary.

**New components (5 new files):**

| Component | Path | Responsibility |
|-----------|------|---------------|
| Pool optimizer | `src/pool/optimizer.py` | Pure computation: `compute_pool_strategy(mc_result, field_size, scoring_system)` returns value table |
| Pool UI loader | `src/ui/pool_loader.py` | `@st.cache_data` wrapper; follows `data_loader.py` caching pattern |
| Matchup context builder | `src/ui/matchup_context.py` | `build_matchup_context(team_a_id, team_b_id, season, _stats_lookup)` |
| Seed history query | `src/ui/seed_history.py` | `@st.cache_data` DuckDB query for historical seed vs. seed win rates |
| Retrain script | `scripts/retrain.py` | CLI: ingest → build features → train → validate → swap artifact |

**Existing files requiring modification (4 files):**

| File | Change Required |
|------|----------------|
| `src/ui/data_loader.py` | Add `load_stats_lookup_cached(season)` — single call site for stats_lookup across all UI features |
| `src/ui/override_controls.py` | Add `st.expander("Team stats")` inside existing slot expanders (additive only) |
| `src/models/features.py` | Parameterize current-season year in `build_stats_lookup()` (remove hard-coded 2025) |
| `src/models/temporal_cv.py` | Update `BACKTEST_YEARS` constant to include 2026 |

**Caching rules to follow** (per existing conventions in `data_loader.py`):
- `load_stats_lookup_cached(season)`: `@st.cache_data` — large dict but serializable; season is the cache key
- `build_matchup_context(team_a_id, team_b_id, season, _stats_lookup)`: underscore prefix on `_stats_lookup` to exclude from hashing
- `load_seed_matchup_history(seed_a, seed_b)`: `@st.cache_data` — integer args; no hash_funcs needed
- `compute_pool_strategy_cached(_mc_result, field_size)`: underscore prefix on `_mc_result`

### Critical Pitfalls

1. **Pool optimizer outputs a chalk bracket, not a contrarian bracket** — happens when the optimizer reuses `simulate_bracket(mode='deterministic')` output rather than implementing a separate code path that accounts for public pick popularity. The warning signs are unambiguous: if the optimizer champion is always a #1 or #2 seed and the output bracket is identical to the deterministic bracket, the feature has no strategic value. Prevention: `EV(pick) ∝ P(team advances to slot) / P(public picks that team at that slot)`. This ratio — not raw win probability — is the output that needs to be computed.

2. **No free structured API for public pick percentages — contrarian logic needs a documented baseline** — ESPN's "Who Picked Whom" comprehensive breakdown is discontinued as a structured endpoint. Getting actual ownership data requires scraping or a paid service. Prevention: use historically calibrated seed-based pick-popularity priors as the MVP baseline (well-documented in PoolGenius research); after bracket announcement, scrape the ESPN Tournament Challenge champion pick percentage page (available publicly post-Selection Sunday); document the data source assumption explicitly in the UI.

3. **Model retraining with mismatched season data silently degrades performance** — if 2025-26 Torvik ratings have different column schema, null handling, or value distributions from the 2024-25 proxy data, the retrained model can embed shifted feature distributions without throwing an error. The ClippedCalibrator `[0.05, 0.89]` bounds may no longer be appropriate. Prevention: diff the new `current_season_stats.parquet` against the proxy on column names, value ranges (mean/std for barthag, adj_o, adj_d), and null count before triggering any retrain; run the multi-year backtest after retraining and require Brier not to regress beyond 0.01 from the 0.1692 baseline.

4. **cbbdata 2025-26 data not available by tournament tip-off — no documented fallback decision** — year=2026 returns empty as of 2026-03-13 (confirmed in `cbbdata_client.py` comments). Prevention: formalize the decision tree now: if 2025-26 data is not indexed by EOD 2026-03-14, deploy the v1.0 model explicitly labeled "2024-25 proxy data" and stop waiting. The v1.0 model (Brier 0.1692) is a fully valid deployment path.

5. **v1.1 changes break the working v1.0 app before tournament tip-off** — a broken app on 2026-03-19 is total project failure. Prevention: `git tag v1.0-stable` before any v1.1 development begins; run an E2E smoke test (bracket renders, MC simulation runs, overrides work, champion displayed) after each significant change; if the app is broken on the morning of 2026-03-19, revert to v1.0-stable immediately without attempting last-minute fixes.

---

## Implications for Roadmap

The Selection Sunday constraint (2026-03-15, 48 hours from research date) makes phase ordering critical. The three features are largely independent but share one prerequisite (data refresh decision) and one shared risk (breaking existing flows). The recommended build order prioritizes stability first, then highest business value, then lower-priority enrichment.

### Phase 0: Stability Baseline

**Rationale:** A broken app at tournament tip-off is total failure. This phase creates the rollback safety net that makes all parallel v1.1 work safe to attempt.
**Delivers:** `git tag v1.0-stable`; confirmed E2E smoke test passes; `bracket_manual.csv` pre-populated with bracketology projections as Selection Sunday fallback
**Addresses:** Pitfall V1.1-T5 (app broken at tip-off), Pitfall V1.1-T2 (bracket fetch fails on Selection Sunday)
**Time estimate:** 1-2 hours
**Research flag:** None — standard git operations and smoke testing

### Phase 1: Data Refresh + Retraining Decision

**Rationale:** Everything downstream depends on knowing which season's data is live. This decision gates retraining and must be made before the bracket is announced.
**Delivers:** `current_season_stats.parquet` refresh attempt; explicit go/no-go decision on retraining; `SELECTION_SUNDAY_DATES` updated for 2026 in `cutoff_dates.py`; data vintage label surfaced in UI sidebar
**Addresses:** Pitfall V1.1-C4 (no fallback plan for unavailable data), Pitfall V1.1-M3 (UI shows stats from wrong season)
**Hard cutoff:** If 2025-26 data not available by EOD 2026-03-14, deploy v1.0 model and label it "2024-25 proxy data" — do not delay
**Time estimate:** 2-3 hours including validation if data becomes available
**Research flag:** Data availability is LOW confidence — confirmed empty as of 2026-03-13; must be re-checked by EOD 2026-03-14

### Phase 2: Pool Strategy Optimizer

**Rationale:** Highest-value stated v1.1 goal. Independent of UI enrichment. Reads `mc_result` already in memory, so it can begin in parallel with Phase 1. Must ship before Selection Sunday to inform actual bracket submission.
**Delivers:** `src/pool/optimizer.py` with `compute_pool_strategy()`; `src/ui/pool_loader.py` with cache wrapper; Pool Strategy tab in `app.py`; pick percentage manual input UI; champion value recommendation callout; pool size input with strategy threshold warning at < 50 entrants
**Implements:** Integration Point B (pool optimizer) from ARCHITECTURE.md
**Addresses:** Pitfall V1.1-C1 (chalk bracket instead of contrarian), Pitfall V1.1-C2 (no pick popularity baseline), Pitfall V1.1-M2 (scoring system not configurable), Pitfall V1.1-M6 (small pool effect)
**MVP scope:** Value table for champion + Final Four slots; manual pick percentage input; standard scoring default (1-2-4-8-16-32) with configurable weights; pool size dropdown
**Defer:** Full 7-round value table, expected score calculator, automated pick percentage fetch
**Research flag:** Pool optimizer algorithm is MEDIUM confidence — EV formula is industry-standard but the pick popularity estimation for the baseline requires a documented assumption. Build the baseline assumption as an explicit, swappable input.

### Phase 3: UI Matchup Context Enrichment

**Rationale:** Delivers good UX but does not change what bracket gets submitted — lower priority than the optimizer. Must be strictly time-boxed.
**Delivers:** `src/ui/matchup_context.py`; `src/ui/seed_history.py`; `load_stats_lookup_cached()` in `data_loader.py`; matchup stats panel inside existing override expanders in `override_controls.py`
**Implements:** Integration Point C (UI enrichment) from ARCHITECTURE.md
**Addresses:** Pitfall V1.1-M3 (data vintage labeling), Pitfall V1.1-T4 (scope creep consuming optimizer time)
**Hard time-box:** Show the 6 FEATURE_COLS (adjoe_diff, adjde_diff, barthag_diff, seed_diff, adjt_diff, wab_diff) plus win probability and historical seed matchup win rate. No additional data sources until Phase 2 (pool optimizer) is verified complete and working.
**Defer:** SHAP feature importance, four-factor breakdown, historical tournament records per team
**Research flag:** None — established Streamlit patterns; follow `data_loader.py` conventions precisely

### Phase 4: Model Retraining (Conditional)

**Rationale:** Conditional on Phase 1 go/no-go. If 2025-26 data becomes available, run this after the pool optimizer is working — do not let retraining block optimizer development.
**Delivers:** Updated `BACKTEST_YEARS` and `build_stats_lookup()` year parameterization; `scripts/retrain.py` orchestration script; retrained `ensemble.joblib` with pre/post Brier comparison; artifact backup at `ensemble_v1.0.joblib`
**Implements:** Integration Point A (model retraining) from ARCHITECTURE.md
**Addresses:** Pitfall V1.1-C3 (schema mismatch silent degradation), Pitfall V1.1-M5 (artifact overwrite without backup), Pitfall V1.1-T3 (retrain blocks bracket filling)
**If data unavailable:** Deploy v1.0 model with "2024-25 proxy data" label; retraining becomes a post-tournament task (after April 2026 when cbbdata indexes season-end ratings)
**Research flag:** Retraining pipeline mechanics are HIGH confidence (derived from direct code audit). Data availability is LOW confidence.

### Phase Ordering Rationale

- Phase 0 before everything: a broken app at tournament time is total failure; the safety tag costs 30 minutes and eliminates that risk.
- Phase 1 before Phase 4: the retraining decision must be made before spending engineering time on it; data availability gates the entire retrain path.
- Phase 2 before Phase 3: the pool optimizer directly answers "which bracket do I submit to the pool." UI enrichment is informational. The research explicitly identifies scope creep on UI as a top time-pressure failure mode.
- Phase 4 is conditional: it runs if data is available; if not, it is deferred until post-tournament. This prevents it from blocking any other phase.
- Phases 2 and 3 can be parallelized if time allows — they share no hard code dependencies beyond `load_stats_lookup_cached()`, which should be added to `data_loader.py` first.

### Research Flags

Phases needing particular care during implementation:

- **Phase 1 (Data Refresh):** Data availability is LOW confidence. Document the go/no-go decision explicitly — the fallback path is as valid as the retrain path, but it must be a deliberate labeled choice.
- **Phase 2 (Pool Optimizer):** The pick popularity estimation baseline is MEDIUM confidence. The EV formula is industry-standard; the source of `pick_pct` when no ESPN data is available requires a documented assumption (seed-based priors). The optimizer must make this assumption visible to the user, not hide it.
- **Phase 4 (Retraining):** The data diff step (schema and distribution validation before retrain) is not in the existing pipeline. It must be added before trusting any retrain output.

Phases with established patterns (minimal implementation risk):

- **Phase 0 (Stability):** Standard git operations.
- **Phase 3 (UI Enrichment):** Streamlit `st.dialog`, `@st.cache_data` with underscore-prefix convention, and DuckDB queries are all established patterns in the codebase. Follow `data_loader.py` exactly.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against live venv; `st.dialog` and `st.popover` confirmed in Streamlit 1.55.0 changelog; no new dependencies required |
| Features | HIGH (pool optimizer domain), MEDIUM (pick popularity data) | Pool optimizer EV framework is well-established across practitioner sources. The data source for public pick percentages has no clean free API — this is a known gap resolved by design decision (seed-based priors as MVP baseline), not by additional research |
| Architecture | HIGH | Derived from direct audit of 12,400+ lines across 167 files; integration points confirmed by reading actual function signatures and output contracts; no assumptions |
| Pitfalls | HIGH (code-grounded), MEDIUM (domain) | Code-grounded pitfalls (schema mismatch, bracket slot contract, cache invalidation) are HIGH; domain pitfalls (pool strategy failure modes) are MEDIUM from practitioner sources |

**Overall confidence:** HIGH for technical execution; MEDIUM for pool strategy output quality (depends on pick popularity data accuracy)

### Gaps to Address

- **Public pick percentage data source:** No free structured API exists for actual pool field pick rates. Resolution: use historically calibrated seed-based pick-popularity priors as MVP baseline; document the assumption explicitly in the UI tooltip or sidebar; after bracket announcement, scrape the ESPN Tournament Challenge champion pick % page (publicly available post-Selection Sunday).

- **cbbdata 2025-26 data availability:** Confirmed unavailable as of 2026-03-13. Resolution: re-check by EOD 2026-03-14; make the go/no-go decision explicit and documented; deploy v1.0 with proxy data label if unavailable.

- **ClippedCalibrator bounds for retrained model:** The `[0.05, 0.89]` bounds were set on the 2024-25 proxy distribution. If 2025-26 had unusual parity or dominance, these bounds may not be optimal after retraining. Resolution: run `plot_calibration()` (already exists in `ensemble.py`) for old vs. new model before deploying the retrained artifact.

- **ESPN bracket fetch post-announcement behavior:** The auto-fetch pipeline was built but not tested against real post-announcement data. Resolution: pre-populate `bracket_manual.csv` from bracketology projections now; use as fallback if auto-fetch returns unexpected format.

---

## Sources

### Primary (HIGH confidence — direct codebase inspection or official docs)

- `src/ingest/cbbdata_client.py`, `src/models/ensemble.py`, `src/models/features.py`, `src/models/temporal_cv.py`, `src/simulator/simulate.py`, `src/ui/data_loader.py`, `src/ui/override_controls.py`, `app.py` — all integration points and data contracts verified by direct read
- Streamlit 1.55.0 release notes and API docs — `st.dialog`, `st.popover` availability confirmed
- pypi.org/project/scipy, numpy, joblib — installed version confirmation via live venv
- `cbbdata_client.py` line 113 comment — 2025-26 data unavailability confirmed
- `models/ensemble.joblib` inspection — artifact structure and version metadata confirmed

### Secondary (MEDIUM confidence — practitioner sources, multiple-source corroboration)

- PoolGenius Bracket Picks FAQ and Risk-Value Framework — pool optimizer EV formula framework (WebFetch verified)
- Syracuse University Analytics Professor interview 2026-03-11 — pool size thresholds (< 50 chalk, > 100 contrarian) (WebFetch verified)
- ActionNetwork and Establish The Run bracket pool strategy guides — contrarian leverage methodology
- arXiv 2508.02725v1 (peer-reviewed) — temporal validation, calibration, retraining risks

### Tertiary (LOW confidence — access-restricted or inferred)

- FTN Fantasy Advanced Bracket Strategies — 403 on WebFetch; findings corroborated by other sources
- ESPN "Who Picked Whom" comprehensive breakdown — discontinued; pick percentage availability is a known gap with no resolution other than scraping or manual entry

---

*Research completed: 2026-03-13*
*Supersedes: 2026-03-02 v1.0 SUMMARY.md (available in git history)*
*Ready for roadmap: yes*
