# Homey Backup & Restore Tools

A set of Python scripts to **back up**, **restore**, and **visualise** devices, flows, zones, and variables from a Homey Pro instance via its local REST API. No cloud, no MCP, no add-ons required.

> 🚨 **Recovering after a factory reset?**
> `restore.py` is a **read-only local browser** — it does not write anything to Homey. You must manually re-import via the Homey web app or REST API, then fix UUID references to devices, zones, folders, and other flows. **Steps must be done in a specific order or flows will be broken on import.**
>
> → **Start with [RECOVERY.md](./RECOVERY.md) and follow the steps in order.**

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended runner)
  - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux)
  - Windows: see [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/)
- A **Homey Pro reachable on your local network** — you'll need its local IP address:
  1. Open the Homey app → **More** → **Settings** → **General**
  2. The IP is listed under **Network** (e.g. `192.168.1.100`)
  3. Alternatively: check your router's DHCP lease table for a device named "Homey"

  > **Tip:** Assign Homey a static IP or DHCP reservation so the address never changes between backup runs.
- A **Personal Access Token** from the Homey mobile app:
  1. Open the Homey app → tap **More** (bottom right)
  2. Tap **Users & Permissions**
  3. Tap **Add Personal Access Token**
  4. Give it a name (e.g. `Backup Script`) and grant all permissions
  5. **Copy the token immediately** — it is only shown once; you cannot retrieve it later
  6. Store it in a password manager

  The token looks like: `atk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

## Recovery After a Factory Reset

If you are restoring a Homey Pro after a factory reset, see **[RECOVERY.md](RECOVERY.md)** for the complete step-by-step playbook — including restore order, UUID mapping, and known limitations.

---

## Quick Start

`backup.py` and `restore.py` are self-contained [uv inline scripts](https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies) — no venv setup needed. `render_flows.py` uses a uv inline script header that auto-installs `cairosvg` when using `--png`; for SVG-only output no extra dependencies are needed:

```bash
# Back up everything
HOMEY_API_URL=http://192.168.x.x HOMEY_API_TOKEN=your-token uv run backup.py

# Browse backups interactively and prepare re-imports
uv run restore.py

