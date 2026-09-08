frappe.pages["tax-table-importer"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tax Table Importer"),
		single_column: true,
	});

	new TaxTableImporter(page);
};

class TaxTableImporter {
	constructor(page) {
		this.page = page;
		this.$body = $(`
			<div class="tax-table-importer" style="max-width: 760px;">
				<p class="text-muted">
					Upload an Avalara-format "TAXRATES_ZIP5" CSV (the CA/AZ ZIP-code sales tax
					tables) to create or update the Sales Taxes and Charges Templates and Tax
					Rules that drive ZIP-based tax automation. Re-uploading a newer quarter's
					file updates existing rates in place instead of duplicating them. Only
					System Managers can run this.
				</p>
				<div class="tax-fields form-layout" style="margin-bottom: 12px;">
					<div class="frappe-control company-field" style="margin-bottom: 8px;"></div>
					<div class="frappe-control account-field" style="margin-bottom: 8px;"></div>
				</div>
				<div class="tax-buttons" style="margin-bottom: 15px;"></div>
				<div class="tax-progress" style="display:none; margin-bottom: 10px;">
					<div class="progress">
						<div class="progress-bar" role="progressbar" style="width: 0%;"></div>
					</div>
					<div class="progress-label text-muted small"></div>
				</div>
				<pre class="tax-log" style="background:#f5f5f5; padding:10px; min-height:120px; max-height:420px; overflow:auto; border-radius:4px;"></pre>
			</div>
		`).appendTo(page.body);

		this.$buttons = this.$body.find(".tax-buttons");
		this.$log = this.$body.find(".tax-log");
		this.$progressWrap = this.$body.find(".tax-progress");
		this.$progressBar = this.$body.find(".progress-bar");
		this.$progressLabel = this.$body.find(".progress-label");

		this.make_fields();
		this.make_buttons();
		this.bind_realtime();
	}

	make_fields() {
		this.company_field = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				options: "Company",
				fieldname: "company",
				label: __("Company"),
				default: frappe.defaults.get_default("company"),
			},
			parent: this.$body.find(".company-field"),
			render_input: true,
		});
		this.company_field.set_value(frappe.defaults.get_default("company"));

		this.account_field = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				options: "Account",
				fieldname: "tax_account",
				label: __("Tax Account (optional — auto-created if left blank)"),
			},
			parent: this.$body.find(".account-field"),
			render_input: true,
		});
	}

	make_buttons() {
		$(`<button class="btn btn-primary btn-sm">${__("Upload Tax Rate CSV")}</button>`)
			.appendTo(this.$buttons)
			.on("click", () => this.upload());

		$(`<button class="btn btn-danger btn-sm" style="margin-left: 8px;">${__("Remove Imported Tax Rules")}</button>`)
			.appendTo(this.$buttons)
			.on("click", () => this.remove());
	}

	upload() {
		new frappe.ui.FileUploader({
			restrictions: { allowed_file_types: [".csv"] },
			on_success: (file) => {
				this.$log.text("Uploaded " + file.file_name + ", queuing import...");
				this.$progressWrap.show();
				this.$progressBar.css("width", "0%");
				this.$progressLabel.text("");

				frappe.call({
					method: "beveren_fsm.field_service_management.api.tax_rate_import.import_tax_rates",
					args: {
						file_url: file.file_url,
						company: this.company_field.get_value(),
						tax_account: this.account_field.get_value() || undefined,
					},
					callback: () => {
						this.$log.text(this.$log.text() + "\nQueued. Progress will update below as it runs...");
					},
					error: () => {
						this.$log.text("Failed to queue the import -- check the browser console and Error Log.");
					},
				});
			},
		});
	}

	remove() {
		frappe.confirm(
			__("This will permanently delete every Tax Rule and Sales Taxes and Charges Template this importer created. Continue?"),
			() => {
				this.$log.text("Removing...");
				frappe.call({
					method: "beveren_fsm.field_service_management.api.tax_rate_import.remove_imported_tax_rules",
					args: { company: this.company_field.get_value() },
					freeze: true,
					freeze_message: __("Removing imported tax rules..."),
					callback: (r) => {
						const d = r.message || {};
						this.$log.text(
							`Removed ${d.templates_removed || 0} template(s) and ${d.rules_removed || 0} tax rule(s).`
						);
					},
					error: () => {
						this.$log.text("Request failed -- check the browser console and Error Log.");
					},
				});
			}
		);
	}

	bind_realtime() {
		frappe.realtime.on("lcs_tax_import_progress", (data) => {
			this.$progressWrap.show();
			const pct = data.total ? Math.round((data.processed / data.total) * 100) : 0;
			this.$progressBar.css("width", pct + "%");
			this.$progressLabel.text(
				`${data.file_name}: ${data.processed}/${data.total} ` +
					`(created ${data.created}, updated ${data.updated}, unchanged ${data.unchanged}, errors ${data.errors})`
			);
		});

		frappe.realtime.on("lcs_tax_import_done", (data) => {
			this.$progressWrap.hide();
			if (!data.ok) {
				this.$log.text("FAILED: " + data.message);
				return;
			}
			let lines = [
				`Done: ${data.file_name}`,
				`Total rows: ${data.total}`,
				`Unique rate templates: ${data.unique_templates}`,
				`Tax account used: ${data.tax_account}`,
				`Created: ${data.created}  Updated: ${data.updated}  Unchanged: ${data.unchanged}  Errors: ${data.errors}`,
			];
			if (data.error_samples && data.error_samples.length) {
				lines.push("", "Sample errors (see Error Log for full detail):");
				lines = lines.concat(data.error_samples);
			}
			this.$log.text(lines.join("\n"));
		});
	}
}
