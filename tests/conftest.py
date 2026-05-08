"""
tests/conftest.py
─────────────────
Shared pytest configuration and fixtures for the Homey Backups test suite.

Adds the project root to sys.path so test files can import top-level modules
(backup, restore, render_flows) without per-file sys.path.insert hacks.
"""

from __future__ import annotations

import json
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


def _write_json(path: pathlib.Path, data: dict) -> pathlib.Path:
    """Write *data* as JSON to *path* and return the path."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
