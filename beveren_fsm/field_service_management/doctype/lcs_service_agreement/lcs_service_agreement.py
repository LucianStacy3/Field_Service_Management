# Copyright (c) 2026, Left Coast Scales, LLC and contributors
# For license information, please see license.txt

import calendar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, get_last_day, getdate, nowdate, today

# ---------------------------------------------------------------------------
# Month name → number map
# ---------------------------------------------------------------------------
MONTH_MAP = {
	"January": 1,
	"February": 2,
	"March": 3,
	"April": 4,
	"May": 5,
	"June": 6,
	"July": 7,
	"August": 8,
	"September": 9,
	"October": 10,
	"November": 11,
	"December": 12,
}

WEEKDAY_MAP = {
	"Monday": 0,
	"Tuesday": 1,
	"Wednesday": 2,
	"Thursday": 3,
	"Friday": 4,
	"Saturday": 5,
	"Sunday": 6,
}

WEEK_NUMBER_MAP = {
	"1st": 1,
	"2nd": 2,
	"3rd": 3,
	"4th": 4,
	"Last": -1,
}


# ---------------------------------------------------------------------------
# DocType controller
# ---------------------------------------------------------------------------


class LCSServiceAgreement(Document):
	# ------------------------------------------------------------------
	# Frappe lifecycle hooks
	# ------------------------------------------------------------------

	def validate(self):
		self.validate_dates()
		self.validate_recurrence()
		self.validate_due_date_rule()
		self.initialise_next_service_order_date()
		self.auto_expire()

	# ------------------------------------------------------------------
	# Validation helpers
	# ------------------------------------------------------------------

	def validate_dates(self):
		if self.contract_end_date and self.contract_start_date:
			if getdate(self.contract_end_date) < getdate(self.contract_start_date):
				frappe.throw(_("Contract End Date cannot be earlier than Contract Start Date"))

	def validate_recurrence(self):
		if self.recurrence_type == "Interval":
			if not self.recurrence_interval or int(self.recurrence_interval) < 1:
				frappe.throw(_("Recurrence Interval must be at least 1"))
			if not self.recurrence_unit:
				frappe.throw(_("Recurrence Unit is required for Interval schedules"))

		elif self.recurrence_type == "Fixed Months":
			if not self.fixed_months:
				frappe.throw(_("Please add at least one month to the Service Months table"))
			# Deduplicate month entries
			seen = set()
			for row in self.fixed_months:
				if row.month in seen:
					frappe.throw(_("Month {0} appears more than once in Service Months").format(row.month))
				seen.add(row.month)

	def validate_due_date_rule(self):
		if self.due_date_type == "Nth Weekday of Month":
			if not self.due_week_number:
				frappe.throw(_("Week Number is required for 'Nth Weekday of Month' due date rule"))
			if not self.due_weekday:
				frappe.throw(_("Weekday is required for 'Nth Weekday of Month' due date rule"))

	def initialise_next_service_order_date(self):
		"""
		Set next_service_order_date on first save only (no_copy=1 means it arrives
		blank on new docs). After the first save the scheduler owns this field.
		"""
		if not self.next_service_order_date and self.contract_start_date:
			if self.recurrence_type == "Fixed Months":
				# Find the first listed month on/after contract_start_date
				self.next_service_order_date = self._first_fixed_month_trigger(
					getdate(self.contract_start_date)
				)
			else:
				self.next_service_order_date = self.contract_start_date

	def auto_expire(self):
		if (
			self.contract_end_date
			and getdate(self.contract_end_date) < getdate(today())
			and self.status == "Active"
		):
			self.status = "Expired"

	# ------------------------------------------------------------------
	# Recurrence helpers — next trigger date
	# ------------------------------------------------------------------

	def _advance_interval(self, from_date):
		"""Return the date one recurrence interval after from_date."""
		from_date = getdate(from_date)
		interval = int(self.recurrence_interval or 1)
		unit = (self.recurrence_unit or "Month").lower()

		if unit == "day":
			return add_days(from_date, interval)
		elif unit == "week":
			return add_days(from_date, interval * 7)
		elif unit == "month":
			return add_months(from_date, interval)
		elif unit == "year":
			return add_months(from_date, interval * 12)
		return add_months(from_date, interval)

	def _first_fixed_month_trigger(self, on_or_after):
		"""
		Return the 1st of the earliest listed month that falls on or after
		on_or_after. Wraps into the next year if necessary.
		"""
		on_or_after = getdate(on_or_after)
		month_numbers = sorted(MONTH_MAP[row.month] for row in self.fixed_months if row.month in MONTH_MAP)
		if not month_numbers:
			return None

		year = on_or_after.year
		for month_num in month_numbers:
			candidate = getdate(f"{year}-{month_num:02d}-01")
			if candidate >= on_or_after:
				return candidate

		# All listed months in the current year are in the past — use the first
		# listed month of next year.
		return getdate(f"{year + 1}-{month_numbers[0]:02d}-01")

	def _next_fixed_month_trigger(self, after_date):
		"""
		Return the 1st of the next listed month strictly after after_date.
		"""
		after_date = getdate(after_date)
		# Move one day forward so "strictly after" works cleanly
		return self._first_fixed_month_trigger(add_days(after_date, 1))

	# ------------------------------------------------------------------
	# Due-date calculation for a given service month/year
	# ------------------------------------------------------------------

	def compute_due_date(self, service_year, service_month):
		"""
		Given the year and month of the service (integers), return the due date
		according to the agreement's due_date_type rule.

		service_year / service_month are the year/month of the Service Order
		being created (i.e., the month the work must be done in).
		"""
		due_type = self.due_date_type or "End of Service Month"

		if due_type == "End of Service Month":
			return _last_day_of_month(service_year, service_month)

		elif due_type == "Last Service + Interval":
			base = getdate(self.last_service_date or self.contract_start_date or today())
			if self.recurrence_type == "Interval":
				return self._advance_interval(base)
			else:
				# Fixed Months: due = last_service_date + 1 full recurrence cycle
				# (distance to the next occurrence in the fixed list)
				return self._next_fixed_month_trigger(base)

		elif due_type == "Nth Weekday of Month":
			return _nth_weekday_of_month(
				service_year,
				service_month,
				WEEK_NUMBER_MAP.get(self.due_week_number, 1),
				WEEKDAY_MAP.get(self.due_weekday, 3),  # default Thursday
			)

		# Fallback
		return _last_day_of_month(service_year, service_month)

	# ------------------------------------------------------------------
	# Service Order creation
	# ------------------------------------------------------------------

	def create_service_order(self, trigger_date=None):
		"""
		Create one Service Order for this agreement.
		trigger_date is a date object representing the month being serviced
		(used for Fixed Months due-date calculations).  Defaults to today.

		Returns the new Service Order name, or None on failure.
		Advances next_service_order_date and last_auto_created_date after success.
		"""
		trigger_date = getdate(trigger_date or today())

		if not self.customer:
			frappe.throw(_("Agreement {0} has no customer — cannot create Service Order").format(self.name))

		# --- Due date ---
		due = self.compute_due_date(trigger_date.year, trigger_date.month)

		# --- Build Service Order ---
		# ------------------------------------------------------------------
		# Fix added: this used to fall back to a hardcoded literal
		# ("Calibration") whenever an agreement had no Service Type set.
		# That literal doesn't match any actual "Service Type" record on
		# this site (the real seeded value is e.g. "ZZTEST Calibration
		# Service"), so any agreement without an explicit service_type
		# crashed so.insert() with a cryptic LinkValidationError instead of
		# creating the Service Order. service_type is an optional field on
		# this doctype (not reqd), so a blank value is a legitimate,
		# reachable state -- it must be handled, not crashed on. Matching
		# the existing defensive pattern used below for the missing
		# placeholder Item: log a clear, actionable error and skip this
		# agreement instead of throwing.
		# ------------------------------------------------------------------
		if not self.service_type:
			frappe.log_error(
				title=f"LCS Service Agreement {self.name} — missing Service Type",
				message=(
					"This agreement has no Service Type set. Service Order was not "
					"created. Set a valid Service Type on the agreement before its "
					"next trigger date."
				),
			)
			return None

		so = frappe.new_doc("Service Order")
		so.customer = self.customer
		so.company = self.company
		so.type = self.service_type
		so.service_area = self.service_area or None
		so.priority = self.priority or "Medium"
		so.posting_date = today()
		so.due_date = str(due)
		so.lcs_service_agreement = self.name

		# ------------------------------------------------------------------
		# Fix added: price_list_currency and plc_conversion_rate are
		# mandatory on Service Order, but only ever get populated by the
		# desk UI's client-side price-list/currency JS when a human picks
		# a Selling Price List. A purely server-side insert (this nightly
		# scheduler) never runs that JS, so insert() failed with
		# MandatoryError: price_list_currency, plc_conversion_rate.
		# This agreement-generated order always uses the free placeholder
		# item below, so there's no real multi-currency pricing to
		# resolve -- default price_list_currency to the company's own
		# currency and the exchange rate to 1.0, the same values the JS
		# would compute for the common single-currency case.
		# ------------------------------------------------------------------
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		so.currency = so.currency or company_currency
		so.price_list_currency = company_currency
		so.plc_conversion_rate = 1.0
		so.conversion_rate = 1.0

		if self.smartercerts_url:
			so.external_system_link = self.smartercerts_url

		# Job requirement notes → Service Order description field (if it exists)
		job_summary = _build_job_summary(self)
		if job_summary and hasattr(so, "description"):
			so.description = job_summary

		# Placeholder item
		placeholder_item = frappe.db.get_value(
			"Item", {"item_name": "Agreement Service", "disabled": 0}, "name"
		)
		if not placeholder_item:
			frappe.log_error(
				title=f"LCS Service Agreement {self.name} — missing placeholder item",
				message=(
					"No active Item named 'Agreement Service' found. "
					"Service Order was not created. Create the item or seed items into the agreement."
				),
			)
			return None

		so.append("items", {"item_code": placeholder_item, "qty": 1, "rate": 0})
		so.insert(ignore_permissions=True)

		# --- Advance schedule ---
		if self.recurrence_type == "Interval":
			next_trigger = self._advance_interval(trigger_date)
		else:
			next_trigger = self._next_fixed_month_trigger(trigger_date)

		self.db_set("last_auto_created_date", today(), update_modified=False)
		self.db_set("next_service_order_date", next_trigger, update_modified=False)

		frappe.logger().info(
			f"LCS Agreement {self.name}: created SO {so.name} " f"(due {due}); next trigger → {next_trigger}"
		)
		return so.name


