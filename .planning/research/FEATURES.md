# Feature Landscape: NCAA Bracket Prediction Tool

**Domain:** Personal ML-powered NCAA tournament bracket predictor
**Researched:** 2026-03-02
**Project:** madness2026 — personal use, single user, ML ensemble

---

## Research Methodology Note

This research surveyed the feature sets of: KenPom, SportsLine, TeamRankings/PoolGenius, ESPN BPI/Bracketology, BracketOdds (UIUC), Nate Silver's model, Opta Analyst, The Power Rank, and multiple open-source GitHub projects. Confidence levels noted per finding.

---

## Table Stakes

Features a bracket predictor must have or it's not worth using.

| Feature | Why Expected | Complexity | Confidence | Notes |
|---------|--------------|------------|------------|-------|
| Win probability for every first-round matchup | Every predictor does this; minimum viable output | Low | HIGH | Seed-vs-seed historical rates + adjusted efficiency margin are standard inputs |
| Win probability for all 63 tournament games | Users need round-by-round cascade, not just R64 | Med | HIGH | Requires propagating probabilities forward through bracket tree |
| Champion prediction with confidence % | The headline output; all major tools produce this | Med | HIGH | Nate Silver, SportsLine, KenPom all produce championship odds per team |
| Seed-based historical win rates by round | Every credible tool cites this baseline | Low | HIGH | 40 years of data (1985-2025); 1-seeds win 99.29%, 12-seeds win ~35% in R64; well-documented |
| Full 68-team bracket display | Tournament has 68 teams including First Four; missing this breaks the bracket | Med | HIGH | First Four games (play-in) produce the R64 field; must be included |
| Round-by-round advancement probabilities | Users need to see likelihood each team reaches each round, not just champion | Med | HIGH | All serious predictors (KenPom, SportsLine, TeamRankings) produce per-team per-round odds |
| Adjusted efficiency metrics as model inputs | KenPom AdjEM/AdjO/AdjD are the foundational features; predictors without them are demonstrably weaker | Med | HIGH | Since 2001, 95.7% of champions had top-22 KenPom offense + top-32 defense; verified via multiple sources |
| Auto-fetch current bracket/seedings | Tournament bracket data must populate automatically, not require manual entry | Med | HIGH | Manual entry is error-prone and makes the tool unusable on Selection Sunday |
| Backtesting against prior tournaments | Credibility of the model depends on showing it works historically | Med | HIGH | Standard practice: "leave one March out" cross-validation used across academic and open-source projects |

---

## Differentiators

Features not universally present, but that meaningfully improve prediction quality or bracket challenge performance.

| Feature | Value Proposition | Complexity | Confidence | Notes |
|---------|-------------------|------------|------------|-------|
| Ensemble of multiple rating systems | Combining KenPom + BPI + Torvik + NET + Vegas lines reduces individual model weaknesses; demonstrably more accurate | High | HIGH | Nate Silver uses 6 systems; ESPN consensus uses KenPom, BPI, Torvik, TeamRankings, SRS; multiple sources confirm ensemble beats single-model |
| Predicted final score / margin of victory | Doubles as a point spread; useful for understanding game texture, not just winner | Med | MEDIUM | Nate Silver, Bart Torvik (T-Rank), and KenPom all produce predicted margins; less common but valuable for characterizing confidence |
| Pool-strategy optimization (contrarian picks) | For bracket challenges, "expected value" vs. a field of opponents matters; picking the chalky favorite won't win large pools | High | HIGH | PoolGenius documents 3.1x win rate improvement; contrarian analysis is a proven differentiator — large pools require differentiation, small pools favor chalk |
| Interactive bracket with override picks | User can manually override a game pick and see downstream probability changes update in real time | High | MEDIUM | The Power Rank has hover-based probability display; NCAA official app has a "path to championship" tool; true drag-and-drop override with cascade recalculation is rare |
| Downstream cascade visualization | Selecting an upset shows how it ripples forward through the bracket tree | High | MEDIUM | Seen in Power Rank (hover probabilities on nodes); not commonly implemented with full cascade recalculation |
| Injury and roster adjustment | Models that adjust for known injuries perform better than static pre-tournament models | High | MEDIUM | Nate Silver explicitly includes injury recalibration; most tools rely on pre-tournament snapshot only |
| Style-of-play matchup analysis | Tempo, pace, 3-point rate, defensive pressure can identify mismatches | High | MEDIUM | Highlighted in ML research: 82-feature datasets include tempo, volatility, fatigue; "shot quality" and "shot volume index" cited by PoolGenius |
| Backtesting comparison against published models | Showing your model vs. KenPom, vs. chalk, vs. random gives credible performance benchmarking | Med | MEDIUM | Open-source College_Basketball project does this; placing in ESPN percentiles is a common benchmark |
| Real-time tournament update mode | Re-running predictions after each game using actual results (who advanced) as ground truth | High | LOW | Referenced as a feature by Nate Silver and SportsLine; requires live data feed and model re-scoring |
| Multiple bracket variants | "Optimal," "contrarian," and "upset-heavy" bracket flavors to fit different pool strategies | Med | MEDIUM | SportsLine produces both an "Optimal Bracket" and an "Upset Bracket" as separate products |
| Confidence intervals around win probabilities | Showing uncertainty (e.g. 60% ± 8%) rather than single point estimates | Med | LOW | Discussed in academic ML papers but rare in consumer tools; adds honesty about model limits |

