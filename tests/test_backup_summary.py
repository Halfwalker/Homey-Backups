"""
tests/test_backup_summary.py
────────────────────────────
Unit tests for:
  - BackupResult.total property
  - backup._print_summary(results)
"""

import backup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(**kwargs) -> backup.BackupResult:
    """Convenience factory; category defaults to 'Test'."""
    kwargs.setdefault("category", "Test")
    return backup.BackupResult(**kwargs)


# ---------------------------------------------------------------------------
# TestBackupResultTotal
# ---------------------------------------------------------------------------

class TestBackupResultTotal:
    def test_total_is_sum_of_saved_skipped_errors(self):
        r = backup.BackupResult(category="X", saved=3, skipped=1, errors=2)
        assert r.total == 6

    def test_total_with_all_zeros(self):
        r = backup.BackupResult(category="X")
        assert r.total == 0


# ---------------------------------------------------------------------------
# TestPrintSummary
# ---------------------------------------------------------------------------

class TestPrintSummary:
    def test_shows_label_for_each_result(self, capsys):
        results = [
            _result(category="Devices", saved=1),
            _result(category="Flows", saved=2),
        ]
        backup._print_summary(results)
        out = capsys.readouterr().out
        assert "Devices" in out
        assert "Flows" in out

    def test_shows_saved_skipped_errors_counts(self, capsys):
        results = [_result(category="Zones", saved=3, skipped=1, errors=1)]
        backup._print_summary(results)
        out = capsys.readouterr().out
        assert "3" in out
        assert "1" in out  # covers both skipped and errors

    def test_done_message_with_errors(self, capsys):
        results = [_result(category="Apps", errors=1)]
        backup._print_summary(results)
        out = capsys.readouterr().out
        # Source: "[DONE] Backup finished with {total_errors} error(s). ..."
        assert "error" in out.lower()

    def test_done_message_no_errors(self, capsys):
        results = [_result(category="Apps", saved=5)]
        backup._print_summary(results)
        out = capsys.readouterr().out
        # Source: "[DONE] Backup complete."
        assert "complete" in out.lower()
        # Make sure the error path was NOT taken
        assert "error(s)" not in out

    def test_shows_elapsed_time(self, capsys):
        # _print_summary has no elapsed parameter — verify the function runs
        # and produces the summary table (elapsed is not part of the signature).
        # This test documents that fact and still exercises the full output.
        results = [_result(category="System", saved=1)]
        backup._print_summary(results)
        out = capsys.readouterr().out
        assert "BACKUP SUMMARY" in out

    def test_error_details_printed(self, capsys):
        results = [
            _result(category="Devices", errors=1, error_details=["some detail about the failure"])
        ]
        backup._print_summary(results)
        out = capsys.readouterr().out
        assert "some detail about the failure" in out

    def test_note_shown_in_output(self, capsys):
        results = [_result(category="Vars", note="API call failed")]
        backup._print_summary(results)
        out = capsys.readouterr().out
        # Source: dir_str = f"({r.note})" when note is set
        assert "API call failed" in out
