import frappe
from frappe.utils import now_datetime, time_diff_in_hours

def process_sla_rules():
    print("SLA checking started... ===============================")
    """Main function to check all active SLA rules for breaches."""
    
    # 1. Get all active SLA rules
    active_rules = frappe.get_all("SLA Rule", filters={"active": 1})

    for rule_ref in active_rules:
        rule = frappe.get_doc("SLA Rule", rule_ref.name)
        
        # 2. Prepare filters for target Doctype (e.g., Purchase Receipt)
        filters = {
            rule.stage_field: rule.stage_value,
            "docstatus": ["<", 2] 
        }
        
        # 3. Fetch documents matching the rule criteria
        target_docs = frappe.get_all(
            rule.applies_to, 
            filters=filters, 
            fields=["name", "modified", "owner"]
        )

        for d in target_docs:
            hours_elapsed = time_diff_in_hours(now_datetime(), d.modified)
            
            # 4. Check if First Escalation limit is breached
            if hours_elapsed >= rule.first_escalation_hours:
                log_sla_breach(d, rule, hours_elapsed)

def log_sla_breach(doc, rule, hours):
    """Creates or updates a breach log and maps users conditionally"""
    
    log_name = frappe.db.exists("SLA Breach Log", {
        "doctype_name": rule.applies_to,
        "record_id": doc.name,
        "stage": rule.stage_value
    })

    if not log_name:
        # CREATE NEW BREACH LOG
        log = frappe.new_doc("SLA Breach Log")
        log.doctype_name = rule.applies_to
        log.record_id = doc.name
        log.stage = rule.stage_value
        log.breached_by = doc.owner 
        log.last_stage_change_on = doc.modified
        log.breached_on = now_datetime()
        log.hours_exceeded = hours
        log.message = rule.message
        log.status = "Open"
    else:
        # UPDATE EXISTING LOG
        log = frappe.get_doc("SLA Breach Log", log_name)
        log.hours_exceeded = hours
        log.breached_by = doc.owner

    # --- FIRST ESCALATION USERS (Always map when breach happens) ---
    log.set("first_user_list", []) # Clear previous to avoid duplicates
    if rule.users:
        for u in rule.users:
            log.append("first_user_list", {
                "user_name": u.user_name 
            })

    # --- SECOND ESCALATION USERS (Map ONLY if second escalation hours is breached) ---
    if hours >= rule.second_escalation_hours:
        log.set("second_user_list", []) # Clear previous to avoid duplicates
        if rule.second_escalation_users:
            for u in rule.second_escalation_users:
                log.append("second_user_list", {
                    "user_name": u.user_name 
                })

    # Save the document
    log.save(ignore_permissions=True)
    frappe.db.commit()