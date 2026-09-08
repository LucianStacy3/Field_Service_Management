# Copyright (c) 2026, Left Coast Scales
# For license information, please see license.txt

"""
Regression test for print-line consolidation (get_print_line_groups).

This is the automated version of the QuickBooks-Online-bundle-parity
question that started this feature: several labor-recovery items (Zone
Charge, Travel Labor, Shipping & Receiving Recovery) need to look like ONE
line to the customer, while the GL, tax, and every standard report still
see them as fully separate postings against their own income accounts.

Uses throwaway "_Test ..." masters (company, items, customer) so it's
safe to run against a real dev/staging site without touching production
data. Requires bench console / bench run-tests access:

    bench --site <site> run-tests --app beveren_fsm \\
        --module beveren_fsm.field_service_management.api.test_print_helpers
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.www.printview import get_html_and_style


COMPANY = "_Test LCS Consolidation Co"
ABBR = "TLCC"


class IntegrationTestPrintConsolidation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls._setup_masters()

	@classmethod
	def _account(cls, name, parent_account_name, account_type=None):
		acc_name = f"{name} - {ABBR}"
		if frappe.db.exists("Account", acc_name):
			return acc_name
		parent = frappe.db.get_value(
			"Account", {"company": COMPANY, "account_name": parent_account_name}, "name"
		)
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": name,
				"company": COMPANY,
				"parent_account": parent,
				"account_type": account_type,
			}
		).insert().name

	@classmethod
	def _setup_masters(cls):
		for wh_type in ("Transit", "Rejected"):
			if not frappe.db.exists("Warehouse Type", wh_type):
				frappe.get_doc({"doctype": "Warehouse Type", "name": wh_type}).insert()

		if not frappe.db.exists(
			"Fiscal Year",
			{
				"year_start_date": ["<=", frappe.utils.nowdate()],
				"year_end_date": [">=", frappe.utils.nowdate()],
			},
		):
			frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": "_Test FY LCS Consolidation",
					"year_start_date": frappe.utils.get_first_day(frappe.utils.nowdate()).replace(month=1, day=1),
					"year_end_date": frappe.utils.get_first_day(frappe.utils.nowdate()).replace(month=12, day=31),
				}
			).insert()

		if not frappe.db.exists("Company", COMPANY):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY,
					"abbr": ABBR,
					"default_currency": "USD",
					"country": "United States",
				}
			).insert()

		company = frappe.get_doc("Company", COMPANY)
		if not company.round_off_account:
			company.round_off_account = cls._account("Round Off", "Indirect Expenses")
			company.save()

		cls.zone_income = cls._account("Zone Charge Income", "Direct Income")
		cls.travel_income = cls._account("Travel Labor Income", "Direct Income")
		cls.recovery_income = cls._account("S&R Recovery Income", "Direct Income")
		cls.parts_income = cls._account("Parts & Service Income", "Direct Income")

		if not frappe.db.exists("Price List", "_Test Standard Selling LCS"):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": "_Test Standard Selling LCS",
					"selling": 1,
					"currency": "USD",
				}
			).insert()

		if not frappe.db.exists("LCS Print Consolidation Group", "_test_recovery_labor"):
			frappe.get_doc(
				{
					"doctype": "LCS Print Consolidation Group",
					"group_name": "_test_recovery_labor",
					"print_label": "Service & Handling",
					"print_description": (
						"Includes travel time, zone-based dispatch charge, and "
						"shipping/receiving recovery for parts on this job."
					),
				}
			).insert()

		cls._make_item("_Test Zone Charge", cls.zone_income, "_test_recovery_labor")
		cls._make_item("_Test Travel Labor", cls.travel_income, "_test_recovery_labor")
		cls._make_item("_Test S&R Recovery", cls.recovery_income, "_test_recovery_labor")
		cls._make_item("_Test Scale Calibration Service", cls.parts_income, None)

		if not frappe.db.exists("Customer", "_Test LCS Consolidation Customer"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_Test LCS Consolidation Customer",
					"customer_group": frappe.db.get_value("Customer Group", {}, "name"),
					"territory": frappe.db.get_value("Territory", {}, "name"),
				}
			).insert()

	@classmethod
	def _make_item(cls, item_code, income_account, consolidation_group):
		if frappe.db.exists("Item", item_code):
			it = frappe.get_doc("Item", item_code)
		else:
			it = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_code,
					"item_group": frappe.db.get_value("Item Group", {}, "name"),
					"is_stock_item": 0,
					"stock_uom": frappe.db.get_value("UOM", {}, "name") or "Nos",
				}
			).insert()

		existing = [d for d in it.item_defaults if d.company == COMPANY]
		if existing:
			existing[0].income_account = income_account
		else:
			it.append("item_defaults", {"company": COMPANY, "income_account": income_account})

		it.lcs_consolidation_group = consolidation_group
		it.save()
		return it.name

	def _make_invoice(self):
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": "_Test LCS Consolidation Customer",
				"company": COMPANY,
				"currency": "USD",
				"conversion_rate": 1,
				"selling_price_list": "_Test Standard Selling LCS",
				"price_list_currency": "USD",
				"plc_conversion_rate": 1,
				"due_date": frappe.utils.nowdate(),
				"items": [
					{"item_code": "_Test Scale Calibration Service", "qty": 1, "rate": 250.00},
					{"item_code": "_Test Zone Charge", "qty": 1, "rate": 35.00},
					{"item_code": "_Test Travel Labor", "qty": 2, "rate": 60.00},
					{"item_code": "_Test S&R Recovery", "qty": 1, "rate": 18.50},
				],
			}
		)
		si.insert()
		si.submit()
		return si

	def test_gl_entries_stay_fully_itemized(self):
		"""
		The heart of the requirement: consolidating the customer-facing
		line must NEVER touch accounting. Every component keeps posting
		to its own income account, at its own amount.
		"""
		si = self._make_invoice()
		gl = frappe._dict(
			(d.account, d.credit)
			for d in frappe.get_all(
				"GL Entry",
				filters={"voucher_no": si.name, "credit": [">", 0]},
				fields=["account", "credit"],
			)
		)

		self.assertEqual(gl.get(self.zone_income), 35.0)
		self.assertEqual(gl.get(self.travel_income), 120.0)
		self.assertEqual(gl.get(self.recovery_income), 18.5)
		self.assertEqual(gl.get(self.parts_income), 250.0)
		self.assertAlmostEqual(sum(gl.values()), 423.5, places=2)

	def test_print_line_groups_collapses_flagged_items_only(self):
		si = self._make_invoice()
		from beveren_fsm.field_service_management.api.print_helpers import (
			get_print_line_groups,
		)

		rows = get_print_line_groups(si)
		item_rows = [r for r in rows if r["type"] == "item"]
		group_rows = [r for r in rows if r["type"] == "group"]

		self.assertEqual(len(item_rows), 1)
		self.assertEqual(item_rows[0]["item_code"], "_Test Scale Calibration Service")

		self.assertEqual(len(group_rows), 1)
		self.assertEqual(group_rows[0]["label"], "Service & Handling")
		self.assertAlmostEqual(group_rows[0]["amount"], 173.5, places=2)
		self.assertIn("travel time", group_rows[0]["note"])

	def test_disabled_group_falls_back_to_itemized_print(self):
		group = frappe.get_doc("LCS Print Consolidation Group", "_test_recovery_labor")
		group.disabled = 1
		group.save()
		try:
			si = self._make_invoice()
			from beveren_fsm.field_service_management.api.print_helpers import (
				get_print_line_groups,
			)

			rows = get_print_line_groups(si)
			item_codes = {r["item_code"] for r in rows if r["type"] == "item"}
			self.assertIn("_Test Zone Charge", item_codes)
			self.assertIn("_Test Travel Labor", item_codes)
			self.assertIn("_Test S&R Recovery", item_codes)
			self.assertEqual([r for r in rows if r["type"] == "group"], [])
		finally:
			group.disabled = 0
			group.save()

	def test_print_output_shows_one_line_not_three(self):
		si = self._make_invoice()
		if not frappe.db.exists("Print Format", "_Test LCS Consolidated Invoice"):
			frappe.get_doc(
				{
					"doctype": "Print Format",
					"name": "_Test LCS Consolidated Invoice",
					"doc_type": "Sales Invoice",
					"print_format_type": "Jinja",
					"custom_format": 1,
					"html": (
						"{% set line_rows = get_print_line_groups(doc) %}"
						"{% for row in line_rows %}"
						"{% if row.type == 'item' %}{{ row.description }}|{% else %}"
						"{{ row.label }}|{{ row.note }}|{% endif %}"
						"{% endfor %}"
					),
				}
			).insert()

		html = get_html_and_style(
			doc="Sales Invoice",
			name=si.name,
			print_format="_Test LCS Consolidated Invoice",
			no_letterhead=1,
		)["html"]

		self.assertIn("Service & Handling", html)
		self.assertIn("travel time", html)
		self.assertNotIn("_Test Zone Charge", html)
		self.assertNotIn("_Test Travel Labor", html)
		self.assertNotIn("_Test S&R Recovery", html)
		self.assertIn("_Test Scale Calibration Service", html)
