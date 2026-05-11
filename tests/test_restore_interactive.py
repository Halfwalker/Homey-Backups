"""
tests/test_restore_interactive.py
──────────────────────────────────
Unit tests for the interactive functions in restore.py:
  - _copy_to_clipboard()
  - _banner()
  - _choose_category()
  - _choose_item()
  - _present_item()
  - main()

All inquirer.prompt calls are mocked — no terminal interaction required.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest
from unittest.mock import patch, MagicMock

import restore


# ---------------------------------------------------------------------------
# TestCopyToClipboard
# ---------------------------------------------------------------------------

class TestCopyToClipboard:

    def test_returns_false_when_no_clipboard_cmd(self):
        with patch("restore._CLIPBOARD_CMD", None):
            result = restore._copy_to_clipboard("hello")
        assert result is False

    def test_returns_true_on_success(self):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("restore._CLIPBOARD_CMD", ["xsel", "--clipboard", "--input"]):
            with patch("restore._sp.Popen", return_value=mock_proc) as mock_popen:
                result = restore._copy_to_clipboard("hello")

        assert result is True
        mock_popen.assert_called_once_with(
            ["xsel", "--clipboard", "--input"],
            stdin=subprocess.PIPE,
            stdout=restore._sp.DEVNULL,
            stderr=restore._sp.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    def test_returns_false_on_nonzero_returncode(self):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 1

        with patch("restore._CLIPBOARD_CMD", ["xsel", "--clipboard", "--input"]):
            with patch("restore._sp.Popen", return_value=mock_proc):
                result = restore._copy_to_clipboard("hello")

        assert result is False

    def test_returns_false_on_exception(self):
        with patch("restore._CLIPBOARD_CMD", ["xsel"]):
            with patch("restore._sp.Popen", side_effect=OSError("no such file")):
                result = restore._copy_to_clipboard("hello")

        assert result is False


# ---------------------------------------------------------------------------
# TestBanner
# ---------------------------------------------------------------------------

class TestBanner:

    def test_prints_banner(self, capsys):
        restore._banner()
        out = capsys.readouterr().out
        assert "Homey Backup" in out


# ---------------------------------------------------------------------------
# TestChooseCategory
# ---------------------------------------------------------------------------

class TestChooseCategory:

    def test_returns_category_string(self):
        with patch("restore.inquirer.prompt", return_value={"category": "device"}):
            result = restore._choose_category()
        assert result == "device"

    def test_raises_keyboard_interrupt_on_none(self):
        with patch("restore.inquirer.prompt", return_value=None):
            with pytest.raises(KeyboardInterrupt):
                restore._choose_category()


# ---------------------------------------------------------------------------
# TestChooseItem
# ---------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {"name": "Living Room Light", "id": "abc-123", "path": pathlib.Path("/tmp/a.json"), "data": {}},
    {"name": "Kitchen Fan",       "id": "def-456", "path": pathlib.Path("/tmp/b.json"), "data": {}},
]


class TestChooseItem:

    def test_returns_selected_item(self):
        side_effects = [
            {"query": ""},
            {"item": SAMPLE_ITEMS[0]},
        ]
        with patch("restore.inquirer.prompt", side_effect=side_effects):
            result = restore._choose_item(SAMPLE_ITEMS, "device")
        assert result is SAMPLE_ITEMS[0]

    def test_back_returns_none(self):
        side_effects = [
            {"query": ""},
            {"item": None},
        ]
        with patch("restore.inquirer.prompt", side_effect=side_effects):
            result = restore._choose_item(SAMPLE_ITEMS, "device")
        assert result is None

    def test_filter_no_match_returns_none(self, capsys):
        side_effects = [
            {"query": "zzznomatch"},
        ]
        with patch("restore.inquirer.prompt", side_effect=side_effects):
            result = restore._choose_item(SAMPLE_ITEMS, "device")
        assert result is None
        out = capsys.readouterr().out
        assert "No device" in out

    def test_raises_keyboard_interrupt_on_filter_none(self):
        with patch("restore.inquirer.prompt", side_effect=[None]):
            with pytest.raises(KeyboardInterrupt):
                restore._choose_item(SAMPLE_ITEMS, "device")

    def test_raises_keyboard_interrupt_on_select_none(self):
        side_effects = [
            {"query": ""},
            None,
        ]
        with patch("restore.inquirer.prompt", side_effect=side_effects):
            with pytest.raises(KeyboardInterrupt):
                restore._choose_item(SAMPLE_ITEMS, "device")


# ---------------------------------------------------------------------------
# TestPresentItem
# ---------------------------------------------------------------------------

class TestPresentItem:

    @pytest.fixture
    def sample_item(self, tmp_path):
        data = {"id": "abc-123", "name": "Living Room Light", "enabled": True}
        p = tmp_path / "device-abc.json"
        p.write_text(json.dumps(data))
        return {"name": "Living Room Light", "id": "abc-123", "path": p, "data": data}

    def test_prints_item_info(self, sample_item, capsys):
        with patch("restore._CLIPBOARD_AVAILABLE", False):
            with patch("restore.inquirer.prompt", return_value={"copy": "No thanks"}):
                restore._present_item(sample_item, "device")
        out = capsys.readouterr().out
        assert "Living Room Light" in out
        assert "abc-123" in out

    def test_copies_to_clipboard_on_yes(self, sample_item):
        with patch("restore._CLIPBOARD_AVAILABLE", True):
            with patch("restore._CLIPBOARD_CMD", ["xsel"]):
                with patch("restore.inquirer.prompt", return_value={"copy": "Yes, copy JSON to clipboard"}):
                    with patch("restore._copy_to_clipboard", return_value=True) as mock_copy:
                        restore._present_item(sample_item, "device")

        mock_copy.assert_called_once()
        call_arg = mock_copy.call_args[0][0]
        # Verify it was called with valid JSON matching the item data
        assert json.loads(call_arg) == sample_item["data"]

    def test_no_copy_on_no_thanks(self, sample_item):
        with patch("restore._CLIPBOARD_AVAILABLE", True):
            with patch("restore.inquirer.prompt", return_value={"copy": "No thanks"}):
                with patch("restore._copy_to_clipboard") as mock_copy:
                    restore._present_item(sample_item, "device")

        mock_copy.assert_not_called()

    def test_advanced_flow_uses_advanced_instructions(self, tmp_path, capsys):
        data = {"id": "f1", "name": "My Flow", "flow_type": "advanced"}
        p = tmp_path / "flow-f1.json"
        p.write_text(json.dumps(data))
        item = {"name": "My Flow", "id": "f1", "path": p, "data": data}

        with patch("restore._CLIPBOARD_AVAILABLE", False):
            with patch("restore.inquirer.prompt", return_value={"copy": "No thanks"}):
                restore._present_item(item, "flow")

        out = capsys.readouterr().out
        assert "ADVANCED FLOW" in out

    def test_no_exception_when_prompt_returns_none(self, sample_item):
        """_present_item handles None from inquirer.prompt gracefully (no exception)."""
        with patch("restore._CLIPBOARD_AVAILABLE", True):
            with patch("restore.inquirer.prompt", return_value=None):
                with patch("restore._copy_to_clipboard") as mock_clip:
                    restore._present_item(sample_item, "device")  # must not raise
        mock_clip.assert_not_called()


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------

class TestMain:

    def test_keyboard_interrupt_at_category_exits(self):
        with patch("sys.argv", ["restore.py"]):
            with patch("restore._choose_category", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    restore.main()
        assert exc_info.value.code == 0

    def test_no_backups_exit_choice(self):
        with patch("sys.argv", ["restore.py"]):
            with patch("restore.list_backup_dates", return_value=[]):
                with patch("restore._choose_category", return_value="device"):
                    with patch("restore.inquirer.prompt", return_value={"action": "Exit"}):
                        with pytest.raises(SystemExit) as exc_info:
                            restore.main()
        assert exc_info.value.code == 0

    def test_no_backups_retry_then_exit(self):
        # Call 1: _choose_category (patched directly) → "device"
        # Call 2: retry prompt in main() → "Choose a different type"
        # Call 3: _choose_category (patched directly) → "device"
        # Call 4: retry prompt in main() → "Exit"
        choose_category_calls = iter(["device", "device"])
        prompt_calls = iter([
            {"action": "Choose a different type"},
            {"action": "Exit"},
        ])

        with patch("sys.argv", ["restore.py"]):
            with patch("restore.list_backup_dates", return_value=[]):
                with patch("restore._choose_category", side_effect=choose_category_calls):
                    with patch("restore.inquirer.prompt", side_effect=prompt_calls):
                        with pytest.raises(SystemExit) as exc_info:
                            restore.main()

        assert exc_info.value.code == 0

    def test_keyboard_interrupt_at_item_select_exits(self, tmp_path):
        fake_dir = tmp_path / "devices"
        fake_dir.mkdir()
        fake_items = [{"name": "X", "id": "1", "path": fake_dir / "x.json", "data": {}}]

        with patch("sys.argv", ["restore.py"]):
            with patch("restore.list_backup_dates", return_value=[fake_dir]):
                with patch("restore._choose_category", return_value="device"):
                    with patch("restore._load_items", return_value=fake_items):
                        with patch("restore.inquirer.prompt", return_value={"date_dir": fake_dir}):
                            with patch("restore._choose_item", side_effect=KeyboardInterrupt):
                                with pytest.raises(SystemExit) as exc_info:
                                    restore.main()

        assert exc_info.value.code == 0

    def test_item_selected_then_exit(self, tmp_path):
        fake_dir = tmp_path / "devices"
        fake_dir.mkdir()
        fake_items = [{"name": "X", "id": "1", "path": fake_dir / "x.json", "data": {}}]
        selected = fake_items[0]

        prompt_calls = iter([
            {"date_dir": fake_dir},        # date selection in main()
            {"again": "Exit"},             # "restore another?" prompt
        ])

        with patch("sys.argv", ["restore.py"]):
            with patch("restore.list_backup_dates", return_value=[fake_dir]):
                with patch("restore._choose_category", return_value="device"):
                    with patch("restore._load_items", return_value=fake_items):
                        with patch("restore.inquirer.prompt", side_effect=prompt_calls):
                            with patch("restore._choose_item", return_value=selected):
                                with patch("restore._present_item"):
                                    with pytest.raises(SystemExit) as exc_info:
                                        restore.main()

        assert exc_info.value.code == 0

    def test_back_from_choose_item_then_exit(self, tmp_path):
        fake_dir = tmp_path / "devices"
        fake_dir.mkdir()
        fake_items = [{"name": "X", "id": "1", "path": fake_dir / "x.json", "data": {}}]

        # First pass: _choose_item returns None (Back), loop continues
        # Second pass: _choose_category raises KeyboardInterrupt → sys.exit(0)
        choose_category_calls = iter(["device", KeyboardInterrupt()])

        def _choose_category_side_effect():
            val = next(choose_category_calls)
            if isinstance(val, BaseException):
                raise val
            return val

        prompt_calls = iter([
            {"date_dir": fake_dir},  # date selection — first pass
        ])

        with patch("sys.argv", ["restore.py"]):
            with patch("restore.list_backup_dates", return_value=[fake_dir]):
                with patch("restore._choose_category", side_effect=_choose_category_side_effect):
                    with patch("restore._load_items", return_value=fake_items):
                        with patch("restore.inquirer.prompt", side_effect=prompt_calls):
                            with patch("restore._choose_item", return_value=None):
                                with pytest.raises(SystemExit) as exc_info:
                                    restore.main()

        assert exc_info.value.code == 0
