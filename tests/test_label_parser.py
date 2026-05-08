"""
tests/test_label_parser.py
Unit tests for the three token-resolver functions in render_flows/_label_parser.py.

Covers only Part 1 (resolver functions):
  - _resolve_placeholders
  - _resolve_uri_refs
  - _resolve_trigger_refs
"""

import pytest
from render_flows._label_parser import (
    _resolve_placeholders,
    _resolve_uri_refs,
    _resolve_trigger_refs,
)


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_placeholders
# ─────────────────────────────────────────────────────────────────────────────

class TestResolvePlaceholders:
    """Tests for _resolve_placeholders(text, args)"""

    def test_simple_substitution(self):
        result = _resolve_placeholders("Turn [[device]] on", {"device": "Lamp"})
        assert result == "Turn Lamp on"

    def test_missing_key_left_untouched(self):
        result = _resolve_placeholders("Set [[missing]]", {})
        assert result == "Set [[missing]]"

    def test_dict_value_uses_name(self):
        result = _resolve_placeholders("Use [[zone]]", {"zone": {"name": "Kitchen"}})
        assert result == "Use Kitchen"

    def test_none_args_leaves_text_unchanged(self):
        text = "Hello [[world]]"
        assert _resolve_placeholders(text, None) == text

    def test_multiple_placeholders(self):
        result = _resolve_placeholders(
            "Set [[device]] to [[state]]",
            {"device": "Lamp", "state": "on"},
        )
        assert result == "Set Lamp to on"


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_uri_refs
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveUriRefs:
    """Tests for _resolve_uri_refs(text, var_lookup)"""

    def test_logic_variable_found(self):
        uuid = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        text = f"[[homey:manager:logic|{uuid}]]"
        result = _resolve_uri_refs(text, {uuid: "MyVariable"})
        assert result == "MyVariable"

    def test_logic_variable_not_found_uses_short_uuid(self):
        uuid = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        text = f"[[homey:manager:logic|{uuid}]]"
        result = _resolve_uri_refs(text, {})
        assert result == f"var:{uuid[:8]}"

    def test_bll_variable(self):
        result = _resolve_uri_refs("[[homey:app:net.i-dev.betterlogic|myvar]]")
        assert result == "BLL(myvar)"

    @pytest.mark.parametrize("cron_ref,expected_label", [
        ("date", "Current date"),
        ("time", "Current time"),
        ("sun_state", "Sun state"),
    ])
    def test_cron_known_type(self, cron_ref, expected_label):
        text = f"[[homey:manager:cron|{cron_ref}]]"
        result = _resolve_uri_refs(text)
        assert result == expected_label

    def test_cron_unknown_type(self):
        # Unknown cron type → replace underscores with spaces, title-case
        result = _resolve_uri_refs("[[homey:manager:cron|some_thing_new]]")
        assert result == "Some Thing New"

    def test_device_capability(self):
        uuid = "device-uuid-1234"
        result = _resolve_uri_refs(f"[[homey:device:{uuid}|measure_temperature]]")
        assert result == "*Temperature"

    def test_device_capability_no_measure_prefix(self):
        uuid = "device-uuid-1234"
        result = _resolve_uri_refs(f"[[homey:device:{uuid}|dim]]")
        assert result == "*Dim"

    def test_unrecognized_scheme_left_unchanged(self):
        token = "[[homey:manager:unknown|foo]]"
        result = _resolve_uri_refs(token)
        assert result == token

    def test_no_uri_tokens_returns_unchanged(self):
        text = "Turn the lamp on at sunset"
        assert _resolve_uri_refs(text) == text

    def test_multiple_refs_in_one_string(self):
        uuid = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        text = f"[[homey:manager:logic|{uuid}]] and [[homey:app:net.i-dev.betterlogic|myvar]]"
        result = _resolve_uri_refs(text, {uuid: "Brightness"})
        assert result == "Brightness and BLL(myvar)"


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_trigger_refs
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveTriggerRefs:
    """Tests for _resolve_trigger_refs(text, trigger_name_map, trigger_cap_map)"""

    def test_cap_map_match(self):
        cap_map = {"card1::temp": "25 °C"}
        result = _resolve_trigger_refs(
            "Value: [[trigger::card1::temp]]",
            trigger_name_map={},
            trigger_cap_map=cap_map,
        )
        assert result == "Value: 25 °C"

    def test_name_map_fallback(self):
        name_map = {"card1": "MotionSensor"}
        result = _resolve_trigger_refs(
            "[[trigger::card1::temp]]",
            trigger_name_map=name_map,
            trigger_cap_map={},
        )
        assert result == "MotionSensor:temp"

    def test_no_maps_returns_short_id(self):
        card_id = "abcdef01-1234-5678-abcd-ef0123456789"
        result = _resolve_trigger_refs(
            f"[[trigger::{card_id}::temp]]",
            trigger_name_map={"other-id": "Sensor"},
            trigger_cap_map={},
        )
        # Falls back to [XXXXXXXX:field] with first 8 chars of card_id
        assert result == f"[{card_id[:8]}:temp]"

    def test_no_trigger_token_returns_text_unchanged(self):
        text = "No trigger tokens here"
        result = _resolve_trigger_refs(text, {"card1": "Sensor"}, {"card1::temp": "25 °C"})
        assert result == text

    def test_both_maps_none_returns_text_unchanged(self):
        text = "[[trigger::card1::temp]]"
        result = _resolve_trigger_refs(text, None, None)
        assert result == text
