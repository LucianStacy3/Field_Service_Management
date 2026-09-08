# Copyright (c) 2026, Left Coast Scales LLC
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class LCSControlledDocument(Document):
	def validate(self):
		self._validate_approval_fields()

	def on_update(self):
		self._log_revision_on_approval()

	# ------------------------------------------------------------------
	# Approval workflow (Draft -> Under Review -> Approved -> Obsolete)
	# ------------------------------------------------------------------

	def _validate_approval_fields(self):
		"""Server-side gatekeeper (Section 8 convention) -- client JS can
		hide/require fields, but this is what actually blocks a bad save."""
		if self.status == "Approved" and not (self.approved_by and self.approval_date):
			frappe.throw(
				frappe._("Approved By and Approval Date are required before status can be Approved.")
			)

	def _log_revision_on_approval(self):
		"""When status transitions into Approved, log the revision instead of
		reconstructing history from the mutable status field (Section 3
		convention). Versioning is ON in Nextcloud (Section 4 decision), so
		document_url never changes on a new revision -- only this log grows."""
		before = self.get_doc_before_save()
		previous_status = before.status if before else None

		if previous_status == self.status or self.status != "Approved":
			return

		self.append(
			"revision_history",
			{
				"issue_number": self.issue_number,
				"change_summary": self.change_summary,
				"approved_by": self.approved_by,
				"approval_date": self.approval_date,
			},
		)
		self.db_update_all()


# ------------------------------------------------------------------
# Scheduled task -- nightly review-date check
# ------------------------------------------------------------------

REVIEW_LEAD_DAYS = 30


def flag_documents_approaching_review():
	"""Nightly scheduler task (registered in hooks.py). Mirrors
	lcs_customer_equipment.flag_overdue_equipment()'s two-pass,
	per-record-error-isolated shape."""
	window_end = add_days(today(), REVIEW_LEAD_DAYS)

	candidates = frappe.get_all(
		"LCS Controlled Document",
		filters={
			"status": "Approved",
			"review_date": ["between", [today(), window_end]],
		},
		fields=["name", "document_number", "title", "originator", "reviewer", "review_date"],
	)
	if not candidates:
		return

	for row in candidates:
		try:
			recipients = [
				frappe.db.get_value("Employee", emp, "user_id")
				for emp in (row.originator, row.reviewer)
				if emp
			]
			recipients = [r for r in recipients if r]
			if recipients:
				frappe.sendmail(
					recipients=recipients,
					subject=f"Controlled document {row.document_number} due for review {row.review_date}",
					message=(
						f"{row.document_number} - {row.title} is due for review on {row.review_date}. "
						f"Please review and re-approve in ERPNext."
					),
				)
		except Exception:
			# Known gotcha (Section 9): an unconfigured/failing mail server
			# rolls back the *entire* transaction if this isn't caught.
			frappe.log_error(
				title=f"Controlled Document review reminder email failed - {row.name}",
				message=frappe.get_traceback(),
			)

	frappe.log_error(
		message=frappe.as_json(candidates),
		title=f"LCS Controlled Document - Approaching Review Date ({len(candidates)})",
	)
