# Copyright (c) 2026, Left Coast Scales LLC
# field_service_management/api/vehicle_inspection.py

import frappe
from frappe.utils import today, now_datetime


def _get_employee():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not permitted", frappe.PermissionError)
	employee = frappe.db.get_value(
		"Employee", {"user_id": user, "status": "Active"},
		["name", "employee_name", "branch"], as_dict=True,
	)
	if not employee:
		frappe.throw("No active Employee record found for your login.")
	return employee


@frappe.whitelist()
def get_dot_page_state():
	"""
	Returns the state the DOT inspection page should render in:
	  - mode: 'pre_trip' (no open record today) or 'post_trip' (open record exists)
	  - record: the open record name if post_trip mode
	  - plus vehicle defaults for pre_trip mode
	"""
	employee = _get_employee()
	today_date = today()

	# Check for an open (Pre-Trip Complete) record for today
	open_record = frappe.db.get_value(
		"LCS DOT Inspection",
		{"driver": employee.name, "inspection_date": today_date, "inspection_status": "Pre-Trip Complete"},
		["name", "vehicle", "odometer_start", "dispatch_branch",
		 "vehicle_year_make_model", "license_plate", "plate_state", "vin_last_4"],
		order_by="creation desc",
		as_dict=True,
	)

	if open_record:
		return {
			"mode": "post_trip",
			"record": open_record,
			"employee_name": employee.employee_name,
			"employee_id": employee.name,
			"today": today_date,
		}

	# No open record — pre-trip mode, return vehicle defaults
	vehicles = frappe.get_all(
		"LCS Vehicle",
		filters={"form_type": "DOT", "status": "Active"},
		fields=["name", "unit_number", "nickname", "year", "make", "model",
		        "vin_last_4", "license_plate", "plate_state", "branch",
		        "last_odometer", "vehicle_type"],
		order_by="branch asc, unit_number asc",
	)
	for v in vehicles:
		nick = f" ({v.nickname})" if v.nickname else ""
		v["display_label"] = f"{v.year} {v.make} {v.model}{nick} - VIN {v.vin_last_4}"

	last_insp = frappe.db.get_value(
		"LCS DOT Inspection",
		{"driver": employee.name},
		["vehicle", "odometer_end", "odometer_start"],
		order_by="inspection_date desc, creation desc",
		as_dict=True,
	)
	last_vehicle = None
	last_odometer = 0
	if last_insp:
		last_vehicle = last_insp.vehicle
		last_odometer = last_insp.odometer_end or last_insp.odometer_start or 0
	if last_vehicle:
		master_odo = frappe.db.get_value("LCS Vehicle", last_vehicle, "last_odometer")
		if master_odo:
			last_odometer = master_odo

	return {
		"mode": "pre_trip",
		"employee_name": employee.employee_name,
		"employee_id": employee.name,
		"branch": employee.branch or "",
		"vehicles": vehicles,
		"last_vehicle": last_vehicle,
		"last_odometer": last_odometer,
		"today": today_date,
	}


@frappe.whitelist()
def get_vehicle_defaults(form_type):
	"""Legacy endpoint — kept for light vehicle form."""
	employee = _get_employee()
	vehicles = frappe.get_all(
		"LCS Vehicle",
		filters={"form_type": form_type, "status": "Active"},
		fields=["name", "unit_number", "nickname", "year", "make", "model",
		        "vin_last_4", "license_plate", "plate_state", "branch",
		        "last_odometer", "last_driver", "vehicle_type"],
		order_by="branch asc, unit_number asc",
	)
	for v in vehicles:
		nick = f" ({v.nickname})" if v.nickname else ""
		v["display_label"] = f"{v.year} {v.make} {v.model}{nick} - VIN {v.vin_last_4}"

	doctype = "LCS DOT Inspection" if form_type == "DOT" else "LCS Light Vehicle Inspection"
	last_insp = frappe.db.get_value(
		doctype, {"driver": employee.name},
		["vehicle", "odometer_end", "odometer_start"],
		order_by="inspection_date desc, creation desc", as_dict=True,
	)
	last_vehicle = None
	last_odometer = 0
	if last_insp:
		last_vehicle = last_insp.vehicle
		last_odometer = last_insp.odometer_end or last_insp.odometer_start or 0
	if last_vehicle:
		master_odo = frappe.db.get_value("LCS Vehicle", last_vehicle, "last_odometer")
		if master_odo:
			last_odometer = master_odo

	return {
		"employee_name": employee.employee_name,
		"employee_id": employee.name,
		"branch": employee.branch or "",
		"vehicles": vehicles,
		"last_vehicle": last_vehicle,
		"last_odometer": last_odometer,
		"today": today(),
	}


