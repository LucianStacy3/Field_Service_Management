// LCS Service Agreement Quote — Client Script v2
// beveren_fsm / Field Service Management
// Equipment entered fresh (no existing equipment link).
// Per-row unit price is auto-suggested from scale type + difficulty; fully editable.
// Extended price = unit_price × qty.  Price per service = sum of extended prices.
// Annual total = price per service × visits per year.

frappe.ui.form.on("LCS Service Agreement Quote", {
  refresh(frm) {
    lcs_saq_status_indicator(frm);
    lcs_saq_action_buttons(frm);
  },

  schedule_type(frm) {
    if (frm.doc.schedule_type === "Interval") {
      frm.set_value("interval_months", frm.doc.interval_months || 12);
    }
    lcs_saq_recalc_totals(frm);
  },

  interval_months: lcs_saq_recalc_totals,
});

// ── Child table events ─────────────────────────────────────────────────────

frappe.ui.form.on("LCS Service Agreement Quote Item", {
  // When scale_type or difficulty changes, fetch a suggested price
  scale_type(frm, cdt, cdn) {
    lcs_saq_suggest_price(frm, cdt, cdn);
  },

  difficulty(frm, cdt, cdn) {
    lcs_saq_suggest_price(frm, cdt, cdn);
  },

  // Recalc extended price when unit_price or qty changes
  unit_price(frm, cdt, cdn) {
    lcs_saq_recalc_row(frm, cdt, cdn);
  },

  quantity(frm, cdt, cdn) {
    lcs_saq_recalc_row(frm, cdt, cdn);
  },

  equipment_items_remove(frm) {
    lcs_saq_recalc_totals(frm);
  },
});

// ── Row-level helpers ──────────────────────────────────────────────────────

function lcs_saq_suggest_price(frm, cdt, cdn) {
  const row = locals[cdt][cdn];
  if (!row.scale_type || !row.difficulty) return;

  // Only auto-fill if the user hasn't already typed a price,
  // OR if scale_type just changed (treat as a reset).
  frappe.call({
    method:
      "beveren_fsm.field_service_management.doctype" +
      ".lcs_service_agreement_quote.lcs_service_agreement_quote" +
      ".get_suggested_price",
    args: {
      scale_type: row.scale_type,
      difficulty: row.difficulty,
    },
    callback(r) {
      if (r.message && r.message.price >= 0) {
        const suggested = r.message.price;
        frappe.model.set_value(cdt, cdn, "unit_price", suggested);
        lcs_saq_recalc_row(frm, cdt, cdn);

        if (suggested === 0) {
          frappe.show_alert(
            {
              message:
                "No default price for this scale type — enter price manually.",
              indicator: "orange",
            },
            5
          );
        }
      }
    },
  });
}

function lcs_saq_recalc_row(frm, cdt, cdn) {
  const row = locals[cdt][cdn];
  const qty = parseFloat(row.quantity || 1);
  const price = parseFloat(row.unit_price || 0);
  frappe.model.set_value(
    cdt,
    cdn,
    "extended_price",
    Math.round(price * qty * 100) / 100
  );
  frm.refresh_field("equipment_items");
  lcs_saq_recalc_totals(frm);
}

// ── Form-level total recalc ────────────────────────────────────────────────

function lcs_saq_recalc_totals(frm) {
  const rows = frm.doc.equipment_items || [];
  const per_service = rows.reduce(
    (sum, r) => sum + (parseFloat(r.extended_price) || 0),
    0
  );

  let visits = 0;
  if (frm.doc.schedule_type === "Interval" && frm.doc.interval_months > 0) {
    visits = 12 / frm.doc.interval_months;
  }

  frm.set_value("price_per_service", Math.round(per_service * 100) / 100);
  frm.set_value("visits_per_year", Math.round(visits * 100) / 100);
  frm.set_value("annual_total", Math.round(per_service * visits * 100) / 100);
}

// ── Status indicator & action buttons ─────────────────────────────────────

function lcs_saq_status_indicator(frm) {
  const colors = {
    Draft: "gray",
    Sent: "blue",
    Accepted: "green",
    Declined: "red",
    Converted: "purple",
  };
  frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || "gray");
}

function lcs_saq_action_buttons(frm) {
  if (frm.is_new()) return;

  if (frm.doc.status === "Draft") {
    frm.add_custom_button(
      "Mark as Sent",
      () => {
        frappe.confirm("Mark this quote as sent to the customer?", () => {
          frm.set_value("status", "Sent");
          frm.save();
        });
      },
      "Actions"
    );
  }

  if (frm.doc.status === "Sent") {
    frm.add_custom_button(
      "Accept",
      () => {
        frappe.confirm("Mark as Accepted?", () => {
          frm.set_value("status", "Accepted");
          frm.save();
        });
      },
      "Actions"
    );

    frm.add_custom_button(
      "Decline",
      () => {
        frappe.confirm("Mark as Declined?", () => {
          frm.set_value("status", "Declined");
          frm.save();
        });
      },
      "Actions"
    );
  }

  if (frm.doc.status === "Accepted" && !frm.doc.linked_service_agreement) {
    frm.add_custom_button(
      "Convert to Service Agreement",
      () => {
        frappe.confirm(
          "Create a new LCS Service Agreement from this quote?",
          () =>
            frappe.call({
              method:
                "beveren_fsm.field_service_management.doctype" +
                ".lcs_service_agreement_quote.lcs_service_agreement_quote" +
                ".LCSServiceAgreementQuote.convert_to_service_agreement",
              doc: frm.doc,
              callback(r) {
                if (r.message) frm.reload_doc();
              },
            })
        );
      },
      "Actions"
    );
  }

  if (frm.doc.linked_service_agreement) {
    frm.add_custom_button("View Service Agreement", () => {
      frappe.set_route(
        "Form",
        "LCS Service Agreement",
        frm.doc.linked_service_agreement
      );
    });
  }
}
