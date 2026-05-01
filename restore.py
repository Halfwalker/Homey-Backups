#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "inquirer",
#   "pyperclip",
# ]
# ///
"""
Homey Restore Tool
Interactive CLI to browse local backups (devices, flows, zones) and prepare
items for re-import into Homey Pro.

No network calls are made here — this tool only reads the local JSON files
produced by backup.py.

---
This script is intended to be run with [uv](https://github.com/astral-sh/uv):
    uv run restore.py
---
"""

import argparse
import json
import pathlib
import sys
import textwrap

try:
    import inquirer
    from inquirer.themes import GreenPassion
except ImportError:
    print(
        "[ERROR] 'inquirer' is not installed.\n"
        "        Run: pip install inquirer",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import pyperclip
    _CLIPBOARD_AVAILABLE = True
except ImportError:
    _CLIPBOARD_AVAILABLE = False

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = pathlib.Path(__file__).parent

CATEGORY_DIRS: dict[str, pathlib.Path] = {
    "device":       _BASE / "devices",
    "flow":         _BASE / "flows",
    "flow_folder":  _BASE / "flow_folders",
    "zone":         _BASE / "zones",
    "variable":     _BASE / "variables",
}

def list_backup_dates(category: str) -> list[pathlib.Path]:
    """Return sorted list of date-coded subdirectories for *category*.

    Returns an empty list if the category backup directory does not yet exist.
    """
    cat_dir = CATEGORY_DIRS[category]
    if not cat_dir.exists():
        return []
    return sorted([p for p in cat_dir.iterdir() if p.is_dir()])


# How to import each category in Homey
IMPORT_INSTRUCTIONS: dict[str, str] = {
    "device": textwrap.dedent("""\
        ── How to re-import a DEVICE into Homey ──────────────────────────────
          Devices cannot be imported directly via the UI; however you can:

          1. Open Homey Developer Tools → https://developer.homey.app/
          2. Navigate to your Homey → Devices → Add via REST API (if supported
             by the driver), OR use the Homey App to re-pair the physical device
             and then apply the backup JSON to restore virtual settings/state.
          3. For advanced scripting: use the Homey Web API (v3) endpoint
               PUT /api/manager/devices/device/<id>
             with the JSON content as the request body.
          4. Alternatively, paste the JSON into a Homey Script (Homeyduino /
             Logic Extra) that calls the Devices API internally.
        ──────────────────────────────────────────────────────────────────────"""),

    "flow": textwrap.dedent("""\
        ── How to re-import a FLOW into Homey ────────────────────────────────
          Option A — Homey Web App (easiest):
            1. Go to https://my.homey.app → Flows
            2. Click the  ⋮  menu → "Import flow"
            3. Paste the JSON from your clipboard (or upload the .json file).

          Option B — Homey Developer Tools:
            1. Open https://developer.homey.app/ → your Homey → Flows
            2. Use the REST endpoint:
                 POST /api/manager/flow/flow
               with the flow JSON as the request body.

          Note: Strip the "id" and "folder" fields from the JSON body when
          creating new flows. If restoring into folders, restore flow_folders
          first and update the "folder" field to the new folder ID.
        ──────────────────────────────────────────────────────────────────────"""),

    "flow_folder": textwrap.dedent("""\
        ── How to re-import FLOW FOLDERS into Homey ──────────────────────────
          Flow folders are restored via the Homey local REST API.
          Restore parent folders before child folders.

          1. To create a new folder:
               POST /api/manager/flow/flowfolder
             Body: {"name": "My Folder", "parent": null}

          2. To update an existing folder (same ID):
               PUT /api/manager/flow/flowfolder/<id>
             with the folder JSON as the request body.

          Tip: Restore folders BEFORE flows so that when you import flows
          you can supply the correct new folder ID in the "folder" field.
          Build an old-UUID → new-UUID mapping as you recreate each folder.
        ──────────────────────────────────────────────────────────────────────"""),

    "zone": textwrap.dedent("""\
        ── How to re-import a ZONE into Homey ────────────────────────────────
          Zones are best restored via the Homey Web API (v3):

          1. Open https://developer.homey.app/ → your Homey → Zones
          2. To create a zone:
               POST /api/manager/zones/zone
             with the zone JSON as the request body.
          3. To update an existing zone (same ID):
               PUT /api/manager/zones/zone/<id>
             with the zone JSON as the request body.

          Tip: restore parent zones before child zones so that parent IDs
          resolve correctly.
        ──────────────────────────────────────────────────────────────────────"""),

    "variable": textwrap.dedent("""\
        ── How to restore a VARIABLE in Homey ────────────────────────────────
          Logic variables are restored via the Homey local REST API:

          1. To create a new Logic variable:
               POST /api/manager/logic/variable
             Body: {"name": "...", "type": "boolean|string|number", "value": ...}

          2. To update an existing variable (same ID):
               PUT /api/manager/logic/variable/<id>
             with the variable JSON as the request body.

          For BLL (Better Logic Library) variables:
            Variables can be set via the BLL app settings page in Homey,
            or via: PUT /api/app/net.i-dev.betterlogic/variable/<name>
        ──────────────────────────────────────────────────────────────────────"""),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_items(directory: pathlib.Path) -> list[dict]:
    """
    Read all *.json files in *directory* and return a list of dicts with:
        name     — item name (from JSON or filename fallback)
        id       — item ID  (from JSON or filename fallback)
        path     — absolute Path to the file
        data     — full parsed JSON dict
    """
    if not directory.exists():
        return []

    items: list[dict] = []
    for filepath in sorted(directory.glob("*.json")):
        try:
            raw = filepath.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] Skipping {filepath.name}: {exc}", file=sys.stderr)
            continue

        # Normalise name / id — Homey uses different keys across resource types
        name = (
            data.get("name")
            or data.get("title")
            or filepath.stem
        )
        item_id = (
            data.get("id")
            or data.get("_id")
            or data.get("ID")
            or filepath.stem
        )

        items.append({
            "name": str(name),
            "id":   str(item_id),
            "path": filepath.resolve(),
            "data": data,
        })

    return items


def _filter_items(items: list[dict], query: str) -> list[dict]:
    """Return items whose name or id contains *query* (case-insensitive)."""
    if not query:
        return items
    q = query.strip().lower()
    return [i for i in items if q in i["name"].lower() or q in i.get("id", "").lower()]


def _copy_to_clipboard(text: str) -> bool:
    """
    Copy *text* to the system clipboard.

    Returns True on success, False if clipboard is unavailable.
    """
    if not _CLIPBOARD_AVAILABLE:
        return False
    try:
        pyperclip.copy(text)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[DEBUG] Clipboard failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Interactive flow
# ---------------------------------------------------------------------------

def _banner() -> None:
    """Print the ASCII art welcome banner."""
    print("\n╔══════════════════════════════════════════════════╗")
    print("║       🏠  Homey Backup — Restore Tool  🏠        ║")
    print("╚══════════════════════════════════════════════════╝\n")


def _choose_category() -> str:
    """Ask the user which backup category to browse.

Returns:
    One of: 'device', 'flow', 'flow_folder', 'zone', or 'variable'.
"""
    answers = inquirer.prompt(
        [
            inquirer.List(
                "category",
                message="What type of item do you want to restore?",
                choices=[
                    ("📦  Device",       "device"),
                    ("⚡  Flow",         "flow"),
                    ("📁  Flow Folder",  "flow_folder"),
                    ("🗂️   Zone",         "zone"),
                    ("🔢  Variable",     "variable"),
                ],
            )
        ],
        theme=GreenPassion(),
        raise_keyboard_interrupt=True,
    )
    if answers is None:
        raise KeyboardInterrupt
    return answers["category"]


def _choose_item(items: list[dict], category: str) -> dict | None:
    """
    Show a searchable list of items and return the one the user selects.
    Returns None if the user asks to go back.
    """
    # Build display labels:  "My Flow Name  (id: abc-123)"
    def label(item: dict) -> str:
        return f"{item['name']:<50}  (id: {item['id']})"

    # Optional filter step
    filter_answer = inquirer.prompt(
        [
            inquirer.Text(
                "query",
                message=f"Filter {category}s by name (leave blank to show all)",
            )
        ],
        theme=GreenPassion(),
        raise_keyboard_interrupt=True,
    )
    if filter_answer is None:
        raise KeyboardInterrupt

    filtered = _filter_items(items, filter_answer["query"])

    if not filtered:
        print(f"\n  [!] No {category}s matched your filter. Try a different term.\n")
        return None

    choices = [(label(i), i) for i in filtered]
    choices.append(("← Back", None))

    select_answer = inquirer.prompt(
        [
            inquirer.List(
                "item",
                message=f"Select a {category} to restore  ({len(filtered)} found)",
                choices=choices,
            )
        ],
        theme=GreenPassion(),
        raise_keyboard_interrupt=True,
    )
    if select_answer is None:
        raise KeyboardInterrupt

    return select_answer["item"]


def _present_item(item: dict, category: str) -> None:
    """Show path, offer clipboard copy, and print import instructions."""
    print()
    print("─" * 60)
    print(f"  ✅  Selected {category}: {item['name']}")
    print(f"      ID   : {item['id']}")
    print(f"      File : {item['path']}")
    print("─" * 60)

    # Always offer clipboard
    content_str = json.dumps(item["data"], indent=2, ensure_ascii=False)

    # Show a truncated JSON preview
    preview_lines = content_str.splitlines()
    max_preview = 20
    preview = "\n".join(f"    {line}" for line in preview_lines[:max_preview])
    if len(preview_lines) > max_preview:
        preview += f"\n    … ({len(preview_lines) - max_preview} more lines)"
    print(f"\n  Preview:\n{preview}\n")

    copy_choices = ["Yes, copy JSON to clipboard", "No thanks"]
    if not _CLIPBOARD_AVAILABLE:
        copy_choices = ["No thanks (pyperclip not installed — pip install pyperclip)"]

    copy_answer = inquirer.prompt(
        [
            inquirer.List(
                "copy",
                message="Copy JSON content to clipboard?",
                choices=copy_choices,
            )
        ],
        theme=GreenPassion(),
        raise_keyboard_interrupt=True,
    )

    if copy_answer and copy_answer["copy"].startswith("Yes"):
        if _copy_to_clipboard(content_str):
            print("\n  📋  JSON copied to clipboard!")
        else:
            print(
                "\n  [WARN] Could not copy to clipboard. "
                "Install pyperclip:  pip install pyperclip",
                file=sys.stderr,
            )

    print()
    # For flows, pick endpoint based on flow_type
    if category == "flow" and item["data"].get("flow_type") == "advanced":
        instructions = IMPORT_INSTRUCTIONS["flow"].replace(
            "POST /api/manager/flow/flow",
            "POST /api/manager/flow/advancedflow",
        ).replace(
            "── How to re-import a FLOW into Homey ────────────────────────────────",
            "── How to re-import an ADVANCED FLOW into Homey ─────────────────────",
        )
        print(instructions)
    else:
        print(IMPORT_INSTRUCTIONS[category])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Interactive restore workflow — browse backups, select items, copy to clipboard."""
    ap = argparse.ArgumentParser(description="Homey Restore — browse backups and copy items to clipboard")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.parse_args()

    _banner()

    while True:
        try:
            category = _choose_category()
        except KeyboardInterrupt:
            print("\n\n  Bye! 👋\n")
            sys.exit(0)

        # Prompt for backup date directory
        date_dirs = list_backup_dates(category)
        if not date_dirs:
            print(f"\n  [!] No {category} backups found in:")
            print(f"      {CATEGORY_DIRS[category].resolve()}/<date-coded-dir>/\n")
            print(f"      Run backup.py first to create the local backups.\n")
            retry = inquirer.prompt(
                [
                    inquirer.List(
                        "action",
                        message="What would you like to do?",
                        choices=["Choose a different type", "Exit"],
                    )
                ],
                theme=GreenPassion(),
                raise_keyboard_interrupt=True,
            )
            if retry is None or retry["action"] == "Exit":
                print("\n  Bye! 👋\n")
                sys.exit(0)
            continue

        date_choices = [(d.name, d) for d in reversed(date_dirs)]
        date_answer = inquirer.prompt(
            [
                inquirer.List(
                    "date_dir",
                    message=f"Select backup date for {category}s:",
                    choices=date_choices,
                )
            ],
            theme=GreenPassion(),
            raise_keyboard_interrupt=True,
        )
        if date_answer is None:
            print("\n  Bye! 👋\n")
            sys.exit(0)
        directory = date_answer["date_dir"]
        items = _load_items(directory)

        if not items:
            print(
                f"\n  [!] No {category}s found in backup: {directory}\n"
                f"      Run backup.py first to create the local backups.\n"
            )
            continue

        print(f"\n  Found {len(items)} {category}(s) in backup {directory.name}.\n")

        try:
            selected = _choose_item(items, category)
        except KeyboardInterrupt:
            print("\n\n  Bye! 👋\n")
            sys.exit(0)

        if selected is None:
            # User hit "Back" — restart the loop
            continue

        try:
            _present_item(selected, category)
        except KeyboardInterrupt:
            print("\n\n  Bye! 👋\n")
            sys.exit(0)

        # Ask whether to restore another item
        again = inquirer.prompt(
            [
                inquirer.List(
                    "again",
                    message="What would you like to do next?",
                    choices=["Restore another item", "Exit"],
                )
            ],
            theme=GreenPassion(),
            raise_keyboard_interrupt=True,
        )
        if again is None or again["again"] == "Exit":
            print("\n  Bye! 👋\n")
            sys.exit(0)


if __name__ == "__main__":
    main()
