# Copyright (c) 2026, Left Coast Scales
# For license information, please see license.txt
#
# ZZTEST test data tools -- loads/removes a sample data set covering the
# LCS test plan (Customer/Contact/Address, Service Type/Area, two test
# Users + Employees + Service Technicians, three LCS Vehicles -- a
# straight truck, a van, and a pickup -- LCS Scale Model + Customer
# Equipment pair, LCS Service Report Checklist Template, LCS Service
# Agreement, a starter Service Request, and four sellable Items --
# indicator, platform, load cell, and leveling foot -- for testing parts
# lookup/consumption) directly through Frappe's ORM -- no external
# scripts, API keys, or REST calls needed. Runs entirely server-side,
# triggered from the "ZZTEST Data Tools" Desk page.
#
# Drop this file at:
#   beveren_fsm/field_service_management/api/zztest_data.py

import json
import os
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import today, add_days

ZZTEST_PREFIX = "ZZTEST"


def _manifest_path():
    return frappe.get_site_path("private", "files", "zztest_manifest.json")


def _lock_path():
    return frappe.get_site_path("private", "files", "zztest_removed.lock")


def _load_manifest():
    path = _manifest_path()
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _save_manifest(manifest):
    with open(_manifest_path(), "w") as f:
        json.dump(manifest, f, indent=2)


def _require_system_manager():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a System Manager can run the ZZTEST data tools."), frappe.PermissionError)


def _default_company():
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        companies = frappe.get_all("Company", pluck="name", limit=1)
        company = companies[0] if companies else None
    if not company:
        frappe.throw(
            _(
                "No Company exists on this site yet. Complete the ERPNext Setup Wizard "
                "(or create a Company record) before loading test data."
            )
        )
    return company


def _company_currency_and_country(company):
    doc = frappe.get_cached_doc("Company", company)
    return (doc.default_currency or "USD"), (doc.country or "United States")


def _break_paired_equipment_links(items):
    """
    LCS Customer Equipment Display/Base pairs point at each other via
    paired_component, so Frappe's link-safety check will always find each
    side "still linked" from the other -- a genuine mutual-reference
    deadlock that no amount of retrying can resolve on its own (confirmed
    live: both remove_test_data() and force_cleanup() got permanently
    stuck on a Display/Base pair, which in turn blocked their LCS Scale
    Model and Manufacturer records too -- this happens on every load/
    remove cycle, not just when other documents reference the test data).

    `items` is an iterable of (doctype, name) tuples -- either the
    manifest entries or force_cleanup()'s discovered set. Since both
    sides of any pair found here are already in our own tracked/
    discovered set (i.e. we're about to try deleting both anyway), it's
    safe to sever the link first so normal (non-force) deletion can
    proceed on each side independently, instead of leaving them deadlocked.
    """
    names = {name for doctype, name in items if doctype == "LCS Customer Equipment"}
    for name in names:
        if not frappe.db.exists("LCS Customer Equipment", name):
            continue
        paired = frappe.db.get_value("LCS Customer Equipment", name, "paired_component")
        if paired and paired in names:
            frappe.db.set_value(
                "LCS Customer Equipment", name, "paired_component", None, update_modified=False
            )


class _Builder:
    """Tracks what this run creates and appends it to the on-disk manifest."""

    def __init__(self):
        self.manifest = _load_manifest()
        self.lines = []
        self.last_created = False

    def log(self, line):
        self.lines.append(line)

    def create(self, doctype, values, dedupe_filters=None, track=True):
        if dedupe_filters:
            existing = frappe.db.get_value(doctype, dedupe_filters)
            if existing:
                self.log(f"= {doctype} '{existing}' already exists, skipping")
                self.last_created = False
                return existing

        doc = frappe.get_doc({"doctype": doctype, **values})
        doc.insert(ignore_permissions=True)
        self.log(f"+ created {doctype} '{doc.name}'")
        if track:
            self.manifest.append({"doctype": doctype, "name": doc.name})
            _save_manifest(self.manifest)
        self.last_created = True
        return doc.name


@frappe.whitelist()
def get_status():
    """Used by the Desk page on load to show current state."""
    _require_system_manager()
    manifest = _load_manifest()
    return {
        "locked": os.path.exists(_lock_path()),
        "record_count": len(manifest),
        "lock_note": open(_lock_path()).read() if os.path.exists(_lock_path()) else None,
    }


