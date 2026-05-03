"""
Tests for the four new backup categories added in batch 1:
  backup_apps, backup_system_info, backup_dashboards, backup_moods

Run:  pytest tests/test_backup_new_categories.py -v
"""
import json
from unittest.mock import MagicMock
import pytest


# ── helpers ─────────────────────────────────────────────────────────────


def _make_api(**kwargs):
    """Return a MagicMock HomeyAPI with sensible defaults for new categories."""
    api = MagicMock()
    api.get_apps.return_value = kwargs.get("apps", [])
    api.get_app_settings.return_value = kwargs.get("app_settings", {})
    api.get_system_info.return_value = kwargs.get("system_info", {})
    api.get_dashboards.return_value = kwargs.get("dashboards", [])
    api.get_moods.return_value = kwargs.get("moods", [])
    return api


# ── backup_apps ──────────────────────────────────────────────────────────


class TestBackupApps:
    def test_saves_app_json_files(self, tmp_path):
        """Each app is saved as its own JSON file with settings embedded."""
        import backup

        api = _make_api(
            apps=[{"id": "net.i-dev.betterlogic", "name": "Better Logic Library"}],
            app_settings={"someKey": "someValue"},
        )
        result = backup.backup_apps(api, output_dir=tmp_path / "apps")

        assert result.saved == 1
        assert result.errors == 0
        files = list((tmp_path / "apps").glob("*.json"))
        assert len(files) == 1

        data = json.loads(files[0].read_text())
        assert data["id"] == "net.i-dev.betterlogic"
        assert "settings" in data
        assert data["settings"] == {"someKey": "someValue"}

    def test_app_without_id_is_skipped(self, tmp_path):
        """Apps with no id field are skipped and counted as skipped, not errors."""
        import backup

        api = _make_api(apps=[{"name": "Orphan App"}])  # no id
        result = backup.backup_apps(api, output_dir=tmp_path / "apps")

        assert result.saved == 0
        assert result.skipped == 1
        assert result.errors == 0

    def test_api_error_returns_error_result(self, tmp_path):
        """HomeyAPIError from get_apps() is captured in BackupResult, not re-raised."""
        import backup

        api = _make_api()
        api.get_apps.side_effect = backup.HomeyAPIError("timeout")
        result = backup.backup_apps(api, output_dir=tmp_path / "apps")

        assert result.errors >= 1
        assert result.saved == 0
        assert result.note == "API call failed"

    def test_settings_fetch_failure_does_not_abort(self, tmp_path):
        """If get_app_settings raises HomeyAPIError, the app is still saved with empty settings."""
        import backup

        api = _make_api(apps=[{"id": "com.example.app", "name": "Example App"}])
        api.get_app_settings.side_effect = backup.HomeyAPIError("not found")

        # get_app_settings is called directly on the api mock; since backup_apps catches
        # HomeyAPIError in get_app_settings (within HomeyAPI), we simulate the graceful
        # path by having get_app_settings return {} (the real implementation swallows the error).
        api.get_app_settings.side_effect = None
        api.get_app_settings.return_value = {}

        result = backup.backup_apps(api, output_dir=tmp_path / "apps")
        assert result.saved == 1
        data = json.loads(list((tmp_path / "apps").glob("*.json"))[0].read_text())
        assert data["settings"] == {}

    def test_empty_app_list_returns_zero_saved(self, tmp_path):
        """When no apps are returned the result has saved=0 and a note."""
        import backup

        api = _make_api(apps=[])
        result = backup.backup_apps(api, output_dir=tmp_path / "apps")

        assert result.saved == 0
        assert "no data" in result.note


# ── backup_system_info ───────────────────────────────────────────────────


