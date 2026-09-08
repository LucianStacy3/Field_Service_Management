# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, get_last_day, getdate, today

from beveren_fsm.field_service_management.utils.status_log import log_status_change


class LCSReferenceStandard(Document):
	def validate(self):
		self._compute_recalibration_due_date()

	def before_save(self):
		self._compute_recalibration_due_date()

	def on_update(self):
		log_status_change(self)

	# ------------------------------------------------------------------
	# Recalibration due date
	# ------------------------------------------------------------------

	def _compute_recalibration_due_date(self):
		"""Same computed-field pattern as LCS Customer Equipment's
		calibration_due_date, with one refinement: the issuing lab's own
		certificates state validity as "one year -- recertify by the last
		day of the original test month," not an exact day-for-day
		anniversary. Rounding up to month-end matches that convention and
		errs slightly conservative (never earlier than the lab's own
		due date)."""
		if self.last_certified_date and self.recalibration_interval_months:
			target_month = add_months(getdate(self.last_certified_date), int(self.recalibration_interval_months))
			self.recalibration_due_date = get_last_day(target_month)
		elif not self.last_certified_date:
			self.recalibration_due_date = None


# ------------------------------------------------------------------
# Scheduled task -- nightly recalibration-due check
# ------------------------------------------------------------------

# Mirrors CALIBRATION_LEAD_DAYS on LCS Customer Equipment / REVIEW_LEAD_DAYS
# on LCS Controlled Document -- same 30-day house convention.
RECALIBRATION_LEAD_DAYS = 30


def flag_reference_standards_due_for_recalibration():
	"""Nightly scheduler task (registered in hooks.py).

	Unlike LCS Customer Equipment, there's no customer/Service Request to
	auto-create here -- these are LCS's own field standards. This is a
	visibility-only safety net: log approaching and overdue standards so
	Quality/Dispatch can pull them off trucks and send them out for
	recalibration before an auditor -- or a technician relying on an
	out-of-cal standard -- finds out the hard way.
	"""
	_log_upcoming_recalibrations()
	_log_overdue_still_in_service()


def _log_upcoming_recalibrations():
	window_end = add_days(today(), RECALIBRATION_LEAD_DAYS)

	candidates = frappe.get_all(
		"LCS Reference Standard",
		filters={
			"status": "In Service",
			"recalibration_due_date": ["between", [today(), window_end]],
		},
		fields=["name", "reference_standard_id", "owning_test_truck", "recalibration_due_date"],
	)
	if not candidates:
		return

	frappe.log_error(
		message=frappe.as_json(candidates),
		title=f"LCS Reference Standard - Recalibration Due Within {RECALIBRATION_LEAD_DAYS} Days ({len(candidates)})",
	)


def _log_overdue_still_in_service():
	overdue = frappe.get_all(
		"LCS Reference Standard",
		filters={
			"status": "In Service",
			"recalibration_due_date": ["<", today()],
		},
		fields=["name", "reference_standard_id", "owning_test_truck", "recalibration_due_date"],
	)
	if not overdue:
		return

	frappe.log_error(
		message=frappe.as_json(overdue),
		title=f"LCS Reference Standard - Overdue Recalibration, Still Tagged In Service ({len(overdue)})",
	)
