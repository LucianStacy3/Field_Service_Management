import frappe

login_required = True

def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw("Not permitted", frappe.PermissionError)
	context.no_cache = 1