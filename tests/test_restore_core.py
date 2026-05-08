"""
tests/test_restore_core.py
──────────────────────────
Unit tests for the two pure-ish helpers in restore.py:
  - _load_items(directory)
  - _filter_items(items, query)

Interactive / inquirer functions and main() are NOT tested here.
"""

from __future__ import annotations

import json
import pathlib


import restore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: pathlib.Path, data: dict) -> pathlib.Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# TestLoadItems
# ---------------------------------------------------------------------------

class TestLoadItems:

    def test_loads_single_json_file(self, tmp_path):
        _write_json(tmp_path / "device-abc.json", {"id": "abc-123", "name": "Living Room Light"})

        items = restore._load_items(tmp_path)

        assert len(items) == 1
        item = items[0]
        assert item["name"] == "Living Room Light"
        assert item["id"] == "abc-123"
        assert "path" in item
        assert isinstance(item["path"], pathlib.Path)

    def test_loads_multiple_files(self, tmp_path):
        for i in range(3):
            _write_json(tmp_path / f"item-{i}.json", {"id": f"id-{i}", "name": f"Item {i}"})

        items = restore._load_items(tmp_path)

        assert len(items) == 3

    def test_skips_invalid_json(self, tmp_path):
        (tmp_path / "bad.json").write_text("not valid json {{", encoding="utf-8")
        _write_json(tmp_path / "good.json", {"id": "ok", "name": "Good Item"})

        items = restore._load_items(tmp_path)

        assert len(items) == 1
        assert items[0]["name"] == "Good Item"

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert restore._load_items(tmp_path) == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        assert restore._load_items(missing) == []

    def test_normalises_name_from_title_field(self, tmp_path):
        _write_json(tmp_path / "flow-xyz.json", {"id": "xyz", "title": "My Flow Title"})

        items = restore._load_items(tmp_path)

        assert items[0]["name"] == "My Flow Title"

    def test_normalises_id_from_underscore_id(self, tmp_path):
        _write_json(tmp_path / "zone-abc.json", {"_id": "mongo-style-id", "name": "My Zone"})

        items = restore._load_items(tmp_path)

        assert items[0]["id"] == "mongo-style-id"

    def test_fallback_id_to_filename_stem(self, tmp_path):
        _write_json(tmp_path / "my-device.json", {"name": "Some Device"})

        items = restore._load_items(tmp_path)

        assert items[0]["id"] == "my-device"

    def test_fallback_name_to_filename_stem(self, tmp_path):
        _write_json(tmp_path / "my-device.json", {"id": "abc"})

        items = restore._load_items(tmp_path)

        assert items[0]["name"] == "my-device"


# ---------------------------------------------------------------------------
# TestFilterItems
# ---------------------------------------------------------------------------

class TestFilterItems:

    def _make_items(self, specs: list[tuple[str, str]]) -> list[dict]:
        """Build a minimal item list from (name, id) tuples."""
        return [{"name": name, "id": item_id} for name, item_id in specs]

    def test_empty_query_returns_all(self):
        items = self._make_items([("Alpha", "id-1"), ("Beta", "id-2"), ("Gamma", "id-3")])
        assert restore._filter_items(items, "") == items

    def test_case_insensitive_name_match(self):
        items = self._make_items([("Kitchen Light", "k-001"), ("Bedroom Fan", "b-002")])
        result = restore._filter_items(items, "kitchen")
        assert len(result) == 1
        assert result[0]["name"] == "Kitchen Light"

    def test_matches_on_id_substring(self):
        items = self._make_items([("Device A", "abc-999"), ("Device B", "xyz-111")])
        result = restore._filter_items(items, "abc")
        assert len(result) == 1
        assert result[0]["id"] == "abc-999"

    def test_no_match_returns_empty(self):
        items = self._make_items([("Alpha", "id-1"), ("Beta", "id-2")])
        assert restore._filter_items(items, "zzznomatch") == []

    def test_whitespace_query_returns_all(self):
        # "  ".strip() → "" → "" is always a substring → all items match
        items = self._make_items([("Alpha", "id-1"), ("Beta", "id-2"), ("Gamma", "id-3")])
        result = restore._filter_items(items, "  ")
        assert result == items
