"""SVGBuilder — a minimal, zero-dependency SVG document builder.

Wraps primitive draw calls (rect, text, path …) behind a thin Python API
and serialises them to a valid SVG string via ``render()``.

Depends on ``_label_parser._word_wrap`` for multi-line text rendering.
Has no other internal package dependencies.
"""

import html

from render_flows._label_parser import _word_wrap


class SVGBuilder:
    """Builds an SVG document from primitive draw calls.
    Uses only Python stdlib (html.escape for text safety)."""

    def __init__(self, width: float, height: float) -> None:
        self.w = width
        self.h = height
        self._defs: list[str] = []
        self._body: list[str] = []

    @staticmethod
    def _attrs(**kw: object) -> str:
        """Convert Python kwargs to SVG attribute string.
        Underscores become hyphens: font_size → font-size."""
        parts: list[str] = []
        for k, v in kw.items():
            if v is None:
                continue
            attr = k.replace("_", "-")
            parts.append(f'{attr}="{v}"')
        return " ".join(parts)

    def add_def(self, raw_xml: str) -> None:
        self._defs.append(raw_xml)

    def rect(self, x: float, y: float, w: float, h: float,
             rx: float = 0, **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {a}/>'
        )

    def circle(self, cx: float, cy: float, r: float, **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" {a}/>')

    def path(self, d: str, **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(f'<path d="{d}" {a}/>')

    def line(self, x1: float, y1: float, x2: float, y2: float,
             **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {a}/>'
        )

    def text(self, content: str, x: float, y: float, **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(
            f'<text x="{x}" y="{y}" {a}>{html.escape(content)}</text>'
        )

    def text_multiline(self, content: str, x: float, y: float,
                       max_chars: int = 42, max_lines: int = 6,
                       line_h: float = 15, **kw: object) -> None:
        """Render word-wrapped text using <tspan> elements."""
        a = self._attrs(**kw)
        all_lines = _word_wrap(content, max_chars)
        lines = all_lines[:max_lines]
        if len(lines) < len(all_lines):
            lines[-1] = lines[-1][: max_chars] + "…"
        spans = ""
        for i, ln in enumerate(lines):
            dy = f' dy="{line_h}"' if i > 0 else ""
            spans += f'<tspan x="{x}"{dy}>{html.escape(ln)}</tspan>'
        self._body.append(f'<text x="{x}" y="{y}" {a}>{spans}</text>')

    def group_open(self, **kw: object) -> None:
        a = self._attrs(**kw)
        self._body.append(f"<g {a}>")

    def group_close(self) -> None:
        self._body.append("</g>")

    def comment(self, msg: str) -> None:
        self._body.append(f"<!-- {msg} -->")

    def render(self) -> str:
        defs = "\n    ".join(self._defs)
        body = "\n  ".join(self._body)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg"\n'
            f'     width="{self.w}" height="{self.h}"\n'
            f'     viewBox="0 0 {self.w} {self.h}">\n'
            f"  <defs>\n    {defs}\n  </defs>\n"
            f"  {body}\n"
            f"</svg>\n"
        )
