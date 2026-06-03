



import frappe
from frappe.utils import (
    get_link_to_form,
    now_datetime,
    add_to_date,
    validate_email_address
)
from collections import defaultdict

def send_daily_sla_emails():

    # 1. Fetch breaches MODIFIED in the last 24 hours that are still 'Open'
    last_allowed_date = add_to_date(now_datetime(), hours=-24) 

    breaches = frappe.get_all(
        "SLA Breach Log",
        filters={
            "status": "Open",
            "modified": [">", last_allowed_date]
        },
        fields=["name", "doctype_name", "record_id", "stage", "hours_exceeded", "message"]
    )

    if not breaches:
        return


    # Map to store: { user_email: [list_of_authorized_logs] }
    user_final_report_map = defaultdict(list)

    # --- 2. DATA PROCESSING AND PERMISSION LOGIC ---
    for b in breaches:
        
        # Fetch cost center from the actual source record
        doc_cc = frappe.db.get_value(b.doctype_name, b.record_id, "cost_center")
        
        log_entry = {
            "name": b.name,
            "doctype_name": b.doctype_name,
            "record_id": b.record_id,
            "stage": b.stage,
            "hours_exceeded": b.hours_exceeded,
            "doc_cc": doc_cc or "N/A",
            "message": b.message or "No specific message provided."
        }

        # --- A. UNRESTRICTED USERS ---
        unrestricted_this_log = set()
        u_roles = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "role_without_cost_center"}, fields=["role"])
        for r in u_roles:
            users = frappe.get_all("Has Role", filters={"role": r.role, "parenttype": "User"}, fields=["parent as email"])
            for u in users: unrestricted_this_log.add(u.email)

        u_mails = frappe.get_all("Email ID", filters={"parent": b.name, "parentfield": "email_idwithout_cost_center"}, fields=["email_id"])
        for e in u_mails: unrestricted_this_log.add(e.email_id)

        for email in unrestricted_this_log:
            if validate_email_address(email, throw=False):
                user_final_report_map[email].append(log_entry)

        # --- B. RESTRICTED USERS ---
        r_candidates = set()
        roles_cc_data = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "first_user_list"}, fields=["role"])
        for r in roles_cc_data:
            users = frappe.get_all("Has Role", filters={"role": r.role, "parenttype": "User"}, fields=["parent as email"])
            for u in users: r_candidates.add(u.email)

        emails_cc_data = frappe.get_all("Email ID", filters={"parent": b.name, "parentfield": "email_id"}, fields=["email_id"])
        for e in emails_cc_data: r_candidates.add(e.email_id)

        for email in r_candidates:
            if email in unrestricted_this_log: continue 
            
            if validate_email_address(email, throw=False):
                user_perms = frappe.get_all("User Permission", filters={"user": email, "allow": "Cost Center"}, fields=["for_value"])
                allowed_ccs = {p.for_value for p in user_perms if p.for_value}

                if doc_cc and doc_cc in allowed_ccs:
                    user_final_report_map[email].append(log_entry)

    # --- 3. SEND CONSOLIDATED EMAILS ---
    if not user_final_report_map:
        return

    content_groups = defaultdict(list) 
    for email, logs in user_final_report_map.items():
        report_signature = tuple(sorted([l['name'] for l in logs]))
        content_groups[report_signature].append((email, logs))

    for signature, members in content_groups.items():
        emails_in_group = [m[0] for m in members]
        logs_to_send = members[0][1]
        
        if emails_in_group:
            content = render_email_template(logs_to_send)
            
            try:
                frappe.sendmail(
                    recipients=emails_in_group[0],
                    bcc=emails_in_group[1:],
                    subject=f"Urgent: SLA Breach Summary ({now_datetime().strftime('%Y-%m-%d')})",
                    content=content,
                    now=True 
                )
            except Exception as e:
                pass

