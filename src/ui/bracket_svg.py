"""
SVG bracket rendering module for NCAA tournament visualization.

Builds a complete SVG string from coordinate layout data (bracket_layout.py)
and simulation results (simulate_bracket() output), suitable for embedding
in Streamlit via st.components.v1.html().

Dark-theme color palette matches Streamlit's default dark theme (#0e1117).

Exports:
    render_bracket_svg_string   - Main entry point; returns SVG string
"""

from __future__ import annotations

import re
from typing import Any

from src.simulator.bracket_schema import build_slot_tree, load_seedings

# ---------------------------------------------------------------------------
# Color scheme (dark theme)
# ---------------------------------------------------------------------------

BG_COLOR = "#0e1117"
BOX_FILL_NORMAL = "#1a1a2e"
BOX_FILL_CHAMPION = "#1e5a3a"
BOX_STROKE = "#4a90d9"
BOX_FILL_OVERRIDDEN = "#2d1f00"    # dark amber background for manual overrides
BOX_STROKE_OVERRIDDEN = "#f5a623"  # bright amber border for manual overrides
TEXT_WINNER = "#ffffff"
TEXT_LOSER = "#666666"
TEXT_PROB = "#4ec9b0"
CONNECTOR_STROKE = "#3a6a9a"
LABEL_COLOR = "#888888"

# Region display names (slot region code -> display name)
REGION_NAMES: dict[str, str] = {
    "W": "WEST",
    "X": "EAST",
    "Y": "SOUTH",
    "Z": "MIDWEST",
}

# Font settings
FONT_FAMILY = "Consolas, Monaco, monospace"
FONT_SIZE_TEAM = 9
FONT_SIZE_META = 8

# Maximum team name display length before truncation
MAX_NAME_LEN = 14


# ---------------------------------------------------------------------------
# Helper: resolve teams for a slot
# ---------------------------------------------------------------------------


def _resolve_slot_teams(
    slot_id: str,
    slot_tree: dict[str, Any],
    seedings: dict[str, int],
    det_result: dict[str, Any],
) -> tuple[int | None, int | None]:
    """Resolve the two competing team IDs for a slot.

    Looks up StrongSeed and WeakSeed references for the given slot and
    resolves each to a team_id by consulting seedings (seed labels) or
    det_result["slots"] (prior round slot winners).

    Args:
        slot_id:    Slot identifier (e.g. 'R1W1', 'R6CH', 'W16').
        slot_tree:  Dict returned by build_slot_tree() -- maps slot_id to
                    {'StrongSeed': str, 'WeakSeed': str}.
        seedings:   Dict from load_seedings() -- maps seed label -> team_id.
        det_result: Dict from simulate_bracket(mode='deterministic') --
                    has 'slots' dict with team_id per slot.

    Returns:
        (strong_team_id, weak_team_id) tuple. Either can be None if the
        reference cannot be resolved (e.g. First Four slots that feed into R1).
    """
    slots_map = slot_tree["slots"] if "slots" in slot_tree else slot_tree
    if slot_id not in slots_map:
        return None, None

    slot_data = slots_map[slot_id]
    strong_ref = slot_data["StrongSeed"]
    weak_ref = slot_data["WeakSeed"]

    def resolve_ref(ref: str) -> int | None:
        # Try seed label first (e.g. 'W01', 'X16a')
        if ref in seedings:
            return seedings[ref]
        # Try as a prior-slot winner
        det_slots = det_result.get("slots", {})
        if ref in det_slots:
            return det_slots[ref]["team_id"]
        return None

    return resolve_ref(strong_ref), resolve_ref(weak_ref)


# ---------------------------------------------------------------------------
# Helper: draw a single game box
# ---------------------------------------------------------------------------


