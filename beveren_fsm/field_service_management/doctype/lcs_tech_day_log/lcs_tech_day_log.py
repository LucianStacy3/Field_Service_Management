# Copyright (c) 2026, Left Coast Scales, LLC and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime

ATTENDANCE_SHIFT = "LCS Standard"  # every technician currently works this shift; no Shift Assignment records exist yet


class LCSTechDayLog(Document):
	"""
	One row per technician per calendar date. `segments` is the gapless
	chain described in the Time-Tracking Proposal (Travel/Prep/Onsite/Shop),
	written primarily via beveren_fsm.field_service_management.api.tech_pwa
	rather than opened directly in Desk during normal operation.
	"""

	def validate(self):
		self.needs_review_count = sum(1 for s in self.segments if s.flagged_for_review)
		self._compute_totals()

	def on_update(self):
		self._maybe_create_attendance()

	def _compute_totals(self):
		total_minutes = 0
		for seg in self.segments:
			if not seg.end_time:
				continue
			# submit_time_action() sets end_time/start_time from raw API string
			# params on segments that were already loaded from the DB (where
			# Frappe's own load path already cast them to datetime objects) —
			# a plain attribute assignment doesn't trigger that cast, so this
			# can see a str on one side and a datetime on the other by the
			# time validate() runs. get_datetime() normalizes either shape
			# and is a no-op if the value is already a datetime.
			gross = (get_datetime(seg.end_time) - get_datetime(seg.start_time)).total_seconds() / 60
			# Lunch is unpaid and comes off net/paid time. A job pause
			# (parts, waiting on customer, etc.) stays on the clock for
			# payroll — it's paid — so seg.pause_minutes is deliberately
			# NOT subtracted here. It's tracked on the segment purely so
			# it can be excluded from customer billing elsewhere, without
			# reducing what the technician is paid for.
			net = max(0, gross - (seg.lunch_minutes or 0))
			seg.net_minutes = round(net)
			total_minutes += seg.net_minutes

		self.total_paid_minutes = round(total_minutes)

		scheduled = 600 if self.schedule_type == "CA Alternative" else 480
		doubletime_threshold = 720
		self.overtime_minutes = max(0, min(self.total_paid_minutes, doubletime_threshold) - scheduled)
		self.doubletime_minutes = max(0, self.total_paid_minutes - doubletime_threshold)

	def _maybe_create_attendance(self):
		"""
		Creates a DRAFT Attendance record once this day is fully wrapped up:
		day_state is Ended, and there are no unresolved flagged segments
		left for the office to review. Runs on every save (on_update), so
		it fires correctly whether the day just ended cleanly, or a flag
		gets cleared later by someone editing this record in Desk.

		Deliberately left as a draft (docstatus 0) — HR reviews and
		submits it themselves; this never auto-submits. Only creates once
		per employee/date — if an Attendance already exists (however it
		got there), this leaves it alone rather than overwriting it.

		Wrapped in try/except: on_update runs inside the same transaction
		as this doc's own save, so an unhandled exception here (e.g. a
		data issue on the Employee record) would roll back the day log
		save itself — which would then block a technician's time-tracking
		sync over an HR-side data problem. Logged instead, so it's visible
		without being able to break the more important save.
		"""
		if self.day_state != "Ended" or self.needs_review_count:
			return
		if not self.segments:
			return
		if frappe.db.exists("Attendance", {"employee": self.employee, "attendance_date": self.log_date}):
			return

		try:
			company = frappe.db.get_value("Employee", self.employee, "company")
			first_segment = self.segments[0]
			last_segment = self.segments[-1]

			attendance = frappe.get_doc({
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": self.log_date,
				"status": "Present",
				"company": company,
				"shift": ATTENDANCE_SHIFT,
				"in_time": first_segment.start_time,
				"out_time": last_segment.end_time,
				"working_hours": round((self.total_paid_minutes or 0) / 60, 2),
			})
			attendance.insert(ignore_permissions=True)  # left as draft — no attendance.submit() call
		except Exception:
			frappe.log_error(
				title=f"LCS Tech Day Log: Attendance auto-create failed for {self.name}",
				message=frappe.get_traceback(),
			)