---

## Anti-Features

Things to deliberately NOT build. These are time sinks that don't improve bracket quality or are harmful to the goal.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Perfect-bracket pursuit as the design goal | Mathematically impossible (1 in 9.2 quintillion); optimizing for perfect bracket leads to wrong choices | Optimize for expected points in a specific pool format, not perfection |
| Excessive first-round focus | First round is 50% of games but carries least scoring weight in most pools; winners are decided in Sweet 16 onward | Weight model effort toward later rounds where points per correct pick multiply |
| Historical trend quotas (e.g., "always pick one 12-seed upset") | Documented anti-pattern; 2025 had only 4 upsets total; trend-following fails in high-chalk years | Let win probability drive picks, not historical seed-line distributions |
| Predicting individual player performance | Player stats are too noisy per-game; team-level efficiency is more predictive and more stable | Stick to team-level adjusted efficiency metrics; include player absence (injury) as a binary flag |
| Real-time score prediction (live game) | This is a different product (live game predictor) with entirely different data requirements | Scope is pre-tournament bracket prediction, not in-game prediction |
| Multi-user / social features | Adds significant complexity; this is a personal tool | Personal use only; no accounts, no group pools, no leaderboards |
| Women's tournament coverage | Separate data, models, and bracket; doubles scope | Build the men's bracket predictor first; add women's in a later phase if desired |
| Comprehensive UI polish before model accuracy is validated | Spending engineering time on visuals before the model is calibrated inverts priorities | Get model producing good predictions first; visualization is a presentation layer |
| Real-money gambling integration | Regulatory and ethical complexity far outside scope | Use win probabilities for bracket optimization only |
| Recruiting/future season prediction | Out of scope; this is about this year's tournament | Scope strictly to current tournament teams |

---

## Feature Dependencies

Dependencies are ordered: the left feature must exist before the right one can be built.

```
Data pipeline (auto-fetch team stats + bracket)
  → Team ratings computation (KenPom-style adjusted efficiency)
    → Single-game win probability model (logistic regression or ensemble)
      → Round-by-round advancement probabilities (simulated bracket propagation)
        → Champion probability (% per team, output of simulation)
          → Predicted score/margin (secondary output of same model)
          → Interactive bracket visualization (consumes win probabilities)
            → Override picks + downstream cascade recalculation

Historical data pipeline (2010–2025 seasons + tournament results)
  → Backtesting harness (leave-one-March-out CV)
    → Model calibration and ensemble weighting
      → Performance benchmark vs. chalk and published models

Win probability per game + pool scoring system
  → Pool-strategy optimization (expected value analysis)
    → Contrarian pick identification
```

### Key Dependency Notes

- **Ensemble is only worth it after individual models are running.** Build each component model (logistic regression, gradient boost) independently, validate each, then combine. Combining bad models produces a bad ensemble.
- **Interactive visualization depends on stable probability outputs.** Do not build the UI until the model produces numbers you trust; otherwise you'll rebuild the UI as model outputs change shape.
- **Backtesting requires a clean historical dataset.** The hardest part of backtesting is consistent team name normalization across sources (Sports-Reference vs. KenPom vs. ESPN use different name formats). Solve this before building any model.
- **Auto-fetch bracket data is time-sensitive.** The bracket releases on Selection Sunday. The data pipeline must be ready before that date each year, not built during the tournament.

---

## MVP Recommendation

For a first working version that produces useful bracket picks:

