# Phase 10: Interactive Override UI - Research

**Researched:** 2026-03-04
**Domain:** Streamlit session_state, SVG interaction workarounds, bracket simulation with override_map
**Confidence:** HIGH

## Summary

Phase 10 adds user-driven bracket overrides to the existing Phase 9 Streamlit app. The core challenge is Streamlit's architecture: the SVG bracket rendered via `st.components.v1.html()` lives in an iframe that cannot send click events back to Python. There is no native way to click a game box in the SVG and trigger a Python callback. The standard solution used in production Streamlit apps is a widget-based workaround: render per-game `st.selectbox` dropdowns (or `st.button` pairs) outside the SVG alongside it, letting the user choose the winner for each game. These widgets write to `st.session_state["override_map"]`, which triggers Streamlit rerun, which re-calls `simulate_bracket()` with the updated override map, and re-renders the SVG with the new results.

The existing simulator (`simulate_bracket()`) already accepts `override_map: dict[str, int]` and fully propagates forced winners downstream — no simulator changes are needed for Phase 10. The data_loader.py functions `run_deterministic()` and `run_monte_carlo()` need `override_map` parameters added so that the cached results reflect the overrides. The cache invalidation strategy is to convert the `override_map` dict to a hashable representation via `hash_funcs={dict: lambda d: str(sorted(d.items()))}`.

The UX approach for 67 game slots is to expose override controls in a collapsible panel or sidebar (not inline with the SVG, since the SVG is in an iframe). A clean structure: show the SVG bracket for visual reference, and in an expandable "Override Picks" section or in the sidebar, provide per-slot `st.selectbox` widgets for a round of interest, pre-populated with the model's predicted winner but allowing the user to switch. A "Reset to model picks" `st.button` clears `st.session_state["override_map"]` and reruns.

**Primary recommendation:** Use `st.selectbox` per game slot for override input, writing choices to `st.session_state["override_map"]`, re-running both deterministic (for bracket display) and Monte Carlo (for advancement probabilities) simulations with the updated override map using `hash_funcs`-enabled cache_data functions. Do NOT attempt SVG click event capture via custom components.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | 1.55.0 (installed) | Session state, widgets, re-render orchestration | Already installed; no alternatives |
| streamlit session_state | built-in | Persist override_map across reruns within session | Only mechanism to survive Streamlit reruns |
| simulate_bracket() | existing code | Accepts override_map, propagates overrides downstream | Already built and tested in Phase 4 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| src.simulator.bracket_schema.build_slot_tree() | existing | Get slot StrongSeed/WeakSeed references for selectbox option labels | Need team names for each slot's two competing teams |
| st.cache_data with hash_funcs | built-in | Cache simulation results keyed by override_map content | Override map dict must be hashable for correct cache invalidation |
| src.ui.data_loader run_deterministic / run_monte_carlo | existing | Re-run simulation with override_map parameter | Already call simulate_bracket; need override_map parameter added |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| st.selectbox per slot | SVG click events via custom component | Custom component requires Node.js/TypeScript build toolchain; 2-3x more complexity; no net UX gain |
| st.selectbox per slot | window.parent.postMessage from iframe JS | Fragile hack; depends on Streamlit internal message routing; breaks across Streamlit versions |
| st.selectbox per slot | streamlit-javascript library | Third-party library; adds dependency; same iframe communication limitations |
| Show all 67 slot dropdowns | Show only slots with active overrides + expandable by round | Better UX; 67 dropdowns at once is overwhelming |

**No new installation required** — all needed libraries are already installed.

## Architecture Patterns

### Recommended Project Structure
```
app.py                         # Modified: add override_map session_state init;
                               #           pass override_map to run_deterministic/run_monte_carlo
src/ui/
├── data_loader.py             # Modified: add override_map param to run_deterministic, run_monte_carlo
├── bracket_svg.py             # Modified: highlight overridden slots visually
├── bracket_layout.py          # No changes
├── advancement_table.py       # No changes
└── override_controls.py       # NEW: build_override_controls() renders per-slot selectboxes
```

### Pattern 1: Override Map Session State Initialization
**What:** Initialize and access `st.session_state["override_map"]` at app startup. This dict maps `slot_id -> team_id` for user-forced winners.
**When to use:** app.py, at the top after data is loaded.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
# Initialize once per session
if "override_map" not in st.session_state:
    st.session_state["override_map"] = {}

