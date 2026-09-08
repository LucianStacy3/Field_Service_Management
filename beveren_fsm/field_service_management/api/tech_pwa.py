"""
beveren_fsm/field_service_management/api/tech_pwa.py

Whitelisted REST endpoints for the LCS Field Tech PWA (/tech). Every
write here mirrors the client-side chained-logic state machine
(src/state/timeTrackingMachine.js) so the server is the final source of
truth once a mutation syncs, while the device stays fully authoritative
offline. All reads use frappe.qb / frappe.get_list to enforce RBAC per
the coding-style guide's security rules — never frappe.get_all here.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime, nowdate, get_datetime, flt


def _current_employee() -> str:
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw("No Employee record is linked to your user account. Contact the office.")
    return employee


def _current_service_technician() -> str:
    """
    Service Technician Item.service_technician links to the Service
    Technician DocType, not directly to Employee — Service Technician
    has its own `employee` field one hop further out. Every appointment
    assignment check has to go through this, not _current_employee().
    """
    employee = _current_employee()
    technician = frappe.db.get_value("Service Technician", {"employee": employee}, "name")
    if not technician:
        frappe.throw(
            "No Service Technician record is linked to your Employee record. Contact the office.",
        )
    return technician


def _format_address(fields: dict) -> str | None:
    """Joins Address doctype fields into a single display/Maps-query-friendly line."""
    parts = [
        fields.get("address_line1"),
        fields.get("address_line2"),
        fields.get("city"),
        fields.get("state"),
        fields.get("pincode"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _site_addresses_for_orders(service_order_names: list[str]) -> dict[str, str | None]:
    """
    Batched version for list views: Service Order -> Address in two
    bulk queries instead of one round-trip per appointment. Address is
    reached via Service Order.customer_address (a Link), not the mixed
    contact/address text block in Service Order.address_details.
    """
    service_order_names = [n for n in service_order_names if n]
    if not service_order_names:
        return {}

    orders = frappe.get_all(
        "Service Order",
        filters={"name": ("in", service_order_names)},
        fields=["name", "customer_address"],
    )
    order_to_address = {o.name: o.customer_address for o in orders if o.customer_address}
    address_names = list(set(order_to_address.values()))
    if not address_names:
        return {}

    addresses = frappe.get_all(
        "Address",
        filters={"name": ("in", address_names)},
        fields=["name", "address_line1", "address_line2", "city", "state", "pincode"],
    )
    address_lookup = {a.name: _format_address(a) for a in addresses}

    return {
        order_name: address_lookup.get(address_name)
        for order_name, address_name in order_to_address.items()
    }


def _site_address_for_order(service_order_name: str | None) -> str | None:
    """Single-lookup version for get_job_detail."""
    if not service_order_name:
        return None
    return _site_addresses_for_orders([service_order_name]).get(service_order_name)


@frappe.whitelist()
def get_current_technician() -> dict:
    """
    Resolves the logged-in user's Employee/Service Technician records.
    Used once on app load so `employee` is never blank in the PWA's sync
    payloads — previously hardcoded to null in App.jsx and never actually
    resolved, even though the server-side fallback in submit_time_action
    (employee or _current_employee()) meant this likely wasn't the cause
    of any missing day logs — just a real gap worth closing regardless.
    """
    return {
        "employee": _current_employee(),
        "service_technician": _current_service_technician(),
    }


@frappe.whitelist()
def complete_appointment(appointment: str) -> dict:
    """
    Marks a job complete: sets Service Appointment.status to "Completed"
    (which cascades to the linked Service Order's status via
    update_service_order_status), and removes it from this technician's
    job list going forward — see the status filter in get_my_jobs.
    Deliberately independent of Service Report submission: requiring
    that first would currently block completion on any service type
    that doesn't yet have a checklist template set up.

    Crew gate: on a multi-technician job, only the designated crew leader
    (Service Technician Item.custom_is_crew_leader) may close it out --
    any one of several technicians tapping "Mark Complete" mid-job (while
    the others are still on site) would otherwise silently drop the job
    from everyone's list and cascade the Service Order forward with no
    consensus. Solo-technician jobs are exempt from this gate: with only
    one assigned technician there's no one else's work to step on, so
    that technician can complete it regardless of the crew-leader flag.
    """
    service_technician = _current_service_technician()
    _assert_assigned(appointment, service_technician)

    assigned = frappe.get_all(
        "Service Technician Item",
        filters={"parent": appointment},
        fields=["service_technician", "custom_is_crew_leader"],
    )
    if len(assigned) > 1:
        is_leader = any(
            row.service_technician == service_technician and row.custom_is_crew_leader
            for row in assigned
        )
        if not is_leader:
            frappe.throw(
                "Only the crew leader can mark this job complete when more than one "
                "technician is assigned.",
                frappe.PermissionError,
            )

    doc = frappe.get_doc("Service Appointment", appointment)
    doc.status = "Completed"
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist()
def get_completion_email_info(appointment: str) -> dict:
    """
    Tells the PWA whether there's a Service Report worth sending as a PDF,
    and whether a client email is already on file (Service Order's
    customer_contact -> Contact.email_id) so it knows whether to prompt
    for one.
    """
    _assert_assigned(appointment, _current_service_technician())

    report = _service_report_for_appointment(appointment)
    if not report:
        return {"has_service_report": False, "email": None}

    service_order = frappe.db.get_value("Service Appointment", appointment, "service_order")
    email = None
    if service_order:
        contact = frappe.db.get_value("Service Order", service_order, "customer_contact")
        if contact:
            email = frappe.db.get_value("Contact", contact, "email_id")

    return {"has_service_report": True, "email": email}


@frappe.whitelist()
def send_service_report_pdf(appointment: str, emails) -> dict:
    """
    Emails the Service Report as a PDF to one or more addresses. `emails`
    may be a list or a comma-separated string (whichever survives the
    JSON round-trip more conveniently from the client).
    """
    _assert_assigned(appointment, _current_service_technician())

    report = _service_report_for_appointment(appointment)
    if not report:
        frappe.throw("No Service Report exists for this appointment to send.")

    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(",") if e.strip()]
    emails = [e for e in (emails or []) if e]
    if not emails:
        frappe.throw("At least one email address is required.")

    pdf_bytes = frappe.get_print("Service Report", report.name, as_pdf=True)
    frappe.sendmail(
        recipients=emails,
        subject=f"Service Report — {report.name}",
        message="Please find attached the service report for your recent appointment.",
        attachments=[{"fname": f"{report.name}.pdf", "fcontent": pdf_bytes}],
    )
    return {"sent_to": emails}


@frappe.whitelist()
def get_my_jobs(from_date: str | None = None, to_date: str | None = None) -> list[dict]:
    """Today's (or a given range's) Service Appointments assigned to the logged-in technician."""
    service_technician = _current_service_technician()
    from_date = from_date or nowdate()
    to_date = to_date or from_date

    tech_rows = frappe.get_all(
        "Service Technician Item",
        filters={"service_technician": service_technician},
        fields=["parent", "custom_is_crew_leader"],
    )
    appointment_names = list({r.parent for r in tech_rows})
    if not appointment_names:
        return []
    crew_leader_by_appointment = {r.parent: bool(r.custom_is_crew_leader) for r in tech_rows}

    appointments = frappe.get_list(
        "Service Appointment",
        filters={
            "name": ("in", appointment_names),
            "scheduled_start_datetime": ("between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]),
            "status": ("!=", "Completed"),  # Mark Complete removes a job from the tech's list
        },
        fields=["name", "customer", "status", "scheduled_start_datetime", "service_order"],
        order_by="scheduled_start_datetime asc",
    )
    address_by_order = _site_addresses_for_orders([a.service_order for a in appointments])
    return [
        {
            "name": a.name,
            "customer_name": a.customer,  # Customer's name field doubles as its display title
            "site_address": address_by_order.get(a.service_order),
            "scheduled_start": a.scheduled_start_datetime,
            "status": a.status,
            "is_crew_leader": crew_leader_by_appointment.get(a.name, False),
        }
        for a in appointments
    ]


@frappe.whitelist()
def get_job_detail(appointment: str) -> dict:
    """Full detail for a single appointment: notes, status, customer."""
    service_technician = _current_service_technician()
    _assert_assigned(appointment, service_technician)

    doc = frappe.get_doc("Service Appointment", appointment)

    is_crew_leader = bool(frappe.db.get_value(
        "Service Technician Item",
        {"parent": appointment, "service_technician": service_technician},
        "custom_is_crew_leader",
    ))

    return {
        "name": doc.name,
        "customer_name": doc.customer,
        "site_address": _site_address_for_order(doc.get("service_order")),
        "scheduled_start": doc.scheduled_start_datetime,
        "status": doc.status,
        "instructions": doc.get("dispatch_instructions"),  # office/sales-entered, read-only for the tech
        "customer_notes": doc.get("customer_notes"),
        "internal_notes": doc.get("internal_notes"),
        "is_crew_leader": is_crew_leader,
        "parts": _parts_for_appointment(doc),
        "reference_numbers": _reference_numbers_for_appointment(doc),
    }


def _reference_numbers_for_appointment(doc) -> dict:
    """
    The full document chain a job can be traced through: Service Request
    (what LCS staff call a "Service Call") -> Service Quotation ->
    Service Order -> this Service Appointment. Any of the upstream links
    may be blank depending on how the job originated (e.g. an order
    created directly with no prior quote or call), so this only
    includes whichever are actually set.
    """
    numbers = {"service_appointment": doc.name}

    service_order = doc.get("service_order")
    if service_order:
        numbers["service_order"] = service_order
        order_refs = frappe.db.get_value(
            "Service Order", service_order, ["service_quotation", "service_request"], as_dict=True
        )
        if order_refs:
            if order_refs.service_quotation:
                numbers["service_quotation"] = order_refs.service_quotation
            if order_refs.service_request:
                numbers["service_call"] = order_refs.service_request  # "Service Call" is LCS's name for Service Request

    return numbers


def _parts_for_appointment(doc) -> list[dict]:
    """
    Service Appointment.items (child doctype Service Order Item) carries
    both services and parts — same table shape as Service Order, since
    appointments are created from an order's line items. is_service
    distinguishes labor lines from actual parts so the PWA can filter or
    label them differently if it wants to.
    """
    return [
        {
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": row.qty,
            "uom": row.uom,
            "rate": row.rate,
            "amount": row.amount,
            "is_service": bool(row.is_service),
        }
        for row in (doc.get("items") or [])
    ]


def _is_service_item_group(item_group: str | None) -> bool:
    return (item_group or "").strip().lower() in {"service", "services"}


@frappe.whitelist()
def search_items(query: str) -> list[dict]:
    """
    Item search for the Tech PWA's Add Part picker. Deliberately not
    scoped to a "parts" item group — a tech might reasonably need to add
    an extra service/labor line too, same flexibility Service Order
    already has on the Desk side.
    """
    if not query or len(query) < 2:
        return []

    # frappe.get_all, not get_list: Field Service User has no read grant
    # on Item (checked — there isn't even a fixture wiring Custom DocPerm
    # into hooks.py for this app, so that's not a quick permission-only
    # fix either). Item master data isn't sensitive per-row, and the
    # actual authorization boundary here is _assert_assigned() on the
    # write side (add_part_to_appointment), not this search.
    items = frappe.get_all(
        "Item",
        filters={"disabled": 0},
        or_filters=[
            ["item_code", "like", f"%{query}%"],
            ["item_name", "like", f"%{query}%"],
        ],
        fields=["item_code", "item_name", "item_group", "standard_rate", "stock_uom"],
        limit_page_length=20,
        order_by="item_name asc",
    )
    for item in items:
        item["is_service"] = _is_service_item_group(item.get("item_group"))
    return items


@frappe.whitelist()
def add_part_to_appointment(appointment: str, item_code: str, qty: float = 1) -> dict:
    """
    Adds a part (or service line) to the appointment's items table from
    the field. Online-only for now, same scope limitation as the Service
    Report — this doesn't queue into the offline mutation outbox, so it
    needs a live connection to succeed.

    Also mirrors the row onto the linked Service Order's own items table
    (merging into an existing item_code's qty rather than duplicating a
    row) — Service Order.items is the only place the Create Invoice flow
    (service_order.js create_service_invoice / fsm_utils.create_service_invoice)
    reads from. Without this, a part a tech adds in the field never
    reaches an invoice — it would sit on Service Appointment.items
    forever, invisible to billing. See LCS ERPNext Implementation
    Roadmap, Section 8 (Phase 5).
    """
    _assert_assigned(appointment, _current_service_technician())

    item = frappe.db.get_value(
        "Item", item_code, ["item_name", "item_group", "standard_rate", "stock_uom"], as_dict=True
    )
    if not item:
        frappe.throw(f"Item {item_code} not found.")

    qty = flt(qty) or 1
    rate = flt(item.standard_rate)
    is_service = bool(_is_service_item_group(item.item_group))

    doc = frappe.get_doc("Service Appointment", appointment)
    doc.append(
        "items",
        {
            "item_code": item_code,
            "item_name": item.item_name,
            "qty": qty,
            "uom": item.stock_uom,
            "rate": rate,
            "amount": rate * qty,
            "is_service": is_service,
        },
    )
    doc.save(ignore_permissions=True)  # allow_on_submit=1 on items — works whether Open or already Scheduled/In Progress

    _mirror_part_to_service_order(doc.get("service_order"), item_code, item.item_name, qty, rate, is_service)

    return {"parts": _parts_for_appointment(doc)}


def _mirror_part_to_service_order(
    service_order: str | None,
    item_code: str,
    item_name: str | None,
    qty: float,
    rate: float,
    is_service: bool,
) -> None:
    """
    Keeps Service Order.items in sync with parts added in the field so
    they actually get billed. Merges into an existing row for the same
    item_code (increments qty/amount) rather than appending a duplicate
    line — mirrors the merge-by-item_code behavior service_order.js's
    create_service_invoice dialog already applies on its own side, and
    means an item invoiced before, then added to again in the field,
    correctly shows a remaining invoiceable qty afterward.

    Skipped quietly if the appointment has no linked Service Order —
    shouldn't happen in practice, but a field tech's part-add shouldn't
    fail over a data issue on an unrelated document.
    """
    if not service_order:
        return

    order = frappe.get_doc("Service Order", service_order)
    existing = next((row for row in order.items if row.item_code == item_code), None)

    if existing:
        existing.qty = flt(existing.qty) + qty
        existing.amount = flt(existing.rate) * existing.qty
    else:
        order.append(
            "items",
            {
                "item_code": item_code,
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "amount": rate * qty,
                "is_service": is_service,
            },
        )

    # Service Order.items lacks allow_on_submit (unlike Service
    # Appointment.items, which has it) and most orders being worked in
    # the field are already submitted (Scheduled/Dispatched/In Progress/
    # Review all have docstatus=1). Without this flag, Frappe's normal
    # update-after-submit guard silently reverts the appended/merged row
    # right back out during save -- no exception, no error in the
    # response, just a no-op -- which is exactly the failure mode this
    # fix exists to close. Confirmed via direct testing against a
    # submitted (status=Review) Service Order: without this flag the
    # part never reached the DB despite a 200 response.
    order.flags.ignore_validate_update_after_submit = True
    order.save(ignore_permissions=True)


def _assert_assigned(appointment: str, service_technician: str) -> None:
    assigned = frappe.db.exists(
        "Service Technician Item", {"parent": appointment, "service_technician": service_technician}
    )
    if not assigned:
        frappe.throw("You are not assigned to this appointment.", frappe.PermissionError)


@frappe.whitelist()
def update_notes(appointment: str, customer_notes: str = "", internal_notes: str = "") -> dict:
    """Writes customer-facing and internal-only notes for an appointment."""
    _assert_assigned(appointment, _current_service_technician())

    doc = frappe.get_doc("Service Appointment", appointment)
    doc.db_set("customer_notes", customer_notes, update_modified=True)
    doc.db_set("internal_notes", internal_notes, update_modified=True)
    return {"ok": True}


# ---- En-route notification ("On My Way") ------------------------------
# Net-new, not an extension of the time-tracking machine (submit_time_action)
# -- that machine's CLOCK_IN_LIGHT "Travel" segment is payroll-relevant and
# isn't reliably tied to a specific appointment. Deliberately does not touch
# Service Appointment.status: the status enum has no "En Route" value, and
# adding one would ripple into update_service_order_status()'s status_mapping
# and the dispatch board's status filtering -- out of scope for what is
# fundamentally a notification. See LCS ERPNext Implementation Roadmap,
# Section 9.3 for the resolved design.

@frappe.whitelist()
def notify_on_my_way(appointment: str) -> dict:
    """
    Sends an "on my way" notification to the customer for this appointment.
    en_route_notified_at doubles as an audit trail and an idempotency guard --
    once set, a technician re-tapping the button in the PWA is a no-op rather
    than a re-send.
    """
    _assert_assigned(appointment, _current_service_technician())

    doc = frappe.get_doc("Service Appointment", appointment)
    if doc.get("en_route_notified_at"):
        return {"ok": True, "already_sent": True, "en_route_notified_at": doc.en_route_notified_at}

    email = None
    if doc.get("service_order"):
        contact = frappe.db.get_value("Service Order", doc.service_order, "customer_contact")
        if contact:
            email = frappe.db.get_value("Contact", contact, "email_id")
    if not email:
        # No email on file -- never block the technician's workflow over a
        # notification. Same graceful-skip precedent as
        # send_scheduled_confirmation_email (Section 9.2) and
        # _send_payment_receipt_email.
        return {"ok": True, "already_sent": False, "skipped_no_recipient": True}

    site_address = _site_address_for_order(doc.get("service_order"))

    technician_first_name = None
    if doc.get("service_technicians"):
        full_name = doc.service_technicians[0].full_name
        if full_name:
            technician_first_name = full_name.split()[0]

    lines = []
    lines.append(
        f"{technician_first_name} is on the way to your site." if technician_first_name
        else "Your technician is on the way to your site."
    )
    if site_address:
        lines.append(f"Site: {site_address}")

    try:
        frappe.sendmail(
            recipients=[email],
            subject=f"Your Technician Is On The Way — {doc.name}",
            message="<br>".join(lines),
        )
    except Exception:
        frappe.log_error(title="En-route notification email failed", message=frappe.get_traceback())
        return {"ok": True, "already_sent": False, "send_failed": True}

    doc.db_set("en_route_notified_at", now_datetime(), update_modified=True)
    return {"ok": True, "already_sent": False, "en_route_notified_at": doc.en_route_notified_at}


@frappe.whitelist()
def upload_job_photo() -> dict:
    """
    Handles multipart file upload for a job photo. Expects form fields:
    file (the image), appointment, caption. Uses frappe's file API so the
    resulting File doc attaches directly to the new LCS Appointment Photo
    record, which links back to the Service Appointment.
    """
    from frappe.handler import upload_file

    appointment = frappe.form_dict.get("appointment")
    caption = frappe.form_dict.get("caption", "")
    _assert_assigned(appointment, _current_service_technician())

    file_doc = upload_file()  # saves the uploaded file, returns a File doc

    photo = frappe.get_doc({
        "doctype": "LCS Appointment Photo",
        "appointment": appointment,
        "photo": file_doc.file_url,
        "caption": caption,
        "taken_by": frappe.session.user,
        "taken_at": now_datetime(),
    })
    photo.insert(ignore_permissions=False)
    return {"file_url": file_doc.file_url, "photo_name": photo.name}


# ---- Service Report (digital checklist) ------------------------------------
# Folds the earlier standalone CSR/Service Report concept into the Tech PWA,
# scoped to Service Appointment instead of Service Order so it lives
# alongside everything else on the job detail screen. One Service Report per
# appointment; checklist items are pre-populated from the
# LCS Service Report Checklist Template matching the appointment's Service
# Order's Service Type, if one exists. Photos are NOT duplicated here — the
# PWA's existing LCS Appointment Photo flow (upload_job_photo, above) already
# covers that.

def _service_report_for_appointment(appointment: str):
    """Returns the existing Service Report for this appointment, if any."""
    name = frappe.db.get_value("Service Report", {"service_appointment": appointment}, "name")
    return frappe.get_doc("Service Report", name) if name else None


def _serialize_service_report(doc) -> dict:
    return {
        "name": doc.name,
        "docstatus": doc.docstatus,
        "technician_notes": doc.get("technician_notes"),
        "submitted_at": doc.get("submitted_at"),
        "checklist": [
            {
                "checklist_item": row.checklist_item,
                "response": row.response,
                "notes": row.notes,
            }
            for row in doc.get("checklist") or []
        ],
    }


@frappe.whitelist()
def get_service_report(appointment: str) -> dict:
    """
    Returns the Service Report for this appointment, creating a new draft
    (with checklist pre-populated from the Service Type's template, if one
    exists) the first time a technician opens the Service Report screen
    for this job.
    """
    _assert_assigned(appointment, _current_service_technician())

    doc = _service_report_for_appointment(appointment)
    if not doc:
        appt = frappe.db.get_value("Service Appointment", appointment, ["service_order", "customer"], as_dict=True)
        doc = frappe.get_doc({
            "doctype": "Service Report",
            "service_appointment": appointment,
            # Set explicitly rather than relying on fetch_from — fetch_from
            # only auto-populates through Desk's client-side JS when a Link
            # field changes in the browser, not when a document is created
            # server-side like this. Left unset, these silently stayed
            # blank on every new Service Report.
            "service_order": appt.service_order if appt else None,
            # custom_service_order is a leftover Custom Field from the old
            # CSR web form (beveren_fsm/www/... era) — added via Customize
            # Form, so it's invisible in git and in this DocType's own
            # JSON. It's mandatory in the live database despite being
            # otherwise unused now; without this, every new Service Report
            # failed MandatoryError on insert. Worth removing this
            # duplicate field via Customize Form at some point, but
            # populating it is the immediate, safe fix either way.
            "custom_service_order": appt.service_order if appt else None,
            "customer": appt.customer if appt else None,
        })
        doc.insert(ignore_permissions=True)  # validate() populates the checklist from the template

    return _serialize_service_report(doc)


def _apply_checklist_updates(doc, checklist, technician_notes: str | None) -> None:
    if checklist is not None:
        if isinstance(checklist, str):
            checklist = frappe.parse_json(checklist)
        responses_by_item = {row.get("checklist_item"): row for row in checklist}
        for row in doc.checklist:
            update = responses_by_item.get(row.checklist_item)
            if update:
                row.response = update.get("response") or row.response
                row.notes = update.get("notes", row.notes)
    if technician_notes is not None:
        doc.technician_notes = technician_notes


@frappe.whitelist()
def save_service_report(appointment: str, checklist=None, technician_notes: str | None = None) -> dict:
    """Saves in-progress checklist responses and notes without submitting."""
    _assert_assigned(appointment, _current_service_technician())

    doc = _service_report_for_appointment(appointment)
    if not doc:
        frappe.throw("No Service Report exists yet for this appointment — call get_service_report first.")
    if doc.docstatus != 0:
        frappe.throw("This Service Report has already been submitted and can no longer be edited here.")

    _apply_checklist_updates(doc, checklist, technician_notes)
    doc.save(ignore_permissions=True)
    return _serialize_service_report(doc)


@frappe.whitelist()
def submit_service_report(appointment: str, checklist=None, technician_notes: str | None = None) -> dict:
    """Applies any final checklist/notes edits, then submits — a Service
    Report is a completed-job audit record once submitted, not a draft."""
    service_technician = _current_service_technician()
    _assert_assigned(appointment, service_technician)

    doc = _service_report_for_appointment(appointment)
    if not doc:
        frappe.throw("No Service Report exists yet for this appointment — call get_service_report first.")
    if doc.docstatus != 0:
        frappe.throw("This Service Report has already been submitted.")

    _apply_checklist_updates(doc, checklist, technician_notes)
    doc.submitted_by = service_technician
    doc.flags.ignore_permissions = True
    doc.submit()
    return _serialize_service_report(doc)


@frappe.whitelist()
def submit_time_action(
    action_type: str,
    at: str,
    job_ref: str | None = None,
    employee: str | None = None,
    reason: str | None = None,
    duration_minutes: int | None = None,
    corrected_arrival_at: str | None = None,
    correction_reason: str | None = None,
    correction_job_ref: str | None = None,
    log_date: str | None = None,
    pause_duration_minutes: int | None = None,
    lunch_duration_minutes: int | None = None,
) -> dict:
    """
    Reconciles one chained-logic time tracking action against the
    technician's LCS Tech Day Log for `log_date` — the technician's own
    local calendar date, supplied explicitly by the client. Validation
    mirrors src/state/timeTrackingMachine.js — see that file for the
    authoritative rules (Section 1.1-1.5 of the Time-Tracking Proposal).

    `at` and `corrected_arrival_at` are local wall-clock strings (no
    'Z'/UTC suffix) — see toLocalDatetimeString() client-side. Frappe
    stores Datetime fields naively (no timezone conversion), so these
    must already be local by the time they arrive here; sending UTC
    would have every stored segment start/end silently shift by the
    browser's UTC offset. Same reasoning applies to log_date: supplied
    explicitly by the client rather than derived from `at` here, since
    `at` alone can't safely be re-parsed into "the technician's calendar
    date" without redoing the same local-time logic already done
    client-side. Falls back to deriving log_date from `at` only for
    mutations already queued before this fix shipped, which won't carry
    log_date at all — that fallback predates the local-time fix too, so
    it inherits the same historical UTC-drift imprecision for any such
    leftover mutations specifically.

    This endpoint is intentionally permissive on ordering: because the
    device is the offline source of truth, the server accepts the action
    log as reported and only flags conflicts for admin review rather than
    rejecting the sync outright, which would strand queued mutations.
    """
    employee = employee or _current_employee()
    log_date = log_date or get_datetime(at).date().isoformat()
    log_name = f"TDL-{employee}-{log_date}"

    if frappe.db.exists("LCS Tech Day Log", log_name):
        log = frappe.get_doc("LCS Tech Day Log", log_name)
    else:
        log = frappe.get_doc({
            "doctype": "LCS Tech Day Log",
            "employee": employee,
            "log_date": log_date,
            "day_state": "Active",
        })
        log.insert(ignore_permissions=True)

    open_segment = log.segments[-1] if log.segments and not log.segments[-1].end_time else None

    segment_type_map = {
        "CLOCK_IN_LIGHT": "Travel",
        "START_INSPECTION": "Prep",
        "ARRIVE": "Onsite" if job_ref else "Shop",
    }

    # Close whatever segment is currently open before opening the next one.
    if action_type in ("SUBMIT_INSPECTION", "ARRIVE", "LEAVE", "END_DAY") and open_segment:
        # Starting a new job/shop directly from a paused job (see the
        # ARRIVE case in timeTrackingMachine.js) closes out any dangling
        # pause/lunch duration on the segment being closed here, since no
        # separate RESUME_JOB/LUNCH_IN call precedes this one to carry it.
        if action_type == "ARRIVE" and pause_duration_minutes:
            open_segment.pause_minutes = (open_segment.pause_minutes or 0) + pause_duration_minutes
        if action_type == "ARRIVE" and lunch_duration_minutes:
            open_segment.lunch_minutes = (open_segment.lunch_minutes or 0) + lunch_duration_minutes
        open_segment.end_time = at

    # Open the segment this action starts (Day-Start / Arrive actions).
    if action_type in ("CLOCK_IN_LIGHT", "START_INSPECTION", "ARRIVE"):
        log.append("segments", {
            "segment_type": segment_type_map[action_type],
            "reference_appointment": job_ref,
            "start_time": at,
        })

    # Submit Inspection and Leave both hand off into Travel.
    if action_type in ("SUBMIT_INSPECTION", "LEAVE"):
        log.append("segments", {"segment_type": "Travel", "start_time": at})

    # Job pause: record the reason immediately (at PAUSE_JOB time); the
    # elapsed minutes arrive later with RESUME_JOB, once the device knows
    # the exact duration.
    if action_type == "PAUSE_JOB" and open_segment and reason:
        open_segment.pause_reason = (
            f"{open_segment.pause_reason}; {reason}" if open_segment.pause_reason else reason
        )

    if action_type == "RESUME_JOB" and open_segment and duration_minutes:
        open_segment.pause_minutes = (open_segment.pause_minutes or 0) + duration_minutes

    # Lunch minutes: previously computed client-side but never actually
    # persisted here despite the field existing on the child table —
    # fixed alongside the new pause tracking above.
    if action_type == "LUNCH_IN" and open_segment and duration_minutes:
        open_segment.lunch_minutes = (open_segment.lunch_minutes or 0) + duration_minutes

    # Manually-entered technician corrections. This mirrors
    # timeTrackingMachine.js's CORRECT_ARRIVAL case exactly — see that
    # file for why these are the only two recoverable flag reasons.
    # Previously this action was never synced to the server at all
    # (excluded client-side), so a flagged segment could only ever be
    # resolved by someone editing the record directly in Desk.
    if action_type == "CORRECT_ARRIVAL" and corrected_arrival_at:
        if correction_reason == "SEQUENTIAL_LOCK":
            if open_segment:
                open_segment.end_time = corrected_arrival_at
                open_segment.flagged_for_review = 1
                open_segment.correction_reason = "Sequential Lock"
            log.append("segments", {"segment_type": "Travel", "start_time": corrected_arrival_at})
        elif correction_reason == "MISSING_CLOCK_IN":
            log.append("segments", {
                "segment_type": "Onsite" if correction_job_ref else "Shop",
                "reference_appointment": correction_job_ref,
                "start_time": corrected_arrival_at,
                "flagged_for_review": 1,
                "correction_reason": "Missing Clock-In",
            })

    if action_type == "END_DAY":
        log.day_state = "Ended"

    if action_type == "REOPEN_DAY":
        # Undoes an End Day tapped by mistake. Flagged for review since
        # it's a correction to a payroll-relevant record, same reasoning
        # as the other manual corrections above.
        log.day_state = "Active"
        if log.segments:
            log.segments[-1].flagged_for_review = 1
            log.segments[-1].correction_reason = "Reopened Day"

    # ---- Live status fields (Technician Status Board, Section 41) ---------
    # current_job / on_lunch / job_paused are kept in sync right here, at
    # the one place all these transitions already happen, instead of
    # re-deriving "what is this technician doing right now" from the
    # segment history on every board refresh.
    if action_type in ("CLOCK_IN_LIGHT", "START_INSPECTION", "ARRIVE", "SUBMIT_INSPECTION", "LEAVE"):
        # Every one of these opens a brand-new segment, so any lunch/pause
        # flag on the log belongs to the segment that just closed -- clear
        # it before the new one starts. ARRIVE-while-paused already folds
        # the closing segment's pause/lunch *minutes* onto that segment
        # above; this is the separate "is it happening right now" flag.
        log.on_lunch = 0
        log.job_paused = 0
        log.current_job = job_ref if action_type == "ARRIVE" else None

    if action_type == "PAUSE_JOB":
        log.job_paused = 1

    if action_type == "RESUME_JOB":
        log.job_paused = 0

    if action_type == "LUNCH_OUT" and open_segment:
        # Previously a no-op here: LUNCH_OUT touched no field at all (the
        # client only reports elapsed lunch minutes later, at LUNCH_IN),
        # so the server never learned a technician had gone to lunch until
        # they were already back. That was fine when nothing server-side
        # needed to know in real time; the status board does.
        log.on_lunch = 1

    if action_type == "LUNCH_IN":
        log.on_lunch = 0

    if action_type == "CORRECT_ARRIVAL" and corrected_arrival_at:
        log.on_lunch = 0
        log.job_paused = 0
        log.current_job = correction_job_ref if correction_reason == "MISSING_CLOCK_IN" else None

    if action_type == "END_DAY":
        log.on_lunch = 0
        log.job_paused = 0
        log.current_job = None

    log.needs_review_count = sum(1 for s in log.segments if s.flagged_for_review)
    log.save(ignore_permissions=True)
    return {"day_log": log.name, "day_state": log.day_state}


# ---- Field Payment Collection (Phase 5) ------------------------------------
# Activates the "Collect Payment" action on the Job Detail screen. See LCS
# ERPNext Implementation Roadmap, Section 8.4/8.5 for the resolved design:
# amount + method (Cash/Check/Card) -> Payment Entry against the Service
# Order's Sales Invoice, record-only (no gateway/processing integration --
# a card charge happens on a separate terminal outside ERPNext), using
# standard mode_of_payment so Phase 7M's surcharge logic (Section 22) has
# a clean field to key off later. Then an emailed receipt reusing the
# site's default Letter Head branding. Collect Payment only proceeds
# against an already-submitted invoice (Section 8.1 step 5) -- never a
# draft that could still be edited -- checked both client-side (PWA hides
# the action until get_payment_info says can_collect) and again here,
# since the client can't be trusted as the only gate on a money-moving
# endpoint.

PAYMENT_METHOD_TO_MODE_OF_PAYMENT = {
    "Cash": "Cash",
    "Check": "Check",
    "Card": "Credit Card",
}


def _latest_submitted_invoice_for_service_order(service_order: str):
    """
    The most recently created submitted Sales Invoice referencing this
    Service Order (custom_reference_service_doctype/_document -- see
    fsm_utils.create_service_invoice). Create Invoice's own
    double-invoicing guard (Section 8.2, custom_invoice_created) isn't
    built yet, so this defensively doesn't assume there's exactly one --
    it just takes the newest.
    """
    names = frappe.get_all(
        "Sales Invoice",
        filters={
            "custom_reference_service_doctype": "Service Order",
            "custom_reference_service_document": service_order,
            "docstatus": 1,
        },
        fields=["name"],
        order_by="creation desc",
        limit_page_length=1,
    )
    if not names:
        return None
    return frappe.get_doc("Sales Invoice", names[0].name)


@frappe.whitelist()
def get_payment_info(appointment: str) -> dict:
    """
    Tells the PWA whether Collect Payment should be shown/enabled for
    this job: whether a submitted Sales Invoice exists for its Service
    Order, and if so whether it still has a balance due.
    """
    _assert_assigned(appointment, _current_service_technician())

    service_order = frappe.db.get_value("Service Appointment", appointment, "service_order")
    invoice = _latest_submitted_invoice_for_service_order(service_order) if service_order else None

    if not invoice:
        return {"can_collect": False, "status": "not_invoiced", "invoice": None, "outstanding_amount": 0, "currency": None, "methods": []}

    if flt(invoice.outstanding_amount) <= 0:
        return {
            "can_collect": False,
            "status": "paid_in_full",
            "invoice": invoice.name,
            "outstanding_amount": 0,
            "currency": invoice.currency,
            "methods": [],
        }

    return {
        "can_collect": True,
        "status": "outstanding",
        "invoice": invoice.name,
        "outstanding_amount": flt(invoice.outstanding_amount),
        "currency": invoice.currency,
        "methods": list(PAYMENT_METHOD_TO_MODE_OF_PAYMENT.keys()),
    }


@frappe.whitelist()
def collect_payment(appointment: str, amount: float, method: str) -> dict:
    """
    Creates and submits a Payment Entry against the appointment's
    Service Order's Sales Invoice, then emails a receipt to the customer
    contact on file. POST-only -- this mutates real accounting records,
    same GET-vs-POST rule from Section 8.6/Section 39 (commit 0cca418).
    """
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_bank_cash_account, get_payment_entry

    _assert_assigned(appointment, _current_service_technician())

    mode_of_payment = PAYMENT_METHOD_TO_MODE_OF_PAYMENT.get(method)
    if not mode_of_payment:
        frappe.throw(f"Unknown payment method: {method}")

    amount = flt(amount)
    if amount <= 0:
        frappe.throw("Enter an amount greater than zero.")

    service_order = frappe.db.get_value("Service Appointment", appointment, "service_order")
    invoice = _latest_submitted_invoice_for_service_order(service_order) if service_order else None
    if not invoice:
        frappe.throw("No submitted invoice was found for this job yet — Collect Payment isn't available until it's invoiced.")
    if flt(invoice.outstanding_amount) <= 0:
        frappe.throw("This invoice is already paid in full.")
    if amount > flt(invoice.outstanding_amount) + 0.005:  # small tolerance for float rounding
        frappe.throw(
            f"That's more than the outstanding balance of "
            f"{frappe.utils.fmt_money(invoice.outstanding_amount, currency=invoice.currency)}."
        )

    # get_payment_entry (ERPNext core) does its own doctype permission
    # check on Sales Invoice/Payment Entry, and Field Service User has no
    # Desk-level grant on either -- correctly so, a tech shouldn't be able
    # to browse the accounting module. _assert_assigned() above is the
    # real authorization boundary for this endpoint, same as every other
    # write in this file, so the actual money-moving calls run as
    # Administrator rather than the technician's own (deliberately
    # narrow) role. Confirmed via direct testing: without this, collect_payment
    # failed with "User ... does not have doctype access via role
    # permission for document Sales Invoice" despite _assert_assigned
    # already having verified the technician owns this job.
    original_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        pe = get_payment_entry("Sales Invoice", invoice.name, party_amount=amount)
        pe.mode_of_payment = mode_of_payment
        # get_bank_cash_account(doc, bank_account) -- NOT (mode_of_payment, company)
        # as first assumed. It reads doc.company and doc.get("mode_of_payment")
        # itself (hence mode_of_payment must already be set on pe, above), and
        # bank_account is an optional preferred-account override we don't need.
        # Confirmed against erpnext/accounts/doctype/payment_entry/payment_entry.py
        # (version-16 branch) after this shipped the wrong signature and failed
        # live testing with "AttributeError: 'str' object has no attribute 'company'".
        bank_cash_account = get_bank_cash_account(pe, None)
        if bank_cash_account and bank_cash_account.get("account"):
            pe.paid_to = bank_cash_account["account"]
        pe.reference_no = f"Field Payment - {appointment}"
        pe.reference_date = nowdate()
        pe.paid_amount = amount
        pe.received_amount = amount
        if pe.references:
            pe.references[0].allocated_amount = amount
        pe.flags.ignore_permissions = True
        pe.insert(ignore_permissions=True)
        pe.submit()
        invoice.reload()
    finally:
        frappe.set_user(original_user)
    receipt_emailed_to = _send_payment_receipt_email(invoice, pe, service_order)

    return {
        "payment_entry": pe.name,
        "amount_paid": flt(pe.paid_amount),
        "outstanding_amount": flt(invoice.outstanding_amount),
        "receipt_emailed_to": receipt_emailed_to,
    }


_RECEIPT_CONTENT_TEMPLATE = """
<div style="font-family: sans-serif; color: #1a1a1a; max-width: 680px; margin: 24px auto;">
  <h2 style="color: #002050; border-bottom: 2px solid #002050; padding-bottom: 8px;">Payment Receipt</h2>
  <table style="width: 100%; font-size: 13px; margin-bottom: 16px;">
    <tr><td style="color: #555;">Invoice</td><td style="text-align: right;">{{ invoice.name }}</td></tr>
    <tr><td style="color: #555;">Payment Date</td><td style="text-align: right;">{{ payment_entry.reference_date }}</td></tr>
    <tr><td style="color: #555;">Payment Method</td><td style="text-align: right;">{{ payment_entry.mode_of_payment }}</td></tr>
    <tr><td style="color: #555;">Customer</td><td style="text-align: right;">{{ invoice.customer_name }}</td></tr>
  </table>
  <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    <thead>
      <tr style="background: #f2f2f2;">
        <th style="text-align: left; padding: 6px;">Item</th>
        <th style="text-align: right; padding: 6px;">Qty</th>
        <th style="text-align: right; padding: 6px;">Rate</th>
        <th style="text-align: right; padding: 6px;">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in invoice.items %}
      <tr style="border-bottom: 1px solid #e0e0e0;">
        <td style="padding: 6px;">{{ item.item_name }}</td>
        <td style="text-align: right; padding: 6px;">{{ item.qty }}</td>
        <td style="text-align: right; padding: 6px;">{{ frappe.utils.fmt_money(item.rate, currency=invoice.currency) }}</td>
        <td style="text-align: right; padding: 6px;">{{ frappe.utils.fmt_money(item.amount, currency=invoice.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <table style="width: 100%; font-size: 13px; margin-top: 16px;">
    <tr><td>Invoice Total</td><td style="text-align: right;">{{ frappe.utils.fmt_money(invoice.grand_total, currency=invoice.currency) }}</td></tr>
    <tr style="font-weight: bold; color: #002050;"><td>Amount Paid Today</td><td style="text-align: right;">{{ frappe.utils.fmt_money(payment_entry.paid_amount, currency=invoice.currency) }}</td></tr>
    <tr><td>Remaining Balance</td><td style="text-align: right;">{{ frappe.utils.fmt_money(invoice.outstanding_amount, currency=invoice.currency) }}</td></tr>
  </table>
  <p style="font-size: 12px; color: #777; margin-top: 24px;">Thank you for your business.</p>
</div>
"""


def _render_payment_receipt_pdf(invoice, payment_entry) -> bytes:
    """
    Builds the receipt PDF by wrapping the site's default Letter Head
    (same header/footer/logo the Service Report PDF picks up automatically
    via Print Settings' with_letterhead flag) around a receipt-specific
    content block, per Section 8.5 -- reuse the branding, not the
    Service-Report-specific checklist section.
    """
    from frappe.utils.pdf import get_pdf

    letter_head = frappe.db.get_value(
        "Letter Head", {"is_default": 1, "disabled": 0}, ["content", "footer"], as_dict=True
    ) or {}
    body = frappe.render_template(
        _RECEIPT_CONTENT_TEMPLATE, {"invoice": invoice, "payment_entry": payment_entry, "frappe": frappe}
    )
    full_html = f"{letter_head.get('content') or ''}{body}{letter_head.get('footer') or ''}"
    return get_pdf(full_html)


def _send_payment_receipt_email(invoice, payment_entry, service_order: str | None) -> str | None:
    """
    Emails the receipt to the customer contact on file. Doesn't fail the
    payment if there's no email on file or sending errors out -- the
    Payment Entry is the durable record; the receipt is a courtesy on
    top of it, same non-blocking spirit as complete_appointment being
    independent of Service Report submission.
    """
    email = None
    if service_order:
        contact = frappe.db.get_value("Service Order", service_order, "customer_contact")
        if contact:
            email = frappe.db.get_value("Contact", contact, "email_id")
    if not email:
        return None

    try:
        pdf_bytes = _render_payment_receipt_pdf(invoice, payment_entry)
        frappe.sendmail(
            recipients=[email],
            subject=f"Payment Receipt — {invoice.name}",
            message="Please find attached your payment receipt. Thank you for your business.",
            attachments=[{"fname": f"Receipt-{payment_entry.name}.pdf", "fcontent": pdf_bytes}],
        )
        return email
    except Exception:
        frappe.log_error(title="Payment receipt email failed", message=frappe.get_traceback())
        return None


# ---- Appointment Confirmation Email (Phase 6) -------------------------------
# Fires once, on the actual transition of Service Appointment.status into
# "Scheduled" -- not on every later save while it's already Scheduled.
# set_scheduled_status() (service_appointment.py) runs on both validate()
# and before_submit(), so a naive "if status == Scheduled" check here would
# re-fire on every subsequent edit. has_value_changed() is the standard
# Frappe way to detect the actual transition. Registered as an on_update
# hook in hooks.py, not whitelisted -- an internal doc lifecycle callback,
# same class as copy_instructions_from_order below. See LCS ERPNext
# Implementation Roadmap, Section 9.2 for the resolved design.

def send_scheduled_confirmation_email(doc, method=None):
    if not (doc.has_value_changed("status") and doc.status == "Scheduled"):
        return

    email = None
    if doc.get("service_order"):
        contact = frappe.db.get_value("Service Order", doc.service_order, "customer_contact")
        if contact:
            email = frappe.db.get_value("Contact", contact, "email_id")
    if not email:
        # No email on file -- never block the actual scheduling operation
        # over a notification. Same graceful-skip precedent as
        # _send_payment_receipt_email below.
        return

    site_address = _site_address_for_order(doc.get("service_order"))

    technician_first_name = None
    if doc.get("service_technicians"):
        full_name = doc.service_technicians[0].full_name
        if full_name:
            technician_first_name = full_name.split()[0]

    window = None
    if doc.scheduled_start_datetime and doc.scheduled_finish_datetime:
        start = get_datetime(doc.scheduled_start_datetime)
        finish = get_datetime(doc.scheduled_finish_datetime)
        window = f"{start.strftime('%A, %B %-d, %Y')}, {start.strftime('%-I:%M %p')}-{finish.strftime('%-I:%M %p')}"

    lines = []
    lines.append(
        f"Your appointment is confirmed for {window}." if window
        else "Your appointment has been scheduled."
    )
    if site_address:
        lines.append(f"Site: {site_address}")
    if technician_first_name:
        lines.append(f"Your technician, {technician_first_name}, is assigned to this visit.")

    try:
        frappe.sendmail(
            recipients=[email],
            subject=f"Appointment Confirmed — {doc.name}",
            message="<br>".join(lines),
        )
    except Exception:
        frappe.log_error(title="Appointment confirmation email failed", message=frappe.get_traceback())


# ---- doc_events hooks: carry dispatch instructions forward through the ----
# ---- Service Request -> Service Order -> Service Appointment chain.    ----
# Registered in hooks.py's doc_events, not whitelisted — these are internal
# document lifecycle callbacks, not REST endpoints. Each only fills in the
# field if it's still blank, so anything typed/edited at the Order level
# is never silently overwritten by a later save.

def copy_instructions_from_request(doc, method=None):
    """Service Order.validate — pulls Service Request.description forward
    into Service Order.dispatch_instructions the first time, if blank."""
    if doc.get("service_request") and not doc.get("dispatch_instructions"):
        source_description = frappe.db.get_value("Service Request", doc.service_request, "description")
        if source_description:
            doc.dispatch_instructions = source_description


def copy_instructions_from_order(doc, method=None):
    """Service Appointment.validate — same pattern, one hop further:
    Service Order.dispatch_instructions -> Service Appointment.dispatch_instructions."""
    if doc.get("service_order") and not doc.get("dispatch_instructions"):
        source_instructions = frappe.db.get_value("Service Order", doc.service_order, "dispatch_instructions")
        if source_instructions:
            doc.dispatch_instructions = source_instructions
