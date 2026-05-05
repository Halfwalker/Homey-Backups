"""render_flows — Homey Flow SVG/PNG rendering package.

Public API re-exported here. Internal modules use the ``_`` prefix and are
not part of the stable interface.

Typical usage::

    from render_flows import render_flow, render_standard_flow

    svg_text = render_flow(flow_json_path)
"""

from render_flows._cli import main
from render_flows._constants import __version__
from render_flows._renderers import render_flow, render_standard_flow
from render_flows._svg_builder import SVGBuilder

__all__ = [
    "__version__",
    "main",
    "render_flow",
    "render_standard_flow",
    "SVGBuilder",
]
