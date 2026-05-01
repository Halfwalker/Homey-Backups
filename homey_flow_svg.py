#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# Note: --png requires cairosvg. Run with: uv run --with cairosvg homey_flow_svg.py [args]
"""
homey_flow_svg.py — Homey Flow → SVG/PNG Visualizer

Renders Homey flow JSON exports (both standard and advanced flows) as SVG
diagrams matching Homey's dark-themed visual editor style. Zero required
external dependencies (optional cairosvg for --png export).

Usage:
    python homey_flow_svg.py path/to/flow.json
    python homey_flow_svg.py path/to/flow.json -o custom-name.svg
    python homey_flow_svg.py Homey_Backups/flows/2026-04-22_13-52/*.json -d output/
    python homey_flow_svg.py flow.json --png

Card types handled: trigger, condition, action, note, all, any, start, delay
Connection types: outputSuccess (blue), outputTrue (green), outputFalse (amber), outputError (amber/orange)
"""

from __future__ import annotations

import argparse
import html
import json
import re as _re
import sys
from pathlib import Path

try:
    import cairosvg as _cairosvg
except ImportError:
    _cairosvg = None

# ─── Version ─────────────────────────────────────────────────────────

__version__ = "0.1.0"

# ─── Homey Visual Constants ──────────────────────────────────────────

CANVAS_BG  = "#1E1E2E"
GRID_COLOR = "#2A2A3A"

# Card dimensions by type → (width, height)
# Note height is dynamic (computed from text length)
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

# Per-type colors  (fill=card bg, stroke=border, accent=type label/bar)
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

NOTE_FILLS: dict[str, str] = {
    "yellow": "#FFF9C4",
    "red":    "#FFCDD2",
    "green":  "#C8E6C9",
    "blue":   "#BBDEFB",
    "purple": "#E1BEE7",
    "grey":   "#CFD8DC",
    "gray":   "#CFD8DC",
}

# Connection / wire colors
CONN_SUCCESS = "#3498DB"   # outputSuccess → blue
CONN_TRUE    = "#2ECC71"   # outputTrue    → green
CONN_FALSE   = "#f59e0b"   # outputFalse   → amber
CONN_ERROR   = "#F39C12"   # outputError   → amber/orange

TEXT_LIGHT = "#D4D4D8"
TEXT_DARK  = "#1E1E2E"
TEXT_MUTED = "#71717A"

FONT = "'Inter','Segoe UI',system-ui,sans-serif"
PADDING = 80
TITLE_H = 50


# ─── SVG Builder (zero external dependencies) ────────────────────────

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
        lines = _word_wrap(content, max_chars)[:max_lines]
        all_lines = _word_wrap(content, max_chars)
        if len(lines) < len(all_lines):
            lines[-1] = lines[-1][: max_chars - 1] + "…"
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


# ─── Helpers ──────────────────────────────────────────────────────────

def _word_wrap(text: str, max_chars: int) -> list[str]:
    """Break text into lines of at most max_chars, splitting on words."""
    text = text.replace("\n", " ").strip()
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


# ─── Token Resolution ─────────────────────────────────────────────────────────
# Homey flow card titles use three distinct placeholder formats:
#
#   [[key]]                      — simple arg substitution (resolved from card.args)
#   [[scheme:...|ref]]           — URI reference, e.g.:
#                                  [[homey:manager:logic|<uuid>]]     → Logic variable
#                                  [[homey:device:<uuid>|<cap>]]      → Device capability
#                                  [[homey:zone:<uuid>]]              → Zone name
#                                  [[homey:app:net.i-dev.betterlogic|<name>]] → BLL variable
#   [[trigger::card_id::cap]]    — cross-card reference to a trigger card's capability value
#
# Each format is handled by a dedicated resolver below.
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_placeholders(text: str, args: dict | None) -> str:
    """Replace [[key]] placeholders with their value from args, if available."""
    if not args:
        return text

    def _sub(m: "_re.Match[str]") -> str:
        key = m.group(1)
        val = args.get(key)
        if val is None:
            return m.group(0)  # leave untouched
        if isinstance(val, dict):
            return str(val.get("name", val))
        return str(val)

    return _re.sub(r"\[\[([^\]|]+)\]\]", _sub, text)


