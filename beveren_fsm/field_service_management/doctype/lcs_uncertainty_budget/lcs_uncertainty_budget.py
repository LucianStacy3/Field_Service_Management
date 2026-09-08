# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document


class LCSUncertaintyBudget(Document):
	def validate(self):
		self._validate_link_target()
		self._validate_no_duplicate_budget()

	def _validate_link_target(self):
		if not self.service_type and not self.item:
			frappe.throw(frappe._("Please link this budget to a Service Type and/or an Item."))

	def _validate_no_duplicate_budget(self):
		"""Guards against two active budgets matching the same Service
		Type + Item combination, which would make "the applicable range"
		ambiguous for whoever/whatever reads it back (print format,
		get_applicable_uncertainty() below)."""
		duplicate = frappe.db.get_value(
			"LCS Uncertainty Budget",
			{
				"service_type": self.service_type,
				"item": self.item,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				frappe._("Budget {0} already covers this Service Type / Item combination.").format(duplicate)
			)


def get_applicable_uncertainty(service_type: str | None = None, item: str | None = None, measured_value: float | None = None):
	"""Look up the reported uncertainty for a measured value, given a
	Service Type and/or Item. Intended for the Calibration Test Report
	print format once that doctype exists (Phase 7B Active Brief Section
	6.6) -- kept here now so the lookup logic lives with the data it
	reads rather than being written twice later.

	Returns a dict {uncertainty_value, uncertainty_type, budget} or None
	if no budget / no matching range is found.
	"""
	if not service_type and not item:
		return None

	filters = {}
	if item:
		filters["item"] = item
	elif service_type:
		filters["service_type"] = service_type

	budget_name = frappe.db.get_value("LCS Uncertainty Budget", filters, "name")
	if not budget_name:
		return None

	budget = frappe.get_doc("LCS Uncertainty Budget", budget_name)

	if measured_value is None:
		return {"budget": budget.name}

	for row in budget.uncertainty_ranges or []:
		range_min = row.range_min if row.range_min is not None else float("-inf")
		range_max = row.range_max if row.range_max is not None else float("inf")
		if range_min <= measured_value <= range_max:
			return {
				"uncertainty_value": row.uncertainty_value,
				"uncertainty_type": row.uncertainty_type,
				"budget": budget.name,
			}

	return None
