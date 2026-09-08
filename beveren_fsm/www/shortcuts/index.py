import frappe
from itertools import groupby

login_required = True

# Section display config: section name -> (emoji, css theme class)
SECTION_META = {
    "Sales":                   ("📋", "ts"),
    "Service":                 ("🔧", "tv"),
    "Vehicle & Fleet":         ("🚛", "tg"),
    "Training & LCS Academy":  ("🎓", "tt"),
    "HR & Personnel":          ("👤", "th"),
    "Admin & Compliance":      ("⚙️", "ta"),
}

SECTION_ORDER = list(SECTION_META.keys())


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)

    context.no_cache = 1

    # --- Employee info ---
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        ["employee_name", "designation", "department"],
        as_dict=True,
    )
    if employee:
        context.employee_name = employee.employee_name
        context.designation   = employee.designation or ""
        context.department    = employee.department or ""
    else:
        context.employee_name = (
            frappe.db.get_value("User", frappe.session.user, "full_name")
            or frappe.session.user
        )
        context.designation = ""
        context.department  = ""

    # --- Current user's roles ---
    user_roles = set(frappe.get_roles(frappe.session.user))

    # --- Fetch all enabled shortcuts ---
    rows = frappe.get_all(
        "LCS Shortcut",
        filters={"enabled": 1},
        fields=["name", "label", "section", "shortcut_url", "description", "icon", "badge", "sort_order"],
        order_by="section asc, sort_order asc, label asc",
    )

    # Remap shortcut_url -> url for the template
    for row in rows:
        row["url"] = row.get("shortcut_url") or ""

    # --- Fetch all role restrictions in one query ---
    all_role_rows = frappe.get_all(
        "LCS Shortcut Role",
        filters={"parent": ["in", [r["name"] for r in rows]]},
        fields=["parent", "role"],
    )

    # Build a dict: shortcut name -> set of allowed roles
    allowed_roles_map = {}
    for rr in all_role_rows:
        allowed_roles_map.setdefault(rr["parent"], set()).add(rr["role"])

    # --- Filter shortcuts by role ---
    visible = []
    for row in rows:
        allowed = allowed_roles_map.get(row["name"])
        if not allowed:
            # No restrictions — visible to everyone
            visible.append(row)
        elif user_roles & allowed:
            # User has at least one of the required roles
            visible.append(row)

    # --- Group by section, preserving canonical order ---
    by_section = {k: list(v) for k, v in groupby(visible, key=lambda r: r["section"])}

    sections = []
    for sec_name in SECTION_ORDER:
        cards = by_section.get(sec_name, [])
        if not cards:
            continue
        icon, theme = SECTION_META.get(sec_name, ("📌", "ta"))
        sections.append({
            "name":  sec_name,
            "icon":  icon,
            "theme": theme,
            "cards": cards,
        })

    # Any section not in canonical order goes last
    for sec_name, cards in by_section.items():
        if sec_name not in SECTION_META:
            sections.append({
                "name":  sec_name,
                "icon":  "📌",
                "theme": "ta",
                "cards": list(cards),
            })

    context.sections = sections

    # --- Admin link visibility ---
    context.is_system_manager = "System Manager" in user_roles