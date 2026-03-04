# Phase 9: Bracket Visualization UI - Research

**Researched:** 2026-03-04
**Domain:** Streamlit application development, SVG bracket layout, programmatic data visualization
**Confidence:** HIGH (Streamlit verified via official docs + PyPI; bracket structure verified against live codebase; slot IDs extracted from live data)

## Summary

Phase 9 builds a Streamlit application (`app.py`) that displays the 68-team NCAA bracket as a programmatic SVG, with per-game win probabilities, a round-by-round advancement table, and a champion panel. The phase depends on the bracket JSON contract from Phase 4 (simulate_bracket() output), model loading from Phase 7 (models/selected.json), and the feature store API from Phase 8 (compute_features name-based API).

Streamlit 1.55.0 is the current stable version (as of March 2026). The bracket SVG must be rendered via `st.components.v1.html()` with an explicit `height` parameter, because the SVG is too large for Streamlit's built-in image rendering. The key architectural challenge is the bracket layout algorithm: the 68-team bracket uses regions W/X/Y/Z (4 regions × 8 R1 slots = 32 first-round games), two Final Four slots (R5WX, R5YZ), and one Championship slot (R6CH). The planner must provide an explicit coordinate system that maps slot IDs to (x, y) pixel positions in the SVG canvas.

The round-by-round advancement table uses `st.dataframe()` with `column_config.ProgressColumn` to show probabilities visually. Streamlit's native `st.dataframe()` supports sorting, search, and download out of the box — no Plotly table is needed. The champion panel is a straightforward `st.metric()` + `st.markdown()` display.

**Primary recommendation:** Use Streamlit 1.55.0 with `st.components.v1.html()` for the SVG bracket, `st.dataframe()` with `ProgressColumn` for the advancement table, `@st.cache_resource` for model loading, and `@st.cache_data` for bracket simulation output. Add `streamlit>=1.42.0` and `plotly>=6.0.0` to pyproject.toml via `uv add`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | >=1.42.0 (latest: 1.55.0) | Web app framework, layout, widgets, session state | Project-specified framework; no alternatives considered |
| plotly | >=6.0.0 (latest: 6.6.0) | Optional: go.Table for styled tables if st.dataframe insufficient | Already in ecosystem; pairs well with Streamlit |
| joblib | already installed | Load TwoTierEnsemble from models/ensemble.joblib | Established project pattern from Phase 7 decision |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | >=3.0.1 (installed) | DataFrame construction for advancement table | Building sortable tables for st.dataframe |
| duckdb | >=1.4.4 (installed) | Read seeds.parquet for team name -> seed label lookups | Bracket data loading (same pattern as bracket_schema.py) |
| base64 | stdlib | Encoding SVG for st.html display alternative | If st.components.v1.html causes height issues |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| st.components.v1.html(svg) | st.html(svg) | st.html is not iframed but uses DOMPurify sanitization which may strip SVG attributes; st.components.v1.html is more reliable for complex inline SVG but requires explicit height |
| st.dataframe with ProgressColumn | plotly go.Table | st.dataframe is sortable/searchable natively; plotly Table cannot sort but has richer styling; use st.dataframe |
| Manual SVG coordinate algorithm | bracketool or react-tournament-brackets | bracketool Python library exists on PyPI but is unmaintained; react-tournament-brackets is JS-only; hand-roll the coordinate algorithm using the documented formula (it is simple geometry, not a "don't hand-roll" case) |

**Installation — add to pyproject.toml:**
```bash
uv add streamlit>=1.42.0 plotly>=6.0.0
```

## Architecture Patterns

### Recommended Project Structure
```
app.py                    # Streamlit entry point (streamlit run app.py)
src/
├── simulator/
│   ├── bracket_schema.py # EXISTING: build_slot_tree(), load_seedings(), ROUND_NAMES
│   └── simulate.py       # EXISTING: simulate_bracket() -> bracket JSON contract
├── models/
│   └── features.py       # EXISTING: compute_features() public API
└── dashboard/
    └── plots.py           # EXISTING: matplotlib plots (not used in Phase 9)
models/
└── selected.json          # EXISTING: {model_artifact_path, model_type, ...}
data/processed/
└── seeds.parquet          # EXISTING: TeamID, TeamName, Seed, Region, SeedNum, IsFirstFour
```

