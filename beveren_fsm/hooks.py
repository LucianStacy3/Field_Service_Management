app_name = "Left Coast Scales"
app_title = "Left Coast Scales"
app_publisher = "Left Coast Scales"
app_description = "Left Coast Scales Field Service Management App"
app_email = "info@leftcoastscales.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "beveren_fsm",
# 		"logo": "/assets/beveren_fsm/logo.png",
# 		"title": "Field Service Management",
# 		"route": "/beveren_fsm",
# 		"has_permission": "beveren_fsm.api.permission.has_app_permission"
# 	}
# ]

fixtures = [
	# ---------------------------------------------------------------------------
	# LCS custom doctypes — export all records (existing, unchanged)
	# ---------------------------------------------------------------------------
	# "LCS Shortcut",  # seeded on initial deploy only — do not re-enable
	"Service Type",
	{
		# Role-permission rows (Role Permissions Manager / DocPerm) that this
		# app depends on -- e.g. Field Service User's read access to Service
		# Appointment, which get_my_jobs() needs (frappe.get_list() enforces
		# DocType-level permissions; frappe.get_all() doesn't, and that
		# inconsistency is exactly how this gap went unnoticed for so long).
		# Was previously live-only: fixed directly on the site via the UI,
		# never exported, so a fresh install/site would silently regress and
		# lock every technician out of their job list again. Filtered to the
		# roles this app actually manages so we never sweep in unrelated
		# site-wide permission rows (e.g. core Frappe roles, HR/Payroll
		# roles) that happen to share the Custom DocPerm doctype.
		"dt": "Custom DocPerm",
		"filters": [
			[
				"role",
				"in",
				["Service Manager", "Field Service User"],
			]
		],
	},
	"Product Location",
	"LCS Service Agreement",
	"LCS Service Agreement Quote",
	"LCS Customer Equipment",
	"LCS Scale Model",
	"LCS Appointment Resource",  # Phase 2C — non-human resource child table
	"LCS Vehicle",
	#"LCS Load Cell Family",
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Service Appointment-customer_notes",
					"Service Appointment-internal_notes",
					"Service Appointment-dispatch_instructions",
					"Service Order-dispatch_instructions",
				],
			]
		],
	},
	# {"dt": "Workspace", "filters": {"name": "Service"}},

	# Custom Fields for Service Order links and Service Area extensions (Phase 2D)
	{
		"doctype": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					# Service Order links (existing)
					"Purchase Order-custom_service_order",
					"Purchase Invoice-custom_service_order",
					"Purchase Receipt-custom_service_order",
					"Stock Entry-custom_service_order",
					"Delivery Note-custom_service_order",
					"Delivery Note-custom_current_product_location",
					"Stock Entry-custom_current_product_location",
					"Purchase Order-custom_current_product_location",
					"Purchase Invoice-custom_current_product_location",
					"Purchase Receipt-custom_current_product_location",
					# Service Area extensions (Phase 2D)
					"Service Area-custom_branch_office",
					"Service Area-custom_state",
					"Service Area-custom_cost_center",
					"Service Area-custom_territory",
					"Service Area-custom_office_address",
					# Sales Invoice reference-to-service-document fields (Phase 5)
					"Sales Invoice-custom_field_service_management_link",
					"Sales Invoice-custom_reference_service_doctype",
					"Sales Invoice-custom_column_break_uspzq",
					"Sales Invoice-custom_reference_service_document",
				],
			]
		],
	},

	# Custom Fields for the LCS NCR -> Customer Equipment "Out of Service" tag
	# (Phase 7B -- ISO 17025 QMS, Section 6.2 / SOP-013 Section 5.3.3)
	{
		"doctype": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"LCS Customer Equipment-custom_out_of_service",
					"LCS Customer Equipment-custom_out_of_service_reason",
					"LCS Customer Equipment-custom_out_of_service_tagged_by",
					"LCS Customer Equipment-custom_out_of_service_date",
				],
			]
		],
	},

	# ---------------------------------------------------------------------------
	# Phase 7B -- ISO 17025 QMS doctypes
	# ---------------------------------------------------------------------------
	"LCS Controlled Document",
	"LCS NCR",
	"LCS RGA",
	"LCS CAPA",
	"LCS Audit",

	# Phase 7B -- Section 6.6, measurement uncertainty & calibration
	# traceability. LCS Reference Standard is seeded from LCS's real
	# 2025/2026 AZ Dept. of Agriculture calibration certificates
	# (owning_test_truck intentionally left blank in the seed data --
	# assign per record in the Desk once trucks are confirmed).
	"LCS Uncertainty Budget",
	"LCS Reference Standard",

	# ---------------------------------------------------------------------------
	# LCS HR / People fixtures — filtered exports of standard Frappe doctypes
	#
	# ORDER MATTERS: Frappe applies fixtures in list order during migrate.
	# Masters (Designation, Department, Role, Shift Type) must land before
	# the records that depend on them (Employee, User, Shift Assignment).
	#
	# These use filtered dict format so we only touch LCS records — we never
	# export every Designation or every User in the system.
	# ---------------------------------------------------------------------------

	# Designations — only the ones LCS actually uses
	{
		"dt": "Designation",
		"filters": [
			["designation_name", "in", [
				"Account Manager",
				"Accountant",
				"Administrative Assistant",
				"Chief Executive Officer",
				"Chief Financial Officer",
				"Data Specialist",
				"General Manager",
				"Inside Sales",
				"Marketing Coordinator",
				"Master Technician",
				"Sales Admin",
				"Sales Manager",
				"Service Administrator",
				"Service Manager",
				"Shop Technician",
				"Technician",
			]],
		],
	},

	# LCS-Training department (the only new department we're adding)
	{
		"dt": "Department",
		"filters": [["department_name", "=", "LCS-Training"]],
	},

	# Employment Type — Full-time (may already exist; safe to re-export)
	{
		"dt": "Employment Type",
		"filters": [["employee_type", "=", "Full-time"]],
	},

	# Custom roles — all others (Field Service User, Dispatcher, Crew Leader,
	# Credit Manager, Fleet Manager, Quality Manager, Training Manager,
	# Compliance Officer, Field Service Manager) already exist in this ERPNext
	# instance. Service Manager and Service Administrator were previously
	# created directly on the live site and are added here so they're no
	# longer dropped on export (same class of gap as the Sales Invoice
	# custom fields fix — see Section 8.9 of the roadmap).
	{
		"dt": "Role",
		"filters": [
			["role_name", "in", [
				"CRM User",
				"CRM Manager",
				"Helpdesk Agent",
				"Helpdesk Manager",
				"Service Manager",
				"Service Administrator",
			]],
		],
	},

	# LCS Standard shift — Mon–Fri 06:30–17:30
	{
		"dt": "Shift Type",
		"filters": [["shift_type_name", "=", "LCS Standard"]],
	},

	# "dt": "User" intentionally excluded.
	# User role assignments are operational data — keeping them in fixtures
	# would overwrite any Desk changes on every deploy.
	# Initial role assignments are handled via ERPNext Data Import (one-time).

	# Print-line consolidation (QBO-bundle-parity: Zone Charge, Travel Labor,
	# Shipping & Receiving Recovery print as one customer-facing line while
	# staying fully itemized in the GL/tax/reports — see LCS Print
	# Consolidation Group doctype and field_service_management/api/print_helpers.py).
	{
		"doctype": "Custom Field",
		"filters": [["name", "in", ["Item-lcs_consolidation_group"]]],
	},
]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = ["/assets/beveren_fsm/css/lcs_theme.css"]
# app_include_js = ["/assets/beveren_fsm/js/beveren_fsm.js"]

