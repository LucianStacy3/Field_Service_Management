frappe.pages["zztest-tools"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ZZTEST Data Tools"),
		single_column: true,
	});

	new ZZTestTools(page);
};

class ZZTestTools {
	constructor(page) {
		this.page = page;
		this.$body = $(`
			<div class="zztest-tools" style="max-width: 760px;">
				<p class="text-muted">
					Loads or removes the ZZTEST sample data set used to walk the test plan
					(Customer, Contacts, Users/Employees, Service Technicians, Vehicles,
					Customer Equipment, sellable Items, a Service Agreement due today, and a
					starter Service Request). Remove Test Data only cleans up what was
					originally created; Force Cleanup also sweeps up anything you created
					manually while testing that links back to it. Only System Managers can
					run this.
				</p>
				<div class="zztest-status alert alert-info">Checking status...</div>
				<div class="zztest-buttons" style="margin-bottom: 15px;"></div>
				<pre class="zztest-log" style="background:#f5f5f5; padding:10px; min-height:120px; max-height:420px; overflow:auto; border-radius:4px;"></pre>
			</div>
		`).appendTo(page.body);

		this.$status = this.$body.find(".zztest-status");
		this.$buttons = this.$body.find(".zztest-buttons");
		this.$log = this.$body.find(".zztest-log");

		this.refresh_status();
	}

	call(method, confirm_message) {
		const run = () => {
			this.$log.text("Running...");
			frappe.call({
				method: `beveren_fsm.field_service_management.api.zztest_data.${method}`,
				freeze: true,
				freeze_message: __("Working..."),
				callback: (r) => {
					const data = r.message || {};
					this.$log.text((data.lines || []).join("\n"));
					this.refresh_status();
				},
				error: () => {
					this.$log.text("Request failed -- check the browser console and Error Log.");
				},
			});
		};

		if (confirm_message) {
			frappe.confirm(confirm_message, run);
		} else {
			run();
		}
	}

	refresh_status() {
		frappe.call({
			method: "beveren_fsm.field_service_management.api.zztest_data.get_status",
			callback: (r) => {
				const data = r.message || {};
				this.render_status(data);
				this.render_buttons(data);
			},
		});
	}

	render_status(data) {
		if (data.locked) {
			this.$status
				.removeClass("alert-info alert-success")
				.addClass("alert-warning")
				.html(
					`<strong>${__("Locked")}</strong> -- test data was fully removed and cannot be reloaded until you click Unlock below.<br>` +
						frappe.utils.escape_html(data.lock_note || "")
				);
		} else if (data.record_count > 0) {
			this.$status
				.removeClass("alert-info alert-warning")
				.addClass("alert-success")
				.html(`${__("Currently tracking")} <strong>${data.record_count}</strong> ${__("ZZTEST record(s)")}.`);
		} else {
			this.$status
				.removeClass("alert-warning alert-success")
				.addClass("alert-info")
				.html(__("No ZZTEST data currently loaded."));
		}
	}

	render_buttons(data) {
		this.$buttons.empty();

		$(`<button class="btn btn-primary btn-sm">${__("Load Test Data")}</button>`)
			.appendTo(this.$buttons)
			.prop("disabled", !!data.locked)
			.on("click", () => {
				this.call(
					"create_test_data",
					__("This will create ZZTEST-prefixed sample records on this site. Continue?")
				);
			});

		$(`<button class="btn btn-danger btn-sm" style="margin-left: 8px;">${__("Remove Test Data")}</button>`)
			.appendTo(this.$buttons)
			.prop("disabled", !data.record_count)
			.on("click", () => {
				this.call(
					"remove_test_data",
					__("This will permanently delete every ZZTEST record tracked on this site. Continue?")
				);
			});

		$(`<button class="btn btn-danger btn-sm" style="margin-left: 8px;">${__("Force Cleanup")}</button>`)
			.appendTo(this.$buttons)
			.prop("disabled", !data.record_count)
			.on("click", () => {
				this.call(
					"force_cleanup",
					__(
						"This goes further than Remove Test Data: it also finds and deletes any Quotations, " +
							"Service Orders, Appointments, Invoices, or other documents you created manually while " +
							"testing that reference the ZZTEST records -- not just the original 27. Documents that " +
							"are still linked to something outside the test data are left alone and reported. " +
							"This cannot be undone. Continue?"
					)
				);
			});

		if (data.locked) {
			$(`<button class="btn btn-default btn-sm" style="margin-left: 8px;">${__("Unlock")}</button>`)
				.appendTo(this.$buttons)
				.on("click", () => {
					this.call(
						"unlock",
						__("This deliberately re-enables loading test data on this site. Continue?")
					);
				});
		}
	}
}