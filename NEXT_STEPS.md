# NEXT_STEPS.md — Homey Backup Toolchain Roadmap

> **Last updated**: 2026-05-01
> **Scope**: `backup.py`, `restore.py`, `homey_flow_svg.py`

## Executive Summary

The Homey backup toolchain is **functional and complete** for its core mission: backup five
categories of Homey data, browse/restore them interactively, and render flow diagrams
as SVG/PNG. All three scripts work, all documentation is written, and the SVG renderer
handles both standard and advanced flows with full name resolution.

What's missing is **resilience** and **developer confidence**. The backup script can
hard-exit mid-run leaving orphaned directories. There are zero automated tests. The five
backup functions are 80% identical copy-paste. And the SVG renderer, while feature-rich
at 1527 lines, has a few edge cases that clip text or misposition ports.

This document organizes ~40 improvements into **nine categories**, from "fix today before
the next backup run" to "someday/maybe dreams." Each item includes a why, an effort
estimate, and cross-references to the original finding IDs from `oracle-review.txt` (B1–B8,
R1–R7, S1–S9) and `INTRO_TO_HOMEY_BACKUPS.md` (#1–#20).

**Time budget estimate**: All Critical + Quick Wins + Testing foundation ≈ 1 weekend.
Everything through Code Quality ≈ 2 weekends. The rest is incremental over time.

---

## Table of Contents

1. [Critical Fixes](#1--critical-fixes)
2. [Quick Wins](#2--quick-wins)
3. [Code Quality & Refactors](#3--code-quality--refactors)
4. [Testing & Reliability](#4--testing--reliability)
5. [UX Polish](#5--ux-polish)
6. [SVG Rendering](#6--svg-rendering)
7. [Automation & Scheduling](#7--automation--scheduling)
8. [New Features & Future Ideas](#8--new-features--future-ideas)
9. [Documentation Maintenance](#9--documentation-maintenance)

---

## 1. 🔴 Critical Fixes

*These can corrupt backup state or crash the tool. Fix before the next backup run.*

| # | Item | Finding | Effort | Why it matters |
|---|------|---------|--------|----------------|
| ✅ 1.1 | **`_get()` hard-exits on API error — no partial-run recovery** | B2 | Medium | Fixed: added `HomeyAPIError` exception; `_get()` raises instead of `sys.exit(1)`; each `backup_*` function catches it and records in `result.error_details`; backup continues to remaining categories. |
| ✅ 1.2 | **Module-level `NOW_STR` / `*_DIR` globals computed at import** | B3, #1 | Medium | Fixed: all six globals removed; backup functions now take `output_dir: Path`; `main()` computes timestamp and passes dirs to each function. Fully testable. |
| ✅ 1.3 | **No `try/except` around `render_flow()` in batch mode** | #2 | Quick | Already handled: cards with missing x/y/type are filtered before rendering; the CLI `main()` loop catches `JSONDecodeError`. Tests confirm both cases. |

### How to fix 1.1 — concrete pattern

```python
# New exception at module level
class HomeyAPIError(Exception):
    """Raised when a Homey API request fails (network, auth, HTTP error)."""

# In HomeyAPI._get() — replace every sys.exit(1) with:
raise HomeyAPIError(f"Cannot connect to Homey at {self.base_url}")

# In each backup_* function:
def backup_devices(api: HomeyAPI, output_dir: Path) -> BackupResult:
    result = BackupResult(category="Devices", output_dir=output_dir.resolve())
    try:
        devices = api.get_devices()
    except HomeyAPIError as exc:
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        return result
    # ... rest of function
```

---

## 2. 💡 Quick Wins

*Each ≤30 minutes. High bang-for-buck. Good warm-up tasks.*

| # | Item | Finding | Script | Why |
|---|------|---------|--------|-----|
| ✅ 2.1 | **Fix `_choose_category()` docstring** — missing `flow_folder` | R2 | restore.py | Fixed: docstring now lists all five return values including `'flow_folder'`. |
| ✅ 2.2 | **Log clipboard errors instead of swallowing** | R4 | restore.py | Fixed: `except Exception as exc` now logs `[DEBUG] Clipboard failed: {exc}` to stderr. |
| ✅ 2.3 | **Add `--version` flag to all three scripts** | #20 | all | Done: `__version__ = "0.1.0"` added to all three scripts; argparse `--version` wired in. `uv run python <script> --version` works on all three. |
| ✅ 2.4 | **Add comment explaining `_draw_wires` closure** | S3 | svg | Done: added two-line comment before `_draw_wires` explaining the closure captures `src_right`/`src_cy`. |
| ✅ 2.5 | **Harden `_build_variable_lookup` UUID extraction** | S9 | svg | Fixed: replaced all three occurrences of `rsplit("-", 5)[-5:]` with `_stem_uuid()` helper using `_UUID_RE = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")`. |
| ✅ 2.6 | **Platform-specific PNG install instructions** | #18 | svg | Done: error message now shows separate install commands for macOS (`brew install cairo`), Linux (`apt install libcairo2-dev`), and Windows (GTK3 runtime link). |
| ✅ 2.7 | **Sync `pyproject.toml` deps with inline script headers** | #12 | all | Done: added `# /// script` PEP 723 header to `homey_flow_svg.py` with `dependencies = []` and a note that `--png` needs `uv run --with cairosvg`. |

---

## 3. 🔧 Code Quality & Refactors

*Testability, DRY, structure. Medium effort, high long-term payoff.*

| # | Item | Finding | Effort | Description |
|---|------|---------|--------|-------------|
| 3.1 | **Extract generic `_backup_category()` function** | #4 | Medium | `backup_devices()`, `backup_flows()`, `backup_flow_folders()`, `backup_zones()`, and `backup_logic_variables()` are 80% identical. The per-category differences are: (a) API call, (b) filename template, (c) flow_type injection. Extract a shared `_backup_items(api_fn, output_dir, category_name, filename_fn)` that handles mkdir, iteration, JSON write, and error collection. |
| 3.2 | **`RunConfig` dataclass for runtime state** | B3 | Medium | Replaces five module-level `*_DIR` globals + `NOW_STR` with a single dataclass. Makes testing trivial (just instantiate with a temp dir), eliminates import-time side effects, and enables `--output-dir`. |
| 3.3 | **`HomeyAPIError` exception hierarchy** | B2 | Quick | Custom exception for API failures. Enables 1.1 above and makes error handling in tests clean. |
| 3.4 | **Type hints audit** | — | Medium | `_get()` claims `-> dict` but BLL endpoint can return `list`. `_parse_label` returns `str` but has code paths that could theoretically return `None` (they don't in practice, but the type checker doesn't know). Add `py.typed` marker. |
| 3.5 | **Split `homey_flow_svg.py` into modules** | — | Large | At 1527 lines, the SVG renderer does too much in one file. Logical split: `svg_builder.py` (SVGBuilder class), `token_resolution.py` (all `_resolve_*` + `_build_*_lookup` functions), `card_rendering.py` (card dims, badges, labels), `flow_renderer.py` (render_flow, render_standard_flow), `cli.py` (argparse + main). This makes each piece independently testable. |
| 3.6 | **`entry_points` in `pyproject.toml`** | — | Quick | Add `[project.scripts]` so `pip install -e .` creates `homey-backup`, `homey-restore`, `homey-flow-svg` CLI commands. |

### 3.1 — DRY pattern sketch

```python
def _backup_items(
    items: list[dict],
    output_dir: Path,
    category: str,
    filename_fn: Callable[[dict], str],
) -> BackupResult:
    """Generic backup loop: mkdir, iterate items, write JSON, collect errors."""
    result = BackupResult(category=category, output_dir=output_dir.resolve())
    if not items:
        result.note = "no data returned by API"
        return result
    output_dir.mkdir(parents=True, exist_ok=False)
    for item in items:
        filename = filename_fn(item)
        # ... write JSON, handle errors, update result ...
    return result
```

---

## 4. 🧪 Testing & Reliability

*Zero test coverage today. This is the single biggest risk to long-term maintainability.*

| # | Item | Effort | Description |
|---|------|--------|-------------|
| 4.1 | **Unit tests for `_dict_to_list()`** | Quick | Pure function, zero deps. Test: empty dict, normal dict, nested non-dict values, missing id injection. This is the easiest first test to write. |
| 4.2 | **Unit tests for token resolution** | Medium | `_resolve_placeholders()`, `_resolve_uri_refs()`, `_resolve_trigger_refs()` are all pure functions. Test with real token patterns from the codebase taxonomy (lines 204-216 of svg). |
| 4.3 | **Unit tests for `_parse_label()` card types** | Medium | Feed it synthetic card dicts for each branch: cron cards, BLL expressions, logic comparisons, zone triggers, device conditions, push notifications. This is where most of the SVG rendering bugs have lived. |
| 4.4 | **Unit tests for `_word_wrap()` and `_card_dims()`** | Quick | Test edge cases: empty string, string exactly at limit, single long word, multi-line overflow. These are the functions behind the text truncation bug. |
| 4.5 | **Integration test: backup round-trip** | Large | Mock `HomeyAPI._get()` to return fixture JSON. Run `backup_devices()` with a temp dir. Verify file count, filenames, and JSON structure. Requires 3.2 (RunConfig) to avoid import-time side effects. |
| 4.6 | **Integration test: SVG render pipeline** | Medium | Load a real flow JSON fixture, render to SVG string (not file), assert it contains expected card count, correct badge text, resolved variable names. Doesn't need pixel comparison — string assertions on SVG XML are sufficient. |
| 4.7 | **Test infrastructure: pytest + fixtures** | Quick | Add `tests/` directory, `conftest.py` with shared fixtures (sample flow JSON, mock API responses), and a `[project.optional-dependencies] dev = ["pytest"]` section in pyproject.toml. |
| 4.8 | **Pre-commit hooks** | Quick | `ruff check` + `ruff format` + `pytest` via pre-commit. Catches issues before they reach the repo. Add `.pre-commit-config.yaml`. |

### Suggested test priority order

```
4.7 → 4.1 → 4.4 → 4.2 → 4.3 → 4.8 → 4.6 → 4.5
 │      │      │      │                         │
 │      │      │      └── catches rendering bugs │
 │      │      └── catches truncation bugs       │
 │      └── easiest, builds confidence           │
 └── infrastructure first                  requires RunConfig (3.2)
```

---

## 5. 🎨 UX Polish

*CLI ergonomics and output readability. None are blockers, all improve daily use.*

| # | Item | Finding | Effort | Description |
|---|------|---------|--------|-------------|
| 5.1 | **`--dry-run` flag for backup.py** | B7, #5 | Medium | Show what would be backed up (category counts, target dirs) without writing. Useful before a big backup to verify API connectivity. |
| 5.2 | **`--output-dir` flag for backup.py** | #14 | Medium | Custom backup root instead of hardcoded `<category>/<timestamp>/`. Enables backing up to NAS, external drive, or CI artifact dir. Depends on 3.2 (RunConfig). |
| 5.3 | **`--force` flag for backup.py** | B7 | Quick | Override the "directory already exists" guard. Useful for re-running a failed backup within the same minute. |
| 5.4 | **Batch export mode for restore.py** | #8 | Medium | "Export all flows from date X to directory Y" — copies all JSONs at once instead of one-at-a-time interactive selection. For users with 50+ flows, the current UX is painful. |
| 5.5 | **JSON preview in restore.py** | #16 | Quick | Show a truncated preview (first 20 lines) before asking "copy to clipboard?" So users can verify they selected the right item. |
| 5.6 | **Filter by ID in restore.py** | #17 | Quick | Currently `_filter_items()` only searches `name`. Add `or q in i["id"].lower()` — one line. |
| 5.7 | **Flow import instructions: normal vs advanced** | #9 | Quick | Current instructions mention `POST /api/manager/flow/flow` but advanced flows use `/api/manager/flow/advancedflow`. Add a note distinguishing the two endpoints. |
| 5.8 | **`--filter` flag for SVG batch rendering** | #19 | Quick | `--filter "kitchen"` to render only flows whose name contains "kitchen". Saves time when re-rendering a subset. |
| 5.9 | **Homey API token format validation** | #6, #13 | Quick | Validate token looks like a JWT (3 dot-separated base64 segments) before making the first request. Fail fast with a clear message instead of a confusing 401 from the API. |
| 5.10 | **Summary table: truncate path from start, not end** | #15 | Quick | Long paths get `…/2026-04-27_19-48` truncated to `…/2026-04-2` — the useful part (the date) is cut. Reverse the truncation: `…ackups/devices/2026-04-27_19-48`. |

---

## 6. 🖼 SVG Rendering

*Known remaining visual issues. Prioritized by user visibility.*

| # | Item | Finding | Effort | Description |
|---|------|---------|--------|-------------|
| 6.1 | **`outputError` port clips on short cards** | #10, S3 | Quick | Error port dot hardcoded at `y + 52` (line 1190). On dynamically-sized cards shorter than ~56px, the port renders below the card boundary. **Fix**: clamp to `min(y + 52, y + ch - 4)`. Also adjust the wire y_offset at line 1049 to match. |
| 6.2 | **Disabled overlay should cover all card types** | #11 | Quick | Currently (line 1170) the disabled overlay `fill="#1E1E2E" opacity="0.5"` is applied only to trigger cards. A disabled flow should dim ALL cards — it's visually misleading to show actions as active when the flow is disabled. Move the overlay outside the `if ctype == "trigger"` check; apply after every standard card render if `not flow.get("enabled", True)`. |
| 6.3 | **Text truncation cuts final character** | SVG_tweaks | Quick | "Snow conditions log" renders as "Snow conditions lo" — the `text_multiline` truncation logic at line 153 (`lines[-1] = lines[-1][: max_chars - 1] + "…"`) is off by one when the text exactly fills the line. **Fix**: increase `max_chars` from 42 to 45 for standard cards (matching advanced card max_chars at line 1145), or adjust the truncation to `[:max_chars]` without the `-1`. |
| 6.4 | **Siren tune name resolution** | SVG_tweaks | Medium | `(0)` should resolve to "Doorbell Chime". Requires a static lookup table per device model. Lower priority — only affects a few card types. Could be a JSON data file `siren_tunes.json` keyed by device driver ID. |
| 6.5 | **Standard flow canvas width doesn't adapt to title** | — | Quick | Unlike `render_flow()` (which has the title-width fix at line 966), `render_standard_flow()` uses a fixed `SVG_W = 640`. Long flow names will overflow. Apply the same `canvas_w = max(SVG_W, title_w)` pattern. |
| 6.6 | **Standard flow disabled overlay missing** | — | Quick | `render_standard_flow()` renders the ENABLED/DISABLED badge but doesn't apply any visual overlay to the cards when disabled. Add the same dimming overlay from 6.2. |

---

## 7. ⏰ Automation & Scheduling

*The toolchain currently requires manual execution. These items move toward hands-free backups.*

| # | Item | Effort | Description |
|---|------|--------|-------------|
| 7.1 | **Cron-friendly exit codes and output** | Quick | `backup.py` currently prints pretty-formatted output. Add `--quiet` flag that suppresses per-file lines and only outputs the summary. Return exit code 0 on full success, 1 on partial failure, 2 on total failure. This makes cron/systemd integration clean. |
| 7.2 | **Systemd timer + service unit files** | Quick | Ship example `homey-backup.service` and `homey-backup.timer` in a `contrib/` directory. Daily backup at 3 AM, logging to journal. |
| 7.3 | **Backup retention / rotation** | Medium | Keep last N backups per category. `--retain 7` deletes timestamped dirs older than the 7th-newest. Without this, disk usage grows unbounded. |
| 7.4 | **Post-backup SVG render hook** | Medium | `--render-svg` flag on backup.py that auto-runs `homey_flow_svg.py` on the just-created flows directory. Produces visual diffs of flows alongside the raw JSON. |
| 7.5 | **Git auto-commit after backup** | Medium | `--git-commit` flag that stages new backup files and creates a commit with message `backup: YYYY-MM-DD HH:MM (N devices, M flows, ...)`. Combined with a remote, this gives versioned offsite backup for free. |
| 7.6 | **Health check endpoint / Healthchecks.io ping** | Quick | After a successful backup, ping a URL (e.g., Healthchecks.io, Uptime Kuma). `--ping-url <url>` flag. Enables alerting when backups stop running. |

---

## 8. 🚀 New Features & Future Ideas

*Beyond the current scope. Ordered roughly by value-to-effort ratio.*

| # | Item | Effort | Description |
|---|------|--------|-------------|
| 8.1 | **Backup diff / comparison tool** | Large | `diff.py 2026-04-20 2026-04-27` — show what changed between two backup dates. Semantic diff (new/removed/modified devices, flows, zones) rather than raw JSON diff. Killer feature for tracking unintended changes. |
| 8.2 | **Incremental backup** | Large | Only fetch and write items that changed since the last backup. Compare JSON hashes. Reduces API load and disk writes for frequent (hourly) backups. |
| 8.3 | **Direct REST restore** | Large | `restore.py --apply <file.json>` that POSTs/PUTs directly to the Homey API instead of just copying to clipboard. Dangerous but powerful — require `--confirm` flag. Would complete the backup→restore cycle programmatically. |
| 8.4 | **Flow dependency graph** | Medium | Analyze flow JSONs to find cross-flow references (flow actions that trigger other flows, shared variables). Output a DOT/SVG dependency graph showing which flows affect which. Useful for impact analysis before editing. |
| 8.5 | **App/driver inventory report** | Quick | Scan device backups, extract unique `driverUri` values, produce a table of installed apps + device counts. Useful for documenting the Homey setup. |
| 8.6 | **Export to Markdown / HTML report** | Medium | Generate a human-readable inventory document: all devices grouped by zone, all flows grouped by folder, all variables with current values. Like a "state of the Homey" snapshot. |
| 8.7 | **Homey firmware version tracking** | Quick | Call `GET /api/manager/system` at backup start, save firmware version to a `meta.json` in the backup dir. Enables correlating behavior changes with firmware updates. Partially addresses #13. |
| 8.8 | **Selective backup** | Quick | `--only devices,flows` to back up specific categories. Useful when you only care about flow changes and want to skip the 30-second device fetch. |
| 8.9 | **Advanced flow hydration guard** | Medium | B8 notes that `get_advanced_flows()` list endpoint might return compact data on some firmware versions. Add a runtime check: if any advanced flow's `cards` dict is empty, fall back to per-flow `get_advanced_flow(id)` hydration. Log when this happens so the behavior is visible. |

---

## 9. 📝 Documentation Maintenance

*The docs are comprehensive today. These items keep them accurate as the code evolves.*

| # | Item | Effort | Description |
|---|------|--------|-------------|
| 9.1 | **Keep RECOVERY.md in sync with restore.py** | Ongoing | If restore.py adds batch export or direct REST restore, RECOVERY.md procedures need updating. |
| 9.2 | **TECHDOCS.md — document token resolution taxonomy** | Quick | The code now has a great comment block (lines 204-216) documenting the three token formats. Mirror this in TECHDOCS.md for people who read docs before code. |
| 9.3 | **CHANGELOG.md** | Quick | Start tracking changes. Even a simple "## Unreleased" section helps. The toolchain is past v0.1 in functionality. |
| 9.4 | **Remove oracle-review.txt and SVG_tweaks.md from repo** | Quick | These are working documents that have been fully incorporated into this roadmap. Archive or delete to avoid confusion about what's current. |

---

## Where to Start

Here's the recommended attack plan, optimized for maximum safety improvement per hour:

### Weekend 1: Safety & Foundation

```
Morning:
  1.1  _get() → HomeyAPIError (Critical — prevents data loss)
  1.2  RunConfig dataclass (Critical — enables everything else)
  1.3  try/except in SVG batch mode (Critical — 5 min fix)
  2.1  Fix docstring (2 min)
  2.2  Log clipboard errors (2 min)
  2.5  Harden UUID extraction (5 min)

Afternoon:
  4.7  Set up pytest + fixtures
  4.1  Test _dict_to_list()
  4.4  Test _word_wrap() and _card_dims()
  4.2  Test token resolution functions
```

### Weekend 2: DRY & Polish

```
Morning:
  3.1  Extract _backup_items() generic function
  6.1  Fix outputError port clipping
  6.2  Fix disabled overlay for all cards
  6.3  Fix text truncation off-by-one

Afternoon:
  5.1  --dry-run flag
  5.2  --output-dir flag
  7.1  Cron-friendly exit codes
  4.8  Pre-commit hooks
```

### Ongoing (pick from the backlog):

- 5.4 Batch export for restore.py
- 7.3 Backup retention
- 7.5 Git auto-commit
- 8.1 Backup diff tool
- 4.5 Integration tests (once RunConfig exists)

### What NOT to prioritize

- **3.5 (Split SVG into modules)**: Don't do this until tests exist. Refactoring 1527 lines without tests is asking for regressions.
- **6.4 (Siren tune lookup)**: Niche, affects very few flows, requires maintaining a device-model-specific data file.
- **8.2 (Incremental backup)**: Premature optimization — full backups are fast over LAN and disk is cheap.
- **8.3 (Direct REST restore)**: High risk, low frequency need. The clipboard workflow is safe and sufficient.

---

*This roadmap is a living document. Cross off items as they're completed, add new findings as they emerge. The IDs (B2, S3, #14, etc.) link back to `oracle-review.txt` and `INTRO_TO_HOMEY_BACKUPS.md` for full context.*