# Access current overrides
override_map: dict[str, int] = st.session_state["override_map"]
```

### Pattern 2: Override-Aware Simulation with hash_funcs Cache Invalidation
**What:** Pass override_map to simulation functions and use `hash_funcs` to make the dict hashable for correct cache invalidation.
**When to use:** data_loader.py — the two cached simulation functions.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
@st.cache_data(hash_funcs={dict: lambda d: str(sorted(d.items()))})
def run_deterministic(
    _predict_fn,
    _seedings: dict,
    season: int = 2025,
    override_map: dict | None = None,
) -> dict:
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="deterministic",
        season=season,
        override_map=override_map or None,
    )

@st.cache_data(hash_funcs={dict: lambda d: str(sorted(d.items()))})
def run_monte_carlo(
    _predict_fn,
    _seedings: dict,
    season: int = 2025,
    n_runs: int = 10000,
    seed: int = 42,
    override_map: dict | None = None,
) -> dict:
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="monte_carlo",
        n_runs=n_runs,
        seed=seed,
        season=season,
        override_map=override_map or None,
    )
```

### Pattern 3: Per-Slot Selectbox Widget with Callback
**What:** For each overrideable slot, render a `st.selectbox` with `[model_pick, other_team]` as options. A callback writes the selection to `st.session_state["override_map"]`.
**When to use:** `src/ui/override_controls.py`, called within the bracket tab or in a sidebar section.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/widgets/st.selectbox
def _make_override_callback(slot_id: str, selectbox_key: str):
    """Return a callback that updates override_map from the selectbox value."""
    def callback():
        selected = st.session_state[selectbox_key]
        # selected is a team_id (int) or None (model pick)
        if selected is None:
            # Remove override for this slot
            st.session_state["override_map"].pop(slot_id, None)
        else:
            st.session_state["override_map"][slot_id] = selected
    return callback

def render_slot_override(
    slot_id: str,
    strong_team_id: int,
    weak_team_id: int,
    model_winner_id: int,
    team_id_to_name: dict[int, str],
    team_id_to_seednum: dict[int, int],
):
    """Render a selectbox for overriding one game slot's winner."""
    current_override = st.session_state["override_map"].get(slot_id)

    strong_name = f"({team_id_to_seednum.get(strong_team_id,'?')}) {team_id_to_name.get(strong_team_id, str(strong_team_id))}"
    weak_name = f"({team_id_to_seednum.get(weak_team_id,'?')}) {team_id_to_name.get(weak_team_id, str(weak_team_id))}"

    # options: (display_label, team_id)
    options = [
        ("Model pick", None),     # None = follow model
        (strong_name, strong_team_id),
        (weak_name, weak_team_id),
    ]

    # Find current index
    current_idx = 0
    if current_override is not None:
        for i, (_, tid) in enumerate(options):
            if tid == current_override:
                current_idx = i
                break

    key = f"override_{slot_id}"
    label_txt = f"{slot_id}: {strong_name} vs {weak_name}"
    selectbox_key = key

    st.selectbox(
        label_txt,
        options=options,
        format_func=lambda opt: opt[0],  # display label only
        index=current_idx,
        key=selectbox_key,
        on_change=_make_override_callback(slot_id, selectbox_key),
    )
```

### Pattern 4: SVG Visual Feedback for Overridden Slots
**What:** Modify `render_bracket_svg_string()` to render overridden game boxes with a distinct fill color (e.g., amber/gold) so users can visually distinguish their manual picks from model picks.
**When to use:** `src/ui/bracket_svg.py` — `_svg_game_box()` already receives `overridden` flag from `det_result["slots"][slot_id]["overridden"]`.
**Example:**
```python
# Source: existing bracket_svg.py — already passes is_champion; extend to is_overridden
BOX_FILL_OVERRIDDEN = "#3a2a00"   # dark amber — distinguishes manual picks
BOX_STROKE_OVERRIDDEN = "#f5a623"  # bright amber border for overridden slots

# In _svg_game_box(), add overridden param:
if is_overridden:
    fill = BOX_FILL_OVERRIDDEN
    stroke = BOX_STROKE_OVERRIDDEN
elif is_champion:
    fill = BOX_FILL_CHAMPION
    stroke = BOX_STROKE
else:
    fill = BOX_FILL_NORMAL
    stroke = BOX_STROKE
