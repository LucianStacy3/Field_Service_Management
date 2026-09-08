import frappe
from frappe.model.document import Document


class LCSScaleModel(Document):
	def validate(self):
		self._validate_unique_model_per_manufacturer()

	def _validate_unique_model_per_manufacturer(self):
		duplicate = frappe.db.get_value(
			"LCS Scale Model",
			{
				"manufacturer": self.manufacturer,
				"model_number": self.model_number,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				frappe._("Model {0} already exists for manufacturer {1}.").format(
					self.model_number, self.manufacturer
				)
			)
