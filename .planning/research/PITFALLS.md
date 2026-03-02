# Domain Pitfalls: NCAA Bracket Prediction

**Domain:** NCAA Men's Basketball Tournament Bracket Prediction
**Researched:** 2026-03-02
**Confidence:** MEDIUM — findings from multiple practitioner sources, academic papers, and verified community wisdom; tournament-specific ML pitfalls are well-documented but not always rigorously peer-reviewed

---

## Critical Pitfalls

Mistakes that cause rewrites, fundamentally broken backtests, or models that perform well in training but fail in deployment.

---

### Pitfall 1: Data Leakage from Tournament Outcomes into Training Features

**What goes wrong:** Features are computed using data that was not available at the time of prediction. The most common form: using full-season statistics (including post-Selection Sunday games) as features for predicting early-round tournament games. A subtler form: including the tournament seed itself as a feature when training on historical tournament games — seeds partially encode the committee's judgment about team strength but were assigned after the season ended and carry committee biases.

**Why it happens:** It feels natural to use "the team's season statistics" as inputs, but stats scraped from a season-end summary include games played after Selection Sunday. Also, many practitioners grab the seed directly from tournament records without thinking about what that number represents or when it became available.

**Consequences:** The model trains on information it cannot have at prediction time. Backtesting looks unrealistically accurate. When deployed to predict the live 2026 bracket, performance drops sharply. Models that include seed as a raw feature may also inherit the selection committee's documented conference bias, causing them to systematically over-value power-conference teams and under-value mid-majors.

**Prevention:**
- Feature engineering must use only data available as of Selection Sunday for each tournament year being modeled
- For regular-season statistics, cut off at the conference tournament final (approximately 2 weeks before Selection Sunday)
- Avoid using the raw seed as a primary feature; instead derive team strength directly from efficiency metrics (AdjEM, KenPom rank) that are themselves date-bounded
- If seed is used, treat it as an independent variable subject to known committee bias, not a clean proxy for team quality

**Detection:** Unusually high training accuracy (above ~78–80%) is a red flag. Compare model predictions before vs. after removing time-bounded features to check for leakage.

**Phase to address:** Data collection and feature engineering (Phase 1–2). This must be correct before any modeling begins.

---

### Pitfall 2: Treating Tournament Games as Independent Samples for Cross-Validation

**What goes wrong:** K-fold cross-validation is applied to tournament game records, randomly mixing game outcomes from different years. This means the model may train on a 2023 Elite Eight game and evaluate on a 2020 first-round game from the same feature space — effectively letting future information bleed into training.

**Why it happens:** K-fold is the default validation method in scikit-learn and most tutorials. Nothing in the API warns you that time-series data requires temporal splitting.

**Consequences:** Cross-validation accuracy is optimistic. The model appears well-validated but has actually memorized patterns that are year-specific or era-specific. When backtesting against a held-out tournament year (e.g., 2025), performance degrades unexpectedly.

**Prevention:**
- Use walk-forward temporal validation: train on years 2000–2019, evaluate on 2020; then train on 2000–2020, evaluate on 2021; etc.
- Never let future tournament outcomes appear in a training fold
- For the 2026 deployment, train on all data through 2025 — but backtest methodology must have been temporal throughout development

**Detection:** If cross-validation score is substantially higher than your hold-out-year test scores, you have temporal leakage.

**Phase to address:** Model selection and backtesting (Phase 3). Must be established before comparing models.

---

### Pitfall 3: Models Default to "Chalk" — Predicting All Favorites, Generating No Useful Variance

**What goes wrong:** A classifier trained on historical matchups learns that the higher-seeded (better) team wins about 71% of the time. It then predicts the favorite to win almost every game. The resulting bracket is heavily favored toward top seeds, producing a prediction that is "accurate" in aggregate (because favorites do win most games) but useless for capturing the actual tournament outcome — and particularly bad when the tournament is NOT chalk.

**Why it happens:** The training set is imbalanced: upsets (lower seed winning) represent only ~29% of games. Models trained without handling class imbalance learn to predict the majority class. This bias is rewarded by accuracy metrics but penalizes log-loss and produces brackets that lack differentiation.

