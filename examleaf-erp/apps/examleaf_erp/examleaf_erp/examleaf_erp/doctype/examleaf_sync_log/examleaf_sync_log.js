frappe.ui.form.on("ExamLeaf Sync Log", {
	refresh(frm) {
		const can_resync = frappe.user.has_role(["EL Admin", "EL Finance", "System Manager"]);
		if (frm.doc.status !== "Error" || frm.doc.direction !== "Inbound" || !can_resync) return;
		frm.add_custom_button(__("Resync"), () =>
			frappe
				.call({
					method: "examleaf_erp.examleaf_erp.doctype.examleaf_sync_log.examleaf_sync_log.resync",
					args: { name: frm.doc.name },
					freeze: true,
				})
				.then((r) =>
					frappe.show_alert({ message: __("Queued again as {0}", [r.message]), indicator: "blue" })
				)
		);
	},
});
