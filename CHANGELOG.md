# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- GitHub Actions CI workflow with local `act` runner support
- Matrix test strategy across Python 3.11 / 3.12 / 3.13
- Summary step to show pass/fail counts at the end of each CI run

### Fixed
- Declared `py-modules` in `pyproject.toml` and removed unused imports to fix lint errors

### Changed
- `.gitignore` updated to exclude `.tokensave/` cache directory

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
- `--force` flag on `backup.py` to overwrite existing backup directories
- JWT validation and path-length truncation in `backup.py`
- `--version` flag on all three scripts
- `pyproject.toml` with `entry_points` for `backup`, `restore`, and `svg` CLI commands
- `ruff` dev dependency + `pre-commit` configuration
- 53 unit tests for pure functions in the SVG renderer
- Critical integration tests for `backup.py` (`HomeyAPIError`, output directory assertions)

### Changed
- Output directory structure reorganised from `<category>/<TIMESTAMP>/` to
  `Backups/<TIMESTAMP>/<category>/` for a cleaner per-snapshot layout
- Auto-discovery in `homey_flow_svg.py` updated to match the new directory structure
- `restore.py` updated to discover backups under `Backups/<TIMESTAMP>/`
- `_backup_items()` helper extracted in `backup.py` to eliminate per-category boilerplate

[Unreleased]: https://github.com/deanouk/Homey-Backups/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/deanouk/Homey-Backups/releases/tag/v0.1.0
