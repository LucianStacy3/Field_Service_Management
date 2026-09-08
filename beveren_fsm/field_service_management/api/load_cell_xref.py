"""
Load Cell Cross-Reference search API.

Place this file at:
  beveren_fsm/field_service_management/api/load_cell_xref.py

(same folder as tech_pwa.py, lead_referral.py, schedule.py, etc.)

Called as: /api/method/beveren_fsm.field_service_management.api.load_cell_xref.search

@frappe.whitelist() is declared at module level, not inside a class, per the
app's established convention (see hooks.py doc_events for other examples).
"""

import frappe


@frappe.whitelist()
def search(query: str = "", limit: int = 100):
    """
    Search LCS Load Cell Family / LCS Load Cell Equivalent for any manufacturer
    name or model/part-number fragment. Returns a list of matched families, each
    with its full list of equivalents attached.
    """
    query = (query or "").strip()
    limit = min(int(limit or 100), 200)

    if not query:
        family_names = frappe.get_all("LCS Load Cell Family", fields=["name"], order_by="primary_manufacturer asc, primary_label asc", limit_page_length=limit)
        names = [f.name for f in family_names]
    else:
        like = f"%{query}%"
        sql = "select distinct f.name from `tabLCS Load Cell Family` f left join `tabLCS Load Cell Equivalent` e on e.parent = f.name where f.primary_label like %(like)s or f.primary_manufacturer like %(like)s or f.coti_sku like %(like)s or e.model like %(like)s or e.manufacturer like %(like)s limit %(limit)s"
        rows = frappe.db.sql(sql, {"like": like, "limit": limit}, as_dict=True)
        names = [r.name for r in rows]

    if not names:
        return []

    families = frappe.get_all("LCS Load Cell Family", filters={"name": ["in", names]}, fields=["name", "primary_label", "primary_manufacturer", "source", "coti_sku", "zemic_ntep_cc"])

    for fam in families:
        fam["equivalents"] = frappe.get_all("LCS Load Cell Equivalent", filters={"parent": fam["name"]}, fields=["manufacturer", "model"], order_by="manufacturer asc")

    return families
