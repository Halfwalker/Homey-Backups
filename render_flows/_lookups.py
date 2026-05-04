"""Backup-directory scanners that build UUID → human-name lookup tables.

When ``render_flow`` needs to show a device name, zone name, or variable
name it cannot get that information from the flow JSON alone — it needs to
cross-reference the backup artefacts that live alongside the flow files.
The functions here scan those artefact directories and return plain ``dict``
objects that the renderer can query by UUID.

Leaf node: imports only from the Python stdlib (``json``, ``re``,
``pathlib``).  No other module in this package imports from here except
``_renderers`` and ``_cli``.
"""

# TODO: move _UUID_RE, _stem_uuid, _build_variable_lookup,
#       _build_device_lookup, _build_cap_titles, _build_zone_lookup,
#       _build_folder_lookup, _auto_discover_sibling,
#       _build_trigger_name_map from homey_flow_svg.py
