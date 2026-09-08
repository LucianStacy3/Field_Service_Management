frappe.ui.form.on("LCS Scale Model", {
  capacity_unit: function (frm) {
    frm.set_value("resolution_unit", frm.doc.capacity_unit || "");
  },

  onload: function (frm) {
    // Sync on load in case they differ
    if (frm.doc.capacity_unit && !frm.doc.resolution_unit) {
      frm.set_value("resolution_unit", frm.doc.capacity_unit);
    }
  },
});
