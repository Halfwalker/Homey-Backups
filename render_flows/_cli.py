"""Command-line interface for render_flows.

``main()`` lives here rather than in ``__main__.py`` so that it can be
imported and re-exported by ``__init__.py`` without the risks that arise
when a package's ``__init__`` imports from its own ``__main__`` module
(Python's import machinery treats ``__main__`` specially when a package is
invoked with ``python -m``).

``__main__.py`` is a three-line wrapper that calls ``main()`` from here.
"""

import argparse
import json
import sys
from pathlib import Path

from render_flows._constants import __version__
from render_flows._lookups import (
    _auto_discover_sibling,
    _build_cap_titles,
    _build_device_lookup,
    _build_folder_lookup,
    _build_variable_lookup,
    _build_zone_lookup,
)
from render_flows._renderers import render_flow


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render Homey flow JSON files (standard and advanced) as SVG/PNG diagrams",
        epilog=(
            "Examples:\n"
            "  python -m render_flows flow.json\n"
            "  python -m render_flows flow.json -o diagram.svg\n"
            "  python -m render_flows flows/*.json -d svg_output/\n"
            "  python -m render_flows flows/*.json -d svg_output/ "
            "--devices-dir devices/2026-04-22_13-52/\n"
            "\n"

        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("inputs", nargs="+", help="Homey flow JSON file(s)")
    ap.add_argument("-o", "--output",
                    help="Output SVG path (single-file mode only)")
    ap.add_argument("-d", "--output-dir",
                    help="Output directory for batch processing")
    ap.add_argument(
        "--devices-dir",
        help=(
            "Directory containing device backup JSON files "
            "(<slug>-<uuid>.json). Used to resolve ownerUri → device name. "
            "Auto-discovers from flow timestamp if not specified."
        ),
    )
    ap.add_argument(
        "--variables-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory containing variable JSON backup files produced by backup.py.\n"
            "Enables resolving [[homey:manager:logic|uuid]] tokens to human names.\n"
            "Example: --variables-dir variables/2026-04-26_12-49/"
        ),
    )
    ap.add_argument(
        "--zones-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory containing zone backup JSON files produced by backup.py. "
            "Enables resolving homey:zone:<uuid> tokens to zone names. "
            "Auto-discovers from flow timestamp if not specified."
        ),
    )
    ap.add_argument(
        "--png",
        action="store_true",
        default=False,
        help="Convert output to PNG instead of SVG (requires cairosvg + libcairo2)",
    )
    ap.add_argument(
        "--filter",
        metavar="TEXT",
        default=None,
        help=(
            "Only render flows whose name contains TEXT (case-insensitive). "
            "Example: --filter kitchen"
        ),
    )
    args = ap.parse_args()

    if args.output and len(args.inputs) > 1:
        print("Error: -o works with a single input only. "
              "Use -d for batch.", file=sys.stderr)
        sys.exit(1)

    # Build device lookup once for all flows
    devices_dir: Path | None = Path(args.devices_dir) if args.devices_dir else None

    # Auto-discover devices directory if not specified
    # Structure: Backups/TIMESTAMP/flows/file.json → Backups/TIMESTAMP/devices/
    if not devices_dir and args.inputs:
        devices_dir = _auto_discover_sibling(args.inputs, "devices")

    device_lookup = _build_device_lookup(devices_dir) if devices_dir else {}
    cap_titles = _build_cap_titles(devices_dir) if devices_dir else {}
    if device_lookup:
        print(f"[INFO] Loaded {len(device_lookup) // 2} device name(s) from {devices_dir}")

    variables_dir: Path | None = Path(args.variables_dir) if args.variables_dir else None

    # Auto-discover variables directory if not specified
    if not variables_dir and args.inputs:
        variables_dir = _auto_discover_sibling(args.inputs, "variables")

    var_lookup = _build_variable_lookup(variables_dir) if variables_dir else {}
    if var_lookup:
        print(f"[INFO] Loaded {len(var_lookup)} variable name(s) from {variables_dir}")

    zones_dir: Path | None = Path(args.zones_dir) if args.zones_dir else None

    # Auto-discover zones directory if not specified
    if not zones_dir and args.inputs:
        zones_dir = _auto_discover_sibling(args.inputs, "zones")

    zone_lookup = _build_zone_lookup(zones_dir) if zones_dir else {}
    if zone_lookup:
        print(f"[INFO] Loaded {len(zone_lookup) // 2} zone name(s) from {zones_dir}")

    # Auto-discover flow_folders directory
    folders_dir: Path | None = (
        _auto_discover_sibling(args.inputs, "flow_folders") if args.inputs else None
    )

    folder_lookup = _build_folder_lookup(folders_dir) if folders_dir else {}
    if folder_lookup:
        print(f"[INFO] Loaded {len(folder_lookup)} folder name(s) from {folders_dir}")

    # ── Consolidated auto-discovery warning ──────────────────────────────
    # Warn only when a dir was NOT supplied explicitly AND auto-discovery
    # also failed to find it (so the user knows names will be unresolved).
    _missing: list[tuple[str, str]] = []
    if not args.devices_dir and not devices_dir:
        _missing.append(("devices", "device names will appear as IDs"))
    if not args.zones_dir and not zones_dir:
        _missing.append(("zones", "zone names will appear as UUIDs"))
    if not args.variables_dir and not variables_dir:
        _missing.append(("variables", "variable references will remain unresolved"))
    if _missing:
        print("Warning: could not auto-discover backup directories for name resolution:",
              file=sys.stderr)
        for _name, _consequence in _missing:
            print(f"  • {_name:<10} → not found ({_consequence})", file=sys.stderr)
        print(
            "Tip: run render_flows.py on files inside flows/YYYY-MM-DD_HH-MM/, or pass\n"
            "     --devices-dir / --zones-dir / --variables-dir explicitly.",
            file=sys.stderr,
        )

    for fpath in args.inputs:
        p = Path(fpath)
        if not p.exists():
            print(f"  ✗ Not found: {fpath}", file=sys.stderr)
            continue

        try:
            flow = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ✗ Bad JSON: {fpath} ({exc})", file=sys.stderr)
            continue

        print(f"  → {flow.get('name', p.stem)}")

        if args.filter and args.filter.lower() not in flow.get("name", "").lower():
            print(f"  ⏭  Skipped (filter): {flow.get('name', p.name)}")
            continue

        if args.output:
            out = args.output
        elif args.output_dir:
            od = Path(args.output_dir)
            od.mkdir(parents=True, exist_ok=True)
            out = str(od / p.with_suffix(".svg").name)
        else:
            out = str(p.with_suffix(".svg"))

        render_flow(
            flow, out,
            device_lookup=device_lookup or None,
            var_lookup=var_lookup or None,
            zone_lookup=zone_lookup or None,
            folder_lookup=folder_lookup or None,
            cap_titles=cap_titles or None,
            to_png=args.png,
        )
