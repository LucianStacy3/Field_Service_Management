# LCS Service Agreement Quote — beveren_fsm Deployment

## File placement

Copy both files into your local `beveren_fsm` clone, then commit and push:

```
beveren_fsm/
└── field_service_management/
    └── www/
        ├── service-agreement-quote.html   ← the page
        └── service-agreement-quote.py     ← the controller
```

**Note:** Frappe maps `www/service-agreement-quote.html` to the route
`/service-agreement-quote` automatically. No `hooks.py` change is needed
for `www/` pages — Frappe discovers them on deploy.

## Deploy steps

1. Copy both files into `beveren_fsm/field_service_management/www/`
2. Commit with a conventional commit message:
   ```
   feat: add service agreement quote web page
   ```
3. Push to `develop` branch
4. In Frappe Cloud dashboard: Deploy → wait for build
5. **No migration needed** — `www/` pages don't touch the database schema
6. Visit `https://lcscales.v.frappe.cloud/service-agreement-quote` to verify

## What the page does

- Collects all fields needed to create an `LCS Service Agreement Quote` record
- Runs entirely inside the Frappe portal (authenticated — redirects guests to login)
- Pre-fills Sales Rep name from `frappe.session.user`
- Saves a Draft `LCS Service Agreement Quote` via `frappe.client.insert`
- Auto-saves to localStorage every 30 seconds as a safety net
- Shows per-visit and extended annual pricing in the customer-facing summary
- Prints a clean customer quote (no internal labor rates or hours)

## Fieldname verification checklist

Before deploying, open the `LCS Service Agreement Quote` DocType in ERPNext
and confirm these fieldnames match exactly. The page uses them in the
`frappe.client.insert` call:

| Field label                    | Fieldname used in page    | Verify |
|-------------------------------|---------------------------|--------|
| Status                        | `status`                  | ☐      |
| Quote Date                    | `quote_date`              | ☐      |
| Valid Until                   | `valid_until`             | ☐      |
| Sales Rep                     | `sales_rep`               | ☐      |
| Customer / Company Name        | `customer_name`           | ☐      |
| Service Address                | `service_address`         | ☐      |
| City, State, ZIP               | `city_state_zip`          | ☐      |
| Contact Name                   | `contact_name`            | ☐      |
| Phone                          | `contact_phone`           | ☐      |
| Email                          | `contact_email`           | ☐      |
| Alternate Contact              | `alt_contact`             | ☐      |
| Alt Phone                      | `alt_phone`               | ☐      |
| Capacity Class                 | `capacity_class`          | ☐      |
| Schedule Type                  | `schedule_type`           | ☐      |
| Interval (Months)              | `interval_months`         | ☐      |
| Equipment (child table)        | `equipment_items`         | ☐      |
| Price per Service Visit        | `price_per_service`       | ☐      |
| Regular Hours rate             | `rate_regular`            | ☐      |
| Overtime Hours rate            | `rate_overtime`           | ☐      |
| Sundays & Holidays rate        | `rate_holiday`            | ☐      |
| Rates Valid Until              | `rates_valid_until`       | ☐      |
| Est. Man Hours per Visit       | `est_man_hours`           | ☐      |
| Plan Service (checkbox)        | `plan_service`            | ☐      |
| Terms                          | `terms`                   | ☐      |
| Internal Notes                 | `internal_notes`          | ☐      |

## Child table fieldnames (LCS Service Agreement Quote Item)

Open the child DocType `LCS Service Agreement Quote Item` and confirm:

| Column label       | Fieldname used in page | Verify |
|-------------------|------------------------|--------|
| Location / Dept   | `location_dept`        | ☐      |
| Scale Type        | `scale_type`           | ☐      |
| Difficulty        | `difficulty`           | ☐      |
| Make              | `make`                 | ☐      |
| Model             | `model`                | ☐      |
| Qty               | `qty`                  | ☐      |
| Unit Price        | `unit_price`           | ☐      |
| Extended Price    | `extended_price`       | ☐      |

**Serial number note:** `serial_no` was not visible as a child table column
in the screenshots. The page appends serial numbers to `internal_notes`
as a text block. If you add `serial_no` to the child table, update the
`equipment_items` mapping in `saveToErpNext()` to include it directly.

## Switching MLU tasks to live data

The page currently uses an embedded `MLU_TASKS` array. Once deployed inside
Frappe, replace the embedded data with a live fetch at the top of the
`<script>` block:

```javascript
frappe.ready(function() {
  frappe.call({
    method: 'frappe.client.get_list',
    args: {
      doctype: 'MLU Labor Standard',
      fields: ['section', 'subsection', 'task_name', 'base_hours'],
      limit_page_length: 500,
      order_by: 'section asc, subsection asc'
    },
    callback(r) {
      if (r.message) {
        // Transform to MLU_TASKS format
        MLU_TASKS = r.message.map(row => ({
          sec:   row.section,
          task:  row.task_name,
          hrs:   row.base_hours,
          mode:  row.task_name.toLowerCase().includes('pm') ||
                 row.task_name.toLowerCase().includes('clean') ? 'pm' : 'cal',
          match: [row.section.replace(/^\d+ - /, '')]
        }));
      }
      addUnit(); addUnit(); addUnit();
      checkRestore();
      calc();
    }
  });
});
```

Move the `addUnit()` / `checkRestore()` / `calc()` calls from the IIFE
into this callback so the MLU data is ready before the form renders.

## Permissions

The page requires login. `service-agreement-quote.py` redirects guests to
`/login`. In production, ensure the `Sales User` or `LCS Sales` role has
`read` permission on:
- `LCS Service Agreement Quote`
- `LCS Service Agreement Quote Item`
- `MLU Labor Standard`

And `create` permission on:
- `LCS Service Agreement Quote`
