# Copyright (c) 2026, Left Coast Scales
# For license information, please see license.txt

"""
Print-time line consolidation for LCS transactions.

Purpose
-------
QuickBooks Online lets a "Bundle" post real GL entries per component while
showing the customer one summarized line. ERPNext's native Product Bundle
does the opposite (one GL line, inconsistent itemized display), so instead
of using Product Bundle for labor-recovery charges (Zone Charge, Travel
Labor, Shipping & Receiving Recovery, etc.), those stay as ordinary,
separate line items -- so GL postings, tax, Sales Register, P&L, and the
Gross Profit report all stay fully itemized and correct -- and get
collapsed ONLY in the print template.

An Item opts into consolidation by setting its `lcs_consolidation_group`
custom field (a Link to "LCS Print Consolidation Group"). That field lives
on the Item master ONLY -- Sales Invoice Item / Sales Order Item / Quotation
Item rows do not automatically inherit it, so get_print_line_groups looks
it up per line via frappe.get_cached_value("Item", item.item_code, ...)
rather than assuming it's on the transaction row itself. (Caught by testing
against a real submitted Sales Invoice, not by inspection -- an earlier
draft assumed item.get("lcs_consolidation_group") would work directly on
doc.items and it silently no-op'd instead.)

get_print_line_groups reshapes a submitted doc's `items` child table into a
flat list of print rows: ordinary items pass through untouched, and every
item whose Item master shares a consolidation group gets summed into one
row using that group's `print_label` and `print_description`.

Nothing here touches accounting, tax, or stock -- it only changes what a
print format iterates over. Registered as a Jinja method in hooks.py, so
any print format can call `get_print_line_groups(doc)` directly.

Wiring notes for print formats:
- The Print Format record must have "Custom Format" checked -- otherwise
  ERPNext silently ignores the custom html and falls back to the default
  field-by-field layout. No error, just the wrong output.
- Example table body: see the Jinja loop pattern in this app's Quotation /
  Sales Order / Sales Invoice print formats -- iterate get_print_line_groups(doc)
  instead of doc.items, rendering {"type": "item", ...} rows normally and
  {"type": "group", ...} rows as one summed line (with `note` printed
  underneath if present).
"""

import frappe


def get_print_line_groups(doc):
	"""
	Return doc.items reshaped for print: ordinary rows pass through,
	rows flagged with the same lcs_consolidation_group are summed into
	one row.

	Returns a list of dicts, each either:
	    {"type": "item",  "item_code": str, "description": str,
	     "qty": float, "rate": float, "amount": float}
	or:
	    {"type": "group", "label": str, "note": str, "amount": float}
	"""
	groups = {}
	rows = []

	for item in doc.items:
		group_name = frappe.get_cached_value(
			"Item", item.item_code, "lcs_consolidation_group"
		)

		if not group_name:
			rows.append(
				{
					"type": "item",
					"item_code": item.item_code,
					"description": item.description or item.item_name,
					"qty": item.qty,
					"rate": item.rate,
					"amount": item.amount,
				}
			)
			continue

		if group_name not in groups:
			# frappe.get_cached_doc keeps this to one DB hit per group
			# per print render, even if several lines share the group.
			meta = frappe.get_cached_doc("LCS Print Consolidation Group", group_name)
			if meta.get("disabled"):
				# Group turned off -- fall back to printing the raw line
				# instead of silently dropping it from the page.
				rows.append(
					{
						"type": "item",
						"item_code": item.item_code,
						"description": item.description or item.item_name,
						"qty": item.qty,
						"rate": item.rate,
						"amount": item.amount,
					}
				)
				continue

			groups[group_name] = {
				"type": "group",
				"label": meta.print_label,
				"note": meta.print_description,
				"amount": 0,
			}

		groups[group_name]["amount"] += item.amount

	# Consolidated rows print together after the ordinary line items.
	rows.extend(groups.values())
	return rows
