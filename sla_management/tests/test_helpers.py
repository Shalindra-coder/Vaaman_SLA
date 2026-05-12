# Copyright (c) 2024, SLA Management Team and contributors
# For license information, please see license.txt

"""
Helper functions for SLA Management tests
"""

import frappe
from frappe.utils import now_datetime, add_to_date


def map_sla_vertical_to_lead_vertical(sla_vertical):
	"""
	Map SLA Rule vertical values to Lead vertical values
	
	Args:
		sla_vertical: Vertical value from SLA Rule
	
	Returns:
		Lead vertical value
	"""
	mapping = {
		"Permanent Staffing": "Permanent",
		"Temporary Staffing": "Temporary",
		"Learning & Development": "L&D",
		"HR Consulting": "LLC",  # Assuming HR Consulting maps to LLC
		"Franchise": "Franchise",
		"Alliances/Partnerships": "LLC",  # Default mapping
		"POSH": "LLC",
		"Labour Law Advisory & Compliance": "LLC"
	}
	return mapping.get(sla_vertical, sla_vertical)


def create_test_lead(lead_name, status, vertical, naming_series="CRM-LEAD-.YYYY.-"):
	"""
	Helper function to create a test Lead with proper naming
	
	Args:
		lead_name: Name of the lead
		status: Lead status
		vertical: Vertical value
		naming_series: Naming series (default: CRM-LEAD-.YYYY.-)
	
	Returns:
		Lead document
	"""
	# Split lead_name into first_name and last_name
	# If lead_name contains space, split it; otherwise use as first_name
	name_parts = lead_name.split(" ", 1)
	first_name = name_parts[0]
	last_name = name_parts[1] if len(name_parts) > 1 else "Test"
	
	# Map SLA vertical to Lead vertical
	lead_vertical = map_sla_vertical_to_lead_vertical(vertical)
	
	lead = frappe.get_doc({
		"doctype": "Lead",
		"first_name": first_name,
		"last_name": last_name,
		"status": status,
		"vertical": lead_vertical,
		"naming_series": naming_series
	})
	
	# Generate name from naming series since Lead uses "prompt" autoname
	from frappe.utils import now_datetime
	import random
	
	# Generate a unique name
	year = str(now_datetime().year)
	counter = random.randint(10000, 99999)
	test_name = f"CRM-LEAD-{year}-{counter}"
	
	# Ensure name is unique
	while frappe.db.exists("Lead", test_name):
		counter = random.randint(10000, 99999)
		test_name = f"CRM-LEAD-{year}-{counter}"
	
	lead.name = test_name
	lead.insert()
	return lead


def create_test_opportunity(opportunity_name, stage, vertical):
	"""
	Helper function to create a test Opportunity
	
	Args:
		opportunity_name: Name of the opportunity
		stage: Opportunity stage
		vertical: Vertical value
	
	Returns:
		Opportunity document
	"""
	opportunity = frappe.get_doc({
		"doctype": "Opportunity",
		"opportunity_from": "Lead",
		"party_name": opportunity_name,
		"stage": stage,
		"vertical": vertical
	})
	opportunity.insert()
	return opportunity


def create_test_sla_rule(vertical, applies_to, stage_field, stage_value, max_hours, active=1):
	"""
	Helper function to create a test SLA Rule
	
	Args:
		vertical: Vertical value
		applies_to: Lead or Opportunity
		stage_field: status or stage
		stage_value: Stage value
		max_hours: Maximum hours allowed
		active: Whether rule is active (default: 1)
	
	Returns:
		SLA Rule document
	"""
	sla_rule = frappe.get_doc({
		"doctype": "SLA Rule",
		"vertical": vertical,
		"applies_to": applies_to,
		"stage_field": stage_field,
		"stage_value": stage_value,
		"max_hours_allowed": max_hours,
		"active": active
	})
	sla_rule.insert()
	return sla_rule


def set_lead_breach_condition(lead_name, hours_ago):
	"""
	Helper to set a lead's last_stage_change_on to create a breach condition
	
	Args:
		lead_name: Name of the lead
		hours_ago: Number of hours ago to set the timestamp
	"""
	breach_time = add_to_date(now_datetime(), hours=-hours_ago)
	frappe.db.set_value("Lead", lead_name, "last_stage_change_on", breach_time)
	frappe.db.commit()

