# Homey Pro — Recovery Playbook

This guide walks you through restoring your Homey Pro configuration from a Homey_Backups backup after a factory reset. Read it top to bottom before starting — the order of steps matters.

---

## Before You Begin: What Cannot Be Automatically Restored

Be honest with yourself about what this toolchain covers. The following **cannot** be restored from these backups and must be handled manually or accepted as lost:

| Item | Status | Notes |
|---|---|---|
| Flow folder structure | ✅ Backed up | Restore folders before flows; build old→new UUID mapping; flows will be in folders after correct import |
| Homey Insights history | ❌ Not backed up | Sensor data, energy history — permanently lost |
| Third-party app settings | ❌ Not backed up | Unifi Protect config, BLL scripts, etc. — must be reconfigured |
| Energy cost settings | ❌ Not backed up | Electricity tariffs etc. — must be reconfigured |
| Dashboards / home screen | ❌ Not backed up | Layout must be rebuilt manually |
| User accounts & invites | ❌ Not backed up | Re-invite users via the Homey app |
| Zigbee/Z-Wave pairing state | ❌ Cannot be backed up | Physical devices must be re-paired; they receive **new UUIDs** |
| Devices | ⚠️ Partial | Settings are backed up for reference, but devices must be re-paired and will get new UUIDs |
| Flows | ✅ Backed up | Can be re-imported; may need UUID fixes after device re-pairing |
| Zones | ✅ Backed up | Can be re-created via API |
| Logic variables | ✅ Backed up | Can be re-created via API |
| BLL variables | ✅ Backed up | Can be re-created via BLL app settings or API |

> **Tip:** Before a planned factory reset, also run **Homey's own cloud backup** (Homey app → Settings → Backup). This covers some things this toolchain does not.

---

## Pre-Reset Checklist

If you haven't performed the factory reset yet, verify these first:

- [ ] Run `uv run backup.py` and confirm the summary shows the expected item counts
- [ ] Check that `flows/`, `zones/`, `variables/`, `devices/` directories were created with today's timestamp
- [ ] Note your Homey's current IP address (check your router's DHCP table)
- [ ] Copy your Personal Access Token somewhere safe, or note that you'll need to generate a new one after reset
- [ ] Note which third-party apps you have installed (BLL, etc.)
- [ ] Run Homey's cloud backup: Homey app → Settings → Backup → Back up now

---

## The Recovery Playbook

### Step 1 — Connect to your reset Homey

After the factory reset completes and Homey is back online:

1. **Find the new IP address** — check your router's DHCP client table, or use the Homey mobile app (it discovers Homey via mDNS)
2. **Generate a new Personal Access Token:**
   - Homey app → More → Users & Permissions → Add Personal Access Token
   - Name it (e.g. `Backup Script`), grant all permissions
   - **Copy the token immediately** — it is only shown once
3. **Verify connectivity:**
   ```bash
   curl -s -H "Authorization: Bearer atk_your_token" \
     http://192.168.x.x/api/manager/system/system | python3 -m json.tool | head -5
   ```
   You should see a JSON object with `name`, `version`, etc. A `401` means a wrong token; a connection error means wrong IP.

4. **Set your env vars:**
   ```bash
   export HOMEY_API_URL=http://192.168.x.x
   export HOMEY_API_TOKEN=atk_your_token
   ```

---

### Step 2 — Reinstall third-party apps

**Do this before restoring variables.** BLL variables and any other app-managed variables cannot be written until the app is installed.

- Open the Homey app → Apps → search and reinstall each app you use (BLL, etc.)
- Wait for each app to fully initialize before proceeding

---

### Step 3 — Restore Zones

Zones must exist before flows are imported — flow cards reference zone UUIDs directly.

**Check parent/child relationships first:**
```bash
# List zones from backup and look at the "parent" field
ls zones/YYYY-MM-DD_HH-MM/
```
Open a few zone JSON files and look at the `parent` field — restore zones with `"parent": null` (root zones) first, then child zones.

**Create each zone via REST API:**
```bash
curl -X POST "$HOMEY_API_URL/api/manager/zones/zone" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Living Room", "parent": null, "icon": "living_room"}'
```

Or use `restore.py` to browse, copy JSON to clipboard, then paste into developer.homey.app:
```bash
uv run restore.py
# Choose: Zone → select backup date → select zone → copy to clipboard
```

