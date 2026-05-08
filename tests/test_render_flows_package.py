"""Verify the render_flows package exports work directly (not via shim)."""

import pytest

from render_flows import SVGBuilder, __version__, main, render_flow, render_standard_flow
from render_flows._constants import CANVAS_BG, CARD_DIMS
from render_flows._label_parser import _parse_label, _word_wrap
from render_flows._lookups import _build_folder_lookup, _stem_uuid
from render_flows._renderers import _card_badge, _card_dims
from render_flows._svg_builder import SVGBuilder as _SVGBuilder  # noqa: F811


class TestPackageImports:
    """Smoke tests that the package structure is correct."""

    def test_version_is_string(self):
        assert isinstance(__version__, str)

    def test_svg_builder_renders(self):
        s = SVGBuilder(100, 100)
        svg = s.render()
        assert "<svg" in svg

    def test_word_wrap_from_package(self):
        assert _word_wrap("hello world", 50) == ["hello world"]

    def test_parse_label_start(self):
        assert _parse_label({"type": "start"}) == "Start"

    def test_card_dims_trigger(self):
        w, h = _card_dims({"type": "trigger"})
        assert w == 340.0

    def test_stem_uuid_basic(self):
        assert _stem_uuid("dev-550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"

    def test_card_badge_trigger(self):
        assert _card_badge({"type": "trigger", "id": ""}) == "TRIGGER"

    def test_main_is_callable(self):
        assert callable(main)

    def test_render_flow_is_callable(self):
        assert callable(render_flow)

    def test_render_standard_flow_is_callable(self):
        assert callable(render_standard_flow)

    def test_constants_accessible(self):
        assert isinstance(CANVAS_BG, str)
        assert isinstance(CARD_DIMS, dict)

    def test_build_folder_lookup_empty_dir(self, tmp_path):
        result = _build_folder_lookup(tmp_path / "does-not-exist")
        assert result == {}

    def test_package_exports_public_symbols(self):
        """render_flows package must export the key public symbols."""
        from render_flows import render_flow, render_standard_flow, main
        assert callable(render_flow)
        assert callable(render_standard_flow)
        assert callable(main)


class TestCardBadge:
    """Tests for _card_badge() — covers every URI pattern in _renderers.py."""

    @pytest.mark.parametrize("card_type,card_id,expected_badge", [
        # ── trigger patterns ──
        ("trigger", "homey:zone:abc123:cap",               "ZONE TRIGGER"),
        ("trigger", "homey:device:abc123:cap",             "DEVICE TRIGGER"),
        ("trigger", "com.basmilius.flowbits:something",    "FLOWBITS TRIGGER"),
        ("trigger", "homey:manager:cron:every_minute",     "CRON TRIGGER"),
        ("trigger", "homey:manager:presence:home",         "PRESENCE TRIGGER"),
        ("trigger", "homey:manager:logic:variable_updated","LOGIC TRIGGER"),
        ("trigger", "homey:manager:system:boot",           "SYSTEM TRIGGER"),
        ("trigger", "net.i-dev.betterlogic:something",     "BLL TRIGGER"),
        # ── condition patterns ──
        ("condition", "net.i-dev.betterlogic:check",       "BLL CONDITION"),
        ("condition", "homey:manager:logic:equal",         "LOGIC CONDITION"),
        ("condition", "homey:device:abc123:cap",           "DEVICE CONDITION"),
        ("condition", "flowbits:is_set",                   "FLOWBITS CONDITION"),
        ("condition", "homey:manager:cron:between",        "CRON CONDITION"),
        ("condition", "homey:manager:presence:is_home",    "PRESENCE CONDITION"),
        ("condition", "homey:manager:mobile:geofence",     "MOBILE CONDITION"),
        # ── action patterns ──
        ("action", "net.i-dev.betterlogic:set_var",        "BLL ACTION"),
        ("action", "homey:manager:notifications:create",   "TIMELINE"),
        ("action", "homey:manager:mobile:push",            "MOBILE ACTION"),
        ("action", "homey:manager:logic:set",              "LOGIC ACTION"),
        ("action", "homey:device:abc123:cap",              "DEVICE ACTION"),
        ("action", "homey:zone:abc123:cap",                "ZONE ACTION"),
        ("action", "homey:manager:flow:start",             "FLOW ACTION"),
        ("action", "homey:manager:presence:set",           "PRESENCE ACTION"),
        ("action", "com.basmilius.flowbits:set",           "FLOWBITS ACTION"),
        ("action", "com.ubnt.unifiprotect:snapshot",       "CAMERA ACTION"),
        ("action", "ady.enhanced_device_widget:update",    "WIDGET ACTION"),
    ])
    def test_card_badge_parametrized(self, card_type, card_id, expected_badge):
        card = {"type": card_type, "id": card_id}
        assert _card_badge(card) == expected_badge

    def test_card_badge_start_card(self):
        """type='start' with no id falls through to ctype.upper()."""
        assert _card_badge({"type": "start"}) == "START"

    def test_card_badge_all_card(self):
        """type='all' with no id falls through to ctype.upper()."""
        assert _card_badge({"type": "all"}) == "ALL"

    def test_card_badge_any_card(self):
        """type='any' with no id falls through to ctype.upper()."""
        assert _card_badge({"type": "any"}) == "ANY"

    def test_card_badge_unknown_trigger(self):
        """trigger with unrecognised id falls back to 'TRIGGER'."""
        card = {"type": "trigger", "id": "com.example.unknown:something"}
        assert _card_badge(card) == "TRIGGER"

    def test_card_badge_unknown_condition(self):
        """condition with unrecognised id falls back to 'CONDITION'."""
        card = {"type": "condition", "id": "com.example.unknown:something"}
        assert _card_badge(card) == "CONDITION"

    def test_card_badge_unknown_action(self):
        """action with unrecognised id falls back to 'ACTION'."""
        card = {"type": "action", "id": "com.example.unknown:something"}
        assert _card_badge(card) == "ACTION"


# ── TestSVGBuilderEdgeCases ──────────────────────────────────────────────


class TestSVGBuilderEdgeCases:
    """Edge-case tests for SVGBuilder methods."""

    def test_line_produces_svg_line_element(self):
        """line() must emit a <line> element in the rendered SVG."""
        svg = _SVGBuilder(200, 200)
        svg.line(x1=0, y1=0, x2=100, y2=100, stroke="red")
        output = svg.render()
        assert "<line" in output

    def test_text_multiline_truncates_to_max_lines(self):
        """When content exceeds max_lines, the last tspan must end with the ellipsis char."""
        svg = _SVGBuilder(400, 400)
        # Provide more words than max_lines can hold (each word on its own line)
        long_content = " ".join(f"word{i}" for i in range(20))
        svg.text_multiline(long_content, x=10, y=20, max_chars=6, max_lines=3)
        output = svg.render()
        # The ellipsis character used in _svg_builder.py is the unicode '…'
        assert "…" in output

    def test_text_multiline_no_truncation_when_within_limit(self):
        """Content that fits within max_lines must NOT have an ellipsis appended."""
        svg = _SVGBuilder(400, 400)
        svg.text_multiline("hello world", x=10, y=20, max_chars=42, max_lines=6)
        output = svg.render()
        assert "…" not in output