# Render a flow as SVG — primary invocation:
uv run render_flows.py Backups/2026-04-26_14-05/flows/my-flow-uuid.json
# or batch-render a whole backup run:
uv run render_flows.py Backups/2026-04-26_14-05/flows/*.json -d flow-rendering/
# or via the package:
python -m render_flows Backups/2026-04-26_14-05/flows/*.json -d flow-rendering/
```

Or, if you prefer a shared virtual environment (useful if you want IDE autocomplete or a persistent install):

```bash
uv sync          # creates .venv and installs all dependencies
uv run backup.py # run within the project venv
```

> Note: only `backup.py` and `restore.py` require dependencies via uv. `render_flows.py` (`uv run render_flows.py` or `python -m render_flows`) has a uv header that auto-installs `cairosvg` for `--png` mode; for SVG-only output it can be run directly with `python` without uv.

---

## Environment Variables

| Variable | Required for | Example |
|---|---|---|
| `HOMEY_API_URL` | `backup.py` | `http://192.168.1.100` |
| `HOMEY_API_TOKEN` | `backup.py` | `atk_abc123...` |

---

## Persistent Setup (optional)

To avoid typing env vars each run, create a `.env` file in this directory:

```
HOMEY_API_URL=http://192.168.1.100
HOMEY_API_TOKEN=atk_your_token_here
```

Then source it before running:

```bash
set -a && source .env && set +a
uv run backup.py
```

Or add the exports to your shell profile (`~/.zshrc`, `~/.bashrc`) for permanent access.

---

## Scripts

### `backup.py` — Back Up Your Homey

Connects directly to the Homey Pro local REST API, fetches devices, flows, zones, logic variables, installed apps, dashboards, light scenes, and system info, and saves each item as an individual JSON file.

#### What it backs up

| Category | API endpoint | Output folder |
|---|---|---|
| Devices | `/api/manager/devices/device` | `Backups/TIMESTAMP/devices/` |
| Flows | `/api/manager/flow/flow` + `/advancedflow` | `Backups/TIMESTAMP/flows/` |
| Flow Folders | `/api/manager/flow/flowfolder` | `Backups/TIMESTAMP/flow_folders/` |
| Zones | `/api/manager/zones/zone` | `Backups/TIMESTAMP/zones/` |
| Variables | `/api/manager/logic/variable` + BLL app | `Backups/TIMESTAMP/variables/` |
| Apps | `/api/manager/apps/app` + per-app `/settings` | `Backups/TIMESTAMP/apps/` |
| Dashboards | `/api/manager/dashboards/dashboard` | `Backups/TIMESTAMP/dashboards/` |
| Light Scenes | `/api/manager/moods/mood` | `Backups/TIMESTAMP/moods/` |
| System Info | `/api/manager/system/state` | `Backups/TIMESTAMP/meta.json` |
| Geolocation ⚠️ | `/api/manager/geolocation/state` + `/option/location` + `/option/address` | `Backups/TIMESTAMP/geolocation.json` — contains home latitude, longitude and address |

> **⚠️ What is NOT backed up**
>
> This toolchain is a **partial backup**, not a full Homey state snapshot. The following are **not** captured:
> - Homey Insights data and history
> - Energy cost configuration
> - User accounts and permission settings
> - Homey cloud backup history
>
> For full disaster recovery, combine this toolchain with **Homey's own cloud backup** (Homey app → Settings → Backup).

> **🔒 Privacy note**: `geolocation.json` contains your home's latitude, longitude and street address. Treat your `Backups/` directory accordingly — do not commit it to a public repository or share it with untrusted parties.

Files are named `<slugified-name>-<id>.json`, e.g.:

```
Backups/2026-04-26_14-05/flows/goodnight-f6417ce9-e7e0-4571-a3f7-87895a0e93e0.json
```

BLL (Better Logic) variables use a different convention: `bll-<variable-name>.json` (no UUID suffix — BLL variables are identified by name, not ID).

Each backup run creates a new timestamped directory (`YYYY-MM-DD_HH-MM`). If the directory already exists, the script exits with an error to prevent overwriting. Pass `--force` to overwrite an existing directory for the same timestamp instead of aborting.

#### CLI flags

| Flag | Description |
|---|---|
| `--force` | Overwrite an existing backup directory for the same timestamp (default: abort if directory exists) |
| `--render-svg` | After backup, render all flow diagrams as SVG files alongside the flow JSON (invokes `render_flows.py`) |
| `--render-png` | After backup, render all flow diagrams as PNG images — requires `cairosvg` (invokes `render_flows.py --png`) |
| `--throttle SECONDS` | Sleep SECONDS between backup categories (default: 0). Use when Homey Pro seems overloaded by rapid sequential API calls |
| `--version` | Print version and exit |

> **Note:** If `HOMEY_API_TOKEN` doesn't look like a Homey PAT (`atk_…`) or a JWT, backup.py prints a non-fatal warning and continues. The backup will still run — the warning is informational only.

#### Summary output

```
╔══ BACKUP SUMMARY ════════════════════════════════════╗
  Category   │  Saved │ Skipped │ Errors │ Output path
  ───────────┼────────┼─────────┼────────┼─────────────────────────
  Devices      │     42 │       0 │      0 │ .../Backups/2026-04-26_14-05/devices
  Flows        │     38 │       0 │      0 │ .../Backups/2026-04-26_14-05/flows
  Flow Folders │      5 │       0 │      0 │ .../Backups/2026-04-26_14-05/flow_folders
  Zones        │     16 │       0 │      0 │ .../Backups/2026-04-26_14-05/zones
  Variables    │     12 │       0 │      0 │ .../Backups/2026-04-26_14-05/variables
  Apps         │      8 │       0 │      0 │ .../Backups/2026-04-26_14-05/apps
  System       │      1 │       0 │      0 │ .../Backups/2026-04-26_14-05/meta.json
  Geolocation  │      1 │       0 │      0 │ .../Backups/2026-04-26_14-05/geolocation.json
  Dashboards   │      3 │       0 │      0 │ .../Backups/2026-04-26_14-05/dashboards
  Moods        │      6 │       0 │      0 │ .../Backups/2026-04-26_14-05/moods
╚══════════════════════════════════════════════════════╝
```

#### Scheduling automated backups (optional)

**Linux/macOS (cron)** — run daily at 2 am:

```bash
0 2 * * * cd /path/to/Homey_Backups && HOMEY_API_URL=http://192.168.1.100 HOMEY_API_TOKEN=atk_xxx uv run backup.py >> backup.log 2>&1
```

**macOS (launchd):** create a plist in `~/Library/LaunchAgents/` — see [Apple's launchd documentation](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html).

#### First-backup sanity check (recommended)

After running `backup.py` for the first time, confirm all of the following before relying on this backup for recovery:

- [ ] The summary shows **non-zero counts** for every category you use
- [ ] Timestamped directories exist: `Backups/YYYY-MM-DD_HH-MM/flows/`, `Backups/YYYY-MM-DD_HH-MM/zones/`, etc.
- [ ] Open any flow JSON — it should contain a `cards` object (advanced flow) or `trigger`/`conditions`/`actions` (standard flow)
- [ ] `uv run restore.py` can browse the backup — choose a category, select today's timestamp, and items appear

If any category shows `0`, verify your Personal Access Token has all permissions granted and re-run.

---

### `restore.py` — Interactively Browse & Prepare Re-imports

An interactive terminal UI that reads local backup files and **prepares** them for re-import into Homey.

> ⚠️ **`restore.py` makes zero network calls and writes nothing to Homey.** It shows you the JSON, copies it to your clipboard, and prints instructions for the manual import step. The actual import — and any UUID remapping — is done by you in the Homey web app or via the REST API. See [RECOVERY.md](./RECOVERY.md) for the full ordered process.

#### Workflow

1. **Choose a category** — Device, Flow, Flow Folder, Zone, or Variable
2. **Select a backup date**
3. **Filter by name or ID** (or press Enter to show all) — filtering matches against both the item name and its ID
4. **Select an item** from the list
5. **Review JSON preview** — a formatted preview of the item JSON is shown before the clipboard copy prompt
6. **Copy JSON to clipboard** (optional) — paste directly into Homey
7. **Import instructions** are printed for the selected category

Press `Ctrl+C` at any prompt to exit cleanly.

Run `uv run restore.py --version` to print the version and exit.

#### Restore order matters

After a factory reset, restore in this exact order to avoid broken references:

1. **Zones** — must exist before flows; flow cards embed zone UUIDs directly
2. **Variables** — should exist before flows that test or set them
3. **Devices** — re-pair physically at any time, then open each broken flow and update device cards
4. **Flow Folders** — must exist before flows; build an old→new UUID mapping as you create each one
5. **Flows** — import last; update device/zone/variable/folder UUID references as you go

> For the full step-by-step procedure including curl examples and UUID reconciliation tables, see **[RECOVERY.md](./RECOVERY.md)**.

#### Re-importing items

**Flow Folders (restore before flows):**
- Create: `POST /api/manager/flow/flowfolder`
- Update: `PUT /api/manager/flow/flowfolder/<id>`
- Restore parent folders before child folders; build an old → new UUID mapping to update flow `folder` fields before import

**Flows (easiest):**
- **Web App:** [my.homey.app](https://my.homey.app) → Flows → ⋮ → *Import flow* → paste JSON
- **REST API:** `POST /api/manager/flow/flow` (normal) or `/api/manager/flow/advancedflow`

**Zones:**
- Create: `POST /api/manager/zones/zone`
- Update: `PUT /api/manager/zones/zone/<id>`
- Restore parent zones before child zones

**Devices:**
- Devices cannot be directly imported; re-pair the physical device via the Homey app
- ⚠️ Re-pairing assigns a **new UUID** — the old UUID in the backup JSON will no longer match
- After re-pairing, use `PUT /api/manager/devices/device/<new-id>` to restore settings, and manually update any flows that referenced the old device UUID
- See [RECOVERY.md](./RECOVERY.md) for the full UUID reconciliation process

**Variables:**
- Logic: `POST /api/manager/logic/variable` or `PUT /api/manager/logic/variable/<id>`
- BLL: via the BLL app settings page or `PUT /api/app/net.i-dev.betterlogic/variable/<name>`

> **Restoring flow folders:** Flow folder structure is backed up to `Backups/TIMESTAMP/flow_folders/`. Restore folders **before** flows so you can supply the correct folder ID in each flow's JSON during import. See [RECOVERY.md](./RECOVERY.md) for the full ordered procedure.

---

### `render_flows` — Visualise Flows as SVG

> **`render_flows.py`** is the primary script. The `render_flows/` package is the implementation. Both `uv run render_flows.py` and `python -m render_flows` work.

Renders Homey flow JSON backups — both standard and advanced flows — as SVG diagrams matching Homey's dark-themed visual editor. **Zero required external dependencies** — stdlib only (optional `cairosvg` for PNG export).

#### Usage

```bash
# Single flow (SVG written alongside the JSON)
python -m render_flows Backups/2026-04-26_14-05/flows/my-flow-uuid.json

# Specify output path
python -m render_flows Backups/2026-04-26_14-05/flows/my-flow-uuid.json -o diagram.svg

# Batch render all flows from a backup run
python -m render_flows Backups/2026-04-26_14-05/flows/*.json -d flow-rendering/

# Also works as a uv script:
uv run render_flows.py Backups/2026-04-26_14-05/flows/my-flow-uuid.json
```

Device, zone, and variable names are **auto-resolved** from matching backup timestamp directories — provided the flow files are at `Backups/TIMESTAMP/flows/` and the corresponding backup dirs (`Backups/TIMESTAMP/devices/`, `Backups/TIMESTAMP/zones/`, `Backups/TIMESTAMP/variables/`) exist at the same level. If you ran `backup.py` before rendering in the standard layout, names are picked up automatically. Otherwise, use `--devices-dir`, `--zones-dir`, or `--variables-dir` to specify paths manually.

#### What it renders

- All card types: `trigger`, `condition`, `action`, `delay`, `any`/`or`, `all`/`and`, `start`, `note`
- Connection wires: blue (success), green (true), **amber (false)**, amber/orange (error)
- Smart badges per card source: `ZONE TRIGGER`, `DEVICE TRIGGER`, `BLL CONDITION`, `BLL ACTION`, `TIMELINE`, `LOGIC ACTION`
- Human-readable labels: zone names, variable names, cron descriptions (`Sun sets in 0 minutes`), BLL expressions (`'Door_Window_Open' contains 'Dining room:deviceName'`)
- Sticky notes with colour coding (yellow, blue, red, green)

#### Optional CLI flags

| Flag | Default | Purpose |
|---|---|---|
| `--devices-dir DIR` | auto | Directory of device backup JSONs |
| `--zones-dir DIR` | auto | Directory of zone backup JSONs |
| `--variables-dir DIR` | auto | Directory of variable backup JSONs |
| `-d DIR` | — | Output directory for batch mode |
| `-o FILE` | — | Output SVG/PNG path (single-file mode) |
| `--filter TEXT` | — | Only render flows whose name contains TEXT (case-insensitive), e.g. `--filter kitchen` |
| `--png` | off | Convert output to PNG instead of SVG (requires `cairosvg` + `libcairo2`) |
| `--version` | — | Print version and exit |

---

## Folder Structure

```
Homey_Backups/
├── backup.py            ← Fetches and saves from Homey via REST API
├── restore.py           ← Interactive CLI to browse and prepare re-imports
├── render_flows.py      ← Primary render script (delegates to render_flows/)
├── render_flows/        ← Flow-to-SVG rendering package
│   ├── __init__.py      ← Public re-exports
│   ├── __main__.py      ← `python -m render_flows` entry point
│   ├── _cli.py          ← CLI argument parsing and orchestration
│   ├── _constants.py    ← Colors, fonts, dimensions, __version__
│   ├── _label_parser.py ← Label/token resolution
│   ├── _lookups.py      ← Device/zone/variable lookup builders
│   ├── _renderers.py    ← render_flow, render_standard_flow
│   └── _svg_builder.py  ← SVGBuilder class
├── pyproject.toml       ← Project metadata and shared dependencies (uv)
├── README.md            ← This file
├── RECOVERY.md          ← Full factory-reset recovery playbook
└── Backups/
    └── YYYY-MM-DD_HH-MM/    ← one directory per backup run
        ├── apps/            ← one JSON per app (with settings embedded)
        ├── dashboards/      ← one JSON per dashboard
        ├── devices/         ← one JSON per device
        ├── flow_folders/    ← one JSON per flow folder
        ├── flows/           ← one JSON per flow
        ├── moods/           ← one JSON per light scene
        ├── variables/       ← one JSON per variable
        ├── zones/           ← one JSON per zone
        ├── geolocation.json ← home location config (lat/lon, address, mode) ⚠️ contains sensitive location data
        └── meta.json        ← system info snapshot
```

---

## Development & CI

### Running tests locally

```bash
./tests/run_tests.sh           # lint (ruff) + run all tests (uses uv)
./tests/run_tests.sh -v        # verbose
./tests/run_tests.sh -k backup # filter by name
```

Or directly with pytest:

```bash
uv run pytest tests/ --tb=short
```

### GitHub Actions workflow

The repo ships with a CI workflow at `.github/workflows/ci.yml`. It runs on every push or pull request that touches a script, test file, or `pyproject.toml`. Steps:

1. `pip install -e ".[dev]"` — installs the package + dev extras (pytest, ruff)
2. `ruff check .` — lint (unused imports, style errors, etc.)
3. `pytest --tb=short` — full test suite

Matrix: **Python 3.11**, **Python 3.12**, and **Python 3.13** (all must pass).

### Running CI locally with act

[nektos/act](https://github.com/nektos/act) runs the GitHub Actions workflow inside Docker, so you can validate it before pushing.

**Requirements:**
- Docker running
- `act` installed:
  - macOS: `brew install act`
  - Linux: `curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash`

**Usage:**

```bash
# Full matrix (3.11 + 3.12) — pulls Docker image on first run (~800 MB)
./tests/run_ci_local.sh

# Single Python version
./tests/run_ci_local.sh --python 3.11

# Dry-run: parse and validate the workflow without pulling Docker
./tests/run_ci_local.sh -n
```

> The first real run pulls `catthehacker/ubuntu:act-latest` (~800 MB). Subsequent runs reuse the cached image.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `HOMEY_API_URL environment variable is not set` | Export `HOMEY_API_URL` and `HOMEY_API_TOKEN` before running, or create a `.env` file (see Persistent Setup above) |
| `Cannot connect to Homey` | Check your Homey's IP; ensure your machine is on the same network |
| `HTTP 401` | Token is invalid or expired — generate a new Personal Access Token in the Homey app |
| `'inquirer' is not installed` | Run `uv sync` or `uv run restore.py` (auto-installs via inline header) |
| Clipboard copy fails (Linux) | `sudo apt install xsel` (preferred) or `sudo apt install xclip` |
| Clipboard copy fails (macOS) | `pbcopy` is auto-detected — should work out of the box; if not, check that `/usr/bin/pbcopy` exists |
| Clipboard copy fails (Windows) | `clip.exe` is auto-detected — should work out of the box; if not, check that `clip` is on your PATH |
| Backup directory already exists | Each backup run needs a unique timestamp — wait a minute, delete the existing directory, or re-run with `--force` to overwrite it |
| SVG shows `[var:041893df]` | Run `backup.py` first to create a `Backups/TIMESTAMP/variables/` backup; the renderer auto-discovers it |
| Flows restored but show as broken | Flow references old device UUID — re-pair the device and update the flow card; see [RECOVERY.md](./RECOVERY.md) |
