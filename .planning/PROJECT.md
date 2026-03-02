# March Madness 2026 Bracket Predictor

## What This Is

An interactive web application that uses an ensemble of machine learning models to predict every game in the 2026 NCAA Men's Basketball Tournament. Given the 68-team bracket, it produces win probabilities for each matchup across all rounds and predicts a champion with both a confidence percentage and a predicted championship game score. The bracket is interactive — users can override individual picks and see how changes ripple through downstream rounds.

## Core Value

Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges — the model must produce better-than-seed-based predictions validated against historical tournament results.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] ML ensemble trained on historical NCAA tournament data from public APIs/datasets
- [ ] Auto-fetch of the 68-team bracket when announced on Selection Sunday
- [ ] Win probability predictions for every game in every round
- [ ] Champion prediction with confidence percentage and predicted championship game score
- [ ] Interactive web bracket visualization — override picks and see downstream effects
- [ ] Backtesting against the 2025 tournament using in-repo data and public sources
- [ ] Multiple model architectures compared (ensemble/experiment approach — pick the best performer)
- [ ] Historical team stats ingestion from public sources (KenPom-style efficiency, seed history, strength of schedule, etc.)

### Out of Scope

- Score predictions for every game — only win probabilities (championship game is the exception)
- Multi-user support — this is a personal tool
- Mobile app — web-only
- Real-time game tracking or live updates during the tournament
- Explainability/feature importance — just show the probabilities, not why

## Context

- The 2026 NCAA tournament is approaching (Selection Sunday mid-March 2026)
- Reference data already in the repo:
  - `2025 NCAA Tournament Guide.html/.pdf` — detailed 2025 tournament analysis
  - `2025-tournament-results-wiki.md` — full 2025 bracket results (Florida won, beat Houston 65-63)
  - `rankings-3-2-26.md` — current power rankings as of March 1, 2026
  - `bauertology-3-2-26.webp` — projected 2026 bracket (bracketology)
  - `true-seed-3-2-26.webp` — overall true seed rankings
- 2025 tournament was historically chalk: all four #1 seeds made the Final Four, no top-4 seed lost in Round 1
- Key 2026 contenders per current rankings: Duke (#1), Michigan (#2), Arizona (#3), UConn (#4), Florida (#5)
- Model needs to handle both historical trends AND the specific characteristics of each year's field

## Constraints

- **Data**: Public APIs/datasets only — no paid subscriptions (KenPom is paid; need free alternatives or scraped equivalents)
- **Timeline**: Must be functional before Selection Sunday 2026 (mid-March)
- **Audience**: Single user (personal tool) — no auth, no deployment complexity needed
- **Tech stack**: To be determined during research phase

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Ensemble/experiment approach for ML | Try multiple model architectures, compare performance, use the best | — Pending |
| Win probabilities over score predictions | Probabilities are more useful for bracket decisions than exact scores | — Pending |
| Backtest against 2025 first | Validates model quality before trusting it for 2026 picks | — Pending |
| Interactive bracket (not read-only) | Ability to override and explore "what if" scenarios adds personal value | — Pending |
| Auto-fetch bracket | Eliminates manual data entry on Selection Sunday | — Pending |

---
*Last updated: 2026-03-02 after initialization*
