# LCS Field Tech PWA — Phase 4 Build

Offline-first technician app implementing the chained-logic time tracking
system from *Field Service Time-Tracking Restructure*, plus job review,
customer/internal notes, and photo capture. Matches the roadmap's Phase 4
spec (`/tech` route, React/Vite, Workbox, IndexedDB via `idb`).

## What's in this build

| Concern | File(s) |
|---|---|
| Chained-logic time tracking state machine | `src/state/timeTrackingMachine.js` |
| Offline storage (jobs cache, day log, notes, photos, outbox) | `src/db/offlineStore.js` |
| Sync engine (drains outbox when back online) | `src/db/sync.js` |
| Frappe REST client | `src/api/client.js` |
| Today's Jobs screen | `src/components/JobList.jsx` |
| Job Detail (notes, photos, time tracker) | `src/components/JobDetail.jsx` |
| Clock buttons + exception handling | `src/components/TimeTracker.jsx`, `ClockCorrectionModal.jsx` |
| Customer/internal notes editor | `src/components/NotesEditor.jsx` |
| Photo capture (up to 10/job) | `src/components/PhotoUpload.jsx` |
| Service worker (app-shell offline boot) | `src/sw.js` (built via vite-plugin-pwa) |
| Server: DocTypes | `server/field_service_management/doctype/*` |
| Server: notes fields fixture | `server/fixtures/custom_field_tech_pwa.json` |
| Server: whitelisted API | `server/field_service_management/api/tech_pwa.py` |
| Server: route controller | `server/www/tech.py`, `server/www/tech.html` |

## The time tracking logic, in one place

