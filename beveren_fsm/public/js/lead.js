// Lead — LCS Referral Incentive
//
// Ported from production's "LCS Lead — Incentive Payout Button" Client
// Script (near-verbatim — only the mechanism changed, from a DB-stored
// Client Script to an app-bundled file wired via hooks.py's doctype_js,
// matching this app's existing convention for Quotation's public/js/quotation.js).
//
// Adds the "Mark Qualified & Paid" button when a Lead has a referring
// employee and hasn't been paid out yet, and shows a green "Incentive Paid"
// indicator once it has. Calls the existing whitelisted
// beveren_fsm.field_service_management.api.lead_referral.mark_incentive_paid
// method to actually record the payout.

frappe.ui.form.on("Lead", {
	refresh: function (frm) {
		if (frm.doc.custom_referring_employee && !frm.doc.custom_incentive_paid) {
			frm.add_custom_button(
				__("Mark Qualified & Paid"),
				function () {
					lcs_mark_paid(frm);
				},
				__("LCS Incentive")
			);
		}

		if (frm.doc.custom_incentive_paid) {
			frm.page.set_indicator(
				__("Incentive Paid — " + frappe.datetime.str_to_user(frm.doc.custom_incentive_paid_date)),
				"green"
			);
		}
	},
});

function lcs_mark_paid(frm) {
	var emp_id = frm.doc.custom_referring_employee;

	frappe.db.get_value("Employee", emp_id, ["first_name", "last_name", "employee_name"]).then(function (r) {
		var emp_name = emp_id;
		if (r && r.message) {
			var d = r.message;
			emp_name = d.employee_name || ((d.first_name || "") + " " + (d.last_name || "")).trim() || emp_id;
		}

		frappe.confirm(
			__(
				"Confirm payout of <strong>$10 cash</strong> to <strong>{0}</strong>?<br><br>" +
					"This will:<ul style='text-align:left;margin-top:8px'>" +
					"<li>Mark this lead as paid in ERPNext</li>" +
					"<li>Add a note to the lead record</li>" +
					"<li>Send a confirmation email to the employee</li></ul>",
				[emp_name]
			),
			function () {
				frappe.call({
					method: "beveren_fsm.field_service_management.api.lead_referral.mark_incentive_paid",
					args: { lead_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Recording payout..."),
					callback: function (r) {
						if (!r.exc) {
							frappe.show_alert(
								{
									message: __("Payout recorded and employee notified."),
									indicator: "green",
								},
								5
							);
							frm.reload_doc();
						}
					},
				});
			}
		);
	});
}
