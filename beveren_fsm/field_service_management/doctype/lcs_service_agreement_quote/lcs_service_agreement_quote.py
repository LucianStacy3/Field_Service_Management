import frappe
from frappe.model.document import Document

# ---------------------------------------------------------------------------
# BASE PRICING TABLE
#
# Derived from LCS Scale Calibration Manual of Labor Units (MLU) 2026.
# Labor hours x $120/hr (internal rate), rounded to nearest $5.
# Keys match the scale_type Select options in the child table JSON exactly.
# Format: { "Scale Type String": (normal_price, difficult_price, very_difficult_price) }
# ---------------------------------------------------------------------------

LCS_BASE_PRICE = {
	# Bench Scales
	"Bench Scale — 0-30 lb": (60, 90, 120),
	"Bench Scale — 31-100 lb": (75, 105, 150),
	"Bench Scale — 101-250 lb": (90, 120, 180),
	"Bench Scale — NTEP / Legal-for-Trade": (90, 120, 180),
	"Bench Scale — Washdown (IP65/69K)": (90, 120, 180),
	# Counting Scales
	"Counting Scale — 0-30 lb": (75, 105, 150),
	"Counting Scale — 31-100 lb": (90, 120, 180),
	"Counting Scale — Dual-Range": (105, 150, 210),
	"Retail / Price-Computing Scale": (90, 120, 150),
	# Floor / Platform Scales
	"Floor Scale — 0-1,000 lb": (120, 180, 240),
	"Floor Scale — 1,001-5,000 lb": (150, 210, 315),
	"Floor Scale — 5,001-10,000 lb": (180, 285, 420),
	"Floor Scale — 10,001-20,000 lb": (210, 360, 495),
	"Floor Scale — Pit-Mounted (add-on)": (75, 105, 180),
	"Pallet Jack Scale": (120, 180, 240),
	"Pallet Jack Scale — Wireless": (150, 210, 285),
	# Process / Industrial Scales
	"Tank / Hopper Scale — Single Vessel": (240, 360, 480),
	"Tank / Hopper Scale — Multi-Vessel": (360, 480, 600),
	"Conveyor / Belt Scale": (300, 420, 540),
	"Animal / Livestock Scale": (180, 270, 360),
	# Truck Scales
	"Truck Scale — Steel Deck, Above Ground": (480, 720, 960),
	"Truck Scale — Steel Deck, Pit Mounted": (600, 840, 1200),
	"Truck Scale — Portable / Axle Pad": (300, 420, 600),
	"Onboard Truck Weighing System": (360, 540, 720),
	# Specialty
	"Crane / Overhead Scale": (180, 270, 360),
	"Rail Scale": (480, 720, 960),
	"Mixer / Batch Scale": (240, 360, 480),
	"Other (see Notes)": (0, 0, 0),
}

DIFFICULTY_INDEX = {"Normal": 0, "Difficult": 1, "Very Difficult": 2}


def suggested_price(scale_type: str, difficulty: str) -> float:
	"""Return the MLU-derived suggested unit price for a given scale type and difficulty."""
	prices = LCS_BASE_PRICE.get(scale_type)
	if not prices:
		return 0.0
	idx = DIFFICULTY_INDEX.get(difficulty, 0)
	return float(prices[idx])


class LCSServiceAgreementQuote(Document):
	# -----------------------------------------------------------------------
	# Lifecycle hooks
	# -----------------------------------------------------------------------

	def before_save(self):
		self._recalc_rows()
		self._recalc_totals()

	def validate(self):
		self._validate_schedule()
		self._recalc_rows()
		self._recalc_totals()

	# -----------------------------------------------------------------------
	# Internal helpers
	# -----------------------------------------------------------------------

	def _recalc_rows(self):
		"""Ensure extended_price = unit_price x quantity for every row."""
		for row in self.equipment_items or []:
			qty = int(row.quantity or 1)
			unit = float(row.unit_price or 0)
			row.extended_price = round(unit * qty, 2)

	def _recalc_totals(self):
		"""Sum extended prices → price_per_service; multiply by visits → annual_total."""
		self.price_per_service = sum(float(r.extended_price or 0) for r in (self.equipment_items or []))
		visits = self._visits_per_year()
		self.visits_per_year = visits
		self.annual_total = round(self.price_per_service * visits, 2)

	def _visits_per_year(self) -> float:
		if self.schedule_type == "Interval" and self.interval_months:
			m = int(self.interval_months)
			return round(12 / m, 4) if m > 0 else 0
		return 0

	def _validate_schedule(self):
		if self.schedule_type == "Interval":
			if not self.interval_months or int(self.interval_months) <= 0:
				frappe.throw("Interval (Months) must be a positive integer.")

	# -----------------------------------------------------------------------
	# Action: Convert to Service Agreement
	# -----------------------------------------------------------------------

	@frappe.whitelist()
	def convert_to_service_agreement(self):
		if self.status != "Accepted":
			frappe.throw("Quote must be Accepted before converting.")

		if self.linked_service_agreement:
			frappe.throw(
				f"Already converted: "
				f"<a href='/app/lcs-service-agreement/{self.linked_service_agreement}'>"
				f"{self.linked_service_agreement}</a>"
			)

		sa = frappe.new_doc("LCS Service Agreement")
		sa.customer = self.customer_name
		sa.capacity_class = self.capacity_class
		sa.schedule_type = self.schedule_type
		sa.interval_months = self.interval_months or 0

		# Equipment rows → SA equipment child table
		for item in self.equipment_items or []:
			sa.append(
				"equipment",
				{
					"location": item.location,
					"make": item.make,
					"model": item.model,
					"serial_no": item.serial_no,
					"capacity": f"{item.capacity or ''} {item.capacity_unit or ''}".strip(),
					"description": item.scale_type,
				},
			)

		sa.insert(ignore_permissions=True)

		self.db_set("linked_service_agreement", sa.name, update_modified=False)
		self.db_set("status", "Converted", update_modified=False)

		frappe.msgprint(
			f"Service Agreement " f"<a href='/app/lcs-service-agreement/{sa.name}'>{sa.name}</a> created.",
			title="Converted",
			indicator="green",
		)
		return sa.name


# ---------------------------------------------------------------------------
# Module-level whitelisted function — must live outside the class so Frappe
# can resolve it via the dotted module path in frappe.call()
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_suggested_price(scale_type: str, difficulty: str) -> dict:
	"""Return { "price": <float> } for the given scale type and difficulty."""
	return {"price": suggested_price(scale_type, difficulty)}