@frappe.whitelist()
def get_vehicle_odometer(vehicle):
	if frappe.session.user == "Guest":
		frappe.throw("Not permitted", frappe.PermissionError)
	odometer = frappe.db.get_value("LCS Vehicle", vehicle, "last_odometer")
	return {"last_odometer": odometer or 0}


@frappe.whitelist(methods=["POST"])
def submit_dot_pretrip(data):
	"""Create a new LCS DOT Inspection with pre-trip data. Status = Pre-Trip Complete."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	vehicle = frappe.get_doc("LCS Vehicle", data.get("vehicle"))

	doc = frappe.new_doc("LCS DOT Inspection")
	doc.update(data)
	doc.driver = employee.name
	doc.inspection_status = "Pre-Trip Complete"
	doc.vehicle_year_make_model = f"{vehicle.year} {vehicle.make} {vehicle.model}"
	doc.license_plate = vehicle.license_plate or ""
	doc.plate_state = vehicle.plate_state or ""
	doc.vin_last_4 = vehicle.vin_last_4 or ""
	if doc.pt_certified:
		doc.pt_certified_time = now_datetime()

	doc.insert(ignore_permissions=True)
	doc.save(ignore_permissions=True)

	# Update vehicle master with start odometer
	if data.get("odometer_start"):
		vehicle.last_odometer = int(data["odometer_start"])
		vehicle.last_odometer_date = data.get("inspection_date") or today()
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}


@frappe.whitelist(methods=["POST"])
def submit_dot_posttrip(data):
	"""Update an existing LCS DOT Inspection with post-trip data. Status = Complete."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	record_name = data.get("record_name")
	if not record_name:
		frappe.throw("No inspection record specified.")

	doc = frappe.get_doc("LCS DOT Inspection", record_name)

	# Verify this driver owns the record
	if doc.driver != employee.name:
		frappe.throw("You are not authorized to update this inspection.")

	# Update post-trip fields
	doc.odometer_end = int(data.get("odometer_end") or 0) or None
	doc.fuel_level = data.get("fuel_level") or ""
	doc.post_brakes = data.get("post_brakes") or "OK"
	doc.post_steering = data.get("post_steering") or "OK"
	doc.post_lights = data.get("post_lights") or "OK"
	doc.post_tires = data.get("post_tires") or "OK"
	doc.post_engine = data.get("post_engine") or "OK"
	doc.post_body = data.get("post_body") or "OK"
	doc.post_safety = data.get("post_safety") or "OK"
	doc.post_cargo = data.get("post_cargo") or "OK"
	doc.post_defect_remarks = data.get("post_defect_remarks") or ""
	doc.post_certified = 1 if data.get("post_certified") else 0
	if doc.post_certified:
		doc.post_certified_time = now_datetime()

	# Compute total miles
	if doc.odometer_start and doc.odometer_end:
		doc.total_miles = max(0, doc.odometer_end - doc.odometer_start)

	doc.inspection_status = "Complete"
	doc.save(ignore_permissions=True)

	# Update vehicle master with end odometer
	if doc.odometer_end:
		vehicle = frappe.get_doc("LCS Vehicle", doc.vehicle)
		vehicle.last_odometer = doc.odometer_end
		vehicle.last_odometer_date = doc.inspection_date
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}


