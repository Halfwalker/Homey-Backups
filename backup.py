#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
#   "python-slugify",
# ]
# ///
"""
Homey Backup Tool
Backs up devices, flows, and zones from a Homey Pro instance via the local REST API.

---
This script is intended to be run with [uv](https://github.com/astral-sh/uv):
    HOMEY_API_URL=http://192.168.x.x HOMEY_API_TOKEN=xxx uv run backup.py
---
"""

import os
import sys
import json
import pathlib
import requests
from dataclasses import dataclass, field
from typing import Optional
from slugify import slugify
import datetime


# ---------------------------------------------------------------------------
# Result type — each backup function returns one of these
# ---------------------------------------------------------------------------

@dataclass
class BackupResult:
    category: str
    saved: int = 0
    skipped: int = 0
    errors: int = 0
    output_dir: Optional[pathlib.Path] = None
    # Human-readable note shown in the summary (e.g. "directory existed, user skipped")
    note: str = ""
    # Individual error messages collected during file writes
    error_details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.saved + self.skipped + self.errors


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOMEY_API_URL = os.environ.get("HOMEY_API_URL", "").rstrip("/")
HOMEY_API_TOKEN = os.environ.get("HOMEY_API_TOKEN", "")
REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _dict_to_list(data: dict) -> list[dict]:
    """Convert Homey's {id: {...}} response format to a flat list with id injected."""
    if not isinstance(data, dict):
        return []
    result = []
    for item_id, item_data in data.items():
        if isinstance(item_data, dict):
            item_data["id"] = item_id
            result.append(item_data)
    return result


# ---------------------------------------------------------------------------
# HomeyAPI — direct HTTP client for the Homey Pro local REST API
# ---------------------------------------------------------------------------

