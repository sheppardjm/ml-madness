"""
Bracket coordinate layout algorithm for NCAA tournament SVG rendering.

Maps every slot_id to pixel (x, y, width, height) coordinates plus connector
line data for use by SVG rendering layers.

This module is pure Python with no Streamlit dependency. It can be developed
and tested independently of the Streamlit app.

Layout overview (left-to-right):
  [FF_W] [R1_W...R4_W]  [R1_X...R4_X]   [R5WX]   [R5YZ]   [R4_Y...R1_Y]  [R4_Z...R1_Z] [FF_Z]
                                            [R6CH]

Left side:
  - W region on top (R1 leftmost, R4 rightmost — rounds advance inward)
  - X region below W (same x-column layout)
Right side:
  - Y region on top (R4 leftmost, R1 rightmost — mirrored)
  - Z region below Y (same mirrored layout)
Center:
  - R5WX (Final Four game from W+X Elite 8 winners)
  - R5YZ (Final Four game from Y+Z Elite 8 winners)
  - R6CH (Championship game between R5WX and R5YZ winners)

First Four slots:
  - W16, X11: pre-column to the left of their respective R1 slots
  - Y11, Y16: pre-column to the right of their respective R1 slots (mirrored side)

Exports:
    compute_bracket_layout(season) -> layout dict with slots, connectors, canvas dims
    SLOT_WIDTH                     - pixel width of each game box
    SLOT_HEIGHT                    - pixel height of one team row in a game box
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

SLOT_WIDTH: int = 150       # pixels per game box width
SLOT_HEIGHT: int = 22       # pixels per team row (game box has 2 rows: team A and team B)
BOX_HEIGHT: int = 44        # full game box height (2 * SLOT_HEIGHT)
ROUND_GAP: int = 30         # horizontal gap between successive round columns
FF_GAP: int = 20            # horizontal gap between First Four pre-column and R1
REGION_V_GAP: int = 20      # vertical gap between the two stacked regions (W/X or Y/Z)
CENTER_GAP: int = 80        # horizontal gap on each side of the center Final Four column
CONNECTOR_OFFSET: int = 5   # horizontal extension of connector line from slot edge

# Vertical spacing for R1 game boxes (tight packing)
_R1_V_SPACING: int = BOX_HEIGHT + 4   # 48px between top edges of adjacent R1 boxes

# Width of the First Four pre-column (same as a normal slot)
_FF_COL_WIDTH: int = SLOT_WIDTH


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _region_from_slot(slot_id: str) -> str:
    """Return the region letter for a slot (W, X, Y, Z, or FF for R5/R6)."""
    if not slot_id.startswith("R"):
        # First Four slot: region is the first character (W, X, Y)
        return slot_id[0]
    round_num = int(slot_id[1])
    if round_num <= 4:
        # R1W1 -> W, R3X2 -> X, etc.
        return slot_id[2]
    # R5WX, R5YZ, R6CH -> "FF"
    return "FF"


def _slot_index_in_round(slot_id: str) -> int:
    """Return 0-based index of a slot within its round+region.

    For R1W3 -> 2 (0-based), for R2X4 -> 3, etc.
    For R5/R6 slots: always 0.
    """
    if not slot_id.startswith("R"):
        return 0
    round_num = int(slot_id[1])
    if round_num >= 5:
        return 0
    # e.g. R1W3: index is int("3") - 1 = 2
    return int(slot_id[3:]) - 1


def _r1_y_for_slot(slot_index: int) -> int:
    """Compute the y-coordinate (top edge) for an R1 slot by its 0-based index.

    R1 has 8 game boxes packed at _R1_V_SPACING apart.
    """
    return slot_index * _R1_V_SPACING


def _centered_y(child_a_y: int, child_b_y: int) -> int:
    """Return the y that centers a parent box between two child boxes.

    Both children have the same BOX_HEIGHT. The parent is centered between
    the top edge of child_a and the bottom edge of child_b.
    """
    top = child_a_y
    bottom = child_b_y + BOX_HEIGHT
    return top + (bottom - top - BOX_HEIGHT) // 2


def _compute_region_slot_ys(num_slots_r1: int = 8) -> dict[int, list[int]]:
    """Compute y-coordinates for all rounds within a single region.

    Uses the doubling-spacing formula from the plan:
        base_spacing = BOX_HEIGHT + 4   (R1 tight spacing = 48px)
        spacing_r    = base_spacing * 2^(r-1)
        y_r_s        = s * spacing_r + (spacing_r - BOX_HEIGHT) // 2

    This ensures each slot in round r is visually centered within the vertical
    band occupied by the 2^(r-1) R1 slots it subsumes, while keeping all
    round columns non-overlapping.

    Note: The NCAA tournament has a "seeding bracket" structure where R2 slot j
    is fed by R1 slots j and (n-1-j) — a symmetric, non-adjacent pairing.
    A naive "center between two children" formula collapses all R2 slots to
    the same y because the children are always equidistant from the midline.
    The doubling-spacing formula avoids this by spacing slots geometrically.

    Returns a dict: round_number -> list of y-coordinates (0-based order).
    Rounds 1-4 (R1=8 slots, R2=4 slots, R3=2 slots, R4=1 slot).
    """
    base_spacing = BOX_HEIGHT + 4   # 48 pixels for R1

    ys: dict[int, list[int]] = {}
    for rnd in range(1, 5):
        n_slots = num_slots_r1 // (2 ** (rnd - 1))
        spacing = base_spacing * (2 ** (rnd - 1))
        ys[rnd] = [
            s * spacing + (spacing - BOX_HEIGHT) // 2
            for s in range(n_slots)
        ]

    return ys


# ---------------------------------------------------------------------------
# Main layout function
# ---------------------------------------------------------------------------


def compute_bracket_layout(season: int = 2025) -> dict[str, Any]:
    """Compute pixel coordinates for all 67 tournament bracket slots.

    Loads the slot tree via build_slot_tree() and maps every slot_id to an
    (x, y, w, h) rectangle, plus connector line data between parent and
    child slots.

    Args:
        season: Tournament season year. Default 2025.

    Returns:
        dict with:
            "slots": {slot_id: {"x", "y", "w", "h", "round", "region", "side"}}
            "connectors": [{"from_slot", "to_slot", "points": [(x,y),...]}]
            "canvas_width": int
            "canvas_height": int
    """
    # Import bracket schema (deferred to avoid circular issues at module level)
    _repo_root = pathlib.Path(__file__).resolve().parents[2]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

    from src.simulator.bracket_schema import build_slot_tree

    tree = build_slot_tree(season)
    slot_tree = tree["slots"]
    ff_slots = tree["ff_slots"]

    # -----------------------------------------------------------------------
    # Step 1: Compute per-region y-coordinate tables
    # -----------------------------------------------------------------------
    # All four regions share the same internal y-layout (8->4->2->1 slots).
    region_ys = _compute_region_slot_ys(8)
    # region_ys[r][j] = y offset within the region for round r, slot index j

    # -----------------------------------------------------------------------
    # Step 2: Determine canvas geometry parameters
    # -----------------------------------------------------------------------
    # Left half: FF_col + R1..R4 = 1 + 4 columns
    # Right half: R4..R1 + FF_col = 4 + 1 columns (mirrored)
    # Center: 1 column for Final Four + Championship (R5WX, R5YZ, R6CH)
    # Total columns: 2 * (1 FF + 4 region) + 1 center = 11 columns
    # But we only have FF pre-columns on the left (W16) and right (Y16, Z16).
    # (W and X share the same x-columns; same for Y and Z)

    # Left side x-positions for rounds 1-4:
    #   round r: x = _FF_COL_WIDTH + FF_GAP + (r-1) * (SLOT_WIDTH + ROUND_GAP)
    # Right side x-positions for rounds 1-4 (mirrored):
    #   determined after we know left side + center width

    # Compute left side total width (FF_col + R1..R4 + half-center-gap):
    n_rounds_per_region = 4
    left_region_width = (
        _FF_COL_WIDTH + FF_GAP
        + n_rounds_per_region * SLOT_WIDTH
        + (n_rounds_per_region - 1) * ROUND_GAP
    )
    # center column: one SLOT_WIDTH wide, with CENTER_GAP on each side
    center_col_x_left_edge = left_region_width + CENTER_GAP
    canvas_width = 2 * left_region_width + 2 * CENTER_GAP + SLOT_WIDTH

    # -----------------------------------------------------------------------
    # Step 3: Determine vertical layout
    # -----------------------------------------------------------------------
    # Region height = height of R1 column = 8 slots * _R1_V_SPACING + BOX_HEIGHT - 4
    region_height = 8 * _R1_V_SPACING - 4 + BOX_HEIGHT
    # Two stacked regions with gap
    half_height = region_height * 2 + REGION_V_GAP
    # Add padding on top and bottom
    V_PADDING = 30
    canvas_height = half_height + 2 * V_PADDING

    # Region y offsets (top of each region within canvas)
    y_top_region = V_PADDING          # W / Y region y offset
    y_bot_region = V_PADDING + region_height + REGION_V_GAP   # X / Z region y offset

    # -----------------------------------------------------------------------
    # Step 4: Compute x-positions for each round on left and right sides
    # -----------------------------------------------------------------------

    def left_x(round_num: int) -> int:
        """x of left edge for round r on the LEFT side (W, X regions)."""
        return _FF_COL_WIDTH + FF_GAP + (round_num - 1) * (SLOT_WIDTH + ROUND_GAP)

    def right_x(round_num: int) -> int:
        """x of left edge for round r on the RIGHT side (Y, Z regions, mirrored).

        On the right side R1 is rightmost, R4 is leftmost (advancing inward).
        """
        # R1 rightmost: canvas_width - _FF_COL_WIDTH - FF_GAP - SLOT_WIDTH
        # R4 leftmost: canvas_width - left_x(4) - SLOT_WIDTH  (symmetric with left side)
        return canvas_width - left_x(round_num) - SLOT_WIDTH

    # -----------------------------------------------------------------------
    # Step 5: Build the slot -> (x, y) mapping
    # -----------------------------------------------------------------------
    result_slots: dict[str, dict[str, Any]] = {}

    def add_slot(
        slot_id: str,
        x: int,
        y: int,
        round_num: int,
        region: str,
        side: str,
    ) -> None:
        result_slots[slot_id] = {
            "x": x,
            "y": y,
            "w": SLOT_WIDTH,
            "h": BOX_HEIGHT,
            "round": round_num,
            "region": region,
            "side": side,
        }

    # --- Left regions: W (top) and X (bottom) ---
    for region, y_offset in (("W", y_top_region), ("X", y_bot_region)):
        for rnd in range(1, 5):
            n_slots = 8 // (2 ** (rnd - 1))   # R1=8, R2=4, R3=2, R4=1
            x = left_x(rnd)
            ys_this_round = region_ys[rnd]
            for j in range(n_slots):
                slot_id = f"R{rnd}{region}{j + 1}"
                y = y_offset + ys_this_round[j]
                add_slot(slot_id, x, y, rnd, region, "left")

    # --- Right regions: Y (top) and Z (bottom) ---
    # RIGHT side is mirrored: R1 slots appear rightmost, R4 leftmost.
    # The slot index within the region is still 0-based from top to bottom,
    # but x-position is computed with right_x().
    for region, y_offset in (("Y", y_top_region), ("Z", y_bot_region)):
        for rnd in range(1, 5):
            n_slots = 8 // (2 ** (rnd - 1))
            x = right_x(rnd)
            ys_this_round = region_ys[rnd]
            for j in range(n_slots):
                slot_id = f"R{rnd}{region}{j + 1}"
                y = y_offset + ys_this_round[j]
                add_slot(slot_id, x, y, rnd, region, "right")

    # --- Final Four and Championship (center column) ---
    # R5WX, R5YZ, and R6CH all share the same x-column (center of canvas).
    # Because the bracket is perfectly left-right symmetric, R4W1 and R4Y1
    # are at the same y, and R4X1 and R4Z1 are at the same y.  A naive
    # "centered between R4 children" formula would collapse all three center
    # slots to the same y.  Instead we stack them explicitly:
    #   R5WX at y corresponding to the upper R4 (W/Y) level
    #   R5YZ at y corresponding to the lower R4 (X/Z) level
    #   R6CH exactly midway between R5WX and R5YZ
    center_x = center_col_x_left_edge

    # Use the R4 y-positions directly for the two Final Four games
    r4w1_y = result_slots["R4W1"]["y"]   # upper R4 level (same as R4Y1)
    r4x1_y = result_slots["R4X1"]["y"]   # lower R4 level (same as R4Z1)

    r5wx_y = r4w1_y
    r5yz_y = r4x1_y
    add_slot("R5WX", center_x, r5wx_y, 5, "FF", "left")
    add_slot("R5YZ", center_x, r5yz_y, 5, "FF", "right")

    # R6CH: centered between R5WX and R5YZ
    r6ch_y = _centered_y(r5wx_y, r5yz_y)
    add_slot("R6CH", center_x, r6ch_y, 6, "FF", "left")

    # --- First Four slots ---
    # FF slot positions determined by the R1 slot they feed into.
    # Left-side FF slots (W16, X11): x = 0 (leftmost column)
    # Right-side FF slots (Y11, Y16): x = canvas_width - _FF_COL_WIDTH
    for ff_slot_id in ff_slots:
        # Find the R1 slot this FF slot feeds into
        parent_r1 = None
        for s_id, s_data in slot_tree.items():
            if s_id.startswith("R1") and (
                s_data["StrongSeed"] == ff_slot_id
                or s_data["WeakSeed"] == ff_slot_id
            ):
                parent_r1 = s_id
                break

        if parent_r1 is None:
            # Should not happen for a valid season, but guard gracefully
            continue

        parent_info = result_slots[parent_r1]
        ff_y = parent_info["y"]
        region = ff_slot_id[0]   # First char is region letter (W, X, Y, Z)

        # W and X are left-side; Y and Z are right-side
        if region in ("W", "X"):
            ff_x = 0
            side = "left"
        else:
            ff_x = canvas_width - _FF_COL_WIDTH
            side = "right"

        add_slot(ff_slot_id, ff_x, ff_y, 0, region, side)

    # -----------------------------------------------------------------------
    # Step 6: Build connector lines
    # -----------------------------------------------------------------------
    # For each slot that has child slots (StrongSeed/WeakSeed referencing
    # another slot_id rather than a seed label like 'W01'), draw an L-shaped
    # connector.
    connectors: list[dict[str, Any]] = []

    def is_slot_ref(seed_ref: str) -> bool:
        """Return True if seed_ref is a slot_id (not a seed label like 'W01')."""
        # Seed labels: region letter + two digits (+ optional a/b)
        # Slot IDs: start with 'R' (e.g. R1W1, R5WX) or are FF slot names (W16)
        # Kaggle seed labels have two-digit numbers: W01, X11, Y16
        # Slot refs starting with 'R' are always slot IDs
        # FF slot IDs (W16, X11, Y11, Y16) also appear as WeakSeed refs
        if seed_ref.startswith("R"):
            return True
        # Check if it's a known FF slot id (in the ff_slots set)
        if seed_ref in ff_slots:
            return True
        return False

    for slot_id, slot_info in result_slots.items():
        if slot_id not in slot_tree:
            continue  # FF slots are not parent-slot keys in the tree

        seeds = slot_tree[slot_id]
        for child_key in ("StrongSeed", "WeakSeed"):
            child_ref = seeds[child_key]
            if not is_slot_ref(child_ref):
                continue
            if child_ref not in result_slots:
                continue

            child_info = result_slots[child_ref]
            parent_info = result_slots[slot_id]

            # Determine side from child
            side = child_info["side"]

            # Child output edge and parent input edge
            child_cx = child_info["y"] + BOX_HEIGHT // 2   # vertical center of child
            parent_cy = parent_info["y"] + BOX_HEIGHT // 2  # vertical center of parent

            if side == "left":
                # Left side: connector goes right from child, then to parent's left edge
                child_out_x = child_info["x"] + SLOT_WIDTH
                parent_in_x = parent_info["x"]
                mid_x = child_out_x + CONNECTOR_OFFSET
                points = [
                    (child_out_x, child_cx),
                    (mid_x, child_cx),
                    (mid_x, parent_cy),
                    (parent_in_x, parent_cy),
                ]
            else:
                # Right side: connector goes left from child, then to parent's right edge
                child_out_x = child_info["x"]
                parent_in_x = parent_info["x"] + SLOT_WIDTH
                mid_x = child_out_x - CONNECTOR_OFFSET
                points = [
                    (child_out_x, child_cx),
                    (mid_x, child_cx),
                    (mid_x, parent_cy),
                    (parent_in_x, parent_cy),
                ]

            connectors.append(
                {
                    "from_slot": child_ref,
                    "to_slot": slot_id,
                    "points": points,
                }
            )

    return {
        "slots": result_slots,
        "connectors": connectors,
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("bracket_layout.py smoke test")
    print("=" * 60)

    layout = compute_bracket_layout(2025)
    slots = layout["slots"]
    connectors = layout["connectors"]
    canvas_width = layout["canvas_width"]
    canvas_height = layout["canvas_height"]

    # 1. Slot count
    print(f"\n[1] Slot count: {len(slots)}")
    assert len(slots) == 67, f"Expected 67 slots, got {len(slots)}"
    print("    OK")

    # 2. Canvas dimensions
    print(f"\n[2] Canvas: {canvas_width} x {canvas_height}")
    assert 1200 <= canvas_width <= 2100, (
        f"Canvas width {canvas_width} outside expected range [1200, 2100]"
    )
    assert 800 <= canvas_height <= 1200, (
        f"Canvas height {canvas_height} outside expected range [800, 1200]"
    )
    print("    OK")

    # 3. All expected slots present
    expected_slots = set()
    for rnd in range(1, 5):
        for reg in ("W", "X", "Y", "Z"):
            n = 8 // (2 ** (rnd - 1))
            for j in range(1, n + 1):
                expected_slots.add(f"R{rnd}{reg}{j}")
    expected_slots |= {"R5WX", "R5YZ", "R6CH", "W16", "X11", "Y11", "Y16"}
    missing = expected_slots - set(slots.keys())
    assert not missing, f"Missing expected slots: {sorted(missing)}"
    print(f"\n[3] All {len(expected_slots)} expected slots present: OK")

    # 4. All 4 regions represented
    regions_present = {v["region"] for v in slots.values()}
    assert "W" in regions_present, "Region W missing"
    assert "X" in regions_present, "Region X missing"
    assert "Y" in regions_present, "Region Y missing"
    assert "Z" in regions_present, "Region Z missing"
    assert "FF" in regions_present, "Region FF (Final Four) missing"
    print(f"\n[4] Regions present: {sorted(regions_present)}: OK")

    # 5. No overlapping slot boxes (check all pairwise rectangle intersections)
    slot_list = list(slots.items())
    n = len(slot_list)
    overlap_count = 0
    for i in range(n):
        id_a, a = slot_list[i]
        for j in range(i + 1, n):
            id_b, b = slot_list[j]
            # Check if rectangles overlap (strictly — touching edges OK)
            overlap_x = a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            overlap_y = a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]
            if overlap_x and overlap_y:
                overlap_count += 1
                print(
                    f"    OVERLAP: {id_a} ({a['x']},{a['y']},{a['w']},{a['h']}) "
                    f"vs {id_b} ({b['x']},{b['y']},{b['w']},{b['h']})"
                )
    assert overlap_count == 0, f"Found {overlap_count} overlapping slot boxes"
    print(f"\n[5] Overlap check ({n*(n-1)//2} pairs): 0 overlaps: OK")

    # 6. Sample slot coordinates
    print("\n[6] Sample slot coordinates:")
    for sample_id in ("R1W1", "R6CH", "W16", "R5WX", "R5YZ", "R4Y1"):
        if sample_id in slots:
            s = slots[sample_id]
            print(
                f"    {sample_id:8s}: x={s['x']:4d}, y={s['y']:4d}, "
                f"round={s['round']}, region={s['region']}, side={s['side']}"
            )

    # 7. Connector count sanity
    print(f"\n[7] Connectors: {len(connectors)}")
    # Each slot except FF and R6CH has a parent -> 67 - 4 FF - 1 R6CH = 62 child->parent links
    # Each parent can receive 2 child connectors (StrongSeed + WeakSeed)
    # Total connectors = number of slot-ref edges in the tree
    # Minimum: 63 (each of 63 non-root non-FF slots has 1 parent)
    # Maximum: 2 * 33 = 66 (each parent has 2 children that are slot refs)
    assert len(connectors) >= 30, f"Too few connectors: {len(connectors)}"
    print("    OK")

    # 8. Left/right symmetry check: R5WX left, R5YZ right
    assert slots["R5WX"]["side"] == "left", "R5WX should be side=left"
    assert slots["R5YZ"]["side"] == "right", "R5YZ should be side=right"
    print("\n[8] R5WX/R5YZ side assignment: OK")

    # 9. FF slots aligned with their parent R1 slots
    from src.simulator.bracket_schema import build_slot_tree
    tree = build_slot_tree(2025)
    slot_data = tree["slots"]
    for ff_id in ("W16", "X11", "Y11", "Y16"):
        # Find R1 parent
        for s_id, s_vals in slot_data.items():
            if s_id.startswith("R1") and (
                s_vals["StrongSeed"] == ff_id or s_vals["WeakSeed"] == ff_id
            ):
                assert slots[ff_id]["y"] == slots[s_id]["y"], (
                    f"FF slot {ff_id} y={slots[ff_id]['y']} != parent R1 {s_id} y={slots[s_id]['y']}"
                )
                break
    print("\n[9] FF slot y-alignment with R1 parents: OK")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)
