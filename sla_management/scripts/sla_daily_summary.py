import frappe
from frappe.utils import get_link_to_form, now_datetime, add_to_date, validate_email_address

def send_daily_sla_emails():
    """Groups breaches from the last 24 hours by user roles and cost center permissions and sends consolidated emails."""
    print("SLA Daily Summary Email Job Started...")
    
    # 1. Calculate the timestamp for 24 hours ago
    last_24_hours = add_to_date(now_datetime(), hours=-24)
    
    # 2. Fetch all 'Open' SLA Breach Logs created within the last 24 hours
    breaches = frappe.get_all("SLA Breach Log", 
        filters={
            "status": "Open",
            "creation": [">", last_24_hours] 
        }, 
        fields=["name", "doctype_name", "record_id", "stage", "hours_exceeded"]
    )
    
    if not breaches:
        print("No new breaches found in the last 24 hours.")
        return

    # Map to store data: { "user_email": [list_of_breach_data] }
    user_report_map = {}

    for b in breaches:
        # Get the Cost Center from the source document (e.g., Purchase Receipt)
        doc_cost_center = frappe.db.get_value(b.doctype_name, b.record_id, "cost_center")
        
        # --- Logic 1: Process Roles WITHOUT Cost Center Restrictions ---
        # Fetch roles from the 'role_without_cost_center' child table
        no_cc_roles_data = frappe.get_all("CC Users", 
            filters={"parent": b.name, "parentfield": "role_without_cost_center"}, 
            fields=["role"]
        )
        no_cc_roles = [r.role for r in no_cc_roles_data if r.role]

        if no_cc_roles:
            # Find users assigned to these specific roles
            users_no_cc = frappe.get_all("Has Role", 
                filters={"role": ["in", no_cc_roles], "parenttype": "User"}, 
                fields=["parent as email"]
            )
            for u in users_no_cc:
                if validate_email_address(u.email, throw=False):
                    if u.email not in user_report_map:
                        user_report_map[u.email] = []
                    
                    # Add breach entry directly (No CC check required for these roles)
                    breach_entry = frappe._dict(b)
                    breach_entry.doc_cc = doc_cost_center or "N/A"
                    
                    # Prevent duplicate entries for the same user in one email
                    if breach_entry not in user_report_map[u.email]:
                        user_report_map[u.email].append(breach_entry)

        # --- Logic 2: Process Roles WITH Cost Center Restrictions ---
        # Fetch Roles from the 'first_user_list' child table
        cc_restricted_roles_data = frappe.get_all("CC Users", 
            filters={"parent": b.name, "parentfield": "first_user_list"}, 
            fields=["role"]
        )
        cc_roles = [r.role for r in cc_restricted_roles_data if r.role]

        if cc_roles:
            # Find users assigned to these roles
            users_with_cc_roles = frappe.get_all("Has Role", 
                filters={"role": ["in", cc_roles], "parenttype": "User"}, 
                fields=["parent as email"]
            )
            
            for u in users_with_cc_roles:
                email = u.email
                if not validate_email_address(email, throw=False):
                    continue

                # Check if this user was already processed in the 'No CC' logic to avoid duplicates
                if email in user_report_map and any(x.name == b.name for x in user_report_map[email]):
                    continue

                # Fetch User Permissions for 'Cost Center'
                user_permissions = frappe.get_all("User Permission",
                    filters={'user': email, 'allow': "Cost Center"},
                    fields=["for_value"]
                )
                allowed_ccs = [p.for_value for p in user_permissions]

                # Include if user has no CC restrictions OR document CC matches their allowed list
                if not allowed_ccs or (doc_cost_center in allowed_ccs):
                    if email not in user_report_map:
                        user_report_map[email] = []
                    
                    breach_entry = frappe._dict(b)
                    breach_entry.doc_cc = doc_cost_center or "N/A"
                    user_report_map[email].append(breach_entry)

    # 6. Send consolidated emails to each identified user
    sent_count = 0
    for user_email, logs in user_report_map.items():
        if not logs: 
            continue
        
        try:
            email_content = render_email_template(logs)
            
            # Send the email directly (now=True)
            frappe.sendmail(
                recipients=user_email,
                subject=f"Consolidated SLA Breach Summary - {now_datetime().strftime('%Y-%m-%d')}",
                content=email_content,
                now=True 
            )
            sent_count += 1
            print(f"Email successfully sent to: {user_email}")
        except Exception as e:
            print(f"Failed to send email to {user_email}: {str(e)}")
    
    print(f"SLA Job Completed. Total users notified: {sent_count}")

def render_email_template(logs):
    """Generates an HTML table containing all breaches for a specific user."""
    html = "<h4>The following records have breached SLA in the last 24 hours:</h4>"
    html += "<table border='1' style='border-collapse: collapse; width: 100%; font-size: 14px; border: 1px solid #ddd;'>"
    html += "<tr style='background-color: #f8f9fa;'><th>Type</th><th>ID</th><th>Cost Center</th><th>Stage</th><th>Delay (Hrs)</th></tr>"
    
    for l in logs:
        # Generate direct link to the record form
        link = get_link_to_form(l.doctype_name, l.record_id)
        html += f"<tr>"
        html += f"<td style='padding:8px;'>{l.doctype_name}</td>"
        html += f"<td style='padding:8px;'>{link}</td>"
        html += f"<td style='padding:8px;'>{l.doc_cc}</td>"
        html += f"<td style='padding:8px;'>{l.stage}</td>"
        html += f"<td style='padding:8px;'>{round(l.hours_exceeded, 2)}</td>"
        html += f"</tr>"
    
    html += "</table><p>Please review and process these pending records immediately.</p>"
    return html