# ---------------------------------------------------------------------------
# Pure-function date helpers
# ---------------------------------------------------------------------------


def _last_day_of_month(year, month):
	"""Return the last calendar day of the given year/month as a date."""
	last_day = calendar.monthrange(year, month)[1]
	return getdate(f"{year}-{month:02d}-{last_day:02d}")


def _nth_weekday_of_month(year, month, week_number, weekday):
	"""
	Return the date of the Nth occurrence of weekday in year/month.

	week_number: 1-4 for 1st-4th, -1 for Last.
	weekday: 0=Monday ... 6=Sunday (calendar.weekday convention).

	Always returns a date within the given month (never overflows to next month).
	"""
	# Collect all occurrences of the weekday in the month
	_, days_in_month = calendar.monthrange(year, month)
	occurrences = [d for d in range(1, days_in_month + 1) if calendar.weekday(year, month, d) == weekday]

	if not occurrences:
		# Should never happen for a valid weekday, but guard anyway
		return _last_day_of_month(year, month)

	if week_number == -1:
		day = occurrences[-1]
	else:
		idx = week_number - 1
		# Clamp: if the month only has 4 occurrences and 5th was requested,
		# use the last one (keeps due date inside the service month)
		day = occurrences[min(idx, len(occurrences) - 1)]

	return getdate(f"{year}-{month:02d}-{day:02d}")


