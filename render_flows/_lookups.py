"""Backup-directory scanners that build UUID → human-name lookup tables.

When the renderer needs to show a device name, zone name, or variable name
it cannot get that information from the flow JSON alone — it must
cross-reference the backup artefacts that live in sibling directories
alongside the flow files (``devices/``, ``zones/``, ``variables/``, etc.).

The functions here scan those artefact directories and return plain ``dict``
objects that the renderer can query by UUID.  All file I/O is done eagerly at
startup rather than lazily so that the render loop itself stays side-effect-free.

Leaf node: imports only from the Python stdlib (``json``, ``re``, ``pathlib``).
No module in this package imports from ``_lookups`` except ``_renderers`` and
``_cli``.
"""

from __future__ import annotations

import json
import re as _re
from pathlib import Path

# ─── UUID helpers ────────────────────────────────────────────────────

# Compiled once at module load.  Homey uses standard RFC-4122 UUIDs as device,
# zone, variable, and flow IDs.  Backup filenames often include them as a suffix
# so we can extract them to build the lookup tables.
_UUID_RE = _re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _stem_uuid(stem: str) -> str | None:
    """Extract a UUID from a filename stem (e.g. ``'my-device-<uuid>'``).

    Returns the UUID string on a match, or ``None`` if the stem contains no
    UUID.  Used by the lookup builders to index devices and zones whose JSON
    filenames follow Homey's ``<slug>-<uuid>.json`` convention.
    """
    m = _UUID_RE.search(stem)
    return m.group(0) if m else None


# ─── Backup directory scanners ───────────────────────────────────────


def _build_variable_lookup(variables_dir: Path) -> dict[str, str]:
    """Scan *variables_dir* for backup JSON files; return ``uuid → name``.

    Covers both Homey Logic variables (keyed by UUID) and BetterLogic (BLL)
    variables (keyed by their string ID).  Returns an empty dict if the
    directory does not exist or contains no parseable files.
    """
    lookup: dict[str, str] = {}
    if not variables_dir or not variables_dir.is_dir():
        return lookup

    for fpath in variables_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        var_id = data.get("id") or data.get("_id") or _stem_uuid(fpath.stem)
        if var_id:
            lookup[var_id] = name
    return lookup


def _build_device_lookup(devices_dir: Path) -> dict[str, str]:
    """Scan *devices_dir* for ``*-<uuid>.json`` files; return ``uuid → name``.

    Inserts each device under two keys so callers can look up by plain UUID
    *or* by the full Homey URI ``homey:device:<uuid>``:

    .. code-block:: python

        {"550e8400-…": "Lounge Lamp", "homey:device:550e8400-…": "Lounge Lamp"}

    Returns an empty dict if the directory does not exist or has no matches.
    """
    lookup: dict[str, str] = {}
    if not devices_dir or not devices_dir.is_dir():
        return lookup

    for fpath in devices_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        # ID may be in the filename suffix (<slug>-<uuid>.json) or in the JSON
        device_id = (
            data.get("id") or data.get("_id")
            # fallback: extract UUID from filename stem (<slug>-<uuid>.json)
            or _stem_uuid(fpath.stem)
        )
        if device_id:
            lookup[device_id] = name
            lookup[f"homey:device:{device_id}"] = name

    return lookup


def _build_cap_titles(devices_dir: "Path | None") -> "dict[str, dict[str, tuple[str, str]]]":
    """Scan *devices_dir*; return ``{device_uuid: {cap_id: (title, unit)}}``.

    Used by ``_build_trigger_name_map`` to produce human-readable capability
    labels such as ``"*Snow (mm)"`` for cross-card trigger references.
    """
    result: dict[str, dict[str, tuple[str, str]]] = {}
    if not devices_dir or not devices_dir.is_dir():
        return result
    for fpath in devices_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        device_id = data.get("id") or data.get("_id") or ""
        if not device_id:
            continue
        caps_obj = data.get("capabilitiesObj") or {}
        cap_map: dict[str, tuple[str, str]] = {}
        for cap_id, cap_info in caps_obj.items():
            if isinstance(cap_info, dict):
                title = cap_info.get("title", "")
                units = cap_info.get("units") or ""
                if title:
                    cap_map[cap_id] = (title, units)
        if cap_map:
            result[device_id] = cap_map
    return result


