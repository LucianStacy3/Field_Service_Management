frappe.ui.form.on("LCS Customer Equipment", {
  onload: function (frm) {
    lcs_ceq_set_address_filter(frm);
    lcs_ceq_set_model_filter(frm);
    lcs_ceq_set_paired_filter(frm);
    lcs_ceq_set_base_model_filter(frm);
  },

  refresh: function (frm) {
    lcs_ceq_set_model_filter(frm);
    lcs_ceq_set_base_model_filter(frm);

    if (frm.doc.paired_component) {
      frm.add_custom_button(
        frm.doc.paired_component,
        function () {
          frappe.set_route(
            "Form",
            "LCS Customer Equipment",
            frm.doc.paired_component
          );
        },
        "Paired Record"
      );
    }
  },

  customer: function (frm) {
    frm.set_value("service_address", "");
    lcs_ceq_set_address_filter(frm);
  },

  manufacturer: function (frm) {
    frm.set_value("scale_model", "");
    lcs_ceq_set_model_filter(frm);
  },

  scale_model: function (frm) {
    if (frm.doc.equipment_type === "Unit" && frm.doc.scale_model) {
      frappe.db.get_doc("LCS Scale Model", frm.doc.scale_model).then((doc) => {
        const cu = doc.capacity_unit || "";
        frm.set_value("capacity", doc.capacity || "");
        frm.set_value("capacity_unit", cu);
        frm.set_value("resolution", doc.resolution || "");
        frm.set_value("resolution_unit", cu);
      });
    } else if (frm.doc.equipment_type === "Display") {
      frm.set_value("capacity", "");
      frm.set_value("capacity_unit", "");
      frm.set_value("resolution", "");
      frm.set_value("resolution_unit", "");
    }
  },

  // Mirror resolution_unit when capacity_unit changed manually on a Unit
  capacity_unit: function (frm) {
    if (frm.doc.equipment_type === "Unit") {
      frm.set_value("resolution_unit", frm.doc.capacity_unit || "");
    }
  },

  base_manufacturer: function (frm) {
    frm.set_value("base_scale_model", "");
    frm.set_value("base_capacity", "");
    frm.set_value("base_capacity_unit", "");
    frm.set_value("base_resolution", "");
    frm.set_value("base_resolution_unit", "");
    frm.set_value("capacity", "");
    frm.set_value("capacity_unit", "");
    frm.set_value("resolution", "");
    frm.set_value("resolution_unit", "");
    lcs_ceq_set_base_model_filter(frm);
  },

  base_scale_model: function (frm) {
    if (!frm.doc.base_scale_model) {
      frm.set_value("base_capacity", "");
      frm.set_value("base_capacity_unit", "");
      frm.set_value("base_resolution", "");
      frm.set_value("base_resolution_unit", "");
      frm.set_value("capacity", "");
      frm.set_value("capacity_unit", "");
      frm.set_value("resolution", "");
      frm.set_value("resolution_unit", "");
      return;
    }
    frappe.db
      .get_doc("LCS Scale Model", frm.doc.base_scale_model)
      .then((doc) => {
        const cu = doc.capacity_unit || "";
        frm.set_value("base_capacity", doc.capacity || "");
        frm.set_value("base_capacity_unit", cu);
        frm.set_value("base_resolution", doc.resolution || "");
        frm.set_value("base_resolution_unit", cu);
        frm.set_value("capacity", doc.capacity || "");
        frm.set_value("capacity_unit", cu);
        frm.set_value("resolution", doc.resolution || "");
        frm.set_value("resolution_unit", cu);
      });
  },

  // Mirror base_resolution_unit when base_capacity_unit changed manually
  base_capacity_unit: function (frm) {
    frm.set_value("base_resolution_unit", frm.doc.base_capacity_unit || "");
  },

  equipment_type: function (frm) {
    if (frm.doc.equipment_type === "Unit") {
      frm.set_value("paired_component", "");
    }
    if (frm.doc.equipment_type === "Display") {
      frm.set_value("capacity", "");
      frm.set_value("capacity_unit", "");
      frm.set_value("resolution", "");
      frm.set_value("resolution_unit", "");
    }
    lcs_ceq_set_paired_filter(frm);
  },
});

function lcs_ceq_set_address_filter(frm) {
  frm.set_query("service_address", function () {
    return {
      query: "frappe.contacts.doctype.address.address.address_query",
      filters: {
        link_doctype: "Customer",
        link_name: frm.doc.customer || "",
      },
    };
  });
}

function lcs_ceq_set_model_filter(frm) {
  frm.set_query("scale_model", function () {
    return {
      filters: {
        manufacturer: frm.doc.manufacturer || "",
      },
    };
  });
}

function lcs_ceq_set_base_model_filter(frm) {
  frm.set_query("base_scale_model", function () {
    return {
      filters: {
        manufacturer: frm.doc.base_manufacturer || "",
      },
    };
  });
}

function lcs_ceq_set_paired_filter(frm) {
  const complement = frm.doc.equipment_type === "Display" ? "Base" : "Display";
  frm.set_query("paired_component", function () {
    return {
      filters: {
        customer: frm.doc.customer || "",
        equipment_type: complement,
        name: ["!=", frm.doc.name || ""],
      },
    };
  });
}
