// Copyright (c) 2026, Left Coast Scales
// For license information, please see license.txt
//
// CRM bridge for sales-originated service work: adds a "Service Order"
// option to the standard ERPNext Quotation's Create menu, alongside the
// existing "Sales Order" option. Covers the second way service work
// gets generated at LCS -- from Sales, as a new Service Agreement,
// quoted repair, or installation -- as opposed to the customer-call /
// Service Request path (Service Request -> Service Quotation ->
// Service Order).
//
// Injected into the core Quotation form via the doctype_js hook (see
// hooks.py: doctype_js = {"Quotation": "public/js/quotation.js"}) so it
// loads alongside ERPNext's own Quotation client script without
// modifying any ERPNext core files.

frappe.ui.form.on("Quotation", {
  refresh: function (frm) {
    // Only offer this once the Quotation is submitted (mirrors how
    // "Sales Order" only appears post-submit), and not once it's been
    // marked Lost.
    if (frm.doc.docstatus !== 1) return;
    if (frm.doc.status === "Lost") return;

    frm.add_custom_button(
      __("Service Order"),
      () => {
        frappe.model.open_mapped_doc({
          method:
            "beveren_fsm.field_service_management.fsm_utils.make_service_order_from_quotation",
          frm: frm,
        });
      },
      __("Create")
    );
  },
});

// ─────────────────────────────────────────────────────────────────────────
// Quoting-process additions, ported from production's ad hoc "Quotation"
// Client Script (see LCS_ERPNext_Implementation_Roadmap prod-vs-dev diff,
// section 1). Two pieces of that script were deliberately NOT ported:
//
//   - The ZIP-code -> tax template lookup (against a custom "AZ Tax ZIP
//     Map" doctype). Dev already has this natively: a Tax Table Importer
//     (field_service_management/page/tax_table_importer) has loaded the
//     same ~3,091 ZIP codes as live Tax Rule + Sales Taxes and Charges
//     Template records, and ERPNext core already re-applies the matching
//     Tax Rule automatically whenever customer/customer_address changes
//     on a Selling transaction. Re-implementing the lookup here would
//     create a second mechanism fighting the first over taxes_and_charges.
//
//   - Setting taxes_and_charges directly when a customer/item is exempt.
//     Same reasoning: Tax Rule already owns template selection. What IS
//     ported below is the *awareness* check -- flip the existing
//     exempt_from_sales_tax checkbox and tell the user why, so exemption
//     is visible on the form the moment it's known, the same trigger
//     points (customer / customer_address / item add / item remove)
//     production used. If your Tax Rule setup doesn't yet have a 0% rule
//     matching tax_category "Exempt", that's a Tax Rule / Tax Table
//     Importer configuration question, not something to patch around
//     here with a second tax mechanism.
// ─────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Quotation", {
  onload: function (frm) {
    set_company(frm);
    if (frm.doc.__islocal) {
      sync_address_from_opportunity(frm);
    }
  },

  refresh: function (frm) {
    set_company(frm);
    if (frm.doc.__islocal) {
      sync_address_from_opportunity(frm);
    }
  },

  party_name: function (frm) {
    if (frm.doc.quotation_to === "Lead" && frm.doc.party_name) {
      sync_address_from_opportunity(frm);
    }
  },

  customer: function (frm) {
    check_sales_tax_exemption(frm);
  },
  customer_address: function (frm) {
    check_sales_tax_exemption(frm);
  },
  items_add: function (frm) {
    check_sales_tax_exemption(frm);
  },
  items_remove: function (frm) {
    check_sales_tax_exemption(frm);
  },
});

// ── ADDRESS SYNC ────────────────────────────────────────────────────────
// When a Quotation is created against a Lead (e.g. from an Opportunity),
// nothing on core ERPNext pulls the Lead/Opportunity's address onto the
// Quotation automatically. This finds the best match and sets it.

