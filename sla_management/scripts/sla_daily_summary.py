



import frappe
from frappe.utils import (
    get_link_to_form,
    now_datetime,
    add_to_date,
    validate_email_address
)
from collections import defaultdict

def send_daily_sla_emails():
    """
    Sends consolidated SLA breach report to enabled users.
    Grouping: By Document Type with Counts.
    """

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

    user_final_report_map = defaultdict(list)

    # --- Helper: Check if User is Enabled ---
    def is_user_active(email):
        if not email: return False
        return frappe.db.get_value("User", email, "enabled") == 1

    # --- 2. DATA PROCESSING AND PERMISSION LOGIC ---
    for b in breaches:
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
            if validate_email_address(email, throw=False) and is_user_active(email):
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
            
            if validate_email_address(email, throw=False) and is_user_active(email):
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
            except Exception:
                pass

def render_email_template(logs):
    """
    Highly Attractive Professional HTML Template Grouped by Doctype.
    """
    grouped_data = defaultdict(list)
    for l in logs:
        grouped_data[l['doctype_name']].append(l)

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
                    This is a consolidated summary of <b>SLA breaches</b> associated with your profile. These records require <b>immediate intervention</b>.
                </p>
    """

    for doctype, doc_logs in grouped_data.items():
        html += f"""
                <div style="margin-top: 40px; margin-bottom: 10px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">
                    <span style="font-size: 18px; font-weight: 700; color: #2d3748;">📂 {doctype}</span>
                    <span style="background-color: #fee2e2; color: #b91c1c; padding: 2px 10px; border-radius: 20px; font-size: 13px; font-weight: bold; margin-left: 10px;">
                        {len(doc_logs)} Breaches
                    </span>
                </div>
                
                <div style="margin-bottom: 30px; overflow-x: auto;">
                    <table style="width:100%; border-collapse: collapse; font-size:13px; border: 1px solid #e2e8f0;">
                        <thead>
                            <tr style="background-color:#1f2937; color:white; text-align: left;">
                                <th style="padding:12px; border:1px solid #374151;">ID / Link</th>
                                <th style="padding:12px; border:1px solid #374151;">Cost Center</th>
                                <th style="padding:12px; border:1px solid #374151;">Stage</th>
                                <th style="padding:12px; border:1px solid #374151;">Delay</th>
                                <th style="padding:12px; border:1px solid #374151;">Message</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        for i, l in enumerate(doc_logs):
            link = get_link_to_form(l['doctype_name'], l['record_id'])
            
            # Delay Formatting (8-hour day logic with "Days Hours" format)
            try:
                time_parts = str(l['hours_exceeded']).split(':')
                total_h = int(time_parts[0])
                d = int(total_h // 8) # Day calculated as 8 hours
                h = int(total_h % 8)
                delay = f"{d} Days {h} Hours"
            except:
                delay = l['hours_exceeded']

            html += f"""
                <tr style="background-color:{'#f8fafc' if i%2==0 else '#ffffff'};">
                    <td style="padding:12px; border:1px solid #e2e8f0; font-weight: bold; color: #2563eb;">{link}</td>
                    <td style="padding:12px; border:1px solid #e2e8f0; color: #4a5568;">{l['doc_cc']}</td>
                    <td style="padding:12px; border:1px solid #e2e8f0;">
                        <span style="background-color: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 11px;">
                            {l['stage']}
                        </span>
                    </td>
                    <td style="padding:12px; border:1px solid #e2e8f0; color:#dc2626; font-weight:bold; white-space: nowrap;">{delay}</td>
                    <td style="padding:12px; border:1px solid #e2e8f0; color: #718096; font-style: italic;">{l['message']}</td>
                </tr>
            """
        html += "</tbody></table></div>"

    html += """
                <!-- Action Box -->
                <div style="background-color: #fff5f5; border-left: 5px solid #ff4d4f; padding: 25px; margin-top: 30px; border-radius: 6px;">
                    <h4 style="margin: 0 0 12px 0; color: #c53030; font-size: 16px;">📌 Required Action:</h4>
                    <ul style="margin: 0; color: #4a5568; font-size: 14px; line-height: 1.7;">
                        <li>Click on the <b>Record ID</b> to investigate the cause of the breach.</li>
                        <li>Update the workflow stage or resolve the document to stop the breach timer.</li>
                    </ul>
                </div>
            </div>

            <!-- Footer Section -->
            <div style="background-color: #f8fafc; padding: 25px; text-align: center; border-top: 1px solid #edf2f7;">
                <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                    This is an automated consolidated notification. Please do not reply.
                </p>
            </div>
        </div>
    </div>
    """
    return html