# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document


class LCSAudit(Document):
	def validate(self):
		self._default_follow_up_status()

	def _default_follow_up_status(self):
		"""A major nonconformity always needs a follow-up review -- don't let
		it silently sit at 'Not Required'."""
		if self.major_nonconformity_found and self.follow_up_status in (None, "", "Not Required"):
			self.follow_up_status = "Pending"
