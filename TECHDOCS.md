# Homey Backups — Technical Reference

> For end-user recovery instructions after a factory reset, see [RECOVERY.md](./RECOVERY.md).

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Homey Backups Toolchain                            │
└──────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐        HTTP (LAN)         ┌──────────────────────┐
│   backup.py     │ ──────────────────────→   │   Homey Pro          │
│  (uv inline)    │   GET /api/manager/...    │   (local REST API)   │
│                 │ ←──────────────────────   │                      │
│  deps:          │         JSON              └──────────────────────┘
│   - requests    │
│   - python-slug │
└────────┬────────┘
         │ writes JSON files
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Local Filesystem                             │
│                                                                  │
│  devices/YYYY-MM-DD_HH-MM/*.json                                 │
│  flow_folders/YYYY-MM-DD_HH-MM/*.json                            │
│  flows/YYYY-MM-DD_HH-MM/*.json                                   │
│  zones/YYYY-MM-DD_HH-MM/*.json                                   │
│  variables/YYYY-MM-DD_HH-MM/*.json                               │
└──────────┬────────────────────────────────────┬──────────────────┘
           │ reads JSON files                   │ reads JSON files
           ▼                                    ▼
┌─────────────────────┐              ┌─────────────────────────────┐
│   restore.py        │              │   homey_flow_svg.py         │
│  (uv inline)        │              │  (stdlib only, no uv hdr)   │
│                     │              │                             │
│  deps:              │              │  optional dep:              │
│   - inquirer        │              │   - cairosvg (for --png)    │
│   - pyperclip       │              │                             │
│                     │              │  outputs:                   │
│  ZERO network calls │              │   - *.svg (default)         │
│  clipboard + TUI    │              │   - *.png (with --png flag) │
└─────────────────────┘              └─────────────────────────────┘
```

**Network boundary**: Only `backup.py` touches the network. Both `restore.py` and `homey_flow_svg.py` are purely offline tools.

---

## backup.py

### Purpose

Connects to a Homey Pro via its local REST API, fetches all devices, flows (normal + advanced), zones, and logic variables (Homey Logic + BLL), and persists each item as an individual JSON file in timestamped directories.

### uv inline script header

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
#   "python-slugify",
# ]
# ///
```

Dependencies:
- `requests` — HTTP client for Homey REST API
- `python-slugify` — filename-safe slug generation from item names

### HomeyAPI class

```python
class HomeyAPI:
    def __init__(self, base_url: str, token: str, timeout: int = 30) -> None
```

All methods use Bearer token auth via `requests.Session`. Base path: `{base_url}/api`.

| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_devices()` | `GET /api/manager/devices/device` | `list[dict]` (flat, id injected) |
| `get_flows()` | `GET /api/manager/flow/flow` | `list[dict]` (normal flows) |
| `get_advanced_flows()` | `GET /api/manager/flow/advancedflow` | `list[dict]` (compact, no cards) |
| `get_advanced_flow(flow_id)` | `GET /api/manager/flow/advancedflow/{id}` | `dict | None` (full card DAG) |
| `get_flow_folders()` | `GET /api/manager/flow/flowfolder` | `list[dict]` (flat, id injected) |

> **⚠️ API response accuracy note:** TECHDOCS describes `get_advanced_flows()` (the list endpoint) as returning "compact, no cards." However, actual backup files on disk contain full `cards` dicts, and `backup_flows()` only calls `get_advanced_flows()` — never `get_advanced_flow()`. This suggests the list endpoint may return full card DAGs on current Homey Pro firmware, making the per-flow fetch redundant. This behaviour should be verified against the target firmware version. `get_advanced_flow()` is retained as a fallback for firmware versions that do return compact data from the list endpoint.
| `get_zones()` | `GET /api/manager/zones/zone` | `list[dict]` (flat) |
| `get_logic_variables()` | `GET /api/manager/logic/variable` | `list[dict]` (Homey Logic vars) |
| `get_bll_variables()` | `GET /api/app/net.i-dev.betterlogic/ALL` | `list[dict]` (BLL vars, empty if app absent) |

Internal helper:
- `_get(path)` — appends `/api{path}` to base URL, exits process on connection/timeout/HTTP errors
- `_dict_to_list(data)` — converts Homey's `{id: {...}}` response format to a flat list with `id` injected into each dict

### Backup categories

| Category | API Path(s) | Output Folder | File Naming |
|----------|-------------|---------------|-------------|
| Devices | `/api/manager/devices/device` | `devices/YYYY-MM-DD_HH-MM/` | `<slug>-<id>.json` |
| Flows | `/api/manager/flow/flow` + `/api/manager/flow/advancedflow` | `flows/YYYY-MM-DD_HH-MM/` | `<slug>-<id>.json` |
| Flow Folders | `/api/manager/flow/flowfolder` | `flow_folders/YYYY-MM-DD_HH-MM/` | `<slug>-<id>.json` |
| Zones | `/api/manager/zones/zone` | `zones/YYYY-MM-DD_HH-MM/` | `<slug>-<id>.json` |
| Variables | `/api/manager/logic/variable` + `/api/app/net.i-dev.betterlogic/ALL` | `variables/YYYY-MM-DD_HH-MM/` | Logic: `<slug>-<id>.json`, BLL: `bll-<name-slug>.json` |

Each category function returns a `BackupResult` dataclass:
```python
@dataclass
class BackupResult:
    category: str
    saved: int = 0
    skipped: int = 0
    errors: int = 0
    output_dir: Optional[pathlib.Path] = None
    note: str = ""
    error_details: list[str] = field(default_factory=list)
```

### Error handling & exit codes

- Missing env vars (`HOMEY_API_URL`, `HOMEY_API_TOKEN`) → `sys.exit(1)` with message
- Connection error / timeout / non-200 response → `sys.exit(1)` immediately
- Backup directory already exists → `sys.exit(1)` (prevents accidental overwrite)
- Individual file write failure → logged to `BackupResult.error_details`, script continues
- Items without an ID → skipped with warning

### Referential integrity (important for restore)

Backed-up JSON files contain hard UUID references to other Homey resources. These references break when resources are restored with new UUIDs (which always happens for devices after a factory reset + re-pair).

| Reference type | Example field | Risk on restore |
|---|---|---|
| Device UUID in flow card | `ownerUri: "homey:device:<uuid>"` | Breaks if device is re-paired (new UUID assigned) |
| Zone UUID in flow card ID | `"homey:zone:<uuid>:capability"` | Breaks if zone is re-created with a different UUID |
| Cross-flow reference | `args.flow.id` in `homey:manager:flow:programmatic_trigger` action | Breaks if target flow receives a new ID on import |
| Variable UUID | `droptoken: "homey:manager:logic|<uuid>"` | Breaks if variable is re-created (new UUID) |
| Folder UUID | `folder: "<uuid>"` in flow JSON | Resolvable — restore flow folders first and remap old→new UUIDs before importing flows |

After a factory reset + device re-pair, flows referencing old device UUIDs will appear as **broken** (red indicator) in the Homey flow editor. They must be manually updated to point to the newly paired devices. See [RECOVERY.md](./RECOVERY.md) for the full UUID reconciliation workflow.

### Known code issues

| Issue | Location | Impact |
|---|---|---|
| `_prompt_overwrite()` is never called | `backup.py:64–94` | The function exists and prompts the user before overwriting, but all four category backup functions bypass it and call `sys.exit(1)` directly on directory collision. It is dead code — either wire it into each backup function or remove it. |

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HOMEY_API_URL` | Yes | Base URL of Homey Pro (e.g. `http://192.168.1.100`) |
| `HOMEY_API_TOKEN` | Yes | Personal Access Token from the Homey mobile app |

### Interpreting backup summary output

| Summary field | Non-zero means |
|---|---|
| `Saved` | Items successfully written to disk |
| `Skipped` | Items without an ID field (logged as warnings in console) |
| `Errors` | File write failures — check console for `[ERROR]` lines |

Common errors and fixes:

| Error / symptom | Cause | Fix |
|---|---|---|
| `HTTP 401` | Token expired or wrong | Generate a new PAT in the Homey app |
| `HTTP 404` on BLL endpoint | Better Logic Library app not installed | Expected — BLL backup will report `0 saved`, which is fine |
| `Cannot connect` / timeout | Wrong IP or machine not on the same LAN | Verify `HOMEY_API_URL`; check both devices are on the same subnet |
| `Backup directory already exists` | Script ran twice in the same minute | Delete the directory or wait one minute |
| Category shows `0 saved` | Token lacks permission for that category | Re-generate token and grant all permissions |

---

## restore.py

### Purpose

Interactive terminal-based browser for local backup files. Allows the user to select a backed-up item, view its JSON, copy it to the clipboard, and get instructions for re-importing it into Homey.

### uv inline script header

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "inquirer",
#   "pyperclip",
# ]
# ///
```

Dependencies:
- `inquirer` — interactive terminal prompts (list selection, text input)
- `pyperclip` — cross-platform clipboard copy (optional — gracefully degrades)

### Interactive menu flow

1. **Banner** — ASCII art header displayed once
2. **Choose category** — `inquirer.List` with choices: Device, Flow, Flow Folder, Zone, Variable
3. **Select backup date** — lists all timestamped subdirectories under the category folder, user picks one
4. **Filter by name** — optional text filter (case-insensitive substring match)
5. **Select item** — scrollable list showing `name (id: uuid)`, or "← Back" to restart
6. **Present item** — shows file path, offers clipboard copy of formatted JSON
7. **Import instructions** — prints category-specific re-import guidance
8. **Loop** — asks "Restore another item" or "Exit"

`Ctrl+C` at any prompt → clean exit with "Bye! 👋".

### Re-import instructions per category

| Category | Method |
|----------|--------|
| Device | Re-pair physical device, then `PUT /api/manager/devices/device/<id>` to restore settings |
| Flow | Web App import (paste JSON) or `POST /api/manager/flow/flow`; strip `id` and `folder` from body on create |
| Flow Folder | `POST /api/manager/flow/flowfolder` (create) or `PUT /api/manager/flow/flowfolder/<id>` (update); parent folders first; build old→new UUID mapping before importing flows |
| Zone | `POST /api/manager/zones/zone` (create) or `PUT /api/manager/zones/zone/<id>` (update); parent zones first |
| Variable | Logic: `POST` or `PUT /api/manager/logic/variable/<id>`; BLL: via app settings or `PUT /api/app/net.i-dev.betterlogic/variable/<name>` |

### Field guidance for API writes

When POSTing or PUTting backed-up JSON to the Homey API, some fields are managed by Homey and should be stripped from the request body.

| Category | Include in body | Strip or ignore |
|---|---|---|
| Flow (normal) | `name`, `enabled`, `trigger`, `conditions`, `actions` | `id` (assigned by Homey on create), `folder` (remap to new folder ID first), `flow_type` (toolchain field) |
| Flow (advanced) | `name`, `enabled`, `cards`, `triggerable` | `id`, `folder` (remap first), `flow_type` |
| Flow Folder | `name`, `parent` (use new parent UUID if nested) | `id` |
| Zone | `name`, `parent`, `icon`, `active` | `id` |
| Variable (Logic) | `name`, `type`, `value` | `id`, `source` (toolchain field), `uri` |
| Variable (BLL) | `value` (PUT by name) | All other fields — BLL variables are set by name via `PUT .../variable/<name>` |

> **Note:** When using `PUT /api/.../<id>` (update by ID), supply the `id` in the URL path, not in the body. The `id` field in the JSON body is typically ignored on PUT.

### No network calls — local only

`restore.py` reads exclusively from the local filesystem. It does not import `requests` or make any HTTP calls. All data comes from the `*.json` files written by `backup.py`.

### Design constraints (intentional)

`restore.py` deliberately does **not**:
- Make any HTTP calls to Homey
- POST or PUT data automatically
- Rewrite UUID references in JSON
- Perform dependency-ordered restores
- Validate that a backup is complete before displaying it

These constraints are intentional: the tool is a safe, offline browser. Recovery remains a guided manual process, giving the user full control over UUID remapping and restore ordering.

---

## homey_flow_svg.py

### Purpose

Renders Homey flow JSON backups — both **standard flows** and **advanced flows** — as SVG diagrams that replicate Homey's dark-themed visual editor. Zero required external dependencies (stdlib only). Optional `cairosvg` dependency enables PNG export.

### Entry point & CLI flags

```python
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render Homey Advanced Flow JSON files as SVG diagrams",
        ...
    )
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `inputs` | positional, nargs="+" | (required) | Homey flow JSON file(s) |
| `-o`, `--output` | str | None | Output SVG/PNG path (single-file mode only) |
| `-d`, `--output-dir` | str | None | Output directory for batch processing |
| `--devices-dir` | str | auto-discovered | Directory of device backup JSONs for name resolution |
| `--zones-dir` | str | auto-discovered | Directory of zone backup JSONs for name resolution |
| `--variables-dir` | str | auto-discovered | Directory of variable backup JSONs for token resolution |
| `--png` | flag | False | Convert output to PNG (requires `cairosvg` + `libcairo2`) |

### Name resolution

The renderer resolves UUIDs to human-readable names using sibling backup directories. Auto-discovery logic:

1. Extract the timestamp from the flow file's parent directory (e.g. `flows/2026-04-23_11-13/` → `"2026-04-23_11-13"`)
2. Look for matching sibling directories:
   - `{script_dir}/devices/{timestamp}/` → device lookup
   - `{script_dir}/zones/{timestamp}/` → zone lookup
   - `{flow_parent}/../variables/{timestamp}/` → variable lookup
3. If found, scan all `*.json` files in each directory and build lookup dicts:
   - `_build_device_lookup(dir)` → `{uuid: name, "homey:device:uuid": name}`
   - `_build_zone_lookup(dir)` → `{uuid: name, "homey:zone:uuid": name}`
   - `_build_variable_lookup(dir)` → `{uuid: name}` (both Logic and BLL vars)
   - `_build_cap_titles(dir)` → `{device_uuid: {cap_id: (title, unit)}}`

If auto-discovery fails, a warning is printed to stderr listing which directories were not found and what will remain unresolved.

### Standard flow rendering (`render_standard_flow`)

```python
def render_standard_flow(
    flow: dict,
    output_path: str,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
    to_png: bool = False,
) -> None:
```

Renders a standard (non-advanced) Homey flow as a **2-column vertical layout**:

- Fixed width: 640px
- Three sections: "When" (trigger), "And conditions", "Then actions"
- Left column: section label in a rounded box
- Right column: cards rendered vertically with accent bar, badge, and multiline label
- Each card's height is dynamic based on label text wrapping
- Title bar at top with flow name + ENABLED/DISABLED badge
- Inverted conditions get a "NOT" prefix on their badge

Entry: `render_flow()` auto-detects whether a flow is standard (has `trigger`/`conditions`/`actions` but no `cards`) and delegates to `render_standard_flow`.

### Advanced flow rendering (`render_flow`)

```python
def render_flow(
    flow: dict,
    output_path: str,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
    to_png: bool = False,
) -> None:
```

**Two-pass rendering algorithm:**

1. **Pass 1 — Connections (wires)**: Iterates all cards, draws cubic Bézier S-curves between output ports and target cards' left edge. Drawn first so wires appear behind cards.
2. **Pass 2 — Cards**: Renders each card based on type (gate, start, delay, note, or standard trigger/condition/action).

**Layout**: Uses the `x`, `y` coordinates stored in the flow JSON (Homey's editor positions). The renderer:
- Computes bounding box across all cards
- Translates so top-left is at `PADDING` (80px)
- Adds `TITLE_H` (50px) for the title bar above

**Port positions** (output side, right edge of card):
- `outputSuccess`: vertical center (`y + h/2`)
- `outputTrue`: `y + 20` for conditions, center for others
- `outputFalse`: `y + 36` for conditions, center for others
- `outputError`: `y + 52` (always)

Input port: left side, vertical center (subtle dot marker).

### Card types

| Type | Dimensions (W×H) | Fill | Stroke | Accent | Ports |
|------|------------------|------|--------|--------|-------|
| `trigger` | 340×72 (dynamic) | `#162B1F` | `#27AE60` | `#2ECC71` | out: success/true/false/error |
| `condition` | 340×72 (dynamic) | `#162232` | `#2980B9` | `#3498DB` | out: true/false/error |
| `action` | 340×72 (dynamic) | `#321E16` | `#D35400` | `#E67E22` | out: success |
| `any` (OR gate) | 79×52 | `#32291A` | `#E67E22` | `#F39C12` | out: success |
| `all` (AND gate) | 79×52 | `#1A2432` | `#2980B9` | `#3498DB` | out: success |
| `start` | 79×52 | `#162B1F` | `#27AE60` | `#2ECC71` | out: success |
| `delay` | 220×64 (dynamic) | `#24163A` | `#8E44AD` | `#9B59B6` | out: success |
| `note` | 320×dynamic | `#FFF9C4`* | `#F9A82520` | `#F9A825` | none |

*Note fill varies by color attribute: yellow `#FFF9C4`, red `#FFCDD2`, green `#C8E6C9`, blue `#BBDEFB`, purple `#E1BEE7`, grey/gray `#CFD8DC`.

Height is computed dynamically by `_card_dims()` based on label text wrapping.

### Connection wire colors

| Output Type | Hex Color | Visual | Meaning |
|-------------|-----------|--------|---------|
| `outputSuccess` | `#3498DB` | Blue | Successful completion |
| `outputTrue` | `#2ECC71` | Green | Condition evaluated true |
| `outputFalse` | `#f59e0b` | Amber/Yellow | Condition evaluated false |
| `outputError` | `#F39C12` | Amber/Orange | Card execution error |

Wires are rendered as cubic Bézier curves (`_bezier()`) with `stroke-width="2.5"`, `opacity="0.7"`, and `stroke-linecap="round"`.

### Label parsing (`_parse_label`)

```python
def _parse_label(
    card: dict,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> str:
```

**Token resolution pipeline:**

1. **Special types** handled first:
   - `note` → returns `card.value`
   - `start` → returns `"Start"`
   - `delay` → parses `args.delay.number` + `args.delay.multiplier` → `"Delay 5 min"`
   - `any`/`all` → returns `"OR"` / `"AND"`

2. **Rich format** (advanced flows with nested `card` object):
   - Uses `card.card.titleFormatted` or `card.card.title`
   - Resolves `[[key]]` placeholders via `_resolve_placeholders(text, args)`
   - Resolves URI refs via `_resolve_uri_refs(text, var_lookup)`
   - Prepends device name from `card.card.ownerUri` via device_lookup

3. **Compact format fallback** (standard flows or flows without nested card):
   - `droptoken` resolution for variable-testing conditions
   - Cron card special labels (sunset, sunrise, time_exactly, etc.)
   - Logic comparison conditions (`<`, `>`, `≥`, `≤`, `=`, `≠`, `between`)
   - Zone triggers (homey:zone:uuid:capability)
   - Aqara FP2 presence triggers (motion_new_true/false, motion_inactive_new)
   - BLL `variable_contains` condition
   - BLL `execute_bl_expression` action
   - Notification/Timeline action
   - Mobile push notification action (text + image variants)
   - Logic `variable_set` action
   - Final fallback: capitalize capability from card ID + prepend device name

**URI ref resolution** (`_resolve_uri_refs`):
- `[[homey:manager:logic|<uuid>]]` → variable name from var_lookup, or `var:<uuid[:8]>`
- `[[homey:app:net.i-dev.betterlogic|<name>]]` → `BLL(<name>)`
- `[[homey:manager:cron|<ref>]]` → human label (Current date, Current time, Sun state)
- `[[homey:device:<uuid>|<cap_id>]]` → `*<Cap Title>` (capability title)

**Trigger ref resolution** (`_resolve_trigger_refs`):
- `[[trigger::<card_id>::<field>]]` → looks up card_id in trigger_cap_map for `"*Title (unit)"`, else trigger_name_map for `"entity:field"`, else `"[uuid[:8]:field]"`

### Badge system

`_card_badge(card)` returns a badge string based on card type and card ID patterns:

**Trigger badges:**
| Pattern in card ID | Badge |
|-------------------|-------|
| `homey:zone:` | `ZONE TRIGGER` |
| `homey:device:` | `DEVICE TRIGGER` |
| `flowbits` | `FLOWBITS TRIGGER` |
| `homey:manager:cron:` | `CRON TRIGGER` |
| `homey:manager:presence:` | `PRESENCE TRIGGER` |
| `homey:manager:logic:` | `LOGIC TRIGGER` |
| `homey:manager:system:` | `SYSTEM TRIGGER` |
| `net.i-dev.betterlogic` | `BLL TRIGGER` |
| (default) | `TRIGGER` |

**Condition badges:**
| Pattern | Badge |
|---------|-------|
| `net.i-dev.betterlogic` | `BLL CONDITION` |
| `homey:manager:logic:` | `LOGIC CONDITION` |
| `homey:device:` | `DEVICE CONDITION` |
| `flowbits` | `FLOWBITS CONDITION` |
| `homey:manager:cron:` | `CRON CONDITION` |
| `homey:manager:presence:` | `PRESENCE CONDITION` |
| `homey:manager:mobile:` | `MOBILE CONDITION` |
| (default) | `CONDITION` |

**Action badges:**
| Pattern | Badge |
|---------|-------|
| `net.i-dev.betterlogic` | `BLL ACTION` |
| `homey:manager:notifications` | `TIMELINE` |
| `homey:manager:mobile` | `MOBILE ACTION` |
| `homey:manager:logic` | `LOGIC ACTION` |
| `homey:device:` | `DEVICE ACTION` |
| `homey:zone:` | `ZONE ACTION` |
| `homey:manager:flow:` | `FLOW ACTION` |
| `homey:manager:presence:` | `PRESENCE ACTION` |
| `com.basmilius.flowbits` | `FLOWBITS ACTION` |
| `com.ubnt.unifiprotect` | `CAMERA ACTION` |
| `ady.enhanced_device_widget` | `WIDGET ACTION` |
| (default) | `ACTION` |

Standard flow renderer also supports `NOT` prefix for inverted conditions.

### `_render_advanced_flow_cards` vs `render_flow`

There is no separate `_render_advanced_flow_cards` function. The relationship is:

- **`render_flow()`** is the universal entry point. It inspects the flow JSON:
  - If `flow["cards"]` exists and is non-empty → renders as an advanced flow (two-pass: wires then cards)
  - If no `cards` but `flow["trigger"]`, `flow["conditions"]`, or `flow["actions"]` exist → delegates to `render_standard_flow()`
  - Otherwise → prints warning and skips

- **`render_standard_flow()`** handles the linear When/And/Then layout for standard flows.

### PNG export

```python
try:
    import cairosvg as _cairosvg
except ImportError:
    _cairosvg = None
```

- `--png` flag triggers PNG conversion via `_write_output()`
- If `cairosvg` is not installed, raises `SystemExit` with install instructions
- Requires system library `libcairo2` (`sudo apt install libcairo2`)
- PNG path: same as SVG path but with `.png` extension
- Conversion: `cairosvg.svg2png(bytestring=svg_str.encode(), write_to=str(png_path))`

### Known limitations / edge cases

- Card label text is truncated at 240 characters with `"…"` appended
- Multiline text wraps at configurable max_chars (42-45 chars depending on context), max 5-6 lines
- Note card height is dynamic but capped by max_lines=6
- Device/zone/variable lookup requires a matching timestamp directory — if backup timestamps differ, auto-discovery fails
- BLL variables referenced by name (not UUID) may not resolve if the BLL app response format varies
- `outputError` port is always positioned at `y + 52` regardless of card height — may clip on very short cards
- Disabled flows: only trigger cards get a "disabled overlay" (semi-transparent rectangle), other cards remain fully visible
- The `_word_wrap` function replaces newlines with spaces before wrapping

---

## Data Formats

### Flow JSON structure (advanced)

```json
{
  "id": "uuid",
  "name": "Flow Name",
  "enabled": true,
  "folder": "folder-uuid-or-null",
  "triggerable": true,
  "cards": {
    "card-uuid-1": {
      "type": "trigger|condition|action|any|all|start|delay|note",
      "id": "homey:device:uuid:capability",
      "x": 100,
      "y": 200,
      "card": {
        "titleFormatted": "When [[device]] changes",
        "title": "When device changes",
        "args": {"key": "value"},
        "ownerUri": "homey:device:uuid"
      },
      "args": {"delay": {"number": 5, "multiplier": 60}},
      "outputSuccess": ["target-card-uuid"],
      "outputTrue": ["target-card-uuid"],
      "outputFalse": ["target-card-uuid"],
      "outputError": ["target-card-uuid"],
      "droptoken": "homey:manager:logic|uuid",
      "ownerUri": "homey:device:uuid",
      "value": "Note text (for note type)",
      "color": "yellow (for note type)"
    }
  }
}
```

> `folder`: UUID of the flow folder this flow belongs to, or `null` if in the root. Flow folder backup **is implemented** — folders are saved to `flow_folders/YYYY-MM-DD_HH-MM/`. However, after a factory reset, folders are re-created with new UUIDs. Build an old→new UUID mapping (see [RECOVERY.md](./RECOVERY.md) Step 6) and update this field in each flow's JSON before importing, or strip it entirely and organise flows manually afterward in the web app.
>
> `triggerable`: When `true`, this advanced flow can be triggered programmatically by other flows via the `homey:manager:flow:programmatic_trigger` action. Important when restoring cross-flow dependencies — if the target flow's UUID changes on import, any flow calling it will be broken.

### Flow JSON structure (standard)

```json
{
  "id": "uuid",
  "name": "Flow Name",
  "enabled": true,
  "folder": "folder-uuid-or-null",
  "flow_type": "normal",
  "trigger": {
    "id": "homey:device:uuid:capability",
    "args": {},
    "ownerUri": "homey:device:uuid"
  },
  "conditions": [
    {
      "id": "homey:manager:logic:equal_boolean",
      "args": {},
      "inverted": false,
      "droptoken": "homey:manager:logic|uuid"
    }
  ],
  "actions": [
    {
      "id": "homey:manager:notifications:create_notification",
      "args": {"text": "Hello [[trigger::card_id::field]]"}
    }
  ]
}
```

### Device JSON (name resolution fields used)

```json
{
  "id": "device-uuid",
  "name": "Living Room Sensor",
  "capabilitiesObj": {
    "measure_temperature": {
      "title": "Temperature",
      "units": "°C"
    },
    "alarm_motion": {
      "title": "Motion",
      "units": ""
    }
  }
}
```

Fields consumed by renderer:
- `id` / `_id` — used as lookup key
- `name` / `title` — human-readable device name
- `capabilitiesObj.{cap_id}.title` — capability display title
- `capabilitiesObj.{cap_id}.units` — measurement unit string

### Zone JSON (name resolution fields used)

```json
{
  "id": "zone-uuid",
  "name": "Living Room"
}
```

Fields consumed: `id`/`_id`, `name`/`title`

### Variable JSON (name resolution fields used)

```json
{
  "id": "variable-uuid",
  "name": "Morning Mode",
  "type": "boolean",
  "value": true,
  "source": "logic"
}
```

Fields consumed: `id`/`_id`, `name`/`title`

---

## Adding New Card Types

1. Add dimensions to `CARD_DIMS`:
   ```python
   CARD_DIMS["mytype"] = (width, height)
   ```

2. Add style to `STYLES`:
   ```python
   STYLES["mytype"] = {"fill": "#hex", "stroke": "#hex", "accent": "#hex"}
   ```

3. Handle in `_parse_label()`:
   ```python
   if ctype == "mytype":
       return "My Label"
   ```

4. Handle rendering in `render_flow()` — inside the **Pass 2 card drawing** section, locate the `elif ctype == "trigger":` block and add a sibling `elif` block:
   ```python
   elif ctype == "mytype":
       x0, y0 = cx + tx, cy + ty
       w, h = _card_dims(card)
       style = STYLES.get("mytype", STYLES["action"])
       _draw_card(svg, x0, y0, w, h, label, badge, style)
   ```
   If your card type has output ports, also add it to `_out_ports()` so Pass 1 wire-drawing knows where to attach connection lines.

5. Optionally handle in `_card_dims()` for dynamic sizing.

---

## Adding New Token Resolvers

Token resolution happens in three functions:

1. **`_resolve_placeholders(text, args)`** — replaces `[[key]]` with values from the card's args dict. To add new arg patterns, modify the `_sub` inner function.

2. **`_resolve_uri_refs(text, var_lookup)`** — replaces `[[scheme|ref]]` patterns. Add new `if scheme == "homey:manager:newmanager":` blocks inside the `_sub` inner function.

3. **`_resolve_trigger_refs(text, trigger_name_map, trigger_cap_map)`** — replaces `[[trigger::card_id::field]]` patterns. The maps are built by `_build_trigger_name_map()`.

To add a new URI scheme:
```python
# In _resolve_uri_refs, add before the final `return full`:
if scheme == "homey:manager:mynewmanager":
    return f"MyManager({ref})"
```

**Verifying your resolver:**
```bash
# Render a flow that uses cards with the new URI scheme
python homey_flow_svg.py flows/TIMESTAMP/your-flow.json -o /tmp/test.svg
# The raw placeholder should no longer appear in the output
grep "mynewmanager" /tmp/test.svg  # expect no output
```

---

## Testing

### Batch render command (visual regression testing)

```bash
# Render all flows from a backup run
python homey_flow_svg.py flows/2026-04-26_14-05/*.json -d test-output/

# Render with PNG output for quick visual inspection
python homey_flow_svg.py flows/2026-04-26_14-05/*.json -d test-output/ --png
```

### What to check visually

- **Labels**: Are device/zone/variable names resolved (no raw UUIDs)?
- **Wires**: Do connections route correctly between cards?
- **Layout**: Do cards overlap? Are notes readable?
- **Badges**: Do card badges match the expected type?
- **Colors**: Are wire colors correct (blue=success, green=true, amber=false)?
- **Standard flows**: Do they render as vertical 2-column layout?
- **Disabled flows**: Does the trigger card show a disabled overlay?
- **Port positions**: Are T/F/E dots on the correct vertical offsets?

### Smoke test (no external deps)

```bash
# Should render without errors, producing .svg files
python homey_flow_svg.py flows/2026-04-26_14-05/some-flow.json
echo $?  # expect 0
```

### Testing restore.py

```bash
# Runs interactively — verify menu navigation, filter, clipboard
uv run restore.py
```

### Testing backup.py

```bash
# Requires live Homey on LAN
HOMEY_API_URL=http://192.168.x.x HOMEY_API_TOKEN=xxx uv run backup.py
# Verify: timestamped dirs created, JSON files valid, summary table prints
```
