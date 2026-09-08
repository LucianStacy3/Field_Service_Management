import json

import frappe
from frappe import _

# Create Invoice moves real accounting data (a Sales Invoice) — restricted to
# Accounting department staff and the Service Administrator role, not
# dispatchers or crew leads. Desk-only; there's no PWA entry point for this.
INVOICE_CREATION_ROLES = ["System Manager", "Accounts Manager", "Accounts User", "Service Administrator"]


@frappe.whitelist()
def create_service_invoice(doctype, docname, customer, items=None):
	if not set(INVOICE_CREATION_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only Accounting staff or a Service Administrator can create invoices."),
			frappe.PermissionError,
		)

	items = json.loads(items) if items else []
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.due_date = frappe.utils.nowdate()
	invoice.custom_reference_service_doctype = doctype
	invoice.custom_reference_service_document = docname
	for item in items:
		invoice.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["qty"],
				"rate": item["rate"],
				"amount": item["amount"],
			},
		)
	invoice.insert()
	return invoice.name


def update_invoice_status(doc, method):
	if not (doc.custom_reference_service_doctype and doc.custom_reference_service_document):
		return

	new_status = "Invoiced" or "Partly Invoiced" if method == "on_submit" else "Not Invoiced"

	# Retrieve all item codes from the Sales Invoice
	invoice_item_codes = {
		item["item_code"]: item["qty"]
		for item in frappe.get_all(
			"Sales Invoice Item", filters={"parent": doc.name}, fields=["item_code", "qty"]
		)
	}

	# Load the referenced service document
	ref_doctype = doc.custom_reference_service_doctype
	ref_docname = doc.custom_reference_service_document
	service_doc = frappe.get_doc(ref_doctype, ref_docname)

	updated = False
	child_tables = ["items"]  # Extend this list if there are more child tables to update (Services, Parts)
	for table in child_tables:
		if not hasattr(service_doc, table):
			frappe.throw(f"No '{table}' child table found in {ref_doctype}")

		for row in getattr(service_doc, table):
			invoiced_qty = invoice_item_codes[row.item_code]
			if row.item_code in invoice_item_codes.keys():
				row.invoiced_qty += invoiced_qty
				if row.invoice_status != new_status:
					if row.qty > invoiced_qty > 0:
						row.invoice_status = "Partly Invoiced"
					if row.qty == invoiced_qty:
						row.invoice_status = "Invoiced"

					updated = True

	if updated:
		service_doc.save()
		frappe.msgprint(
			f"Updated invoice status for <strong>Services and Parts</strong> in "
			f"<strong>{ref_doctype}</strong> {ref_docname}"
		)

	update_associated_docs_invoice_status(doc, method)


def update_associated_docs_invoice_status(doc, method):
	if not (doc.custom_reference_service_doctype and doc.custom_reference_service_document):
		return

	source_doc = frappe.get_doc(doc.custom_reference_service_doctype, doc.custom_reference_service_document)
	source_items = source_doc.get("items", [])

	possible_doctypes = {"Service Order", "Service Appointment"}
	target_doctype = (possible_doctypes - {doc.custom_reference_service_doctype}).pop()

	if target_doctype == "Service Order":
		target_docnames = [source_doc.service_order] if source_doc.service_order else []
	elif target_doctype == "Service Appointment":
		target_docnames = frappe.get_all(
			target_doctype, filters={"service_order": source_doc.name}, pluck="name"
		)
	else:
		target_docnames = []

	# For Service Appointments, update other similar appointments in the same order
	if doc.custom_reference_service_doctype == "Service Appointment":
		similar_appointments = frappe.get_all(
			source_doc.doctype,
			filters={"service_order": source_doc.service_order, "name": ["!=", source_doc.name]},
			pluck="name",
		)
		for appointment_name in similar_appointments:
			update_target_documents(source_doc.doctype, appointment_name, source_items)

	for target_name in target_docnames:
		update_target_documents(target_doctype, target_name, source_items)