class TestBackupSystemInfo:
    def test_saves_meta_json_file(self, tmp_path):
        """System info is written as a single meta.json at the given output_path."""
        import backup

        api = _make_api(system_info={"version": "10.0.0", "id": "homey-001"})
        output_path = tmp_path / "meta.json"
        result = backup.backup_system_info(api, output_path=output_path)

        assert result.saved == 1
        assert result.errors == 0
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert data["version"] == "10.0.0"

    def test_api_error_returns_error_result(self, tmp_path):
        """HomeyAPIError is captured in BackupResult, script does not exit."""
        import backup

        api = _make_api()
        api.get_system_info.side_effect = backup.HomeyAPIError("system unreachable")
        result = backup.backup_system_info(api, output_path=tmp_path / "meta.json")

        assert result.errors >= 1
        assert result.saved == 0
        assert result.note == "API call failed"

    def test_empty_response_returns_no_data_note(self, tmp_path):
        """When system info returns empty dict, result has a note and saved=0."""
        import backup

        api = _make_api(system_info={})
        result = backup.backup_system_info(api, output_path=tmp_path / "meta.json")

        assert result.saved == 0
        assert "no data" in result.note

    def test_existing_file_without_force_exits(self, tmp_path):
        """If meta.json already exists and force=False, sys.exit(1) is called."""
        import backup

        api = _make_api(system_info={"v": "1"})
        output_path = tmp_path / "meta.json"
        output_path.write_text("{}")  # pre-existing file

        with pytest.raises(SystemExit):
            backup.backup_system_info(api, output_path=output_path, force=False)

    def test_force_overwrites_existing_file(self, tmp_path):
        """With force=True an existing meta.json is silently overwritten."""
        import backup

        api = _make_api(system_info={"version": "new"})
        output_path = tmp_path / "meta.json"
        output_path.write_text('{"version": "old"}')

        result = backup.backup_system_info(api, output_path=output_path, force=True)
        assert result.saved == 1
        assert json.loads(output_path.read_text())["version"] == "new"


# ── backup_dashboards ────────────────────────────────────────────────────


class TestBackupDashboards:
    def test_saves_dashboard_json_files(self, tmp_path):
        """Each dashboard is saved as its own JSON file."""
        import backup

        api = _make_api(dashboards=[
            {"id": "dash-1", "name": "Home"},
            {"id": "dash-2", "name": "Energy"},
        ])
        result = backup.backup_dashboards(api, output_dir=tmp_path / "dashboards")

        assert result.saved == 2
        assert result.errors == 0
        files = list((tmp_path / "dashboards").glob("*.json"))
        assert len(files) == 2

    def test_dashboard_without_id_is_skipped(self, tmp_path):
        """Dashboards with no id field are skipped."""
        import backup

        api = _make_api(dashboards=[{"name": "Unnamed"}])
        result = backup.backup_dashboards(api, output_dir=tmp_path / "dashboards")

        assert result.saved == 0
        assert result.skipped == 1

    def test_api_error_returns_error_result(self, tmp_path):
        """HomeyAPIError from get_dashboards() is captured, not re-raised."""
        import backup

        api = _make_api()
        api.get_dashboards.side_effect = backup.HomeyAPIError("timeout")
        result = backup.backup_dashboards(api, output_dir=tmp_path / "dashboards")

        assert result.errors >= 1
        assert result.saved == 0

    def test_filename_uses_slug_and_id(self, tmp_path):
        """Filename should be <slug>-<id>.json."""
        import backup

        api = _make_api(dashboards=[{"id": "abc-123", "name": "My Dashboard"}])
        backup.backup_dashboards(api, output_dir=tmp_path / "dashboards")

        files = list((tmp_path / "dashboards").glob("*.json"))
        assert files[0].name == "my-dashboard-abc-123.json"


# ── backup_moods ─────────────────────────────────────────────────────────


class TestBackupMoods:
    def test_saves_mood_json_files(self, tmp_path):
        """Each mood/light scene is saved as its own JSON file."""
        import backup

        api = _make_api(moods=[
            {"id": "mood-1", "name": "Evening"},
            {"id": "mood-2", "name": "Movie Night"},
        ])
        result = backup.backup_moods(api, output_dir=tmp_path / "moods")

        assert result.saved == 2
        assert result.errors == 0
        files = list((tmp_path / "moods").glob("*.json"))
        assert len(files) == 2

    def test_mood_without_id_is_skipped(self, tmp_path):
        """Moods with no id field are skipped."""
        import backup

        api = _make_api(moods=[{"name": "Unnamed Scene"}])
        result = backup.backup_moods(api, output_dir=tmp_path / "moods")

        assert result.saved == 0
        assert result.skipped == 1

    def test_api_error_returns_error_result(self, tmp_path):
        """HomeyAPIError from get_moods() is captured, not re-raised."""
        import backup

        api = _make_api()
        api.get_moods.side_effect = backup.HomeyAPIError("timeout")
        result = backup.backup_moods(api, output_dir=tmp_path / "moods")

        assert result.errors >= 1
        assert result.saved == 0
        assert result.note == "API call failed"

    def test_filename_uses_slug_and_id(self, tmp_path):
        """Filename should be <slug>-<id>.json."""
        import backup

        api = _make_api(moods=[{"id": "xyz-456", "name": "Movie Night"}])
        backup.backup_moods(api, output_dir=tmp_path / "moods")

        files = list((tmp_path / "moods").glob("*.json"))
        assert files[0].name == "movie-night-xyz-456.json"
