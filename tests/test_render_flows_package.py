"""Verify the render_flows package exports work directly (not via shim)."""

from render_flows import SVGBuilder, __version__, main, render_flow, render_standard_flow
from render_flows._constants import CANVAS_BG, CARD_DIMS
from render_flows._label_parser import _parse_label, _word_wrap
from render_flows._lookups import _build_folder_lookup, _stem_uuid
from render_flows._renderers import _card_badge, _card_dims


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
