# Technology Stack: NCAA Men's Basketball Bracket Predictor

**Project:** madness2026
**Researched:** 2026-03-02
**Research mode:** Ecosystem (Stack dimension)

---

## Recommended Stack

This is a Python-first project. The ML ecosystem lives entirely in Python. The web UI can be either a Streamlit app (single-process, easy) or a React frontend hitting a FastAPI backend (harder, better UX). See "Alternatives Considered" for the tradeoff analysis — **Streamlit is recommended for personal use**.

---

### Python Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Runtime | 3.12 is the sweet spot: fully stable, supported by all ML libraries (XGBoost 3.2 requires >=3.10, pandas 3.0 requires >=3.11, scikit-learn 1.8 requires >=3.11). 3.13 has experimental JIT but ecosystem still catching up. |

**Confidence: HIGH** — Verified against PyPI requirements for all major dependencies.

---

### Data Acquisition

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| CBBpy | 2.1.2 | ESPN game/boxscore scraper | Pure-Python, actively maintained (Jan 2025), pulls from ESPN. Provides game metadata, boxscores, play-by-play, schedules. Works for historical seasons back to ESPN's data. |
| requests | latest | HTTP client | Used internally by CBBpy; also needed for calling unofficial ESPN API endpoints directly |
| beautifulsoup4 | latest | HTML parsing | Dependency of CBBpy; also useful for scraping barttorvik.com data |

**Confidence: HIGH** — CBBpy version verified at PyPI. ESPN unofficial API endpoints confirmed to exist and require no auth key.

**Key data sources (free, no subscription):**

| Source | Access Method | Data Provided | Confidence |
|--------|--------------|---------------|------------|
| ESPN unofficial API | Direct HTTP GET (no auth) | Game scores, schedules, team metadata, postseason games | MEDIUM — unofficial, no stability guarantee |
| CBBpy (ESPN-backed) | `pip install CBBpy` | Game boxscores, play-by-play, schedules (2003+) | HIGH — actively maintained |
| cbbdata API (barttorvik-backed) | Free API key via registration | Adjusted efficiency, NET rankings, game predictions, Torvik ratings (2008+) | MEDIUM — free key needed, R-centric but REST API accessible from Python |
| Kaggle March Machine Learning Mania | Dataset download | Historical tournament results, seeds, team stats (2003-2025) | HIGH — official Kaggle competition dataset, updated annually |
| barttorvik.com | Web scraping (no official API) | T-Rank ratings, adjusted efficiency, tempo-free stats | LOW — scraping-only, site uses Cloudflare bot protection |
| Warren Nolan (warrennolan.com) | Web scraping | NET rankings, RPI, schedule strength | LOW — scraping only, no documented API |
| data.ncaa.com | Direct HTTP GET (JSON endpoints) | Official bracket, seeds, game results for postseason | MEDIUM — unofficial but stable pattern: `https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{year}/{month}/{day}/scoreboard.json` |
| Sports-Reference (college basketball) | Web scraping with rate limiting | Historical stats (limited, 20 req/min rate limit) | MEDIUM — rate-limited but documented |

**What replaces KenPom (paid):**
- **Primary replacement: cbbdata API** — provides barttorvik-based adjusted efficiency (barthag, adjOE, adjDE, tempo) which is methodologically similar to KenPom. Free API key. Updated daily during season.
- **Secondary: Kaggle dataset** — includes precomputed efficiency ratings for tournament teams each year going back to 2003.
- **Direct barttorvik.com scraping** is risky due to Cloudflare protection; cbbdata API is the correct free path.

---

### Data Storage

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| DuckDB | 1.4.4 | Primary analytical store | Serverless, file-based, columnar, 17x faster than pandas for analytical queries. Query Parquet and CSV files directly. Zero-copy pandas integration. Perfect for a personal project — no server to manage. |
| Parquet (via pandas/pyarrow) | — | Historical data archive | Store season data as Parquet files. DuckDB queries them directly without loading into memory. Portable. |
| SQLite | stdlib | Bracket state, picks, run metadata | Relational state that changes frequently (bracket picks, simulation runs, model run logs). SQLite handles OLTP, DuckDB handles analytics. |

**Confidence: HIGH** — DuckDB version verified at PyPI. DuckDB vs SQLite split is a well-documented pattern for analytics-heavy personal projects.

---