```

### Pattern 5: Reset to Model Picks Button
**What:** A single `st.button` clears `st.session_state["override_map"]` via an `on_click` callback.
**When to use:** Displayed prominently near the override controls section.
**Example:**
```python
# Source: https://docs.streamlit.io/develop/concepts/design/buttons
def _reset_overrides():
    st.session_state["override_map"] = {}

st.button(
    "Reset to model picks",
    on_click=_reset_overrides,
    type="secondary",
    help="Clear all manual overrides and restore ensemble model predictions",
)
```

### Pattern 6: Override Controls Layout — Round-Grouped Expanders
**What:** Group override controls by round within `st.expander` sections. This avoids showing 67 dropdowns at once. Default state: first round collapsed, all rounds collapsed until user expands. Show a badge indicating how many active overrides exist per round.
**When to use:** `override_controls.py` — the main `build_override_controls()` function.
**Example:**
```python
# Display override controls grouped by round name
OVERRIDE_ROUNDS = [
    ("Round of 64",  [f"R1W{i}" for i in range(1,9)] + [f"R1X{i}" for i in range(1,9)] + [...]),
    ("Round of 32",  [...]),
    ("Sweet 16",     [...]),
    ("Elite 8",      [...]),
    ("Final Four",   ["R5WX", "R5YZ"]),
    ("Championship", ["R6CH"]),
]

for round_name, slot_ids in OVERRIDE_ROUNDS:
    n_active = sum(1 for sid in slot_ids if sid in st.session_state["override_map"])
    label = f"{round_name}" + (f" ({n_active} overrides)" if n_active else "")
    with st.expander(label, expanded=False):
        for slot_id in slot_ids:
            # render selectbox for this slot
            render_slot_override(slot_id, ...)