@frappe.whitelist()
def create_test_data():
    _require_system_manager()

    if os.path.exists(_lock_path()):
        frappe.throw(
            _(
                "Test data was already created and removed once on this site, and was "
                "locked to stop it being silently re-applied. Use the 'Unlock' button on "
                "the ZZTEST Data Tools page if you deliberately want to re-seed it."
            )
        )

    b = _Builder()
    company = _default_company()
    currency, country = _company_currency_and_country(company)

    b.log("1. Manufacturer")
    manufacturer = b.create(
        "Manufacturer",
        {"short_name": f"{ZZTEST_PREFIX} Manufacturer"},
        dedupe_filters={"short_name": f"{ZZTEST_PREFIX} Manufacturer"},
    )

    b.log("2. LCS Scale Models (Base + Display)")
    base_model = b.create(
        "LCS Scale Model",
        {
            "manufacturer": manufacturer,
            "model_number": f"{ZZTEST_PREFIX} Base 500x0.1",
            "equipment_type": "Base",
            "capacity": 500,
            "capacity_unit": "lb",
            "resolution": 0.1,
            "resolution_unit": "lb",
        },
        dedupe_filters={"model_number": f"{ZZTEST_PREFIX} Base 500x0.1"},
    )
    display_model = b.create(
        "LCS Scale Model",
        {
            "manufacturer": manufacturer,
            "model_number": f"{ZZTEST_PREFIX} Display 500x0.1",
            "equipment_type": "Display",
            "capacity": 500,
            "capacity_unit": "lb",
            "resolution": 0.1,
            "resolution_unit": "lb",
        },
        dedupe_filters={"model_number": f"{ZZTEST_PREFIX} Display 500x0.1"},
    )

    b.log("3. Service Type")
    service_type_name = f"{ZZTEST_PREFIX} Calibration Service"
    service_type = b.create(
        "Service Type",
        {"name": service_type_name, "description": "QA test service type"},
        dedupe_filters={"name": service_type_name},
    )

    b.log("4. Service Area")
    service_area_name = f"{ZZTEST_PREFIX} Test Area"
    service_area = b.create(
        "Service Area",
        {"service_area": service_area_name},
        dedupe_filters={"name": service_area_name},
    )

    b.log("5. Customer")
    customer_name = f"{ZZTEST_PREFIX} Acme Scale Co"
    customer = b.create(
        "Customer",
        {"customer_name": customer_name, "customer_type": "Company"},
        dedupe_filters={"customer_name": customer_name},
    )

    b.log("6. Address")
    address_title = f"{ZZTEST_PREFIX} Acme Scale Co"
    address = b.create(
        "Address",
        {
            "address_title": address_title,
            "address_type": "Office",
            "address_line1": "123 Test Way",
            "city": "Perris",
            "state": "CA",
            "pincode": "92570",
            "country": country,
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        },
        dedupe_filters={"address_title": address_title, "address_type": "Office"},
    )

    b.log("7. Contact")
    contact = b.create(
        "Contact",
        {
            "first_name": ZZTEST_PREFIX,
            "last_name": "Contact",
            "links": [{"link_doctype": "Customer", "link_name": customer}],
            "email_ids": [{"email_id": "zztest.contact@example.com", "is_primary": 1}],
            "phone_nos": [{"phone": "555-010-0100", "is_primary_phone": 1}],
        },
        dedupe_filters={"first_name": ZZTEST_PREFIX, "last_name": "Contact"},
    )

    b.log("8. Users & Employees (for Tech PWA + permission tests)")
    gender = frappe.db.get_value("Gender", {"name": ["in", ["Other", "Male", "Female"]]}) or None
    field_service_role = "Field Service User"
    if not frappe.db.exists("Role", field_service_role):
        b.log(
            f"  NOTE: Role '{field_service_role}' does not exist on this site (it's created "
            f"manually, not via fixtures -- see hooks.py). Test users are created without it; "
            f"the low-privilege permission-sync test won't be meaningful until that role exists."
        )

    def _make_employee_user(first_name, email):
        user_name = b.create(
            "User",
            {
                "email": email,
                "first_name": first_name,
                "last_name": "ZZTEST",
                "send_welcome_email": 0,
                "enabled": 1,
            },
            dedupe_filters={"name": email},
        )
        if b.last_created and frappe.db.exists("Role", field_service_role):
            user_doc = frappe.get_doc("User", user_name)
            user_doc.append("roles", {"role": field_service_role})
            user_doc.save(ignore_permissions=True)

        employee_name = b.create(
            "Employee",
            {
                "first_name": first_name,
                "last_name": "ZZTEST",
                "company": company,
                "status": "Active",
                "gender": gender,
                "date_of_birth": add_days(today(), -365 * 30),
                "date_of_joining": add_days(today(), -180),
                "user_id": user_name,
            },
            dedupe_filters={"first_name": first_name, "last_name": "ZZTEST", "company": company},
        )
        return user_name, employee_name

    tech_one_user, tech_one_employee = _make_employee_user(f"{ZZTEST_PREFIX} Tech1", "zztest.tech1@example.com")
    tech_two_user, tech_two_employee = _make_employee_user(f"{ZZTEST_PREFIX} Tech2", "zztest.tech2@example.com")
    b.log(
        "  No password is set on these accounts -- use the User list's 'Set New Password' "
        "action to log in as one of them."
    )

    b.log("9. Service Technicians (for crew-leader / overlap tests)")
    b.create(
        "Service Technician",
        {"full_name": f"{ZZTEST_PREFIX} Tech One", "service_area": service_area, "employee": tech_one_employee},
        dedupe_filters={"full_name": f"{ZZTEST_PREFIX} Tech One"},
    )
    b.create(
        "Service Technician",
        {"full_name": f"{ZZTEST_PREFIX} Tech Two", "service_area": service_area, "employee": tech_two_employee},
        dedupe_filters={"full_name": f"{ZZTEST_PREFIX} Tech Two"},
    )

    b.log("10. LCS Vehicles (fleet / non-human resources: truck, van, pickup)")
    b.create(
        "LCS Vehicle",
        {
            "unit_number": f"{ZZTEST_PREFIX}-99",
            "nickname": "Test Truck",
            "vehicle_type": "Straight Truck",
            "form_type": "DOT",
            "status": "Active",
            "service_area": service_area,
            "branch": "Perris",
            "year": 2022,
            "make": "Freightliner",
            "model": "M2",
        },
        dedupe_filters={"unit_number": f"{ZZTEST_PREFIX}-99"},
    )
    b.create(
        "LCS Vehicle",
        {
            "unit_number": f"{ZZTEST_PREFIX}-98",
            "nickname": "Test Van",
            "vehicle_type": "Van",
            "form_type": "Light Vehicle",
            "status": "Active",
            "service_area": service_area,
            "branch": "Perris",
            "year": 2023,
            "make": "Ford",
            "model": "Transit",
        },
        dedupe_filters={"unit_number": f"{ZZTEST_PREFIX}-98"},
    )
    b.create(
        "LCS Vehicle",
        {
            "unit_number": f"{ZZTEST_PREFIX}-97",
            "nickname": "Test Pickup",
            "vehicle_type": "Pickup",
            "form_type": "Light Vehicle",
            "status": "Active",
            "service_area": service_area,
            "branch": "Perris",
            "year": 2021,
            "make": "Ford",
            "model": "F-150",
        },
        dedupe_filters={"unit_number": f"{ZZTEST_PREFIX}-97"},
    )
    b.log(
        "  NOTE: calibration test weights don't have a standalone master doctype in this app -- "
        "'Calibration Equipment' is only enterable as a free-text resource row directly on a "
        "Service Appointment (LCS Appointment Resource), e.g. type '500 lb Test Weight Set' "
        "when assigning resources during the manual lifecycle walkthrough."
    )

    b.log("11. LCS Customer Equipment - Display (auto-pairs a Base)")
    display_serial = f"{ZZTEST_PREFIX}-DISP-0001"
    display_equipment = b.create(
        "LCS Customer Equipment",
        {
            "customer": customer,
            "service_address": address,
            "status": "Active",
            "equipment_type": "Display",
            "manufacturer": manufacturer,
            "scale_model": display_model,
            "serial_number": display_serial,
            "base_manufacturer": manufacturer,
            "base_scale_model": base_model,
            "base_serial_number": f"{ZZTEST_PREFIX}-BASE-0001",
            "calibration_interval_months": 12,
            "last_calibration_date": add_days(today(), -180),
        },
        dedupe_filters={"serial_number": display_serial},
    )
    # after_insert on the Display record auto-creates the paired Base --
    # only capture/track it when THIS call actually just created the
    # Display (not on a re-run where it was found via dedupe_filters),
    # otherwise re-running this would append a duplicate manifest entry
    # for a Base record already being tracked.
    if b.last_created:
        paired_base = frappe.db.get_value("LCS Customer Equipment", display_equipment, "paired_component")
        if paired_base:
            b.log(f"+ auto-paired Base record '{paired_base}'")
            b.manifest.append({"doctype": "LCS Customer Equipment", "name": paired_base})
            _save_manifest(b.manifest)

    b.log("12. LCS Customer Equipment - overdue calibration (for scheduler test)")
    overdue_serial = f"{ZZTEST_PREFIX}-OVERDUE-0001"
    b.create(
        "LCS Customer Equipment",
        {
            "customer": customer,
            "service_address": address,
            "status": "Active",
            "equipment_type": "Unit",
            "manufacturer": manufacturer,
            "scale_model": base_model,
            "serial_number": overdue_serial,
            "calibration_interval_months": 1,
            "last_calibration_date": add_days(today(), -400),
        },
        dedupe_filters={"serial_number": overdue_serial},
    )

    b.log("13. LCS Service Report Checklist Template")
    b.create(
        "LCS Service Report Checklist Template",
        {
            "service_type": service_type,
            "items": [
                {"item_text": "Zero-balance check"},
                {"item_text": "Load test at 50% capacity"},
                {"item_text": "Load test at full capacity"},
                {"item_text": "Calibration sticker applied"},
            ],
        },
        dedupe_filters={"name": service_type},
    )

    b.log("14. LCS Service Agreement (Active, due today, auto-create ON)")
    b.create(
        "LCS Service Agreement",
        {
            "agreement_name": f"{ZZTEST_PREFIX} Monthly Calibration Agreement",
            "status": "Active",
            "customer": customer,
            "company": company,
            "contract_start_date": add_days(today(), -30),
            "next_service_order_date": today(),
            "recurrence_type": "Interval",
            "recurrence_interval": 1,
            "recurrence_unit": "Month",
            "auto_create_service_orders": 1,
            "due_date_type": "Last Service + Interval",
            "service_type": service_type,
            "service_area": service_area,
            "priority": "Medium",
            "sites": [{"site_name": "Main Site", "address": address}],
            "equipment": [
                {
                    "equipment_description": "ZZTEST Bench Scale",
                    "serial_no": display_serial,
                    "model": display_model,
                }
            ],
        },
        dedupe_filters={
            "agreement_name": f"{ZZTEST_PREFIX} Monthly Calibration Agreement",
            "customer": customer,
        },
    )

    b.log("15. Starter Service Request (walk the rest of the lifecycle manually)")
    b.create(
        "Service Request",
        {
            "subject": f"{ZZTEST_PREFIX} Sample Service Request",
            "priority": "Medium",
            "due_date": add_days(today(), 7),
            "customer": customer,
            "company": company,
            "type": service_type,
            "currency": currency,
            "posting_date": today(),
            "status": "Open",
        },
        dedupe_filters={"subject": f"{ZZTEST_PREFIX} Sample Service Request"},
    )

    b.log("16. Sellable Items (scale components: indicators, platforms, load cells, feet)")
    item_group = frappe.db.get_value("Item Group", {"item_group_name": "Products"})
    if not item_group:
        # fall back to whatever root/group Item Group exists on this site
        item_group = frappe.db.get_value("Item Group", {"is_group": 1})
    if not item_group:
        b.log("  NOTE: no Item Group found on this site -- skipping sample Items.")
    else:
        stock_uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {})
        sample_items = [
            ("ZZTEST-IND-100", "ZZTEST Digital Weight Indicator"),
            ("ZZTEST-PLT-4X4", "ZZTEST Floor Scale Platform 4x4 ft"),
            ("ZZTEST-LC-5K", "ZZTEST Load Cell - 5,000 lb Capacity"),
            ("ZZTEST-FOOT-SS", "ZZTEST Stainless Steel Leveling Foot"),
        ]
        for item_code, item_name in sample_items:
            b.create(
                "Item",
                {
                    "item_code": item_code,
                    "item_name": item_name,
                    "item_group": item_group,
                    "stock_uom": stock_uom,
                    "is_stock_item": 1,
                    "description": item_name,
                },
                dedupe_filters={"item_code": item_code},
            )

    b.log(f"\nDone. {len(b.manifest)} record(s) tracked in zztest_manifest.json.")
    frappe.db.commit()
    return {"lines": b.lines, "manifest_count": len(b.manifest)}


