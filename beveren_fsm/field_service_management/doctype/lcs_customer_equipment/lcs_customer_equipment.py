import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, today


class LCSCustomerEquipment(Document):
	def validate(self):
		self._compute_calibration_due_date()
		self._validate_model_belongs_to_manufacturer()
		self._validate_serial_unique_per_manufacturer()
		self._validate_base_serial_unique()

	def before_save(self):
		self._compute_calibration_due_date()

	def after_insert(self):
		self._create_paired_base()

	def on_update(self):
		self._create_paired_base()

	# ------------------------------------------------------------------
	# Calibration due date
	# ------------------------------------------------------------------

	def _compute_calibration_due_date(self):
		if self.last_calibration_date and self.calibration_interval_months:
			self.calibration_due_date = add_months(
				getdate(self.last_calibration_date),
				int(self.calibration_interval_months),
			)
		elif not self.last_calibration_date:
			self.calibration_due_date = None

	# ------------------------------------------------------------------
	# Model must belong to selected manufacturer
	# ------------------------------------------------------------------

	def _validate_model_belongs_to_manufacturer(self):
		if self.scale_model and self.manufacturer:
			model_manufacturer = frappe.db.get_value("LCS Scale Model", self.scale_model, "manufacturer")
			if model_manufacturer != self.manufacturer:
				frappe.throw(
					frappe._("Model {0} belongs to {1}, not {2}.").format(
						self.scale_model, model_manufacturer, self.manufacturer
					)
				)

		if self.base_scale_model and self.base_manufacturer:
			base_model_manufacturer = frappe.db.get_value(
				"LCS Scale Model", self.base_scale_model, "manufacturer"
			)
			if base_model_manufacturer != self.base_manufacturer:
				frappe.throw(
					frappe._("Base model {0} belongs to {1}, not {2}.").format(
						self.base_scale_model, base_model_manufacturer, self.base_manufacturer
					)
				)

	# ------------------------------------------------------------------
	# Serial number uniqueness per manufacturer
	# ------------------------------------------------------------------

	def _validate_serial_unique_per_manufacturer(self):
		if not self.serial_number or not self.manufacturer:
			return

		duplicate = frappe.db.get_value(
			"LCS Customer Equipment",
			{
				"serial_number": self.serial_number,
				"manufacturer": self.manufacturer,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				frappe._(
					"Serial number {0} is already registered for manufacturer {1} " "on record {2}."
				).format(self.serial_number, self.manufacturer, duplicate)
			)

	def _validate_base_serial_unique(self):
		if not self.base_serial_number or not self.base_manufacturer:
			return

		if self.paired_component:
			return

		duplicate = frappe.db.get_value(
			"LCS Customer Equipment",
			{
				"serial_number": self.base_serial_number,
				"manufacturer": self.base_manufacturer,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				frappe._(
					"Base serial number {0} is already registered for manufacturer {1} " "on record {2}."
				).format(self.base_serial_number, self.base_manufacturer, duplicate)
			)

	# ------------------------------------------------------------------
	# Auto-create paired base record
	# ------------------------------------------------------------------

	def _create_paired_base(self):
		if self.equipment_type != "Display":
			return

		if self.paired_component:
			return

		if not self.base_manufacturer or not self.base_scale_model:
			return

		# Get base model specs to write back to the display record
		base_model = frappe.get_doc("LCS Scale Model", self.base_scale_model)

		# Create the base record
		base = frappe.new_doc("LCS Customer Equipment")
		base.customer = self.customer
		base.service_address = self.service_address
		base.status = self.status
		base.equipment_type = "Base"
		base.manufacturer = self.base_manufacturer
		base.scale_model = self.base_scale_model
		base.serial_number = self.base_serial_number
		base.capacity = self.base_capacity or base_model.capacity
		base.capacity_unit = self.base_capacity_unit or base_model.capacity_unit
		base.resolution = self.base_resolution or base_model.resolution
		base.resolution_unit = self.base_resolution_unit or base_model.resolution_unit
		base.location_description = self.location_description
		base.calibration_interval_months = self.calibration_interval_months
		base.last_calibration_date = self.last_calibration_date
		base.paired_component = self.name
		base.flags.ignore_permissions = True
		base.insert()

		# Write base capacity/resolution back to the display record
		frappe.db.set_value(
			"LCS Customer Equipment",
			self.name,
			{
				"paired_component": base.name,
				"capacity": base.capacity,
				"capacity_unit": base.capacity_unit,
				"resolution": base.resolution,
				"resolution_unit": base.resolution_unit,
			},
		)
		self.paired_component = base.name
		self.capacity = base.capacity
		self.capacity_unit = base.capacity_unit
		self.resolution = base.resolution
		self.resolution_unit = base.resolution_unit

		frappe.msgprint(
			frappe._("Paired base record {0} created automatically.").format(base.name),
			indicator="green",
			alert=True,
		)


# ------------------------------------------------------------------
# Scheduled task — nightly overdue check
# ------------------------------------------------------------------


# Days of advance notice before calibration_due_date to auto-create a
# Service Request. Resolved Aug 16, 2026 (Section 9.7) -- 30 days gives
# dispatch a full month to schedule the recalibration visit.
CALIBRATION_LEAD_DAYS = 30


def flag_overdue_equipment():
	"""
	Nightly scheduler task (registered in hooks.py's scheduler_events --
	unchanged by this Phase 6 addition, same function name kept on purpose
	so no hooks.py edit was needed).

	Two passes, per LCS ERPNext Implementation Roadmap Section 9.4:
	1. Equipment approaching its calibration_due_date (within
	   CALIBRATION_LEAD_DAYS) gets a Service Request auto-created, unless
	   one already exists for it. Modeled directly on
	   lcs_service_agreement.auto_create_service_orders()'s per-record
	   error-isolated pattern -- one bad equipment record can't block the
	   rest.
	2. Equipment that's already overdue and still has no Service Request
	   at all (the original behavior, kept as a safety net) is logged to
	   the Error Log for visibility.
	"""
	_create_calibration_service_requests()
	_log_overdue_without_service_request()


def _has_open_service_request(equipment_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"Service Request",
			{"custom_customer_equipment": equipment_name, "status": ["!=", "Closed"]},
		)
	)


def _create_calibration_service_requests():
	window_end = add_days(today(), CALIBRATION_LEAD_DAYS)

	candidates = frappe.get_all(
		"LCS Customer Equipment",
		filters={
			"status": "Active",
			"calibration_due_date": ["between", [today(), window_end]],
		},
		fields=["name", "customer", "manufacturer", "scale_model", "serial_number", "calibration_due_date"],
	)

	for row in candidates:
		try:
			if _has_open_service_request(row.name):
				continue

			company = _default_company()
			company_currency = frappe.get_cached_value("Company", company, "default_currency")

			sr = frappe.new_doc("Service Request")
			sr.customer = row.customer
			sr.custom_customer_equipment = row.name
			sr.due_date = row.calibration_due_date
			sr.posting_date = today()
			sr.company = company
			sr.currency = company_currency
			# "Inspection" reused per Lucian's decision (Section 9.7) --
			# none of the six existing Service Types name calibration
			# work specifically, and a new one wasn't warranted.
			sr.type = "Inspection"
			sr.priority = "Medium"
			sr.subject = f"Calibration due — {row.scale_model or row.manufacturer}, {row.serial_number}"
			sr.insert(ignore_permissions=True)

			frappe.logger().info(
				f"LCS Customer Equipment {row.name}: created Service Request {sr.name} "
				f"(calibration due {row.calibration_due_date})"
			)
		except Exception:
			frappe.log_error(
				title=f"Calibration Service Request auto-create failed — {row.name}",
				message=frappe.get_traceback(),
			)


def _log_overdue_without_service_request():
	overdue = frappe.get_all(
		"LCS Customer Equipment",
		filters={
			"status": "Active",
			"calibration_due_date": ["<", today()],
		},
		fields=["name", "customer", "manufacturer", "scale_model", "serial_number", "calibration_due_date"],
	)
	if not overdue:
		return

	still_uncovered = [row for row in overdue if not _has_open_service_request(row.name)]
	if not still_uncovered:
		return

	frappe.log_error(
		message=frappe.as_json(still_uncovered),
		title=f"LCS Customer Equipment - Overdue Calibrations With No Service Request ({len(still_uncovered)})",
	)


def _default_company():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		companies = frappe.get_all("Company", pluck="name", limit=1)
		company = companies[0] if companies else None
	if not company:
		frappe.throw("No Company exists on this site yet. Complete the ERPNext Setup Wizard first.")
	return company
