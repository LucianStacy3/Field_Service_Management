# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class LCSLightVehicleInspection(Document):

	def before_save(self):
		if self.pd_certified and not self.pd_certified_time:
			self.pd_certified_time = now_datetime()

		if self.eod_certified and not self.eod_certified_time:
			self.eod_certified_time = now_datetime()

	def on_submit(self):
		self._update_vehicle_odometer()

	def on_update_after_submit(self):
		self._update_vehicle_odometer()

	def _update_vehicle_odometer(self):
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