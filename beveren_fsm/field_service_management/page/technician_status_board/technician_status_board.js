frappe.pages["technician-status-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Technician Status Board"),
		single_column: true,
	});

	new TechnicianStatusBoard(page, wrapper);
};

const STATUS_BADGE_CLASS = {
	Onsite: "badge-onsite",
	Traveling: "badge-traveling",
	"Prepping Truck": "badge-traveling",
	"In Shop": "badge-traveling",
	Paused: "badge-paused",
	"On Lunch": "badge-lunch",
	"Off Duty": "badge-idle",
	"Not Started": "badge-idle",
};

const REFRESH_MS = 15000;

class TechnicianStatusBoard {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;

		page.set_secondary_action(__("Refresh"), () => this.load());

		this.$body = $(`
			<div class="technician-status-board">
				<style>
					.technician-status-board table { width: 100%; }
					.technician-status-board .status-badge {
						display: inline-block; padding: 2px 10px; border-radius: 10px;
						font-size: 12px; font-weight: 600; color: #fff;
					}
					.technician-status-board .badge-onsite { background: #2e8b57; }
					.technician-status-board .badge-traveling { background: #4a90d9; }
					.technician-status-board .badge-paused { background: #d9822b; }
					.technician-status-board .badge-lunch { background: #8e6fce; }
					.technician-status-board .badge-idle { background: #9aa0a6; }
					.technician-status-board .job-cell { color: #666; font-size: 12px; }
					.technician-status-board .since-cell { color: #999; font-size: 12px; white-space: nowrap; }
					.technician-status-board tr.idle-row { opacity: 0.55; }
				</style>
				<p class="text-muted">
					Live view of what each technician is doing right now. Updates
					automatically every 15 seconds -- reflects the last action a
					technician's device successfully synced, so a status can lag
					briefly behind reality if they're offline.
				</p>
				<div class="tsb-error alert alert-danger" style="display:none;"></div>
				<table class="table table-bordered">
					<thead>
						<tr>
							<th>Technician</th>
							<th>Status</th>
							<th>Job / Customer</th>
							<th>Since</th>
						</tr>
					</thead>
					<tbody class="tsb-rows">
						<tr><td colspan="4" class="text-muted">Loading...</td></tr>
					</tbody>
				</table>
			</div>
		`).appendTo(page.body);

		this.$rows = this.$body.find(".tsb-rows");
		this.$error = this.$body.find(".tsb-error");

		this.load();
		this.timer = setInterval(() => {
			// Guards against an orphaned interval still polling after the
			// user has navigated to a different Desk page -- Frappe pages
			// are singletons kept in the DOM, but this is a cheap, cheap
			// insurance against ever piling up background requests.
			if (!document.body.contains(this.wrapper)) {
				clearInterval(this.timer);
				return;
			}
			this.load();
		}, REFRESH_MS);
	}

	load() {
		frappe.call({
			method: "beveren_fsm.field_service_management.api.technician_status_board.get_technician_status_board",
			callback: (r) => {
				this.$error.hide();
				this.render(r.message || []);
			},
			error: () => {
				this.$error.text(__("Couldn't load technician status -- check the browser console and Error Log.")).show();
			},
		});
	}

	render(rows) {
		if (!rows.length) {
			this.$rows.html('<tr><td colspan="4" class="text-muted">No technicians found.</td></tr>');
			return;
		}

		this.$rows.html(rows.map((r) => this.row_html(r)).join(""));
	}

	row_html(r) {
		const badge_class = STATUS_BADGE_CLASS[r.status] || "badge-idle";
		const job_html = r.job
			? `<a href="/app/service-appointment/${encodeURIComponent(r.job)}">${frappe.utils.escape_html(r.customer_name || r.job)}</a>`
			: "";
		const since_html = r.since ? comment_when(r.since) : "";

		return `
			<tr class="${r.idle ? "idle-row" : ""}">
				<td>${frappe.utils.escape_html(r.full_name)}</td>
				<td><span class="status-badge ${badge_class}">${frappe.utils.escape_html(r.status)}</span></td>
				<td class="job-cell">${job_html}</td>
				<td class="since-cell">${since_html}</td>
			</tr>
		`;
	}
}