def _resolve_uri_refs(text: str, var_lookup: dict[str, str] | None = None) -> str:
    """Replace Homey URI tokens in *text* with human-readable labels.

    Handles three patterns:
    - ``[[homey:manager:logic|<uuid>]]``  → ``[var:<name>]`` (or ``[var:<uuid[:8]>]`` if not in lookup)
    - ``[[homey:app:net.i-dev.betterlogic|<name>]]`` → ``[bll:<name>]`` (underscores → spaces)
    - All other ``[[homey:...|...]]`` tokens → left unchanged (device refs handled elsewhere)
    """
    def _sub(m: "_re.Match[str]") -> str:
        full = m.group(0)
        scheme = m.group(1)   # e.g. "homey:manager:logic"
        ref = m.group(2)       # e.g. uuid or variable name

        if scheme == "homey:manager:logic":
            name = (var_lookup or {}).get(ref, "")
            if name:
                return name
            return f"var:{ref[:8]}"

        if scheme == "homey:app:net.i-dev.betterlogic":
            return f"BLL({ref})"

        if scheme == "homey:manager:cron":
            _cron_labels = {
                "date": "Current date",
                "time": "Current time",
                "sun_state": "Sun state",
            }
            return _cron_labels.get(ref, ref.replace("_", " ").title())

        if scheme.startswith("homey:device:"):
            cap_title = ref
            if cap_title.startswith("measure_"):
                cap_title = cap_title[len("measure_"):]
            cap_title = cap_title.replace("_", " ").title()
            return f"*{cap_title}"

        return full   # leave unrecognized refs untouched

    return _re.sub(
        r"\[\[([^\]|]+)\|([^\]]+)\]\]",
        _sub,
        text,
    )


