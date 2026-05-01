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

import argparse
import os
import sys
import json
import pathlib
import requests
from dataclasses import dataclass, field
from typing import Optional
from collections.abc import Callable
from slugify import slugify
import datetime

__version__ = "0.1.0"



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
    Generic backup loop shared by all five backup_* functions.

    items       — pre-fetched, pre-processed list of dicts
    output_dir  — where to write JSON files (must not exist yet)
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
            print(f"  Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)
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

    def _filename(item: dict) -> str | None:
        item_id = item.get("id") or item.get("_id") or item.get("ID")
        name = item.get("name") or item.get("title") or ""
        if not item_id:
            print(f"[WARN] Device without ID skipped: {name!r}")
            return None
        return f"{slugify(name, separator='-') if name else 'unnamed'}-{item_id}.json"

    return _backup_items(items, output_dir, "Devices", "devices", _filename,
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

    def _filename(item: dict) -> str | None:
        item_id = item.get("id") or item.get("_id") or item.get("ID")
        name = item.get("name") or item.get("title") or ""
        if not item_id:
            print(f"[WARN] Flow without ID skipped: {name!r}")
            return None
        return f"{slugify(name, separator='-') if name else 'unnamed'}-{item_id}.json"

    return _backup_items(items, output_dir, "Flows", "flows", _filename,
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

    def _filename(item: dict) -> str | None:
        item_id = item.get("id") or item.get("_id") or item.get("ID")
        name = item.get("name") or item.get("title") or ""
        if not item_id:
            print(f"[WARN] Flow folder without ID skipped: {name!r}")
            return None
        return f"{slugify(name, separator='-') if name else 'unnamed'}-{item_id}.json"

    return _backup_items(items, output_dir, "Flow Folders", "flow folders", _filename,
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

    def _filename(item: dict) -> str | None:
        item_id = item.get("id") or item.get("_id") or item.get("ID")
        name = item.get("name") or item.get("title") or ""
        if not item_id:
            print(f"[WARN] Zone without ID skipped: {name!r}")
            return None
        return f"{slugify(name, separator='-') if name else 'unnamed'}-{item_id}.json"

    return _backup_items(items, output_dir, "Zones", "zones", _filename,
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


def main() -> None:
    """Validate config, connect to Homey, and run all five backup categories."""
    ap = argparse.ArgumentParser(description="Homey Backup — back up devices, flows, zones and variables via local REST API")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite an existing backup directory for the same timestamp (use with caution).",
    )
    args = ap.parse_args()

    if not HOMEY_API_URL:
        print("[ERROR] HOMEY_API_URL environment variable is not set.", file=sys.stderr)
        print("        Set it to your Homey Pro's IP, e.g.: export HOMEY_API_URL=http://192.168.1.100", file=sys.stderr)
        sys.exit(1)
    if not HOMEY_API_TOKEN:
        print("[ERROR] HOMEY_API_TOKEN environment variable is not set.", file=sys.stderr)
        print("        Generate a Personal Access Token in the Homey mobile app.", file=sys.stderr)
        sys.exit(1)

    # Validate token looks like a JWT (3 dot-separated base64 segments)
    _token_parts = HOMEY_API_TOKEN.split(".")
    if len(_token_parts) != 3:
        print(
            "[WARN] HOMEY_API_TOKEN does not look like a valid JWT "
            "(expected 3 dot-separated segments). Attempting connection anyway.",
            file=sys.stderr,
        )

    print(f"Connecting to Homey Pro at {HOMEY_API_URL} …\n")
    api = HomeyAPI(HOMEY_API_URL, HOMEY_API_TOKEN)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    base = pathlib.Path(__file__).parent

    results: list[BackupResult] = []
    results.append(backup_devices(api, output_dir=base / "devices" / now_str, force=args.force))
    results.append(backup_flows(api, output_dir=base / "flows" / now_str, force=args.force))
    results.append(backup_flow_folders(api, output_dir=base / "flow_folders" / now_str, force=args.force))
    results.append(backup_zones(api, output_dir=base / "zones" / now_str, force=args.force))
    results.append(backup_logic_variables(api, output_dir=base / "variables" / now_str, force=args.force))

    _print_summary(results)


if __name__ == "__main__":
    main()
