# Copyright (c) 2026, Left Coast Scales LLC
"""
Shared helper for the "current state is separate from history of state
changes" convention (LCS ERPNext Implementation Roadmap Sections 41.4-41.5,
Phase 7B Active Brief Section 3). Any parent doctype that carries a child
table of type "LCS Status Log Entry" (fieldname: status_log) can call
log_status_change() from its own on_update() to append an audit-trail row
whenever its status field actually changes, instead of relying on the
mutable status field alone as history.

Reused across LCS NCR and LCS CAPA (Phase 7B Section 6.2/6.3). Kept as a
shared util rather than copy-pasted per doctype, per this app's existing
DRY conventions (e.g. lcs_service_agreement.auto_create_service_orders()'s
per-record error isolation pattern reused in lcs_customer_equipment.py).
"""
import frappe


def log_status_change(doc, child_fieldname="status_log", notes=None):
	"""Append a status_log row if doc.status changed since the last save.

	Call from on_update(). Uses get_doc_before_save() rather than db.get_value
	so this works consistently for both existing and brand-new documents.
	"""
	before = doc.get_doc_before_save()
	previous_status = before.status if before else None

	if previous_status == doc.status:
		return

	doc.append(
		child_fieldname,
		{
			"status": doc.status,
			"changed_by": frappe.session.user,
			"changed_on": frappe.utils.now_datetime(),
			"notes": notes or "",
		},
	)
	doc.db_update_all()