class HomeyAPI:
    """Direct HTTP client for the Homey Pro local REST API."""

    def __init__(self, base_url: str, token: str, timeout: int = REQUEST_TIMEOUT):
        """Initialize the HTTP client.

        Args:
            base_url: Homey Pro local URL, e.g. ``http://192.168.1.100``.
            token: Personal Access Token from the Homey mobile app
                   (More → Users & Permissions → Add Personal Access Token).
            timeout: Per-request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self._http = requests.Session()
        self._http.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        self.timeout = timeout

    def _get(self, path: str) -> dict:
        """GET {base_url}/api{path} and return parsed JSON."""
        url = f"{self.base_url}/api{path}"
        try:
            resp = self._http.get(url, timeout=self.timeout)
        except requests.exceptions.ConnectionError:
            print(f"[ERROR] Cannot connect to Homey at {self.base_url}", file=sys.stderr)
            sys.exit(1)
        except requests.exceptions.Timeout:
            print(f"[ERROR] Request timed out: {url}", file=sys.stderr)
            sys.exit(1)
        except requests.exceptions.RequestException as exc:
            print(f"[ERROR] HTTP error: {exc}", file=sys.stderr)
            sys.exit(1)

        if resp.status_code != 200:
            print(f"[ERROR] Homey API returned HTTP {resp.status_code} for {url}", file=sys.stderr)
            sys.exit(1)

        return resp.json()

    def get_devices(self) -> list[dict]:
        """Return all devices as a flat list (with id injected)."""
        data = self._get("/manager/devices/device")
        return _dict_to_list(data)

    def get_flows(self) -> list[dict]:
        """Return all normal flows as a flat list."""
        data = self._get("/manager/flow/flow")
        return _dict_to_list(data)

    def get_advanced_flows(self) -> list[dict]:
        """Return all advanced flows as a flat list with full card DAGs.

        The Homey local REST API list endpoint returns complete flow data
        including the ``cards`` DAG — no separate per-flow fetch is needed.
        """
        data = self._get("/manager/flow/advancedflow")
        return _dict_to_list(data)

    def get_advanced_flow(self, flow_id: str) -> dict | None:
        """Return a single advanced flow with full card DAG, or None on error."""
        url = f"{self.base_url}/api/manager/flow/advancedflow/{flow_id}"
        try:
            resp = self._http.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            print(f"  ✗  [WARN] Request failed for flow {flow_id}: {exc}")
            return None
        if resp.status_code != 200:
            print(f"  ✗  [WARN] HTTP {resp.status_code} for advanced flow {flow_id}")
            return None
        data = resp.json()
        data["id"] = flow_id
        return data

    def get_flow_folders(self) -> list[dict]:
        """Return all flow folders as a flat list."""
        data = self._get("/manager/flow/flowfolder")
        return _dict_to_list(data)

    def get_zones(self) -> list[dict]:
        """Return all zones as a flat list."""
        data = self._get("/manager/zones/zone")
        return _dict_to_list(data)

    def get_logic_variables(self) -> list[dict]:
        """Return all Homey Logic (named) variables as a flat list."""
        data = self._get("/manager/logic/variable")
        return _dict_to_list(data)

    def get_bll_variables(self) -> list[dict]:
        """Return BLL (Better Logic Library) variables, or empty list if app not present.

        Uses the special /ALL route which returns every variable as a flat list.
        Each item has: name, value, type, remove, lastChanged — no UUID id field.
        """
        url = f"{self.base_url}/api/app/net.i-dev.betterlogic/ALL"
        try:
            resp = self._http.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return _dict_to_list(data)
        return []


# ---------------------------------------------------------------------------
# Backup logic — devices
# ---------------------------------------------------------------------------

# Date-coded backup directory (YYYY-MM-DD_HH-mm)
NOW_STR = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
DEVICES_DIR = pathlib.Path(__file__).parent / "devices" / NOW_STR


def backup_devices(api: HomeyAPI) -> BackupResult:
    """
    Fetch all devices from Homey via the local REST API and save each as a JSON file.

    File naming: devices/<slugified-name>-<id>.json

    Returns a BackupResult with counts and the output directory.
    """
    print("\n── Backing up devices ──────────────────────────────────────────")
    result = BackupResult(category="Devices", output_dir=DEVICES_DIR.resolve())

    devices = api.get_devices()

    if DEVICES_DIR.exists():
        print(f"[ERROR] Backup directory already exists: {DEVICES_DIR}", file=sys.stderr)
        sys.exit(1)
    DEVICES_DIR.mkdir(parents=True, exist_ok=False)

    if not devices:
        print("[WARN] No devices returned by API.")
        result.note = "no data returned by API"
        return result

    for device in devices:
        device_id = device.get("id") or device.get("_id") or device.get("ID")
        name = device.get("name") or device.get("title") or ""

        if not device_id:
            print(f"[WARN] Device without ID skipped: {name!r}")
            result.skipped += 1
            continue

        slug = slugify(name, separator="-") if name else "unnamed"
        filename = f"{slug}-{device_id}.json"
        filepath = DEVICES_DIR / filename

        try:
            filepath.write_text(
                json.dumps(device, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [ERROR] Failed to write {msg}", file=sys.stderr)
            result.errors += 1
            result.error_details.append(msg)

    return result


# ---------------------------------------------------------------------------
# Backup logic — flows
# ---------------------------------------------------------------------------

FLOWS_DIR = pathlib.Path(__file__).parent / "flows" / NOW_STR
FLOW_FOLDERS_DIR = pathlib.Path(__file__).parent / "flow_folders" / NOW_STR


def backup_flows(api: HomeyAPI) -> BackupResult:
    """
    Fetch all normal and advanced flows from Homey via the local REST API and save
    each as a JSON file.

    File naming: flows/<slugified-name>-<id>.json
    Sets flow_type field: "normal" or "advanced"

    Returns a BackupResult with counts and the output directory.
    """
    print("\n── Backing up flows ────────────────────────────────────────────")
    result = BackupResult(category="Flows", output_dir=FLOWS_DIR.resolve())

    normal_flows = api.get_flows()

    if FLOWS_DIR.exists():
        print(f"[ERROR] Backup directory already exists: {FLOWS_DIR}", file=sys.stderr)
        sys.exit(1)
    FLOWS_DIR.mkdir(parents=True, exist_ok=False)
    for flow in normal_flows:
        flow["flow_type"] = "normal"

    advanced_flows = api.get_advanced_flows()
    for flow in advanced_flows:
        flow["flow_type"] = "advanced"

    flows = normal_flows + advanced_flows

    if not flows:
        print("[WARN] No flows returned by API.")
        result.note = "no data returned by API"
        return result

    for flow in flows:
        flow_id = flow.get("id") or flow.get("_id") or flow.get("ID")
        name = flow.get("name") or flow.get("title") or ""

        if not flow_id:
            print(f"[WARN] Flow without ID skipped: {name!r}")
            result.skipped += 1
            continue

        slug = slugify(name, separator="-") if name else "unnamed"
        filename = f"{slug}-{flow_id}.json"
        filepath = FLOWS_DIR / filename

        try:
            filepath.write_text(
                json.dumps(flow, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [ERROR] Failed to write {msg}", file=sys.stderr)
            result.errors += 1
            result.error_details.append(msg)

    return result


# ---------------------------------------------------------------------------
# Backup logic — flow folders
# ---------------------------------------------------------------------------

def backup_flow_folders(api: HomeyAPI) -> BackupResult:
    """
    Fetch all flow folders from Homey via the local REST API and save each as
    a JSON file.  Folder backup is required for full flow restore — each flow
    JSON contains a `folder` UUID that references one of these entries.

    File naming: flow_folders/<slugified-name>-<id>.json

    Returns a BackupResult with counts and the output directory.
    """
    print("\n── Backing up flow folders ─────────────────────────────────────")
    result = BackupResult(category="Flow Folders", output_dir=FLOW_FOLDERS_DIR.resolve())

    folders = api.get_flow_folders()

    if FLOW_FOLDERS_DIR.exists():
        print(f"[ERROR] Backup directory already exists: {FLOW_FOLDERS_DIR}", file=sys.stderr)
        sys.exit(1)
    FLOW_FOLDERS_DIR.mkdir(parents=True, exist_ok=False)

    if not folders:
        print("[WARN] No flow folders returned by API (all flows may be in the root).")
        result.note = "no data returned by API"
        return result

    for folder in folders:
        folder_id = folder.get("id") or folder.get("_id") or folder.get("ID")
        name = folder.get("name") or folder.get("title") or ""

        if not folder_id:
            print(f"[WARN] Flow folder without ID skipped: {name!r}")
            result.skipped += 1
            continue

        slug = slugify(name, separator="-") if name else "unnamed"
        filename = f"{slug}-{folder_id}.json"
        filepath = FLOW_FOLDERS_DIR / filename

        try:
            filepath.write_text(
                json.dumps(folder, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [ERROR] Failed to write {msg}", file=sys.stderr)
            result.errors += 1
            result.error_details.append(msg)

    return result


# ---------------------------------------------------------------------------
# Backup logic — zones
# ---------------------------------------------------------------------------

ZONES_DIR = pathlib.Path(__file__).parent / "zones" / NOW_STR


def backup_zones(api: HomeyAPI) -> BackupResult:
    """
    Fetch all zones from Homey via the local REST API and save each as a JSON file.

    File naming: zones/<slugified-name>-<id>.json

    Returns a BackupResult with counts and the output directory.
    """
    print("\n── Backing up zones ────────────────────────────────────────────")
    result = BackupResult(category="Zones", output_dir=ZONES_DIR.resolve())

    zones = api.get_zones()

    if ZONES_DIR.exists():
        print(f"[ERROR] Backup directory already exists: {ZONES_DIR}", file=sys.stderr)
        sys.exit(1)
    ZONES_DIR.mkdir(parents=True, exist_ok=False)

    if not zones:
        print("[WARN] No zones returned by API.")
        result.note = "no data returned by API"
        return result

    for zone in zones:
        zone_id = zone.get("id") or zone.get("_id") or zone.get("ID")
        name = zone.get("name") or zone.get("title") or ""

        if not zone_id:
            print(f"[WARN] Zone without ID skipped: {name!r}")
            result.skipped += 1
            continue

        slug = slugify(name, separator="-") if name else "unnamed"
        filename = f"{slug}-{zone_id}.json"
        filepath = ZONES_DIR / filename

        try:
            filepath.write_text(
                json.dumps(zone, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [ERROR] Failed to write {msg}", file=sys.stderr)
            result.errors += 1
            result.error_details.append(msg)

    return result


# ---------------------------------------------------------------------------
# Backup logic — logic variables (Homey Logic + Better Logic Library)
# ---------------------------------------------------------------------------

VARIABLES_DIR = pathlib.Path(__file__).parent / "variables" / NOW_STR


def backup_logic_variables(api: HomeyAPI) -> BackupResult:
    """
    Fetch all Homey Logic variables and BLL (Better Logic Library) variables,
    merge them, and save each as a JSON file.

    File naming:
      Logic vars: variables/<slugified-name>-<id>.json
      BLL vars:   variables/bll-<slugified-name>.json  (name is the unique key, no UUID)

    Returns a BackupResult with counts and the output directory.
    """
    print("\n── Backing up logic variables ──────────────────────────────────")
    result = BackupResult(category="Variables", output_dir=VARIABLES_DIR.resolve())

    logic_vars = api.get_logic_variables()
    bll_vars = api.get_bll_variables()
    for item in logic_vars:
        item["source"] = "logic"
    for item in bll_vars:
        item["source"] = "bll"
    variables = logic_vars + bll_vars

    if VARIABLES_DIR.exists():
        print(f"[ERROR] Backup directory already exists: {VARIABLES_DIR}", file=sys.stderr)
        sys.exit(1)
    VARIABLES_DIR.mkdir(parents=True, exist_ok=False)

    if not variables:
        print("[WARN] No logic variables returned by API.")
        result.note = "no data returned by API"
        return result

    for variable in variables:
        source = variable.get("source", "logic")
        name = variable.get("name") or variable.get("title") or ""

        if source == "bll":
            # BLL variables are identified by name, not UUID
            if not name:
                print("[WARN] BLL variable without name skipped")
                result.skipped += 1
                continue
            name_slug = slugify(name, separator="-") or "unnamed"
            filename = f"bll-{name_slug}.json"
        else:
            var_id = variable.get("id") or variable.get("_id") or variable.get("ID")
            if not var_id:
                print(f"[WARN] Variable without ID skipped: {name!r}")
                result.skipped += 1
                continue
            slug = slugify(name, separator="-") if name else "unnamed"
            filename = f"{slug}-{var_id}.json"

        filepath = VARIABLES_DIR / filename

        try:
            filepath.write_text(
                json.dumps(variable, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [WARN] {msg}")
            result.errors += 1
            result.error_details.append(msg)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _print_summary(results: list[BackupResult]) -> None:
    """Print a formatted summary table of all backup categories."""
    col_cat  = 15   # "Category"
    col_save = 7    # "Saved"
    col_skip = 8    # "Skipped"
    col_err  = 7    # "Errors"
    col_dir  = 50   # "Output path"

    sep  = f"{'─' * col_cat}─┼─{'─' * col_save}─┼─{'─' * col_skip}─┼─{'─' * col_err}─┼─{'─' * col_dir}"
    head = (
        f"{'Category':<{col_cat}} │ {'Saved':>{col_save}} │ {'Skipped':>{col_skip}} │"
        f" {'Errors':>{col_err}} │ {'Output path':<{col_dir}}"
    )

    print("\n")
    print("╔══ BACKUP SUMMARY " + "═" * (len(sep) - 16) + "╗")
    print(f"  {head}")
    print(f"  {sep}")

    total_saved = total_skipped = total_errors = 0

    for r in results:
        dir_str = str(r.output_dir) if r.output_dir else "—"
        if r.note:
            dir_str = f"({r.note})"
        row = (
            f"  {r.category:<{col_cat}} │ {r.saved:>{col_save}} │ {r.skipped:>{col_skip}} │"
            f" {r.errors:>{col_err}} │ {dir_str:<{col_dir}}"
        )
        print(row)
        total_saved   += r.saved
        total_skipped += r.skipped
        total_errors  += r.errors

    print(f"  {sep}")
    totals = (
        f"  {'TOTAL':<{col_cat}} │ {total_saved:>{col_save}} │ {total_skipped:>{col_skip}} │"
        f" {total_errors:>{col_err}} │ {'':>{col_dir}}"
    )
    print(totals)
    print("╚" + "═" * (len(sep) + 4) + "╝")

    # Print any file-write error details
    all_errors = [(r.category, detail) for r in results for detail in r.error_details]
    if all_errors:
        print("\n[ERROR DETAILS]")
        for category, detail in all_errors:
            print(f"  {category}: {detail}")

    # Overall outcome line
    print()
    if total_errors > 0:
        print(f"[DONE] Backup finished with {total_errors} error(s). Review details above.")
    elif total_saved == 0 and total_skipped == 0:
        print("[DONE] Backup finished — nothing was written (all categories skipped or empty).")
    else:
        print("[DONE] Backup complete.")


def main() -> None:
    """Validate config, connect to Homey, and run all four backup categories."""
    if not HOMEY_API_URL:
        print("[ERROR] HOMEY_API_URL environment variable is not set.", file=sys.stderr)
        print("        Set it to your Homey Pro's IP, e.g.: export HOMEY_API_URL=http://192.168.1.100", file=sys.stderr)
        sys.exit(1)
    if not HOMEY_API_TOKEN:
        print("[ERROR] HOMEY_API_TOKEN environment variable is not set.", file=sys.stderr)
        print("        Generate a Personal Access Token in the Homey mobile app.", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to Homey Pro at {HOMEY_API_URL} …\n")
    api = HomeyAPI(HOMEY_API_URL, HOMEY_API_TOKEN)

    results: list[BackupResult] = []
    results.append(backup_devices(api))
    results.append(backup_flows(api))
    results.append(backup_flow_folders(api))
    results.append(backup_zones(api))
    results.append(backup_logic_variables(api))

    _print_summary(results)


if __name__ == "__main__":
    main()
