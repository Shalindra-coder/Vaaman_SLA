
import frappe
from frappe.utils import get_link_to_form



def send_daily_sla_emails():
    """Groups breaches by user and sends a single consolidated email at 9 AM"""
    # Fetch all logs created/updated recently
    breaches = frappe.get_all("SLA Breach Log", fields=["*"])
    user_report_map = {}

    for b in breaches:
        # Combine both user lists to find who to notify
        notify_users = []
        notify_users += frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "first_user_list"}, fields=["user"])
        
        if b.hours_exceeded >= 72: # Logic for 72hr CC escalation
            notify_users += frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "second_user_list"}, fields=["user"])

        for u in notify_users:
            if u.user not in user_report_map:
                user_report_map[u.user] = []
            user_report_map[u.user].append(b)

    # Send one mail per user
    for user_email, logs in user_report_map.items():
        if not user_email: continue
        
        email_content = render_email_template(logs)
        frappe.send_mail(
            recipients=[user_email],
            subject="Action Required: Consolidated SLA Breach Report",
            message=email_content
        )

def render_email_template(logs):
    """Generates HTML table for the email"""
    html = "<h4>The following requests are pending beyond SLA limits:</h4>"
    html += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
    html += "<tr><th>Type</th><th>ID</th><th>Stage</th><th>Delay (Hrs)</th></tr>"
    
    for l in logs:
        link = get_link_to_form(l.doctype_name, l.record_id)
        html += f"<tr><td>{l.doctype_name}</td><td>{link}</td><td>{l.stage}</td><td>{round(l.hours_exceeded, 1)}</td></tr>"
    
    html += "</table><p>Please clear these pending tasks immediately.</p>"
    return html