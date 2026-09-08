# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document

from beveren_fsm.field_service_management.utils.status_log import log_status_change


class LCSNCR(Document):
	def validate(self):
		self._validate_disposition_approval()

	def on_update(self):
		log_status_change(self)
		self._sync_out_of_service_tag()

	def _validate_disposition_approval(self):
		"""Redundant with mandatory_depends_on in the DocType JSON on purpose --
		server-side validation is the real gatekeeper (Section 8), client-side
		conditional-mandatory can be bypassed via the API."""
		if self.disposition == "Accept with Justification" and not self.customer_approval_reference:
			frappe.throw(
				frappe._("Accept with Justification requires a Customer Approval Reference (SOP-013 5.4.2).")
			)

	def _sync_out_of_service_tag(self):
		"""One-directional: checking this box tags the linked Customer
		Equipment record. Unchecking it does NOT auto-clear the tag, since
		another open NCR could still apply to the same equipment -- clearing
		is a deliberate edit on the Customer Equipment record itself."""
		if not (self.tag_equipment_out_of_service and self.customer_equipment):
			return

		frappe.db.set_value(
			"LCS Customer Equipment",
			self.customer_equipment,
			{
				"custom_out_of_service": 1,
				"custom_out_of_service_reason": frappe.utils.strip_html(self.description_of_nonconformity or ""),
				"custom_out_of_service_tagged_by": self.identified_by,
				"custom_out_of_service_date": self.date_identified,
			},
		)
