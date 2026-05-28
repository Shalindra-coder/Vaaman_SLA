


import frappe
from frappe.utils import now_datetime, get_datetime

def process_sla_rules():
    """Main function to check all active SLA rules for breaches."""
    # print("SLA checking started... ===============================")
    
    active_rules = frappe.get_all("SLA Rule", filters={"active": 1})

    for rule_ref in active_rules:
        rule = frappe.get_doc("SLA Rule", rule_ref.name)
        
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
            # 1. Total difference nikalne ke liye datetime objects ka use karein
            diff = now_datetime() - get_datetime(d.modified)
            total_seconds = diff.total_seconds()
            hours_elapsed = total_seconds / 3600
            
            # Check if breached
            if hours_elapsed >= rule.first_escalation_hours:
                total_secs = int(total_seconds)
                h = total_secs // 3600
                m = (total_secs % 3600) // 60
                hh_mm_format = f"{h}:{m:02d}"
                
                log_sla_breach(d, rule, hh_mm_format)

def log_sla_breach(doc, rule, formatted_time):
    """Records entries in SLA Breach Log"""
    
    log_name = frappe.db.exists("SLA Breach Log", {
        "doctype_name": rule.applies_to,
        "record_id": doc.name,
        "stage": rule.stage_value,
        "status": "Open"
    })

    if not log_name:
        log = frappe.new_doc("SLA Breach Log")
        log.doctype_name = rule.applies_to
        log.record_id = doc.name
        log.stage = rule.stage_value
        log.last_stage_change_on = doc.modified
        log.breached_on = now_datetime()
        log.status = "Open"
    else:
        log = frappe.get_doc("SLA Breach Log", log_name)

    log.hours_exceeded = formatted_time
    log.breached_by = doc.owner
    log.message = rule.message

    # Mapping child tables
    log.set("first_user_list", [])
    if rule.users:
        for u in rule.users:
            log.append("first_user_list", {"role": u.role})

    log.set("role_without_cost_center", [])
    if rule.role_without_cost_center:
        for r in rule.role_without_cost_center:
            log.append("role_without_cost_center", {"role": r.role})

    log.save(ignore_permissions=True)
    frappe.db.commit()