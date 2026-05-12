import frappe
from frappe.utils import now_datetime, time_diff_in_hours, get_link_to_form, add_hours

def process_sla_rules():
    """Main function to check all active SLA rules for breaches"""
    # Get all active SLA rules
    active_rules = frappe.get_all("SLA Rule", filters={"active": 1})

    for rule_ref in active_rules:
        rule = frappe.get_doc("SLA Rule", rule_ref.name)
        
        # Prepare filters for target Doctype
        filters = {
            rule.stage_field: rule.stage_value,
            "docstatus": ["<", 2] # Exclude cancelled docs
        }
        
        # If Cost Center check is enabled, add it to filters (if field exists in target)
        # Note: Logic assumes target doctype has 'cost_center' if checkbox is ticked
        
        # Fetch documents matching the stage
        target_docs = frappe.get_all(rule.applies_to, filters=filters, fields=["name", "modified", "owner"])

        for d in target_docs:
            hours_elapsed = time_diff_in_hours(now_datetime(), d.modified)
            
            # Check if breached (First Escalation)
            if hours_elapsed >= rule.first_escalation_hours:
                log_sla_breach(d, rule, hours_elapsed)

def log_sla_breach(doc, rule, hours):
    """Creates or updates a breach log and attaches users from rule"""
    log_name = frappe.db.exists("SLA Breach Log", {
        "doctype_name": rule.applies_to,
        "record_id": doc.name,
        "stage": rule.stage_value
    })

    if not log_name:
        # Create new Breach Log
        log = frappe.new_doc("SLA Breach Log")
        log.doctype_name = rule.applies_to
        log.record_id = doc.name
        log.stage = rule.stage_value
        log.last_stage_change_on = doc.modified
        log.breached_on = now_datetime()
        log.hours_exceeded = hours
        log.message = rule.message

        # Sync First Escalation Users (e.g., Sector Head, CCO)
        for u in rule.users:
            log.append("first_user_list", {"user": u.user})

        # Sync Second Escalation Users (e.g., Owner, Requester) if time > second_escalation_hours
        if hours >= rule.second_escalation_hours:
            for u in rule.second_escalation_users:
                log.append("second_user_list", {"user": u.user})

        log.insert(ignore_permissions=True)
    else:
        # Update existing log with latest hours
        frappe.db.set_value("SLA Breach Log", log_name, "hours_exceeded", hours)