```

### Anti-Patterns to Avoid
- **SVG click events via components.html:** `st.components.v1.html()` renders in an iframe with no return channel to Python. Do not attempt this.
- **Custom component with Node.js/TypeScript for SVG clicks:** Valid technically but requires build toolchain, external dependencies, and 3-5x more implementation complexity with no UX advantage over selectbox-based approach.
- **Mutating `st.session_state["override_map"]` dict inline (not in callback):** Streamlit reruns from top to bottom; mutations must happen inside `on_change`/`on_click` callbacks (which execute before the rerun) to be visible during the same rerun.
- **Passing `override_map={}` vs `override_map=None`:** Passing an empty dict `{}` to `simulate_bracket()` causes the override validation code to run but finds nothing to validate — that's fine. But passing `None` skips validation entirely. Normalize to `None` when override_map is empty to preserve the clean code path in simulator.
- **Caching override-aware simulation without hash_funcs:** Without `hash_funcs={dict: ...}`, Streamlit will attempt to hash the dict (may fail or use default dict identity hashing, which never invalidates on content change). Always use `hash_funcs` when the dict IS a cache-key argument (not underscore-prefixed).
- **Showing 67 selectboxes unconditionally:** This makes the UI unusable. Use round-grouped `st.expander` to keep the interface clean.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bracket click-to-override | SVG onclick + postMessage custom Streamlit component | st.selectbox widgets | Selectbox gives native Streamlit behavior, correct session_state integration, instant rerun — no build toolchain |
| Override persistence across reruns | Writing overrides to a file | st.session_state["override_map"] | Session state is Streamlit's designed persistence mechanism; file-based is fragile and session-unaware |
| Cache invalidation for override_map | Custom cache key string construction | hash_funcs={dict: ...} param on @st.cache_data | Official mechanism; handles edge cases (empty dict vs None) correctly |
| Override validation | Re-implement slot ID and team ID checks | simulate_bracket() override_map validation | Already implemented in Phase 4 (04-05); raises ValueError for invalid entries |
| Visual override indicator | Custom SVG rendering pipeline | det_result["slots"][slot_id]["overridden"] flag (already in API) + fill color in _svg_game_box() | Phase 4 simulator already marks overridden=True per slot; just use that flag in SVG rendering |

**Key insight:** The entire override propagation system is already built in Phase 4. Phase 10 only needs to: (1) wire up session_state to store the user's choices, (2) pass those choices to the cached simulation functions, and (3) make the SVG visually indicate which slots are overridden.

## Common Pitfalls

### Pitfall 1: SVG Click Events Not Reaching Python
**What goes wrong:** Developer tries to add `onclick` handler to SVG `<rect>` elements and read the click in Python. Nothing happens.
**Why it happens:** `st.components.v1.html()` renders content in an iframe, which is isolated from Streamlit's Python runtime. JavaScript events cannot directly trigger Python callbacks.
**How to avoid:** Use the selectbox-based approach. The SVG is display-only. Controls live as native Streamlit widgets outside the iframe.
**Warning signs:** onclick handlers defined in SVG but no Python state changes occur when clicking.

### Pitfall 2: Override Map Not Invalidating Cache
**What goes wrong:** User changes an override via selectbox, rerun triggers, but `run_deterministic()` returns the old cached result because the dict is not re-hashed correctly.
**Why it happens:** Streamlit's default dict hashing uses object identity, not content. Passing the same dict object mutated in session_state does not change the hash.
**How to avoid:**
- Pass `override_map` as a parameter (not the dict from session_state directly); use `hash_funcs={dict: lambda d: str(sorted(d.items()))}`.
- Alternatively: pass `tuple(sorted(override_map.items()))` as the argument instead of the raw dict (tuples are natively hashable).
**Warning signs:** Changing override via selectbox and re-rendering shows same bracket result as before the override.

### Pitfall 3: Override Selectbox Loses Its Value on Rerun
**What goes wrong:** User selects an override team from selectbox, page reruns, selectbox shows "Model pick" again (reverts to default).
**Why it happens:** Streamlit selectboxes reset to default `index=0` on each rerun unless the current value is read from session_state and the `index` is explicitly set.
**How to avoid:** In `render_slot_override()`, look up the current override from `st.session_state["override_map"].get(slot_id)` and set `index=` to the matching option index.
**Warning signs:** Override selectbox immediately reverts on every rerun; bracket never shows overridden state.

### Pitfall 4: Passing Empty Dict `{}` vs `None` to simulate_bracket()
**What goes wrong:** `simulate_bracket(override_map={})` triggers override validation code (builds slot tree, validates keys/teams) even though there are no overrides. This is a minor performance hit but not a bug.
**Why it happens:** Simulator validation code runs for any non-None override_map.
**How to avoid:** Normalize: `override_map=st.session_state["override_map"] or None`. The `or None` coerces empty dict to None, skipping validation.
**Warning signs:** Simulation is slightly slower than expected when no overrides are active.

### Pitfall 5: Monte Carlo With Override is Slow for Large n_runs
**What goes wrong:** After each override change, the Monte Carlo re-runs 10,000 simulations. With cache invalidation on every selectbox change, the UI feels sluggish (~0.2s per rerun, but users notice if tab-switching).
**Why it happens:** The override_map changes the cache key, so Monte Carlo can't use the cached pre-override result.
**How to avoid:** The cache_data mechanism handles this correctly (the new result IS cached for subsequent reruns with the same override). The first rerun after an override is necessarily slow. Consider n_runs=5000 for override mode (acceptable confidence; faster refresh) — but this is a UX tuning decision, not a bug.
**Warning signs:** UI noticeably slow after each override change; Monte Carlo running time logged each time.

### Pitfall 6: override_map dict Mutation Happens Outside Callback
**What goes wrong:** Developer writes `st.session_state["override_map"][slot_id] = team_id` inline in the app script (not inside a callback). This runs on every rerun, masking earlier changes.
**Why it happens:** Streamlit reruns the script top-to-bottom on every widget interaction. Inline dict mutations that run unconditionally overwrite the state set by the previous interaction.
**How to avoid:** Always mutate `st.session_state["override_map"]` inside `on_change` or `on_click` callbacks only. Callbacks run BEFORE the rerun and their side effects (session_state mutations) are visible in that rerun.
**Warning signs:** Override "sticks" for one rerun then resets; selectbox appears to work visually but bracket doesn't update.

### Pitfall 7: Team Reference Not Resolvable After Override
**What goes wrong:** User overrides slot R3W1 with a team that didn't win R2W1 in the model's deterministic output. `_resolve_slot_teams()` in `bracket_svg.py` looks up `det_result["slots"]["R2W1"]["team_id"]` to find the teams competing in R3W1 — but after the override, the det_result is recalculated and the "competing teams" for R3W1 may have changed.
**Why it happens:** The SVG rendering resolves which two teams compete in a slot by tracing upstream through the slot tree. If an upstream slot was also overridden or if the model's upstream picks changed, the "two teams competing" in a slot are dynamic.
**How to avoid:** Recalculate the full `det_result` on each override (which the cache handles) and re-resolve competing teams from the NEW det_result, not a stale one. The re-render using the fresh det_result will show the correct teams.
**Warning signs:** SVG shows wrong team names in slots adjacent to the overridden one.

## Code Examples

Verified patterns from existing codebase and official sources:

### Adding override_map to run_deterministic in data_loader.py
```python
# Source: existing src/ui/data_loader.py + official st.cache_data hash_funcs pattern
@st.cache_data(hash_funcs={dict: lambda d: str(sorted(d.items()))})
def run_deterministic(
    _predict_fn,
    _seedings: dict,
    season: int = 2025,
    override_map: dict | None = None,
) -> dict:
    """Run deterministic bracket simulation, optionally with user overrides."""
    return simulate_bracket(
        seedings=_seedings,
        predict_fn=_predict_fn,
        mode="deterministic",
        season=season,
        override_map=override_map or None,
    )
