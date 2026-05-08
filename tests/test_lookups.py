"""Tests for render_flows/_lookups.py — the five lookup-building functions."""
import json


from render_flows._lookups import (
    _build_cap_titles,
    _build_device_lookup,
    _build_trigger_name_map,
    _build_variable_lookup,
    _build_zone_lookup,
)

UUID = "550e8400-e29b-41d4-a716-446655440000"
UUID2 = "660e8400-e29b-41d4-a716-446655440001"


# ─── Helpers ─────────────────────────────────────────────────────────


def _write(directory, filename, data):
    p = directory / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ─── _build_variable_lookup ──────────────────────────────────────────


class TestBuildVariableLookup:
    def test_returns_uuid_to_name_mapping(self, tmp_path):
        _write(tmp_path, "var.json", {"id": UUID, "name": "My Var"})
        result = _build_variable_lookup(tmp_path)
        assert result[UUID] == "My Var"

    def test_falls_back_to_stem_uuid(self, tmp_path):
        _write(tmp_path, f"var-{UUID}.json", {"name": "Stem Var"})
        result = _build_variable_lookup(tmp_path)
        assert result[UUID] == "Stem Var"

    def test_skips_files_without_name(self, tmp_path):
        _write(tmp_path, "var.json", {"id": UUID})
        result = _build_variable_lookup(tmp_path)
        assert UUID not in result

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        result = _build_variable_lookup(tmp_path / "nope")
        assert result == {}

    def test_bad_json_skipped(self, tmp_path):
        (tmp_path / "bad.json").write_text("{not valid json", encoding="utf-8")
        _write(tmp_path, "good.json", {"id": UUID, "name": "Good"})
        result = _build_variable_lookup(tmp_path)
        assert result == {UUID: "Good"}


# ─── _build_device_lookup ────────────────────────────────────────────


class TestBuildDeviceLookup:
    def test_returns_dual_key_mapping(self, tmp_path):
        _write(tmp_path, "device.json", {"id": UUID, "name": "Lounge Lamp"})
        result = _build_device_lookup(tmp_path)
        assert result[UUID] == "Lounge Lamp"
        assert result[f"homey:device:{UUID}"] == "Lounge Lamp"

    def test_falls_back_to_stem_uuid(self, tmp_path):
        _write(tmp_path, f"lounge-lamp-{UUID}.json", {"name": "Stem Lamp"})
        result = _build_device_lookup(tmp_path)
        assert result[UUID] == "Stem Lamp"
        assert result[f"homey:device:{UUID}"] == "Stem Lamp"

    def test_skips_nameless_devices(self, tmp_path):
        _write(tmp_path, "device.json", {"id": UUID})
        result = _build_device_lookup(tmp_path)
        assert UUID not in result

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        result = _build_device_lookup(tmp_path / "nope")
        assert result == {}


# ─── _build_cap_titles ───────────────────────────────────────────────


class TestBuildCapTitles:
    def test_extracts_capability_titles(self, tmp_path):
        _write(tmp_path, "device.json", {
            "id": UUID,
            "name": "Weather",
            "capabilitiesObj": {
                "measure_rain": {"title": "Snow", "units": "mm"},
                "measure_temp": {"title": "Temperature", "units": "°C"},
            },
        })
        result = _build_cap_titles(tmp_path)
        assert result[UUID]["measure_rain"] == ("Snow", "mm")
        assert result[UUID]["measure_temp"] == ("Temperature", "°C")

    def test_skips_devices_without_capabilities(self, tmp_path):
        _write(tmp_path, "device.json", {"id": UUID, "name": "Bare Device"})
        result = _build_cap_titles(tmp_path)
        assert UUID not in result

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        result = _build_cap_titles(tmp_path / "nope")
        assert result == {}


# ─── _build_zone_lookup ──────────────────────────────────────────────


class TestBuildZoneLookup:
    def test_returns_dual_key_mapping(self, tmp_path):
        _write(tmp_path, "zone.json", {"id": UUID, "name": "Living Room"})
        result = _build_zone_lookup(tmp_path)
        assert result[UUID] == "Living Room"
        assert result[f"homey:zone:{UUID}"] == "Living Room"

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        result = _build_zone_lookup(tmp_path / "nope")
        assert result == {}


# ─── _build_trigger_name_map ─────────────────────────────────────────


CARD_UUID = "aaaaaaaa-0000-0000-0000-000000000001"


class TestBuildTriggerNameMap:
    def test_maps_device_trigger_to_device_name(self):
        cards = {
            CARD_UUID: {
                "type": "trigger",
                "id": f"homey:device:{UUID}:measure_rain",
            }
        }
        device_lookup = {UUID: "Weather Station"}
        name_map, cap_map = _build_trigger_name_map(
            cards, device_lookup=device_lookup
        )
        assert name_map[CARD_UUID] == "Weather Station"

    def test_maps_zone_trigger_to_zone_name(self):
        cards = {
            CARD_UUID: {
                "type": "trigger",
                "id": f"homey:zone:{UUID}:become_active",
            }
        }
        zone_lookup = {UUID: "Living Room"}
        name_map, _ = _build_trigger_name_map(cards, zone_lookup=zone_lookup)
        assert name_map[CARD_UUID] == "Living Room"

    def test_skips_non_trigger_cards(self):
        cards = {
            "action-1": {"type": "action", "id": f"homey:device:{UUID}:on_off"},
            "condition-1": {"type": "condition", "id": f"homey:device:{UUID}:measure"},
        }
        name_map, _ = _build_trigger_name_map(
            cards, device_lookup={UUID: "Lamp"}
        )
        assert "action-1" not in name_map
        assert "condition-1" not in name_map

    def test_builds_cap_map_from_cap_titles(self):
        cards = {
            CARD_UUID: {
                "type": "trigger",
                "id": f"homey:device:{UUID}:measure_rain",
            }
        }
        device_lookup = {UUID: "Weather Station"}
        cap_titles = {UUID: {"measure_rain": ("Snow", "mm")}}
        _, cap_map = _build_trigger_name_map(
            cards, device_lookup=device_lookup, cap_titles=cap_titles
        )
        assert cap_map[f"{CARD_UUID}::measure_rain"] == "*Snow (mm)"

    def test_empty_cards_returns_empty_maps(self):
        name_map, cap_map = _build_trigger_name_map({})
        assert name_map == {}
        assert cap_map == {}
