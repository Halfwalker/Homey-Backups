#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["cairosvg>=2.7"]
# ///
"""
homey_flow_svg.py — Homey Flow → SVG/PNG Visualizer

Renders Homey flow JSON exports (both standard and advanced flows) as SVG
diagrams matching Homey's dark-themed visual editor style.
Run with `uv run homey_flow_svg.py` — uv auto-installs cairosvg (for --png).
Also needs the libcairo2 native library (Linux: `sudo apt install libcairo2-dev`).

Usage:
    python homey_flow_svg.py path/to/flow.json
    python homey_flow_svg.py path/to/flow.json -o custom-name.svg
    python homey_flow_svg.py Homey_Backups/flows/2026-04-22_13-52/*.json -d output/
    python homey_flow_svg.py flow.json --png

Card types handled: trigger, condition, action, note, all, any, start, delay
Connection types: outputSuccess (blue), outputTrue (green), outputFalse (amber), outputError (amber/orange)
"""

from __future__ import annotations

# ─── SVG Builder (canonical source: render_flows/_svg_builder.py) ─────
from render_flows._svg_builder import SVGBuilder  # noqa: F401 — re-exported for backward compat

# ─── Label parsing (canonical source: render_flows/_label_parser.py) ──
from render_flows._label_parser import (  # noqa: F401 — re-exported for backward compat
    _parse_label,
    _word_wrap,
)

# ─── Lookup builders (canonical source: render_flows/_lookups.py) ─────
from render_flows._lookups import (  # noqa: F401 — re-exported for backward compat
    _auto_discover_sibling,
    _build_folder_lookup,
    _stem_uuid,
)

# ─── Renderers (canonical source: render_flows/_renderers.py) ─────────
from render_flows._renderers import (  # noqa: F401 — re-exported for backward compat
    _bezier,
    _card_badge,
    _card_dims,
    _compute_card_labels,
    _write_output,
    render_flow,
    render_standard_flow,
)

# ─── CLI Entry Point (canonical source: render_flows/_cli.py) ─────────
from render_flows._cli import main  # noqa: F401 — re-exported for backward compat


if __name__ == "__main__":
    main()
