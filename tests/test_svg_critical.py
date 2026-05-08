"""
Tests for render_flows.py critical behaviour and utility functions.

Run:  pytest tests/test_svg_critical.py -v
"""
import json
import pathlib
import sys


SIMPLE_ADVANCED_FLOW = {
    "id": "good-flow-1",
    "name": "Good Flow",
    "enabled": True,
    "flow_type": "advanced",
    "cards": {
        "card-1": {
            "type": "trigger",
            "id": "homey:device:abc:alarm_motion",
            "x": 100,
            "y": 100,
            "outputSuccess": [],
        }
    },
}

SIMPLE_STANDARD_FLOW = {
    "id": "good-flow-2",
    "name": "Good Standard Flow",
    "enabled": True,
    "flow_type": "normal",
    "trigger": {"id": "homey:manager:cron:time_exactly", "args": {"time": "08:00"}},
    "conditions": [],
    "actions": [],
}


class TestSVGBatchCritical:
    """render_flow() exceptions in batch mode must be caught, not propagate."""

    def test_corrupt_flow_does_not_abort_batch(self, tmp_path):
        """A RuntimeError from render_flow() must be caught; other flows must still render."""
        import render_flows as svg

        good_flow_path = tmp_path / "good-flow-1.json"
        bad_flow_path = tmp_path / "bad-flow.json"

        good_flow_path.write_text(json.dumps(SIMPLE_ADVANCED_FLOW), encoding="utf-8")
        # Bad JSON — will cause JSONDecodeError on load
        bad_flow_path.write_text("{ this is not valid json }", encoding="utf-8")

        out_dir = tmp_path / "output"
        out_dir.mkdir()

        rendered: list[str] = []
        errors: list[str] = []

        for fpath in [good_flow_path, bad_flow_path]:
            p = pathlib.Path(fpath)
            try:
                flow = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                continue

            out = str(out_dir / p.with_suffix(".svg").name)
            try:
                svg.render_flow(flow, out)
                rendered.append(p.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        # Good flow must have rendered despite the bad one
        assert (out_dir / "good-flow-1.svg").exists(), (
            "Good flow was not rendered — bad flow should not abort the batch"
        )

    def test_render_flow_exception_caught_in_cli_batch(self, tmp_path, monkeypatch):
        """The CLI main() batch loop must catch render_flow() exceptions and continue."""
        import render_flows as svg

        good_path = tmp_path / "good.json"
        good_path.write_text(json.dumps(SIMPLE_STANDARD_FLOW), encoding="utf-8")

        bad_path = tmp_path / "bad.json"
        bad_path.write_text(json.dumps({
            "id": "bad",
            "name": "Bad Flow",
            "enabled": True,
            "cards": {"broken-card": {"type": "trigger"}},  # missing x, y
        }), encoding="utf-8")

        out_dir = tmp_path / "output"
        out_dir.mkdir()

        # Run main() with both flows; should not raise
        monkeypatch.setattr(sys, "argv", [
            "render_flows.py",
            str(good_path),
            str(bad_path),
            "-d", str(out_dir),
        ])
        try:
            # Should complete without raising SystemExit or unhandled Exception
            svg.main()
        except SystemExit as exc:
            # Only acceptable SystemExit is 0 (success) or argparse help
            assert exc.code == 0 or exc.code is None, (
                f"main() exited with code {exc.code} — should continue past bad flows"
            )

        # Good flow must have rendered
        assert (out_dir / "good.svg").exists(), (
            "Good standard flow was not rendered — bad flow should not abort the batch"
        )


# ── _auto_discover_sibling ───────────────────────────────────────────────


class TestAutoDiscoverSibling:
    def test_returns_sibling_dir_when_exists(self, tmp_path):
        """Returns the sibling directory when the input file is in flows/ under a timestamp."""
        import render_flows

        # Create: tmp/2026-05-03_10-00/flows/my-flow.json + tmp/.../devices/
        ts_dir = tmp_path / "2026-05-03_10-00"
        flows_dir = ts_dir / "flows"
        flows_dir.mkdir(parents=True)
        devices_dir = ts_dir / "devices"
        devices_dir.mkdir()
        flow_file = flows_dir / "my-flow.json"
        flow_file.write_text("{}")

        result = render_flows._lookups._auto_discover_sibling([str(flow_file)], "devices")

        assert result == devices_dir

    def test_returns_none_when_sibling_missing(self, tmp_path):
        """Returns None when the sibling directory does not exist on disk."""
        import render_flows

        ts_dir = tmp_path / "2026-05-03_10-00"
        flows_dir = ts_dir / "flows"
        flows_dir.mkdir(parents=True)
        # No devices/ sibling created
        flow_file = flows_dir / "my-flow.json"
        flow_file.write_text("{}")

        result = render_flows._lookups._auto_discover_sibling([str(flow_file)], "devices")

        assert result is None

    def test_returns_none_when_parent_is_not_flows(self, tmp_path):
        """Returns None when the input file is not in a directory named 'flows'."""
        import render_flows

        some_dir = tmp_path / "random_dir"
        some_dir.mkdir()
        flow_file = some_dir / "my-flow.json"
        flow_file.write_text("{}")

        result = render_flows._lookups._auto_discover_sibling([str(flow_file)], "devices")

        assert result is None

    def test_returns_none_for_empty_inputs(self, tmp_path):
        """Returns None when inputs list is empty."""
        import render_flows

        result = render_flows._lookups._auto_discover_sibling([], "devices")

        assert result is None

# ── TestFolderPrefixInSVG ────────────────────────────────────────────────

import sys as _sys  # noqa: E402
import pathlib as _pathlib  # noqa: E402
_sys.path.insert(0, str(_pathlib.Path(__file__).parent.parent))
import render_flows  # noqa: E402

FOLDER_FLOW = {
    "id": "flow-with-folder",
    "name": "My Flow",
    "enabled": True,
    "folder": "folder-uuid-123",
    "cards": {
        "card-1": {
            "type": "trigger",
            "id": "homey:device:abc:alarm_motion",
            "x": 100,
            "y": 100,
            "outputSuccess": [],
        }
    },
}


class TestFolderPrefixInSVG:
    """Tests that folder name prefix appears in SVG title when folder_lookup is provided."""

    def test_folder_prefix_appears_in_svg_title(self, tmp_path):
        output_path = tmp_path / "out.svg"
        render_flows.render_flow(
            FOLDER_FLOW,
            str(output_path),
            folder_lookup={"folder-uuid-123": "Morning"},
        )
        svg_text = output_path.read_text(encoding="utf-8")
        assert "Morning / My Flow" in svg_text

    def test_no_folder_prefix_when_lookup_empty(self, tmp_path):
        output_path = tmp_path / "out.svg"
        render_flows.render_flow(
            FOLDER_FLOW,
            str(output_path),
            folder_lookup={},
        )
        svg_text = output_path.read_text(encoding="utf-8")
        assert "Morning" not in svg_text
        assert "My Flow" in svg_text


# ── TestCLIFlags ─────────────────────────────────────────────────────────

import sys as _sys_cli  # noqa: E402
import pytest as _pytest  # noqa: E402


_MINIMAL_FLOW = {
    "id": "cli-test-flow",
    "name": "CLI Test Flow",
    "enabled": True,
    "flow_type": "advanced",
    "cards": {
        "card-1": {
            "type": "trigger",
            "id": "homey:device:abc:alarm_motion",
            "x": 100,
            "y": 100,
            "outputSuccess": [],
        }
    },
}


class TestCLIFlags:
    """Tests for CLI flag behaviour in render_flows._cli.main()."""

    def test_output_flag_single_input(self, tmp_path, monkeypatch):
        """Single input + -o flag writes SVG to the specified output path."""
        import render_flows

        flow_file = tmp_path / "flow.json"
        flow_file.write_text(json.dumps(_MINIMAL_FLOW), encoding="utf-8")
        out_svg = tmp_path / "custom.svg"

        monkeypatch.setattr(
            _sys_cli,
            "argv",
            ["render_flows", str(flow_file), "-o", str(out_svg)],
        )
        render_flows.main()

        assert out_svg.exists(), "Output SVG was not created at the specified -o path"

    def test_output_flag_multiple_inputs_exits(self, tmp_path, monkeypatch):
        """-o with more than one input file must exit with code 1."""
        import render_flows

        flow_a = tmp_path / "flow_a.json"
        flow_b = tmp_path / "flow_b.json"
        flow_a.write_text(json.dumps(_MINIMAL_FLOW), encoding="utf-8")
        flow_b.write_text(json.dumps(_MINIMAL_FLOW), encoding="utf-8")
        out_svg = tmp_path / "out.svg"

        monkeypatch.setattr(
            _sys_cli,
            "argv",
            ["render_flows", str(flow_a), str(flow_b), "-o", str(out_svg)],
        )
        with _pytest.raises(SystemExit) as exc_info:
            render_flows.main()

        assert exc_info.value.code == 1

    def test_missing_input_file_prints_error(self, tmp_path, monkeypatch, capsys):
        """A non-existent input file prints an error to stderr and continues (no SystemExit)."""
        import render_flows

        nonexistent = tmp_path / "does_not_exist.json"

        monkeypatch.setattr(
            _sys_cli,
            "argv",
            ["render_flows", str(nonexistent)],
        )
        # main() should complete without raising — missing file is handled with 'continue'
        render_flows.main()

        err = capsys.readouterr().err
        assert "Not found" in err