# include js, css files in header of web template
# web_include_css = "/assets/beveren_fsm/css/beveren_fsm.css"
# web_include_js = "/assets/beveren_fsm/js/beveren_fsm.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "beveren_fsm/public/scss/website"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {
	"Quotation": "public/js/quotation.js",
	"Lead": "public/js/lead.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# bench --site fsm.local export-fixtures  (reference — actual fixtures list is above)

# Svg Icons
# ------------------
# app_include_icons = "beveren_fsm/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "beveren_fsm.utils.jinja_methods",
# 	"filters": "beveren_fsm.utils.jinja_filters"
# }

jinja = {
	"methods": [
		"beveren_fsm.field_service_management.api.print_helpers.get_print_line_groups",
	]
}

# Installation
# ------------

# before_install = "beveren_fsm.install.before_install"
# after_install = "beveren_fsm.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "beveren_fsm.uninstall.before_uninstall"
# after_uninstall = "beveren_fsm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# before_app_install = "beveren_fsm.utils.before_app_install"
# after_app_install = "beveren_fsm.utils.after_app_install"

# Integration Cleanup
# -------------------
# before_app_uninstall = "beveren_fsm.utils.before_app_uninstall"
# after_app_uninstall = "beveren_fsm.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# notification_config = "beveren_fsm.notifications.get_notification_config"

