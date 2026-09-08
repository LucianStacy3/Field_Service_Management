import frappe
from frappe.utils import today, get_url


# ── Existing functions (unchanged — already live in this file) ─────────────
#
# get_employee_list() and mark_incentive_paid() were already implemented in
# this file before this port. They match production's expectations exactly
# (verified against the "LCS Lead — Incentive Payout Button" Client Script
# and the "Submit a Referral" Web Form's embedded client script), so they're
# reproduced here unchanged and this file is a drop-in replacement.


@frappe.whitelist(allow_guest=True)
def get_employee_list():
	"""
	Returns active employees with only first/last name components.
	Excludes Sales - LCS and Management - LCS departments.
	Called by the public Lead Referral webform dropdown.
	No PII beyond name fragments is returned.
	"""
	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"department": ["not in", ["Sales - LCS", "Management - LCS"]],
		},
		fields=["name", "first_name", "last_name"],
		order_by="first_name asc, last_name asc",
	)
	return employees


@frappe.whitelist()
def mark_incentive_paid(lead_name):
	"""
	Called by the Lead form's 'Mark Qualified & Paid' button.
	1. Sets custom_incentive_paid and custom_incentive_paid_date
	2. Adds a timestamped note to the Lead
	3. Emails the referring employee their payout confirmation
	"""
	if not frappe.has_permission("Lead", "write", lead_name):
		frappe.throw("You do not have permission to update this Lead.")

	lead = frappe.get_doc("Lead", lead_name)

	if lead.custom_incentive_paid:
		frappe.throw(f"Incentive for {lead_name} has already been recorded as paid.")

	if not lead.custom_referring_employee:
		frappe.throw("This lead has no referring employee on record.")

	paid_date = today()

	# 1. Update paid flags
	lead.db_set("custom_incentive_paid", 1, update_modified=True)
	lead.db_set("custom_incentive_paid_date", paid_date, update_modified=True)

	# 2. Resolve employee details
	emp = frappe.get_doc("Employee", lead.custom_referring_employee)
	emp_full_name = emp.employee_name or ((emp.first_name or "") + " " + (emp.last_name or "")).strip()
	emp_email = emp.company_email or emp.personal_email or ""

	referred_name = ((lead.first_name or "") + " " + (lead.last_name or "")).strip()
	referred_co = lead.company_name or ""
	referred_city = lead.city or ""

	# 3. Add payout note to Lead
	note_text = (
		"QUALIFIED & PAID — " + paid_date + "\n\n"
		"Lead confirmed as qualified by Sales.\n"
		"Referring employee: " + emp_full_name + "\n"
		"Cash payout of $10 disbursed from petty cash.\n"
		"Recorded by: " + frappe.session.user
	)

	lead.reload()
	lead.append(
		"notes",
		{
			"note": note_text,
			"added_by": frappe.session.user,
			"added_on": paid_date,
		},
	)
	lead.save(ignore_permissions=True)

	# 4. Email employee confirmation
	if emp_email:
		try:
			frappe.sendmail(
				recipients=[emp_email],
				subject="Your LCS referral has been qualified — you've been paid!",
				message=(
					"<p>Hi " + (emp.first_name or emp_full_name) + ",</p>"
					"<p>Your referral has been reviewed by Sales and confirmed as qualified. "
					"Your <strong>$10 cash payout</strong> has been recorded and is ready at the office.</p>"
					"<table style='border-collapse:collapse;width:100%;max-width:480px;"
					"font-family:Arial,sans-serif;font-size:14px'>"
					"<tr style='background:#1B2A4A;color:#fff'>"
					"<td colspan='2' style='padding:10px 14px;font-weight:bold'>Payout Summary</td></tr>"
					"<tr style='background:#F2F4F8'>"
					"<td style='padding:8px 14px;font-weight:bold;width:40%'>Referred contact</td>"
					"<td style='padding:8px 14px'>" + referred_name + "</td></tr>"
					"<tr>"
					"<td style='padding:8px 14px;font-weight:bold'>Company</td>"
					"<td style='padding:8px 14px'>"
					+ referred_co
					+ (", " + referred_city if referred_city else "")
					+ "</td></tr>"
					"<tr style='background:#F2F4F8'>"
					"<td style='padding:8px 14px;font-weight:bold'>Payout amount</td>"
					"<td style='padding:8px 14px'><strong>$10.00 cash</strong></td></tr>"
					"<tr>"
					"<td style='padding:8px 14px;font-weight:bold'>Date confirmed</td>"
					"<td style='padding:8px 14px'>" + paid_date + "</td></tr>"
					"</table>"
					"<p style='margin-top:16px;padding:12px 16px;background:#EAF3DE;"
					"border-left:4px solid #3B6D11;font-family:Arial,sans-serif;"
					"font-size:14px;color:#27500A'>"
					"Keep it going — every qualified lead earns you $10, and milestone bonuses "
					"stack at 10, 25, and 50 leads.</p>"
					"<p style='font-size:12px;color:#666;margin-top:24px'>— Left Coast Scales</p>"
				),
				now=True,
			)
		except Exception:
			frappe.log_error(title="Referral payout email failed", message=frappe.get_traceback())

	frappe.db.commit()
	return {"status": "ok", "paid_date": paid_date, "employee": emp_full_name}