```

### Calling simulation with override_map in app.py
```python
# In app.py, after session_state initialization
override_map = st.session_state.get("override_map", {})

# Normalize empty dict to None for simulator performance
_override_map = override_map if override_map else None

det_result = run_deterministic(predict_fn, seedings, season, override_map=_override_map)
mc_result = run_monte_carlo(predict_fn, seedings, season, override_map=_override_map)
```

### Reset button pattern
```python
# Source: https://docs.streamlit.io/develop/concepts/design/buttons
def _reset_overrides():
    st.session_state["override_map"] = {}

col1, col2 = st.columns([3, 1])
with col2:
    st.button(
        "Reset to model picks",
        on_click=_reset_overrides,
        type="secondary",
        use_container_width=True,
        help="Clear all manual overrides and restore ensemble model predictions",
    )
with col1:
    n_overrides = len(st.session_state.get("override_map", {}))
    if n_overrides:
        st.info(f"{n_overrides} manual override(s) active")
```

### Resolving competing teams for a slot (for selectbox options)
```python
# Source: existing src/ui/bracket_svg.py _resolve_slot_teams() — reuse this logic
from src.ui.bracket_svg import _resolve_slot_teams
from src.simulator.bracket_schema import build_slot_tree, load_seedings

def get_slot_teams(slot_id, det_result, season=2025):
    """Get strong and weak team IDs for a slot from the current det_result."""
    slot_tree = build_slot_tree(season)
    seedings = load_seedings(season)
    strong_id, weak_id = _resolve_slot_teams(slot_id, slot_tree, seedings, det_result)
    return strong_id, weak_id
```

### Checking overridden flag for SVG visual feedback
```python
# Source: existing src/ui/bracket_svg.py + simulate.py output contract
# det_result["slots"][slot_id]["overridden"] is True for forced slots
# Use this in _svg_game_box() to apply different fill/stroke

BOX_FILL_OVERRIDDEN = "#2d1f00"    # dark amber background
BOX_STROKE_OVERRIDDEN = "#f5a623"  # bright amber border

# Modified _svg_game_box() signature:
def _svg_game_box(x, y, w, h, ..., is_champion: bool, is_overridden: bool) -> str:
    if is_overridden:
        fill = BOX_FILL_OVERRIDDEN
        stroke_color = BOX_STROKE_OVERRIDDEN
    elif is_champion:
        fill = BOX_FILL_CHAMPION
        stroke_color = BOX_STROKE
    else:
        fill = BOX_FILL_NORMAL
        stroke_color = BOX_STROKE
    ...
```

### Advancement table update after override
```python
# No changes to build_advancement_df() needed.
# mc_result with override_map will have updated advancement_probs automatically.
# The downstream cascade is handled by simulate_bracket() internals.
adv_df = build_advancement_df(mc_result, team_id_to_name, team_id_to_seed, all_team_ids)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `st.cache` (deprecated) | `@st.cache_data` with `hash_funcs` | Streamlit 1.18+ | Must use hash_funcs for dict args |
| SVG click handlers directly | Widget-based override controls | Always true in Streamlit | No native SVG->Python click path exists |
| Mutating state inline in script body | `on_change`/`on_click` callbacks | Streamlit 1.0+ | Callbacks execute before rerun; mutations are stable |
| Forcing a full page reload for overrides | Session state + cached simulation | Always true | Session_state persists override_map; cache serves result on same rerun |

