"""
Tests for critical backup.py behaviour: connection handling, error recovery,
argparse flags, and post-backup render hooks.

Run:  pytest tests/test_backup_critical.py -v
"""
import pathlib
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

# ── helpers ─────────────────────────────────────────────────────────────


def _make_api(devices=None, flows=None, advanced_flows=None,
              flow_folders=None, zones=None, logic_vars=None, bll_vars=None):
    """Return a MagicMock HomeyAPI pre-configured with empty-list defaults."""
    api = MagicMock()
    api.get_devices.return_value = devices if devices is not None else []
    api.get_flows.return_value = flows if flows is not None else []
    api.get_advanced_flows.return_value = advanced_flows if advanced_flows is not None else []
    api.get_flow_folders.return_value = flow_folders if flow_folders is not None else []
    api.get_zones.return_value = zones if zones is not None else []
    api.get_logic_variables.return_value = logic_vars if logic_vars is not None else []
    api.get_bll_variables.return_value = bll_vars if bll_vars is not None else []
    return api


# ── Critical 1.1 — HomeyAPIError ──────────────────────────────────────


class TestHomeyAPIError:
    """_get() should raise HomeyAPIError (not call sys.exit) on network or HTTP errors."""

    def test_connection_error_raises_homey_api_error(self):
        """Connection failure must raise HomeyAPIError, not sys.exit(1)."""
        import backup
        api = backup.HomeyAPI("http://192.168.1.1", "fake-token")
        import requests.exceptions
        with patch.object(api._http, "get",
                          side_effect=requests.exceptions.ConnectionError("refused")):
            with pytest.raises(backup.HomeyAPIError):
                api._get("/manager/devices/device")

    def test_timeout_raises_homey_api_error(self):
        """Request timeout must raise HomeyAPIError, not sys.exit(1)."""
        import backup
        api = backup.HomeyAPI("http://192.168.1.1", "fake-token")
        import requests.exceptions
        with patch.object(api._http, "get",
                          side_effect=requests.exceptions.Timeout("timed out")):
            with pytest.raises(backup.HomeyAPIError):
                api._get("/manager/flow/flow")

    def test_http_error_status_raises_homey_api_error(self):
        """Non-200 HTTP response must raise HomeyAPIError, not sys.exit(1)."""
        import backup
        api = backup.HomeyAPI("http://192.168.1.1", "fake-token")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch.object(api._http, "get", return_value=mock_resp):
            with pytest.raises(backup.HomeyAPIError):
                api._get("/manager/devices/device")

    def test_backup_devices_returns_error_result_on_api_failure(self, tmp_path):
        """When the API fails, backup_devices() must return BackupResult with errors, not exit."""
        import backup
        api = backup.HomeyAPI("http://192.168.1.1", "fake-token")
        with patch.object(api, "get_devices",
                          side_effect=backup.HomeyAPIError("cannot connect")):
            result = backup.backup_devices(api, output_dir=tmp_path / "devices")
        assert result.errors >= 1
        assert result.saved == 0

    def test_backup_continues_after_single_category_failure(self, tmp_path):
        """If devices API fails, main() should continue to other categories."""
        import backup
        api = backup.HomeyAPI("http://192.168.1.1", "fake-token")

        # devices will fail; others return empty
        with patch.object(api, "get_devices",
                          side_effect=backup.HomeyAPIError("cannot connect")):
            with patch.object(api, "get_flows", return_value=[]):
                with patch.object(api, "get_advanced_flows", return_value=[]):
                    device_result = backup.backup_devices(
                        api, output_dir=tmp_path / "devices"
                    )
        # Other categories can still run — just verify devices reported an error
        assert device_result.errors >= 1


# ── Critical 1.2 — output_dir parameter / no module-level globals ─────