### Pattern 1: Streamlit App Entry Point with set_page_config
**What:** `app.py` must call `st.set_page_config()` as the FIRST Streamlit command. Wide layout is mandatory for a 68-team bracket.
**When to use:** Always — this is the only valid pattern.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/configuration/st.set_page_config
import streamlit as st

st.set_page_config(
    page_title="March Madness 2025 Predictions",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

### Pattern 2: Model Loading with st.cache_resource
**What:** The TwoTierEnsemble model is a global singleton — expensive to load, shared across reruns. Use `@st.cache_resource`.
**When to use:** Any time you load a joblib/pickle model artifact.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource
import json
import joblib
import streamlit as st

@st.cache_resource
def load_model():
    """Load TwoTierEnsemble from models/selected.json -> model_artifact_path."""
    with open("models/selected.json") as f:
        meta = json.load(f)
    return joblib.load(meta["model_artifact_path"]), meta

ensemble, model_meta = load_model()
```

### Pattern 3: Bracket Simulation with st.cache_data
**What:** `simulate_bracket()` output is deterministic given the same model + seedings. Cache it as data (not resource) so reruns don't resimulate.
**When to use:** Any expensive computation that returns serializable output (dict, DataFrame).
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
@st.cache_data
def run_simulation(_predict_fn, _seedings, season=2025):
    """Cache bracket simulation output. Underscore prefix makes params unhashable-safe."""
    from src.simulator.simulate import simulate_bracket
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="deterministic",
        season=season,
    )
```

### Pattern 4: SVG Bracket Layout — Coordinate Algorithm
**What:** Map each slot_id to (x, y) pixel coordinates in the SVG canvas. The bracket has 4 regions (W, X, Y, Z), each with 8 R1 slots, narrowing to 4/2/1 slots per subsequent round.
**When to use:** This IS the core engineering challenge of Plan 09-02.

**Bracket structure facts (verified against live data):**
- First Four slots: `W16`, `X11`, `Y11`, `Y16` (4 play-in games)
- R1 slots: `R1W1`–`R1W8`, `R1X1`–`R1X8`, `R1Y1`–`R1Y8`, `R1Z1`–`R1Z8` (32 games)
- R2 slots: `R2W1`–`R2W4`, `R2X1`–`R2X4`, `R2Y1`–`R2Y4`, `R2Z1`–`R2Z4` (16 games)
- R3 slots: `R3W1`–`R3W2`, `R3X1`–`R3X2`, `R3Y1`–`R3Y2`, `R3Z1`–`R3Z2` (8 games)
- R4 slots: `R4W1`, `R4X1`, `R4Y1`, `R4Z1` (4 Elite Eight games)
- R5 slots: `R5WX` (W vs X Final Four semi), `R5YZ` (Y vs Z Final Four semi)
- R6 slot: `R6CH` (Championship)

**Layout convention — 4-panel design:**
```
Left half:          Center:       Right half:
[W region] [X region] [FINAL FOUR] [Y region] [Z region]
R1->R4     R1->R4      R5WX R5YZ   R4<-R1     R4<-R1
                       R6CH
```
Regions W and X bracket together on the left half; regions Y and Z bracket together on the right half.

**Coordinate formula (from Toornament developer guide — verified):**
```python
# Source: https://developer.toornament.com/v2/guides/display-bracket
# For a region traversed left-to-right (W, X left half):
# x increases with round number (R1 leftmost, R4 rightmost before FF)
# y increases with slot number within round

SLOT_HEIGHT = 60   # pixels per game slot
SLOT_WIDTH = 160   # pixels per game box (team names + prob)
ROUND_GAP = 40     # horizontal gap between rounds

def slot_x(round_num: int, region_panel: str) -> int:
    """Return left-edge pixel x for a given round in a given panel."""
    # Left half (W, X): round 1 at left, round 4 at center
    # Right half (Y, Z): round 4 at center, round 1 at right (mirrored)
    ...

def slot_y(slot_num: int, round_num: int) -> int:
    """Return top-edge pixel y for a given slot in a given round."""
    # Slots in later rounds are spaced 2x further apart (tree structure)
    spacing = SLOT_HEIGHT * (2 ** (round_num - 1))
    offset = spacing // 2 - SLOT_HEIGHT // 2  # center in spacing
    return slot_num * spacing + offset
```

**Connector lines:** Use SVG `<polyline>` or `<path>` elements connecting parent-child slot boxes with L-shaped horizontal/vertical lines.

### Pattern 5: SVG Rendering via st.components.v1.html
**What:** Render the complete SVG string inside an iframe. Must specify explicit `height` or content is clipped at 150px default.
**When to use:** Any time you need to render custom HTML/SVG with more than trivial size.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v1.html
import streamlit.components.v1 as components

def render_bracket_svg(svg_string: str, height: int = 900) -> None:
    """Render SVG bracket in a scrollable iframe."""
    html = f"""
    <html>
    <body style="margin:0; background:#0e1117;">
    {svg_string}
    </body>
    </html>
    """
    components.html(html, height=height, scrolling=True)
```

### Pattern 6: Advancement Table with ProgressColumn
**What:** Display P(team reaches round) as a sortable, searchable table with visual progress bars.
**When to use:** Plan 09-04 round-by-round advancement table.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/data/st.column_config/st.column_config.progresscolumn
import pandas as pd
import streamlit as st

def render_advancement_table(advancement_probs: dict) -> None:
    """Render sortable advancement probability table."""
    rows = []
    for team_id, probs in advancement_probs.items():
        row = {"Team": team_id_to_name[team_id], "Seed": team_seed_map[team_id]}
        row.update(probs)  # Round of 64, Round of 32, ..., Champion
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("Champion", ascending=False)

    round_cols = ["Round of 64", "Round of 32", "Sweet 16", "Elite 8",
                  "Final Four", "Championship", "Champion"]

    column_config = {
        col: st.column_config.ProgressColumn(
            col,
            format="%.1f%%",
            min_value=0.0,
            max_value=1.0,
        )
        for col in round_cols if col in df.columns
    }

    st.dataframe(
        df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
    )
```

### Pattern 7: Session State Initialization
**What:** Initialize session state keys at app startup to avoid KeyError on first rerun.
**When to use:** Any time the app has user-controllable state (sidebar model selector, display mode).
**Example:**
```python
# Source: https://docs.streamlit.io/develop/concepts/architecture/session-state
if "simulation_result" not in st.session_state:
    st.session_state.simulation_result = None
if "season" not in st.session_state:
    st.session_state.season = 2025
```

### Recommended App Structure (app.py)
```python
# app.py — single-file entry point
st.set_page_config(...)         # MUST be first

# Sidebar
with st.sidebar:
    st.header("Configuration")
    season = st.selectbox("Season", [2025])
    st.caption(f"Model: {model_meta['selected_model']}")
    st.caption(f"Brier: {model_meta['mean_brier']:.4f}")

# Load data (cached)
ensemble, model_meta = load_model()
seedings, predict_fn = load_seedings_and_predict_fn(ensemble, season)
det_result = run_simulation(predict_fn, seedings, season)  # deterministic
mc_result = run_mc_simulation(predict_fn, seedings, season)  # monte carlo

# Tabs layout
tab1, tab2, tab3 = st.tabs(["Bracket", "Advancement Table", "Champion"])

with tab1:
    render_bracket_svg(det_result)

with tab2:
    render_advancement_table(mc_result["advancement_probs"])

with tab3:
    render_champion_panel(mc_result, det_result)
```

### Anti-Patterns to Avoid
- **Calling `st.set_page_config()` after any other Streamlit command:** This raises a StreamlitAPIException. It must be the first call.
- **Using `@st.cache_data` for the model object:** Models are mutable singletons — use `@st.cache_resource` to avoid per-session copies.
- **Forgetting `height=` on components.html():** Default height is 150px; the SVG bracket will be invisible or badly clipped without explicit height.
- **Parametrizing cache_data functions with unhashable args (like model objects):** Use underscore-prefixed parameter names (`_predict_fn`) to tell Streamlit not to hash them.
- **Hard-coding team IDs as display names:** Use seeds.parquet (TeamName column) for human-readable names.
- **Running `simulate_bracket()` on every rerun:** Wrap it in `@st.cache_data`; simulation takes several seconds.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sortable probability table | Custom HTML/JS table | st.dataframe with ProgressColumn | Native sorting, search, download; zero custom code |
| Model caching across reruns | Module-level global variable | @st.cache_resource | Handles thread safety, invalidation, and TTL properly |
| Data caching | Module-level dict | @st.cache_data | Handles serialization, per-session copies, and TTL |
| Team name lookup | Custom name dict in app.py | data/processed/seeds.parquet via duckdb | Already built in Phase 2; TeamName column maps team_id -> display name |
| Bracket slot structure | Custom slot tree | src.simulator.bracket_schema.build_slot_tree() | Already built in Phase 4; use the existing API |
| Predict function | Raw model.predict_proba() calls | src.simulator.bracket_schema.build_predict_fn() | Handles seed ordering, scaler, feature names |

**Key insight:** The SVG coordinate layout algorithm IS hand-rolled — this is appropriate because it is simple geometry (see formula above), and no Python library produces a correctly shaped 68-team NCAA bracket with the W/X/Y/Z region + Final Four layout. The formula is 20 lines of Python.

## Common Pitfalls

### Pitfall 1: Height Clipping in st.components.v1.html
**What goes wrong:** The bracket SVG appears as a thin 150px strip; teams and game boxes are invisible.
**Why it happens:** `st.components.v1.html()` defaults to height=150px. The SVG for a 68-team bracket with 8 R1 slots per region needs roughly 800–1200px of height.
**How to avoid:** Always pass explicit `height=` to components.html(). Calculate height from `n_rows * SLOT_HEIGHT + PADDING` before rendering.
**Warning signs:** Bracket renders but only shows the first few games; scroll doesn't reveal more content even with `scrolling=True`.

### Pitfall 2: st.cache_data with Unhashable Parameters
**What goes wrong:** `TypeError: unhashable type: 'TwoTierEnsemble'` when passing the model to a @st.cache_data function.
**Why it happens:** `@st.cache_data` tries to hash all function arguments to create a cache key. `TwoTierEnsemble` (a complex sklearn-based object) is not hashable.
**How to avoid:** Prefix unhashable parameters with underscore: `def run_simulation(_predict_fn, _seedings, season)`. Streamlit will skip hashing underscored params.
**Warning signs:** Error on first app load, not on rerun.

### Pitfall 3: set_page_config Called Too Late
**What goes wrong:** `StreamlitAPIException: `set_page_config()` can only be called once per app page, and must be called as the first Streamlit command in your script.`
**Why it happens:** Any import that calls st.something() (like importing a helper that renders UI) before set_page_config runs.
**How to avoid:** Put `st.set_page_config()` on lines 1-5 of app.py, before any other Streamlit calls or imports of modules that make Streamlit calls.
**Warning signs:** App crashes immediately on load with StreamlitAPIException.

### Pitfall 4: Monte Carlo Advancement Probs Missing Teams
**What goes wrong:** Advancement table only shows ~30 teams instead of 68; 38 teams with zero advancement probability are silently dropped.
**Why it happens:** `simulate_bracket()` monte carlo mode only includes teams in `advancement_probs` if `round_counts` is non-empty. First Four losers appear in zero slots after FF, so they have no entries.
**How to avoid:** When building the advancement table DataFrame, start from all 68 seedings and LEFT JOIN with advancement_probs. Teams with no entry get 0.0 for all round probabilities.
**Warning signs:** Advancement table has fewer rows than expected; First Four participants (seeds 11, 16) are missing.

### Pitfall 5: Team Name Display Using team_id Instead of TeamName
**What goes wrong:** Bracket shows numeric IDs like "1181", "1222" instead of "Duke", "Houston".
**Why it happens:** `simulate_bracket()` returns team_id integers. The display layer must translate IDs to names.
**How to avoid:** Build a `team_id_to_name: dict[int, str]` from seeds.parquet at startup:
```python
# Verified: seeds.parquet has TeamID, TeamName, Seed columns
df = duckdb.connect().execute(
    f"SELECT TeamID, TeamName, Seed FROM read_parquet('data/processed/seeds.parquet') WHERE Season={season}"
).df()
team_id_to_name = dict(zip(df.TeamID, df.TeamName))
team_id_to_seed = dict(zip(df.TeamID, df.Seed))
```
**Warning signs:** Bracket slots show 4-digit integers instead of team names.

### Pitfall 6: SVG Connector Lines Not Connecting Slots
**What goes wrong:** SVG game boxes render correctly but have no lines connecting parent to child games; bracket looks like a disconnected grid.
**Why it happens:** Connector lines must be drawn separately using the slot tree's parent-child relationships. `simulate_bracket()` only returns winners per slot, not the tree structure.
**How to avoid:** Call `build_slot_tree()` separately to get the StrongSeed/WeakSeed parent relationships. For each slot, draw an L-shaped `<path>` from its right edge to its parent's left input point.
**Warning signs:** Game boxes appear but float in isolation; bracket structure is not visually apparent.

### Pitfall 7: Streamlit Rerun Resimulates the Bracket
**What goes wrong:** Every user interaction (click, scroll, hover) triggers a full rerun that calls `simulate_bracket()`, making the app take 5-10 seconds to respond.
**Why it happens:** Streamlit reruns the entire script on any widget interaction. Without caching, simulate_bracket() runs every time.
**How to avoid:** Wrap all expensive computations in `@st.cache_data`. The cache key includes `(season,)` so season changes correctly invalidate the cache.
**Warning signs:** App feels sluggish on every interaction; console shows repeated "Simulating bracket..." log messages.

## Code Examples

Verified patterns from official sources:

### Loading model per Phase 7 contract
```python
# Pattern from prior decision [07-03]: models/selected.json -> model_artifact_path -> joblib.load()
import json
import joblib
import streamlit as st

@st.cache_resource
def load_ensemble():
    with open("models/selected.json") as f:
        meta = json.load(f)
    # meta["model_artifact_path"] = "models/ensemble.joblib"
    # meta["model_type"] = "TwoTierEnsemble"
    ensemble = joblib.load(meta["model_artifact_path"])
    return ensemble, meta
```

### Building predict_fn for the ensemble
```python
# Phase 9 must use bracket_schema.build_predict_fn() adapted for TwoTierEnsemble
# The existing build_predict_fn() only supports logistic baseline.
# For TwoTierEnsemble, the pattern from Phase 6 backtest.py is:
from src.models.features import _compute_features_by_id, build_stats_lookup, FEATURE_COLS
import numpy as np

@st.cache_resource
def build_ensemble_predict_fn(_ensemble, season=2025):
    stats_lookup = build_stats_lookup("data/processed")
    scaler = _ensemble.scaler  # TwoTierEnsemble stores the scaler

    def predict_fn(team_a_id: int, team_b_id: int) -> float:
        features = _compute_features_by_id(season, team_a_id, team_b_id, stats_lookup)
        x = np.array([[features[col] for col in FEATURE_COLS]])
        x_scaled = scaler.transform(x)
        prob = _ensemble.predict_proba(x_scaled)[0, 1]
        return float(np.clip(prob, 0.0, 1.0))

    return predict_fn
```

### SVG Game Box Element
```python
def svg_game_box(x: int, y: int, w: int, h: int, team_name: str,
                 seed: int, win_prob: float, is_winner: bool = False) -> str:
    """Render a single game slot as SVG group."""
    fill = "#1e3a5f" if is_winner else "#1a1a2e"
    text_color = "#ffffff"
    prob_pct = f"{win_prob:.0%}"
    seed_label = f"({seed})"
    return f"""
    <g>
      <rect x="{x}" y="{y}" width="{w}" height="{h}"
            fill="{fill}" stroke="#4a90d9" stroke-width="1" rx="3"/>
      <text x="{x+8}" y="{y+14}" fill="{text_color}" font-size="10"
            font-family="monospace">{seed_label}</text>
      <text x="{x+35}" y="{y+14}" fill="{text_color}" font-size="10"
            font-family="monospace" clip-path="url(#clip{x}{y})">{team_name}</text>
      <text x="{x+w-4}" y="{y+14}" fill="#4ec9b0" font-size="10"
            font-family="monospace" text-anchor="end">{prob_pct}</text>
    </g>
    """
```

### Session State Initialization Pattern
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
def init_session_state():
    defaults = {
        "season": 2025,
        "show_ff": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
```

### Advancement Table Build Pattern
```python
def build_advancement_df(mc_result: dict, team_id_to_name: dict,
                         team_id_to_seed: dict, all_team_ids: list) -> pd.DataFrame:
    """Build advancement probability DataFrame from Monte Carlo result.
    Includes all 68 teams with 0.0 for teams that didn't advance."""
    round_cols = ["Round of 64", "Round of 32", "Sweet 16",
                  "Elite 8", "Final Four", "Championship", "Champion"]
    rows = []
    adv = mc_result.get("advancement_probs", {})
    for team_id in all_team_ids:
        probs = adv.get(team_id, {})
        row = {
            "Team": team_id_to_name.get(team_id, str(team_id)),
            "Seed": team_id_to_seed.get(team_id, 99),
        }
        for col in round_cols:
            row[col] = probs.get(col, 0.0)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("Champion", ascending=False)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `st.cache` (deprecated) | `@st.cache_resource` / `@st.cache_data` | Streamlit 1.18+ | Use correct decorator based on data vs resource |
| `use_container_width=True` in st.plotly_chart | `width="stretch"` | Streamlit 1.54+ | Old param still works but deprecated |
| `st.beta_columns()` | `st.columns()` | Streamlit 1.0+ | beta_ prefix removed years ago |

**Deprecated/outdated:**
- `st.cache`: Replaced by `@st.cache_data` and `@st.cache_resource`. Do not use.
- `components.v1.html` imported directly (not via module): Now generates a deprecation warning. Use `import streamlit.components.v1 as components; components.html(...)` instead.

## Open Questions

1. **predict_fn adapter for TwoTierEnsemble**
   - What we know: `build_predict_fn()` in bracket_schema.py only wraps the logistic baseline model (ClippedCalibrator/StandardScaler pattern). TwoTierEnsemble has its own `scaler` attribute and `predict_proba()` interface (verified from ensemble.py).
   - What's unclear: Does the app need a new `build_ensemble_predict_fn()` helper in bracket_schema.py or in app.py directly? Phase 7 decision [07-03] says "load models/selected.json -> read model_artifact_path -> joblib.load() to get TwoTierEnsemble instance" but doesn't specify the predict_fn adapter.
   - Recommendation: Plan 09-01 must implement the adapter directly in app.py (or a new `src/simulator/predict_adapter.py`). The code pattern is documented in Code Examples above.

2. **SVG canvas dimensions for 68-team bracket**
   - What we know: 4 regions × 8 R1 games = 32 first-round slots. The bracket height grows with n_slots_per_region × SLOT_HEIGHT.
   - What's unclear: The exact canvas width and height to pass to `components.html(height=?)`. This must be computed by the layout algorithm.
   - Recommendation: Use SLOT_HEIGHT=50, SLOT_WIDTH=150, ROUND_GAP=30. Compute total canvas height as `8 * SLOT_HEIGHT * 2 + padding` for each region panel. Expect ~900px height for a legible layout.

3. **First Four slot positioning**
   - What we know: FF slots are `W16`, `X11`, `Y11`, `Y16`. These appear BEFORE the R1 slots in topological order.
   - What's unclear: Where visually they appear in the bracket — they feed into specific R1 slots (e.g., `W16` feeds into `R1W8`).
   - Recommendation: Position FF slots as a "pre-round" column to the left of R1. They are smaller boxes connected to the R1 slot they feed. This is a layout detail for Plan 09-02.

## Sources

### Primary (HIGH confidence)
- Official Streamlit docs v1.54.0 - `st.components.v1.html` API, `st.session_state`, `st.cache_resource`, `st.cache_data`, `st.set_page_config`, `st.dataframe`, `st.column_config.ProgressColumn`
- PyPI JSON API - Streamlit 1.55.0 current version; Plotly 6.6.0 current version
- Live codebase inspection - `src/simulator/bracket_schema.py`, `src/simulator/simulate.py`, `src/models/ensemble.py`, `src/models/features.py`
- Live data query - `data/processed/seeds.parquet` season=2025: 68 teams, regions W/X/Y/Z, TeamName column confirmed
- `models/selected.json` - verified structure: `{selected_model, model_artifact_path, model_type: TwoTierEnsemble}`

### Secondary (MEDIUM confidence)
- Toornament developer guide - bracket coordinate algorithm (in-order tree traversal, x=depth, y=visit order) — confirmed the general formula; specific pixel values are project-specific
- Streamlit community discussion — `components.html` height default 150px, must specify explicit height for large SVG content (multiple community posts agree)

### Tertiary (LOW confidence)
- WebSearch results on SVG bracket layout — general pattern confirmed but no NCAA-specific 68-team coordinate examples found; the coordinate algorithm is straightforward enough to implement without a library

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Streamlit 1.55.0 and Plotly 6.6.0 verified on PyPI; installation pattern via `uv add` verified
- Architecture: HIGH — Streamlit API verified from official docs; bracket slot structure verified from live codebase and data
- Pitfalls: HIGH — Streamlit height clipping and cache patterns verified from official docs; team name pitfall verified from live seeds.parquet inspection; other pitfalls from official API behavior

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (Streamlit releases frequently but APIs are stable)
