import frappe
from frappe.utils import (
    get_link_to_form,
    now_datetime,
    add_to_date,
    validate_email_address
)


def send_daily_sla_emails():

    # LAST 24 HOURS
    last_24_hours = add_to_date(now_datetime(), hours=-24)

    breaches = frappe.get_all(
        "SLA Breach Log",
        filters={
            "status": "Open",
            "creation": [">", last_24_hours]
        },
        fields=[
            "name",
            "doctype_name",
            "record_id",
            "stage",
            "hours_exceeded"
        ]
    )

    if not breaches:
        print("No new breaches found in the last 24 hours.")
        return

    user_report_map = {}

    for b in breaches:

        # DOCUMENT COST CENTER
        doc_cost_center = frappe.db.get_value(
            b.doctype_name,
            b.record_id,
            "cost_center"
        )

        # 1. ROLE WITHOUT COST CENTER RESTRICTION

        no_cc_roles_data = frappe.get_all(
            "CC Users",
            filters={
                "parent": b.name,
                "parentfield": "role_without_cost_center"
            },
            fields=["role"]
        )

        no_cc_roles = [r.role for r in no_cc_roles_data if r.role]

        if no_cc_roles:

            users = frappe.get_all(
                "Has Role",
                filters={
                    "role": ["in", no_cc_roles],
                    "parenttype": "User"
                },
                fields=["parent as email"]
            )

            for u in users:

                email = u.email

                if not validate_email_address(email, throw=False):
                    continue

                if email not in user_report_map:
                    user_report_map[email] = []

                user_report_map[email].append(
                    frappe._dict({
                        "doctype_name": b.doctype_name,
                        "record_id": b.record_id,
                        "stage": b.stage,
                        "hours_exceeded": b.hours_exceeded,
                        "doc_cc": doc_cost_center or "N/A"
                    })
                )

        # 2. ROLE WITH COST CENTER RESTRICTION

        cc_roles_data = frappe.get_all(
            "CC Users",
            filters={
                "parent": b.name,
                "parentfield": "first_user_list"
            },
            fields=["role"]
        )

        cc_roles = [r.role for r in cc_roles_data if r.role]

        if cc_roles:

            users = frappe.get_all(
                "Has Role",
                filters={
                    "role": ["in", cc_roles],
                    "parenttype": "User"
                },
                fields=["parent as email"]
            )

            for u in users:

                email = u.email

                if not validate_email_address(email, throw=False):
                    continue

                # USER COST CENTER PERMISSIONS
                user_permissions = frappe.get_all(
                    "User Permission",
                    filters={
                        "user": email,
                        "allow": "Cost Center"
                    },
                    fields=["for_value"]
                )

                allowed_ccs = {
                    p.for_value
                    for p in user_permissions
                    if p.for_value
                }

                # STRICT MATCH ONLY
                if doc_cost_center and doc_cost_center in allowed_ccs:

                    if email not in user_report_map:
                        user_report_map[email] = []

                    user_report_map[email].append(
                        frappe._dict({
                            "doctype_name": b.doctype_name,
                            "record_id": b.record_id,
                            "stage": b.stage,
                            "hours_exceeded": b.hours_exceeded,
                            "doc_cc": doc_cost_center
                        })
                    )

        # --- CHANGE START: EMAIL ID WITH COST CENTER RESTRICTION ---
        email_with_cc_data = frappe.get_all(
            "Email ID",
            filters={
                "parent": b.name,
                "parentfield": "email_id"
            },
            fields=["email_id"]
        )

        for e in email_with_cc_data:
            email = e.email_id
            if not validate_email_address(email, throw=False):
                continue

            # Check Cost Center Permission
            user_permissions = frappe.get_all(
                "User Permission",
                filters={"user": email, "allow": "Cost Center"},
                fields=["for_value"]
            )
            allowed_ccs = {p.for_value for p in user_permissions if p.for_value}

            if doc_cost_center and doc_cost_center in allowed_ccs:
                if email not in user_report_map:
                    user_report_map[email] = []
                
                user_report_map[email].append(
                    frappe._dict({
                        "doctype_name": b.doctype_name,
                        "record_id": b.record_id,
                        "stage": b.stage,
                        "hours_exceeded": b.hours_exceeded,
                        "doc_cc": doc_cost_center
                    })
                )
        # --- CHANGE END ---

        email_no_cc_data = frappe.get_all(
            "Email ID", # Child Doctype name
            filters={
                "parent": b.name,
                "parentfield": "email_idwithout_cost_center"
            },
            fields=["email_id"]
        )

        for e in email_no_cc_data:
            email = e.email_id
            if not validate_email_address(email, throw=False):
                continue

            if email not in user_report_map:
                user_report_map[email] = []

            # Isme bina permission check kiye data add hoga
            user_report_map[email].append(
                frappe._dict({
                    "doctype_name": b.doctype_name,
                    "record_id": b.record_id,
                    "stage": b.stage,
                    "hours_exceeded": b.hours_exceeded,
                    "doc_cc": doc_cost_center or "N/A"
                })
            )
        # --- CHANGE END ---

    # SEND EMAILS

    sent_count = 0

    for email, logs in user_report_map.items():

        if not logs:
            continue

        try:

            content = render_email_template(logs)

            frappe.sendmail(
                recipients=email,
                subject=f"SLA Breach Summary - {now_datetime().strftime('%Y-%m-%d')}",
                content=content,
                now=True
            )

            sent_count += 1

            print(f"Email sent to: {email}")

        except Exception as e:

            print(f"Failed for {email}: {str(e)}")

    print(f"Completed. Total users notified: {sent_count}")


