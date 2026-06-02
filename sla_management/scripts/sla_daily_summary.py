import frappe
from frappe.utils import (
    get_link_to_form,
    now_datetime,
    add_to_date,
    validate_email_address
)
from collections import defaultdict

def send_daily_sla_emails():
    last_allowed_date = add_to_date(now_datetime(), hours=-24) 

    breaches = frappe.get_all(
        "SLA Breach Log",
        filters={
            "status": "Open",
            "creation": [">", last_allowed_date]
        },
        fields=["name", "doctype_name", "record_id", "stage", "hours_exceeded"]
    )

    if not breaches:
        return

    unrestricted_emails = set()
    restricted_user_map = {} # Format: { email: [list_of_logs] }
    all_breaches_list = []

    # --- 2. DATA COLLECTION AND PERMISSION LOGIC ---
    for b in breaches:
        # Fetch the cost center from the source document
        doc_cc = frappe.db.get_value(b.doctype_name, b.record_id, "cost_center")
        
        # Log object for the email template
        log_entry = {
            "doctype_name": b.doctype_name,
            "record_id": b.record_id,
            "stage": b.stage,
            "hours_exceeded": b.hours_exceeded,
            "doc_cc": doc_cc or "N/A"
        }
        all_breaches_list.append(log_entry)

        # A. Collect Unrestricted Users (Roles + Direct Emails)
        # These users will see all data without cost center restrictions
        u_roles = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "role_without_cost_center"}, fields=["role"])
        for r in u_roles:
            users = frappe.get_all("Has Role", filters={"role": r.role, "parenttype": "User"}, fields=["parent as email"])
            for u in users: unrestricted_emails.add(u.email)

        u_mails = frappe.get_all("Email ID", filters={"parent": b.name, "parentfield": "email_idwithout_cost_center"}, fields=["email_id"])
        for e in u_mails: unrestricted_emails.add(e.email_id)

        # B. Collect Restricted Users Candidates (With Cost Center Filter)
        r_candidates = set()
        roles_cc_data = frappe.get_all("CC Users", filters={"parent": b.name, "parentfield": "first_user_list"}, fields=["role"])
        for r in roles_cc_data:
            users = frappe.get_all("Has Role", filters={"role": r.role, "parenttype": "User"}, fields=["parent as email"])
            for u in users: r_candidates.add(u.email)

        emails_cc_data = frappe.get_all("Email ID", filters={"parent": b.name, "parentfield": "email_id"}, fields=["email_id"])
        for e in emails_cc_data: r_candidates.add(e.email_id)

        # Permission Check for Restricted Users
        for email in r_candidates:
            if email in unrestricted_emails: continue # Not needed here if already in unrestricted list
            if validate_email_address(email, throw=False):
                # Check Cost Center permissions from the User Permission table
                user_perms = frappe.get_all("User Permission", filters={"user": email, "allow": "Cost Center"}, fields=["for_value"])
                allowed_ccs = {p.for_value for p in user_perms if p.for_value}

                if doc_cc and doc_cc in allowed_ccs:
                    if email not in restricted_user_map: restricted_user_map[email] = []
                    restricted_user_map[email].append(log_entry)

    # --- 3. SEND EMAIL TO UNRESTRICTED GROUP (Group 1 - 1 Mail Only) ---
    if unrestricted_emails:
        valid_u_list = [e for e in unrestricted_emails if validate_email_address(e, throw=False)]
        if valid_u_list:
            content = render_email_template(all_breaches_list)
            frappe.sendmail(
                recipients=valid_u_list[0],
                bcc=valid_u_list[1:], # BCC used to reduce server hits
                subject=f"Urgent: SLA Breach Summary (Full Report) - {now_datetime().strftime('%Y-%m-%d')}",
                content=content,
                now=True
            )

    # --- 4. SEND EMAIL TO RESTRICTED GROUPS (Group 2 - Based on Data) ---
    # Group users who should see the exact same set of breaches
    content_groups = defaultdict(list)
    for email, logs in restricted_user_map.items():
        # Create a unique signature using Record IDs for grouping
        report_signature = tuple(sorted([l['record_id'] for l in logs]))
        content_groups[report_signature].append((email, logs))

    for signature, members in content_groups.items():
        emails_in_group = [m[0] for m in members]
        logs_to_send = members[0][1]
        
        if emails_in_group:
            content = render_email_template(logs_to_send)
            frappe.sendmail(
                recipients=emails_in_group[0],
                bcc=emails_in_group[1:],
                subject=f"Urgent: SLA Breach Summary (Restricted) - {now_datetime().strftime('%Y-%m-%d')}",
                content=content,
                now=True
            )

