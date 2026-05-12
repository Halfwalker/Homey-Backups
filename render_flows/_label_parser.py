"""Label parsing and token resolution for Homey flow cards.

Homey flow card titles use three distinct placeholder formats:

  ``[[key]]``
      Simple arg substitution — resolved from card.args.

  ``[[scheme:...|ref]]``
      URI reference, e.g.:
        ``[[homey:manager:logic|<uuid>]]``     → Logic variable name
        ``[[homey:device:<uuid>|<cap>]]``      → Device capability label
        ``[[homey:zone:<uuid>]]``              → Zone name
        ``[[homey:app:net.i-dev.betterlogic|<name>]]`` → BLL variable

  ``[[trigger::card_id::cap]]``
      Cross-card reference to a trigger card's capability value.

Each format is handled by a dedicated resolver below (_resolve_placeholders,
_resolve_uri_refs, _resolve_trigger_refs).  _parse_label orchestrates all
three to produce a final human-readable label from raw card JSON.

Leaf node: imports only from the Python stdlib (``re``).  No module in this
package imports from ``_label_parser`` except ``_svg_builder`` (for
``_word_wrap``) and ``_renderers`` (for ``_parse_label`` and ``_word_wrap``).
"""

from __future__ import annotations

import re as _re


# ─── Text utilities ──────────────────────────────────────────────────


def _word_wrap(text: str, max_chars: int) -> list[str]:
    """Break *text* into lines of at most *max_chars* characters.

    Splits on whitespace boundaries only — never mid-word.  Returns a list
    with at least one element; an empty or whitespace-only input yields
    ``[""]``.
    """
    text = text.replace("\n", " ").strip()
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


# ─── Token resolvers ─────────────────────────────────────────────────


def _resolve_placeholders(text: str, args: dict | None) -> str:
    """Replace ``[[key]]`` placeholders with their value from *args*.

    Leaves a placeholder untouched when the corresponding key is absent
    from *args* or when *args* is ``None``/empty.
    """
    if not args:
        return text

    def _sub(m: "_re.Match[str]") -> str:
        key = m.group(1)
        val = args.get(key)
        if val is None:
            return m.group(0)  # leave untouched — value not available
        if isinstance(val, dict):
            return str(val.get("name", val))
        return str(val)

    return _re.sub(r"\[\[([^\]|]+)\]\]", _sub, text)


def _resolve_uri_refs(text: str, var_lookup: dict[str, str] | None = None) -> str:
    """Replace Homey URI tokens in *text* with human-readable labels.

    Handles:
    - ``[[homey:manager:logic|<uuid>]]``             → variable name (or short UUID fallback)
    - ``[[homey:app:net.i-dev.betterlogic|<name>]]`` → ``BLL(<name>)``
    - ``[[homey:manager:cron|<type>]]``              → friendly cron label
    - ``[[homey:device:<uuid>|<cap>]]``              → ``*<CapTitle>``
    - All other ``[[homey:...|...]]`` tokens         → left unchanged
    """
    def _sub(m: "_re.Match[str]") -> str:
        full = m.group(0)
        scheme = m.group(1)   # e.g. "homey:manager:logic"
        ref = m.group(2)       # e.g. uuid or variable name

        if scheme == "homey:manager:logic":
            name = (var_lookup or {}).get(ref, "")
            if name:
                return name
            # UUID not in lookup — use first 8 chars so the label is still
            # recognisable without being a full 36-char UUID.
            return f"var:{ref[:8]}"

        if scheme == "homey:app:net.i-dev.betterlogic":
            return f"BLL({ref})"

        if scheme == "homey:manager:cron":
            _cron_labels = {
                "date": "Current date",
                "time": "Current time",
                "sun_state": "Sun state",
            }
            return _cron_labels.get(ref, ref.replace("_", " ").title())

        if scheme.startswith("homey:device:"):
            cap_title = ref
            if cap_title.startswith("measure_"):
                cap_title = cap_title[len("measure_"):]
            cap_title = cap_title.replace("_", " ").title()
            return f"*{cap_title}"

        return full   # leave unrecognized refs untouched

    return _re.sub(
        r"\[\[([^\]|]+)\|([^\]]+)\]\]",
        _sub,
        text,
    )