@frappe.whitelist()
def remove_test_data():
    _require_system_manager()

    manifest = _load_manifest()
    if not manifest:
        return {
            "lines": ["Nothing tracked -- nothing to remove."],
            "manifest_count": 0,
            "locked": os.path.exists(_lock_path()),
        }

    # Break any Display/Base mutual-pairing links up front -- see
    # _break_paired_equipment_links() docstring. Without this, a paired
    # equipment record is *permanently* stuck: it's always "still linked"
    # from its own pair, no matter how many times you retry.
    _break_paired_equipment_links((e["doctype"], e["name"]) for e in manifest)

    lines = []
    remaining = list(manifest)
    for entry in reversed(manifest):
        doctype, name = entry["doctype"], entry["name"]
        try:
            if not frappe.db.exists(doctype, name):
                lines.append(f"= {doctype} '{name}' already gone, skipping")
                remaining.remove(entry)
                continue
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            if docstatus == 1:
                frappe.get_doc(doctype, name).cancel()
                lines.append(f"- cancelled {doctype} '{name}'")
            # Deliberately NOT force=True: if something still links to this
            # record (e.g. a Quotation/Order/Invoice you created manually
            # while testing), Frappe should refuse and we report it below
            # rather than silently deleting the master and leaving that
            # other document with a dangling reference. Use Force Cleanup
            # if you want those linked records cleaned up too.
            frappe.delete_doc(doctype, name, ignore_permissions=True)
            lines.append(f"- deleted {doctype} '{name}'")
            remaining.remove(entry)
        except Exception:
            frappe.log_error(title=f"ZZTEST cleanup failed: {doctype} {name}", message=frappe.get_traceback())
            lines.append(f"! FAILED to delete {doctype} '{name}' -- still linked from something else, see Error Log")

    _save_manifest(remaining)
    locked = False
    if not remaining:
        _write_lock()
        lines.append("\nAll test data removed. Site is now locked against re-seeding.")
        locked = True
    else:
        lines.append(f"\n{len(remaining)} record(s) failed to delete -- left tracked for retry.")

    frappe.db.commit()
    return {"lines": lines, "manifest_count": len(remaining), "locked": locked}


