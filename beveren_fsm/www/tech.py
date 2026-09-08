# Copyright (c) 2026, Left Coast Scales, LLC and contributors
# For license information, please see license.txt

"""
www/tech.py

Controller for the /tech route — the LCS Field Tech PWA shell. Requires
a logged-in session and a linked Employee record, since every whitelisted
API in field_service_management.api.tech_pwa assumes one exists.

Also resolves the *current* built JS/CSS filenames from Vite's build
manifest (asset-manifest.json, copied alongside sw.js/manifest.json in
this same www/tech/ folder at build time) rather than hardcoding them.
Frappe serves /assets/... with long-lived cache headers on the
assumption that filenames change whenever content does — hashed
filenames are what make that assumption true, and reading them from the
manifest means tech.html never needs manual updates after a rebuild.
"""

import json
import os

import frappe
import frappe.sessions

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw("Please log in to use the Field Tech app.", frappe.PermissionError)

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw(
			"No Employee record is linked to your account yet. Contact the office before using the Field Tech app.",
			frappe.PermissionError,
		)

	context.no_breadcrumbs = True
	context.no_header = True
	context.employee = employee

	# tech.html deliberately does not extend templates/web.html (no Frappe
	# site chrome around the app shell), which means it also misses out on
	# the CSRF token injection that page normally provides for free. Every
	# write in api/tech_pwa.py is a whitelisted POST, so without this the
	# token src/api/client.js reads is always empty and every mutation is
	# rejected with CSRFTokenError. Mirrors the working pattern in
	# www/schedule.py and www/service-agreement-quote/index.py.
	context.csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep

	manifest = _load_asset_manifest()
	entry = manifest.get("index.html", {})
	context.tech_js = entry.get("file")
	context.tech_css = entry.get("css", [])
	return context


def _load_asset_manifest() -> dict:
	# Resolved relative to this file rather than via frappe.get_app_path —
	# tech.py and its sibling tech/asset-manifest.json always sit next to
	# each other on disk no matter where Frappe has this app installed,
	# so this can't drift the way an app-name-based lookup can.
	manifest_path = os.path.join(os.path.dirname(__file__), "tech", "asset-manifest.json")
	if not os.path.exists(manifest_path):
		frappe.log_error(
			title="Tech PWA asset manifest missing",
			message=f"Expected {manifest_path} — did the frontend build output get committed?",
		)
		return {}
	with open(manifest_path) as f:
		return json.load(f)