def _resolve_trigger_refs(
    text: str,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> str:
    """Replace [[trigger::CARD_ID::FIELD]] tokens with capability label or entity name."""
    if "[[trigger::" not in text:
        return text
    if not trigger_name_map and not trigger_cap_map:
        return text

    def _sub(m: "_re.Match[str]") -> str:
        card_id = m.group(1)
        field = m.group(2)
        if trigger_cap_map:
            cap_label = trigger_cap_map.get(f"{card_id}::{field}")
            if cap_label:
                return cap_label
        name = (trigger_name_map or {}).get(card_id, "")
        if name:
            return f"{name}:{field}"
        return f"[{card_id[:8]}:{field}]"

    return _re.sub(r"\[\[trigger::([^:]+)::([^\]]+)\]\]", _sub, text)


_UUID_RE = _re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _stem_uuid(stem: str) -> str | None:
    """Extract a UUID from a filename stem (e.g. 'my-device-<uuid>'), or return None."""
    m = _UUID_RE.search(stem)
    return m.group(0) if m else None


def _build_variable_lookup(variables_dir: Path) -> dict[str, str]:
    """Scan *variables_dir* for backup JSON files and return a mapping of
    variable_uuid → human_name (for Homey Logic vars) and
    bll_id → human_name (for BLL vars).
    """
    lookup: dict[str, str] = {}
    if not variables_dir or not variables_dir.is_dir():
        return lookup

    for fpath in variables_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        var_id = data.get("id") or data.get("_id") or _stem_uuid(fpath.stem)
        if var_id:
            lookup[var_id] = name
    return lookup


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


def _parse_label(
    card: dict,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> str:
    """Extract a human-readable label from card JSON data.

    Supports two formats:
    - Rich (get_advanced_flow): card has a nested ``card`` sub-key with
      ``titleFormatted``, ``title``, ``args``, ``ownerUri``, etc.
    - Compact (list_flows): plain fields directly on the card dict.
    """
    ctype = card["type"]

    if ctype == "note":
        return card.get("value", "")
    if ctype == "start":
        return "Start"
    if ctype == "delay":
        d = (card.get("args") or {}).get("delay", {})
        n = d.get("number", "?")
        m = int(d.get("multiplier", 1))
        unit = {1: "sec", 60: "min", 3600: "hr"}.get(m, f"×{m}s")
        return f"Delay {n} {unit}"
    if ctype == "any":
        return "OR"
    if ctype == "all":
        return "AND"

    # ── Rich format: card has a nested "card" object ─────────────────────
    rich = card.get("card")
    if isinstance(rich, dict):
        args = rich.get("args") or card.get("args") or {}
        # Prefer titleFormatted (may contain [[placeholder]] patterns)
        label = rich.get("titleFormatted") or rich.get("title") or ""
        if label:
            label = _resolve_placeholders(label, args)
            label = _resolve_uri_refs(label, var_lookup)

        # Prepend device/owner name when available
        owner_uri = rich.get("ownerUri") or ""
        if owner_uri and device_lookup:
            # ownerUri may be "homey:device:<uuid>" or just a uuid
            uuid_part = owner_uri.split(":")[-1]
            device_name = (
                device_lookup.get(owner_uri)
                or device_lookup.get(uuid_part)
                or ""
            )
            if device_name and device_name not in label:
                label = f"{device_name}  {label}" if label else device_name

        if label:
            return label.strip()

    # ── Compact format fallback ───────────────────────────────────────────
    # ── droptoken: variable-testing conditions (e.g. equal_boolean) ──────
    droptoken = card.get("droptoken")
    if droptoken and isinstance(droptoken, str) and "|" in droptoken:
        dt_scheme, _, dt_ref = droptoken.partition("|")
        if dt_scheme == "homey:manager:logic":
            dt_name = (var_lookup or {}).get(dt_ref, "")
            if dt_name:
                card_id_str = card.get("id", "")
                if "equal_boolean" in card_id_str:
                    return f"{dt_name}  ==  yes"
                # For comparison ops (gt, lt, gte, lte, eq, ne, between), fall through to logic handler
                _cmp_ops = ("lt", "gt", "gte", "lte", "eq", "ne", "between")
                if card_id_str.startswith("homey:manager:logic:") and \
                        card_id_str.rsplit(":", 1)[-1] in _cmp_ops:
                    pass  # handled by logic comparison block below
                else:
                    return dt_name
            # Not in lookup — fall through to ID-based label
        elif "betterlogic" in dt_scheme:
            return dt_ref.replace("_", " ")

    # ── Cron card special labels ─────────────────────────────────────────
    card_id_str = card.get("id", "")

    # ── Logic comparison conditions ───────────────────────────────────────
    _LOGIC_OPS = {"lt": "<", "gt": ">", "gte": "≥", "lte": "≤", "eq": "=", "ne": "≠"}
    if card_id_str.startswith("homey:manager:logic:"):
        op_key = card_id_str.rsplit(":", 1)[-1]
        if op_key in _LOGIC_OPS or op_key == "between":
            # Resolve left-hand side from droptoken
            lhs = "?"
            dt = card.get("droptoken", "")
            if dt and "|" in dt:
                dt_scheme, _, dt_ref = dt.partition("|")
                if "homey:manager:logic" in dt_scheme:
                    lhs = (var_lookup or {}).get(dt_ref, dt_ref[:8])
                else:
                    lhs = dt_ref.replace("_", " ").capitalize()
            # Resolve right-hand side from args.comparator
            a = card.get("args") or {}
            rhs_raw = a.get("comparator", "?")
            if isinstance(rhs_raw, str) and "[[" in rhs_raw:
                rhs = _resolve_uri_refs(rhs_raw, var_lookup)
            else:
                rhs = str(rhs_raw)
            if op_key == "between":
                rhs2_raw = a.get("comparator2", "?")
                if isinstance(rhs2_raw, str) and "[[" in rhs2_raw:
                    rhs2 = _resolve_uri_refs(rhs2_raw, var_lookup)
                else:
                    rhs2 = str(rhs2_raw)
                return f"{lhs} between {rhs} and {rhs2}"
            return f"{lhs} {_LOGIC_OPS[op_key]} {rhs}"
    if "homey:manager:cron:" in card_id_str:
        cron_type = card_id_str.split("homey:manager:cron:")[-1]
        cron_args = card.get("args") or {}
        if cron_type == "sunset":
            before = cron_args.get("before", 0)
            return f"Sun sets in {before} minutes"
        if cron_type == "sunrise":
            before = cron_args.get("before", 0)
            return f"Sun rises in {before} minutes"
        if cron_type == "time_exactly":
            t = cron_args.get("time", "?")
            return f"At {t}"
        if cron_type == "after_sunrise":
            return "After sunrise"
        if cron_type == "after_sunset":
            return "After sunset"
        if cron_type == "before_sunrise":
            before = cron_args.get("before", 0)
            return f"{before} min before sunrise"
        if cron_type == "before_sunset":
            before = cron_args.get("before", 0)
            return f"{before} min before sunset"
        # Unknown cron type — fall through to ID-based label

    # ── Zone trigger ─────────────────────────────────────────────────────
    if card_id_str.startswith("homey:zone:"):
        parts = card_id_str.split(":")
        if len(parts) >= 4:
            zone_uuid = parts[2]
            cap_state = parts[3]
            zone_name = (zone_lookup or {}).get(zone_uuid, zone_uuid[:8])
            cap_args_val = (card.get("args") or {}).get("capability", {})
            cap_name = cap_args_val.get("name", "") if isinstance(cap_args_val, dict) else ""
            state_str = "is false" if cap_state.endswith("_false") else "is true"
            if cap_name:
                return f"{zone_name}: {cap_name} {state_str}"
            return f"{zone_name}: {cap_state.replace('_', ' ')}"

    # ── Aqara FP2 presence zone triggers ─────────────────────────────────
    if ctype == "trigger" and ":alarm_motion_new_true" in card_id_str:
        zone_arg = (card.get("args") or {}).get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            return f"{zone_name} occupied"

    if ctype == "trigger" and ":alarm_motion_new_false" in card_id_str:
        zone_arg = (card.get("args") or {}).get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            return f"{zone_name} unoccupied"

    if ctype == "trigger" and ":motion_inactive_new" in card_id_str:
        a = card.get("args") or {}
        zone_arg = a.get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            minutes = a.get("minutes", "?")
            timeunit = a.get("timeunit", "seconds")
            return f"{zone_name} is {minutes} {timeunit} inactive"

    # ── BLL variable_contains condition ──────────────────────────────────
    if "net.i-dev.betterlogic:variable_contains" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        raw_val = a.get("value", "?")
        if isinstance(raw_val, str):
            raw_val = _resolve_trigger_refs(raw_val, trigger_name_map, trigger_cap_map)
            raw_val = _resolve_uri_refs(raw_val, var_lookup)
        return f"'{var_name}' contains '{raw_val}'"

    # ── BLL execute_bl_expression action ────────────────────────────────
    if "net.i-dev.betterlogic:execute_bl_expression" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        expr = str(a.get("expression", ""))
        expr = _resolve_trigger_refs(expr, trigger_name_map, trigger_cap_map)
        expr = _resolve_uri_refs(expr, var_lookup)
        return f"Set {var_name} to {expr}"

    # ── Notification / Timeline action ───────────────────────────────────
    if "homey:manager:notifications:create_notification" in card_id_str:
        a = card.get("args") or {}
        text_val = str(a.get("text", ""))
        text_val = _resolve_trigger_refs(text_val, trigger_name_map, trigger_cap_map)
        text_val = _resolve_uri_refs(text_val, var_lookup)
        return text_val

    # ── Mobile push notification action ──────────────────────────────────
    if "homey:manager:mobile:" in card_id_str and "push" in card_id_str:
        a = card.get("args") or {}
        user_dict = a.get("user")
        user_name = user_dict.get("name", "") if isinstance(user_dict, dict) else ""

        # push_image: resolve device from droptoken
        if "push_image" in card_id_str:
            dt = card.get("droptoken", "")
            img_source = ""
            if dt and "|" in dt:
                dt_scheme, _, dt_ref = dt.partition("|")
                if dt_scheme.startswith("homey:device:") and device_lookup:
                    dev_uuid = dt_scheme.split(":")[2]
                    img_source = (
                        device_lookup.get(dev_uuid)
                        or device_lookup.get(dt_scheme)
                        or f"device:{dev_uuid[:8]}"
                    )
                if not img_source:
                    img_source = dt_ref.replace("-", " ").replace("_", " ")
            target = f"to {user_name}" if user_name else ""
            return f"Send image {img_source} {target}".strip() if img_source else f"Push image {target}".strip()

        text_val = str(a.get("text", ""))
        text_val = _resolve_trigger_refs(text_val, trigger_name_map, trigger_cap_map)
        text_val = _resolve_uri_refs(text_val, var_lookup)
        if user_name:
            return f"→ {user_name}: {text_val}" if text_val else f"→ {user_name}"
        return text_val or "Push notification"

    # ── Logic variable-set actions ────────────────────────────────────────
    if "homey:manager:logic:variable_set" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        value = str(a.get("value", ""))
        value = _resolve_uri_refs(value, var_lookup)
        # Strip {{...}} math-expression wrapper
        if value.startswith("{{") and value.endswith("}}"):
            value = value[2:-2]
        return f"{var_name} = {value}"

    card_id = card.get("id") or ""
    parts = card_id.split(":")
    capability = parts[-1] if parts else "unknown"
    capability = capability.replace("_", " ").title()

    # Prepend device/owner name when available
    owner_uri = card.get("ownerUri") or ""
    device_name = ""
    if device_lookup:
        if owner_uri:
            uuid_part = owner_uri.split(":")[-1]
            device_name = (
                device_lookup.get(owner_uri)
                or device_lookup.get(uuid_part)
                or ""
            )
        # Fallback: extract device UUID from card ID (homey:device:<uuid>:<cap>)
        if not device_name and card_id.startswith("homey:device:") and len(parts) >= 4:
            dev_uuid = parts[2]
            device_name = (
                device_lookup.get(dev_uuid)
                or device_lookup.get(f"homey:device:{dev_uuid}")
                or ""
            )
    if device_name and device_name not in capability:
        capability = f"{device_name}  {capability}"

    args = card.get("args")
    if args and isinstance(args, dict):
        snippets: list[str] = []

        # Combine duration + unit into one snippet when both are present
        if "duration" in args and "unit" in args:
            dur_val = str(args['duration'])
            if "[[" in dur_val:
                dur_val = _resolve_uri_refs(dur_val, var_lookup)
                dur_val = _resolve_trigger_refs(dur_val, trigger_name_map, trigger_cap_map)
            snippets.append(f"{dur_val} {args['unit']}")
            remaining = [(k, v) for k, v in args.items() if k not in ("duration", "unit")]
        else:
            remaining = list(args.items())

        for k, v in remaining[:3]:   # allow up to 3 remaining args
            if isinstance(v, dict) and "name" in v:
                snippets.append(str(v["name"]))
            elif isinstance(v, str) and v.startswith("[["):
                resolved = _resolve_uri_refs(v, var_lookup)
                resolved = _resolve_trigger_refs(resolved, trigger_name_map, trigger_cap_map)
                snippets.append(resolved)
            elif not isinstance(v, (dict, list)):
                val_str = str(v)
                if "[[" in val_str:
                    val_str = _resolve_uri_refs(val_str, var_lookup)
                    val_str = _resolve_trigger_refs(val_str, trigger_name_map, trigger_cap_map)
                snippets.append(val_str)

        if snippets:
            capability += f"  ({', '.join(snippets)})"

    return capability


def _build_device_lookup(devices_dir: Path) -> dict[str, str]:
    """Scan *devices_dir* for ``*-<uuid>.json`` files and build a mapping of
    ``uuid → device name`` (and ``homey:device:<uuid> → name``).

    Returns an empty dict if the directory does not exist or has no matches.
    """
    lookup: dict[str, str] = {}
    if not devices_dir or not devices_dir.is_dir():
        return lookup

    for fpath in devices_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        # ID may be in the filename suffix (<slug>-<uuid>.json) or in the JSON
        device_id = (
            data.get("id") or data.get("_id")
            # fallback: extract UUID from filename stem (<slug>-<uuid>.json)
            or _stem_uuid(fpath.stem)
        )
        if device_id:
            lookup[device_id] = name
            lookup[f"homey:device:{device_id}"] = name

    return lookup


def _build_cap_titles(devices_dir: "Path | None") -> "dict[str, dict[str, tuple[str, str]]]":
    """Scan *devices_dir* and return {device_uuid: {cap_id: (title, unit)}}."""
    result: dict[str, dict[str, tuple[str, str]]] = {}
    if not devices_dir or not devices_dir.is_dir():
        return result
    for fpath in devices_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        device_id = data.get("id") or data.get("_id") or ""
        if not device_id:
            continue
        caps_obj = data.get("capabilitiesObj") or {}
        cap_map: dict[str, tuple[str, str]] = {}
        for cap_id, cap_info in caps_obj.items():
            if isinstance(cap_info, dict):
                title = cap_info.get("title", "")
                units = cap_info.get("units") or ""
                if title:
                    cap_map[cap_id] = (title, units)
        if cap_map:
            result[device_id] = cap_map
    return result


def _build_zone_lookup(zones_dir: Path) -> dict[str, str]:
    """Scan *zones_dir* for backup JSON files; return uuid → zone_name mapping."""
    lookup: dict[str, str] = {}
    if not zones_dir or not zones_dir.is_dir():
        return lookup
    for fpath in zones_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        zone_id = (
            data.get("id") or data.get("_id")
            or _stem_uuid(fpath.stem)
        )
        if zone_id:
            lookup[zone_id] = name
            lookup[f"homey:zone:{zone_id}"] = name
    return lookup


def _build_trigger_name_map(
    cards: dict[str, dict],
    zone_lookup: dict[str, str] | None = None,
    device_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
) -> "tuple[dict[str, str], dict[str, str]]":
    """Map trigger card_id → resolved entity name, and build capability ref map.

    Returns:
        (trigger_name_map, trigger_cap_map) where trigger_cap_map maps
        "card_uuid::cap_id" → formatted label like "*Snow (mm)".
    """
    result: dict[str, str] = {}
    cap_map: dict[str, str] = {}
    for cid, card in cards.items():
        if card.get("type") != "trigger":
            continue
        card_id_str = card.get("id", "")
        name = ""
        device_uuid = ""
        if card_id_str.startswith("homey:zone:"):
            parts = card_id_str.split(":")
            if len(parts) >= 4:
                name = (zone_lookup or {}).get(parts[2], "")
        elif card_id_str.startswith("homey:device:"):
            parts = card_id_str.split(":")
            if len(parts) >= 4:
                device_uuid = parts[2]
                name = (device_lookup or {}).get(device_uuid, "")
        if not name:
            owner_uri = card.get("ownerUri") or ""
            if owner_uri.startswith("homey:zone:"):
                name = (zone_lookup or {}).get(owner_uri.split(":")[-1], "")
            elif owner_uri.startswith("homey:device:"):
                device_uuid = owner_uri.split(":")[-1]
                name = (device_lookup or {}).get(device_uuid, "")
        if name:
            result[cid] = name
        # Build capability map: "card_uuid::cap_id" → "*Title (unit)"
        if device_uuid and cap_titles:
            dev_caps = cap_titles.get(device_uuid)
            if dev_caps:
                for cap_id, (title, unit) in dev_caps.items():
                    label = f"*{title} ({unit})" if unit else f"*{title}"
                    cap_map[f"{cid}::{cap_id}"] = label
    return result, cap_map


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
                "  Install it:  pip install cairosvg\n"
                "  Also needs the libcairo2 native library:\n"
                "    macOS:   brew install cairo\n"
                "    Linux:   sudo apt install libcairo2-dev\n"
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
) -> None:
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
    if not cards:
        if flow.get("trigger") or flow.get("conditions") or flow.get("actions"):
            render_standard_flow(flow, output_path, device_lookup, var_lookup, zone_lookup, cap_titles, to_png)
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
    flow_name = flow.get("name", "Unnamed Flow")
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
    name = flow.get("name", "Unnamed Flow")
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
        _draw_wires(card.get("outputError"), CONN_ERROR, 52 - ch / 2)

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
            if ctype == "trigger" and not flow.get("enabled", True):
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
    print(f"  ✓ {written}  ({canvas_w:.0f}×{canvas_h:.0f}px, "
          f"{n} cards [{', '.join(types)}])")


def render_standard_flow(
    flow: dict,
    output_path: str,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
    to_png: bool = False,
) -> None:
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
    svg = SVGBuilder(SVG_W, svg_h)
    svg.add_def(
        '<filter id="shadow" x="-4%" y="-4%" width="112%" height="112%">'
        '<feDropShadow dx="1" dy="2" stdDeviation="3" '
        'flood-color="#000" flood-opacity="0.35"/>'
        "</filter>"
    )
    svg.rect(0, 0, SVG_W, svg_h, fill=CANVAS_BG)

    # Title
    name = flow.get("name", "Unnamed Flow")
    enabled = flow.get("enabled", True)
    badge = "ENABLED" if enabled else "DISABLED"
    badge_color = "#2ECC71" if enabled else "#E74C3C"

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

    written = _write_output(svg.render(), Path(output_path), to_png)
    n_cards = (1 if trigger_card else 0) + len(condition_cards) + len(action_cards)
    print(f"  ✓ {written}  ({SVG_W}×{svg_h:.0f}px, {n_cards} cards [standard flow])")


# ─── CLI Entry Point ─────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render Homey flow JSON files (standard and advanced) as SVG/PNG diagrams",
        epilog=(
            "Examples:\n"
            "  python homey_flow_svg.py flow.json\n"
            "  python homey_flow_svg.py flow.json -o diagram.svg\n"
            "  python homey_flow_svg.py flows/*.json -d svg_output/\n"
            "  python homey_flow_svg.py flows/*.json -d svg_output/ "
            "--devices-dir devices/2026-04-22_13-52/\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("inputs", nargs="+", help="Homey flow JSON file(s)")
    ap.add_argument("-o", "--output",
                    help="Output SVG path (single-file mode only)")
    ap.add_argument("-d", "--output-dir",
                    help="Output directory for batch processing")
    ap.add_argument(
        "--devices-dir",
        help=(
            "Directory containing device backup JSON files "
            "(<slug>-<uuid>.json). Used to resolve ownerUri → device name. "
            "Auto-discovers from flow timestamp if not specified."
        ),
    )
    ap.add_argument(
        "--variables-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory containing variable JSON backup files produced by backup.py.\n"
            "Enables resolving [[homey:manager:logic|uuid]] tokens to human names.\n"
            "Example: --variables-dir variables/2026-04-26_12-49/"
        ),
    )
    ap.add_argument(
        "--zones-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory containing zone backup JSON files produced by backup.py. "
            "Enables resolving homey:zone:<uuid> tokens to zone names. "
            "Auto-discovers from flow timestamp if not specified."
        ),
    )
    ap.add_argument(
        "--png",
        action="store_true",
        default=False,
        help="Convert output to PNG instead of SVG (requires cairosvg + libcairo2)",
    )
    args = ap.parse_args()

    if args.output and len(args.inputs) > 1:
        print("Error: -o works with a single input only. "
              "Use -d for batch.", file=sys.stderr)
        sys.exit(1)

    # Build device lookup once for all flows
    devices_dir: Path | None = Path(args.devices_dir) if args.devices_dir else None

    # Auto-discover devices directory if not specified
    # Look for a matching timestamp in devices/ directory based on flow file
    if not devices_dir and args.inputs:
        for input_path in args.inputs:
            p = Path(input_path)
            # Extract timestamp from flow path like flows/2026-04-23_11-13/flow.json
            parent = p.parent
            if parent.name and "_" in parent.name:
                timestamp = parent.name  # e.g., "2026-04-23_11-13"
                auto_devices = Path(__file__).parent / "devices" / timestamp
                if auto_devices.exists():
                    devices_dir = auto_devices
                    break

    device_lookup = _build_device_lookup(devices_dir) if devices_dir else {}
    cap_titles = _build_cap_titles(devices_dir) if devices_dir else {}
    if device_lookup:
        print(f"[INFO] Loaded {len(device_lookup) // 2} device name(s) from {devices_dir}")

    variables_dir: Path | None = Path(args.variables_dir) if args.variables_dir else None

    # Auto-discover variables directory if not specified
    if not variables_dir and args.inputs:
        for input_path in args.inputs:
            p = Path(input_path)
            if p.parent.name and "_" in p.parent.name:
                ts = p.parent.name  # "2026-04-26_12-49"
                auto_vars = Path(__file__).parent / "variables" / ts
                if auto_vars.exists():
                    variables_dir = auto_vars
                    break

    var_lookup = _build_variable_lookup(variables_dir) if variables_dir else {}
    if var_lookup:
        print(f"[INFO] Loaded {len(var_lookup)} variable name(s) from {variables_dir}")

    zones_dir: Path | None = Path(args.zones_dir) if args.zones_dir else None

    # Auto-discover zones directory if not specified
    if not zones_dir and args.inputs:
        for input_path in args.inputs:
            p = Path(input_path)
            if p.parent.name and "_" in p.parent.name:
                timestamp = p.parent.name
                auto_zones = Path(__file__).parent / "zones" / timestamp
                if auto_zones.exists():
                    zones_dir = auto_zones
                    break

    zone_lookup = _build_zone_lookup(zones_dir) if zones_dir else {}
    if zone_lookup:
        print(f"[INFO] Loaded {len(zone_lookup) // 2} zone name(s) from {zones_dir}")

    # ── Consolidated auto-discovery warning ──────────────────────────────
    # Warn only when a dir was NOT supplied explicitly AND auto-discovery
    # also failed to find it (so the user knows names will be unresolved).
    _missing: list[tuple[str, str]] = []
    if not args.devices_dir and not devices_dir:
        _missing.append(("devices", "device names will appear as IDs"))
    if not args.zones_dir and not zones_dir:
        _missing.append(("zones", "zone names will appear as UUIDs"))
    if not args.variables_dir and not variables_dir:
        _missing.append(("variables", "variable references will remain unresolved"))
    if _missing:
        print("Warning: could not auto-discover backup directories for name resolution:",
              file=sys.stderr)
        for _name, _consequence in _missing:
            print(f"  • {_name:<10} → not found ({_consequence})", file=sys.stderr)
        print(
            "Tip: run homey_flow_svg.py on files inside flows/YYYY-MM-DD_HH-MM/, or pass\n"
            "     --devices-dir / --zones-dir / --variables-dir explicitly.",
            file=sys.stderr,
        )

    for fpath in args.inputs:
        p = Path(fpath)
        if not p.exists():
            print(f"  ✗ Not found: {fpath}", file=sys.stderr)
            continue

        try:
            flow = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ✗ Bad JSON: {fpath} ({exc})", file=sys.stderr)
            continue

        print(f"  → {flow.get('name', p.stem)}")

        if args.output:
            out = args.output
        elif args.output_dir:
            od = Path(args.output_dir)
            od.mkdir(parents=True, exist_ok=True)
            out = str(od / p.with_suffix(".svg").name)
        else:
            out = str(p.with_suffix(".svg"))

        render_flow(flow, out, device_lookup=device_lookup or None, var_lookup=var_lookup or None, zone_lookup=zone_lookup or None, cap_titles=cap_titles or None, to_png=args.png)


if __name__ == "__main__":
    main()
