"""Flow rendering functions and SVG geometry helpers.

Contains the two public rendering entry points (``render_flow`` for advanced
flows and ``render_standard_flow`` for standard flows) plus the private
helpers they rely on (_card_badge, _card_dims, _bezier, _compute_card_labels,
_write_output).

This module sits at the top of the internal dependency graph:
it imports from _constants, _svg_builder, _label_parser, and _lookups but
nothing imports from it except __init__ and _cli.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import cairosvg as _cairosvg
except ImportError:
    _cairosvg = None

from render_flows._constants import (
    CANVAS_BG,
    CARD_DIMS,
    CARD_RADIUS,
    CONN_ERROR,
    CONN_FALSE,
    CONN_SUCCESS,
    CONN_TRUE,
    FONT,
    GRID_COLOR,
    NOTE_FILLS,
    PADDING,
    STYLES,
    TEXT_DARK,
    TEXT_LIGHT,
    TITLE_H,
)
from render_flows._label_parser import _parse_label, _word_wrap
from render_flows._lookups import _build_trigger_name_map
from render_flows._svg_builder import SVGBuilder


def _card_badge(card: dict) -> str:
    """Return the type-badge text shown in the card's top-left corner.

    Classifies the card by inspecting its ``id`` URI to produce specific labels
    such as 'DEVICE TRIGGER', 'BLL ACTION', 'ZONE TRIGGER', 'TIMELINE', etc.
    Falls back to the card type string (e.g. 'TRIGGER') if no specific badge matches.
    """
    ctype = card.get("type", "")
    cid = card.get("id", "")
    if ctype == "trigger":
        if "homey:zone:" in cid:
            return "ZONE TRIGGER"
        if "homey:device:" in cid:
            return "DEVICE TRIGGER"
        if "flowbits" in cid:
            return "FLOWBITS TRIGGER"
        if "homey:manager:cron:" in cid:
            return "CRON TRIGGER"
        if "homey:manager:presence:" in cid:
            return "PRESENCE TRIGGER"
        if "homey:manager:logic:" in cid:
            return "LOGIC TRIGGER"
        if "homey:manager:system:" in cid:
            return "SYSTEM TRIGGER"
        if "net.i-dev.betterlogic" in cid:
            return "BLL TRIGGER"
        return "TRIGGER"
    if ctype == "condition":
        if "net.i-dev.betterlogic" in cid:
            return "BLL CONDITION"
        if "homey:manager:logic:" in cid:
            return "LOGIC CONDITION"
        if "homey:device:" in cid:
            return "DEVICE CONDITION"
        if "flowbits" in cid:
            return "FLOWBITS CONDITION"
        if "homey:manager:cron:" in cid:
            return "CRON CONDITION"
        if "homey:manager:presence:" in cid:
            return "PRESENCE CONDITION"
        if "homey:manager:mobile:" in cid:
            return "MOBILE CONDITION"
        return "CONDITION"
    if ctype == "action":
        if "net.i-dev.betterlogic" in cid:
            return "BLL ACTION"
        if "homey:manager:notifications" in cid:
            return "TIMELINE"
        if "homey:manager:mobile" in cid:
            return "MOBILE ACTION"
        if "homey:manager:logic" in cid:
            return "LOGIC ACTION"
        if "homey:device:" in cid:
            return "DEVICE ACTION"
        if "homey:zone:" in cid:
            return "ZONE ACTION"
        if "homey:manager:flow:" in cid:
            return "FLOW ACTION"
        if "homey:manager:presence:" in cid:
            return "PRESENCE ACTION"
        if "com.basmilius.flowbits" in cid:
            return "FLOWBITS ACTION"
        if "com.ubnt.unifiprotect" in cid:
            return "CAMERA ACTION"
        if "ady.enhanced_device_widget" in cid:
            return "WIDGET ACTION"
        return "ACTION"
    return ctype.upper()


def _compute_card_labels(
    cards: dict[str, dict],
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Pre-compute the display label for every card. Returns card_uuid → label."""
    return {
        cid: _parse_label(card, device_lookup, var_lookup, zone_lookup, trigger_name_map, trigger_cap_map)
        for cid, card in cards.items()
    }


