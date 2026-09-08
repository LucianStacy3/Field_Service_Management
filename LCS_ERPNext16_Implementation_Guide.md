# Left Coast Scales — ERPNext 16 Implementation & Development Guide

### `beveren_fsm` on Frappe Cloud | `develop` branch | `lcscales.v.frappe.cloud`

> **This guide is LCS-specific.** It reflects our actual environment, stack, and deployment patterns. Keep it updated as you build.

---

## Table of Contents

1. [Implementation Architecture](#1-implementation-architecture)
2. [The Custom Application Paradigm](#2-the-custom-application-paradigm)
3. [Deployment Pipeline](#3-deployment-pipeline)
4. [System Modification: Extending Core ERPNext](#4-system-modification-extending-core-erpnext)
5. [Webpages, Portals, and SPAs](#5-webpages-portals-and-spas)
6. [Security and Performance Best Practices](#6-security-and-performance-best-practices)
7. [Python & JavaScript Coding Standards](#7-python--javascript-coding-standards)
8. [LCS Brand System & Design](#8-lcs-brand-system--design)
9. [ERPNext Desk Theming](#9-erpnext-desk-theming)
10. [Implementation Lessons & Gotchas](#10-implementation-lessons--gotchas)
11. [Phase Planning & Roadmap](#11-phase-planning--roadmap)

---

## 1. Implementation Architecture

### 1.1 Our Stack

| Layer | Tool |
|-------|------|
| **ERP Platform** | ERPNext v16 + Frappe v16 |
| **Hosting** | Frappe Cloud (shared bench, PaaS) |
| **Custom App** | `beveren_fsm` — module: `field_service_management` |
| **Repository** | `LeftCoastScales/Field_Service_Management` on GitHub |
| **Active Branch** | `develop` |
| **Production URL** | `lcscales.v.frappe.cloud` |
| **Local IDE** | VSCodium + GitHub Desktop |
| **Frontend SPA** | React / Vite / TypeScript (dispatch board, `/schedule`) |
| **SPA Build Trigger** | GitHub Actions — `build-schedule.yaml` |

### 1.2 What Frappe Cloud Abstracts Away

Frappe Cloud is a managed PaaS. **You have no SSH or shell access** to the production server. There is no direct Nginx config, no Supervisor control, no MariaDB shell. Everything flows through:

- **Git commits → GitHub → Frappe Cloud deploy** for Python, fixtures, and frontend assets
- **Frappe Desk** (Server Scripts, Client Scripts) for logic that doesn't require a deploy
- **Frappe Cloud dashboard** for site management, migration triggers, and deploy logs

### 1.3 Three-Environment Model

```
VSCodium (local)
    │  edit code
    ↓
GitHub Desktop → push to 'develop'
    │
    ↓
GitHub Actions  ← triggers on schedule/src/** changes
    │  builds React SPA, commits dist assets back to develop
    ↓
Frappe Cloud — Deploy beveren_fsm app
    │  pulls develop branch, runs bench migrate
    ↓
lcscales.v.frappe.cloud (production)
```

> **Note:** LCS uses VSCodium locally. Codespaces is not used.

---

## 2. The Custom Application Paradigm

### 2.1 The Cardinal Rule

**Never modify core ERPNext or Frappe files.** Any direct edit to core files is overwritten on the next Frappe Cloud update and will break your instance. Every customization lives inside `beveren_fsm`.

### 2.2 App Directory Structure

```
beveren_fsm/
├── hooks.py                          ← App-wide wiring: fixtures, CSS, events, routes
├── fixtures/                         ← Fixture JSON exports (bench export-fixtures output)
│   ├── custom_field.json
│   ├── property_setter.json
│   └── ...
├── field_service_management/         ← Main module
│   ├── custom/                       ← sync_on_migrate dict-format files ONLY
│   │   └── custom_field.json         ← Dict format (not list format)
│   ├── doctype/                      ← Custom DocType definitions
│   │   └── lcs_vehicle/
│   │       ├── lcs_vehicle.json
│   │       ├── lcs_vehicle.py
│   │       └── lcs_vehicle.js
│   ├── api/                          ← @frappe.whitelist() Python endpoints
│   └── www/                          ← Public-facing web pages
├── public/
│   └── css/
│       └── lcs_theme.css             ← LCS brand CSS injected into Desk
└── schedule/                         ← React/Vite/TypeScript dispatch board SPA
    ├── src/
    └── dist/                         ← Built assets (committed by GitHub Actions)
```

**Critical distinction:** 
- `beveren_fsm/fixtures/` — **list-format** fixture JSON (exported via `bench export-fixtures`)
- `field_service_management/custom/` — **dict-format** `sync_on_migrate` customization files only

Do not mix these formats or locations.

### 2.3 DocType Naming

Always prefix custom DocTypes with `LCS` to prevent naming collisions with core ERPNext, third-party apps, and future Frappe updates.

| ❌ Bad | ✅ Good |
|--------|---------|
| `Vehicle` | `LCS Vehicle` |
| `Inspection Report` | `LCS DOT Inspection` |
| `Service Agreement` | `LCS Service Agreement` |

### 2.4 Python Version

ERPNext v16 runs on **Python 3.11 / 3.12**. Write code targeting 3.11 syntax.

---

## 3. Deployment Pipeline

This is the most important section. The deployment path depends on **what type of change** you made.

### 3.1 Decision Matrix

| Change Type | Deploy Method |
|-------------|----------------|
| New/modified DocType JSON or Python | Commit → Push → Frappe Cloud Deploy → **Trigger Migration** |
| New/modified fixture JSON | Commit → Push → Frappe Cloud Deploy → **Trigger Migration** |
| New/modified `hooks.py` | Commit → Push → Frappe Cloud Deploy → **Trigger Migration** |
| CSS file (`lcs_theme.css`) | Commit → Push → Frappe Cloud Deploy (no migration needed) |
| React SPA (`schedule/src/**`) | Touch any `schedule/src/` file → Commit → Push → GitHub Actions runs `build-schedule.yaml` → auto-commits built assets → Frappe Cloud Deploy |
| Server Script | Edit directly in Frappe Desk → Save (no deploy needed) |
| Client Script | Edit directly in Frappe Desk → Save (no deploy needed) |
| Workspace shortcuts / Number Cards | Edit directly in Frappe Desk → Save (no deploy needed) |

### 3.2 Standard Commit → Deploy Cycle

**Step-by-step workflow using VSCodium + GitHub Desktop:**

1. Make changes in VSCodium
2. Run `pre-commit run --all-files` locally and commit any auto-fixes before pushing
3. In GitHub Desktop: stage, write commit message using conventional commits (see §7.3), push to `develop`
4. In Frappe Cloud dashboard: navigate to your bench → Apps → `beveren_fsm` → **Deploy**
5. Wait for the build to complete (watch the deploy log)
6. If the change involves DocTypes, fixtures, or hooks: click **Trigger Migration** on the site
7. Hard refresh the browser (`Ctrl+Shift+R`) and verify

### 3.3 Pre-Commit CI — Known Failure Causes

Your repo has pre-commit hooks that run in GitHub Actions CI. Pushes fail CI if any of the following are present in committed Python files:

| Issue | Fix |
|-------|-----|
| EN dashes (`—`) in string literals | Replace with ASCII hyphen or escaped character |
| F-strings with complex expressions | Simplify or use `.format()` |
| Missing EOF newline | Add a blank line at end of file |
| Multiplication signs (`×`) in strings | Replace with `*` or `x` |

**Always run `pre-commit run --all-files` locally before pushing.** If pre-commit auto-modifies files, stage and commit those changes before pushing again. CI won't pass until the repo is clean.

### 3.4 GitHub Actions — SPA Build

The `build-schedule.yaml` workflow triggers when any file under `schedule/src/**` changes on the `develop` branch. It:

1. Installs Node dependencies
2. Creates a dummy `common_site_config.json` at `/home/runner/work/sites/` (required by the Vite config's Frappe bench path resolver)
3. Runs `vite build`
4. Commits the compiled `schedule/dist/` assets back to `develop` using `git add -f` (bypassing `.gitignore`)

If the SPA isn't updating after a push, check the Actions tab in GitHub for build errors before troubleshooting Frappe Cloud.

---

## 4. System Modification: Extending Core ERPNext

### 4.1 Fixtures — The Right Way

Fixtures carry database records (Custom Fields, Property Setters, Client Scripts, etc.) from your local dev environment into production via Git.

**hooks.py fixture registration:**

```python
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Field Service Management"]]
    },
    {
        "dt": "Property Setter",
        "filters": [["module", "=", "Field Service Management"]]
    },
    {
        "dt": "Client Script",
        "filters": [["module", "=", "Field Service Management"]]
    },
    # DocTypes that are fully owned by this app can be exported without filters:
    {"dt": "LCS Vehicle"},
    {"dt": "LCS Service Agreement"},
]
```

**Export command** (run in your local bench, not Frappe Cloud):

```bash
bench --site dev.localhost export-fixtures
```

This writes JSON files to `beveren_fsm/fixtures/`. Commit them. On the next Frappe Cloud deploy + Trigger Migration, Frappe's `sync_fixtures` runs and upserts every record. Existing records are updated in place; nothing is duplicated.

> **Filter reliability warning:** Filtering by `"module"` works for most DocTypes but is not universal. For Custom Fields added to standard DocTypes (e.g., `Sales Invoice`, `Service Area`), verify the filter actually captures your records by inspecting the exported JSON before committing.

### 4.2 Document Hooks (hooks.py)

Intercept ERPNext document lifecycle events without touching core code:

```python
# beveren_fsm/hooks.py

doc_events = {
    "Sales Invoice": {
        "validate": "beveren_fsm.field_service_management.api.billing.validate_fsm_integration",
        "on_submit": "beveren_fsm.field_service_management.api.billing.push_to_field_service"
    },
    "LCS Service Agreement": {
        "on_submit": "beveren_fsm.field_service_management.api.service_agreement.on_submit_handler"
    }
}
```

### 4.3 CSS Injection (hooks.py)

```python
# CRITICAL: Must be a list with square brackets, not a bare string
app_include_css = ["/assets/beveren_fsm/css/lcs_theme.css"]
```

> **Gotcha:** Using a bare string (`app_include_css = "/assets/..."`) instead of a list silently fails — the CSS does not load. Always use square brackets.

### 4.4 Overriding Standard DocType Classes

For fundamental behavioral changes to core ERPNext classes:

```python
# beveren_fsm/hooks.py
override_doctype_class = {
    "Sales Invoice": "beveren_fsm.overrides.custom_sales_invoice.LCSSalesInvoice"
}

# beveren_fsm/overrides/custom_sales_invoice.py
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class LCSSalesInvoice(SalesInvoice):
    def calculate_taxes_and_totals(self):
        # Inject LCS-specific logic before calling standard method
        super().calculate_taxes_and_totals()
```

### 4.5 Website Routes (SPA Registration)

Register the dispatch board SPA route in `hooks.py`:

```python
website_route_rules = [
    {"from_route": "/schedule/<path:app_path>", "to_route": "schedule"},
]
```

---

## 5. Webpages, Portals, and SPAs

### 5.1 Traditional Web Pages (www/ directory)

Frappe serves files in the `www/` directory directly as portal pages. Ideal for public forms, dashboards, and employee tools that don't need the full Desk UI.

**File structure:**

```
beveren_fsm/field_service_management/www/
├── shortcuts.html          → /shortcuts
├── shortcuts.py            → controller
├── timeclock.html          → /timeclock
├── timeclock-kiosk.html    → /timeclock-kiosk
└── referral-leaderboard.html → /referral-leaderboard
```

**Controller pattern (.py):**

```python
# www/shortcuts.py
import frappe

def get_context(context):
    # Respect RBAC — use get_list, not get_all
    context.shortcuts = frappe.get_list(
        "LCS Shortcut",
        fields=["name", "label", "url", "icon", "roles"],
        order_by="sort_order asc"
    )
    context.no_breadcrumbs = True
    return context
```

**View pattern (.html):**

```html
<!-- www/shortcuts.html -->
{% extends "templates/web.html" %}

{% block page_content %}
<div class="lcs-portal-container">
    {% for shortcut in shortcuts %}
    <a class="lcs-shortcut-card" href="{{ shortcut.url }}">
        <span class="lcs-icon">{{ shortcut.icon }}</span>
        <span class="lcs-label">{{ shortcut.label }}</span>
    </a>
    {% endfor %}
</div>
{% endblock %}
```

Drop a matching `.css` and `.js` file in the same `www/` directory — Frappe auto-injects them on that page only.

### 5.2 React/Vite SPA (Dispatch Board)

The dispatch board at `/schedule` is a full React/Vite/TypeScript SPA living in `beveren_fsm/schedule/`.

**Key patterns:**

- All Frappe data access goes through `frappe.call()` or the REST API, authenticated via session cookie
- The Vite config references a Frappe bench path — GitHub Actions provides a dummy `common_site_config.json` to satisfy this during CI build
- Built assets in `schedule/dist/` are committed to `develop` by GitHub Actions with `git add -f` to bypass `.gitignore`
- Frappe Cloud serves the compiled assets; it does not run Node in production

**API endpoint pattern (Python side):**

```python
# beveren_fsm/field_service_management/api/service_appointment.py
import frappe

@frappe.whitelist()
def get_appointments_for_date(date: str) -> list:
    """Return appointments with technician and resource data for the dispatch board."""
    appointments = frappe.get_list(
        "Service Appointment",
        filters={"appointment_date": date},
        fields=["name", "customer", "service_area", "status"],
    )
    # Build child table data explicitly — field-by-field
    for appt in appointments:
        appt["service_technicians"] = frappe.get_all(
            "Service Technician Item",
            filters={"parent": appt["name"]},
            fields=["technician", "custom_is_crew_leader", "custom_clock_in", "custom_clock_out"]
        )
    return appointments
```

> **Important:** When adding new child table fields, you must manually add them to **both** the `appointment_resources` and `service_technicians` arrays in the API file. Frappe does not automatically include new fields in `get_all()` unless they are explicitly named.

### 5.3 Frappe Web Forms

Web Forms are configured in the Desk (not via code) and render as mobile-responsive portal pages. They write directly to DocType records and support multi-step workflows.

LCS uses Web Forms for:

- DOT morning/evening vehicle inspections (`LCS DOT Inspection`)
- Light vehicle inspection workflows (`LCS Light Vehicle Inspection`)
- Lead referral submissions (public, no login required)

**Web Form configuration tips:**

- Set **"Login Required"** off for public forms (lead referral)
- Use **"Allow Multiple Submissions"** for recurring workflows (vehicle inspections)
- Custom CSS on Web Forms goes in the Web Form's "CSS" field in the Desk — keep it minimal and use LCS CSS variables (see §8)

---

## 6. Security and Performance Best Practices

### 6.1 Whitelisting API Methods

Any Python method called from JavaScript or the REST API must be decorated with `@frappe.whitelist()`:

```python
@frappe.whitelist()
def get_employee_list(department_exclude: list | None = None) -> list:
    filters = {}
    if department_exclude:
        filters["department"] = ["not in", department_exclude]
    return frappe.get_list("Employee", filters=filters, fields=["name", "employee_name"])
```

### 6.2 RBAC — Always Use get_list, Not get_all

```python
# ❌ WRONG — bypasses the user's permissions
frappe.get_all("LCS Service Agreement")

# ✅ CORRECT — enforces role-based access
frappe.get_list("LCS Service Agreement")

# ✅ Acceptable — only in automated background jobs with no user session
frappe.get_all("LCS Service Agreement", ignore_permissions=True)
```

### 6.3 Query Builder Over Raw SQL

```python
# ❌ Never use string concatenation in SQL — SQL injection risk
frappe.db.sql(f"SELECT name FROM `tabLCS Vehicle` WHERE branch = '{branch}'")

# ✅ Safe — use Query Builder
Vehicle = frappe.qb.DocType("LCS Vehicle")
results = (
    frappe.qb.from_(Vehicle)
    .select(Vehicle.name, Vehicle.license_plate)
    .where(Vehicle.branch == branch)
    .run(as_dict=True)
)
```

### 6.4 Background Jobs for Heavy Processing

```python
# For month-end PDF generation, bulk email, etc.
frappe.enqueue(
    "beveren_fsm.field_service_management.api.reports.generate_monthly_certs",
    queue="long",
    month=month,
    branch=branch
)
```

---

## 7. Python & JavaScript Coding Standards

### 7.1 Python Standards

Target Python 3.11/3.12. PEP-8 compliance is enforced by pre-commit hooks — violations block CI.

```python
# Type hints on all API methods
@frappe.whitelist()
def calculate_calibration_variance(expected_value: float, actual_value: float) -> dict:
    variance: float = abs(expected_value - actual_value)
    is_compliant: bool = variance <= 0.05
    return {"variance": variance, "compliant": is_compliant}
```

**Naming conventions:**

| Scope | Convention |
|-------|------------|
| Variables, functions, modules | `snake_case` |
| Class names | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` |
| DocType names | `Title Case with LCS Prefix` |
| Custom fields on standard DocTypes | `custom_` prefix (auto-applied by Frappe) |

### 7.2 JavaScript Standards (Client Scripts & SPA)

- Always use `const` or `let` — never `var`
- Arrow functions for callbacks
- Template literals instead of string concatenation
- In Client Scripts: wrap all logic inside the `frappe.ui.form.on()` callback to avoid polluting global scope

```javascript
// Client Script pattern
frappe.ui.form.on('LCS Service Agreement', {
    refresh(frm) {
        if (frm.doc.status === 'Active') {
            frm.add_custom_button('Renew', () => {
                frappe.call({
                    method: 'beveren_fsm.field_service_management.api.service_agreement.renew',
                    args: { name: frm.doc.name },
                    callback: (r) => frm.reload_doc()
                });
            });
        }
    }
});
```

### 7.3 Conventional Commit Messages

Frappe Cloud deployments are triggered by Git commits. A clean history is critical for tracing what changed across deployments.

| Prefix | Use For |
|--------|---------|
| `feat:` | New DocType, new API endpoint, new page |
| `fix:` | Bug correction |
| `chore:` | Fixture exports, dependency updates |
| `style:` | CSS/theme changes |
| `refactor:` | Code restructuring without behavior change |
| `docs:` | SOP, guide, or README changes |

**Examples:**

```
feat: add LCS Vehicle DocType with 18-vehicle seed fixtures
fix: correct pre-commit EN dash violation in service_appointment.py
chore: export Phase 3C fixture updates for appointment resource columns
style: update lcs_theme.css dark mode sidebar rules
```

---

## 8. LCS Brand System & Design

This section defines the complete LCS visual identity as it applies to ERPNext portals, web forms, HTML tools, and printed documents.

### 8.1 Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| **Navy** | `#002050` | Primary brand color. Headers, navbars, sidebars, section banners, primary buttons |
| **Crimson** | `#900010` | Accent and alert color. Section headings, warning indicators, destructive actions |
| **Steel Blue** | `#004080` | Secondary interactive color. Secondary buttons, links, bordered callouts |
| **Gold** | `#C8A020` | Highlight and emphasis. Badges, crew leader indicators, callout accents |
| **Navy Alt** | `#1A3A7A` | Hover state for Navy elements. Sidebar hover, button hover backgrounds |
| **Blue** | `#2E74B5` | Informational accents. Info callout borders, secondary link color |
| **Light Blue** | `#D6E4F7` | Background fills. Card backgrounds, alternating table rows, form field highlights |
| **White** | `#FFFFFF` | Primary content background, text on dark backgrounds |
| **Off-White** | `#F8F9FA` | Page background, subtle section separation |
| **Text Dark** | `#212529` | Primary body text on light backgrounds |

### 8.2 CSS Custom Properties

Use these variables in all portal CSS, web form CSS, and inline styles. This ensures a single-point color update propagates everywhere.

```css
:root {
    /* LCS Brand Palette */
    --lcs-navy:        #002050;
    --lcs-crimson:     #900010;
    --lcs-steel-blue:  #004080;
    --lcs-gold:        #C8A020;
    --lcs-navy-alt:    #1A3A7A;
    --lcs-blue:        #2E74B5;
    --lcs-light-blue:  #D6E4F7;

    /* Semantic Aliases */
    --lcs-primary:          var(--lcs-navy);
    --lcs-primary-hover:    var(--lcs-navy-alt);
    --lcs-accent:           var(--lcs-crimson);
    --lcs-secondary:        var(--lcs-steel-blue);
    --lcs-highlight:        var(--lcs-gold);
    --lcs-surface:          var(--lcs-light-blue);
    --lcs-surface-alt:      #F0F4FA;

    /* Text */
    --lcs-text-on-dark:     #FFFFFF;
    --lcs-text-muted-dark:  var(--lcs-light-blue);
    --lcs-text-body:        #212529;
    --lcs-text-muted:       #6C757D;

    /* Borders */
    --lcs-border:           #C9D4E8;
    --lcs-border-strong:    var(--lcs-steel-blue);

    /* Spacing */
    --lcs-radius:           6px;
    --lcs-radius-lg:        10px;
    --lcs-shadow:           0 2px 8px rgba(0, 32, 80, 0.12);
    --lcs-shadow-lg:        0 4px 16px rgba(0, 32, 80, 0.18);
}
```

### 8.3 Typography

```css
/* Font Stack */
--lcs-font-body:    'Inter', 'Segoe UI', Arial, sans-serif;
--lcs-font-mono:    'Consolas', 'Courier New', monospace;

/* Scale */
--lcs-text-xs:    11px;
--lcs-text-sm:    13px;
--lcs-text-base:  14px;   /* Frappe Desk default */
--lcs-text-md:    16px;
--lcs-text-lg:    18px;
--lcs-text-xl:    22px;
--lcs-text-2xl:   28px;
```

### 8.4 Component Patterns

#### Page / Section Header Banner

```css
.lcs-header-banner {
    background-color: var(--lcs-navy);
    color: var(--lcs-text-on-dark);
    padding: 16px 24px;
    border-radius: var(--lcs-radius) var(--lcs-radius) 0 0;
    font-size: var(--lcs-text-xl);
    font-weight: 700;
    letter-spacing: 0.5px;
    border-bottom: 3px solid var(--lcs-gold);
}
```

#### Crimson Section Heading

```css
.lcs-section-heading {
    color: var(--lcs-crimson);
    font-size: var(--lcs-text-lg);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    border-bottom: 2px solid var(--lcs-crimson);
    padding-bottom: 6px;
    margin: 24px 0 12px 0;
}
```

#### Primary Button (Navy)

```css
.lcs-btn-primary {
    background-color: var(--lcs-navy);
    color: var(--lcs-text-on-dark);
    border: none;
    border-radius: var(--lcs-radius);
    padding: 8px 20px;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.15s ease;
}
.lcs-btn-primary:hover {
    background-color: var(--lcs-navy-alt);
}
```

#### Accent Button (Crimson)

```css
.lcs-btn-accent {
    background-color: var(--lcs-crimson);
    color: var(--lcs-text-on-dark);
    border: none;
    border-radius: var(--lcs-radius);
    padding: 8px 20px;
    font-weight: 600;
    cursor: pointer;
}
.lcs-btn-accent:hover {
    background-color: #7A000D;
}
```

#### Info / Callout Card

```css
.lcs-card {
    background-color: var(--lcs-surface);
    border: 1px solid var(--lcs-border);
    border-left: 4px solid var(--lcs-steel-blue);
    border-radius: var(--lcs-radius);
    padding: 14px 18px;
    margin-bottom: 16px;
    box-shadow: var(--lcs-shadow);
}

/* Variants */
.lcs-card.warning  { border-left-color: var(--lcs-gold);    background-color: #FDF8EC; }
.lcs-card.critical { border-left-color: var(--lcs-crimson); background-color: #FDF0F0; }
.lcs-card.success  { border-left-color: #28A745;            background-color: #F0FAF3; }
```

#### Table (Data Display)

```css
.lcs-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--lcs-text-sm);
}
.lcs-table thead tr {
    background-color: var(--lcs-navy);
    color: var(--lcs-text-on-dark);
}
.lcs-table thead th {
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    letter-spacing: 0.4px;
}
.lcs-table tbody tr:nth-child(even) {
    background-color: var(--lcs-light-blue);
}
.lcs-table tbody td {
    padding: 9px 14px;
    border-bottom: 1px solid var(--lcs-border);
}
```

#### Badge

```css
.lcs-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: var(--lcs-text-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.lcs-badge.navy    { background: var(--lcs-navy);    color: white; }
.lcs-badge.gold    { background: var(--lcs-gold);    color: #1A1A1A; }
.lcs-badge.crimson { background: var(--lcs-crimson); color: white; }
.lcs-badge.blue    { background: var(--lcs-blue);    color: white; }
```

### 8.5 Document (DOCX/Print) Palette

When producing Word documents using the Node.js `docx` library, use these hex values directly:

| Role | Hex | Strip `#` for docx |
|------|-----|:---:|
| Navy banner fill | `#002050` | `002050` |
| Crimson heading | `#900010` | `900010` |
| Steel Blue accent | `#004080` | `004080` |
| Gold highlight | `#C8A020` | `C8A020` |
| Light Blue fill | `#D6E4F7` | `D6E4F7` |
| Navy Alt hover/sub | `#1A3A7A` | `1A3A7A` |

**Standard document structure:**

- **Header:** Navy banner (`#002050`) with white LCS wordmark, logo right-aligned
- **Footer:** Multi-location contact strip — navy text, horizontal rule in Steel Blue, page number right-aligned
- **Section headings:** Crimson (`#900010`), all-caps, bold, with 2pt rule underline
- **Callout boxes:** Light Blue (`#D6E4F7`) fill, Steel Blue (`#004080`) left border 6pt
- **Warning/critical callouts:** Gold (`#C8A020`) fill for warnings, Crimson fill for critical
- **Tables:** Navy header row (white text), Light Blue alternating rows, Steel Blue border

### 8.6 Logo

- File: `/files/lcs_logo.PNG`
- Always render on white or Light Blue backgrounds — the logo has no built-in background
- Do not place on Crimson backgrounds (contrast fails)
- Minimum width: 120px in web, 1.5 inches in print

---

## 9. ERPNext Desk Theming

### 9.1 Two Distinct Targets

The ERPNext interface has two visually separate areas, each styled differently:

| Area | Styled Via |
|------|------------|
| **Desk** (backend — forms, lists, workspaces) | Desk Theme GUI + `lcs_theme.css` via `app_include_css` |
| **Portal / Web** (customer-facing, `/shortcuts`, `/timeclock`, etc.) | `lcs_theme.css` via `web_include_css`, plus per-page CSS files |

Website Settings `<head> HTML` only targets the portal, not the Desk. Do not try to style the Desk from there.

### 9.2 Desk Theme GUI (Primary Method)

The Desk Theme GUI is the correct tool for Navbar, Sidebar, Button, and Table colors. It bypasses the CSS specificity war with `frappe_desk_theme.bundle.css`.

**Navigation:** Search bar → "Desk Theme" → Edit

**LCS Desk Theme settings:**

| Field | Value |
|-------|-------|
| Sidebar background | `#002050` |
| Sidebar text | `#D6E4F7` |
| Sidebar hover background | `#1A3A7A` |
| Sidebar hover text | `#FFFFFF` |
| Navbar background | `#002050` |
| Navbar text | `#FFFFFF` |
| Primary button color | `#002050` |
| Primary button hover | `#1A3A7A` |

### 9.3 lcs_theme.css (Supplemental)

Use `lcs_theme.css` for everything the Desk Theme GUI doesn't cover — Number Card borders, page header rules, form section accents, and dark mode overrides.

```css
/* beveren_fsm/public/css/lcs_theme.css */

/* Number Cards */
.widget.number-widget-box {
    border-top: 3px solid var(--lcs-navy) !important;
}

/* Page head border */
.page-head {
    border-bottom: 2px solid var(--lcs-steel-blue) !important;
}

/* Dark mode overrides (Desk Theme GUI has no dark mode controls) */
html[data-theme="dark"] {
    --sidebar-bg: #001535;
    --navbar-bg: #001535;
    --card-bg: #1A2540;
    --text-color: #D6E4F7;
}
```

**Registration in hooks.py:**

```python
# MUST be a list — bare string silently fails
app_include_css = ["/assets/beveren_fsm/css/lcs_theme.css"]
```

### 9.4 Specificity Battles

`frappe_desk_theme.bundle.css` is installed on the site and loads before `lcs_theme.css`. It wins the cascade for navbar and sidebar when using standard selectors. The solution is the Desk Theme GUI (which uses JavaScript-injected inline styles, which always win). For elements not covered by the GUI, use `!important` sparingly and increase selector specificity.

---

## 10. Implementation Lessons & Gotchas

Real issues encountered during LCS development. Save yourself the debug time.

### Deployment Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| CSS not loading | `app_include_css` is a bare string, not a list | Wrap in `[ ]` |
| Fixtures not importing | JSON in wrong directory (inside module vs. `fixtures/`) | Move to `beveren_fsm/fixtures/` |
| Custom fields missing after deploy | Forgot to Trigger Migration after deploy | Always deploy → then Trigger Migration |
| SPA not updating | GitHub Actions build didn't run, or failed | Check Actions tab; touch a file in `schedule/src/` to trigger |
| CI failing on push | EN dashes, f-strings, or missing EOF newlines | Run `pre-commit run --all-files` locally first |

### Data Modeling Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| DocType `autoname` silently ignored | `autoname` key in JSON has incorrect value or wrong case | Check exact field name and value format in the JSON |
| Custom field not appearing in API response | `get_all()` doesn't auto-include new fields | Explicitly add field name to `fields=[]` list |
| Child table fields missing from API | Only some fields listed in API response builder | Add new fields manually to both response-building locations in the API file |
| Fixture sync duplicating records | Wrong fixture format (dict vs. list) | `fixtures/` = list format; `custom/` = dict format — never mix |

### ERPNext v16 UI Notes

- **Navigation differs from v15:** v16 uses a tabbed layout. Never give "scroll to section" directions — always reference fields by name
- **Server Scripts vs. committed code:** Server Scripts edited in Desk are **not** in the repo. Document them separately if they are critical business logic
- **`frappe.get_all()` in portal:** Bypasses RBAC silently — always use `frappe.get_list()` in user-facing contexts

### Theming Issues

- **`frappe_desk_theme.bundle.css` wins cascade:** Use Desk Theme GUI for navbar/sidebar — it uses inline styles which always win
- **Website Settings head HTML:** Only targets portal pages, never the Desk
- **Dark mode:** Desk Theme GUI has no dark mode controls — handle in `lcs_theme.css` with `html[data-theme="dark"]` block

### Real-World Lessons from LCS Builds

#### The Site Was Running the Wrong App Version

After installing the Beveren FSM app from Frappe marketplace and starting to build out custom `beveren_fsm` in the LCS fork, pushes had no effect on the site whatsoever. Deploys completed without error, migrations ran clean, and nothing changed.

**Root cause:** The site was still running `Beveren-Software-Inc/Field_Service_Management` on branch `Marketplace-Release` — the original marketplace version, not the LCS fork.

**Fix:** Go to bench Apps tab, uninstall the marketplace version, add the LCS fork as a bench-level app (`LeftCoastScales/Field_Service_Management`, branch `develop`), install it on the site, and trigger migration.

**Lesson:** When a deploy has no effect, first check the bench Apps tab. Verify the repository and branch shown for `beveren_fsm`. If it doesn't say `LeftCoastScales/Field_Service_Management` on `develop`, that's the problem — not the code.

#### The Wrong Branch Got Installed

Immediately after the above fix, the wrong branch was installed during bench-level app setup. `LucianStacy3-manuals-1` was selected instead of `develop`. The app installed cleanly, migration ran, but LCS customizations still didn't appear — because that branch didn't have them.

**Lesson:** Always verify the branch in the bench Apps tab before debugging anything else. It should say `develop`. If it says anything else, that's the first thing to fix.

#### Frappe Silently Drops Malformed DocType JSON

The `LCS Service Agreement` DocType was built, committed, pushed, deployed, and migrated — repeatedly — and never appeared in the system. No error in the Error Log. No migration failure message. The deploy log showed success. The DocType simply did not exist.

**Root causes:**

1. Single malformed line in `lcs_service_agreement.json`: `"autoname": "naming_series:"` (empty value after colon)
2. A `links` block referencing `Service Order`, a DocType that didn't exist on the bench yet

Frappe's migrate process encounters these, cannot parse the rules, and silently skips the entire DocType — no exception, no log entry, nothing.

**The only reliable verification:** Query the database directly via Frappe Cloud's SQL Playground:

```sql
SELECT name FROM tabDocType WHERE name LIKE 'LCS%';
```

If your DocType isn't in that result set after a successful migration, the JSON is malformed. Don't spend time looking at Python or hooks — start with the JSON.

**Correct `autoname` syntax for naming series:**

```json
"autoname": "naming_series:"
```

The colon at the end with nothing after it is intentional. What breaks it is having partial content after the colon or an incorrect value type.

#### `@frappe.whitelist()` Inside a Class Body Doesn't Work

When building the `LCS Service Agreement Quote` pricing suggester, the method was initially defined inside the DocType controller class with the decorator:

```python
class LCSServiceAgreementQuote(Document):
    @frappe.whitelist()
    def get_suggested_price(self, scale_type, difficulty):
        ...
```

The JavaScript `frappe.call` returned a "method not found" error.

**Fix:** Define the whitelisted function **outside** the class at module level:

```python
class LCSServiceAgreementQuote(Document):
    pass  # or other class methods


@frappe.whitelist()
def get_suggested_price(scale_type: str, difficulty: str) -> dict:
    ...
```

Frappe resolves `@frappe.whitelist()` methods by walking the module path. It cannot resolve methods on class instances through that path. Any API endpoint callable from JavaScript must be a module-level function.

#### Frappe CRM vs. ERPNext CRM

LCS started on Frappe CRM — the standalone Frappe app with its own Leads, Deals, and Organizations interface. About four weeks in, the transition was made to ERPNext CRM.

**The problem:** Creating a Quotation from a Frappe CRM Deal required a custom Client Script to bridge the systems. Even then, the Company field didn't populate correctly, causing "Please specify Company" errors on every transaction.

**The solution:** ERPNext CRM is native to ERPNext — Leads, Opportunities, and Quotations connect without bridging scripts, and the Company field populates automatically from user defaults.

**Current decision:** For a single-company operation where the CRM and ERP need to be tightly coupled, ERPNext CRM is the right call.

#### Server Scripts Are Not in the Repository

Several LCS features — the lead referral API, the leaderboard, parts of the referral program dashboard — were built as Frappe Server Scripts edited directly in the Desk. This was intentional: Server Scripts don't require a deploy, which makes iteration fast.

**But the cost:** These scripts are not in version control. If the site is rebuilt or data migrated, the scripts are lost. For critical business logic, either commit the scripts as fixtures or rewrite them as committed Python in the app.

**Current practice:** Fast iteration on Server Scripts is fine for exploratory features. Before going to production, audit which Server Scripts are critical and move them into `beveren_fsm` as proper Python fixtures.

---

## 11. Phase Planning & Roadmap

### Phase Implementation Model

For **Opus or Sonnet** — use this workflow when starting a new phase.

#### When Starting a Phase (Sonnet or Opus)

1. **Paste your implementation guide** — Sonnet learns your patterns (fixtures, custom fields, scheduler hooks, client scripts, naming conventions)
2. **Ask for code in LCS style** — "Follow the pattern from LCS Service Agreement and LCS Customer Equipment"
3. **Commit to GitHub before deploy** — Sonnet helps you write the fixtures correctly (you've documented the gotchas)

#### When Facing Architectural Decisions (Opus)

1. **Ask before coding:** "Here's Phase 7F–7H scope. Walk me through the onboarding → credit application → Phase 7H credit check flow. What happens if credit_limit is not set?"
2. **Get whiteboard-level architecture** — Opus provides decision trees, edge cases, and recommendations
3. **Then escalate to Sonnet** — Sonnet codes the approved design
4. **Estimate:** ~30 min with Opus per decision = $0.50–$1.50

### Phase-by-Phase Breakdown

| **Phase** | **Status** | **Model** | **Scope** |
|-----------|-----------|----------|-----------|
| **2E** | ✓ Complete (6/16) | — | Crew & time tracking |
| **3** | In Progress | **Sonnet** | Dispatch board SPA |
| **4** | Pending | **Sonnet→Opus if needed** | Tech PWA (offline) |
| **5** | Pending | **Opus first, then Sonnet** | Invoicing & payments |
| **7A** | Pending | **Sonnet** | Training & safety records |
| **7B** | Pending | **Opus first, then Sonnet** | ISO 17025 QMS |
| **7C** | Pending | **Sonnet** | AP receipt entry app |
| **7D** | Pending | **Sonnet** | Vendor & purchasing |
| **7E** | Pending | **Opus first** | ISNetworld integration |
| **7F** | Pending | **Opus first, then Sonnet** | Customer onboarding portal |
| **7G** | Pending | **Opus + Sonnet** | Creditsafe integration |
| **7H** | Pending | **Opus + Sonnet** | Credit limit enforcement |
| **7I** | Pending | **Sonnet** | Website contact form |
| **7J** | Pending | **Opus first** | TriNet HR sync |
| **7K** | Pending | **Sonnet** | Annual profile verify |
| **7L** | Pending | **Sonnet after 5** | Collections / dunning |
| **7M** | Pending | **Sonnet** | CC surcharge |
| **7N** | Pending | **Sonnet** | Late fee automation |
| **7O** | Pending | **Sonnet** | Internal IT ticketing |
| **7P** | Pending | **Sonnet** | Customer support ticketing |
| **7Q** | Pending | Neither (eval) | Internal chat system |
| **7R** | Pending | **Sonnet** | Communication tracking |
| **7S** | Pending | **Sonnet** | Email server migration |
| **7T** | Pending | **Sonnet** | Document duplication |
| **7U** | Pending | **Sonnet** | Recurring training invoices |
| **7V** | Pending | **Sonnet** | Recurring vendor bills |
| **7W** | Pending | **Sonnet** | Vehicle & equipment mgmt |

### Critical Decision Points: Escalate to Opus

#### Phase 5 (Invoicing & Payments)

**Decision:** How do Service Order → Invoice, consumed parts (Stock Entry), and field payment chain together?

**Why Opus:** Non-trivial data flow across three doctype families. Getting the order of operations wrong means rework later when Phase 7L, 7M, 7N layer on.

**Key questions:**
- Should parts consumed only when Invoice is created, or when Service Order completes?
- Do field payments (cash/check/card collected on-site) get recorded immediately or deferred until office reconciliation?
- If tech partially completes a job, is Invoice created as draft or held until final completion?

#### Phase 7B (ISO 17025 QMS)

**Decision:** Document control, NCRs, CAPAs, internal audits—what's the approval workflow?

**Why Opus:** Regulatory compliance. An audit 18 months from now will trace your NCR closure and CAPA effectiveness. Build it right the first time.

**Key questions:**
- Which roles approve Document revisions, NCR closure, CAPA completion?
- What's the audit trail for traceability (dates, approver, evidence)?
- Escalation if CAPA effectiveness check fails?

#### Phase 7E (ISNetworld Integration)

**Decision:** Will ISNetworld grant API access, or do we fall back to manual tracking?

**Why Opus:** ISN API access is the critical path. If denied, Path B (manual doctype) needs solid UX design.

**Key questions:**
- Path A (API): Nightly sync, error handling, token refresh
- Path B (manual): Admin form for entering compliance status, expiration dates, training records manually
- Fallback escalation if API becomes unavailable mid-stream

#### Phase 7F–7H (Onboarding + Credit)

**Decision:** If a customer completes onboarding but no credit_limit is set, what happens when they place a Service Order in Phase 7H?

**Why Opus:** These phases are linked. A design flaw in 7F creates a blocking bug in 7H.

**Key questions:**
- Does Phase 7F auto-set a default credit_limit (e.g., $5,000) pending review, or leave it blank?
- If blank, does Phase 7H block all orders, or skip the check (credit_limit = 0 = no limit)?
- When does credit_limit get approved: onboarding submission, or separate credit review step?
- If customer is Pending Credit Approval, can they still place orders?

#### Phase 7J (TriNet Bi-Directional Sync)

**Decision:** Who is the system of record—ERPNext Frappe HR or TriNet PEO?

**Why Opus:** Bi-directional sync without a clear source of truth causes data conflicts.

**Example problem:**
- HR creates employee in Frappe HR
- Nightly sync pushes to TriNet
- TriNet admin updates job title
- Next sync pulls job title back to Frappe HR, overwriting local changes
- Chaos ensues

**Key decisions:**
- ERPNext Frappe HR is source of truth (push-only to TriNet)?
- TriNet is source of truth (pull-only from TriNet)?
- Hybrid: Frappe HR owns org structure, TriNet owns payroll data?
- Conflict resolution: if both systems change the same field, which wins?

### Cost & ROI

| **Investment** | **Cost** | **Prevents** |
|---|---|---|
| 6–8 Opus design sessions | ~$5–$15 | 1–2 weeks rework per major phase = $10K+ in engineering time |
| Sonnet for routine work | ~$0.003 per 1K tokens | None; it's the baseline |

**Bottom line:** Use Opus strategically. The cost is trivial; the upside is preventing costly rework.

### Summary

- **Phase 2E:** ✅ Complete (6/16/26). Crew leader, time tracking, and travel time fields deployed.
- **Phases 3 onward:** Use Sonnet as default. Escalate to Opus for Phases 5, 7B, 7E, 7F–7H, and 7J (critical architecture decisions).
- **Total Opus budget:** ~6–8 sessions (~$5–$15). Saves weeks of rework.
- **Keep the implementation guide handy** — both models learn from your established patterns (fixtures, naming, client scripts, scheduler hooks).

---

**Last updated:** June 2026 | **Next review:** When Phase 3 completes
