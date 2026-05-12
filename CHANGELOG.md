# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

---

## [0.3.3] — 2026-05-11

Code quality and test coverage improvements for the render_flows package.

### Fixed
- `render_flows/_svg_builder.py`: SVG attribute values now escaped with `html.escape()` — prevents injecting unescaped `<`, `>`, `&` from device or flow names
- `render_flows/_cli.py`: `--filter` no longer prints `→ FlowName` before the "Skipped" message — progress line now only appears for flows that pass the filter
- `render_flows/_renderers.py`: `render_flow()` now guards the `cards` field type — warns and returns `None` if `cards` is a list instead of a dict, rather than crashing

### Changed
- `render_flows/_renderers.py`: `render_flow()` and `render_standard_flow()` now accept a `verbose=True` parameter — pass `False` to suppress the `✓ … cards` summary line when using these functions as a library
- `render_flows/_renderers.py`: `render_flow()` and `render_standard_flow()` now return `Path | None` (the written output path) instead of `None`

### Tests
- `tests/test_svg_critical.py`: 3 new tests covering previously untested paths: `_write_output()` `SystemExit` when cairosvg is missing, `_auto_discover_sibling()` non-timestamp dir rejection, and `render_flow()` write permission error propagation

### Docs
- `README.md`: `geolocation.json` flagged as sensitive — contains home latitude, longitude and address; added privacy note advising against committing `Backups/` to a public repository

---

## [0.3.2] — 2026-05-11

Oracle-reviewed quality pass: clipboard fix, doc gaps, test coverage, and code cleanup.

### Fixed
- `restore.py`: backup date list now shows newest timestamp first (was ascending)
- `restore.py`: clipboard now works on macOS (`pbcopy`) and Windows (`clip.exe`) — broken after pyperclip removal

### Changed
- `backup.py`: extracted `_default_filename()` helper, eliminating 7 near-identical closures across backup functions
- Removed `pyperclip` dependency — clipboard is now handled via subprocess; no external library needed

### Docs
- `TECHDOCS.md`: filled 5 gaps — interactive menu categories, re-import table, module dependency graph, `render_flow()`/`render_standard_flow()` signatures, disabled-flow overlay wording
- `RECOVERY.md`: added mood restoration step, app settings restoration step, and zone UUID remapping warning
- `README.md`: updated clipboard troubleshooting — removed stale pyperclip advice, added macOS/Windows guidance

### Tests
- `test_restore_interactive.py`: 23 new tests covering interactive restore functions — `restore.py` coverage 31% → 92%
- `test_backup_critical.py`: 6 new `TestMain` tests covering `backup.main()` env validation, all 10 backup categories, and render flag dispatch
- `test_label_parser.py`: 18 new branch-coverage tests — `_label_parser.py` 85% → 100%
- Added end-to-end SVG render pipeline integration tests
- Housekeeping: unified `_make_api` in `conftest.py`, removed dead `_write_json`, reformatted 190-char line in `_cli.py`

---

## [0.3.1] — 2026-05-08

No user-facing changes. Full test infrastructure overhaul.

### Added
- Coverage tooling: `pyproject.toml` `[tool.coverage]` source/omit config,
  `tests/run_tests.sh` updated with `--cov` flags, `ci.yml` updated for coverage reporting
- `tests/conftest.py` — centralized path setup and shared fixtures; eliminates
  per-file `sys.path.insert` hacks across the test suite
- `tests/test_label_parser.py` — 40 tests covering `_resolve_placeholders`,
  `_resolve_uri_refs`, `_resolve_trigger_refs`, and 20+ `_parse_label` card-type branches
- `tests/test_lookups.py` — 19 tests for 5 previously-untested lookup builder functions
  (`_build_variable_lookup`, `_build_device_lookup`, `_build_cap_titles`,
  `_build_zone_lookup`, `_build_trigger_name_map`)
- `tests/test_restore_core.py` — 14 tests for `_load_items` and `_filter_items` in `restore.py`
- `tests/test_backup_summary.py` — 9 tests for `_print_summary` and `BackupResult.total`

### Changed
- `tests/test_backup_critical.py`: +6 `HomeyAPI` error-path tests; subprocess tests
  refactored to use `monkeypatch` on `backup.__file__` (no longer write stub files
  into the real project tree); removed dead `test_import_does_not_create_directories`
- `tests/test_render_flows_package.py`: +35 tests — parametrized `_card_badge` across
  all URI patterns, `SVGBuilder` edge cases, and `render_standard_flow` direct call
- `tests/test_svg_critical.py`: +3 CLI flag tests; manual `sys.argv` backup/restore
  replaced with `monkeypatch`; mid-file `sys.path.insert` removed; `import render_flows`
  moved to top-level imports
- `tests/test_pure_functions.py`: per-file `sys.path.insert` removed
- `tests/test_backup_new_categories.py`: renamed `test_settings_fetch_failure_does_not_abort`
  → `test_app_saved_with_empty_settings`; removed dead `side_effect` override code

