"""SVGBuilder — a minimal, zero-dependency SVG document builder.

Wraps primitive draw calls (rect, text, path …) behind a thin Python API
and serialises them to a valid SVG string via ``render()``.

Depends on ``_label_parser._word_wrap`` for multi-line text rendering.
Has no other internal package dependencies.
"""

# TODO: move SVGBuilder class from homey_flow_svg.py