# ── New functions, ported from production's Server Scripts ─────────────────
#   - referral_leaderboard()      <- Server Script "Referral Leaderboard API"
#   - on_lead_after_insert()      <- Server Script "LCS Lead Referral — On Submit"
#     (a DocType Event / After Insert script — the name is misleading, it
#     does not run on Lead submission, it runs right after a Lead is created,
#     e.g. via the public Web Form)


@frappe.whitelist(allow_guest=True)
def referral_leaderboard():
	"""
	Returns per-employee referral stats for the leaderboard.
	Ported verbatim from production's "Referral Leaderboard API" Server Script.
	"""
	data = frappe.db.sql(
		"""
		SELECT
			COALESCE(custom_referring_employee_name, custom_referring_employee) as employee_name,
			COUNT(*) as total,
			SUM(CASE WHEN status = 'Opportunity' THEN 1 ELSE 0 END) as qualified,
			SUM(CASE WHEN custom_incentive_paid = 1 THEN 1 ELSE 0 END) as paid,
			SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) as converted,
			SUM(CASE WHEN custom_incentive_paid = 1 THEN 10 ELSE 0 END) as total_earned
		FROM `tabLead`
		WHERE custom_referring_employee IS NOT NULL
			AND custom_referring_employee != ''
		GROUP BY custom_referring_employee
		ORDER BY total DESC
		""",
		as_dict=True,
	)
	return data


