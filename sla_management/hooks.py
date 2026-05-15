
app_name = "sla_management"
app_title = "SLA Management"
app_publisher = "SLA Management Team"
app_description = "SLA Tracker & Escalation System for ERPNext (Lead + Opportunity)"
app_email = "crm-head@promptpersonnel.com"
app_license = "mit"

# Document Events
doc_events = {
	"Lead": {
		"before_save": "sla_management.utils.document_events.update_last_stage_change_on"
	},
	"Opportunity": {
		"before_save": "sla_management.utils.document_events.update_last_stage_change_on"
	}
}

# Scheduled Tasks
scheduler_events = {
	"hourly": [
		"sla_management.scripts.sla_checker.process_sla_rules"
	],
	"daily": [
		"sla_management.scripts.sla_daily_summary.send_daily_sla_emails"
	]
}

# Include JS files for doctype views

# Fixtures
