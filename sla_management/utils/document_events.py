# Copyright (c) 2024, SLA Management Team and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def update_last_stage_change_on(doc, method=None):
	"""
	Update last_stage_change_on when stage/status changes.
	Works for both Lead and Opportunity.
	"""
	if doc.get("__islocal"):
		# New document - set initial timestamp
		doc.last_stage_change_on = now_datetime()
	else:
		# Existing document - check if stage changed
		# For Lead, check 'status' field
		# For Opportunity, check 'stage' field
		stage_field = "status" if doc.doctype == "Lead" else "stage"
		
		if doc.has_value_changed(stage_field):
			doc.last_stage_change_on = now_datetime()