class TestOutputDirParameter:
    """backup_* functions must accept an output_dir parameter."""

    def test_backup_devices_accepts_output_dir(self, tmp_path):
        """backup_devices() must accept an output_dir parameter and write there."""
        import backup
        api = _make_api(devices=[{"id": "dev-1", "name": "My Sensor"}])
        out = tmp_path / "my_devices"
        result = backup.backup_devices(api, output_dir=out)
        assert result.saved == 1
        assert out.exists()
        files = list(out.glob("*.json"))
        assert len(files) == 1

    def test_backup_flows_accepts_output_dir(self, tmp_path):
        """backup_flows() must accept an output_dir parameter and write there."""
        import backup
        api = _make_api(flows=[{"id": "f-1", "name": "My Flow",
                                 "trigger": {}, "conditions": [], "actions": []}])
        out = tmp_path / "my_flows"
        result = backup.backup_flows(api, output_dir=out)
        assert result.saved == 1
        assert out.exists()

    def test_backup_zones_accepts_output_dir(self, tmp_path):
        """backup_zones() must accept an output_dir parameter and write there."""
        import backup
        api = _make_api(zones=[{"id": "z-1", "name": "Kitchen"}])
        out = tmp_path / "my_zones"
        result = backup.backup_zones(api, output_dir=out)
        assert result.saved == 1
        assert out.exists()

    def test_backup_flow_folders_accepts_output_dir(self, tmp_path):
        """backup_flow_folders() must accept an output_dir parameter and write there."""
        import backup
        api = _make_api(flow_folders=[{"id": "ff-1", "name": "Lighting"}])
        out = tmp_path / "my_folders"
        result = backup.backup_flow_folders(api, output_dir=out)
        assert result.saved == 1
        assert out.exists()

    def test_backup_logic_variables_accepts_output_dir(self, tmp_path):
        """backup_logic_variables() must accept an output_dir parameter and write there."""
        import backup
        api = _make_api(logic_vars=[{"id": "var-1", "name": "Morning Mode", "type": "boolean", "value": True}])
        out = tmp_path / "my_vars"
        result = backup.backup_logic_variables(api, output_dir=out)
        assert result.saved == 1
        assert out.exists()

    def test_import_does_not_create_directories(self):
        """Importing backup.py must not create any directories on disk."""
        # The module-level *_DIR globals currently resolve to real paths
        # but should NOT mkdir them. After the fix, they should not exist at
        # module level at all.
        import backup
        # None of the module-level dirs should have been created just by importing
        import importlib
        if "backup" in sys.modules:
            importlib.reload(backup)
        # The key assertion: backup module's *_DIR globals (if any) must not exist on disk
        for attr in ("DEVICES_DIR", "FLOWS_DIR", "ZONES_DIR", "VARIABLES_DIR", "FLOW_FOLDERS_DIR"):
            if hasattr(backup, attr):
                p = getattr(backup, attr)
                if isinstance(p, pathlib.Path):
                    assert not p.exists(), (
                        f"Importing backup.py created {p} — "
                        f"module-level dirs must not be created at import time (fix B3)"
                    )


# ── _render_flows ────────────────────────────────────────────────────────


class TestRenderFlows:
    def test_skips_when_flows_dir_missing(self, tmp_path, capsys):
        """If flows/ dir doesn't exist, _render_flows prints a skip message and does nothing."""
        import backup

        backup._render_flows(tmp_path / "flows")

        out = capsys.readouterr().out
        assert "SKIP" in out
        assert "does not exist" in out

    def test_skips_when_flows_dir_is_empty(self, tmp_path, capsys):
        """If flows/ exists but has no JSON files, _render_flows prints a skip message."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()

        backup._render_flows(flows_dir)

        out = capsys.readouterr().out
        assert "SKIP" in out
        assert "no JSON files" in out

    def test_calls_subprocess_with_flow_files(self, tmp_path):
        """With JSON files present and the script found, subprocess.run is called."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        flow_file = flows_dir / "my-flow.json"
        flow_file.write_text("{}")

        # Place a fake homey_flow_svg.py next to backup.py
        svg_script = pathlib.Path(backup.__file__).parent / "homey_flow_svg.py"
        created = False
        if not svg_script.exists():
            svg_script.write_text("# stub\n")
            created = True

        try:
            with patch("subprocess.run") as mock_run:
                backup._render_flows(flows_dir, png=False)
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert str(flow_file) in cmd
                assert "--png" not in cmd
        finally:
            if created:
                svg_script.unlink()

    def test_adds_png_flag_when_png_true(self, tmp_path):
        """When png=True, --png is appended to the subprocess command."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        (flows_dir / "flow.json").write_text("{}")

        svg_script = pathlib.Path(backup.__file__).parent / "homey_flow_svg.py"
        created = False
        if not svg_script.exists():
            svg_script.write_text("# stub\n")
            created = True

        try:
            with patch("subprocess.run") as mock_run:
                backup._render_flows(flows_dir, png=True)
                cmd = mock_run.call_args[0][0]
                assert "--png" in cmd
        finally:
            if created:
                svg_script.unlink()

    def test_missing_svg_script_prints_error_not_exception(self, tmp_path, capsys):
        """If homey_flow_svg.py is not found, an error is printed (no crash)."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        (flows_dir / "flow.json").write_text("{}")

        # Patch __file__ so the script lookup points somewhere it can't exist
        with patch.object(backup, "__file__", str(tmp_path / "backup.py")):
            backup._render_flows(flows_dir)

        err = capsys.readouterr().err
        assert "not found" in err