def update_target_documents(target_doctype, target_docname, source_items):
	target_doc = frappe.get_doc(target_doctype, target_docname)

	# Build a lookup for items in the target document by item_code
	target_items_lookup = {row.item_code: row for row in target_doc.get("items", [])}

	updated = False
	for item in source_items:
		target_row = target_items_lookup.get(item.item_code)
		# Update only if the invoice status is different from the source's current status
		if target_row and target_row.invoice_status != item.invoice_status:
			target_row.invoice_status = item.invoice_status
			target_row.invoiced_qty = item.invoiced_qty
			updated = True

	if updated:
		target_doc.save()
		frappe.msgprint(
			f"Updated invoice status for <strong>Services and Parts</strong> in "
			f"<strong>{target_doctype}</strong> {target_docname}"
		)


def update_per_billed_status(doc, method):
	total_amount = 0.0
	billed_amount = 0.0

	if not (doc.custom_reference_service_doctype or doc.custom_reference_service_document):
		return

	ref_doc = frappe.get_doc(doc.custom_reference_service_doctype, doc.custom_reference_service_document)

	for item in ref_doc.get("items", []):
		full_amount = item.amount or 0.0
		total_amount += full_amount

		invoiced_qty = item.get("invoiced_qty", 0)
		item_qty = item.qty or 0
		proportion_invoiced = (invoiced_qty / item_qty) if item_qty else 0

		billed_amount += full_amount * proportion_invoiced

	ref_doc.per_billed = (billed_amount / total_amount) * 100 if total_amount else 0.0
	ref_doc.save()


@frappe.whitelist()
def update_appointment_from_api(
	name, scheduled_start_datetime, scheduled_finish_datetime, service_technicians, items
):
	appointment = frappe.get_doc("Service Appointment", name)
	# delete all items from the appointment
	appointment.service_technicians = []
	appointment.items = []

	for item in items:
		appointment.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["qty"],
				"rate": item["rate"],
				"amount": item["amount"],
			},
		)

	for service_technician in service_technicians:
		appointment.append(
			"service_technicians",
			{
				"service_technician": service_technician["service_technician"],
				"full_name": service_technician["full_name"],
				# "service_area": service_technician["service_area"],
				# "specialization": service_technician["specialization"]
			},
		)

	appointment.scheduled_start_datetime = scheduled_start_datetime
	appointment.scheduled_finish_datetime = scheduled_finish_datetime

	appointment.save()
	return appointment.name


@frappe.whitelist()
def make_service_order_from_quotation(source_name, target_doc=None):
	"""
	CRM bridge for sales-originated service work (new Service Agreements,
	quoted repairs, installations): maps a submitted, standard ERPNext
	Quotation onto a new Service Order.

	Customer resolution reuses ERPNext's own Quotation -> Sales Order
	logic (erpnext.selling.doctype.quotation.quotation._make_customer),
	so Lead- and Prospect-type Quotations behave exactly like they
	already do today when your sales team converts one to a Sales Order:
	if a Customer already exists for that Lead/Prospect it's reused,
	otherwise one is auto-created from the Lead's/Prospect's details.
	Customer-type Quotations map straight across. This intentionally
	mirrors core ERPNext behavior rather than inventing a new conversion
	path.

	Lands on a new (unsaved) Service Order with customer and items
	filled in -- same pattern as the app's existing Service Quotation ->
	Service Order bridge (see service_order.make_order_from_quote) --
	so Service Type, Priority and Due Date can be set before saving.
	"""
	# NOTE: on ERPNext v16 this helper lives in quotation.py itself, not a
	# separate mapper.py (that split happens in a later ERPNext version).
	# Importing from quotation.py keeps this working on the version this
	# site actually runs.
	from erpnext.selling.doctype.quotation.quotation import _make_customer
	from frappe.model.mapper import get_mapped_doc

	customer = _make_customer(source_name, ignore_permissions=False)

	def set_missing_values(source, target):
		if customer:
			target.customer = customer.name

	mapping = {
		"Quotation": {
			"doctype": "Service Order",
			"validation": {"docstatus": ["=", 1]},
			# party_name holds a Customer, Lead, or Prospect name depending on
			# quotation_to -- never map it straight into the Customer link
			# field. The resolved `customer` above (via _make_customer) is
			# always a real Customer, set in set_missing_values instead.
			"field_no_map": ["party_name"],
		},
		"Quotation Item": {
			"doctype": "Service Order Item",
			"field_map": {"parent": "prevdoc_docname", "name": "quotation_item"},
			"condition": lambda d: not d.get("is_alternative"),
		},
	}

	doc = get_mapped_doc("Quotation", source_name, mapping, target_doc, set_missing_values)
	return doc
