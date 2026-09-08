"""
Bookkeeper mailbox -> Customer/Supplier timeline linking.

Scope: bookkeeper@leftcoastscales.com is LCS's shared accounting inbox --
it receives both AP vendor correspondence (invoices, payment-status mail
from suppliers) and AR/collections-related mail from customers. Neither
side is auto-linked to the relevant ERPNext record by default, so this
hook does that matching whenever new mail lands.

Wired via hooks.py doc_events on Communication / after_insert.
"""

import frappe
from email.utils import parseaddr

BOOKKEEPER_EMAIL_ACCOUNT = "Bookkeeper"


def link_bookkeeper_communication(doc, method=None):
    """
    Runs after any new Communication is inserted. Only acts on inbound
    email received through the Bookkeeper Email Account -- everything
    else (outbound mail, every other mailbox, comments, etc.) is left
    untouched.

    On a match, sets reference_doctype/reference_name so the email shows
    up on the matching Customer's or Supplier's Communication timeline
    in ERPNext. Emails that match neither are left exactly as they land:
    no new Contact, Customer, or Supplier is created, and nothing else
    about the Communication is changed. They simply stay visible,
    unlinked, in the Bookkeeper inbox for manual triage.
    """
    if doc.communication_type != "Communication":
        return
    if doc.communication_medium != "Email":
        return
    if doc.sent_or_received != "Received":
        return
    if doc.email_account != BOOKKEEPER_EMAIL_ACCOUNT:
        return
    if doc.reference_doctype and doc.reference_name:
        # Already linked -- e.g. Frappe threaded this as a reply onto an
        # existing record. Don't clobber a link that may be more specific
        # than what sender-matching alone would produce.
        return

    sender_email = parseaddr(doc.sender or "")[1].strip().lower()
    if not sender_email:
        return

    reference_doctype, reference_name = _match_party(sender_email)
    if not reference_doctype:
        return

    doc.db_set("reference_doctype", reference_doctype, update_modified=False)
    doc.db_set("reference_name", reference_name, update_modified=False)


def _match_party(sender_email: str):
    """
    Resolve a sender's email address to the Customer or Supplier it
    belongs to, checking both sides (LCS's own request -- this mailbox
    carries both AP and AR mail).

    Match order:
      1. Customer.email_id / Supplier.email_id -- a direct hit on the
         party master's own email field, when populated.
      2. A Contact whose email_id matches the sender, resolved to
         whichever Customer or Supplier that Contact is linked to. This
         is the common case in practice: the person actually emailing is
         usually a named contact (an AP clerk, a specific salesperson),
         not the address on the master record itself.

    Returns (doctype, name) or (None, None) if nothing matches.
    """
    for doctype in ("Customer", "Supplier"):
        name = frappe.db.get_value(doctype, {"email_id": sender_email}, "name")
        if name:
            return doctype, name

    contact_name = frappe.db.get_value("Contact", {"email_id": sender_email}, "name")
    if not contact_name:
        return None, None

    links = frappe.get_all(
        "Dynamic Link",
        filters={
            "parenttype": "Contact",
            "parent": contact_name,
            "link_doctype": ["in", ("Customer", "Supplier")],
        },
        fields=["link_doctype", "link_name"],
        limit=1,
    )
    if links:
        return links[0]["link_doctype"], links[0]["link_name"]

    # The Contact matched but isn't linked to a Customer or Supplier --
    # link to the Contact itself rather than leaving the email unlinked.
    return "Contact", contact_name