def on_lead_after_insert(doc, method=None):
	"""
	Runs right after a new Lead is inserted (wired via hooks.py doc_events,
	replacing production's raw "LCS Lead Referral — On Submit" Server Script
	on the same DocType Event).

	Ported logic, same as production:
	  1. Resolve the referring employee's display name.
	  2. Normalize status/type and stamp custom_referring_employee_name.
	  3. Append a note documenting the referral.
	  4. Email an internal notification to Field Service Managers.
	  5. Email the referring employee a "we got it" confirmation.

	Two things were deliberately changed from production, since this is a
	fresh port rather than a copy:
	  - The internal notification no longer goes to a single hardcoded
	    production email address. It goes to everyone holding the
	    "Field Service Manager" role instead (falls back to Administrator
	    if none are found), so this keeps working as staff changes.
	  - The "Open Lead" link now points at this site's own Lead form
	    (/app/lead/<name>) instead of production's CRM-style URL, since
	    Frappe CRM isn't installed here and core ERPNext's Lead form is
	    the real destination.
	"""
	if not doc.custom_referring_employee:
		return

	emp = frappe.get_doc("Employee", doc.custom_referring_employee)
	emp_full_name = (
		emp.employee_name
		or ((emp.first_name or "") + " " + (emp.last_name or "")).strip()
	)
	emp_email = emp.company_email or emp.personal_email or ""

	referring_cust = doc.custom_referring_customer or "an existing LCS customer"
	referring_co = doc.custom_referring_customer_company or ""
	referred_name = ((doc.first_name or "") + " " + (doc.last_name or "")).strip()
	referred_co = doc.company_name or ""
	referred_city = doc.city or ""
	paid_date = today()

	doc.db_set("status", "Lead", update_modified=False)
	doc.db_set("type", "Client", update_modified=False)
	doc.db_set("custom_referring_employee_name", emp_full_name, update_modified=False)

	note_text = (
		"Lead submitted via LCS Lead Incentive Program on " + paid_date + ".\n\n"
		"Submitted by: " + emp_full_name + "\n"
		"Referring customer: " + referring_cust
		+ (" (" + referring_co + ")" if referring_co else "")
		+ "\nReferred contact: " + referred_name
		+ (" at " + referred_co if referred_co else "")
		+ (", " + referred_city if referred_city else "")
		+ "\n\nPayout: Pending Sales qualification."
	)

	doc.reload()
	doc.append(
		"notes",
		{
			"note": note_text,
			"added_by": frappe.session.user,
			"added_on": paid_date,
		},
	)
	doc.save(ignore_permissions=True)

	# Internal notification -> everyone with the Field Service Manager role
	manager_emails = frappe.get_all(
		"Has Role",
		filters={"role": "Field Service Manager", "parenttype": "User"},
		pluck="parent",
	)
	manager_emails = frappe.get_all(
		"User",
		filters={"name": ["in", manager_emails], "enabled": 1},
		pluck="name",
	) or ["Administrator"]

	lead_url = get_url() + "/app/lead/" + doc.name

	try:
		frappe.sendmail(
			recipients=manager_emails,
			subject="New Incentive Lead: " + (referred_co or referred_name),
			message=(
				"<p>Hi,</p>"
				"<p>A new referral has been submitted through the LCS Lead Incentive Program.</p>"
				"<table style='border-collapse:collapse;width:100%;max-width:540px;font-family:Arial,sans-serif;font-size:14px'>"
				"<tr style='background:#1B2A4A;color:#fff'><td colspan='2' style='padding:10px 14px;font-weight:bold'>Lead Details</td></tr>"
				"<tr style='background:#F2F4F8'><td style='padding:8px 14px;font-weight:bold;width:40%'>Submitted by</td><td style='padding:8px 14px'>" + emp_full_name + "</td></tr>"
				"<tr><td style='padding:8px 14px;font-weight:bold'>Referring customer</td><td style='padding:8px 14px'>" + referring_cust + (" — " + referring_co if referring_co else "") + "</td></tr>"
				"<tr style='background:#F2F4F8'><td style='padding:8px 14px;font-weight:bold'>Referred contact</td><td style='padding:8px 14px'>" + referred_name + (" — " + (doc.job_title or "") if doc.job_title else "") + "</td></tr>"
				"<tr><td style='padding:8px 14px;font-weight:bold'>Company</td><td style='padding:8px 14px'>" + referred_co + (", " + referred_city if referred_city else "") + "</td></tr>"
				"<tr style='background:#F2F4F8'><td style='padding:8px 14px;font-weight:bold'>Phone</td><td style='padding:8px 14px'>" + (doc.phone or "—") + "</td></tr>"
				"<tr><td style='padding:8px 14px;font-weight:bold'>Email</td><td style='padding:8px 14px'>" + (doc.email_id or "—") + "</td></tr>"
				"</table>"
				"<p style='margin-top:16px'><a href='" + lead_url + "' style='background:#1B2A4A;color:#fff;padding:8px 16px;border-radius:4px;text-decoration:none;font-family:Arial,sans-serif;font-size:14px'>Open Lead in ERPNext →</a></p>"
				"<p style='font-size:12px;color:#666;margin-top:24px'>Once confirmed, open the lead and click <strong>Mark Qualified &amp; Paid</strong> to log the payout.</p>"
			),
			now=True,
		)
	except Exception:
		frappe.log_error(title="Referral notification email failed", message=frappe.get_traceback())

	# Confirmation to the referring employee
	if emp_email:
		try:
			frappe.sendmail(
				recipients=[emp_email],
				subject="Your LCS referral has been submitted",
				message=(
					"<p>Hi " + (emp.first_name or emp_full_name) + ",</p>"
					"<p>Your referral has been received and is in the queue for Sales review.</p>"
					"<table style='border-collapse:collapse;width:100%;max-width:480px;font-family:Arial,sans-serif;font-size:14px'>"
					"<tr style='background:#1B2A4A;color:#fff'><td colspan='2' style='padding:10px 14px;font-weight:bold'>Your Referral</td></tr>"
					"<tr style='background:#F2F4F8'><td style='padding:8px 14px;font-weight:bold;width:40%'>Contact</td><td style='padding:8px 14px'>" + referred_name + "</td></tr>"
					"<tr><td style='padding:8px 14px;font-weight:bold'>Company</td><td style='padding:8px 14px'>" + referred_co + (", " + referred_city if referred_city else "") + "</td></tr>"
					"<tr style='background:#F2F4F8'><td style='padding:8px 14px;font-weight:bold'>Submitted</td><td style='padding:8px 14px'>" + paid_date + "</td></tr>"
					"</table>"
					"<p style='margin-top:16px'>Once Sales confirms this lead is qualified, you will receive another email and your <strong>$10 cash payout</strong> will be ready at the office.</p>"
					"<p style='font-size:12px;color:#666;margin-top:24px'>— Left Coast Scales</p>"
				),
				now=True,
			)
		except Exception:
			frappe.log_error(title="Referral confirmation email failed", message=frappe.get_traceback())
