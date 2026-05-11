"""
tests/conftest.py
─────────────────
Shared pytest configuration and fixtures for the Homey Backups test suite.

Adds the project root to sys.path so test files can import top-level modules
(backup, restore, render_flows) without per-file sys.path.insert hacks.
"""

from __future__ import annotations

import pathlib
import sys

# ── Path setup ───────────────────────────────────────────────────────────────
# Make project root importable. pytest only adds the rootdir to sys.path when
# there's no src/ layout; with py-modules + packages in pyproject.toml the
# project root IS the right location, but conftest.py guarantees it cleanly.

_ROOT = pathlib.Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Shared fixtures ──────────────────────────────────────────────────────────

import pytest  # noqa: E402 — must come after sys.path is set


@pytest.fixture
def minimal_advanced_flow():
    """A minimal valid advanced flow dict with one trigger card."""
    return {
        "id": "test-flow-1",
        "name": "Test Flow",
        "enabled": True,
        "flow_type": "advanced",
        "cards": {
            "card-trigger": {
                "type": "trigger",
                "id": "homey:device:dev-uuid:alarm_motion",
                "x": 0,
                "y": 0,
                "outputSuccess": [],
            },
        },
    }


@pytest.fixture
def flow_with_connections():
    """A minimal advanced flow with a trigger → action connection."""
    return {
        "id": "test-flow-2",
        "name": "Connected Flow",
        "enabled": True,
        "flow_type": "advanced",
        "cards": {
            "card-trigger": {
                "type": "trigger",
                "id": "homey:device:dev-uuid:alarm_motion",
                "x": 0,
                "y": 0,
                "outputSuccess": ["card-action"],
            },
            "card-action": {
                "type": "action",
                "id": "homey:device:dev-uuid:onoff",
                "x": 400,
                "y": 0,
            },
        },
    }


def _make_api(**kwargs):
    """Return a MagicMock HomeyAPI pre-configured with default empty returns.

    Supports all backup category methods. Pass keyword args to override:
      devices, flows, advanced_flows, flow_folders, zones, logic_vars, bll_vars,
      apps, app_settings, system_info, dashboards, moods, geolocation
    """
    from unittest.mock import MagicMock
    api = MagicMock()
    api.get_devices.return_value = kwargs.get("devices", [])
    api.get_flows.return_value = kwargs.get("flows", [])
    api.get_advanced_flows.return_value = kwargs.get("advanced_flows", [])
    api.get_flow_folders.return_value = kwargs.get("flow_folders", [])
    api.get_zones.return_value = kwargs.get("zones", [])
    api.get_logic_variables.return_value = kwargs.get("logic_vars", [])
    api.get_bll_variables.return_value = kwargs.get("bll_vars", [])
    api.get_apps.return_value = kwargs.get("apps", [])
    api.get_app_settings.return_value = kwargs.get("app_settings", {})
    api.get_system_info.return_value = kwargs.get("system_info", {})
    api.get_dashboards.return_value = kwargs.get("dashboards", [])
    api.get_moods.return_value = kwargs.get("moods", [])
    api.get_geolocation.return_value = kwargs.get("geolocation", {})
    return api
