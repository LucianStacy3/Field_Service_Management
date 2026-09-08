# beveren_fsm/www/service-agreement-quote.py
# Route: /service-agreement-quote

import frappe
import frappe.sessions

no_cache = 1

def get_context(context):
    # Inject CSRF token so frappe.call() works from the portal page
    context.csrf_token = frappe.sessions.get_csrf_token()
    frappe.db.commit()

    context.no_cache = 1
    context.show_sidebar = False
    context.title = "LCS Service Agreement Quote"

    # Pass logged-in user's full name to pre-fill sales rep
    if frappe.session.user != "Guest":
        user = frappe.get_doc("User", frappe.session.user)
        context.sales_rep_name = user.full_name or frappe.session.user
    else:
        context.sales_rep_name = ""