@frappe.whitelist(methods=["POST"])
def submit_dot_inspection(data):
	"""Legacy single-submit endpoint — kept for compatibility."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	vehicle = frappe.get_doc("LCS Vehicle", data.get("vehicle"))

	doc = frappe.new_doc("LCS DOT Inspection")
	doc.update(data)
	doc.driver = employee.name
	doc.inspection_status = "Complete"
	doc.vehicle_year_make_model = f"{vehicle.year} {vehicle.make} {vehicle.model}"
	doc.license_plate = vehicle.license_plate or ""
	doc.plate_state = vehicle.plate_state or ""
	doc.vin_last_4 = vehicle.vin_last_4 or ""
	if doc.pt_certified:
		doc.pt_certified_time = now_datetime()
	if doc.post_certified:
		doc.post_certified_time = now_datetime()

	doc.insert(ignore_permissions=True)
	doc.save(ignore_permissions=True)

	odometer = data.get("odometer_end") or data.get("odometer_start")
	if odometer:
		vehicle.last_odometer = int(odometer)
		vehicle.last_odometer_date = data.get("inspection_date") or today()
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}


@frappe.whitelist(methods=["POST"])
def submit_light_inspection(data):
	"""Create and save an LCS Light Vehicle Inspection from the web form."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	vehicle = frappe.get_doc("LCS Vehicle", data.get("vehicle"))

	doc = frappe.new_doc("LCS Light Vehicle Inspection")
	doc.update(data)
	doc.driver = employee.name
	doc.vehicle_type = vehicle.vehicle_type
	doc.vehicle_year_make = f"{vehicle.year} {vehicle.make} {vehicle.model}"
	doc.unit_fleet_number = vehicle.unit_number
	doc.license_plate = vehicle.license_plate or ""
	doc.plate_state = vehicle.plate_state or ""

	if doc.pd_certified:
		doc.pd_certified_time = now_datetime()
	if doc.eod_certified:
		doc.eod_certified_time = now_datetime()

	doc.insert(ignore_permissions=True)
	doc.save(ignore_permissions=True)

	odometer = data.get("odometer_end") or data.get("odometer_start")
	if odometer:
		vehicle.last_odometer = int(odometer)
		vehicle.last_odometer_date = data.get("inspection_date") or today()
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}


@frappe.whitelist()
def get_light_page_state():
	"""
	Returns the state the light vehicle inspection page should render in:
	  - mode: 'pre_departure' or 'post_trip'
	"""
	employee = _get_employee()
	today_date = today()

	open_record = frappe.db.get_value(
		"LCS Light Vehicle Inspection",
		{"driver": employee.name, "inspection_date": today_date, "inspection_status": "Pre-Departure Complete"},
		["name", "vehicle", "odometer_start", "dispatch_branch",
		 "vehicle_year_make", "vehicle_type", "unit_fleet_number",
		 "license_plate", "plate_state"],
		order_by="creation desc",
		as_dict=True,
	)

	if open_record:
		return {
			"mode": "post_trip",
			"record": open_record,
			"employee_name": employee.employee_name,
			"employee_id": employee.name,
			"today": today_date,
		}

	vehicles = frappe.get_all(
		"LCS Vehicle",
		filters={"form_type": "Light Vehicle", "status": "Active"},
		fields=["name", "unit_number", "nickname", "year", "make", "model",
		        "vin_last_4", "license_plate", "plate_state", "branch",
		        "last_odometer", "vehicle_type"],
		order_by="branch asc, unit_number asc",
	)
	for v in vehicles:
		nick = f" ({v.nickname})" if v.nickname else ""
		v["display_label"] = f"{v.year} {v.make} {v.model}{nick} - VIN {v.vin_last_4}"

	last_insp = frappe.db.get_value(
		"LCS Light Vehicle Inspection",
		{"driver": employee.name},
		["vehicle", "odometer_end", "odometer_start"],
		order_by="inspection_date desc, creation desc",
		as_dict=True,
	)
	last_vehicle = None
	last_odometer = 0
	if last_insp:
		last_vehicle = last_insp.vehicle
		last_odometer = last_insp.odometer_end or last_insp.odometer_start or 0
	if last_vehicle:
		master_odo = frappe.db.get_value("LCS Vehicle", last_vehicle, "last_odometer")
		if master_odo:
			last_odometer = master_odo

	return {
		"mode": "pre_departure",
		"employee_name": employee.employee_name,
		"employee_id": employee.name,
		"branch": employee.branch or "",
		"vehicles": vehicles,
		"last_vehicle": last_vehicle,
		"last_odometer": last_odometer,
		"today": today_date,
	}