def _card_dims(card: dict, label: str | None = None) -> tuple[float, float]:
    """Return (width, height) for a card. Notes, delays, and labeled cards sized dynamically."""
    ctype = card["type"]
    w, h = CARD_DIMS.get(ctype, (340, 72))
    if ctype == "note":
        text = card.get("value", "")
        lines = _word_wrap(text, 42)
        h = max(48, 20 + len(lines) * 15 + 14)
    elif ctype == "delay":
        d = (card.get("args") or {}).get("delay", {})
        n = d.get("number", "?")
        m = int(d.get("multiplier", 1))
        unit = {1: "sec", 60: "min", 3600: "hr"}.get(m, f"×{m}s")
        dlabel = f"Delay {n} {unit}"
        w = max(117, min(280, int(38 + len(dlabel) * 7.5 + 16)))
    elif ctype in ("trigger", "condition", "action") and label:
        body_max_chars = int((w - 24) / 6.5)
        lines = _word_wrap(label[:240], body_max_chars)
        n_lines = min(len(lines), 6)
        h = max(h, 32 + n_lines * 16 + 12)
    return float(w), float(h)


def _bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    """Cubic Bézier path data for a smooth horizontal S-curve."""
    dx = max(abs(x2 - x1) * 0.45, 50)
    return (
        f"M{x1:.1f},{y1:.1f} "
        f"C{x1 + dx:.1f},{y1:.1f} {x2 - dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
    )


# ─── Main Renderer ───────────────────────────────────────────────────

def _write_output(svg_str: str, out_path: Path, to_png: bool) -> Path:
    """Write SVG string to *out_path*. If *to_png*, convert via cairosvg and change extension."""
    if to_png:
        if _cairosvg is None:
            raise SystemExit(
                "ERROR: --png requires cairosvg.\n"
                "  Recommended: use uv run render_flows.py --png  (auto-installs cairosvg)\n"
                "  Manual:      pip install cairosvg\n"
                "  Also needs the libcairo2 native library:\n"
                "    Linux:   sudo apt install libcairo2-dev\n"
                "    macOS:   brew install cairo\n"
                "    Windows: install the GTK3 runtime from\n"
                "             https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer"
            )
        png_path = out_path.with_suffix(".png")
        _cairosvg.svg2png(bytestring=svg_str.encode(), write_to=str(png_path))
        return png_path
    else:
        out_path.write_text(svg_str, encoding="utf-8")
        return out_path