### Tests
- 124 → 249 tests (+125); coverage 53% → 76%

---

## [0.3.0] — 2026-05-04

### Added
- `render_flows/` package — `homey_flow_svg.py` (1605 lines) extracted into 8 focused modules:
  `_constants`, `_label_parser`, `_lookups`, `_svg_builder`, `_renderers`, `_cli`,
  `__init__`, `__main__`; acyclic dependency graph, fully unit-testable
- `render_flows.py` — new primary CLI script (`uv run render_flows.py`); replaces `homey_flow_svg.py`
- `python -m render_flows` invocation via `render_flows/__main__.py`
- `render-flows` pyproject entry point (`render-flows = "render_flows:main"`)
- `tests/test_render_flows_package.py` — 13 smoke tests for direct `render_flows.*` imports
- GitHub Actions CI workflow with local `act` runner support (`.github/workflows/ci.yml`)
- Matrix test strategy across Python 3.11 / 3.12 / 3.13 with summary step
- `tests/run_ci_local.sh` helper to run the matrix locally via `act`
- 13 additional tests for `_build_folder_lookup`, `list_backup_dates`, `--force` flag, and folder SVG prefix

### Fixed
- Pre-existing ruff lint errors in test files (E402, F401) that blocked pre-commit hooks

### Changed
- `homey_flow_svg.py` removed; replaced by `render_flows.py` (script) + `render_flows/` (package)
- `pyproject.toml`: added `packages = ["render_flows"]`; removed obsolete `homey-flow-svg` entry point;
  declared `py-modules` explicitly to satisfy newer pip
- All three CLI scripts now follow `uv run <name>.py` convention:
  `backup.py`, `restore.py`, `render_flows.py`
- Tests updated to import directly from canonical `render_flows.*` modules (not via shim)
- `.gitignore` updated to exclude `.tokensave/` cache directory

### Tests
- 98 → 124 tests (+26 across batch-4 and render_flows package smoke tests)

---

## [0.2.1] — 2026-05-03

### Changed
- Extracted `_auto_discover_sibling(inputs, sibling_name)` helper in `homey_flow_svg.py` — four
  near-identical 8-line discovery loops replaced with one-liners
- TECHDOCS auto-discovery section corrected to describe the actual algorithm

### Tests
- 94 → 98 tests (+4 for `_auto_discover_sibling`)

---

## [0.2.0] — 2026-05-02

### Added
- New backup categories: apps (with per-app settings), system info (`meta.json`),
  dashboards, light scenes (moods), home geolocation config
- `--render-svg` flag on `backup.py`: auto-renders SVG diagrams after backup
- `--render-png` flag on `backup.py`: auto-renders PNG diagrams after backup (requires cairosvg)
- `--force` flag on `backup.py` to overwrite existing backup directories
- Cross-reference comments linking `CATEGORY_SUBDIRS` coupling between `backup.py` and `restore.py`

### Changed
- `_backup_items()` generic helper extracted in `backup.py` — eliminated ~200 lines of per-category
  boilerplate; backup.py: 637 → 538 lines

### Tests
- 84 → 94 tests (+10 for new backup categories and render hook edge cases)

---

## [0.1.0] — 2026-04-01

Initial release.

### Added
- `backup.py` — backs up devices, flows (standard + advanced), flow folders, zones, logic variables,
  and Better Logic Library variables to `Backups/<TIMESTAMP>/<category>/`
- `restore.py` — dry-run JSON preview, filter by ID, flow-type import instructions
- `homey_flow_svg.py` — renders standard and advanced flows as SVG/PNG diagrams; auto-discovers
  companion backup files (devices, zones, variables, flow folders) from the backup directory;
  folder prefix in titles, `--filter` flag, cairosvg PEP 723 inline dependency
- JWT validation and path-length truncation in `backup.py`
- `--version` flag on all three scripts
- `pyproject.toml` with entry points for `backup`, `restore`, and `svg` CLI commands
- `ruff` dev dependency + `pre-commit` configuration
- 53 unit tests for pure functions in the SVG renderer
- Critical integration tests for `backup.py` (`HomeyAPIError`, output directory assertions)

### Changed
- Output directory structure reorganised from `<category>/<TIMESTAMP>/` to
  `Backups/<TIMESTAMP>/<category>/` for a cleaner per-snapshot layout
- `restore.py` updated to discover backups under `Backups/<TIMESTAMP>/`
- `_backup_items()` helper extracted in `backup.py` to eliminate per-category boilerplate

[Unreleased]: https://github.com/Halfwalker/Homey-Backups/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/Halfwalker/Homey-Backups/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Halfwalker/Homey-Backups/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Halfwalker/Homey-Backups/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Halfwalker/Homey-Backups/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Halfwalker/Homey-Backups/releases/tag/v0.1.0