**Must have (MVP):**
1. Historical data pipeline: 2010–2025 game results and team stats (KenPom/Sports-Reference)
2. Team name normalization across sources
3. Single-game win probability model (logistic regression on adjusted efficiency differentials)
4. Bracket simulation: run 10,000+ bracket simulations, aggregate advancement odds
5. Champion prediction with % confidence
6. Round-by-round advancement probabilities for all 68 teams
7. 2025 backtesting: validate model retroactively against actual 2025 tournament results
8. Auto-fetch 2026 bracket data (after Selection Sunday)
9. Static bracket visualization: display model picks with probabilities

**Add after MVP is validated:**
- Ensemble: add gradient boosting + additional rating systems (BPI, Torvik, NET) alongside logistic regression
- Predicted score/margin of victory
- Interactive bracket with override picks and downstream cascade
- Pool-strategy optimization (contrarian analysis for specific pool sizes)
- Injury adjustment flag

**Explicitly defer indefinitely:**
- Real-time tournament update mode (complex data feed, adds marginal bracket value)
- Multiple bracket flavors (useful but build one good bracket first)
- Women's tournament

---

## What the 2025 Tournament Teaches Us About Feature Priorities

The 2025 tournament was one of the least upset-prone in history (only 4 upsets total, all #1 seeds made the Final Four). This is relevant to feature design:

- **Upset prediction is high variance, low expected value.** A model that correctly picks chalk in 2025 would have massively outperformed upset-hunters. Features that bias toward upset detection (e.g., historical 12-5 rates) hurt more years than they help.
- **Champion prediction matters most.** NCAA.com data confirms bracket challenge winners are near-perfect from Sweet 16 onward and correctly predicted the championship matchup. The model should invest effort in champion/Final Four accuracy, not R64 upset picking.
- **The Elite Eight seed composition in 2025 (four 1-seeds, three 2-seeds, one 3-seed) was nearly identical to 2008.** High-chalk years are not rare. The model should not be tuned to "spread the upsets around."
- **Adjusted efficiency margin is the most verified predictor.** Every champion since 2001 was inside the top-22 offense and top-32 defense. Build around this signal first.

---

## Sources

- [KenPom 2025 NCAA Tournament Probabilities](https://kenpom.substack.com/p/2025-ncaa-tournament-probabilities) — HIGH confidence
- [Nate Silver 2025 March Madness Predictions](https://www.natesilver.net/p/2025-march-madness-ncaa-tournament-predictions) — HIGH confidence (methodology verified via WebFetch)
- [PoolGenius Bracket Strategy Guide](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/bracket-strategy-guide/) — HIGH confidence (WebFetch verified)
- [NCAA.com: 5 Tips from Bracket Challenge Game Winners Since 2015](https://www.ncaa.com/news/basketball-men/bracketiq/2026-02-24/5-ncaa-bracket-tips-learned-studying-every-bracket-challenge-game-winner-2015) — MEDIUM confidence (metadata confirmed, full article not extractable)
- [College_Basketball GitHub (pjmartinkus)](https://github.com/pjmartinkus/College_Basketball) — HIGH confidence (WebFetch verified methodology)
- [BracketOdds UIUC FAQ](https://bracketodds.cs.illinois.edu/BI.html) — MEDIUM confidence (WebFetch partial)
- [SportsLine 2026 Bracket Simulation](https://www.sportsline.com/insiders/2026-ncaa-tournament-optimal-bracket-simulation-model-on-epic-run-reveals-picks-predictions/) — MEDIUM confidence
- [TeamRankings 2026 Bracket Predictions](https://www.teamrankings.com/ncaa-tournament/bracket-predictions/) — MEDIUM confidence
- [Bracketology 101: Duke Chronicle seeding breakdown](https://www.dukechronicle.com/article/2025/01/duke-mens-basketball-bracketology-ncaa-tournament-seeding-breakdown-march-madness-net-rankings-kenpom-torvik-bpi-scheyer) — MEDIUM confidence
- [CBBpy Python library](https://pypi.org/project/CBBpy/) — HIGH confidence (official PyPI documentation)
- [Sportsreference Python API](https://sportsreference.readthedocs.io/en/stable/) — HIGH confidence (official documentation)
- [2025 NCAA Tournament Wikipedia results](https://en.wikipedia.org/wiki/2025_NCAA_Division_I_men%27s_basketball_tournament) — HIGH confidence (primary source, local file)
- [PoolGenius Contrarian Value Picks](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/balancing-risk-and-value-in-your-bracket/) — MEDIUM confidence
- [Predicting NCAA Upsets with ML — Towards Data Science](https://towardsdatascience.com/predicting-upsets-in-the-ncaa-tournament-with-machine-learning-816fecf41f01) — MEDIUM confidence
