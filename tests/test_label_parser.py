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
    _parse_label,
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

    def test_none_value_leaves_placeholder_untouched(self):
        # Line 74: key present in args but value is None → placeholder survives unchanged
        result = _resolve_placeholders("Turn [[device]] on", {"device": None})
        assert result == "Turn [[device]] on"

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


# ─────────────────────────────────────────────────────────────────────────────
# _parse_label
# ─────────────────────────────────────────────────────────────────────────────

def _pl(card, **kwargs):
    """Convenience wrapper — positional args match _parse_label signature."""
    return _parse_label(card, **kwargs)


class TestParseLabel:
    """Branch-coverage tests for _parse_label."""

    # ── Cron variants ────────────────────────────────────────────────────────

    def test_cron_sunrise(self):
        card = {"type": "trigger", "id": "homey:manager:cron:sunrise", "args": {"before": 5}}
        assert _pl(card) == "Sun rises in 5 minutes"

    @pytest.mark.parametrize("suffix,expected", [
        ("after_sunrise", "After sunrise"),
        ("after_sunset", "After sunset"),
    ])
    def test_cron_after_variants(self, suffix, expected):
        card = {"type": "trigger", "id": f"homey:manager:cron:{suffix}", "args": {}}
        assert _pl(card) == expected

    def test_cron_before_sunrise(self):
        card = {"type": "trigger", "id": "homey:manager:cron:before_sunrise", "args": {"before": 10}}
        assert _pl(card) == "10 min before sunrise"

    def test_cron_before_sunset(self):
        card = {"type": "trigger", "id": "homey:manager:cron:before_sunset", "args": {"before": 15}}
        assert _pl(card) == "15 min before sunset"

    # ── Zone trigger ─────────────────────────────────────────────────────────

    def test_zone_trigger_with_zone_lookup(self):
        zone_uuid = "zone-uuid-1111"
        card = {
            "type": "trigger",
            "id": f"homey:zone:{zone_uuid}:alarm_motion_true",
            "args": {},
        }
        result = _pl(card, zone_lookup={zone_uuid: "Living Room"})
        assert "Living Room" in result

    def test_zone_trigger_zone_not_in_lookup(self):
        zone_uuid = "zone-uuid-2222"
        card = {
            "type": "trigger",
            "id": f"homey:zone:{zone_uuid}:alarm_motion_true",
            "args": {},
        }
        # Falls back to first 8 chars of UUID
        result = _pl(card, zone_lookup={})
        assert zone_uuid[:8] in result

    # ── BLL branches ─────────────────────────────────────────────────────────

    def test_bll_variable_contains(self):
        card = {
            "type": "condition",
            "id": "net.i-dev.betterlogic:variable_contains",
            "args": {"variable": {"name": "MyVar"}, "value": "hello"},
        }
        result = _pl(card)
        assert result == "'MyVar' contains 'hello'"

    def test_bll_execute_expression(self):
        card = {
            "type": "action",
            "id": "net.i-dev.betterlogic:execute_bl_expression",
            "args": {"variable": {"name": "Counter"}, "expression": "Counter + 1"},
        }
        result = _pl(card)
        assert result == "Set Counter to Counter + 1"

    # ── Logic variable_set ────────────────────────────────────────────────────

    def test_logic_variable_set_basic(self):
        card = {
            "type": "action",
            "id": "homey:manager:logic:variable_set",
            "args": {"variable": {"name": "Score"}, "value": "42"},
        }
        assert _pl(card) == "Score = 42"

    def test_logic_variable_set_strips_math_wrapper(self):
        card = {
            "type": "action",
            "id": "homey:manager:logic:variable_set",
            "args": {"variable": {"name": "Score"}, "value": "{{Score + 1}}"},
        }
        assert _pl(card) == "Score = Score + 1"

    # ── Notification / timeline ───────────────────────────────────────────────

    def test_notification_action(self):
        card = {
            "type": "action",
            "id": "homey:manager:notifications:create_notification",
            "args": {"text": "Hello world"},
        }
        assert _pl(card) == "Hello world"

    # ── Mobile push ───────────────────────────────────────────────────────────

    def test_mobile_push_with_user(self):
        card = {
            "type": "action",
            "id": "homey:manager:mobile:send_notification_push",
            "args": {"user": {"name": "Alice"}, "text": "Dinner time"},
        }
        result = _pl(card)
        assert result == "→ Alice: Dinner time"

    def test_mobile_push_image(self):
        card = {
            "type": "action",
            "id": "homey:manager:mobile:push_image",
            "args": {"user": {"name": "Bob"}},
            "droptoken": "homey:device:dev-uuid-9999|snapshot",
        }
        result = _pl(card, device_lookup={"dev-uuid-9999": "Doorbell"})
        assert "Doorbell" in result

    # ── Rich format ───────────────────────────────────────────────────────────

    def test_rich_format_title_formatted(self):
        card = {
            "type": "action",
            "card": {
                "titleFormatted": "Turn [[device]] on",
                "args": {"device": "Kitchen Light"},
            },
        }
        assert _pl(card) == "Turn Kitchen Light on"

    def test_rich_format_owner_uri_device_lookup(self):
        dev_uuid = "dev-uuid-abcd"
        card = {
            "type": "action",
            "card": {
                "titleFormatted": "Set dim level",
                "ownerUri": f"homey:device:{dev_uuid}",
                "args": {},
            },
        }
        result = _pl(card, device_lookup={dev_uuid: "Bedroom Light"})
        assert "Bedroom Light" in result

    # ── Fallback / generic args ───────────────────────────────────────────────

    def test_fallback_with_args_dict_with_name(self):
        card = {
            "type": "action",
            "id": "some:unknown:action",
            "args": {"zone": {"name": "Garden"}},
        }
        result = _pl(card)
        assert "Garden" in result

    def test_fallback_duration_unit_combined(self):
        card = {
            "type": "action",
            "id": "some:unknown:fade",
            "args": {"duration": "30", "unit": "seconds"},
        }
        result = _pl(card)
        assert "30 seconds" in result

    # ── Droptoken: equal_boolean (line 238) ───────────────────────────────────

    def test_droptoken_equal_boolean_returns_eq_yes(self):
        # Line 238: droptoken → logic var + "equal_boolean" in card id → "<name>  ==  yes"
        card = {
            "type": "condition",
            "id": "homey:manager:logic:equal_boolean",
            "droptoken": "homey:manager:logic|var-uuid-bool",
        }
        result = _pl(card, var_lookup={"var-uuid-bool": "IsNightMode"})
        assert result == "IsNightMode  ==  yes"

    # ── Droptoken: logic var, non-comparison → return dt_name (line 245) ─────

    def test_droptoken_logic_var_non_comparison_returns_name(self):
        # Line 245: logic var in lookup, card id is NOT a comparison op → bare name
        card = {
            "type": "condition",
            "id": "homey:manager:logic:some_other_condition",
            "droptoken": "homey:manager:logic|var-uuid-1234",
        }
        result = _pl(card, var_lookup={"var-uuid-1234": "IsNightMode"})
        assert result == "IsNightMode"

    # ── Droptoken: betterlogic scheme → dt_ref.replace("_", " ") (line 248) ──

    def test_droptoken_bll_returns_ref_as_name(self):
        # Line 248: droptoken scheme contains "betterlogic" → underscores → spaces
        card = {
            "type": "condition",
            "id": "some:other:card",
            "droptoken": "net.i-dev.betterlogic|my_var_name",
        }
        assert _pl(card) == "my var name"

    # ── Logic comparison: non-logic droptoken lhs (line 266) ─────────────────

    def test_logic_comparison_non_logic_droptoken_lhs(self):
        # Line 266: comparison op card with droptoken scheme != homey:manager:logic
        #           (and not betterlogic) → lhs = dt_ref.replace("_", " ").capitalize()
        card = {
            "type": "condition",
            "id": "homey:manager:logic:gt",
            "droptoken": "homey:device:dev-uuid-abc|room_temperature",
            "args": {"comparator": "22"},
        }
        result = _pl(card)
        assert result == "Room temperature > 22"

    # ── Logic comparison: comparator contains [[...]] (line 271) ─────────────

    def test_logic_comparison_comparator_uri_ref(self):
        # Line 271: rhs_raw contains "[[" → resolved via _resolve_uri_refs
        card = {
            "type": "condition",
            "id": "homey:manager:logic:eq",
            "droptoken": "homey:manager:logic|var-uuid-a",
            "args": {"comparator": "[[homey:manager:logic|var-uuid-b]]"},
        }
        result = _pl(
            card,
            var_lookup={"var-uuid-a": "Score", "var-uuid-b": "Target"},
        )
        assert result == "Score = Target"

    # ── Logic comparison: between operator (lines 275-280) ───────────────────

    def test_logic_comparison_between(self):
        # Lines 275-280: "between" op returns "<lhs> between <rhs> and <rhs2>"
        card = {
            "type": "condition",
            "id": "homey:manager:logic:between",
            "droptoken": "homey:manager:logic|var-uuid-5678",
            "args": {"comparator": "10", "comparator2": "20"},
        }
        result = _pl(card, var_lookup={"var-uuid-5678": "Temperature"})
        assert result == "Temperature between 10 and 20"

    def test_logic_comparison_between_rhs2_uri_ref(self):
        # Line 277: comparator2 contains "[[" → resolved via _resolve_uri_refs
        card = {
            "type": "condition",
            "id": "homey:manager:logic:between",
            "droptoken": "homey:manager:logic|var-uuid-5678",
            "args": {
                "comparator": "10",
                "comparator2": "[[homey:manager:logic|var-uuid-5679]]",
            },
        }
        result = _pl(card, var_lookup={"var-uuid-5678": "Temperature", "var-uuid-5679": "MaxTemp"})
        assert result == "Temperature between 10 and MaxTemp"

    # ── Zone trigger with capability name (line 317) ──────────────────────────

    def test_zone_trigger_with_capability_name(self):
        # Line 317: cap_name is non-empty → "<zone>: <cap_name> is true/false"
        zone_uuid = "zone-uuid-3333"
        card = {
            "type": "trigger",
            "id": f"homey:zone:{zone_uuid}:alarm_motion_true",
            "args": {"capability": {"name": "Motion Sensor"}},
        }
        result = _pl(card, zone_lookup={zone_uuid: "Hallway"})
        assert result == "Hallway: Motion Sensor is true"

    # ── Aqara FP2 presence triggers (lines 322-340) ───────────────────────────

    def test_aqara_fp2_motion_new_true(self):
        # Lines 322-325: ":alarm_motion_new_true" in id + zone dict → "<zone> occupied"
        card = {
            "type": "trigger",
            "id": "homey:device:dev-uuid:alarm_motion_new_true",
            "args": {"zone": {"name": "Bedroom"}},
        }
        assert _pl(card) == "Bedroom occupied"

    def test_aqara_fp2_motion_new_false(self):
        # Lines 328-331: ":alarm_motion_new_false" in id + zone dict → "<zone> unoccupied"
        card = {
            "type": "trigger",
            "id": "homey:device:dev-uuid:alarm_motion_new_false",
            "args": {"zone": {"name": "Office"}},
        }
        assert _pl(card) == "Office unoccupied"

    def test_aqara_fp2_motion_inactive(self):
        # Lines 334-340: ":motion_inactive_new" in id + zone dict → "<zone> is N unit inactive"
        card = {
            "type": "trigger",
            "id": "homey:device:dev-uuid:motion_inactive_new",
            "args": {"zone": {"name": "Living Room"}, "minutes": 5, "timeunit": "minutes"},
        }
        assert _pl(card) == "Living Room is 5 minutes inactive"

    # ── Mobile push_image: no device_lookup match → dt_ref fallback (line 391) ─

    def test_mobile_push_image_no_device_lookup_match(self):
        # Line 391: push_image with droptoken but device not in device_lookup
        #           → img_source = dt_ref.replace("-"," ").replace("_"," ")
        card = {
            "type": "action",
            "id": "homey:manager:mobile:push_image",
            "args": {},
            "droptoken": "homey:device:unknown-uuid|my_snapshot",
        }
        result = _pl(card, device_lookup={})
        assert "my snapshot" in result

    # ── Mobile push: no user_name → text_val or "Push notification" (line 400) ─

    def test_mobile_push_no_user_returns_text(self):
        # Line 400 (text branch): no user → returns text_val directly
        card = {
            "type": "action",
            "id": "homey:manager:mobile:send_notification_push",
            "args": {"text": "Door opened"},
        }
        assert _pl(card) == "Door opened"

    def test_mobile_push_no_user_no_text_returns_fallback(self):
        # Line 400 (fallback branch): no user, empty text → "Push notification"
        card = {
            "type": "action",
            "id": "homey:manager:mobile:send_notification_push",
            "args": {"text": ""},
        }
        assert _pl(card) == "Push notification"

    def test_mobile_push_user_no_text(self):
        # Line 399 else-branch: user present but text is empty → "→ Alice"
        card = {
            "type": "action",
            "id": "homey:manager:mobile:send_notification_push",
            "args": {"user": {"name": "Alice"}, "text": ""},
        }
        assert _pl(card) == "→ Alice"

    # ── Device name via ownerUri (lines 424-425) ──────────────────────────────

    def test_device_name_from_owner_uri(self):
        # Lines 424-425: non-rich card with ownerUri → device_name from device_lookup
        dev_uuid = "dev-uuid-4242"
        card = {
            "type": "action",
            "id": f"homey:device:{dev_uuid}:dim",
            "ownerUri": f"homey:device:{dev_uuid}",
            "args": {"value": "0.5"},
        }
        result = _pl(card, device_lookup={dev_uuid: "Living Room Lamp"})
        assert "Living Room Lamp" in result

    # ── Generic args: duration with [[...]] URI ref (lines 449-450) ──────────

    def test_generic_args_duration_uri_ref(self):
        # Lines 449-450: duration value contains "[[" → resolved via _resolve_uri_refs
        dur_uuid = "var-uuid-dur1"
        card = {
            "type": "action",
            "id": "homey:device:dev-uuid:dim",
            "args": {
                "duration": f"[[homey:manager:logic|{dur_uuid}]]",
                "unit": "seconds",
            },
        }
        result = _pl(card, var_lookup={dur_uuid: "FadeTime"})
        assert "FadeTime seconds" in result

    # ── Generic args: string arg starting with [[...]] (lines 459-462) ───────

    def test_generic_args_string_starts_with_uri_ref(self):
        # Lines 459-462: arg value is a str starting with "[[" → resolved
        val_uuid = "var-uuid-val1"
        card = {
            "type": "action",
            "id": "homey:device:dev-uuid:set_color",
            "args": {"color": f"[[homey:manager:logic|{val_uuid}]]"},
        }
        result = _pl(card, var_lookup={val_uuid: "FavoriteColor"})
        assert "FavoriteColor" in result

    # ── Generic args: non-dict string arg containing [[...]] (lines 465-467) ──

    def test_generic_args_string_with_embedded_uri_ref(self):
        # Lines 465-467: arg value is a str NOT starting with "[[" but containing "[[" inside
        val_uuid = "var-uuid-emb1"
        card = {
            "type": "action",
            "id": "homey:device:dev-uuid:set_dim",
            "args": {"value": f"min([[homey:manager:logic|{val_uuid}]], 1)"},
        }
        result = _pl(card, var_lookup={val_uuid: "MaxBrightness"})
        assert "MaxBrightness" in result