### ML / Feature Engineering

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| pandas | 3.0.1 | Data manipulation and feature engineering | Standard for tabular sports data. Required for CBBpy output. |
| numpy | latest stable | Numerical operations | Foundation for all ML libraries |
| scikit-learn | 1.8.0 | Baseline models, preprocessing, cross-validation, stacking | Logistic Regression, Random Forest, Pipeline, StratifiedKFold, StackingClassifier. Community-verified ~67-75% accuracy on tournament data. |
| XGBoost | 3.2.0 | Primary gradient boosted tree model | Most frequently used model in winning Kaggle March Mania entries. Confirmed current version is 3.2.0 (not 2.x as training data might suggest). Requires Python >=3.10. |
| LightGBM | 4.6.0 | Secondary gradient boosted tree model | Faster training than XGBoost on large feature sets. Slightly different inductive bias — adds diversity to ensemble. |
| optuna | latest | Hyperparameter tuning | Bayesian optimization for XGBoost/LightGBM hyperparameters. Preferred over GridSearchCV for this domain. |
| joblib | latest | Model persistence and parallelism | Serialize trained models to disk. Parallelize cross-validation folds. |

**Confidence: HIGH for versions** — XGBoost 3.2.0, scikit-learn 1.8.0, LightGBM 4.6.0, pandas 3.0.1 all verified at PyPI as of 2026-03-02.

**Model architecture: Stacking ensemble**

The recommended approach based on multiple Kaggle winning solutions and NCAA bracket prediction research:

```
Layer 1 (Base models, trained with cross-validation):
  - XGBoost classifier (primary)
  - LightGBM classifier
  - Logistic Regression (interpretable baseline)
  - Random Forest (scikit-learn)

Layer 2 (Meta-learner):
  - Logistic Regression on base model out-of-fold predictions

Output: Win probability for team A vs team B
```

Key features to engineer:
- Seed difference (SEED_DIFF) — single strongest predictor
- Adjusted offensive efficiency (adjOE) delta
- Adjusted defensive efficiency (adjDE) delta
- Barthag (projected win % vs average D1 opponent)
- Tempo differential
- Strength of schedule
- Win % in last 10 games
- Conference strength
- Historical seed vs seed win rates

---

### Web Visualization (Bracket UI)

**Recommendation: Streamlit for personal use**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Streamlit | 1.54.0 | Full web application framework | Single-process Python. No separate frontend build. Native integration with pandas/plotly. Sufficient for single-user personal tool. Ships fast. |
| Plotly | latest | Win probability charts, confidence visualizations | Integrates directly with Streamlit via `st.plotly_chart`. Interactive hover, bar charts for probability distributions. |
| react-tournament-brackets | npm (g-loot) | Bracket visualization component | Only option if going React route. Supports single elimination, SVG viewer with pan/zoom, customizable themes. Last meaningful commit unclear but actively used. |

**Why Streamlit over React+FastAPI for this project:**
- Personal use only — single user, no concurrency needs
- No auth layer needed
- Python all the way through — no context switching
- `st.session_state` handles bracket pick overrides
- Can render bracket as SVG/HTML using Plotly or custom HTML components
- Time constraint (Selection Sunday 2026) makes simpler architecture lower risk

**Streamlit bracket rendering approach:**
Streamlit does not have a native bracket component. Options:
1. `st.components.v1.html()` — inject a custom HTML/SVG bracket rendered server-side in Python
2. Embed a small React bracket widget as a static component using `streamlit-components`
3. Render bracket as a Plotly figure using nested shapes (custom, more work)

**Recommendation:** Use `st.components.v1.html()` with a self-contained SVG bracket generated in Python. The bracket structure (68 teams, known positions) is fixed enough that a programmatic SVG is feasible.

---

### Bracket Auto-Fetch (Selection Sunday)

| Component | Approach | Confidence |
|-----------|----------|------------|
| Primary: ESPN unofficial API | `GET https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=YYYYMMDD&groups=50` then filter `bracketRound` field | MEDIUM — unofficial, works as of 2025 |
| Fallback: data.ncaa.com | `GET https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{year}/{month}/{day}/scoreboard.json` | MEDIUM — JSON format, has historically been stable |
| Fallback: Manual CSV | Hand-enter 68 teams and seeds from bracket announcement | LOW effort, guaranteed to work |

**Important:** No official, documented, stable API exists for the NCAA tournament bracket. Both ESPN and NCAA.com provide unofficial JSON endpoints that have been used by developers but carry no stability guarantee. **Build the fetcher with graceful fallback to manual CSV entry.** This is a one-time operation per year.

---

### Development Environment

