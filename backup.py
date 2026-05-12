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
Backs up devices, flows, flow folders, zones, logic variables, apps, dashboards,
light scenes (moods), system info, and geolocation from a Homey Pro instance via
the local REST API.

---
This script is intended to be run with [uv](https://github.com/astral-sh/uv):
    HOMEY_API_URL=http://192.168.x.x HOMEY_API_TOKEN=xxx uv run backup.py
---
"""

import argparse
import os
import subprocess
import sys
import time
import json
import pathlib
import requests
from dataclasses import dataclass, field
from typing import Optional
from collections.abc import Callable
from slugify import slugify
import datetime

__version__ = "0.3.3"



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


class HomeyAPIError(Exception):
    """Raised when a Homey Pro API request fails (network error, timeout, or non-200 response).

    Callers should catch this and record it in BackupResult.error_details rather than
    letting it propagate — this allows the backup to continue to other categories even
    if one API call fails.
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

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
            raise HomeyAPIError(f"Cannot connect to Homey at {self.base_url}: {url}")
        except requests.exceptions.Timeout:
            raise HomeyAPIError(f"Request timed out: {url}")
        except requests.exceptions.RequestException as exc:
            raise HomeyAPIError(f"HTTP error fetching {url}: {exc}")

        if resp.status_code != 200:
            raise HomeyAPIError(f"Homey API returned HTTP {resp.status_code} for {url}")

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

    def get_apps(self) -> list[dict]:
        """Return all installed Homey apps as a flat list."""
        data = self._get("/manager/apps/app")
        return _dict_to_list(data)

    def get_app_settings(self, app_id: str) -> dict:
        """Return settings for a specific app, or {} if unavailable (404, no settings, etc.)."""
        try:
            data = self._get(f"/manager/apps/app/{app_id}/settings")
            return data if isinstance(data, dict) else {}
        except HomeyAPIError:
            return {}

    def get_system_info(self) -> dict:
        """Return Homey system state (firmware version, home location, etc.).

        Tries /manager/system/state first; falls back to /manager/system if that fails.
        """
        try:
            data = self._get("/manager/system/state")
            return data if isinstance(data, dict) else {}
        except HomeyAPIError:
            data = self._get("/manager/system")
            return data if isinstance(data, dict) else {}

    def get_geolocation(self) -> dict:
        """Return merged home geolocation config (state + location option + address option).

        Calls three separate endpoints and merges results under keys
        ``state``, ``location``, and ``address``.  Any endpoint that fails
        is silently skipped (empty dict for that key) so a partial result
        is still useful.
        """
        result: dict = {}
        for key, path in [
            ("state",    "/manager/geolocation/state"),
            ("location", "/manager/geolocation/option/location"),
            ("address",  "/manager/geolocation/option/address"),
        ]:
            try:
                data = self._get(path)
                result[key] = data if isinstance(data, dict) else {}
            except HomeyAPIError:
                result[key] = {}
        return result

    def get_dashboards(self) -> list[dict]:
        """Return all user-created Homey dashboards as a flat list."""
        data = self._get("/manager/dashboards/dashboard")
        return _dict_to_list(data)

    def get_moods(self) -> list[dict]:
        """Return all Homey light scenes (moods) as a flat list."""
        data = self._get("/manager/moods/mood")
        return _dict_to_list(data)


# ---------------------------------------------------------------------------
# Generic backup helper
# ---------------------------------------------------------------------------


def _backup_items(
    items: list[dict],
    output_dir: pathlib.Path,
    category: str,
    header: str,
    filename_fn: Callable[[dict], str | None],
    warn_empty: str = "No data returned by API.",
    force: bool = False,
) -> BackupResult:
    """
    Generic backup loop shared by all list-based backup_* functions.

    items       — pre-fetched, pre-processed list of dicts
    output_dir  — where to write JSON files (must not exist yet).
                  The directory name must match the corresponding value in
                  restore.py's CATEGORY_SUBDIRS dict so that restore.py can
                   find it. (backup_system_info and backup_geolocation use
                   single-file output paths and do NOT use this helper.)
    category    — display name for BackupResult (e.g. "Devices")
    header      — printed header line (e.g. "devices")
    filename_fn — returns filename string for this item, or None to skip
    warn_empty  — warning message if items is empty
    """
    print(f"\n── Backing up {header} {('─' * max(0, 47 - len(header)))}")
    result = BackupResult(category=category, output_dir=output_dir.resolve())

    if output_dir.exists():
        if not force:
            print(f"[ERROR] Backup directory already exists: {output_dir}", file=sys.stderr)
            print("  Use --force to overwrite.", file=sys.stderr)
            result.errors += 1
            result.note = "already exists — use --force to overwrite"
            return result
        else:
            print(f"[WARN] Overwriting existing backup directory: {output_dir}", file=sys.stderr)
    output_dir.mkdir(parents=True, exist_ok=force)

    if not items:
        print(f"[WARN] {warn_empty}")
        result.note = "no data returned by API"
        return result

    for item in items:
        filename = filename_fn(item)
        if filename is None:
            result.skipped += 1
            continue
        filepath = output_dir / filename
        try:
            filepath.write_text(
                json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  ✓  {filename}")
            result.saved += 1
        except OSError as exc:
            msg = f"{filename}: {exc}"
            print(f"  ✗  [ERROR] Failed to write {msg}", file=sys.stderr)
            result.errors += 1
            result.error_details.append(msg)

    return result


def _default_filename(item: dict, category_label: str) -> str | None:
    """Return the JSON filename for *item*, or ``None`` if the item has no ID.

    Used by all ``backup_*`` functions that follow the standard
    ``{slug}-{id}.json`` naming pattern.  *category_label* is used only in
    the ``[WARN]`` message when an ID is missing (e.g. ``"Device"``,
    ``"Flow"``, ``"Zone"``).
    """
    item_id = item.get("id") or item.get("_id") or item.get("ID")
    name = item.get("name") or item.get("title") or ""
    if not item_id:
        print(f"[WARN] {category_label} without ID skipped: {name!r}")
        return None
    return f"{slugify(name, separator='-') if name else 'unnamed'}-{item_id}.json"


# ---------------------------------------------------------------------------
# Backup logic — devices
# ---------------------------------------------------------------------------

def backup_devices(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all devices from Homey and save each as a JSON file."""
    try:
        items = api.get_devices()
    except HomeyAPIError as exc:
        result = BackupResult(category="Devices")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    return _backup_items(items, output_dir, "Devices", "devices",
                         lambda item: _default_filename(item, "Device"),
                         warn_empty="No devices returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — flows
# ---------------------------------------------------------------------------

def backup_flows(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all normal and advanced flows and save each as a JSON file."""
    try:
        normal = api.get_flows()
        advanced = api.get_advanced_flows()
    except HomeyAPIError as exc:
        result = BackupResult(category="Flows")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    for flow in normal:
        flow["flow_type"] = "normal"
    for flow in advanced:
        flow["flow_type"] = "advanced"
    items = normal + advanced

    return _backup_items(items, output_dir, "Flows", "flows",
                         lambda item: _default_filename(item, "Flow"),
                         warn_empty="No flows returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — flow folders
# ---------------------------------------------------------------------------

def backup_flow_folders(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all flow folders and save each as a JSON file."""
    try:
        items = api.get_flow_folders()
    except HomeyAPIError as exc:
        result = BackupResult(category="Flow Folders")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    return _backup_items(items, output_dir, "Flow Folders", "flow folders",
                         lambda item: _default_filename(item, "Flow folder"),
                         warn_empty="No flow folders returned by API (all flows may be in root).", force=force)


# ---------------------------------------------------------------------------
# Backup logic — zones
# ---------------------------------------------------------------------------

def backup_zones(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all zones and save each as a JSON file."""
    try:
        items = api.get_zones()
    except HomeyAPIError as exc:
        result = BackupResult(category="Zones")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    return _backup_items(items, output_dir, "Zones", "zones",
                         lambda item: _default_filename(item, "Zone"),
                         warn_empty="No zones returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — logic variables (Homey Logic + Better Logic Library)
# ---------------------------------------------------------------------------

def backup_logic_variables(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all Homey Logic and BLL variables and save each as a JSON file."""
    try:
        logic_vars = api.get_logic_variables()
        bll_vars = api.get_bll_variables()
    except HomeyAPIError as exc:
        result = BackupResult(category="Variables")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    for item in logic_vars:
        item["source"] = "logic"
    for item in bll_vars:
        item["source"] = "bll"
    items = logic_vars + bll_vars

    def _filename(item: dict) -> str | None:
        source = item.get("source", "logic")
        name = item.get("name") or item.get("title") or ""
        if source == "bll":
            if not name:
                print("[WARN] BLL variable without name skipped")
                return None
            return f"bll-{slugify(name, separator='-') or 'unnamed'}.json"
        else:
            var_id = item.get("id") or item.get("_id") or item.get("ID")
            if not var_id:
                print(f"[WARN] Variable without ID skipped: {name!r}")
                return None
            slug = slugify(name, separator="-") if name else "unnamed"
            return f"{slug}-{var_id}.json"

    return _backup_items(items, output_dir, "Variables", "logic variables", _filename,
                         warn_empty="No logic variables returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — installed apps (+ per-app settings embedded)
# ---------------------------------------------------------------------------

def backup_apps(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all installed apps, enrich each with its settings, and save as JSON files."""
    try:
        items = api.get_apps()
    except HomeyAPIError as exc:
        result = BackupResult(category="Apps")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    # Enrich each app with its per-app settings (graceful — returns {} if unavailable)
    for item in items:
        app_id = item.get("id")
        if app_id:
            item["settings"] = api.get_app_settings(app_id)

    return _backup_items(items, output_dir, "Apps", "apps",
                         lambda item: _default_filename(item, "App"),
                         warn_empty="No apps returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — system info (single-file, not a directory)
# ---------------------------------------------------------------------------

def backup_system_info(api: HomeyAPI, output_path: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch Homey system state and save as a single JSON file (meta.json)."""
    print("\n── Backing up system info " + "─" * 22)
    result = BackupResult(category="System", output_dir=output_path.resolve())

    if output_path.exists() and not force:
        print(f"[ERROR] Backup file already exists: {output_path}", file=sys.stderr)
        print("  Use --force to overwrite.", file=sys.stderr)
        result.errors += 1
        result.note = "already exists — use --force to overwrite"
        return result

    try:
        info = api.get_system_info()
    except HomeyAPIError as exc:
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    if not info:
        print("[WARN] No system info returned by API.")
        result.note = "no data returned by API"
        return result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓  {output_path.name}")
        result.saved += 1
    except OSError as exc:
        result.errors += 1
        result.error_details.append(str(exc))

    return result


# ---------------------------------------------------------------------------
# Backup logic — geolocation
# ---------------------------------------------------------------------------

def backup_geolocation(api: HomeyAPI, output_path: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch home geolocation config and save as a single JSON file (geolocation.json).

    Merges data from three API endpoints (state, location option, address option)
    under keys ``state``, ``location``, and ``address``.
    """
    print("\n── Backing up geolocation " + "─" * 24)
    result = BackupResult(category="Geolocation", output_dir=output_path.resolve())

    if output_path.exists() and not force:
        print(f"[ERROR] Backup file already exists: {output_path}", file=sys.stderr)
        print("  Use --force to overwrite.", file=sys.stderr)
        result.errors += 1
        result.note = "already exists — use --force to overwrite"
        return result

    try:
        geo = api.get_geolocation()
    except Exception as exc:  # pragma: no cover — get_geolocation() swallows per-endpoint errors
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    if not any(geo.values()):
        print("[WARN] No geolocation data returned by API.")
        result.note = "no data returned by API"
        return result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(json.dumps(geo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓  {output_path.name}")
        result.saved += 1
    except OSError as exc:
        result.errors += 1
        result.error_details.append(str(exc))

    return result


# ---------------------------------------------------------------------------
# Backup logic — dashboards
# ---------------------------------------------------------------------------

def backup_dashboards(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all Homey dashboards and save each as a JSON file."""
    try:
        items = api.get_dashboards()
    except HomeyAPIError as exc:
        result = BackupResult(category="Dashboards")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    return _backup_items(items, output_dir, "Dashboards", "dashboards",
                         lambda item: _default_filename(item, "Dashboard"),
                         warn_empty="No dashboards returned by API.", force=force)


# ---------------------------------------------------------------------------
# Backup logic — moods (light scenes)
# ---------------------------------------------------------------------------

def backup_moods(api: HomeyAPI, output_dir: pathlib.Path, force: bool = False) -> BackupResult:
    """Fetch all Homey light scenes (moods) and save each as a JSON file."""
    try:
        items = api.get_moods()
    except HomeyAPIError as exc:
        result = BackupResult(category="Moods")
        result.errors += 1
        result.error_details.append(str(exc))
        result.note = "API call failed"
        print(f"[ERROR] {exc}", file=sys.stderr)
        return result

    return _backup_items(items, output_dir, "Moods", "light scenes",
                         lambda item: _default_filename(item, "Mood"),
                         warn_empty="No moods returned by API.", force=force)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _write_manifest(results: list[BackupResult], backup_root: pathlib.Path, timestamp: str, tool_version: str) -> None:
    """Write a manifest.json to backup_root recording category counts and completion status."""
    manifest = {
        "schema_version": 1,
        "tool_version": tool_version,
        "timestamp": timestamp,
        "completed": True,
        "categories": {
            result.category: {
                "saved": result.saved,
                "skipped": result.skipped,
                "errors": result.errors,
            }
            for result in results
        },
    }
    (backup_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
        # Truncate from the left so the date portion (most useful) is always visible
        if len(dir_str) > col_dir:
            dir_str = "…" + dir_str[-(col_dir - 1):]
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


# ---------------------------------------------------------------------------
# Post-backup render helper
# ---------------------------------------------------------------------------


def _render_flows(flows_dir: pathlib.Path, *, png: bool = False) -> None:
    """Invoke render_flows.py on all flow JSON files in *flows_dir*.

    Called after backup when --render-svg or --render-png is set.
    Errors from the renderer are printed but do not affect the backup result.
    """
    if not flows_dir.is_dir():
        print(f"\n[SKIP] Flow render: {flows_dir} does not exist (flows backup may have failed).")
        return

    flow_files = sorted(flows_dir.glob("*.json"))
    if not flow_files:
        print(f"\n[SKIP] Flow render: no JSON files found in {flows_dir}.")
        return

    svg_script = pathlib.Path(__file__).parent / "render_flows.py"
    if not svg_script.exists():
        print(f"\n[ERROR] Flow render: render_flows.py not found at {svg_script}.", file=sys.stderr)
        return

    cmd = [sys.executable, str(svg_script)] + [str(f) for f in flow_files]
    if png:
        cmd.append("--png")

    mode = "PNG" if png else "SVG"
    print(f"\n── Rendering flow diagrams ({mode}) " + "─" * 20)
    try:
        subprocess.run(cmd, check=False)
    except OSError as exc:
        print(f"[ERROR] Flow render failed: {exc}", file=sys.stderr)


def main() -> None:
    """Validate config, connect to Homey, and run all backup categories."""
    ap = argparse.ArgumentParser(description="Homey Backup — back up devices, flows, zones and variables via local REST API")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite an existing backup directory for the same timestamp (use with caution).",
    )
    ap.add_argument(
        "--render-svg",
        action="store_true",
        default=False,
        help="After backup, render all flow diagrams as SVG files alongside the flow JSON.",
    )
    ap.add_argument(
        "--render-png",
        action="store_true",
        default=False,
        help="After backup, render all flow diagrams as PNG images (requires cairosvg).",
    )
    ap.add_argument(
        "--throttle",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help=(
            "Sleep SECONDS between backup categories (default: 0). "
            "Use when Homey Pro seems overloaded by rapid sequential API calls."
        ),
    )
    args = ap.parse_args()

    HOMEY_API_URL = os.environ.get("HOMEY_API_URL", "").rstrip("/")
    HOMEY_API_TOKEN = os.environ.get("HOMEY_API_TOKEN", "")

    if not HOMEY_API_URL:
        print("[ERROR] HOMEY_API_URL environment variable is not set.", file=sys.stderr)
        print("        Set it to your Homey Pro's IP, e.g.: export HOMEY_API_URL=http://192.168.1.100", file=sys.stderr)
        sys.exit(1)
    if not HOMEY_API_TOKEN:
        print("[ERROR] HOMEY_API_TOKEN environment variable is not set.", file=sys.stderr)
        print("        Generate a Personal Access Token in the Homey mobile app.", file=sys.stderr)
        sys.exit(1)

    # Accept both Homey PATs (atk_ prefix) and JWT-style local tokens (3 dot-separated segments)
    _token_parts = HOMEY_API_TOKEN.split(".")
    if not HOMEY_API_TOKEN.startswith("atk_") and len(_token_parts) != 3:
        print(
            "[WARN] HOMEY_API_TOKEN does not look like a valid Homey token "
            "(expected atk_… PAT or a 3-segment JWT). Attempting connection anyway.",
            file=sys.stderr,
        )

    print(f"Connecting to Homey Pro at {HOMEY_API_URL} …\n")
    api = HomeyAPI(HOMEY_API_URL, HOMEY_API_TOKEN)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    base = pathlib.Path(__file__).parent
    backup_root = base / "Backups" / now_str

    # NOTE: Directory names below must stay in sync with CATEGORY_SUBDIRS in restore.py.
    # Single-file backups (meta.json, geolocation.json) are not in CATEGORY_SUBDIRS.
    _category_fns = [
        lambda: backup_devices(api, output_dir=backup_root / "devices", force=args.force),
        lambda: backup_flows(api, output_dir=backup_root / "flows", force=args.force),
        lambda: backup_flow_folders(api, output_dir=backup_root / "flow_folders", force=args.force),
        lambda: backup_zones(api, output_dir=backup_root / "zones", force=args.force),
        lambda: backup_logic_variables(api, output_dir=backup_root / "variables", force=args.force),
        lambda: backup_apps(api, output_dir=backup_root / "apps", force=args.force),
        lambda: backup_system_info(api, output_path=backup_root / "meta.json", force=args.force),
        lambda: backup_geolocation(api, output_path=backup_root / "geolocation.json", force=args.force),
        lambda: backup_dashboards(api, output_dir=backup_root / "dashboards", force=args.force),
        lambda: backup_moods(api, output_dir=backup_root / "moods", force=args.force),
    ]
    results: list[BackupResult] = []
    for i, fn in enumerate(_category_fns):
        if i > 0 and args.throttle > 0:
            time.sleep(args.throttle)
        results.append(fn())

    _print_summary(results)

    if args.render_svg or args.render_png:
        _render_flows(backup_root / "flows", png=args.render_png)

    _write_manifest(results, backup_root, now_str, __version__)


if __name__ == "__main__":
    main()
