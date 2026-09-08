# Copyright (c) 2025, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc


class ServiceQuotation(Document):
	def validate(self):
		self.validate_items()

	def before_submit(self):
		if self.service_request:
			request = frappe.get_doc("Service Request", self.service_request)
			request.status = "Quotation"
			request.save()

	def on_cancel(self):
		self.cancel_linked_request()

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Please add at least one item"))

	def cancel_linked_request(self):
		if not self.service_request:
			return
		request = frappe.get_doc("Service Request", self.service_request)
		request.status = "Open"
		self.service_request = ""
		request.save()

	# ------------------------------------------------------------------
	# Stub added to fix: 'ServiceQuotation' object has no attribute
	# 'process_item_selection'
	#
	# Same root cause already fixed on Service Order: ERPNext's standard
	# item-grid JS automatically calls this server method via
	# run_doc_method whenever a child row has reserve_stock=1 (ERPNext's
	# stock-reservation feature). Service Quotation Item also carries a
	# reserve_stock field, so selecting any item in a new Service
	# Quotation's Items grid triggers the same automatic call and threw
	# an AttributeError before this stub existed -- blocking quotation
	# creation entirely. Service Quotation doesn't use ERPNext's stock
	# reservation workflow, so this is a harmless no-op that just lets
	# the automatic call succeed instead of throwing.
	# ------------------------------------------------------------------
	@frappe.whitelist()
	def process_item_selection(self, item_idx=None):
		return


@frappe.whitelist()
def make_service_quotation(source_name, target_doc=None, selected_items=None):
	mapping = {
		"Service Request": {
			"doctype": "Service Quotation",
			"field_map": {
				"name": "service_request",
				"customer": "party_name",
				"company": "company",
				"posting_date": "posting_date",
				"due_date": "due_date",
				"customer_address": "service_address",
				"cost_center": "cost_center",
				"project": "project",
				"currency": "currency",
				"serial_no": "serial_no",
				"preferred_date_1": "preferred_date_1",
				"preferred_time": "preferred_time",
				"preference_note": "preference_note",
			},
		}
	}
	doc = get_mapped_doc("Service Request", source_name, mapping, target_doc)
	return doc