def _resolve_trigger_refs(
    text: str,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> str:
    """Replace ``[[trigger::CARD_ID::FIELD]]`` tokens with a readable label.

    Resolution order:
    1. If *trigger_cap_map* has an entry for ``CARD_ID::FIELD``, use it.
    2. If *trigger_name_map* has the card's name, return ``<name>:<FIELD>``.
    3. Fall back to ``[<CARD_ID[:8]>:<FIELD>]``.

    Returns *text* unchanged when it contains no trigger tokens or when
    both lookup tables are empty/None.
    """
    if "[[trigger::" not in text:
        return text
    if not trigger_name_map and not trigger_cap_map:
        return text

    def _sub(m: "_re.Match[str]") -> str:
        card_id = m.group(1)
        field = m.group(2)
        if trigger_cap_map:
            cap_label = trigger_cap_map.get(f"{card_id}::{field}")
            if cap_label:
                return cap_label
        name = (trigger_name_map or {}).get(card_id, "")
        if name:
            return f"{name}:{field}"
        return f"[{card_id[:8]}:{field}]"

    return _re.sub(r"\[\[trigger::([^:]+)::([^\]]+)\]\]", _sub, text)


# ─── Label extraction ────────────────────────────────────────────────


def _parse_label(
    card: dict,
    device_lookup: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
    zone_lookup: dict[str, str] | None = None,
    trigger_name_map: dict[str, str] | None = None,
    trigger_cap_map: dict[str, str] | None = None,
) -> str:
    """Extract a human-readable label from card JSON data.

    Supports two formats:
    - Rich (get_advanced_flow): card has a nested ``card`` sub-key with
      ``titleFormatted``, ``title``, ``args``, ``ownerUri``, etc.
    - Compact (list_flows): plain fields directly on the card dict.
    """
    ctype = card["type"]

    if ctype == "note":
        return card.get("value", "")
    if ctype == "start":
        return "Start"
    if ctype == "delay":
        d = (card.get("args") or {}).get("delay", {})
        n = d.get("number", "?")
        m = int(d.get("multiplier", 1))
        unit = {1: "sec", 60: "min", 3600: "hr"}.get(m, f"×{m}s")
        return f"Delay {n} {unit}"
    if ctype == "any":
        return "OR"
    if ctype == "all":
        return "AND"

    # ── Rich format: card has a nested "card" object ─────────────────────
    rich = card.get("card")
    if isinstance(rich, dict):
        args = rich.get("args") or card.get("args") or {}
        # Prefer titleFormatted (may contain [[placeholder]] patterns)
        label = rich.get("titleFormatted") or rich.get("title") or ""
        if label:
            label = _resolve_placeholders(label, args)
            label = _resolve_uri_refs(label, var_lookup)
            label = _resolve_trigger_refs(label, trigger_name_map, trigger_cap_map)

        # Prepend device/owner name when available
        owner_uri = rich.get("ownerUri") or ""
        if owner_uri and device_lookup:
            # ownerUri may be "homey:device:<uuid>" or just a uuid
            uuid_part = owner_uri.split(":")[-1]
            device_name = (
                device_lookup.get(owner_uri)
                or device_lookup.get(uuid_part)
                or ""
            )
            if device_name and device_name not in label:
                label = f"{device_name}  {label}" if label else device_name

        if label:
            return label.strip()

    # ── Compact format fallback ───────────────────────────────────────────
    # ── droptoken: variable-testing conditions (e.g. equal_boolean) ──────
    droptoken = card.get("droptoken")
    if droptoken and isinstance(droptoken, str) and "|" in droptoken:
        dt_scheme, _, dt_ref = droptoken.partition("|")
        if dt_scheme == "homey:manager:logic":
            dt_name = (var_lookup or {}).get(dt_ref, "")
            if dt_name:
                card_id_str = card.get("id", "")
                if "equal_boolean" in card_id_str:
                    return f"{dt_name}  ==  yes"
                # For comparison ops (gt, lt, gte, lte, eq, ne, between), fall through to logic handler
                _cmp_ops = ("lt", "gt", "gte", "lte", "eq", "ne", "between")
                if card_id_str.startswith("homey:manager:logic:") and \
                        card_id_str.rsplit(":", 1)[-1] in _cmp_ops:
                    pass  # handled by logic comparison block below
                else:
                    return dt_name
            # Not in lookup — fall through to ID-based label
        elif "betterlogic" in dt_scheme:
            return dt_ref.replace("_", " ")

    # ── Cron card special labels ─────────────────────────────────────────
    card_id_str = card.get("id", "")

    # ── Logic comparison conditions ───────────────────────────────────────
    _LOGIC_OPS = {"lt": "<", "gt": ">", "gte": "≥", "lte": "≤", "eq": "=", "ne": "≠"}
    if card_id_str.startswith("homey:manager:logic:"):
        op_key = card_id_str.rsplit(":", 1)[-1]
        if op_key in _LOGIC_OPS or op_key == "between":
            # Resolve left-hand side from droptoken
            lhs = "?"
            dt = card.get("droptoken", "")
            if dt and "|" in dt:
                dt_scheme, _, dt_ref = dt.partition("|")
                if "homey:manager:logic" in dt_scheme:
                    lhs = (var_lookup or {}).get(dt_ref, dt_ref[:8])
                else:
                    lhs = dt_ref.replace("_", " ").capitalize()
            # Resolve right-hand side from args.comparator
            a = card.get("args") or {}
            rhs_raw = a.get("comparator", "?")
            if isinstance(rhs_raw, str) and "[[" in rhs_raw:
                rhs = _resolve_uri_refs(rhs_raw, var_lookup)
            else:
                rhs = str(rhs_raw)
            if op_key == "between":
                rhs2_raw = a.get("comparator2", "?")
                if isinstance(rhs2_raw, str) and "[[" in rhs2_raw:
                    rhs2 = _resolve_uri_refs(rhs2_raw, var_lookup)
                else:
                    rhs2 = str(rhs2_raw)
                return f"{lhs} between {rhs} and {rhs2}"
            return f"{lhs} {_LOGIC_OPS[op_key]} {rhs}"
    if "homey:manager:cron:" in card_id_str:
        cron_type = card_id_str.split("homey:manager:cron:")[-1]
        cron_args = card.get("args") or {}
        if cron_type == "sunset":
            before = cron_args.get("before", 0)
            return f"Sun sets in {before} minutes"
        if cron_type == "sunrise":
            before = cron_args.get("before", 0)
            return f"Sun rises in {before} minutes"
        if cron_type == "time_exactly":
            t = cron_args.get("time", "?")
            return f"At {t}"
        if cron_type == "after_sunrise":
            return "After sunrise"
        if cron_type == "after_sunset":
            return "After sunset"
        if cron_type == "before_sunrise":
            before = cron_args.get("before", 0)
            return f"{before} min before sunrise"
        if cron_type == "before_sunset":
            before = cron_args.get("before", 0)
            return f"{before} min before sunset"
        # Unknown cron type — fall through to ID-based label

    # ── Zone trigger ─────────────────────────────────────────────────────
    if card_id_str.startswith("homey:zone:"):
        parts = card_id_str.split(":")
        if len(parts) >= 4:
            zone_uuid = parts[2]
            cap_state = parts[3]
            zone_name = (zone_lookup or {}).get(zone_uuid, zone_uuid[:8])
            cap_args_val = (card.get("args") or {}).get("capability", {})
            cap_name = cap_args_val.get("name", "") if isinstance(cap_args_val, dict) else ""
            state_str = "is false" if cap_state.endswith("_false") else "is true"
            if cap_name:
                return f"{zone_name}: {cap_name} {state_str}"
            return f"{zone_name}: {cap_state.replace('_', ' ')}"

    # ── Aqara FP2 presence zone triggers ─────────────────────────────────
    if ctype == "trigger" and ":alarm_motion_new_true" in card_id_str:
        zone_arg = (card.get("args") or {}).get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            return f"{zone_name} occupied"

    if ctype == "trigger" and ":alarm_motion_new_false" in card_id_str:
        zone_arg = (card.get("args") or {}).get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            return f"{zone_name} unoccupied"

    if ctype == "trigger" and ":motion_inactive_new" in card_id_str:
        a = card.get("args") or {}
        zone_arg = a.get("zone")
        if isinstance(zone_arg, dict):
            zone_name = zone_arg.get("name", "Unknown zone")
            minutes = a.get("minutes", "?")
            timeunit = a.get("timeunit", "seconds")
            return f"{zone_name} is {minutes} {timeunit} inactive"

    # ── BLL variable_contains condition ──────────────────────────────────
    if "net.i-dev.betterlogic:variable_contains" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        raw_val = a.get("value", "?")
        if isinstance(raw_val, str):
            raw_val = _resolve_trigger_refs(raw_val, trigger_name_map, trigger_cap_map)
            raw_val = _resolve_uri_refs(raw_val, var_lookup)
        return f"'{var_name}' contains '{raw_val}'"

    # ── BLL execute_bl_expression action ────────────────────────────────
    if "net.i-dev.betterlogic:execute_bl_expression" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        expr = str(a.get("expression", ""))
        expr = _resolve_trigger_refs(expr, trigger_name_map, trigger_cap_map)
        expr = _resolve_uri_refs(expr, var_lookup)
        return f"Set {var_name} to {expr}"

    # ── Notification / Timeline action ───────────────────────────────────
    if "homey:manager:notifications:create_notification" in card_id_str:
        a = card.get("args") or {}
        text_val = str(a.get("text", ""))
        text_val = _resolve_trigger_refs(text_val, trigger_name_map, trigger_cap_map)
        text_val = _resolve_uri_refs(text_val, var_lookup)
        return text_val

    # ── Mobile push notification action ──────────────────────────────────
    if "homey:manager:mobile:" in card_id_str and "push" in card_id_str:
        a = card.get("args") or {}
        user_dict = a.get("user")
        user_name = user_dict.get("name", "") if isinstance(user_dict, dict) else ""

        # push_image: resolve device from droptoken
        if "push_image" in card_id_str:
            dt = card.get("droptoken", "")
            img_source = ""
            if dt and "|" in dt:
                dt_scheme, _, dt_ref = dt.partition("|")
                if dt_scheme.startswith("homey:device:") and device_lookup:
                    dev_uuid = dt_scheme.split(":")[2]
                    img_source = (
                        device_lookup.get(dev_uuid)
                        or device_lookup.get(dt_scheme)
                        or f"device:{dev_uuid[:8]}"
                    )
                if not img_source:
                    img_source = dt_ref.replace("-", " ").replace("_", " ")
            target = f"to {user_name}" if user_name else ""
            return f"Send image {img_source} {target}".strip() if img_source else f"Push image {target}".strip()

        text_val = str(a.get("text", ""))
        text_val = _resolve_trigger_refs(text_val, trigger_name_map, trigger_cap_map)
        text_val = _resolve_uri_refs(text_val, var_lookup)
        if user_name:
            return f"→ {user_name}: {text_val}" if text_val else f"→ {user_name}"
        return text_val or "Push notification"

    # ── Logic variable-set actions ────────────────────────────────────────
    if "homey:manager:logic:variable_set" in card_id_str:
        a = card.get("args") or {}
        var_dict = a.get("variable")
        var_name = var_dict.get("name", "?") if isinstance(var_dict, dict) else str(var_dict or "?")
        value = str(a.get("value", ""))
        value = _resolve_uri_refs(value, var_lookup)
        # Strip {{...}} math-expression wrapper
        if value.startswith("{{") and value.endswith("}}"):
            value = value[2:-2]
        return f"{var_name} = {value}"

    card_id = card.get("id") or ""
    parts = card_id.split(":")
    capability = parts[-1] if parts else "unknown"
    capability = capability.replace("_", " ").title()

    # Prepend device/owner name when available
    owner_uri = card.get("ownerUri") or ""
    device_name = ""
    if device_lookup:
        if owner_uri:
            uuid_part = owner_uri.split(":")[-1]
            device_name = (
                device_lookup.get(owner_uri)
                or device_lookup.get(uuid_part)
                or ""
            )
        # Fallback: extract device UUID from card ID (homey:device:<uuid>:<cap>)
        if not device_name and card_id.startswith("homey:device:") and len(parts) >= 4:
            dev_uuid = parts[2]
            device_name = (
                device_lookup.get(dev_uuid)
                or device_lookup.get(f"homey:device:{dev_uuid}")
                or ""
            )
    if device_name and device_name not in capability:
        capability = f"{device_name}  {capability}"

    args = card.get("args")
    if args and isinstance(args, dict):
        snippets: list[str] = []

        # Combine duration + unit into one snippet when both are present
        if "duration" in args and "unit" in args:
            dur_val = str(args['duration'])
            if "[[" in dur_val:
                dur_val = _resolve_uri_refs(dur_val, var_lookup)
                dur_val = _resolve_trigger_refs(dur_val, trigger_name_map, trigger_cap_map)
            snippets.append(f"{dur_val} {args['unit']}")
            remaining = [(k, v) for k, v in args.items() if k not in ("duration", "unit")]
        else:
            remaining = list(args.items())

        for k, v in remaining[:3]:   # allow up to 3 remaining args
            if isinstance(v, dict) and "name" in v:
                snippets.append(str(v["name"]))
            elif isinstance(v, str) and v.startswith("[["):
                resolved = _resolve_uri_refs(v, var_lookup)
                resolved = _resolve_trigger_refs(resolved, trigger_name_map, trigger_cap_map)
                snippets.append(resolved)
            elif not isinstance(v, (dict, list)):
                val_str = str(v)
                if "[[" in val_str:
                    val_str = _resolve_uri_refs(val_str, var_lookup)
                    val_str = _resolve_trigger_refs(val_str, trigger_name_map, trigger_cap_map)
                snippets.append(val_str)

        if snippets:
            capability += f"  ({', '.join(snippets)})"

    return capability
