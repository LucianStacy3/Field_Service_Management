# Copyright (c) 2026, Left Coast Scales
# For license information, please see license.txt
#
# Tax Table Importer -- reads Avalara-format "TAXRATES_ZIP5" CSV files (the
# CA/AZ ZIP-code sales tax tables) and creates/updates the standard ERPNext
# records that back ZIP-based tax automation:
#
#   1. One "Sales Taxes and Charges Template" per unique combined rate,
#      per state (e.g. "LCS Sales Tax - CA 10.5000%")
#   2. One "Tax Rule" per ZIP code, matching on billing_zipcode + state,
#      pointing at the matching template above
#
# Expected CSV columns (Avalara TaxRates ZIP5 export):
#   State, ZipCode, TaxRegionName, EstimatedCombinedRate, StateRate,
#   EstimatedCountyRate, EstimatedCityRate, EstimatedSpecialRate, RiskLevel
#
# Runs as a background job (the CA + AZ files together are ~3,000 rows,
# too slow for a single synchronous HTTP request) with live progress sent
# to the browser over Frappe's realtime channel. Re-uploading a newer
# quarter's file updates existing Tax Rule / template records in place
# rather than duplicating them (which would otherwise trip ERPNext's
# "Conflicting Tax Rule" check on identical zipcode/state/company filters).
#
# Drop this file at:
#   beveren_fsm/field_service_management/api/tax_rate_import.py

import csv
import io

import frappe
from frappe import _

TEMPLATE_PREFIX = "LCS Sales Tax"
PROGRESS_EVENT = "lcs_tax_import_progress"
DONE_EVENT = "lcs_tax_import_done"
COUNTRY_BY_STATE = {"CA": "United States", "AZ": "United States"}


def _default_company():
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        companies = frappe.get_all("Company", pluck="name", limit=1)
        company = companies[0] if companies else None
    if not company:
        frappe.throw(_("No Company exists on this site yet. Complete the ERPNext Setup Wizard first."))
    return company