**Consequences:** The bracket predicts all 1-seeds to the Final Four every year. When 2025 happened to be chalk, this looks fine — but calibration is wrong (the model is not actually assigning 71% probabilities; it may be assigning 90%+). When 2022 or 2023 tournament variance returns, the bracket falls apart.

**Prevention:**
- Evaluate with calibration metrics (Brier score, log-loss) not just accuracy
- Apply class-imbalance handling: resampling (SMOTE or undersample favorites), or class weights in the loss function
- Calibrate model outputs to ensure predicted probabilities reflect historical upset rates (e.g., ~33% for a 5 vs. 12 matchup, not 15%)
- Generate multiple bracket simulations — if 10,000 simulations all have the same Final Four, your probabilities are too extreme

**Detection:** Run 10,000 Monte Carlo simulations from your win probabilities. If less than 5% of simulations produce a bracket with even one 10+ seed in the Sweet 16, your probabilities are miscalibrated.

**Phase to address:** Model training and calibration (Phase 3), and simulation design (Phase 4).

---

### Pitfall 4: Ignoring the Transfer Portal Era — Using Historical Team Identity Across Seasons

**What goes wrong:** Models trained on multi-year team statistics assume some team identity continuity year-over-year. A "Kentucky 2024" feature assumes the 2024 team resembles the 2023 team. Since 2021, the transfer portal has fundamentally broken this assumption: in 2025, 53% of tournament rotation players had previously played at another D-I school, and roughly one-third were new to their team that very season.

**Why it happens:** Historical team-level aggregate statistics (points per game, KenPom AdjEM) obscure player composition. A researcher pulling "team stats for Duke 2023–2025" gets a continuous series, but the actual roster may have 70% new players in 2025.

**Consequences:** Features computed from year-over-year team trends (momentum, consistency, previous tournament experience) are unreliable for recent seasons. A model trained on 2003–2018 data when rosters were stable may perform differently on 2022–2025 data with portal-era rosters.

**Prevention:**
- Use season-bounded statistics (what did this team do THIS season, not prior seasons) as the primary feature set
- Be cautious with multi-year trend features; if used, test whether they degrade performance in portal-era years (2021+)
- Do not use raw "team tournament experience" features without verifying that the current roster's players actually accumulated that experience

**Detection:** Compare model accuracy on pre-2021 holdout years vs. 2021–2024 holdout years. If accuracy degrades significantly in portal-era years, your features have a roster-continuity problem.

**Phase to address:** Feature engineering (Phase 2), with explicit consideration in backtesting (Phase 3).

---

### Pitfall 5: Backtesting Only on 2025 — A Sample Size of One with a Historically Unusual Outcome

**What goes wrong:** The project specifies "backtesting against 2025 first." This is correct to start, but 2025 was historically chalk: all four #1 seeds in the Final Four, only the second time in 38 years this happened. A model that "backtests well on 2025" may simply be a chalk-heavy model that happens to match a chalk-heavy tournament — not a model that correctly learned to assign appropriate uncertainty.

**Why it happens:** Single-year validation is fast and concrete. It's tempting to call a model "validated" after one good backtest.

**Consequences:** The model appears validated but is actually miscalibrated for variance. It will underperform in typical tournament years (2022: NC State to Final Four; 2023: FAU to Final Four; 2024: N.C. State to Elite 8) where 8+ seeds upset 1/2 seeds.

