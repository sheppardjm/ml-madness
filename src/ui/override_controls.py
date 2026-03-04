"""
Override controls module for NCAA tournament bracket UI.

Provides per-slot selectbox widgets grouped by round, allowing users to
manually override game predictions. Overrides are stored in
st.session_state["override_map"] and cascade through downstream simulation.

Exports:
    build_override_controls  - Main entry point; renders round-grouped expanders
    reset_overrides          - Callback for the reset button
    OVERRIDE_ROUNDS          - List of (round_display_name, [slot_ids]) tuples
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Round / slot configuration
# ---------------------------------------------------------------------------

OVERRIDE_ROUNDS: list[tuple[str, list[str]]] = [
    ("First Four", ["W16", "X11", "Y11", "Y16"]),
    ("Round of 64", [f"R1{r}{i}" for r in "WXYZ" for i in range(1, 9)]),
    ("Round of 32", [f"R2{r}{i}" for r in "WXYZ" for i in range(1, 5)]),
    ("Sweet 16", [f"R3{r}{i}" for r in "WXYZ" for i in range(1, 3)]),
    ("Elite 8", [f"R4{r}1" for r in "WXYZ"]),
    ("Final Four", ["R5WX", "R5YZ"]),
    ("Championship", ["R6CH"]),
]

# Maximum team name display length in selectbox labels
MAX_NAME_LEN = 16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_name(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Truncate a team name to max_len characters with '...' suffix."""
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def _make_override_callback(slot_id: str, selectbox_key: str):
    """Return a closure that reads the selectbox value and updates override_map.

    The selectbox stores its selected value at st.session_state[selectbox_key]
    as a (label, team_id_or_None) tuple. If team_id is None the override is
    removed; otherwise the slot is forced to that team.

    Args:
        slot_id:       Game slot identifier (e.g. 'R1W1', 'R6CH').
        selectbox_key: Streamlit widget key for the corresponding selectbox.

    Returns:
        Callable suitable for use as selectbox on_change callback.
    """
    def _callback():
        override_map = st.session_state.get("override_map", {})
        selected_option = st.session_state[selectbox_key]
        # selected_option is a (label, team_id_or_None) tuple
        team_id = selected_option[1]
        if team_id is None:
            # "Model pick" selected -- remove override
            override_map.pop(slot_id, None)
        else:
            override_map[slot_id] = team_id
        st.session_state["override_map"] = override_map

    return _callback


def _render_slot_override(
    slot_id: str,
    det_result: dict,
    team_id_to_name: dict[int, str],
    team_id_to_seednum: dict[int, int],
    season: int,
) -> None:
    """Render a single selectbox widget for one game slot override.

    Resolves the two competing teams for the slot via _resolve_slot_teams()
    and builds a selectbox with options [("Model pick", None), strong, weak].
    If either team cannot be resolved the widget is skipped.

    Args:
        slot_id:            Game slot identifier.
        det_result:         Deterministic simulation result (override-aware).
        team_id_to_name:    Dict mapping team_id -> display name.
        team_id_to_seednum: Dict mapping team_id -> seed number.
        season:             Tournament season year.
    """
    # Deferred imports to keep module safe outside Streamlit context
    # (per decision [09-04] deferred import pattern)
    from src.simulator.bracket_schema import build_slot_tree, load_seedings
    from src.ui.bracket_svg import _resolve_slot_teams

    slot_tree = build_slot_tree(season)
    seedings = load_seedings(season)

    strong_id, weak_id = _resolve_slot_teams(slot_id, slot_tree, seedings, det_result)

    if strong_id is None or weak_id is None:
        # Cannot resolve competing teams -- skip this selectbox
        return

    # Build display labels
    def team_label(team_id: int) -> str:
        name = team_id_to_name.get(team_id, str(team_id))
        seed = team_id_to_seednum.get(team_id)
        seed_str = f"({seed})" if seed is not None else "(?)"
        return f"{seed_str} {_truncate_name(name)}"

    options = [
        ("Model pick", None),
        (team_label(strong_id), strong_id),
        (team_label(weak_id), weak_id),
    ]

    # Determine current index from override_map
    current_override = st.session_state.get("override_map", {}).get(slot_id)
    current_index = 0
    if current_override is not None:
        for i, (_, tid) in enumerate(options):
            if tid == current_override:
                current_index = i
                break

    widget_key = f"override_{slot_id}"

    st.selectbox(
        label=slot_id,
        options=options,
        index=current_index,
        format_func=lambda opt: opt[0],
        key=widget_key,
        on_change=_make_override_callback(slot_id, widget_key),
        label_visibility="visible",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reset_overrides() -> None:
    """Callback for the reset button. Clears all manual overrides."""
    st.session_state["override_map"] = {}


def build_override_controls(
    det_result: dict,
    team_id_to_name: dict[int, str],
    team_id_to_seednum: dict[int, int],
    season: int,
) -> None:
    """Render round-grouped override controls in the Streamlit bracket tab.

    Creates one collapsible expander per round (7 rounds total, covering all
    67 game slots). Each expander shows a selectbox for every slot in that
    round. The expander label includes the count of active overrides.

    Args:
        det_result:         Override-aware deterministic simulation result.
                            Used to resolve competing teams for each slot.
        team_id_to_name:    Dict mapping team_id -> display name.
        team_id_to_seednum: Dict mapping team_id -> seed number.
        season:             Tournament season year.
    """
    override_map = st.session_state.get("override_map", {})

    for round_name, slot_ids in OVERRIDE_ROUNDS:
        # Count active overrides for this round
        n_active = sum(1 for sid in slot_ids if sid in override_map)

        if n_active > 0:
            override_suffix = f" ({n_active} override{'s' if n_active != 1 else ''})"
            label = f"{round_name}{override_suffix}"
        else:
            label = round_name

        with st.expander(label, expanded=False):
            for slot_id in slot_ids:
                _render_slot_override(
                    slot_id,
                    det_result,
                    team_id_to_name,
                    team_id_to_seednum,
                    season,
                )
