import frappe
from frappe.utils import now_datetime, time_diff_in_hours

def process_sla_rules():
    """Main function to check all active SLA rules for breaches."""
    print("SLA checking started... ===============================")
    
    # 1. Fetch all active SLA rules
    active_rules = frappe.get_all("SLA Rule", filters={"active": 1})

    for rule_ref in active_rules:
        # Fetch the complete document to access child tables like 'users' and 'role_without_cost_center'
        rule = frappe.get_doc("SLA Rule", rule_ref.name)
        
        # 2. Filter records of the target Doctype based on the rule configuration
        filters = {
            rule.stage_field: rule.stage_value,
            "docstatus": ["<", 2],
            "modified": [">=", "2026-04-01 00:00:00"] 

        }
        
        target_docs = frappe.get_all(
            rule.applies_to, 
            filters=filters, 
            fields=["name", "modified", "owner"]
        )

        for d in target_docs:
            # Calculate the hours elapsed since the last modification
            hours_elapsed = time_diff_in_hours(now_datetime(), d.modified)
            
            # 3. Check if the elapsed time exceeds the first escalation limit
            if hours_elapsed >= rule.first_escalation_hours:
                log_sla_breach(d, rule, hours_elapsed)

def log_sla_breach(doc, rule, hours):
    """Records entries in SLA Breach Log and maps roles from both child tables"""
    
    # Check if an 'Open' log already exists for this specific record and stage
    log_name = frappe.db.exists("SLA Breach Log", {
        "doctype_name": rule.applies_to,
        "record_id": doc.name,
        "stage": rule.stage_value,
        "status": "Open"
    })

    if not log_name:
        # Create a new Breach Log entry
        log = frappe.new_doc("SLA Breach Log")
        log.doctype_name = rule.applies_to
        log.record_id = doc.name
        log.stage = rule.stage_value
        log.last_stage_change_on = doc.modified
        log.breached_on = now_datetime()
        log.status = "Open"
    else:
        # Fetch the existing log to update it
        log = frappe.get_doc("SLA Breach Log", log_name)

    # Update general breach information
    log.hours_exceeded = hours
    log.breached_by = doc.owner
    log.message = rule.message

    # --- Mapping Role List (users -> first_user_list) ---
    log.set("first_user_list", []) # Clear existing entries
    if rule.users:
        for u in rule.users:
            log.append("first_user_list", {
                "role": u.role 
            })

    # --- Mapping Role Without Cost Center (role_without_cost_center -> role_without_cost_center) ---
    log.set("role_without_cost_center", []) # Clear existing entries
    if rule.role_without_cost_center:
        for r in rule.role_without_cost_center:
            log.append("role_without_cost_center", {
                "role": r.role 
            })

    # Save the document and commit to the database
    log.save(ignore_permissions=True)
    frappe.db.commit()