def _write_lock():
    if os.path.exists(_manifest_path()):
        os.remove(_manifest_path())
    with open(_lock_path(), "w") as f:
        f.write(
            f"Test data fully removed on {datetime.now().isoformat(timespec='seconds')}.\n"
            f"create_test_data will refuse to run while this file exists.\n"
            f"Use the Unlock button on the ZZTEST Data Tools page if you deliberately "
            f"want to re-seed test data.\n"
        )


@frappe.whitelist()
def unlock():
    """Deliberate override: remove the lock so create_test_data can run again."""
    _require_system_manager()
    if os.path.exists(_lock_path()):
        os.remove(_lock_path())
        return {"lines": ["Lock removed. You can load test data again."]}
    return {"lines": ["Not locked -- nothing to do."]}


MAX_FORCE_CLEANUP_DISCOVERED = 2000


@frappe.whitelist()
def force_cleanup():
    """
    Regular remove_test_data() only ever touches the records it originally
    created. If you've since walked the lifecycle manually (Quotation ->
    Service Order -> Service Appointment -> Sales Invoice, extra Service
    Reports, Stock Entries, etc.), those documents reference the ZZTEST
    Customer/Items/etc. and will block the normal cleanup with "linked
    record" errors.

    This does a wider cleanup: starting from whatever's still tracked in
    the manifest, it uses Frappe's own link-discovery (the same mechanism
    that normally blocks a delete with "Cannot delete ... as it is linked
    with ...") to find every document anywhere in the system that's
    connected to the test data -- directly or transitively -- then
    repeatedly retries deleting the whole set until it's fully gone or
    nothing more can be removed.

    It does NOT bypass Frappe's link checks on documents outside that
    discovered set. If something you didn't create during ZZTEST testing
    (a real, unrelated document) still references one of these records,
    that specific record is left alone and reported rather than force-
    deleted -- "force" here means "reaches further than the original 27
    records," not "ignores every safety check."
    """
    _require_system_manager()

    from frappe.model.delete_doc import get_dynamic_linked_docs, get_linked_docs

    manifest = _load_manifest()
    if not manifest:
        return {
            "lines": ["Nothing tracked -- nothing to force-clean."],
            "removed": 0,
            "locked": os.path.exists(_lock_path()),
        }

    lines = []

    # --- Discovery: BFS outward from every tracked root -----------------
    discovered = {(e["doctype"], e["name"]) for e in manifest}
    frontier = list(discovered)
    aborted = False
    while frontier:
        next_frontier = []
        for doctype, name in frontier:
            if not frappe.db.exists(doctype, name):
                continue
            try:
                doc = frappe.get_doc(doctype, name)
                links = get_linked_docs(doc, method="Delete") + get_dynamic_linked_docs(doc, method="Delete")
            except Exception:
                links = []
            for link in links:
                key = (link["reference_doctype"], link["reference_docname"])
                if key not in discovered:
                    discovered.add(key)
                    next_frontier.append(key)
                    if len(discovered) > MAX_FORCE_CLEANUP_DISCOVERED:
                        aborted = True
                        break
            if aborted:
                break
        if aborted:
            break
        frontier = next_frontier

    if aborted:
        return {
            "lines": [
                f"Stopped: found more than {MAX_FORCE_CLEANUP_DISCOVERED} linked records while "
                f"tracing out from the test data. That's far more than this test set should ever "
                f"touch, so this looks like it may be reaching into real data -- aborting without "
                f"deleting anything. Contact support before proceeding if you expected this."
            ],
            "removed": 0,
            "locked": False,
        }

    lines.append(
        f"Traced {len(discovered)} record(s) connected to the test data "
        f"({len(manifest)} originally tracked, {len(discovered) - len(manifest)} discovered from manual testing)."
    )

    # Same Display/Base mutual-pairing deadlock as remove_test_data() --
    # break it across the whole discovered set before attempting deletes.
    _break_paired_equipment_links(discovered)

    # --- Deletion: retry passes until stable -----------------------------
    remaining = set(discovered)
    removed = []
    for _pass in range(30):
        if not remaining:
            break
        progressed = False
        for doctype, name in list(remaining):
            try:
                if not frappe.db.exists(doctype, name):
                    remaining.discard((doctype, name))
                    progressed = True
                    continue
                docstatus = frappe.db.get_value(doctype, name, "docstatus")
                if docstatus == 1:
                    frappe.get_doc(doctype, name).cancel()
                frappe.delete_doc(doctype, name, ignore_permissions=True)
                removed.append((doctype, name))
                remaining.discard((doctype, name))
                progressed = True
            except Exception:
                continue
        if not progressed:
            break

    lines.append(f"Removed {len(removed)} record(s).")
    if remaining:
        lines.append(
            f"{len(remaining)} record(s) still couldn't be removed -- something outside the "
            f"test data (a real document) still references them. See Error Log for details:"
        )
        for doctype, name in list(remaining)[:20]:
            lines.append(f"  - {doctype} / {name}")
            frappe.log_error(
                title=f"ZZTEST force cleanup stuck: {doctype} {name}",
                message="Still referenced by something outside the discovered test-data set.",
            )

    remaining_manifest = [e for e in manifest if (e["doctype"], e["name"]) in remaining]
    _save_manifest(remaining_manifest)
    locked = False
    if not remaining_manifest:
        _write_lock()
        lines.append("\nAll tracked test data removed. Site is now locked against re-seeding.")
        locked = True

    frappe.db.commit()
    return {"lines": lines, "removed": len(removed), "locked": locked}
