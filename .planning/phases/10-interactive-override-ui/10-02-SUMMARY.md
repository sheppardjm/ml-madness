---
phase: 10-interactive-override-ui
plan: 02
subsystem: ui
tags: [streamlit, override_controls, bracket_svg, session_state, selectbox, amber]

# Dependency graph
requires:
  - phase: 10-interactive-override-ui
    plan: 01
    provides: "override_map plumbing from session_state through cached simulation functions"
  - phase: 09-bracket-visualization-ui
    provides: "bracket_svg.py render pipeline and app.py tab structure"
  - phase: 04-bracket-simulator
    provides: "simulate_bracket() with overridden flag in slot output (plan 04-05)"
provides:
  - Per-slot selectbox override controls grouped by round in collapsible expanders
  - Amber visual distinction for overridden slots in SVG bracket
  - Reset button that clears all overrides in one click
  - Full integration in app.py bracket tab with count indicator
affects:
  - 10-03 (final phase plan, if any) or end of phase 10

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred imports inside _render_slot_override() for build_slot_tree/load_seedings/_resolve_slot_teams (safe outside Streamlit context)"
    - "format_func=lambda opt: opt[0] extracts display label from (label, team_id) tuple options"
    - "on_change callback closure reads st.session_state[selectbox_key][1] for team_id"
    - "is_overridden takes priority over is_champion in fill/stroke selection"

key-files:
  created:
    - src/ui/override_controls.py
  modified:
    - src/ui/bracket_svg.py
    - app.py

key-decisions:
  - "OVERRIDE_ROUNDS defines all 67 slots across 7 round groups (4 FF + 32 R1 + 16 R2 + 8 R3 + 4 R4 + 2 R5 + 1 R6)"
  - "Amber override coloring (BOX_FILL_OVERRIDDEN=#2d1f00, BOX_STROKE_OVERRIDDEN=#f5a623) takes priority over champion green"
  - "reset_overrides() is a standalone Streamlit callback (not a method) for st.button on_click"
  - "Override controls placed below SVG bracket in bracket tab; sidebar warning from 10-01 retained as persistent cross-tab indicator"
  - "Reset button disabled when no overrides active (n_overrides == 0) to provide clear affordance"

patterns-established:
  - "Selectbox option tuple pattern: (label_str, team_id_or_None) with format_func=lambda opt: opt[0]"
  - "Override callback: read st.session_state[selectbox_key][1], pop slot if None else set slot"

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 10 Plan 02: Override UI Controls Summary

**Override controls with per-slot selectboxes, amber SVG feedback, reset button, and full app.py integration delivering complete user-facing manual bracket override capability**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-04T16:56:51Z
- **Completed:** 2026-03-04T17:00:06Z
- **Tasks:** 3
- **Files modified:** 2 (bracket_svg.py, app.py)
- **Files created:** 1 (override_controls.py)

## Accomplishments

- New `override_controls.py` module with `build_override_controls()`, `reset_overrides()`, and `OVERRIDE_ROUNDS` covering all 67 game slots
- `_svg_game_box()` upgraded with `is_overridden` parameter; amber fill (#2d1f00) and stroke (#f5a623) render on overridden slots
- `render_bracket_svg_string()` reads `slot_sim.get("overridden", False)` and passes to `_svg_game_box()`
- app.py bracket tab now shows SVG + divider + reset button + override info + round-grouped expanders
- Reset button disabled when no overrides active; sidebar warning from 10-01 retained

## Task Commits

Each task committed atomically:

1. **Task 1: Create override_controls.py** - `f92e6ea` (feat)
2. **Task 2: Add override visual feedback to bracket_svg.py** - `a510b22` (feat)
3. **Task 3: Integrate override controls into app.py** - `799b5a0` (feat)

**Plan metadata:** see final docs commit below

## Files Created/Modified

- `src/ui/override_controls.py` (created) - OVERRIDE_ROUNDS, build_override_controls(), reset_overrides(), _render_slot_override(), _make_override_callback()
- `src/ui/bracket_svg.py` (modified) - BOX_FILL_OVERRIDDEN, BOX_STROKE_OVERRIDDEN constants; is_overridden param on _svg_game_box(); overridden flag read in render_bracket_svg_string()
- `app.py` (modified) - Import build_override_controls/reset_overrides; reset button + info panel + build_override_controls() call in bracket tab

## Decisions Made

- OVERRIDE_ROUNDS covers 7 round groups with exactly 67 slots: 4 (First Four) + 32 (R64) + 16 (R32) + 8 (S16) + 4 (E8) + 2 (FF) + 1 (Championship). Verified via assert.
- Amber override visual (#2d1f00 fill, #f5a623 stroke) takes priority over champion green. An overridden championship slot shows amber, not green — user's manual pick overrides the model's champion display.
- `reset_overrides()` implemented as a module-level function (not a method or lambda) since Streamlit `on_click` callbacks must be plain callables.
- Override controls placed in the bracket tab (below SVG) so users can see the bracket and controls side-by-side. The sidebar override warning from 10-01 is retained as a persistent cross-tab indicator.
- Reset button uses `disabled=(n_overrides == 0)` to disable when no overrides are active — clear affordance that clicking is only meaningful when overrides exist.
- Deferred imports in `_render_slot_override()` for `build_slot_tree`, `load_seedings`, and `_resolve_slot_teams` (per decision [09-04] pattern) so the module is safe to import outside a Streamlit context.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All three tasks verified cleanly:
- OVERRIDE_ROUNDS total slot count == 67 (confirmed via assert)
- BOX_FILL_OVERRIDDEN and BOX_STROKE_OVERRIDDEN constants importable
- `is_overridden` in `_svg_game_box()` signature (confirmed via inspect.signature)
- Amber colors appear in SVG output when override is active (end-to-end test)
- app.py: import line and build_override_controls() call both present
- app.py syntax valid (ast.parse())
- Streamlit starts and serves HTML without import errors

## Next Phase Readiness

- Phase 10 plan 10-02 complete; override UI is fully functional
- Users can select alternate winners via selectboxes, see amber highlighting on overridden slots, and use the reset button to restore model picks
- All downstream panels (SVG bracket, advancement table, champion panel) already reflect override-aware simulation results via the override_map pipeline from 10-01
- No blockers for phase completion

---
*Phase: 10-interactive-override-ui*
*Completed: 2026-03-04*
