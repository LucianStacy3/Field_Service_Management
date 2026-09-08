# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class LCSDOTInspection(Document):

	def before_save(self):
		# Compute total miles if both odometer readings are present
		if self.odometer_start and self.odometer_end:
			self.total_miles = max(0, self.odometer_end - self.odometer_start)

		# Stamp certification time when pre-trip certified
		if self.pt_certified and not self.pt_certified_time:
			self.pt_certified_time = now_datetime()

		# Stamp post-trip certification time
		if self.post_certified and not self.post_certified_time:
			self.post_certified_time = now_datetime()

	def on_submit(self):
		self._update_vehicle_odometer()

	def on_update_after_submit(self):
		self._update_vehicle_odometer()

	def _update_vehicle_odometer(self):
		"""Push the latest odometer reading back to the LCS Vehicle master."""
		if not self.vehicle:
			return
		odometer = self.odometer_end or self.odometer_start
		if not odometer:
			return
		vehicle = frappe.get_doc("LCS Vehicle", self.vehicle)
		if not vehicle.last_odometer or odometer > vehicle.last_odometer:
			vehicle.last_odometer = odometer
			vehicle.last_odometer_date = self.inspection_date
			vehicle.last_driver = self.driver
			vehicle.save(ignore_permissions=True)