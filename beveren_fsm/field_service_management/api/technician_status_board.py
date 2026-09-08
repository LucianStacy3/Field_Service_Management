"""
technician_status_board.py

Backend for the "Technician Status Board" Desk Page (Section 41 of the
roadmap) -- a dispatcher-facing, at-a-glance view of what every field
technician is doing right now: traveling, prepping the truck, onsite at
a job (and which one), paused on a job (and why), on lunch, in the shop,
or off duty for the day.

Reads LCS Tech Day Log.current_job / on_lunch / job_paused, which
submit_time_action() (see tech_pwa.py) keeps in sync on every technician
action -- this module does no derivation of its own from segment history,
it only reads today's already-current snapshot per technician and shapes
it for display.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime


# Display-status precedence when more than one flag is true at once: a
# technician can be on_lunch while job_paused is *also* still true
# underneath (see ReturnFromLunchModal's "Still Paused" path) -- lunch
# wins for display purposes since it's the more immediately relevant fact
# ("they're at lunch" matters more to a dispatcher right now than "and
# also the job under that lunch is paused").
def _display_status(day_log: dict | None) -> str:
    if not day_log:
        return "Not Started"

    day_state = day_log.get("day_state")
    if day_state == "Not Started" or day_state is None:
        return "Not Started"
    if day_state == "Ended":
        return "Off Duty"

    if day_log.get("on_lunch"):
        return "On Lunch"
    if day_log.get("job_paused"):
        return "Paused"

    open_segment_type = day_log.get("_open_segment_type")
    return {
        "Travel": "Traveling",
        "Prep": "Prepping Truck",
        "Onsite": "Onsite",
        "Shop": "In Shop",
    }.get(open_segment_type, "Active")


@frappe.whitelist()
def get_technician_status_board() -> list[dict]:
    """
    One row per Service Technician: current display status, the job
    they're on/paused on (if any) with customer name, and how long
    they've been in that status. Ordered technicians-with-something-
    happening first (Not Started / Off Duty sorted to the bottom), then
    alphabetically -- the busiest-looking board is the most useful one
    for a dispatcher scanning it.
    """
    technicians = frappe.get_all(
        "Service Technician",
        fields=["name", "full_name", "employee"],
        order_by="full_name asc",
    )
    if not technicians:
        return []

    today = frappe.utils.today()
    employee_names = [t.employee for t in technicians if t.employee]

    day_logs = frappe.get_all(
        "LCS Tech Day Log",
        filters={"employee": ["in", employee_names], "log_date": today},
        fields=[
            "name",
            "employee",
            "day_state",
            "current_job",
            "on_lunch",
            "job_paused",
            "modified",
        ],
    ) if employee_names else []
    day_log_by_employee = {d.employee: d for d in day_logs}

    # Pull each open segment's type + start_time in one query rather than
    # loading full LCS Tech Day Log docs (with their whole segments child
    # table) per technician -- this endpoint is meant to be polled every
    # few seconds by the board, so it stays index-friendly and flat.
    open_segments = {}
    if day_logs:
        rows = frappe.db.sql(
            """
            select parent, segment_type, start_time
            from `tabLCS Tech Day Log Segment`
            where parent in %(parents)s and end_time is null
            """,
            {"parents": [d.name for d in day_logs]},
            as_dict=True,
        )
        open_segments = {r.parent: r for r in rows}

    job_names = {d.current_job for d in day_logs if d.current_job}
    jobs = frappe.get_all(
        "Service Appointment",
        filters={"name": ["in", list(job_names)]},
        fields=["name", "customer"],
    ) if job_names else []
    job_by_name = {j.name: j for j in jobs}

    customer_names = {j.customer for j in jobs if j.customer}
    customers = frappe.get_all(
        "Customer",
        filters={"name": ["in", list(customer_names)]},
        fields=["name", "customer_name"],
    ) if customer_names else []
    customer_name_by_id = {c.name: c.customer_name for c in customers}

    now = now_datetime()
    rows = []
    for tech in technicians:
        log = day_log_by_employee.get(tech.employee)
        log_dict = dict(log) if log else None
        if log_dict:
            seg = open_segments.get(log_dict["name"])
            log_dict["_open_segment_type"] = seg.segment_type if seg else None
            since = seg.start_time if seg else log_dict.get("modified")
        else:
            since = None

        job = job_by_name.get(log_dict["current_job"]) if log_dict and log_dict.get("current_job") else None
        customer_name = customer_name_by_id.get(job.customer) if job else None

        status = _display_status(log_dict)
        minutes_in_status = int((now - since).total_seconds() // 60) if since else None

        rows.append({
            "technician": tech.name,
            "full_name": tech.full_name or tech.name,
            "status": status,
            "job": job.name if job else None,
            "customer_name": customer_name,
            "since": since,
            "minutes_in_status": minutes_in_status,
            "idle": status in ("Not Started", "Off Duty"),
        })

    rows.sort(key=lambda r: (r["idle"], r["full_name"]))
    return rows
