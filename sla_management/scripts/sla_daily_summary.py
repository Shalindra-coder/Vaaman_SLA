import frappe
from frappe.utils import get_link_to_form, now_datetime, add_to_date

def send_daily_sla_emails():
    """Groups breaches from the last 24 hours by user and sends a consolidated email"""
    print("SLA Daily Summary Email Job Started...")
    
    # Calculate the time 24 hours ago from now
    last_24_hours = add_to_date(now_datetime(), hours=-24)
    
    # 1. Fetch only Open SLA Breach Logs created within the last 24 hours
    breaches = frappe.get_all("SLA Breach Log", 
        filters={
            "status": "Open",
            "creation": [">", last_24_hours] 
        }, 
        fields=["*"]
    )
    
    user_report_map = {}

    for b in breaches:
        # Get the Cost Center from the original target document (e.g., Purchase Receipt)
        doc_cost_center = frappe.db.get_value(b.doctype_name, b.record_id, "cost_center")
        
        # Collect all users to be notified from both child tables
        notify_users = []
        
        # Fetch emails from First Escalation User List
        u1 = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "first_user_list"}, fields=["user_name"])
        notify_users += [x.user_name for x in u1]

        # Fetch emails from Second Escalation User List
        u2 = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "second_user_list"}, fields=["user_name"])
        notify_users += [x.user_name for x in u2]

        # Remove duplicate email addresses
        unique_emails = set(filter(None, notify_users))

        for email in unique_emails:
            # Check for User Permissions related to Cost Center
            user_permissions = frappe.get_all("User Permission",
                                              filters={'user': email, 'allow': "Cost Center"},
                                              fields=["for_value"])
            
            allowed_cost_centers = [p.for_value for p in user_permissions]

            # Logic:
            # If the user has no specific Cost Center permissions (Global User) OR the document's Cost Center matches their permission
            if not allowed_cost_centers or doc_cost_center in allowed_cost_centers:
                if email not in user_report_map:
                    user_report_map[email] = []
                
                # Attach Cost Center info to the log object for the email template
                b.doc_cc = doc_cost_center or "N/A"
                user_report_map[email].append(b)

    # 2. Send one consolidated email to each identified user
    for user_email, logs in user_report_map.items():
        if not logs: 
            continue
        
        email_content = render_email_template(logs)
        
        frappe.sendmail(
            recipients=[user_email],
            subject="Action Required: Daily SLA Breach Summary",
            message=email_content,
            now=True
        )
    
    print(f"SLA Daily Summary Email Job Completed. Users notified: {len(user_report_map)}")

def render_email_template(logs):
    """Generates an HTML table for the email content"""
    html = "<h4>The following records have breached SLA in the last 24 hours:</h4>"
    html += "<table border='1' style='border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;'>"
    html += "<tr style='background-color: #f2f2f2;'><th>Type</th><th>ID</th><th>Cost Center</th><th>Stage</th><th>Delay (Hrs)</th></tr>"
    
    for l in logs:
        # Create a direct link to the document form
        link = get_link_to_form(l.doctype_name, l.record_id)
        html += "<tr>"
        html += f"<td style='padding:5px;'>{l.doctype_name}</td>"
        html += f"<td style='padding:5px;'>{link}</td>"
        html += f"<td style='padding:5px;'>{l.doc_cc}</td>"
        html += f"<td style='padding:5px;'>{l.stage}</td>"
        html += f"<td style='padding:5px;'>{round(l.hours_exceeded, 1)}</td>"
        html += "</tr>"
    
    html += "</table><p>Please review and process these pending records immediately.</p>"
    return html