# Permissions
# -----------
# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"on_submit": [
			"beveren_fsm.field_service_management.fsm_utils.update_invoice_status",
			"beveren_fsm.field_service_management.fsm_utils.update_per_billed_status",
		],
		"on_cancel": [
			"beveren_fsm.field_service_management.fsm_utils.update_invoice_status",
			"beveren_fsm.field_service_management.fsm_utils.update_per_billed_status",
		],
	},
	"Delivery Note": {
		"on_submit": [
			"beveren_fsm.field_service_management.doctype.service_order.service_order.update_product_movement_on_submit",
		],
	},
	"Purchase Order": {
		"on_submit": [
			"beveren_fsm.field_service_management.doctype.service_order.service_order.update_product_movement_on_submit",
		],
	},
	"Purchase Receipt": {
		"on_submit": [
			"beveren_fsm.field_service_management.doctype.service_order.service_order.update_product_movement_on_submit",
		],
	},
	"Purchase Invoice": {
		"on_submit": [
			"beveren_fsm.field_service_management.doctype.service_order.service_order.update_product_movement_on_submit",
		],
	},
	"Stock Entry": {
		"on_submit": [
			"beveren_fsm.field_service_management.doctype.service_order.service_order.update_product_movement_on_submit",
		],
	},
	"Service Order": {
		"validate": "beveren_fsm.field_service_management.api.tech_pwa.copy_instructions_from_request",
	},
	"Service Appointment": {
		"validate": "beveren_fsm.field_service_management.api.tech_pwa.copy_instructions_from_order",
		"on_update": "beveren_fsm.field_service_management.api.tech_pwa.send_scheduled_confirmation_email",
	},
	"Lead": {
		"after_insert": "beveren_fsm.field_service_management.api.lead_referral.on_lead_after_insert",
	},
	"Communication": {
		"after_insert": "beveren_fsm.field_service_management.api.bookkeeper_mail.link_bookkeeper_communication",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"beveren_fsm.field_service_management.doctype.service_request.service_request.update_status",
		"beveren_fsm.field_service_management.doctype.lcs_service_agreement.lcs_service_agreement.auto_create_service_orders",
		"beveren_fsm.field_service_management.doctype.lcs_customer_equipment.lcs_customer_equipment.flag_overdue_equipment",
		"beveren_fsm.field_service_management.doctype.lcs_controlled_document.lcs_controlled_document.flag_documents_approaching_review",
		"beveren_fsm.field_service_management.doctype.lcs_reference_standard.lcs_reference_standard.flag_reference_standards_due_for_recalibration",
	],
}

# Testing
# -------

# before_tests = "beveren_fsm.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "beveren_fsm.event.get_events"
# }
#
# override_doctype_dashboards = {
# 	"Task": "beveren_fsm.task.get_dashboard_data"
# }

# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["beveren_fsm.utils.before_request"]
# after_request = ["beveren_fsm.utils.after_request"]

# Job Events
# ----------
# before_job = ["beveren_fsm.utils.before_job"]
# after_job = ["beveren_fsm.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"beveren_fsm.auth.validate"
# ]

# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


website_route_rules = [
	{"from_route": "/schedule/<path:app_path>", "to_route": "schedule"},
]