# EMAIL TEMPLATE

def render_email_template(logs):

    html = f"""
    <div style="
        font-family: Arial, sans-serif;
        background-color: #f4f6f9;
        padding: 20px;
    ">

        <div style="
            max-width: 1000px;
            margin: auto;
            background: #ffffff;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        ">

            <!-- HEADER -->

            <div style="
                background: linear-gradient(90deg, #ff4d4f, #ff7875);
                color: white;
                padding: 20px;
                text-align: center;
            ">

                <h2 style="margin:0;">
                    🚨 SLA Breach Summary Report
                </h2>

                <p style="
                    margin-top:8px;
                    font-size:14px;
                ">
                    Last 24 Hours Breach Notification
                </p>

            </div>

            <!-- BODY -->

            <div style="padding:20px;">

                <p style="
                    font-size:14px;
                    color:#444;
                ">
                    Hello Team,
                    <br><br>

                    Below are the SLA breached records identified in the last 24 hours.
                </p>

                <table style="
                    width:100%;
                    border-collapse: collapse;
                    font-size:14px;
                ">

                    <thead>

                        <tr style="
                            background-color:#1f2937;
                            color:white;
                        ">

                            <th style="
                                padding:12px;
                                border:1px solid #ddd;
                            ">
                                Document Type
                            </th>

                            <th style="
                                padding:12px;
                                border:1px solid #ddd;
                            ">
                                Record ID
                            </th>

                            <th style="
                                padding:12px;
                                border:1px solid #ddd;
                            ">
                                Cost Center
                            </th>

                            <th style="
                                padding:12px;
                                border:1px solid #ddd;
                            ">
                                Current Stage
                            </th>

                            <th style="
                                padding:12px;
                                border:1px solid #ddd;
                            ">
                                Delay (Hours)
                            </th>

                        </tr>

                    </thead>

                    <tbody>
    """

    for i, l in enumerate(logs):

        link = get_link_to_form(
            l.doctype_name,
            l.record_id
        )

        row_color = "#f9fafb" if i % 2 == 0 else "#ffffff"

        try:
            delay_display = f"{round(float(l.hours_exceeded), 2)} hrs"
        except:
            delay_display = f"{l.hours_exceeded} hrs"

        html += f"""

            <tr style="
                background-color:{row_color};
            ">

                <td style="
                    padding:10px;
                    border:1px solid #ddd;
                ">
                    {l.doctype_name}
                </td>

                <td style="
                    padding:10px;
                    border:1px solid #ddd;
                ">
                    {link}
                </td>

                <td style="
                    padding:10px;
                    border:1px solid #ddd;
                ">
                    {l.doc_cc}
                </td>

                <td style="
                    padding:10px;
                    border:1px solid #ddd;
                    color:#d97706;
                    font-weight:bold;
                ">
                    {l.stage}
                </td>

                <td style="
                    padding:10px;
                    border:1px solid #ddd;
                    color:#dc2626;
                    font-weight:bold;
                ">
                    {delay_display}
                </td>

            </tr>
        """

    html += """

                    </tbody>

                </table>

                <br>

                <div style="
                    margin-top:20px;
                    padding:15px;
                    background:#fff7ed;
                    border-left:4px solid #f97316;
                    color:#7c2d12;
                    font-size:13px;
                ">
                    ⚠ Please review the breached records and take necessary action as soon as possible.
                </div>

            </div>

            <!-- FOOTER -->

            <div style="
                background:#f3f4f6;
                padding:15px;
                text-align:center;
                font-size:12px;
                color:#666;
            ">
                This is an automated SLA notification generated by ERP System.
            </div>

        </div>

    </div>
    """

    return html