Then at [developer.homey.app](https://developer.homey.app) → your Homey → Zones → use the REST interface to POST.

> **Verify:** All zones appear in the Homey app before proceeding to Step 4.

---

### Step 4 — Restore Variables

**Homey Logic variables:**
```bash
# Create a new variable
curl -X POST "$HOMEY_API_URL/api/manager/logic/variable" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Morning Mode", "type": "boolean", "value": false}'
```

The variable JSON in your backup contains `id`, `name`, `type`, `value`. When **creating**, omit the `id` (Homey assigns a new one). When you need to update by the same ID, use `PUT /api/manager/logic/variable/<id>`.

**BLL variables:**
```bash
# Set a BLL variable by name
curl -X PUT "$HOMEY_API_URL/api/app/net.i-dev.betterlogic/variable/VariableName" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": false}'
```

Or set them via the BLL app settings page in the Homey app.

> **Note:** Logic variable UUIDs will change when re-created. Flows that condition on variables by UUID will need to be checked after import. However, BLL variables are referenced by **name** not UUID, so BLL-based flow conditions survive re-creation cleanly.

---

### Step 5 — Re-pair Physical Devices

This is the most manual and most critical step.

1. Open the Homey app → Devices → Add Device
2. Re-pair each physical device following its pairing procedure
3. After pairing, **record the new UUID** for each device:
   - Open [developer.homey.app](https://developer.homey.app) → your Homey → Devices
   - Find the device and copy its ID
4. Build a mapping table of **old UUID → new UUID**:

   | Device Name | Old UUID (from backup) | New UUID (after re-pair) |
   |---|---|---|
   | Front Door Lock | `ffed5c35-c775-...` | `new-uuid-here` |
   | Kitchen Sensor | `249ec8ef-d92c-...` | `new-uuid-here` |
   | … | … | … |

> **⚠️ This mapping table is critical.** Every flow card that controls or reads a device uses the device's UUID. After re-pairing, the old UUIDs no longer exist on your Homey. You will use this table in Step 7 to fix broken flows.

The device backup JSON files are useful as **reference documents** — they contain the device name, settings, and capability configuration from before the reset. However, you cannot simply POST the backup JSON to restore a device; devices are managed by their app driver and must be physically re-paired.

---

### Step 6 — Restore Flow Folders

Flow folders must be recreated **before** importing flows so you can supply the correct folder ID in each flow's JSON.

**List your backed-up folders:**
```bash
ls flow_folders/YYYY-MM-DD_HH-MM/
```

**Create each folder:**
```bash
curl -X POST "$HOMEY_API_URL/api/manager/flow/flowfolder" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Evening Routines", "parent": null}'
```

The response body will contain the new folder UUID. Build a mapping:

| Folder Name | Old UUID (from backup) | New UUID (from POST response) |
|---|---|---|
| Evening Routines | `f28d0c9c-9276-...` | `new-uuid-here` |
| … | … | … |

Before importing flows (Step 7), update each flow JSON's `"folder"` field from the old UUID to the new UUID — or strip the `"folder"` field and manually drag flows into folders afterward in the Homey web app.

---

### Step 7 — Restore Flows

**Via the Homey web app (easiest, one at a time):**
1. Go to [my.homey.app](https://my.homey.app) → Flows
2. Click the ⋮ menu → *Import flow*
3. Paste the JSON (use `restore.py` to copy it to clipboard)

**Via REST API (bulk):**
```bash
# Normal flow
curl -X POST "$HOMEY_API_URL/api/manager/flow/flow" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @flows/YYYY-MM-DD_HH-MM/my-flow-name-uuid.json

# Advanced flow
curl -X POST "$HOMEY_API_URL/api/manager/flow/advancedflow" \
  -H "Authorization: Bearer $HOMEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @flows/YYYY-MM-DD_HH-MM/my-advanced-flow-uuid.json
```

> **Strip the `id` field** from the JSON body when creating new flows — Homey assigns a new ID. Update the `folder` field using your old→new folder UUID mapping from Step 6 (or strip it entirely to place flows in root and organise manually).

After importing, expect to see flows marked with a **red broken indicator** for any that reference re-paired devices. That is normal and expected — you fix them in Step 8.

---

### Step 8 — Fix Broken Flow References

Open [my.homey.app](https://my.homey.app) → Flows. Broken flows show a red ⚠️ indicator.

For each broken flow:
1. Open it in the editor
2. Find the card(s) with a warning — these reference old device UUIDs
3. Using your old → new UUID mapping table from Step 5, identify which device the card should point to
4. Delete the broken card and re-add the correct device/capability
5. Save the flow

> **Cross-flow references:** Some flows call other flows via the `homey:manager:flow:programmatic_trigger` action (common in advanced flows). If the target flow was imported with a new UUID, update the reference in the calling flow.

> **Variable references:** If Logic variable UUIDs changed (Step 4), conditions that test variables by UUID will also be broken. BLL variable conditions (by name) should be fine.

---

### Step 9 — Validate

- Trigger a few key flows manually (via the Homey app or the ▶ button in the web editor) and verify they execute correctly end-to-end
- Check that variables update as expected
- Spot-check the Homey Insights timeline for any execution errors
- Test physical devices (lights, locks, sensors) via the Homey app to confirm pairing succeeded
- Verify scheduled flows (cron triggers) fire at the expected times

---

## Troubleshooting Recovery Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Flow shows red broken indicator | References old device UUID | Step 8: open flow, replace broken device card |
| `curl: 401 Unauthorized` | Token invalid or wrong | Regenerate token in Homey app (Step 1) |
| `curl: Connection refused` | Wrong IP address | Check router DHCP table for Homey's new IP |
| `curl: 404 Not Found` | Wrong API path or resource doesn't exist yet | Verify the endpoint; create the resource first |
| Variable not found in flow condition | Variable not yet restored | Complete Step 4 before importing flows |
| Zone not found in flow | Zone not yet restored | Complete Step 3 first; if UUID changed, re-link in flow |
| BLL variable missing after restore | BLL app not installed yet | Install BLL app (Step 2) before setting BLL variables |
| Flow imported but immediately broken | `id` conflict or bad JSON | Strip `id` from the JSON body before POSTing |
| Flows appear in root instead of folders | Folder UUID changed — `folder` field in flow JSON still has old ID | Update each flow's `folder` field using your old→new folder UUID mapping from Step 6, or drag flows into folders manually in my.homey.app |
| Device has wrong settings after re-pair | Settings not automatically applied | Open device backup JSON for reference; manually re-apply settings in Homey app |

---

## Quick Reference: Restore Order

```
Step 1: Connect + new token
Step 2: Reinstall apps (BLL, etc.)
Step 3: Restore Zones           ← must exist before flows
Step 4: Restore Variables       ← must exist before flows
Step 5: Re-pair Devices         ← record old→new UUID mapping
Step 6: Restore Flow Folders    ← build old→new folder UUID mapping
Step 7: Restore Flows           ← update folder fields using Step 6 mapping
Step 8: Fix broken flow refs    ← use device UUID mapping from Step 5
Step 9: Validate                ← trigger flows, check Insights
```