def _resolve_tax_account(company, tax_account=None):
    """Find (or create) an Account to post the imported sales tax templates to."""
    if tax_account:
        if not frappe.db.exists("Account", tax_account):
            frappe.throw(_("Account {0} does not exist.").format(tax_account))
        return tax_account

    # 1. An existing non-group Tax account
    existing = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name"
    )
    if existing:
        return existing

    # 2. A group Tax account (e.g. "Duties and Taxes") -- create a leaf under it
    parent = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Tax", "is_group": 1}, "name"
    )
    # 3. Fall back to an account literally named "Duties and Taxes"
    if not parent:
        parent = frappe.db.get_value(
            "Account", {"company": company, "account_name": ["like", "%Duties and Taxes%"], "is_group": 1}, "name"
        )
    # 4. Fall back to any root Liability group (e.g. "Current Liabilities")
    if not parent:
        parent = frappe.db.get_value(
            "Account",
            {"company": company, "root_type": "Liability", "is_group": 1, "account_name": ["like", "%Current Liabilities%"]},
            "name",
        )
    if not parent:
        frappe.throw(
            _(
                "Couldn't find a suitable parent account to create a Sales Tax Payable account "
                "under (looked for a Tax-type or 'Duties and Taxes' or 'Current Liabilities' group "
                "on Company {0}). Set up your Chart of Accounts first, or specify a Tax Account "
                "manually on the importer page."
            ).format(company)
        )

    company_abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = f"Sales Tax Payable - {company_abbr}"
    if frappe.db.exists("Account", account_name):
        return account_name

    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": "Sales Tax Payable",
            "parent_account": parent,
            "company": company,
            "account_type": "Tax",
            "is_group": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _get_or_create_template(company, tax_account, state, rate_decimal, cache):
    """rate_decimal is e.g. 0.105 for 10.5%. One template per (state, rate)."""
    key = (state, round(rate_decimal, 6))
    if key in cache:
        return cache[key]

    rate_pct = round(rate_decimal * 100, 4)
    title = f"{TEMPLATE_PREFIX} - {state} {rate_pct:.4f}%"

    existing = frappe.db.get_value("Sales Taxes and Charges Template", {"title": title, "company": company}, "name")
    if existing:
        cache[key] = existing
        return existing

    doc = frappe.get_doc(
        {
            "doctype": "Sales Taxes and Charges Template",
            "title": title,
            "company": company,
            "taxes": [
                {
                    "charge_type": "On Net Total",
                    "account_head": tax_account,
                    "description": f"{state} Combined Sales Tax ({rate_pct:.4f}%)",
                    "rate": rate_pct,
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    cache[key] = doc.name
    return doc.name


def _upsert_tax_rule(company, state, zipcode, template_name):
    existing = frappe.db.get_value(
        "Tax Rule",
        {"company": company, "tax_type": "Sales", "billing_state": state, "billing_zipcode": zipcode},
        "name",
    )
    if existing:
        current_template = frappe.db.get_value("Tax Rule", existing, "sales_tax_template")
        if current_template != template_name:
            frappe.db.set_value("Tax Rule", existing, "sales_tax_template", template_name)
            return "updated"
        return "unchanged"

    doc = frappe.get_doc(
        {
            "doctype": "Tax Rule",
            "tax_type": "Sales",
            "company": company,
            "billing_state": state,
            "billing_zipcode": zipcode,
            "billing_country": COUNTRY_BY_STATE.get(state, "United States"),
            "sales_tax_template": template_name,
            "priority": 1,
        }
    )
    doc.insert(ignore_permissions=True)
    return "created"


def parse_rate_file(content):
    """Yields dicts with state, zipcode, rate (float) from raw CSV text.
    Split out so it can be unit-tested / dry-run without touching the DB."""
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        state = (row.get("State") or "").strip().upper()
        zipcode = (row.get("ZipCode") or "").strip()
        rate_raw = row.get("EstimatedCombinedRate")
        if not state or not zipcode or rate_raw in (None, ""):
            continue
        yield {"state": state, "zipcode": zipcode, "rate": float(rate_raw), "region": row.get("TaxRegionName")}


@frappe.whitelist()
def import_tax_rates(file_url, company=None, tax_account=None):
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a System Manager can import tax rates."), frappe.PermissionError)

    company = company or _default_company()
    file_doc = frappe.get_doc("File", {"file_url": file_url})

    frappe.enqueue(
        _run_import,
        queue="long",
        timeout=3600,
        job_name=f"lcs_tax_import_{file_doc.name}",
        file_name=file_doc.file_name,
        content=file_doc.get_content(),
        company=company,
        tax_account=tax_account,
        user=frappe.session.user,
    )
    return {"queued": True}


def _run_import(file_name, content, company, tax_account, user):
    rows = list(parse_rate_file(content if isinstance(content, str) else content.decode("utf-8")))
    total = len(rows)
    stats = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0}
    error_samples = []

    try:
        tax_account = _resolve_tax_account(company, tax_account)
    except Exception as e:
        frappe.publish_realtime(
            DONE_EVENT,
            {"ok": False, "message": str(e), "file_name": file_name},
            user=user,
        )
        return

    template_cache = {}

    for i, row in enumerate(rows, start=1):
        try:
            template_name = _get_or_create_template(company, tax_account, row["state"], row["rate"], template_cache)
            result = _upsert_tax_rule(company, row["state"], row["zipcode"], template_name)
            stats[result] += 1
        except Exception:
            stats["errors"] += 1
            if len(error_samples) < 10:
                error_samples.append(f"{row.get('state')} {row.get('zipcode')}: {frappe.get_traceback(with_context=False)[:300]}")
            frappe.log_error(title=f"LCS tax import row failed: {row}", message=frappe.get_traceback())

        if i % 100 == 0 or i == total:
            frappe.db.commit()
            frappe.publish_realtime(
                PROGRESS_EVENT,
                {"processed": i, "total": total, "file_name": file_name, **stats},
                user=user,
            )

    frappe.db.commit()
    frappe.publish_realtime(
        DONE_EVENT,
        {
            "ok": True,
            "file_name": file_name,
            "total": total,
            "tax_account": tax_account,
            "unique_templates": len(template_cache),
            "error_samples": error_samples,
            **stats,
        },
        user=user,
    )


@frappe.whitelist()
def remove_imported_tax_rules(company=None):
    """Optional cleanup/redo: removes every Tax Rule + Sales Taxes and Charges
    Template this importer created (identified by the title prefix), so you
    can start over cleanly. Does not touch anything else in your Chart of
    Accounts, and leaves the Tax Account itself in place."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a System Manager can do this."), frappe.PermissionError)

    company = company or _default_company()

    templates = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company, "title": ["like", f"{TEMPLATE_PREFIX}%"]},
        pluck="name",
    )
    rule_count = 0
    for template_name in templates:
        rules = frappe.get_all("Tax Rule", filters={"sales_tax_template": template_name}, pluck="name")
        for r in rules:
            frappe.delete_doc("Tax Rule", r, ignore_permissions=True, force=True)
            rule_count += 1
        frappe.delete_doc("Sales Taxes and Charges Template", template_name, ignore_permissions=True, force=True)

    frappe.db.commit()
    return {"templates_removed": len(templates), "rules_removed": rule_count}