**Deprecated/outdated:**
- `st.cache`: Do not use. Replaced by `@st.cache_data` and `@st.cache_resource`.
- `st.components.v1.html` for bidirectional communication: Not supported. Use native Streamlit widgets for all user-input overrides.

## Open Questions

1. **Override controls placement: sidebar vs inline tab**
   - What we know: sidebar widgets persist across tab switches; inline widgets only render on the active tab.
   - What's unclear: Whether users want global override access (sidebar) or round-specific access (bracket tab only).
   - Recommendation: Place override controls in the Bracket tab (same place as SVG) using `st.expander` groups per round. This keeps the context (viewing bracket, making picks). The sidebar can show a summary count of active overrides.

2. **Which slots to expose override controls for**
   - What we know: All 63 non-seed slots are theoretically overrideable (R1-R6 game slots). First Four slots (W16, X11, Y11, Y16) can also be overridden.
   - What's unclear: Whether First Four overrides are worth the UI complexity.
   - Recommendation: Include First Four in override controls (4 extra slots, minimal complexity). simulator already handles them.

3. **Selectbox label truncation for team names**
   - What we know: team names can be long (e.g., "Connecticut", "North Carolina"). Seed info takes additional characters. The selectbox label is the slot ID + both team names.
   - What's unclear: Whether selectbox labels in expander will overflow or wrap gracefully in Streamlit's wide layout.
   - Recommendation: Use truncated names in selectbox option labels (max 16 chars, same MAX_NAME_LEN pattern from bracket_svg.py). Slot ID as label prefix.

4. **Whether to show original model prediction alongside override in selectbox**
   - What we know: The phase requirements say "show original model prediction alongside override." The selectbox already shows both teams; the model's pick can be labeled differently (e.g., "Model: Duke (1)" vs just "Duke (1)").
   - What's unclear: Exact label formatting.
   - Recommendation: Format selectbox options as:
     - Option 0: "Model pick" (restores to no-override)
     - Option 1: "Duke (1)" [strong team]
     - Option 2: "Vermont (16)" [weak team]
     After override, show current selection and model's original pick as a `st.caption()` below the selectbox.

## Sources

### Primary (HIGH confidence)
- Official Streamlit docs — `st.session_state` API, session state persistence, callback execution order
- Official Streamlit docs — `st.cache_data` with `hash_funcs` for dict arguments
- Official Streamlit docs — `st.components.v1.html` limitations (no return channel from iframe)
- Official Streamlit docs — `st.selectbox`, `on_change` callbacks, key-based session state
- Official Streamlit docs — `st.button` with `on_click` callback and state persistence
- Streamlit 2026 release notes — confirmed no new native SVG click event API
- `src/simulator/simulate.py` (existing) — verified override_map parameter, overridden=True flag in slot output
- `src/ui/data_loader.py` (existing) — verified run_deterministic/run_monte_carlo signatures to modify
- `src/ui/bracket_svg.py` (existing) — verified _svg_game_box() signature, is_champion pattern to extend for is_overridden
- `app.py` (existing) — verified current app structure and tab layout
- Streamlit community discussion on SVG click events — confirmed iframe isolation, confirmed no native path back to Python

### Secondary (MEDIUM confidence)
- Streamlit community discussion — `window.parent.postMessage` as a workaround; verified as fragile, not recommended
- `hash_funcs={dict: lambda d: str(sorted(d.items()))}` pattern — confirmed from official cache_data docs, verified hashable

### Tertiary (LOW confidence)
- streamlit-javascript third-party library — mentioned as alternative but not verified as production-ready; not recommended
- n_runs=5000 for override mode as UX optimization — not verified; based on reasoning about performance tradeoffs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Streamlit 1.55.0 verified installed; simulate_bracket override_map verified from live code
- Architecture: HIGH — selectbox-based approach verified against Streamlit docs; callback patterns verified; SVG iframe limitation confirmed from official docs
- Pitfalls: HIGH — cache invalidation pitfall verified from official docs; override selectbox revert pitfall verified from session_state docs; SVG click limitation confirmed

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (Streamlit APIs stable; no breaking changes expected in 30 days)