@frappe.whitelist(methods=["POST"])
def submit_light_pretrip(data):
	"""Create a new LCS Light Vehicle Inspection with pre-departure data."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	vehicle = frappe.get_doc("LCS Vehicle", data.get("vehicle"))

	doc = frappe.new_doc("LCS Light Vehicle Inspection")
	doc.update(data)
	doc.driver = employee.name
	doc.inspection_status = "Pre-Departure Complete"
	doc.vehicle_type = vehicle.vehicle_type
	doc.vehicle_year_make = f"{vehicle.year} {vehicle.make} {vehicle.model}"
	doc.unit_fleet_number = vehicle.unit_number
	doc.license_plate = vehicle.license_plate or ""
	doc.plate_state = vehicle.plate_state or ""

	if doc.pd_certified:
		doc.pd_certified_time = now_datetime()

	doc.insert(ignore_permissions=True)
	doc.save(ignore_permissions=True)

	if data.get("odometer_start"):
		vehicle.last_odometer = int(data["odometer_start"])
		vehicle.last_odometer_date = data.get("inspection_date") or today()
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}


@frappe.whitelist(methods=["POST"])
def submit_light_posttrip(data):
	"""Update an existing LCS Light Vehicle Inspection with end-of-day data."""
	import json
	if isinstance(data, str):
		data = json.loads(data)

	employee = _get_employee()
	record_name = data.get("record_name")
	if not record_name:
		frappe.throw("No inspection record specified.")

	doc = frappe.get_doc("LCS Light Vehicle Inspection", record_name)

	if doc.driver != employee.name:
		frappe.throw("You are not authorized to update this inspection.")

	doc.odometer_end = int(data.get("odometer_end") or 0) or None
	doc.fuel_level = data.get("fuel_level") or ""
	doc.eod_exterior = data.get("eod_exterior") or "OK"
	doc.eod_lights = data.get("eod_lights") or "OK"
	doc.eod_tires = data.get("eod_tires") or "OK"
	doc.eod_brakes = data.get("eod_brakes") or "OK"
	doc.eod_fluid_leaks = data.get("eod_fluid_leaks") or "OK"
	doc.eod_equipment_returned = data.get("eod_equipment_returned") or "OK"
	doc.eod_fuel_adequate = data.get("eod_fuel_adequate") or "OK"
	doc.eod_vehicle_secured = data.get("eod_vehicle_secured") or "OK"
	doc.eod_keys_returned = data.get("eod_keys_returned") or "OK"
	doc.eod_new_defects = data.get("eod_new_defects") or ""
	doc.eod_fuel_added = float(data.get("eod_fuel_added") or 0) or None
	doc.eod_fuel_location = data.get("eod_fuel_location") or ""
	doc.eod_receipt_number = data.get("eod_receipt_number") or ""
	doc.eod_certified = 1 if data.get("eod_certified") else 0
	if doc.eod_certified:
		doc.eod_certified_time = now_datetime()

	doc.inspection_status = "Complete"
	doc.save(ignore_permissions=True)

	if doc.odometer_end:
		vehicle = frappe.get_doc("LCS Vehicle", doc.vehicle)
		vehicle.last_odometer = doc.odometer_end
		vehicle.last_odometer_date = doc.inspection_date
		vehicle.last_driver = employee.name
		vehicle.save(ignore_permissions=True)

	return {"name": doc.name, "status": "success"}