async function sync_address_from_opportunity(frm) {
  if (frm.doc.quotation_to !== "Lead") return;
  if (!frm.doc.party_name) return;
  if (frm.doc.customer_address) return;

  const opp_name = frm.doc.opportunity || frm.doc.prev_doc_name;

  let addresses = [];

  // Path 1: address linked to the source Opportunity
  if (opp_name) {
    addresses = await frappe.db.get_list("Address", {
      filters: [
        ["Dynamic Link", "link_doctype", "=", "Opportunity"],
        ["Dynamic Link", "link_name", "=", opp_name],
      ],
      fields: ["name", "address_type"],
      order_by: "modified desc",
      limit: 5,
    });
  }

  // Path 2: address linked directly to the Lead
  if (!addresses || addresses.length === 0) {
    addresses = await frappe.db.get_list("Address", {
      filters: [
        ["Dynamic Link", "link_doctype", "=", "Lead"],
        ["Dynamic Link", "link_name", "=", frm.doc.party_name],
      ],
      fields: ["name", "address_type"],
      order_by: "modified desc",
      limit: 5,
    });
  }

  if (!addresses || addresses.length === 0) return;

  const billing = addresses.find((a) => a.address_type === "Billing");
  const chosen = billing || addresses[0];

  await frm.set_value("customer_address", chosen.name);
  frm.refresh_field("customer_address");
  check_sales_tax_exemption(frm);

  frappe.show_alert({ message: __("Billing address set: {0}", [chosen.name]), indicator: "green" });
}

// ── SALES TAX EXEMPTION AWARENESS ──────────────────────────────────────
// Item Tax Template used at LCS to mark labor/services as tax-exempt.
// Kept as a constant here (same convention production used) rather than
// hardcoding a resulting tax template name -- Tax Rule still decides that.
const EXEMPT_ITEM_TAX_TEMPLATE = "Labor - Tax Exempt";

async function check_sales_tax_exemption(frm) {
  if (frm.doc.customer) {
    const cust = await frappe.db.get_value("Customer", frm.doc.customer, "tax_category");
    if (cust?.message?.tax_category === "Exempt") {
      if (!frm.doc.exempt_from_sales_tax) {
        await frm.set_value("exempt_from_sales_tax", 1);
        frappe.show_alert({ message: __("Exempt customer — flagged as tax exempt."), indicator: "blue" });
      }
      return;
    }
  }

  const items = frm.doc.items || [];
  if (!items.length) return;

  let allExempt = true;
  for (const item of items) {
    if (!item.item_code) {
      allExempt = false;
      break;
    }
    const itm = await frappe.db.get_value("Item", item.item_code, "taxes");
    const itemTaxes = itm?.message?.taxes || [];
    const isExempt = itemTaxes.some((t) => t.item_tax_template === EXEMPT_ITEM_TAX_TEMPLATE);
    if (!isExempt) {
      allExempt = false;
      break;
    }
  }

  if (allExempt && !frm.doc.exempt_from_sales_tax) {
    await frm.set_value("exempt_from_sales_tax", 1);
    frappe.show_alert({ message: __("All items exempt — flagged as tax exempt."), indicator: "blue" });
  }
}

// ── COMPANY DEFAULT ─────────────────────────────────────────────────────

function set_company(frm) {
  if (!frm.doc.company) {
    const company = frappe.defaults.get_default("company");
    if (company) frm.set_value("company", company);
  }
}

// ── CUSTOM PRINT DESCRIPTION ────────────────────────────────────────────
// Lets a user type a print-friendly description per Quotation Item without
// disturbing the item's normal description -- it writes into the same
// `description` field, so no schema change is needed.

frappe.ui.form.on("Quotation Item", {
  form_render: function (frm, cdt, cdn) {
    setTimeout(function () {
      const row = locals[cdt][cdn];
      $(".custom-print-desc-wrapper").remove();
      const $target = $(".grid-form-body");
      $target.prepend(`
        <div class="custom-print-desc-wrapper" style="padding: 15px; border-bottom: 1px solid #d1d8dd; margin-bottom: 10px;">
          <label style="font-size: 12px; color: #8D99A6;">Description</label>
          <textarea
            id="custom_print_desc_input"
            style="width: 100%; margin-top: 5px; padding: 8px; border: 1px solid #d1d8dd; border-radius: 4px; min-height: 100px; font-size: 13px;"
            placeholder="Enter description for print..."
          >${row.description || ""}</textarea>
        </div>
      `);
      $("#custom_print_desc_input").on("blur", function () {
        frappe.model.set_value(cdt, cdn, "description", $(this).val());
        frappe.show_alert("Description saved");
      });
    }, 500);
  },
});
