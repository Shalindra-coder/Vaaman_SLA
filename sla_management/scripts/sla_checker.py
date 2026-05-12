
# Copyright (c) 2024
# SLA Management App - Final Logic with Correct Field Names

import frappe
from frappe.utils import now_datetime, get_datetime, time_diff_in_hours

def get_hierarchy_records(employee_email, vertical):
    """ CRM Reporting Hierarchy se manager nikaalta hai """
    if not employee_email: return []
    return frappe.get_all(
        "CRM Reporting Hierarchy",
        filters={
            "email": employee_email.strip(),
            "department": vertical.strip()
        },
        fields=["reporting_manager_email", "department"]
    )

def send_sla_notification(user, doctype, docname, stage, hours_spent, hours_exceeded):
    """ Notification Log entry """
    days_exceeded = hours_exceeded / 24.0
    try:
        noti = frappe.new_doc("Notification Log")
        noti.for_user = user
        noti.type = "Alert"
        noti.document_type = doctype
        noti.document_name = docname
        noti.subject = f"SLA Breach: {docname}"
        noti.email_content = f"Record '{docname}' stuck in '{stage}' for {hours_spent:.1f} hrs."
        noti.insert(ignore_permissions=True)
    except Exception as e:
        frappe.logger().error(f"SLA Notification failed: {e}")

def create_breach_log(rule, doc, log_stage, current_time, sla_start, hours_exceeded):
    """ SLA Breach Log create karta hai with Correct Field Names from First Code """
    hierarchy_list = get_hierarchy_records(doc.owner, doc.custom_vertical)

    if not hierarchy_list:
        hierarchy_list = [{"reporting_manager_email": "", "department": doc.custom_vertical}]

    created = False
    for entry in hierarchy_list:
        mgr_email = entry.get("reporting_manager_email") or ""
        dept = entry.get("department") or doc.custom_vertical

        # Duplicate Check (Fields from First Code)
        if frappe.db.exists("SLA Breach Log", {
            "record_id": doc.name,
            "stage": log_stage,
            "vertical": dept,
            "reporting_manager_email": mgr_email
        }):
            continue

        log = frappe.get_doc({
            "doctype": "SLA Breach Log",
            "vertical": dept,
            "doctype_name": doc.doctype,
            "record_id": doc.name,
            "breached_by": doc.owner,
            "stage": log_stage,
            "hours_exceeded": hours_exceeded / 24.0, # Days logic
            "last_stage_change_on": sla_start,
            "breached_on": current_time,
            "reporting_manager_email": mgr_email,
            "message": rule.message # Message from Rule
        })
        log.insert(ignore_permissions=True)
        created = True
    
    if created: frappe.db.commit()
    return created

def sla_checker():
    print("SLA Checker Execution Started...")
    frappe.logger().info("Starting SLA Checker...")
    
    rules = frappe.get_all("SLA Rule", filters={"active": 1}, fields=["*"])
    now_time = now_datetime()
    total_logs = 0

    for rule in rules:
        max_hrs = rule.max_hours_allowed
        r_stage = rule.stage_value or "" # Handle NoneType
        
        # LEAD SECTION
        if rule.applies_to == "Lead":
            
            # --- RULE 1: SEPARATE - ONLY FOR "NEW" STATUS ---
            if r_stage == "New":
                leads = frappe.get_all("Lead", 
                    filters={"custom_vertical": rule.vertical, "status": "New"}, 
                    fields=["name", "owner", "creation", "status", "custom_vertical"])
                
                for lead in leads:
                    sla_start = get_datetime(lead.creation)
                    hrs_spent = time_diff_in_hours(now_time, sla_start)
                    if hrs_spent > max_hrs:
                        if create_breach_log(rule, lead, "New", now_time, sla_start, hrs_spent - max_hrs):
                            send_sla_notification(lead.owner, "Lead", lead.name, "New", hrs_spent, hrs_spent - max_hrs)
                            total_logs += 1

            # --- RULE 2: LEAD CONVERTED BUT NO OPPORTUNITY CREATED ---
            elif r_stage == "Converted":
                leads = frappe.get_all("Lead", 
                    filters={"custom_vertical": rule.vertical, "status": "Converted"}, 
                    fields=["name", "owner", "modified", "status", "custom_vertical"])
                
                for lead in leads:
                    # Correct Linking Logic from First Code
                    opp = frappe.db.get_value(
                        "Opportunity",
                        {"opportunity_from": "Lead", "party_name": lead.name},
                        ["name", "creation"],
                        as_dict=True
                    )
                    
                    sla_start = get_datetime(lead.modified) # Time of conversion
                    calc_end = get_datetime(opp.creation) if opp else now_time
                    hrs_spent = time_diff_in_hours(calc_end, sla_start)
                    
                    if hrs_spent > max_hrs:
                        if create_breach_log(rule, lead, "Converted", now_time, sla_start, hrs_spent - max_hrs):
                            send_sla_notification(lead.owner, "Lead", lead.name, "Converted (Missing Opp)", hrs_spent, hrs_spent - max_hrs)
                            total_logs += 1

            # --- RULE 3 & 4: MULTIPLE STATUS (Working, Nurturing) ---
            elif "Working" in r_stage or "Nurturing" in r_stage:
                allowed_statuses = [s.strip() for s in r_stage.split(',') if s.strip()]
                
                leads = frappe.get_all("Lead", 
                    filters={
                        "custom_vertical": rule.vertical, 
                        "status": ["in", allowed_statuses]
                    }, 
                    fields=["name", "owner", "creation", "status", "custom_vertical"])
                
                for lead in leads:
                    sla_start = get_datetime(lead.creation) # Creation se check
                    hrs_spent = time_diff_in_hours(now_time, sla_start)
                    if hrs_spent > max_hrs:
                        if create_breach_log(rule, lead, lead.status, now_time, sla_start, hrs_spent - max_hrs):
                            send_sla_notification(lead.owner, "Lead", lead.name, lead.status, hrs_spent, hrs_spent - max_hrs)
                            total_logs += 1

        # OPPORTUNITY SECTION
        elif rule.applies_to == "Opportunity":
            # Agreement ya jo bhi stage rule mein define ho
            opps = frappe.get_all("Opportunity", 
                filters={"custom_vertical": rule.vertical, "status": r_stage}, 
                fields=["name", "owner", "modified", "status", "custom_vertical"])
            
            for opp in opps:
                # Opportunity mein hamesha 'modified' se check hota hai (Stage Change Point)
                sla_start = get_datetime(opp.modified)
                hrs_spent = time_diff_in_hours(now_time, sla_start)
                
                if hrs_spent > max_hrs:
                    if create_breach_log(rule, opp, r_stage, now_time, sla_start, hrs_spent - max_hrs):
                        send_sla_notification(opp.owner, "Opportunity", opp.name, r_stage, hrs_spent, hrs_spent - max_hrs)
                        total_logs += 1

    frappe.logger().info(f"SLA Checker Completed. Total Logs: {total_logs}")
    return total_logs