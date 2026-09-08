# Copyright (c) 2026, Left Coast Scales, LLC and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class LCSAppointmentPhoto(Document):
	def before_insert(self):
		if not self.taken_by:
			self.taken_by = frappe.session.user
		if not self.taken_at:
			self.taken_at = frappe.utils.now_datetime()