**Prevention:**
- Backtest against multiple years: include at least 3 recent tournaments spanning different variance profiles
  - 2025: chalk year (all 1s in Final Four)
  - 2024: moderate chaos (NC State's run)
  - 2023: high chaos (FAU, San Diego State Final Four)
  - 2022: high chaos (Saint Peter's Elite Eight)
- Evaluate using log-loss or Brier score across all years, not just "did you pick the champion"
- A good model should show calibrated probabilities across years, not just accuracy in one year

**Detection:** If your model scores well on 2025 but log-loss degrades sharply on 2022 and 2023 holdouts, you have a chalk-biased model.

**Phase to address:** Backtesting design (Phase 3). Multi-year validation must be the standard, not 2025-only.

---

## Moderate Pitfalls

Mistakes that cause technical debt, misleading metrics, or brackets that look scientific but are not.

---

### Pitfall 6: Seed Bias from Committee Subjectivity

**What goes wrong:** Seeds are assigned by an NCAA selection committee with documented conference bias. Research has found that being in the Pac-12 was equivalent to being ranked ~31 spots higher in RPI than the seed implied; Missouri Valley Conference teams were treated as if they were 32 spots lower. Using seed directly as a model feature inherits this bias.

**Why it happens:** Seed is the most visible tournament feature. It's easy to include and correlates with tournament success.

**Consequences:** Models treat mid-major teams as weaker than they are, systematically missing the FAU, San Diego State, or Loyola-Chicago type runs. The model will structurally undervalue automatic-bid mid-major champions.

**Prevention:**
- Primary strength features should be efficiency-based (KenPom AdjEM, Barthag/Torvik T-Rank) rather than seed
- If seed is included, treat it as one feature among many, not a primary signal
- Test whether removing seed improves performance on mid-major upset games

**Sources:** TIME.com analysis of selection committee biases; research confirming seeding bias toward major conferences (LOW-MEDIUM confidence, methodology varies)

---

### Pitfall 7: Feature Multicollinearity — Redundant Statistics Bloating the Feature Set

**What goes wrong:** Practitioners include raw box score statistics (points per game, offensive rebounds, defensive rebounds, total rebounds, field goal attempts, field goal makes, field goal percentage) as separate features. These are linearly dependent. Similarly: AdjO, AdjD, and AdjEM — where AdjEM = AdjO minus AdjD — are collinear. Including all three doesn't add information; it destabilizes coefficient estimates in linear models and inflates feature importance scores.

**Why it happens:** More features feels like more information. Scraping all available statistics and dumping them into a model is the path of least resistance.

**Consequences:** Linear models (logistic regression) produce unreliable coefficients. Feature importance rankings in tree models are distorted. Model interprets noise from redundant features as signal.

**Prevention:**
- Use tempo-adjusted efficiency metrics (AdjEM or similar) rather than raw box score stats
- Explicitly exclude redundant features: if you include AdjO and AdjD, drop AdjEM (it's derived)
- Apply VIF (Variance Inflation Factor) analysis before finalizing feature set
- Prefer a small set of meaningful features over a large set of correlated ones; 8–12 well-chosen features typically outperform 40+ correlated ones

---

### Pitfall 8: Ignoring Probability Calibration — Accuracy Metrics Hide Miscalibration

**What goes wrong:** A model is evaluated with accuracy ("correctly predicted 74% of games") but never checked for calibration. The model may predict a team has 90% win probability when the actual historical win rate for that matchup type is 65%. Accuracy looks fine because the team does usually win, but the confidence interval is wrong — and wrong probabilities cascade into bracket simulations that are overconfident.

**Why it happens:** Classification accuracy is the default metric. Log-loss and Brier score require more setup and interpretation.

**Consequences:** Monte Carlo simulations using uncalibrated probabilities produce brackets that look crisp (few upsets) but are structurally wrong. The model might assign 5% probability to outcomes that historically happen 20% of the time.

**Prevention:**
- Use Brier score as the primary evaluation metric (lower is better; measures calibration directly)
- Supplement with log-loss for penalty on overconfident wrong predictions
- Plot reliability diagrams (calibration curves): bins of predicted probability vs. actual win rate should fall near the diagonal
- Apply Platt scaling or isotonic regression to calibrate output probabilities if needed

---

### Pitfall 9: Small Total Sample — Treating Tournament Games as Sufficient Training Data Alone

**What goes wrong:** 63 tournament games per year × 40 years = ~2,500 historical tournament games. That sounds like a lot but after filtering to matchup types (e.g., 5 vs. 12 seed), subsets get tiny. Models trained only on tournament game outcomes don't have enough data to learn reliable game-by-game features.

**Why it happens:** The natural impulse is to train on tournament games to predict tournament games. But this ignores the massive regular-season data available.

**Consequences:** Models overfit to tournament-specific patterns that may be noise. Some seed matchups have fewer than 50 historical examples — not enough to make statistical claims.

**Prevention:**
- Train models primarily on regular-season game data (tens of thousands of games available since 2003) to learn what predicts wins
- Use tournament data only for calibration/validation, not as the primary training set
- For matchup-specific seed probabilities (e.g., 5 vs. 12), use base rates from the full tournament history rather than trying to fit a model to 40 data points

---

### Pitfall 10: Bracket Filling Strategy Confusion — Win Probability vs. Expected Bracket Score

**What goes wrong:** Win probabilities are computed correctly, but the bracket is filled by picking the most probable winner at each step (greedy). This ignores that bracket scoring is exponential: a correctly predicted champion is worth as much as every correct first-round game combined (32 points in standard ESPN scoring). A greedy probability approach picks the "safest" team at each round but misses that picking a slightly-less-probable champion correctly is worth far more than the probability loss in early rounds.

**Why it happens:** "Pick the most likely winner" is intuitive and feels analytically rigorous.

**Consequences:** The bracket is essentially chalk (always picks the top seed) and leaves no room for the differentiating picks that win pools. In a pool of 100 people who all follow this approach, no one wins; in a pool where one person correctly calls a 2-seed champion, that person wins everything.

**Prevention:**
- Separate win-probability computation from bracket optimization
- For the final bracket, optimize for expected bracket score, not individual game probabilities — these require different approaches (Monte Carlo across all possible paths, adjusted for the scoring system)
- Recognize that bracket pool strategy and tournament prediction are different problems; the model answers "who will probably win each game" but filling a bracket to win a pool requires accounting for what other entrants are likely to pick

---

### Pitfall 11: Not Accounting for Injury and Roster Status at Tournament Time

**What goes wrong:** The model uses season-aggregate statistics to characterize teams without knowledge of player availability at tip-off. A star player out with injury makes the efficiency metrics irrelevant; a player returning from a season-ending injury dramatically upgrades them. The model has no way to know either.

**Why it happens:** Injury data for college basketball is poorly standardized and historically unavailable. This is genuinely hard to solve.

**Consequences:** A team's model-predicted strength may be significantly wrong for their specific tournament games. Example: a team predicted at 65% win probability drops to 40% because their top scorer is injured — but the model doesn't know.

**Prevention:**
- Acknowledge this as an irreducible model blind spot; document it explicitly in the project
- Build a manual override mechanism: before filling the final 2026 bracket, allow human review of injury reports for each team and allow probability adjustments
- Starting in 2026, the NCAA requires teams to submit player availability reports the night before and 2 hours before each game — this data should be factored in for the live bracket, even manually
- For backtesting purposes, this blind spot means backtest accuracy is an upper bound on real-world performance

**Phase to address:** Bracket generation (Phase 4), and explicitly noted as a known limitation in project documentation.

---

## Minor Pitfalls

Mistakes that cause confusion or wasted time but are recoverable.

---

### Pitfall 12: Picking Too Many Upsets Under "March Madness" Intuition

**What goes wrong:** The narrative around March Madness is about upsets. Practitioners building models (or users interpreting results) may manually dial up upset probability because "it's March Madness." Data consistently shows the public over-picks upsets relative to historical rates.

**Why it happens:** Upset stories are memorable; quiet chalk tournament runs are not. Availability bias drives over-weighting of high-upset years.

**Prevention:**
- A strategy of always picking the better seed would have been correct 87.5% of the time in 2004 and 75% in 2005, versus public performance of 75.2% and 72.9% — upsets are already baked into base rates
- Validate that model upset rates approximately match historical base rates by seed pairing; don't inflate them further
- For bracket pools: one or two well-chosen upset picks in high-leverage rounds (Sweet 16+) are more valuable than many first-round upset guesses

**Source:** Journal of Applied Social Psychology (2009), PoolGenius historical analysis (MEDIUM confidence)

---

### Pitfall 13: Using Matching Historical Seed Distributions as a Validation Target

**What goes wrong:** A practitioner verifies their model by checking that "historically, about 2% of 15-seeds win" and their model produces 2% 15-seed win rates. This creates false confidence. Historical seed distributions are aggregate patterns, not laws. Single tournament results deviate wildly from expected distributions.

**Why it happens:** Matching historical rates feels like calibration but is actually just reproducing base rates.

**Consequences:** The "Final Four seeds should average to 11" heuristic has been wrong in 2021 (total 15), 2023 (total 22), and 2024 (total 17). A model calibrated to reproduce this pattern would have been wrong in 3 of the last 4 years.

**Prevention:**
- Validate on per-game accuracy and calibration curves, not aggregate seed distribution matching
- Individual game log-loss and Brier score are the right metrics; seed distribution matching is not a reliable target

---

### Pitfall 14: Tournament Format Changes Contaminating Historical Data

**What goes wrong:** The NCAA tournament expanded from 64 to 65 teams in 2001 (play-in game), then to 68 teams in 2011 (four First Four games). Models trained on historical data before 2011 will either miss the First Four entirely or treat those games incorrectly if the data is not consistently filtered.

**Why it happens:** Kaggle datasets and scraped data often include First Four games labeled as Round 1 or not labeled at all. A model that includes First Four games as equivalent to 64-team Round 1 games is training on different competitive contexts.

**Prevention:**
- Filter historical data consistently: either always exclude First Four play-in games or always include them with a proper flag
- Be explicit about what "Round 1" means in your dataset for each year
- For bracket prediction purposes (predicting the 64-team bracket), First Four games are a selection mechanism, not a bracket game — handle them separately

---

## Phase-Specific Warnings

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|---------------|------------|
| Data Collection | Historical tournament records | Mixing pre-2011 (64-team) and post-2011 (68-team) data without flags | Explicitly mark tournament format per year; filter First Four games consistently |
| Data Collection | Season statistics | Using full-season stats that include post-Selection Sunday games | Cut stat windows at conference tournament completion |
| Feature Engineering | Strength metrics | Including raw seeds as primary features, inheriting committee bias | Use efficiency-based metrics (KenPom AdjEM, Torvik) as primary strength signals |
| Feature Engineering | Collinearity | Including AdjO + AdjD + AdjEM simultaneously, or total rebounds + offensive/defensive rebounds | Run VIF analysis; remove derived features that duplicate their components |
| Model Training | Class imbalance | Accuracy-optimizing model learns to always pick the favorite | Use Brier score / log-loss as loss function; apply class weights or resampling |
| Model Training | Overfitting | Deep models memorize year-specific tournament quirks | Temporal holdout validation; prefer simpler models (logistic regression, gradient boost) over deep learning given small N |
| Backtesting | Single-year validation | 2025 was historically chalk; a good 2025 backtest may be a chalk model | Multi-year backtest required: include 2022, 2023, 2024, 2025 — all with different variance profiles |
| Backtesting | Temporal leakage | K-fold CV randomly mixes tournament years | Use walk-forward temporal splits only |
| Simulation | Bracket filling strategy | Greedy probability picking produces all-chalk brackets | Simulate 10,000+ brackets; optimize for expected score, not per-game probability |
| Simulation | Miscalibration | Uncalibrated probabilities produce overconfident simulations | Calibration curves required before simulation; apply Platt scaling if needed |
| Deployment | Injury status | Season statistics don't reflect game-day roster | Manual review of 2026 injury reports required before bracket submission; build override mechanism |
| Deployment | Transfer portal | Historical team identity assumptions broken for 2022+ | Season-bounded features only; no multi-year team trend features without explicit testing |

---

## The Fundamental Accuracy Ceiling

Research across multiple sources (Georgia Tech's Joel Sokol, LSTM/Transformer papers, historical competition results) converges on this finding: **the best NCAA tournament prediction models top out at approximately 74–76% game-level accuracy.** This is an empirical ceiling, not a solvable software problem.

This ceiling exists because:
- Young athletes under tournament pressure produce high-variance outcomes
- Single-elimination format amplifies individual game variance
- Coaching adjustments can neutralize quantitative team strengths
- Fatigue, travel, and scheduling compress games in ways regular season stats don't capture

The implication for this project: **the goal is not to exceed this ceiling.** The goal is to build a well-calibrated model that assigns correct probabilities, handles the 2025 chalk case and the 2022 chaos case with equal correctness, and then uses those probabilities to fill a bracket strategically. A 74% accurate model with well-calibrated uncertainty estimates is a success; a 74% accurate model with poorly calibrated probabilities is a failure.

---

## Sources

- [Applying Machine Learning to March Madness — adeshpande3](https://adeshpande3.github.io/Applying-Machine-Learning-to-March-Madness) — key finding: chalk bias in gradient boosted models (MEDIUM confidence, practitioner)
- [Predicting NCAA basketball match outcomes using ML techniques: results and lessons learned](https://www.researchgate.net/publication/257749099_Predicting_college_basketball_match_outcomes_using_machine_learning_techniques_some_results_and_lessons_learned) — academic, confirms ~75% ceiling (MEDIUM confidence)
- [Forecasting NCAA Basketball Outcomes with Deep Learning (arXiv 2508.02725)](https://arxiv.org/html/2508.02725v1) — data leakage, calibration vs. discrimination tradeoff, temporal validation (MEDIUM confidence, peer-reviewed)
- [PoolGenius: Madness Myths — Historical Trends](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/madness-myths-your-bracket-should-match-historical-trends/) — seed distribution unreliability, 2021/2023/2024 Final Four seed totals (MEDIUM confidence)
- [PoolGenius: The Danger of Picking Too Many Upsets](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/the-danger-of-picking-too-many-upsets/) — public over-picks upsets; always-pick-better-seed baseline data (MEDIUM confidence)
- [PoolGenius: Bracket Strategy Guide](https://poolgenius.teamrankings.com/ncaa-bracket-picks/articles/bracket-strategy-guide/) — champion selection value, pool strategy (MEDIUM confidence)
- [TIME.com: March Madness Selection Committee Biases](https://keepingscore.blogs.time.com/2013/03/15/predicting-the-ncaa-mens-basketball-field-and-discovering-the-selection-committees-biases/) — conference seeding bias (LOW-MEDIUM confidence, 2013 data)
- [Predicting March Madness Upsets (Medium, Matt Worley)](https://towardsdatascience.com/predicting-upsets-in-the-ncaa-tournament-with-machine-learning-816fecf41f01) — class imbalance in upset prediction (LOW confidence, paywalled)
- [FasterCapital: Lookahead Bias in Sports Predictions](https://fastercapital.com/content/Lookahead-Bias-in-Sports-Predictions--The-Science-of-Accurate-Forecasts.html) — temporal leakage fundamentals (MEDIUM confidence)
- [NCAA Transfer Portal Impact — PBS News / CNBC](https://www.cnbc.com/2025/04/04/why-ncaa-transfer-portal-is-affecting-march-madness-.html) — 53% of 2025 tournament rotation players previously at another D-I school (HIGH confidence, reported fact)
- [NCAA announces 2026 injury reports — Bleacher Report](https://bleacherreport.com/articles/25273019-ncaa-announces-march-madness-2026-will-feature-team-injury-reports-after-rule-change) — 2026 will have official injury reports for first time (HIGH confidence)
- [March Madness 2025: All 4 No. 1 seeds in Final Four — Yahoo Sports](https://sports.yahoo.com/college-basketball/article/march-madness-2025-all-4-no-1-seeds-are-in-the-final-four-but-are-they-all-created-equally-004443321.html) — 2025 was second time in 38 years all 1s reached Final Four (HIGH confidence)
- [DRatings: Log Loss vs. Brier Score](https://www.dratings.com/log-loss-vs-brier-score/) — metric selection guidance (MEDIUM confidence)
- [Sports-AI.dev: AI Model Calibration — Brier Score](https://www.sports-ai.dev/blog/ai-model-calibration-brier-score) — calibration methodology for sports models (MEDIUM confidence)