def _truncate(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Truncate a team name to max_len characters with '...' suffix."""
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def _svg_game_box(
    x: int,
    y: int,
    w: int,
    h: int,
    strong_name: str,
    strong_seed: int | None,
    weak_name: str,
    weak_seed: int | None,
    winner_id: int | None,
    strong_id: int | None,
    weak_id: int | None,
    win_prob: float,
    is_champion: bool,
    is_overridden: bool = False,
) -> str:
    """Build an SVG <g> group for a single game box.

    Draws:
    - Background rectangle with rounded corners
    - Two text rows (strong team top, weak team bottom)
    - Winner row highlighted in white, loser dimmed
    - Win probability shown on winner's row (right-aligned)
    - Amber fill/stroke when slot is a manual override

    Args:
        x, y, w, h:    Box position and size.
        strong_name:   Display name for StrongSeed team.
        strong_seed:   Integer seed number for StrongSeed team (or None).
        weak_name:     Display name for WeakSeed team.
        weak_seed:     Integer seed number for WeakSeed team (or None).
        winner_id:     team_id of the game winner from det_result.
        strong_id:     team_id of the StrongSeed team.
        weak_id:       team_id of the WeakSeed team.
        win_prob:      Win probability for the winner (0-1 float).
        is_champion:   If True, use champion box fill color (green).
        is_overridden: If True, use amber fill/stroke to indicate manual override.
                       Takes priority over is_champion so overridden championship
                       slots show amber rather than green.

    Returns:
        SVG <g> element string.
    """
    row_h = h // 2
    # Override visual takes priority: amber > champion > normal
    if is_overridden:
        fill = BOX_FILL_OVERRIDDEN
        stroke_color = BOX_STROKE_OVERRIDDEN
    elif is_champion:
        fill = BOX_FILL_CHAMPION
        stroke_color = BOX_STROKE
    else:
        fill = BOX_FILL_NORMAL
        stroke_color = BOX_STROKE
    prob_str = f"{win_prob:.1%}"

    # Determine which row is winner
    strong_is_winner = (winner_id is not None and strong_id is not None
                        and winner_id == strong_id)
    weak_is_winner = (winner_id is not None and weak_id is not None
                      and winner_id == weak_id)

    # If both or neither match (e.g., both None), default to strong being winner
    if not strong_is_winner and not weak_is_winner:
        strong_is_winner = True  # fallback

    # Text colors
    strong_color = TEXT_WINNER if strong_is_winner else TEXT_LOSER
    weak_color = TEXT_WINNER if weak_is_winner else TEXT_LOSER

    # Truncated names
    sname = _truncate(strong_name)
    wname = _truncate(weak_name)

    # Seed labels (show as 2-digit, e.g. " 1" or "16")
    def seed_str(s: int | None) -> str:
        if s is None:
            return "??"
        return f"{s:2d}"

    s_seed = seed_str(strong_seed)
    w_seed_s = seed_str(weak_seed)

    # Build each row's text content
    # Format: "{seed} {name}" with probability right-aligned on winner row
    # Text y-position: middle of each row
    strong_y = y + row_h // 2 + FONT_SIZE_TEAM // 2
    weak_y = y + row_h + row_h // 2 + FONT_SIZE_TEAM // 2

    # Horizontal text padding
    text_x = x + 3

    # Probability text x (right-aligned within box)
    prob_x = x + w - 3

    # Build rows
    strong_prob = prob_str if strong_is_winner else ""
    weak_prob = prob_str if weak_is_winner else ""

    strong_label = f"{s_seed} {sname}"
    weak_label = f"{w_seed_s} {wname}"

    lines = [
        f'<g>',
        # Box background
        (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
         f'rx="2" ry="2" fill="{fill}" stroke="{stroke_color}" stroke-width="1"/>'),
        # Divider line between rows
        (f'<line x1="{x}" y1="{y + row_h}" x2="{x + w}" y2="{y + row_h}" '
         f'stroke="{stroke_color}" stroke-width="0.5" opacity="0.4"/>'),
        # Strong seed row text
        (f'<text x="{text_x}" y="{strong_y}" '
         f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_TEAM}" '
         f'fill="{strong_color}"'
         + (' font-weight="bold"' if strong_is_winner else '') +
         f'>{_xml_escape(strong_label)}</text>'),
    ]

    # Strong prob (right-aligned)
    if strong_prob:
        lines.append(
            f'<text x="{prob_x}" y="{strong_y}" '
            f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_META}" '
            f'fill="{TEXT_PROB}" text-anchor="end">{strong_prob}</text>'
        )

    lines.append(
        f'<text x="{text_x}" y="{weak_y}" '
        f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_TEAM}" '
        f'fill="{weak_color}"'
        + (' font-weight="bold"' if weak_is_winner else '') +
        f'>{_xml_escape(weak_label)}</text>'
    )

    if weak_prob:
        lines.append(
            f'<text x="{prob_x}" y="{weak_y}" '
            f'font-family="{FONT_FAMILY}" font-size="{FONT_SIZE_META}" '
            f'fill="{TEXT_PROB}" text-anchor="end">{weak_prob}</text>'
        )

    lines.append('</g>')
    return "\n".join(lines)


def _xml_escape(s: str) -> str:
    """Escape special XML characters in text content."""
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


# ---------------------------------------------------------------------------
# Helper: region label positions
# ---------------------------------------------------------------------------


def _compute_region_label_positions(
    layout: dict[str, Any],
) -> list[tuple[str, int, int]]:
    """Compute (label_text, x, y) positions for region and center labels.

    Returns list of (text, cx, y) tuples where cx is the center x of the
    column and y is above the first slot in that column.
    """
    labels: list[tuple[str, int, int]] = []
    slots = layout["slots"]

    PADDING_ABOVE = 16  # pixels above slot top edge

    # Region labels: one per region's R1 column
    for region in ("W", "X", "Y", "Z"):
        r1_slots = [
            info for sid, info in slots.items()
            if sid.startswith("R1") and info["region"] == region
        ]
        if not r1_slots:
            continue
        min_y = min(s["y"] for s in r1_slots)
        x_vals = [s["x"] for s in r1_slots]
        cx = x_vals[0] + r1_slots[0]["w"] // 2
        label = REGION_NAMES.get(region, region)
        labels.append((label, cx, min_y - PADDING_ABOVE))

    # Final Four labels: above R5WX and R5YZ
    for slot_id, label_text in (("R5WX", "FINAL FOUR"), ("R5YZ", "FINAL FOUR")):
        if slot_id in slots:
            info = slots[slot_id]
            cx = info["x"] + info["w"] // 2
            labels.append((label_text, cx, info["y"] - PADDING_ABOVE))

    # Championship label: above R6CH
    if "R6CH" in slots:
        info = slots["R6CH"]
        cx = info["x"] + info["w"] // 2
        labels.append(("CHAMPIONSHIP", cx, info["y"] - PADDING_ABOVE))

    return labels


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_bracket_svg_string(
    det_result: dict[str, Any],
    layout: dict[str, Any],
    team_id_to_name: dict[int, str],
    team_id_to_seednum: dict[int, int],
    season: int = 2025,
) -> str:
    """Build a complete SVG string for the NCAA tournament bracket.

    Combines coordinate layout data with simulation results to produce a
    dark-themed SVG showing all 67 game slots with team names, seed numbers,
    win probabilities, and connector lines.

    Args:
        det_result:         Dict from simulate_bracket(mode='deterministic').
                            Must have 'slots' dict and 'champion' dict.
        layout:             Dict from compute_bracket_layout(). Must have
                            'slots', 'connectors', 'canvas_width', 'canvas_height'.
        team_id_to_name:    Dict mapping team_id (int) -> display name (str).
        team_id_to_seednum: Dict mapping team_id (int) -> seed number (int).
        season:             Tournament season year. Default: 2025.

    Returns:
        Complete SVG string (not wrapped in HTML -- caller wraps).
    """
    # --- Load slot tree and seedings internally ---
    slot_tree_raw = build_slot_tree(season)
    seedings = load_seedings(season)

    canvas_width = layout["canvas_width"]
    canvas_height = layout["canvas_height"]
    layout_slots = layout["slots"]
    connectors = layout["connectors"]

    champion_team_id = det_result.get("champion", {}).get("team_id")

    # Build SVG element list
    parts: list[str] = []

    # --- SVG root ---
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {canvas_width} {canvas_height}" '
        f'width="{canvas_width}" height="{canvas_height}">'
    )

    # --- Background ---
    parts.append(
        f'<rect width="{canvas_width}" height="{canvas_height}" fill="{BG_COLOR}"/>'
    )

    # --- Connector lines (drawn first, behind boxes) ---
    for conn in connectors:
        pts = conn["points"]
        if len(pts) < 2:
            continue
        points_str = " ".join(f"{px},{py}" for px, py in pts)
        parts.append(
            f'<polyline points="{points_str}" '
            f'stroke="{CONNECTOR_STROKE}" stroke-width="1" '
            f'fill="none" stroke-linejoin="round"/>'
        )

    # --- Game boxes ---
    det_slots = det_result.get("slots", {})

    for slot_id, slot_info in layout_slots.items():
        x = slot_info["x"]
        y = slot_info["y"]
        w = slot_info["w"]
        h = slot_info["h"]

        # Get simulation result for this slot
        slot_sim = det_slots.get(slot_id, {})
        winner_id: int | None = slot_sim.get("team_id")
        win_prob: float = slot_sim.get("win_prob", 0.5)
        is_overridden: bool = slot_sim.get("overridden", False)

        # Resolve competing teams
        strong_id, weak_id = _resolve_slot_teams(
            slot_id, slot_tree_raw, seedings, det_result
        )

        # Look up names and seeds
        def get_name(tid: int | None) -> str:
            if tid is None:
                return "TBD"
            return team_id_to_name.get(tid, str(tid))

        def get_seed(tid: int | None) -> int | None:
            if tid is None:
                return None
            return team_id_to_seednum.get(tid)

        strong_name = get_name(strong_id)
        strong_seed = get_seed(strong_id)
        weak_name = get_name(weak_id)
        weak_seed = get_seed(weak_id)

        is_champion = (slot_id == "R6CH" and winner_id == champion_team_id)

        parts.append(_svg_game_box(
            x=x, y=y, w=w, h=h,
            strong_name=strong_name,
            strong_seed=strong_seed,
            weak_name=weak_name,
            weak_seed=weak_seed,
            winner_id=winner_id,
            strong_id=strong_id,
            weak_id=weak_id,
            win_prob=win_prob,
            is_champion=is_champion,
            is_overridden=is_overridden,
        ))

    # --- Region and center labels ---
    label_positions = _compute_region_label_positions(layout)
    for label_text, cx, ly in label_positions:
        parts.append(
            f'<text x="{cx}" y="{ly}" '
            f'font-family="{FONT_FAMILY}" font-size="10" '
            f'fill="{LABEL_COLOR}" text-anchor="middle" '
            f'font-weight="bold">{label_text}</text>'
        )

    # --- SVG close ---
    parts.append("</svg>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import duckdb
    from src.ui.bracket_layout import compute_bracket_layout
    from src.simulator.bracket_schema import build_predict_fn
    from src.simulator.simulate import simulate_bracket

    print("=" * 60)
    print("bracket_svg.py smoke test")
    print("=" * 60)

    seedings = load_seedings(2025)
    predict_fn, stats = build_predict_fn(season=2025)
    det_result = simulate_bracket(seedings, predict_fn, mode="deterministic", season=2025)
    layout = compute_bracket_layout(2025)

    conn = duckdb.connect()
    df = conn.execute(
        "SELECT TeamID, TeamName, SeedNum FROM read_parquet('data/processed/seeds.parquet') WHERE Season=2025"
    ).df()
    conn.close()
    team_id_to_name = dict(zip(df.TeamID, df.TeamName))
    team_id_to_seednum = dict(zip(df.TeamID, df.SeedNum))

    svg = render_bracket_svg_string(det_result, layout, team_id_to_name, team_id_to_seednum)

    assert "<svg" in svg, "Missing <svg tag"
    assert "</svg>" in svg, "Missing </svg>"
    print(f"SVG length: {len(svg)} chars")

    found = sum(1 for name in team_id_to_name.values() if name in svg)
    print(f"Team names found: {found}")
    assert found >= 30, f"Expected 30+ team names, found {found}"

    import re as _re
    prob_matches = _re.findall(r"\d{1,3}\.\d%", svg)
    print(f"Probability values found: {len(prob_matches)}")
    assert len(prob_matches) >= 10, f"Expected 10+ probabilities, found {len(prob_matches)}"

    print("Smoke test PASS")
