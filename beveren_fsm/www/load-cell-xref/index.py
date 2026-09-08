"""
Place at: beveren_fsm/www/load-cell-xref/index.py
(alongside index.html in the same www/load-cell-xref/ folder)

The folder name is hyphenated, matching the public URL /load-cell-xref.
This was double-checked against two live precedents already deployed in
this exact repo — beveren_fsm/www/service-agreement-quote/index.py and
beveren_fsm/www/vehicle-inspection/ — both hyphenated on-disk www page
folders with working Python controllers. The hyphen-breaks-the-module-path
bug from PR #20/#21 was specific to Web Form controller resolution
(Frappe scrubs the docname to build that module path); plain www/ page
controllers are loaded directly from their on-disk path and hyphens are
fine there. No website_route_rules entry is needed for this page.

Matches the real pattern used by www/shortcuts/index.py: a module-level
login_required flag rather than a manual guest check.
"""

import frappe

login_required = True


def get_context(context):
    context.no_cache = 1