Everything from Sections 1.1–1.5 of the proposal is encoded as pure
functions in `timeTrackingMachine.js` — no UI or network code in there,
so it's independently testable and it's the one place to check when a
payroll question comes up ("why did this day compute as 10h + 40m
lunch?"). The device runs this machine as the source of truth while
offline; `submit_time_action` in `tech_pwa.py` reconciles the same
actions into `LCS Tech Day Log` once synced.

Handled directly in the state machine:
- Start of day via Clock In (light) or Start Truck Inspection (heavy)
- Prep → Travel → Onsite/Shop chaining, with Lunch as a pause inside the
  active segment rather than its own segment
- **Point-of-Action Override** — clocking out with no matching clock-in
  pops the correction modal, flags the record, and requires a second tap
  to actually close the job
- **Sequential Clock-In Lock** — can't arrive at a new job/shop while a
  previous one is still open; same correction flow
- End-of-day rule: paid travel home vs. unpaid commute after returning
  to the shop, driven by *which* segment is open when End of Day is tapped
- `classifyOvertime()` applies the 8h/10h/12h thresholds per schedule

## What's genuinely new vs. the roadmap's Phase 4 sketch

The original Phase 4 sketch didn't call out customer/internal notes as a
distinct fields — I added them as two separate fields on Service
Appointment (`customer_notes`, `internal_notes`) rather than one, since
you were clear these are different audiences: one prints on the service
report, the other never leaves the office. Enforcing that split lives in
the fixture + `update_notes` API, not just the UI, so a future
"email/print service report" build can't accidentally leak internal
notes by trusting the client.

## Deployment — exact steps for your repo

Your repo root (`Field_Service_Management/`) is the `beveren_fsm` app itself;
the Python package is `beveren_fsm/beveren_fsm/`, and your module folder
inside that is `field_service_management/`. Everything below assumes that
layout.

### 1. Server-side files

Copy from this zip's `server/` folder into your repo:

```
server/field_service_management/doctype/*         → beveren_fsm/beveren_fsm/field_service_management/doctype/
server/field_service_management/api/*              → beveren_fsm/beveren_fsm/field_service_management/api/
server/fixtures/custom_field_tech_pwa.json          → beveren_fsm/beveren_fsm/fixtures/
server/www/tech.py                                  → beveren_fsm/beveren_fsm/www/tech.py
server/www/tech.html                                → beveren_fsm/beveren_fsm/www/tech.html
```

(`doctype/__init__.py` and `api/__init__.py` are already in the zip —
don't skip them, Frappe needs them to import the new modules. If your
`field_service_management/api/` folder doesn't exist yet, this creates it;
if it already exists with other files, just merge `tech_pwa.py` and
`__init__.py` in alongside them.)

### 2. Register the fixture and confirm module name

Add to `hooks.py` (merge into your existing `fixtures` list — don't
replace it):

```python
fixtures = [
    # ...your existing entries...
    {"dt": "Custom Field", "filters": [["name", "like", "Service Appointment-%notes"]]},
]
```

The three new DocType JSONs have `"module": "Field Service Management"` —
that has to exactly match your Module Def name in Desk (**Setup → Module
Def**, or check any existing custom doctype's `module` field to confirm
the spelling). If your module is actually named something else, tell me
and I'll fix the JSONs before you deploy — a mismatched module name is
the single most common reason a fixture install silently fails.

### 3. Commit and deploy — your normal pipeline

VSCodium → review the new files → GitHub Desktop commit/push to `develop`
→ Frappe Cloud Deploy → **Trigger Migration**. The migration is what
actually creates the three new DocTypes and imports the Custom Field
fixture — nothing happens until you trigger it.

### 4. Verify in Desk after migration

- **Setup → DocType** — confirm `LCS Tech Day Log`, `LCS Tech Day Log
  Segment`, and `LCS Appointment Photo` all appear.
- Open a **Service Appointment** and confirm `Customer Notes` /
  `Internal Notes` fields showed up (Customize Form if they're not
  visible in the current tab layout).

### 5. Role Permissions Manager (can't be scripted — same as every other phase)

Go to **Search → Role Permissions Manager** and grant:
- `Field Service User` — read/write on `LCS Tech Day Log`, `LCS
  Appointment Photo`
- `Field Service Manager` — read + report on both, for payroll review

### 6. Build the frontend

The `src/`, `public/`, `index.html`, `vite.config.js`, `package.json` in
this zip are a standalone Vite project — put them somewhere alongside
`schedule/` in your repo (e.g. a new `tech/` folder at the repo root,
parallel to `schedule/`). Then:

```bash
cd tech
yarn install
yarn build
```

This produces `dist/tech.js`, `dist/tech.css`, `dist/sw.js`,
`dist/manifest.json`, and `dist/icons/*` (once you've added icons — see
below). Filenames are pinned (not hashed) on purpose, so `tech.html`
never needs updating after a rebuild.

### 7. Place the build output

This is the one step that differs from `/schedule`, because a service
worker's scope defaults to the folder it's served from, and `start_url:
/tech` needs `sw.js` reachable at exactly `/tech/sw.js` — not
`/assets/.../sw.js`. So the JS/CSS bundle and the shell/manifest/service
worker are committed to two different places:

```
dist/tech.js, dist/tech.css       → beveren_fsm/beveren_fsm/public/tech/
dist/sw.js                        → beveren_fsm/beveren_fsm/www/tech/sw.js
dist/manifest.json                → beveren_fsm/beveren_fsm/www/tech/manifest.json
dist/icons/*                      → beveren_fsm/beveren_fsm/www/tech/icons/
```

Anything under an app's `public/` folder is served at
`/assets/<app_name>/...` by Frappe automatically. Anything under `www/`
is served at the matching URL directly — that's why `sw.js` and
`manifest.json` go there instead: `www/tech/sw.js` → `/tech/sw.js`.

Commit all of that, push, deploy, migrate — same pipeline as step 3.

### 8. Icons

Neither this zip nor the build produces real icon files. Generate
`icon-192.png`, `icon-512.png`, and `icon-512-maskable.png` from the LCS
mark in navy (`#002050`) and drop them in `tech/public/icons/` **before**
`yarn build`, so they land in `dist/icons/` and get committed in step 7.
Without them, the "Add to Home Screen" install prompt looks broken.

### 9. Test it

Visit `https://lcscales.v.frappe.cloud/tech` while logged in as a
technician with a linked Employee record. Confirm: today's jobs load,
tapping a job shows notes/photos/time tracker, clocking in/out updates
the banner, and (this is the one that's easy to miss) toggle your phone
to airplane mode mid-job and confirm notes/photos/clock actions still
work and the sync pill shows "Offline" — then reconnect and watch it
drain to "Synced."

## Known gaps / next pass

- `submit_time_action` reconciles the happy path faithfully but doesn't
  yet replay lunch pauses or corrections server-side — it trusts the
  device's flagged segments. Worth hardening once real payroll exports
  start running against `LCS Tech Day Log`.
- No Collect Payment / parts consumption yet — that's Phase 5 per the
  roadmap, not touched here.
- Photo deletion isn't in the UI (only add). Add a long-press delete if
  techs need to remove a bad shot before sync.
- `get_my_jobs` currently returns just today's appointments; wire up a
  date picker against the existing `from_date`/`to_date` params for
  "tomorrow's jobs" if that's wanted before the build is signed off.