def render_email_template(logs):
    """
    Highly Attractive Professional HTML Template
    """
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; padding: 20px;">
        <div style="max-width: 1100px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.1);">
            
            <!-- Header Section -->
            <div style="background: linear-gradient(90deg, #ff4d4f, #ff7875); color: white; padding: 30px; text-align: center;">
                <h2 style="margin:0; font-size: 26px; letter-spacing: 1px; font-weight: 700;">🚨 SLA BREACH NOTIFICATION</h2>
                <p style="margin: 8px 0 0; opacity: 0.9; font-size: 16px;">Consolidated Priority Action Report</p>
            </div>

            <!-- Body Content -->
            <div style="padding: 35px;">
                <p style="font-size: 17px; color: #1a202c; font-weight: 600;">Dear Team,</p>
                <p style="font-size: 15px; color: #4a5568; line-height: 1.6;">
                    This is a consolidated summary of <b>SLA breaches</b> associated with your profile. These records have exceeded their allowed timeframe and require <b>immediate intervention</b>.
                </p>
                
                <div style="margin: 30px 0; overflow-x: auto;">
                    <table style="width:100%; border-collapse: collapse; font-size:14px; border: 1px solid #e2e8f0;">
                        <thead>
                            <tr style="background-color:#1f2937; color:white; text-align: left;">
                                <th style="padding:15px; border:1px solid #374151;">Document Type</th>
                                <th style="padding:15px; border:1px solid #374151;">ID / Link</th>
                                <th style="padding:15px; border:1px solid #374151;">Cost Center</th>
                                <th style="padding:15px; border:1px solid #374151;">Stage</th>
                                <th style="padding:15px; border:1px solid #374151;">Delay (DD:HH)</th>
                                <th style="padding:15px; border:1px solid #374151;">Message</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    for i, l in enumerate(logs):
        link = get_link_to_form(l['doctype_name'], l['record_id'])
        row_color = "#f8fafc" if i % 2 == 0 else "#ffffff"

        # Delay Formatting (DD:HH)
        try:
            # Assumes format HH:MM:SS or float
            val = str(l['hours_exceeded']).split(':')[0]
            total_h = float(val)
            d = int(total_h // 24)
            h = int(total_h % 24)
            delay = f"{d:02}:{h:02}"
        except:
            delay = l['hours_exceeded']

        html += f"""
            <tr style="background-color:{row_color};">
                <td style="padding:14px; border:1px solid #e2e8f0; color: #2d3748;">{l['doctype_name']}</td>
                <td style="padding:14px; border:1px solid #e2e8f0; font-weight: bold; color: #2563eb;">{link}</td>
                <td style="padding:14px; border:1px solid #e2e8f0; color: #4a5568;">{l['doc_cc']}</td>
                <td style="padding:14px; border:1px solid #e2e8f0;">
                    <span style="background-color: #fef3c7; color: #92400e; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 12px;">
                        {l['stage']}
                    </span>
                </td>
                <td style="padding:14px; border:1px solid #e2e8f0; color:#dc2626; font-weight:bold; font-size: 15px;">{delay}</td>
                <td style="padding:14px; border:1px solid #e2e8f0; color: #718096; font-style: italic; font-size: 12px;">{l['message']}</td>
            </tr>
        """
    
    html += """
                        </tbody>
                    </table>
                </div>

                <!-- Action Box -->
                <div style="background-color: #fff5f5; border-left: 5px solid #ff4d4f; padding: 25px; margin-top: 30px; border-radius: 6px;">
                    <h4 style="margin: 0 0 12px 0; color: #c53030; font-size: 16px;">📌 Required Action:</h4>
                    <ul style="margin: 0; color: #4a5568; font-size: 14px; line-height: 1.7;">
                        <li>Click on the <b>Record ID</b> to investigate the cause of the breach.</li>
                        <li>Update the workflow stage or resolve the document to stop the breach timer.</li>
                        <li>Provide internal comments if the delay is due to external dependencies.</li>
                    </ul>
                </div>
            </div>

            <!-- Footer Section -->
            <div style="background-color: #f8fafc; padding: 25px; text-align: center; border-top: 1px solid #edf2f7;">
                <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                    This is an automated consolidated notification based on your permissions. Please do not reply.
                </p>
                <p style="margin: 6px 0 0; font-size: 13px; font-weight: bold; color: #475569;">
                    SLA Management System
                </p>
            </div>
        </div>
    </div>
    """
    return html