def render_flow(
    flow: dict,
    output_path: str,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
    to_png: bool = False,
    folder_lookup: dict[str, str] | None = None,
    verbose: bool = True,
) -> "Path | None":
    """Render a single Homey flow as an SVG file.

    Dispatches based on flow type:
    - Advanced flows (with a ``cards`` DAG) are rendered using a two-pass layout:
      Pass 1 draws connection wires (behind), Pass 2 draws card bodies (on top).
    - Standard flows (trigger / conditions / actions columns) are delegated to
      ``render_standard_flow()``.

    Args:
        flow: Parsed flow JSON dict (from Homey local REST API backup).
        output_path: Destination file path (.svg or .png).
        device_lookup: UUID → device name mapping for label resolution.
        var_lookup: UUID → variable name mapping.
        zone_lookup: UUID → zone name mapping.
        cap_titles: ``{device_uuid: {cap_id: (title, units)}}`` for trigger-ref resolution.
        to_png: If True, output PNG via cairosvg instead of SVG (requires cairosvg).
    """
    cards: dict[str, dict] = flow.get("cards", {})
    if not isinstance(cards, dict):
        print(
            f"  ⚠ Flow '{flow.get('name', '?')}' has malformed 'cards' field "
            f"(expected dict, got {type(cards).__name__}), skipping.",
            file=sys.stderr,
        )
        return None
    if not cards:
        if flow.get("trigger") or flow.get("conditions") or flow.get("actions"):
            render_standard_flow(flow, output_path, device_lookup, var_lookup, zone_lookup, cap_titles, to_png, folder_lookup, verbose)
            return
        print("  ⚠ No cards in flow, skipping.", file=sys.stderr)
        return

    # Validate card structure — skip cards missing required geometry or type
    cards = {
        cid: c for cid, c in cards.items()
        if isinstance(c, dict) and "x" in c and "y" in c and "type" in c
    }
    if not cards:
        print(f"  ⚠ No valid cards in flow '{flow.get('name', '?')}', skipping.", file=sys.stderr)
        return

    # Build trigger→name map for [[trigger::CARD_ID::...]] resolution
    trigger_name_map, trigger_cap_map = _build_trigger_name_map(cards, zone_lookup, device_lookup, cap_titles)

    # Pre-compute labels then dimensions for every card
    card_labels = _compute_card_labels(cards, device_lookup, var_lookup, zone_lookup, trigger_name_map, trigger_cap_map)
    dims: dict[str, tuple[float, float]] = {
        cid: _card_dims(c, card_labels.get(cid)) for cid, c in cards.items()
    }

    # Canvas bounding box (accounts for varying card sizes)
    min_x = min(c["x"] for c in cards.values())
    min_y = min(c["y"] for c in cards.values())
    max_right  = max(c["x"] + dims[cid][0] for cid, c in cards.items())
    max_bottom = max(c["y"] + dims[cid][1] for cid, c in cards.items())

    canvas_w = (max_right - min_x) + PADDING * 2
    canvas_h = (max_bottom - min_y) + PADDING * 2 + TITLE_H

    # Ensure canvas is wide enough for the title bar (title + badge)
    raw_flow_name = flow.get("name", "Unnamed Flow")
    _folder_id = flow.get("folder")
    _folder_name = (folder_lookup or {}).get(_folder_id) if _folder_id else None
    flow_name = f"{_folder_name} / {raw_flow_name}" if _folder_name else raw_flow_name
    enabled_flag = flow.get("enabled", True)
    _badge_len = len("ENABLED" if enabled_flag else "DISABLED")
    title_w = PADDING + len(flow_name) * 11 + _badge_len * 8 + 80
    canvas_w = max(canvas_w, title_w)

    # Translate all cards so the top-left starts at PADDING
    ox = PADDING - min_x
    oy = PADDING - min_y + TITLE_H
    for c in cards.values():
        c["_rx"] = c["x"] + ox
        c["_ry"] = c["y"] + oy

    svg = SVGBuilder(canvas_w, canvas_h)

    # ── Defs: drop-shadow filter ──
    svg.add_def(
        '<filter id="shadow" x="-4%" y="-4%" width="112%" height="112%">'
        '<feDropShadow dx="1" dy="2" stdDeviation="3" '
        'flood-color="#000" flood-opacity="0.35"/>'
        "</filter>"
    )

    # ── Background ──
    svg.rect(0, 0, canvas_w, canvas_h, fill=CANVAS_BG)

    # Subtle dot-grid (Homey-style)
    for gx in range(0, int(canvas_w) + 1, 40):
        for gy in range(0, int(canvas_h) + 1, 40):
            svg.circle(gx, gy, 0.8, fill=GRID_COLOR, opacity="0.5")

    # ── Title bar ──
    name = flow_name  # already resolved with folder prefix above
    enabled = flow.get("enabled", True)
    badge = "ENABLED" if enabled else "DISABLED"
    badge_color = "#2ECC71" if enabled else "#E74C3C"

    svg.text(
        name, PADDING, 34,
        fill="#FFFFFF", font_size="20", font_weight="bold", font_family=FONT,
    )
    # Badge offset: rough estimate of title width
    badge_x = PADDING + len(name) * 11 + 24
    svg.rect(badge_x, 20, len(badge) * 8 + 16, 22, rx=4,
             fill=badge_color, opacity="0.15")
    svg.text(
        badge, badge_x + 8, 35,
        fill=badge_color, font_size="11", font_weight="700",
        font_family=FONT, letter_spacing="0.5",
    )

    # ── Pass 1: Draw connections (behind cards) ──
    # SVG uses the painter's model (later elements render on top). Wires must be
    # emitted first so card bodies occlude them at intersections — not the reverse.
    svg.comment("═══ Connections ═══")
    svg.group_open(id="connections")

    for cid, card in cards.items():
        cw, ch = dims[cid]
        src_right = card["_rx"] + cw
        src_cy = card["_ry"] + ch / 2
        is_cond = card["type"] == "condition"

        # Closure capturing src_right and src_cy from the enclosing loop iteration.
        # Each call draws bezier wires from this card's right-side output port.
        def _draw_wires(
            targets: list[str] | None,
            color: str,
            y_offset: float = 0,
        ) -> None:
            for tid in targets or []:
                if tid not in cards:
                    continue
                tw, th = dims[tid]
                dst_left = cards[tid]["_rx"]
                dst_cy = cards[tid]["_ry"] + th / 2
                svg.path(
                    _bezier(src_right, src_cy + y_offset, dst_left, dst_cy),
                    stroke=color, stroke_width="2.5", fill="none",
                    stroke_linecap="round", opacity="0.7",
                )

        _draw_wires(card.get("outputSuccess"), CONN_SUCCESS)
        if is_cond:
            _draw_wires(card.get("outputTrue"),  CONN_TRUE,  20 - ch / 2)
            _draw_wires(card.get("outputFalse"), CONN_FALSE, 36 - ch / 2)
        else:
            _draw_wires(card.get("outputTrue"),  CONN_TRUE,  0)
            _draw_wires(card.get("outputFalse"), CONN_FALSE, 0)
        _draw_wires(card.get("outputError"), CONN_ERROR, min(52, ch - 4) - ch / 2)

    svg.group_close()

    # ── Pass 2: Draw cards ──
    svg.comment("═══ Cards ═══")
    svg.group_open(id="cards")

    for cid, card in cards.items():
        ctype = card["type"]
        style = STYLES.get(ctype, STYLES["action"])
        cw, ch = dims[cid]
        x, y = card["_rx"], card["_ry"]
        label = card_labels.get(cid, "")

        # ── Note card (floating sticky) ──
        if ctype == "note":
            nfill = NOTE_FILLS.get(card.get("color", "yellow"), NOTE_FILLS["yellow"])
            svg.rect(x, y, cw, ch, rx=6,
                     fill=nfill, stroke="#00000018", stroke_width="1",
                     opacity="0.92")
            svg.text_multiline(
                label, x + 10, y + 18,
                max_chars=42, max_lines=6, line_h=15,
                fill=TEXT_DARK, font_size="11.5", font_family=FONT,
            )
            continue  # notes have no connection ports

        # ── Gate cards (ALL / ANY) ──
        if ctype in ("all", "any"):
            svg.rect(x, y, cw, ch, rx=CARD_RADIUS,
                     fill=style["fill"], stroke=style["stroke"],
                     stroke_width="2", filter="url(#shadow)")
            gate_label = "OR" if ctype == "any" else "AND"
            svg.text(
                gate_label, x + cw / 2, y + ch / 2 + 6,
                fill=style["accent"], font_size="16", font_weight="bold",
                font_family=FONT, text_anchor="middle",
            )

        # ── Start card ──
        elif ctype == "start":
            svg.rect(x, y, cw, ch, rx=CARD_RADIUS,
                     fill=style["fill"], stroke=style["stroke"],
                     stroke_width="2", filter="url(#shadow)")
            # Play-button triangle as SVG path (avoids font glyph issues)
            tri_x = x + cw / 2 - 20
            tri_y = y + ch / 2
            svg.path(
                f"M{tri_x - 4},{tri_y - 5} L{tri_x + 4},{tri_y} L{tri_x - 4},{tri_y + 5} Z",
                fill=style["accent"],
            )
            svg.text(
                "START", x + cw / 2 + 5, y + ch / 2 + 5,
                fill=style["accent"], font_size="13", font_weight="bold",
                font_family=FONT, text_anchor="middle",
            )

        # ── Delay card ──
        elif ctype == "delay":
            svg.rect(x, y, cw, ch, rx=CARD_RADIUS,
                     fill=style["fill"], stroke=style["stroke"],
                     stroke_width="1.5", filter="url(#shadow)")
            # Clock icon accent
            svg.circle(x + 20, y + ch / 2, 10,
                       fill="none", stroke=style["accent"],
                       stroke_width="1.5", opacity="0.6")
            svg.text(
                label, x + 38, y + ch / 2 + 5,
                fill=TEXT_LIGHT, font_size="13", font_family=FONT,
            )

        # ── Standard cards: trigger / condition / action ──
        else:
            svg.rect(x, y, cw, ch, rx=CARD_RADIUS,
                     fill=style["fill"], stroke=style["stroke"],
                     stroke_width="1.5", filter="url(#shadow)")

            # Left accent bar
            svg.rect(x + 1, y + 10, 3, ch - 20, rx=1.5,
                     fill=style["accent"])

            # Type badge (top-left) — prefix "NOT" for inverted conditions
            badge_text = _card_badge(card)
            if ctype == "condition" and card.get("inverted"):
                badge_text = f"NOT {badge_text}"
            svg.text(
                badge_text, x + 14, y + 17,
                fill=style["accent"], font_size="10", font_weight="700",
                font_family=FONT, letter_spacing="0.5", opacity="0.85",
            )

            # Main label — use multiline for full context
            display = label[:240] if len(label) > 240 else label
            svg.text_multiline(
                display, x + 14, y + 34,
                max_chars=45, max_lines=5, line_h=14,
                fill=TEXT_LIGHT, font_size="11.5", font_family=FONT,
            )

            # Port indicators — fixed offsets from card top
            if card.get("outputTrue"):
                svg.text(
                    "T", x + cw - 22, y + 22,
                    fill=CONN_TRUE, font_size="9", font_weight="700",
                    font_family=FONT, opacity="0.6",
                )
            if card.get("outputFalse"):
                svg.text(
                    "F", x + cw - 22, y + 38,
                    fill=CONN_FALSE, font_size="9", font_weight="700",
                    font_family=FONT, opacity="0.6",
                )
            if card.get("outputError"):
                svg.text(
                    "E", x + cw - 22, y + 54,
                    fill=CONN_ERROR, font_size="9", font_weight="700",
                    font_family=FONT, opacity="0.6",
                )

            # Disabled overlay
            if not flow.get("enabled", True):
                svg.rect(x, y, cw, ch, rx=CARD_RADIUS,
                         fill="#1E1E2E", opacity="0.5")

        # ── Connection port dots ──
        cy_mid = y + ch / 2
        is_cond = ctype == "condition"

        if card.get("outputSuccess"):
            svg.circle(x + cw, cy_mid, 5,
                       fill=CONN_SUCCESS, stroke="#FFFFFF30", stroke_width="1.5")
        if card.get("outputTrue"):
            py = (y + 20) if is_cond else cy_mid
            svg.circle(x + cw, py, 5,
                       fill=CONN_TRUE, stroke="#FFFFFF30", stroke_width="1.5")
        if card.get("outputFalse"):
            py = (y + 36) if is_cond else cy_mid
            svg.circle(x + cw, py, 5,
                       fill=CONN_FALSE, stroke="#FFFFFF30", stroke_width="1.5")
        if card.get("outputError"):
            py = y + 52
            svg.circle(x + cw, py, 5,
                       fill=CONN_ERROR, stroke="#FFFFFF30", stroke_width="1.5")

        # Input port (left side) — subtle marker
        svg.circle(x, cy_mid, 3.5,
                   fill="#FFFFFF10", stroke="#FFFFFF08", stroke_width="1")

    svg.group_close()

    # ── Write output to disk ──
    written = _write_output(svg.render(), Path(output_path), to_png)

    # Summary
    n = len(cards)
    types = sorted(set(c["type"] for c in cards.values()))
    if verbose:
        print(f"  ✓ {written}  ({canvas_w:.0f}×{canvas_h:.0f}px, "
              f"{n} cards [{', '.join(types)}])")
    return written


