# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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

[Unreleased]: https://github.com/Halfwalker/Homey-Backups/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Halfwalker/Homey-Backups/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Halfwalker/Homey-Backups/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Halfwalker/Homey-Backups/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Halfwalker/Homey-Backups/releases/tag/v0.1.0
