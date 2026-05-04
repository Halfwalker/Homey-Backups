"""Label parsing and token resolution for Homey flow cards.

Homey flow cards carry structured ``args`` dicts whose values are often
URI-encoded references to devices, zones, or variables rather than plain
strings.  The functions here resolve those references into human-readable
labels suitable for display in the rendered SVG.

Leaf node: imports only from the Python stdlib (``re``).  No other module in
this package imports from this one except ``_svg_builder`` (for ``_word_wrap``).
"""

# TODO: move _word_wrap, _resolve_placeholders, _resolve_uri_refs,
#       _resolve_trigger_refs, _parse_label from homey_flow_svg.py
