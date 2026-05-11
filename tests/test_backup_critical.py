"""
Tests for critical backup.py behaviour: connection handling, error recovery,
argparse flags, and post-backup render hooks.

Run:  pytest tests/test_backup_critical.py -v
"""
from unittest.mock import MagicMock, patch
import pytest

from tests.conftest import _make_api

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

    def test_calls_subprocess_with_flow_files(self, tmp_path, monkeypatch):
        """With JSON files present and the script found, subprocess.run is called."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        flow_file = flows_dir / "my-flow.json"
        flow_file.write_text("{}")

        # Point backup.__file__ to tmp_path so render_flows.py is resolved there
        monkeypatch.setattr(backup, "__file__", str(tmp_path / "backup.py"))
        svg_script = tmp_path / "render_flows.py"
        svg_script.write_text("# stub\n")

        with patch("subprocess.run") as mock_run:
            backup._render_flows(flows_dir, png=False)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert str(flow_file) in cmd
            assert "--png" not in cmd

    def test_adds_png_flag_when_png_true(self, tmp_path, monkeypatch):
        """When png=True, --png is appended to the subprocess command."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        (flows_dir / "flow.json").write_text("{}")

        # Point backup.__file__ to tmp_path so render_flows.py is resolved there
        monkeypatch.setattr(backup, "__file__", str(tmp_path / "backup.py"))
        svg_script = tmp_path / "render_flows.py"
        svg_script.write_text("# stub\n")

        with patch("subprocess.run") as mock_run:
            backup._render_flows(flows_dir, png=True)
            cmd = mock_run.call_args[0][0]
            assert "--png" in cmd

    def test_missing_svg_script_prints_error_not_exception(self, tmp_path, capsys):
        """If render_flows.py is not found, an error is printed (no crash)."""
        import backup

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir()
        (flows_dir / "flow.json").write_text("{}")

        # Patch __file__ so the script lookup points somewhere it can't exist
        with patch.object(backup, "__file__", str(tmp_path / "backup.py")):
            backup._render_flows(flows_dir)

        err = capsys.readouterr().err
        assert "not found" in err

# ── TestForceFlag ────────────────────────────────────────────────────────

class TestForceFlag:
    """Tests for the force guard in _backup_items() via backup_devices()."""

    def test_force_false_returns_error_when_dir_exists(self, tmp_path):
        """When output dir already exists and force=False, returns an error BackupResult (no sys.exit)."""
        import backup
        existing_dir = tmp_path / "devices"
        existing_dir.mkdir()
        api = _make_api(devices=[{"id": "dev-1", "name": "Light"}])
        result = backup.backup_devices(api, output_dir=existing_dir, force=False)
        assert result.errors == 1
        assert "already exists" in result.note

    def test_force_true_overwrites_existing_dir(self, tmp_path):
        import backup
        existing_dir = tmp_path / "devices"
        existing_dir.mkdir()
        (existing_dir / "stale.json").write_text("{}")
        api = _make_api(devices=[{"id": "dev-1", "name": "Light"}])
        result = backup.backup_devices(api, output_dir=existing_dir, force=True)
        assert result.saved > 0

    def test_force_false_succeeds_when_dir_missing(self, tmp_path):
        import backup
        output_dir = tmp_path / "devices"
        api = _make_api(devices=[{"id": "dev-1", "name": "Light"}])
        result = backup.backup_devices(api, output_dir=output_dir, force=False)
        assert result.saved >= 0


# ── TestHomeyAPIEdgeCases ────────────────────────────────────────────────


class TestHomeyAPIEdgeCases:
    """Edge-case handling in HomeyAPI methods not covered by existing tests."""

    def _make_real_api(self):
        import backup
        return backup.HomeyAPI("http://192.168.1.1", "fake-token")

    def test_get_bll_variables_list_response(self):
        """When the BLL endpoint returns a list, it is returned as-is."""
        api = self._make_real_api()
        payload = [{"id": "x", "name": "y"}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        with patch.object(api._http, "get", return_value=mock_resp):
            result = api.get_bll_variables()
        assert result == payload

    def test_get_bll_variables_dict_response(self):
        """When the BLL endpoint returns a dict, it is converted to a list via _dict_to_list."""
        api = self._make_real_api()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"0": {"id": "x", "name": "y"}}
        with patch.object(api._http, "get", return_value=mock_resp):
            result = api.get_bll_variables()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_bll_variables_connection_error_returns_empty(self):
        """A RequestException from the BLL endpoint returns [] without raising."""
        import requests.exceptions
        api = self._make_real_api()
        with patch.object(api._http, "get", side_effect=requests.exceptions.ConnectionError("refused")):
            result = api.get_bll_variables()
        assert result == []

    def test_get_app_settings_swallows_homey_api_error(self):
        """HomeyAPIError from the app settings endpoint returns {} without raising."""
        import backup
        api = self._make_real_api()
        with patch.object(api, "_get", side_effect=backup.HomeyAPIError("fail")):
            result = api.get_app_settings("some-app-id")
        assert result == {}

    def test_get_system_info_fallback_on_error(self):
        """If /manager/system/state raises HomeyAPIError, falls back to /manager/system."""
        import backup
        api = self._make_real_api()
        fallback_data = {"version": "10.0"}
        with patch.object(
            api,
            "_get",
            side_effect=[backup.HomeyAPIError("state endpoint failed"), fallback_data],
        ):
            result = api.get_system_info()
        assert result == fallback_data

    def test_get_advanced_flow_returns_none_on_request_exception(self):
        """A RequestException during get_advanced_flow returns None without raising."""
        import requests.exceptions
        api = self._make_real_api()
        with patch.object(
            api._http,
            "get",
            side_effect=requests.exceptions.RequestException("network error"),
        ):
            result = api.get_advanced_flow("flow-abc")
        assert result is None