def render_standard_flow(
    flow: dict,
    output_path: str,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
    to_png: bool = False,
    folder_lookup: dict[str, str] | None = None,
    verbose: bool = True,
) -> "Path | None":
    """Render a standard (non-advanced) Homey flow as a 2-column SVG."""
    SVG_W = 640
    LABEL_X = 16
    LABEL_W = 110
    CARD_X = 144
    CARD_W = 480
    GAP = 12
    SECTION_GAP = 24

    def _synth_card(data: dict, ctype: str) -> dict:
        c = dict(data)
        c["type"] = ctype
        return c

    trigger_data = flow.get("trigger") or {}
    conditions = flow.get("conditions") or []
    actions = flow.get("actions") or []

    trigger_card = _synth_card(trigger_data, "trigger") if trigger_data else None
    condition_cards = [_synth_card(c, "condition") for c in conditions]
    action_cards = [_synth_card(a, "action") for a in actions]

    # Build trigger name/cap maps from the synthetic trigger card
    all_synth: dict[str, dict] = {}
    if trigger_card:
        all_synth["__trigger__"] = trigger_card
    trigger_name_map, trigger_cap_map = _build_trigger_name_map(
        all_synth, zone_lookup, device_lookup, cap_titles
    )

    def _label_for(card: dict) -> str:
        return _parse_label(card, device_lookup, var_lookup, zone_lookup, trigger_name_map, trigger_cap_map)

    def _card_h(label: str) -> float:
        body_max_chars = int((CARD_W - 24) / 6.5)
        lines = _word_wrap(label[:240], body_max_chars)
        n_lines = min(len(lines), 6)
        return max(60.0, 32 + n_lines * 16 + 12)

    # ── Compute layout ──
    y_cursor = 54.0  # space for title
    sections: list[tuple[str, float, list[tuple[dict, str, float]]]] = []

    if trigger_card:
        section_y = y_cursor
        t_label = _label_for(trigger_card)
        cards_in = [(trigger_card, t_label, y_cursor)]
        sections.append(("When", section_y, cards_in))
        y_cursor += max(_card_h(t_label), 40.0) + SECTION_GAP

    if condition_cards:
        section_y = y_cursor
        cards_in = []
        for cc in condition_cards:
            lbl = _label_for(cc)
            cards_in.append((cc, lbl, y_cursor))
            y_cursor += _card_h(lbl) + GAP
        y_cursor += SECTION_GAP - GAP
        sections.append(("And conditions", section_y, cards_in))

    if action_cards:
        section_y = y_cursor
        cards_in = []
        for ac in action_cards:
            lbl = _label_for(ac)
            cards_in.append((ac, lbl, y_cursor))
            y_cursor += _card_h(lbl) + GAP
        y_cursor += SECTION_GAP - GAP
        sections.append(("Then actions", section_y, cards_in))

    svg_h = y_cursor + 30
    # Resolve title with optional folder prefix
    raw_name = flow.get("name", "Unnamed Flow")
    _folder_id = flow.get("folder")
    _folder_name = (folder_lookup or {}).get(_folder_id) if _folder_id else None
    name = f"{_folder_name} / {raw_name}" if _folder_name else raw_name
    enabled = flow.get("enabled", True)
    badge = "ENABLED" if enabled else "DISABLED"
    badge_color = "#2ECC71" if enabled else "#E74C3C"
    # Ensure canvas is wide enough for the title bar
    _badge_len = len(badge)
    title_w = LABEL_X + len(name) * 9 + _badge_len * 8 + 80
    canvas_w = max(SVG_W, title_w)  # ensure title fits
    svg = SVGBuilder(canvas_w, svg_h)
    svg.add_def(
        '<filter id="shadow" x="-4%" y="-4%" width="112%" height="112%">'
        '<feDropShadow dx="1" dy="2" stdDeviation="3" '
        'flood-color="#000" flood-opacity="0.35"/>'
        "</filter>"
    )
    svg.rect(0, 0, canvas_w, svg_h, fill=CANVAS_BG)

    # Title (name, badge, badge_color computed above)

    svg.text(
        name, LABEL_X, 30,
        fill="#FFFFFF", font_size="16", font_weight="bold", font_family=FONT,
    )
    badge_x = LABEL_X + len(name) * 9 + 16
    svg.rect(badge_x, 16, len(badge) * 8 + 16, 22, rx=4,
             fill=badge_color, opacity="0.15")
    svg.text(
        badge, badge_x + 8, 30,
        fill=badge_color, font_size="11", font_weight="700",
        font_family=FONT, letter_spacing="0.5",
    )

    # Sections
    for section_label, section_y, cards_in_section in sections:
        # Label box
        svg.rect(LABEL_X, section_y, LABEL_W, 40, rx=6,
                 fill="#1e2332", stroke="#3a4056", stroke_width="1")
        svg.text(
            section_label, LABEL_X + LABEL_W / 2, section_y + 24,
            fill="#FFFFFF", font_size="10", font_weight="bold",
            font_family=FONT, text_anchor="middle",
        )
        # Cards
        for card, card_label, card_y in cards_in_section:
            ctype = card["type"]
            style = STYLES.get(ctype, STYLES["action"])
            c_h = _card_h(card_label)
            # Card background
            svg.rect(CARD_X, card_y, CARD_W, c_h, rx=CARD_RADIUS,
                     fill=style["fill"], stroke=style["stroke"],
                     stroke_width="1.5", filter="url(#shadow)")
            # Accent bar
            svg.rect(CARD_X + 1, card_y + 10, 3, c_h - 20, rx=1.5,
                     fill=style["accent"])
            # Badge
            badge_text = _card_badge(card)
            if ctype == "condition" and card.get("inverted"):
                badge_text = f"NOT {badge_text}"
            svg.text(
                badge_text, CARD_X + 14, card_y + 17,
                fill=style["accent"], font_size="10", font_weight="700",
                font_family=FONT, letter_spacing="0.5", opacity="0.85",
            )
            # Label
            body_max_chars = int((CARD_W - 24) / 6.5)
            svg.text_multiline(
                card_label, CARD_X + 14, card_y + 34,
                max_chars=body_max_chars, max_lines=6, line_h=14,
                fill=TEXT_LIGHT, font_size="11.5", font_family=FONT,
            )
            # Disabled overlay
            if not flow.get("enabled", True):
                svg.rect(CARD_X, card_y, CARD_W, c_h, rx=CARD_RADIUS,
                         fill="#1E1E2E", opacity="0.5")

    written = _write_output(svg.render(), Path(output_path), to_png)
    n_cards = (1 if trigger_card else 0) + len(condition_cards) + len(action_cards)
    if verbose:
        print(f"  ✓ {written}  ({canvas_w}×{svg_h:.0f}px, {n_cards} cards [standard flow])")
    return written
