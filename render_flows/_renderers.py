"""Flow rendering functions and SVG geometry helpers.

Contains the two public rendering entry points (``render_flow`` for advanced
flows and ``render_standard_flow`` for standard flows) plus the private
helpers they rely on (_card_badge, _card_dims, _bezier, _compute_card_labels,
_write_output).

This module sits at the top of the internal dependency graph:
it imports from _constants, _svg_builder, _label_parser, and _lookups but
nothing imports from it except __init__ and _cli.
"""

# TODO: move _card_badge, _compute_card_labels, _card_dims, _bezier,
#       _write_output, render_flow, render_standard_flow
#       from homey_flow_svg.py