def _build_job_summary(agreement):
	"""Build a plain-text job requirements summary from agreement fields."""
	parts = []
	if agreement.equipment_required:
		parts.append(f"Equipment: {agreement.equipment_required.strip()}")
	if agreement.ppe_requirements:
		parts.append(f"PPE: {agreement.ppe_requirements.strip()}")
	if agreement.weight_standards:
		parts.append(f"Weight Standards: {agreement.weight_standards.strip()}")
	if agreement.calibration_sticker_type and agreement.calibration_sticker_type != "Other / See Notes":
		parts.append(f"Sticker Type: {agreement.calibration_sticker_type}")
	if agreement.job_notes:
		parts.append(agreement.job_notes.strip())
	return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Scheduler entry point — called nightly from hooks.py
# ---------------------------------------------------------------------------


def auto_create_service_orders():
	"""
	Nightly scheduler task.

	For Interval agreements: fires when next_service_order_date <= today.
	For Fixed Months agreements: fires on the 1st of each listed month
	  (next_service_order_date is always set to the 1st of the upcoming
	   service month, so the same <= today check works).

	Errors are isolated per agreement so one bad record can't block others.
	"""
	today_date = getdate(today())

	agreements = frappe.get_all(
		"LCS Service Agreement",
		filters={
			"status": "Active",
			"auto_create_service_orders": 1,
			"next_service_order_date": ["<=", today_date],
		},
		fields=["name"],
	)

	for row in agreements:
		try:
			doc = frappe.get_doc("LCS Service Agreement", row.name)

			# Auto-expire if end date passed
			if doc.contract_end_date and getdate(doc.contract_end_date) < today_date:
				doc.db_set("status", "Expired", update_modified=False)
				frappe.logger().info(f"LCS Agreement {doc.name}: marked Expired.")
				continue

			trigger_date = getdate(doc.next_service_order_date)
			so_name = doc.create_service_order(trigger_date=trigger_date)

			if so_name:
				frappe.logger().info(f"Scheduler: SO {so_name} created for agreement {doc.name}")

		except Exception:
			frappe.log_error(
				title=f"LCS Service Agreement auto-create failed: {row.name}",
				message=frappe.get_traceback(),
			)
