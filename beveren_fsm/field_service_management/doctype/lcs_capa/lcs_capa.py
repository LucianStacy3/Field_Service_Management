# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document

from beveren_fsm.field_service_management.utils.status_log import log_status_change


class LCSCAPA(Document):
	def validate(self):
		self._validate_ncr_required_for_corrective()

	def on_update(self):
		log_status_change(self)

	def _validate_ncr_required_for_corrective(self):
		if self.action_type == "Corrective" and not self.ncr:
			frappe.throw(
				frappe._("Corrective CAPAs must link the NCR whose root cause they address (SOP-013 5.7).")
			)
