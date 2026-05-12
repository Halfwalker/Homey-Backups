"""Visual constants for Homey flow rendering.

All colours, fonts, layout dimensions, and per-card-type style tables live
here.  Imported by ``_renderers``, ``_cli``, and ``__init__``; the other
internal modules (``_label_parser``, ``_svg_builder``, ``_lookups``) are
independent of these values.  Nothing in this module imports from the rest
of the package (it is a leaf node in the dependency graph).

Colour values match Homey's dark-themed visual editor style so that
rendered SVGs feel native to the Homey UI.
"""

from __future__ import annotations

# ─── Version ─────────────────────────────────────────────────────────

__version__ = "0.3.4"

# ─── Canvas ──────────────────────────────────────────────────────────

CANVAS_BG  = "#1E1E2E"
GRID_COLOR = "#2A2A3A"

# ─── Card dimensions ─────────────────────────────────────────────────

# Base (width, height) per card type.  Height for trigger/condition/action
# is the minimum; the actual height grows dynamically with the label text.
# "note" height is always 0 here because it is computed entirely from content.
CARD_DIMS: dict[str, tuple[int, int]] = {
    "trigger":   (340, 72),
    "condition": (340, 72),
    "action":    (340, 72),
    "any":       (79, 52),
    "all":       (79, 52),
    "start":     (79, 52),
    "delay":     (220, 64),
    "note":      (320, 0),
}

CARD_RADIUS = 10

# ─── Per-type card styles ────────────────────────────────────────────

# Each entry maps a card type to its visual style:
#   fill   — card background colour
#   stroke — card border colour
#   accent — type-label bar / badge colour
# Colours are chosen to match Homey's dark editor palette.
STYLES: dict[str, dict[str, str]] = {
    "trigger":   {"fill": "#162B1F", "stroke": "#27AE60", "accent": "#2ECC71"},
    "condition": {"fill": "#162232", "stroke": "#2980B9", "accent": "#3498DB"},
    "action":    {"fill": "#321E16", "stroke": "#D35400", "accent": "#E67E22"},
    "any":       {"fill": "#32291A", "stroke": "#E67E22", "accent": "#F39C12"},
    "all":       {"fill": "#1A2432", "stroke": "#2980B9", "accent": "#3498DB"},
    "start":     {"fill": "#162B1F", "stroke": "#27AE60", "accent": "#2ECC71"},
    "delay":     {"fill": "#24163A", "stroke": "#8E44AD", "accent": "#9B59B6"},
    "note":      {"fill": "#FFF9C4", "stroke": "#F9A82520", "accent": "#F9A825"},
}

# Note cards can carry an explicit colour attribute; map it to a fill hex.
NOTE_FILLS: dict[str, str] = {
    "yellow": "#FFF9C4",
    "red":    "#FFCDD2",
    "green":  "#C8E6C9",
    "blue":   "#BBDEFB",
    "purple": "#E1BEE7",
    "grey":   "#CFD8DC",
    "gray":   "#CFD8DC",
}

# ─── Connection / wire colours ────────────────────────────────────────

# Each output port type gets its own wire colour so the flow direction is
# obvious at a glance without reading port labels.
CONN_SUCCESS = "#3498DB"   # outputSuccess → blue
CONN_TRUE    = "#2ECC71"   # outputTrue    → green
CONN_FALSE   = "#f59e0b"   # outputFalse   → amber
CONN_ERROR   = "#F39C12"   # outputError   → amber/orange

# ─── Text ────────────────────────────────────────────────────────────

TEXT_LIGHT = "#D4D4D8"   # primary text on dark card backgrounds
TEXT_DARK  = "#1E1E2E"   # text on light surfaces (note cards)

# ─── Layout ──────────────────────────────────────────────────────────

FONT    = "'Inter','Segoe UI',system-ui,sans-serif"
PADDING = 80    # canvas padding around the outermost cards (px)
TITLE_H = 50    # vertical space reserved for the flow title bar (px)
