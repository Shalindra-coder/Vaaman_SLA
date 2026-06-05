






import frappe
from frappe.utils import now_datetime, get_datetime
from datetime import datetime, time, timedelta

def process_sla_rules():
    """Main function to check all active SLA rules for breaches."""
    active_rules = frappe.get_all("SLA Rule", filters={"active": 1})

    for rule_ref in active_rules:
        rule = frappe.get_doc("SLA Rule", rule_ref.name)
        
        is_today_weekend = now_datetime().weekday() >= 5
        if rule.applied_suterday_and_sunday and is_today_weekend:
            continue

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
            total_seconds = get_business_seconds(
                get_datetime(d.modified), 
                now_datetime(), 
                include_weekends = not rule.applied_suterday_and_sunday
            )
            
            hours_elapsed = total_seconds / 3600
            
            if hours_elapsed >= rule.first_escalation_hours:
                total_secs = int(total_seconds)
                h = total_secs // 3600
                m = (total_secs % 3600) // 60
                hh_mm_format = f"{h}:{m:02d}"
                
                log_sla_breach(d, rule, hh_mm_format)

def get_business_seconds(start_dt, end_dt, include_weekends=False):
    WORK_START_H = 10 
    WORK_END_H = 18    # 6 PM
    CUTOFF_H = 17    # 5 PM
    
    total_seconds = 0
    
    # If record modified at or after 5 PM, start counting from next day 10 AM
    if start_dt.time() >= time(CUTOFF_H, 0):
        current_dt = datetime.combine(start_dt.date() + timedelta(days=1), time(WORK_START_H, 0))
    else:
        current_dt = start_dt

    while current_dt.date() <= end_dt.date():
        is_weekend = current_dt.weekday() >= 5
        
        if include_weekends or not is_weekend:
            day_start = datetime.combine(current_dt.date(), time(WORK_START_H, 0))
            day_end = datetime.combine(current_dt.date(), time(WORK_END_H, 0))

            actual_start = max(current_dt, day_start)
            actual_end = min(end_dt, day_end)

            if actual_start < actual_end:
                total_seconds += (actual_end - actual_start).total_seconds()

        current_dt = datetime.combine(current_dt.date() + timedelta(days=1), time(WORK_START_H, 0))
        
    return total_seconds

def log_sla_breach(doc, rule, formatted_time):
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
    
    log.set("first_user_list", [{"role": u.role} for u in rule.get("users", [])])
    log.set("role_without_cost_center", [{"role": r.role} for r in rule.get("role_without_cost_center", [])])
    log.set("email_id", [{"email_id": e.email_id} for e in rule.get("email_id", [])])
    log.set("email_idwithout_cost_center", [{"email_id": e.email_id} for e in rule.get("email_idwithout_cost_centerf", [])])

    log.save(ignore_permissions=True)
    frappe.db.commit()