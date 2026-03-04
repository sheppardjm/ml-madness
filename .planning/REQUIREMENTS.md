# Requirements: March Madness 2026 Bracket Predictor

**Defined:** 2026-03-02
**Core Value:** Accurate, data-driven bracket predictions that give a competitive edge in bracket challenges

## v1 Requirements

### Data Pipeline

- [ ] **DATA-01**: Historical tournament data backfilled from Kaggle (20+ years of seasons)
- [x] **DATA-02**: Current 2025-26 season stats pulled from CBBpy + cbbdata APIs
- [ ] **DATA-03**: Team name normalization mapping across all data sources (ESPN, Kaggle, Sports-Reference, cbbdata)
- [x] **DATA-04**: Auto-fetch 68-team bracket from ESPN unofficial API with manual CSV fallback

### Modeling

- [x] **MODL-01**: Logistic regression baseline model trained on efficiency differentials
- [ ] **MODL-02**: XGBoost + LightGBM stacking ensemble producing calibrated win probabilities
- [x] **MODL-03**: Walk-forward temporal validation (train on years 1–N, test on year N+1)
- [x] **MODL-04**: Model evaluation using Brier score and log-loss (not just accuracy)

### Simulation

- [ ] **SIML-01**: Monte Carlo bracket simulation (10K+ runs) propagating probabilities through all 67 games
- [ ] **SIML-02**: Champion prediction with confidence percentage
- [ ] **SIML-03**: Predicted championship game score
- [ ] **SIML-04**: Round-by-round advancement probabilities for each team

### Backtesting

- [ ] **BACK-01**: Backtest model against 2025 tournament using in-repo results data
- [ ] **BACK-02**: Multi-year holdout validation across 2022–2025 (chalk + upset-heavy years)
- [ ] **BACK-03**: Model comparison dashboard showing baseline vs ensemble performance

### Web UI

- [ ] **WEBU-01**: Visual 68-team bracket display with predicted winners
- [ ] **WEBU-02**: Win probabilities shown per game matchup
- [ ] **WEBU-03**: Interactive pick overrides with downstream cascade recalculation

## v2 Requirements

### Strategy

- **STRT-01**: Pool-strategy optimization identifying contrarian picks where public diverges from model
- **STRT-02**: Multiple bracket generation optimized for different pool sizes

### Data Enrichment

- **ENRC-01**: Injury data integration from NCAA mandatory availability reports
- **ENRC-02**: Conference tournament momentum/recency weighting

### Explainability

- **EXPL-01**: Feature importance display per matchup (why Team A over Team B)
- **EXPL-02**: Historical analogues (similar past matchups and their outcomes)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Score predictions for every game | Win probabilities are more useful for bracket decisions; only championship gets a score |
| Multi-user support | Personal tool — no auth, accounts, or sharing needed |
| Mobile app | Web-only; Streamlit handles responsive adequately |
| Real-time game tracking | Tool is for pre-tournament bracket filling, not live monitoring |
| Explainability (v1) | Probabilities are sufficient; feature importance deferred to v2 |
| Paid data sources (KenPom) | Free alternatives (cbbdata/Bart Torvik) provide equivalent metrics |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-04 | Phase 2 | Complete |
| MODL-01 | Phase 3 | Complete |
| MODL-03 | Phase 3 | Complete |
| MODL-04 | Phase 3 | Complete |
| SIML-01 | Phase 4 | Pending |
| SIML-02 | Phase 4 | Pending |
| SIML-03 | Phase 4 | Pending |
| SIML-04 | Phase 4 | Pending |
| BACK-01 | Phase 5 | Pending |
| BACK-02 | Phase 5 | Pending |
| MODL-02 | Phase 6 | Pending |
| BACK-03 | Phase 7 | Pending |
| WEBU-01 | Phase 9 | Pending |
| WEBU-02 | Phase 9 | Pending |
| WEBU-03 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-02*
*Last updated: 2026-03-04 after Phase 3 completion — MODL-01, MODL-03, MODL-04 marked Complete*