def _build_zone_lookup(zones_dir: Path) -> dict[str, str]:
    """Scan *zones_dir* for backup JSON files; return ``uuid → zone_name``.

    Inserts each zone under both its plain UUID and the full Homey URI
    ``homey:zone:<uuid>`` so callers can use either form.
    """
    lookup: dict[str, str] = {}
    if not zones_dir or not zones_dir.is_dir():
        return lookup
    for fpath in zones_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or data.get("title") or ""
        if not name:
            continue
        zone_id = (
            data.get("id") or data.get("_id")
            or _stem_uuid(fpath.stem)
        )
        if zone_id:
            lookup[zone_id] = name
            lookup[f"homey:zone:{zone_id}"] = name
    return lookup


def _build_folder_lookup(flow_folders_dir: Path) -> dict[str, str]:
    """Scan *flow_folders_dir* for backup JSON files; return ``uuid → folder_name``.

    Flow folders are optional in Homey — not all installations use them.
    Returns an empty dict when the directory is absent or empty.
    """
    lookup: dict[str, str] = {}
    if not flow_folders_dir or not flow_folders_dir.is_dir():
        return lookup
    for fpath in flow_folders_dir.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("name") or ""
        folder_id = data.get("id") or data.get("_id") or _stem_uuid(fpath.stem)
        if folder_id and name:
            lookup[folder_id] = name
    return lookup


def _auto_discover_sibling(inputs: list[str], sibling_name: str) -> "Path | None":
    """Auto-discover a sibling backup directory from a list of flow file paths.

    Given flow files at ``Backups/TIMESTAMP/flows/*.json``, returns
    ``Backups/TIMESTAMP/<sibling_name>/`` if that directory exists, else ``None``.

    This allows ``main()`` to auto-resolve ``--devices-dir``, ``--zones-dir``,
    ``--variables-dir``, and the flow_folders directory from the input file
    paths when the user does not supply those flags explicitly.  The heuristic
    relies on Homey Backups' directory layout where all backup categories sit
    as siblings under the same timestamp directory.
    """
    for input_path in inputs:
        parent = Path(input_path).parent
        if parent.name == "flows" and "_" in parent.parent.name:
            candidate = parent.parent / sibling_name
            if candidate.exists():
                return candidate
    return None


def _build_trigger_name_map(
    cards: dict[str, dict],
    zone_lookup: dict[str, str] | None = None,
    device_lookup: dict[str, str] | None = None,
    cap_titles: "dict[str, dict[str, tuple[str, str]]] | None" = None,
) -> "tuple[dict[str, str], dict[str, str]]":
    """Map trigger card_id → resolved entity name and build a capability ref map.

    Returns a 2-tuple ``(trigger_name_map, trigger_cap_map)``:

    - ``trigger_name_map``:  ``{card_uuid: device_or_zone_name}``
    - ``trigger_cap_map``:   ``{card_uuid::cap_id: "*Title (unit)"}``

    The capability map is used by ``_resolve_trigger_refs`` in ``_label_parser``
    to expand ``[[trigger::CARD_ID::cap_id]]`` tokens into readable labels like
    ``"*Snow (mm)"`` rather than raw capability IDs.
    """
    result: dict[str, str] = {}
    cap_map: dict[str, str] = {}
    for cid, card in cards.items():
        if card.get("type") != "trigger":
            continue
        card_id_str = card.get("id", "")
        name = ""
        device_uuid = ""
        if card_id_str.startswith("homey:zone:"):
            parts = card_id_str.split(":")
            if len(parts) >= 4:
                name = (zone_lookup or {}).get(parts[2], "")
        elif card_id_str.startswith("homey:device:"):
            parts = card_id_str.split(":")
            if len(parts) >= 4:
                device_uuid = parts[2]
                name = (device_lookup or {}).get(device_uuid, "")
        if not name:
            owner_uri = card.get("ownerUri") or ""
            if owner_uri.startswith("homey:zone:"):
                name = (zone_lookup or {}).get(owner_uri.split(":")[-1], "")
            elif owner_uri.startswith("homey:device:"):
                device_uuid = owner_uri.split(":")[-1]
                name = (device_lookup or {}).get(device_uuid, "")
        if name:
            result[cid] = name
        # Build capability map: "card_uuid::cap_id" → "*Title (unit)"
        if device_uuid and cap_titles:
            dev_caps = cap_titles.get(device_uuid)
            if dev_caps:
                for cap_id, (title, unit) in dev_caps.items():
                    label = f"*{title} ({unit})" if unit else f"*{title}"
                    cap_map[f"{cid}::{cap_id}"] = label
    return result, cap_map