| Technology | Purpose | Why |
|------------|---------|-----|
| uv | Package manager and virtual env | Faster than pip, replaces pip+virtualenv. Modern Python tooling standard as of 2025. |
| Jupyter notebooks | EDA and model development | Standard for iterative ML work. Use for data exploration, feature engineering, model training. |
| pytest | Testing | Standard Python test framework. Test data pipeline and probability calculations. |
| python-dotenv | Config management | Store any API keys (cbbdata) in `.env`. Keep out of version control. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Web UI | Streamlit | React + FastAPI | React requires building a separate frontend, JS build tooling, and a Python API layer. 3x more code for same personal-use result. Only worthwhile if you want a polished public-facing app. |
| Web UI | Streamlit | Dash (Plotly) | Dash has a steeper learning curve than Streamlit. Less community activity. Streamlit has better DX for ML projects. |
| ML gradient boosting | XGBoost + LightGBM | PyTorch neural net | Neural nets are overcomplicated for this domain. Tabular data with ~100 features per matchup. Gradient boosted trees consistently outperform neural nets on tabular sports data. Lower interpretability gain for added complexity. |
| Data storage | DuckDB | PostgreSQL | PostgreSQL requires a running server. This is a local personal project — no server overhead needed. DuckDB is embedded. |
| Data storage | DuckDB | Pure pandas | pandas loads everything into memory. DuckDB queries on-disk Parquet lazily. With 20 years of season data, memory efficiency matters. |
| Data source | CBBpy + cbbdata | hoopR (R package) | hoopR is R-native. Python project should stay in Python. CBBpy provides equivalent ESPN-sourced data. |
| Data source | Kaggle dataset | Building scraper from scratch | Kaggle March Mania dataset has 20+ years of structured tournament data in CSV format. Building an equivalent scraper takes significant time. Use Kaggle for historical backfill, CBBpy for current season. |
| Package manager | uv | pip/conda | conda is heavy and slow. pip without lockfiles leads to reproducibility issues. uv is faster and modern. |
| Bracket visualization | Python SVG via st.components | D3.js | D3 requires full JS/build environment. For a bracket with 67 games and fixed structure, programmatic SVG is sufficient and stays in Python. |

---

## Versions Summary (Verified 2026-03-02)

| Package | Verified Version | Source |
|---------|-----------------|--------|
| Python | 3.12 (recommended) | PyPI constraint analysis |
| XGBoost | 3.2.0 | pypi.org/project/xgboost |
| scikit-learn | 1.8.0 | pypi.org/project/scikit-learn |
| LightGBM | 4.6.0 | pypi.org/project/lightgbm |
| pandas | 3.0.1 | pypi.org/project/pandas |
| DuckDB | 1.4.4 | pypi.org/project/duckdb |
| Streamlit | 1.54.0 | pypi.org/project/streamlit |
| FastAPI | 0.135.1 | pypi.org/project/fastapi (alt only) |
| CBBpy | 2.1.2 | pypi.org/project/CBBpy |

---

## Installation

```bash
# Create virtual environment with uv
uv venv --python 3.12
source .venv/bin/activate

# Data acquisition
uv pip install CBBpy requests beautifulsoup4

# ML stack
uv pip install pandas numpy scikit-learn xgboost lightgbm optuna joblib pyarrow

# Storage
uv pip install duckdb

# Web UI
uv pip install streamlit plotly

# Dev tools
uv pip install jupyter pytest python-dotenv

# Optional: notebook support
uv pip install ipykernel
```

---

## Sources

| Claim | Source | Confidence |
|-------|--------|------------|
| XGBoost version 3.2.0 | https://pypi.org/project/xgboost/ | HIGH |
| scikit-learn version 1.8.0, Python >=3.11 | https://pypi.org/project/scikit-learn/ | HIGH |
| LightGBM version 4.6.0 | https://pypi.org/project/lightgbm/ | HIGH |
| pandas version 3.0.1, Python >=3.11 | https://pypi.org/project/pandas/ | HIGH |
| DuckDB version 1.4.4 | https://pypi.org/project/duckdb/ | HIGH |
| Streamlit version 1.54.0, Python >=3.10 | https://pypi.org/project/streamlit/ | HIGH |
| FastAPI version 0.135.1 | https://pypi.org/project/fastapi/ | HIGH |
| CBBpy version 2.1.2, ESPN-backed | https://pypi.org/project/CBBpy/ | HIGH |
| cbbdata API is free, barttorvik-backed | https://cbbdata.aweatherman.com/articles/release.html | MEDIUM |
| ESPN unofficial API endpoints | https://github.com/pseudo-r/Public-ESPN-API | MEDIUM |
| data.ncaa.com JSON bracket endpoint | Web search, developer community reports | LOW — verify when bracket is published |
| XGBoost/LightGBM commonly used for bracket prediction | https://blog.collegefootballdata.com/talking-tech-march-madness-xgboost/, https://www.kaggle.com/code/sadettinamilverdil/ncaa-basketball-predictions-with-xgboost | MEDIUM |
| Kaggle March Mania 2025 dataset | https://www.kaggle.com/competitions/march-machine-learning-mania-2025/ | HIGH |
| react-tournament-brackets library | https://github.com/g-loot/react-tournament-brackets | MEDIUM — version unclear |
| DuckDB 17x faster than pandas for analytics | https://www.digitalocean.com/community/tutorials/duckdb-complements-pandas-for-large-scale-analytics | MEDIUM |
| barttorvik.com uses Cloudflare bot protection | Direct WebFetch attempt returned "Verifying your browser, please wait..." | HIGH |
