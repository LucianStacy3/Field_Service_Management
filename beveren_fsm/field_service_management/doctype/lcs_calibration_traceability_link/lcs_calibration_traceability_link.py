# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class LCSCalibrationTraceabilityLink(Document):
	pass


def is_standard_in_cal_on(reference_standard: str, used_on_date) -> bool:
	"""Was `reference_standard` in calibration on `used_on_date`?

	Shared helper (not just a method on this child doctype) because the
	actual validation has to run from the parent Service Order's own
	validate() -- reusing the Phase 2C overlap-validation shape, where
	Service Appointment.validate_overlap() iterates its own child rows
	rather than relying on child-row controllers being invoked directly.
	"""
	if not reference_standard or not used_on_date:
		return False

	std = frappe.db.get_value(
		"LCS Reference Standard",
		reference_standard,
		["status", "recalibration_due_date"],
		as_dict=True,
	)
	if not std:
		return False

	if std.status in ("Out for Recalibration", "Retired"):
		return False

	if not std.recalibration_due_date:
		# No due date computed yet (missing Last Certified Date / interval)
		# -- can't confirm in-cal, so treat as not in-cal rather than
		# silently passing an unverifiable standard.
		return False

	return getdate(used_on_date) <= getdate(std.recalibration_due_date)