def render_email_template(logs):
    # Stylish HTML Template
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f9; padding: 20px;">
        <div style="max-width: 1000px; margin: auto; background: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            
            <!-- Header Section -->
            <div style="background: linear-gradient(90deg, #ff4d4f, #ff7875); color: white; padding: 25px; text-align: center;">
                <h2 style="margin:0; font-size: 24px; letter-spacing: 1px;">🚨 SLA BREACH NOTIFICATION</h2>
                <p style="margin: 5px 0 0; opacity: 0.9;">High Priority: Action Required</p>
            </div>

            <!-- Body Content -->
            <div style="padding: 30px;">
                <p style="font-size: 16px; color: #333;">Dear Team,</p>
                <p style="font-size: 15px; color: #555; line-height: 1.6;">
                    This is a consolidated summary of <b>SLA breaches</b> identified. Please review these entries and take <b>immediate action</b> to resolve the pending tasks.
                </p>
                
                <div style="margin: 25px 0;">
                    <table style="width:100%; border-collapse: collapse; font-size:14px; border: 1px solid #eee;">
                        <thead>
                            <tr style="background-color:#1f2937; color:white;">
                                <th style="padding:15px; border:1px solid #374151;">Document Type</th>
                                <th style="padding:15px; border:1px solid #374151;">Record ID</th>
                                <th style="padding:15px; border:1px solid #374151;">Cost Center</th>
                                <th style="padding:15px; border:1px solid #374151;">Stage</th>
                                <th style="padding:15px; border:1px solid #374151;">Delay (DD:HH)</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    for i, l in enumerate(logs):
        link = get_link_to_form(l['doctype_name'], l['record_id'])
        row_color = "#fcfcfc" if i % 2 == 0 else "#ffffff"

        # Delay Formatting
        try:
            total_h = float(str(l['hours_exceeded']).split(':')[0])
            d = int(total_h // 24)
            h = int(total_h % 24)
            delay = f"{d:02}:{h:02}"
        except:
            delay = l['hours_exceeded']

        html += f"""
            <tr style="background-color:{row_color};">
                <td style="padding:12px; border:1px solid #eee; color: #444;">{l['doctype_name']}</td>
                <td style="padding:12px; border:1px solid #eee; color: #2563eb;">{link}</td>
                <td style="padding:12px; border:1px solid #eee; color: #444;">{l['doc_cc']}</td>
                <td style="padding:12px; border:1px solid #eee; font-weight: 500; color: #854d0e;">{l['stage']}</td>
                <td style="padding:12px; border:1px solid #eee; color:#dc2626; font-weight:bold;">{delay}</td>
            </tr>
        """
    
    html += """
                        </tbody>
                    </table>
                </div>

                <!-- Action Box -->
                <div style="background-color: #fff5f5; border-left: 5px solid #ff4d4f; padding: 20px; margin-top: 30px; border-radius: 4px;">
                    <h4 style="margin: 0 0 10px 0; color: #c53030;">📌 Immediate Instruction:</h4>
                    <ul style="margin: 0; color: #4a5568; font-size: 14px; line-height: 1.6;">
                        <li>Check the reason for the delay by clicking on the Record ID.</li>
                        <li>Update the status or complete the pending stage immediately.</li>
                    </ul>
                </div>
            </div>

            <!-- Footer -->
            <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                <p style="margin: 0; font-size: 12px; color: #94a3b8;">This is an automated consolidated notification. Please do not reply to this email.</p>
                <p style="margin: 5px 0 0; font-size: 12px; font-weight: bold; color: #64748b;">ERP Notification System</p>
            </div>
        </div>
    </div>
    """
    return html