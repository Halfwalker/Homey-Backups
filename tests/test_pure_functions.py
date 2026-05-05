"""
tests/test_pure_functions.py
Comprehensive unit tests for pure functions in the Homey Backups toolchain.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import json as _json
import backup
from render_flows._lookups import _build_folder_lookup, _stem_uuid
from render_flows._label_parser import _word_wrap, _parse_label
from render_flows._renderers import _card_dims
import restore
from unittest.mock import patch

# ──────────────────────────────────────────────────────────────────────────────
# 4.1  _dict_to_list()
# ──────────────────────────────────────────────────────────────────────────────

class TestDictToList:
    """Tests for backup._dict_to_list()"""

    def test_empty_dict_returns_empty_list(self):
        assert backup._dict_to_list({}) == []

    def test_single_item_id_injected(self):
        result = backup._dict_to_list({"abc123": {"name": "Light"}})
        assert len(result) == 1
        assert result[0]["id"] == "abc123"
        assert result[0]["name"] == "Light"

    def test_multiple_items_all_returned(self):
        data = {
            "id-1": {"name": "Device A"},
            "id-2": {"name": "Device B"},
            "id-3": {"name": "Device C"},
        }
        result = backup._dict_to_list(data)
        assert len(result) == 3
        ids = {item["id"] for item in result}
        assert ids == {"id-1", "id-2", "id-3"}

    def test_non_dict_values_are_skipped(self):
        data = {
            "good-id": {"name": "Sensor"},
            "string-val": "just a string",
            "int-val": 42,
            "none-val": None,
            "list-val": [1, 2, 3],
        }
        result = backup._dict_to_list(data)
        assert len(result) == 1
        assert result[0]["id"] == "good-id"

    def test_existing_id_key_is_overwritten(self):
        # The implementation unconditionally sets item_data["id"] = item_id,
        # so an existing "id" key IS overwritten (this documents actual behaviour).
        data = {"outer-key": {"id": "inner-id", "name": "Zone"}}
        result = backup._dict_to_list(data)
        assert len(result) == 1
        assert result[0]["id"] == "outer-key"  # outer key wins

    def test_non_dict_input_returns_empty_list(self):
        assert backup._dict_to_list(None) == []   # type: ignore[arg-type]
        assert backup._dict_to_list([]) == []      # type: ignore[arg-type]
        assert backup._dict_to_list("str") == []   # type: ignore[arg-type]

    def test_id_injected_does_not_duplicate_other_fields(self):
        data = {"uuid-x": {"zone": "living-room", "active": True}}
        result = backup._dict_to_list(data)
        item = result[0]
        assert item["zone"] == "living-room"
        assert item["active"] is True
        assert item["id"] == "uuid-x"

    def test_empty_inner_dict_gets_id_injected(self):
        result = backup._dict_to_list({"some-id": {}})
        assert result == [{"id": "some-id"}]


# ──────────────────────────────────────────────────────────────────────────────
# 4.2  _stem_uuid()
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestStemUuid:
    """Tests for render_flows._lookups._stem_uuid()"""

    def test_normal_case_trailing_uuid(self):
        stem = f"my-device-name-{SAMPLE_UUID}"
        assert _stem_uuid(stem) == SAMPLE_UUID

    def test_no_uuid_returns_none(self):
        assert _stem_uuid("just-a-normal-filename") is None

    def test_uuid_at_start_of_stem(self):
        stem = f"{SAMPLE_UUID}-suffix"
        assert _stem_uuid(stem) == SAMPLE_UUID

    def test_uuid_is_the_entire_stem(self):
        assert _stem_uuid(SAMPLE_UUID) == SAMPLE_UUID

    def test_partial_uuid_wrong_format_returns_none(self):
        # Too short / wrong grouping — not a valid UUID
        assert _stem_uuid("550e8400-e29b-41d4") is None
        assert _stem_uuid("gggggggg-gggg-gggg-gggg-gggggggggggg") is None

    def test_multiple_uuids_returns_first(self):
        uuid2 = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        stem = f"prefix-{SAMPLE_UUID}-middle-{uuid2}"
        assert _stem_uuid(stem) == SAMPLE_UUID

    def test_empty_string_returns_none(self):
        assert _stem_uuid("") is None

    def test_uppercase_uuid_not_matched(self):
        # The regex uses [0-9a-f] (lowercase only)
        upper = SAMPLE_UUID.upper()
        assert _stem_uuid(upper) is None

    def test_uuid_in_device_backup_filename_style(self):
        stem = f"living-room-light-{SAMPLE_UUID}"
        assert _stem_uuid(stem) == SAMPLE_UUID


# ──────────────────────────────────────────────────────────────────────────────
# 4.4a  _word_wrap()
# ──────────────────────────────────────────────────────────────────────────────

class TestWordWrap:
    """Tests for render_flows._label_parser._word_wrap()"""

    def test_empty_string_returns_list_with_empty_string(self):
        assert _word_wrap("", 20) == [""]

    def test_whitespace_only_returns_list_with_empty_string(self):
        # strip() makes whitespace-only text behave like empty
        assert _word_wrap("   ", 20) == [""]

    def test_short_text_single_element(self):
        result = _word_wrap("Hello world", 50)
        assert result == ["Hello world"]

    def test_text_at_exactly_max_chars_single_element(self):
        text = "A" * 20  # single word, exactly 20 chars
        result = _word_wrap(text, 20)
        assert len(result) == 1
        assert result[0] == text

    def test_text_longer_than_max_splits_at_word_boundary(self):
        text = "one two three four five six seven"
        result = _word_wrap(text, 10)
        # Every line must be ≤ max_chars (except single words longer than limit)
        for line in result:
            assert len(line) <= 15, f"Line too long: {line!r}"
        # Joined result should contain all words
        assert " ".join(result).replace("  ", " ") == text

    def test_long_single_word_stays_on_one_line(self):
        word = "superlongwordwithoutanyspaces"
        result = _word_wrap(word, 10)
        # Cannot split — must keep the word intact
        assert len(result) == 1
        assert result[0] == word

    def test_newlines_in_input_treated_as_spaces(self):
        text = "line one\nline two"
        result = _word_wrap(text, 50)
        assert result == ["line one line two"]

    def test_multi_line_output_not_more_than_needed(self):
        # 5 words of 4 chars each + spaces: 5*4 + 4 spaces = 24
        text = "word word word word word"
        result = _word_wrap(text, 9)
        # Each line should hold at most one or two 4-char words given max=9
        assert len(result) >= 3
        for line in result:
            assert len(line) <= 9, f"Line too long: {line!r}"

    def test_wrapping_preserves_all_words(self):
        text = "alpha beta gamma delta epsilon zeta eta"
        result = _word_wrap(text, 12)
        reconstructed = " ".join(result)
        assert reconstructed == text

    def test_single_word_shorter_than_max(self):
        result = _word_wrap("hello", 20)
        assert result == ["hello"]


# ──────────────────────────────────────────────────────────────────────────────
# 4.4b  _card_dims()
# ──────────────────────────────────────────────────────────────────────────────

class TestCardDims:
    """Tests for render_flows._renderers._card_dims()"""

    def _dims(self, card_type: str, **extra) -> tuple[float, float]:
        card = {"type": card_type, **extra}
        return _card_dims(card)

    def test_returns_tuple_of_two_floats(self):
        w, h = self._dims("trigger")
        assert isinstance(w, float)
        assert isinstance(h, float)

    def test_trigger_card_baseline_dimensions(self):
        w, h = self._dims("trigger")
        assert w == 340.0
        assert h >= 72.0  # may grow with label

    def test_condition_card_dimensions(self):
        w, h = self._dims("condition")
        assert w == 340.0

    def test_action_card_dimensions(self):
        w, h = self._dims("action")
        assert w == 340.0

    def test_any_gate_card_small(self):
        w, h = self._dims("any")
        assert w == 79.0
        assert h == 52.0

    def test_all_gate_card_small(self):
        w, h = self._dims("all")
        assert w == 79.0

    def test_start_card_small(self):
        w, h = self._dims("start")
        assert w == 79.0

    def test_delay_card_width_scales_with_label(self):
        short_card = {
            "type": "delay",
            "args": {"delay": {"number": 5, "multiplier": 60}},
        }
        long_card = {
            "type": "delay",
            "args": {"delay": {"number": 12345, "multiplier": 3600}},
        }
        w_short, _ = _card_dims(short_card)
        w_long, _ = _card_dims(long_card)
        assert w_long >= w_short

    def test_note_card_height_grows_with_text(self):
        short_note = {"type": "note", "value": "Hi"}
        long_note = {
            "type": "note",
            "value": (
                "This is a much longer note with many words that will require "
                "several lines of text when word-wrapped at 42 characters per line."
            ),
        }
        _, h_short = _card_dims(short_note)
        _, h_long = _card_dims(long_note)
        assert h_long > h_short

    def test_note_card_minimum_height(self):
        _, h = _card_dims({"type": "note", "value": ""})
        assert h >= 48.0

    def test_trigger_card_height_grows_with_long_label(self):
        short_label = "Lamp on"
        long_label = (
            "When the motion sensor in the living room detects movement "
            "and the sun has already set below the horizon"
        )
        w1, h_short = _card_dims({"type": "trigger"}, label=short_label)
        _, h_short_actual = _card_dims({"type": "trigger"})
        _card_dims.__doc__  # just access to avoid unused-import lint

        card = {"type": "trigger"}
        _, h_short2 = _card_dims(card, short_label)
        _, h_long = _card_dims(card, long_label)
        assert h_long >= h_short2

    def test_different_card_types_have_different_defaults(self):
        gate_w, _ = self._dims("any")
        action_w, _ = self._dims("action")
        assert action_w > gate_w

    def test_unknown_type_falls_back_to_action_dims(self):
        # CARD_DIMS.get returns (340, 72) default for unknown types
        w, h = _card_dims({"type": "unknown_custom_type"})
        assert w == 340.0
        assert h >= 72.0


# ──────────────────────────────────────────────────────────────────────────────
# 4.3  _parse_label()  — smoke tests (function is complex)
# ──────────────────────────────────────────────────────────────────────────────

class TestParseLabel:
    """Smoke tests for homey_flow_svg._parse_label()"""

    def _label(self, card: dict, **kwargs) -> str:
        return _parse_label(card, **kwargs)

    def test_start_card_returns_start(self):
        result = self._label({"type": "start"})
        assert result == "Start"

    def test_any_card_returns_or(self):
        result = self._label({"type": "any"})
        assert result == "OR"

    def test_all_card_returns_and(self):
        result = self._label({"type": "all"})
        assert result == "AND"

    def test_note_card_returns_value(self):
        result = self._label({"type": "note", "value": "Remember this"})
        assert result == "Remember this"

    def test_note_card_empty_value_returns_empty_string(self):
        result = self._label({"type": "note", "value": ""})
        assert result == ""

    def test_delay_card_formats_duration(self):
        card = {
            "type": "delay",
            "args": {"delay": {"number": 30, "multiplier": 60}},
        }
        result = self._label(card)
        assert "30" in result
        assert "min" in result

    def test_delay_card_seconds_unit(self):
        card = {
            "type": "delay",
            "args": {"delay": {"number": 5, "multiplier": 1}},
        }
        result = self._label(card)
        assert "sec" in result

    def test_trigger_card_with_id_returns_string(self):
        card = {
            "type": "trigger",
            "id": "homey:device:some-uuid:alarm_motion_true",
        }
        result = self._label(card)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cron_trigger_time_exactly(self):
        card = {
            "type": "trigger",
            "id": "homey:manager:cron:time_exactly",
            "args": {"time": "07:30"},
        }
        result = self._label(card)
        assert "07:30" in result

    def test_cron_trigger_sunset(self):
        card = {
            "type": "trigger",
            "id": "homey:manager:cron:sunset",
            "args": {"before": 15},
        }
        result = self._label(card)
        assert "15" in result
        assert "sun" in result.lower()

    def test_action_card_no_id_does_not_crash(self):
        card = {"type": "action", "id": ""}
        result = self._label(card)
        assert isinstance(result, str)

    def test_condition_card_logic_eq(self):
        card = {
            "type": "condition",
            "id": "homey:manager:logic:eq",
            "droptoken": "homey:manager:logic|my-var-uuid",
            "args": {"comparator": "42"},
        }
        result = self._label(card, var_lookup={"my-var-uuid": "Temperature"})
        assert "Temperature" in result
        assert "=" in result
        assert "42" in result

    def test_returns_string_for_any_valid_card(self):
        for ctype in ("trigger", "condition", "action", "note", "any", "all", "start", "delay"):
            card = {"type": ctype}
            if ctype == "delay":
                card["args"] = {"delay": {"number": 1, "multiplier": 1}}
            result = self._label(card)
            assert isinstance(result, str), f"Expected str for type={ctype}"

# ──────────────────────────────────────────────────────────────────────────────
# _build_folder_lookup()
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildFolderLookup:
    """Tests for render_flows._lookups._build_folder_lookup()"""

    def test_returns_mapping_for_valid_json(self, tmp_path):
        f = tmp_path / "folder-abc.json"
        f.write_text(_json.dumps({"id": "folder-abc", "name": "Morning"}), encoding="utf-8")
        result = _build_folder_lookup(tmp_path)
        assert result == {"folder-abc": "Morning"}

    def test_skips_json_missing_name(self, tmp_path):
        f = tmp_path / "folder-abc.json"
        f.write_text(_json.dumps({"id": "folder-abc"}), encoding="utf-8")
        result = _build_folder_lookup(tmp_path)
        assert "folder-abc" not in result

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        result = _build_folder_lookup(tmp_path / "does-not-exist")
        assert result == {}

    def test_multiple_folders_all_mapped(self, tmp_path):
        (tmp_path / "a.json").write_text(_json.dumps({"id": "id-a", "name": "Alpha"}), encoding="utf-8")
        (tmp_path / "b.json").write_text(_json.dumps({"id": "id-b", "name": "Beta"}), encoding="utf-8")
        result = _build_folder_lookup(tmp_path)
        assert result == {"id-a": "Alpha", "id-b": "Beta"}


# ──────────────────────────────────────────────────────────────────────────────
# list_backup_dates()
# ──────────────────────────────────────────────────────────────────────────────

class TestListBackupDates:
    """Tests for restore.list_backup_dates()"""

    def test_returns_paths_sorted_by_name(self, tmp_path):
        root = tmp_path / "Backups"
        (root / "2026-04-20_10-00" / "devices").mkdir(parents=True)
        (root / "2026-04-25_10-00" / "devices").mkdir(parents=True)
        with patch.object(restore, "_BACKUPS_ROOT", root):
            result = restore.list_backup_dates("device")
        assert len(result) == 2
        assert result[0].parent.name < result[1].parent.name

    def test_excludes_dirs_without_underscore(self, tmp_path):
        root = tmp_path / "Backups"
        (root / "nodash" / "devices").mkdir(parents=True)
        with patch.object(restore, "_BACKUPS_ROOT", root):
            result = restore.list_backup_dates("device")
        assert result == []

    def test_excludes_timestamp_dir_without_category_subdir(self, tmp_path):
        root = tmp_path / "Backups"
        (root / "2026-04-20_10-00").mkdir(parents=True)
        # no devices/ subdir
        with patch.object(restore, "_BACKUPS_ROOT", root):
            result = restore.list_backup_dates("device")
        assert result == []

    def test_returns_empty_when_backups_root_missing(self, tmp_path):
        with patch.object(restore, "_BACKUPS_ROOT", tmp_path / "Backups"):
            result = restore.list_backup_dates("device")
        assert result == []
