


# Copyright (c) 2024
# SLA Management App

import frappe
from frappe.utils import now_datetime, add_days, get_datetime, validate_email_address
from frappe import _


def sla_daily_summary():
    """
    Daily Scheduled Job
    - Collects all SLA Breach Log records (ALL verticals)
    - Groups them by reporting_manager_email
    - Sends ONE consolidated email per manager
    """

    print("Executing SLA Daily Summary...")
    frappe.logger().info("Starting SLA Daily Summary...")

    # Last 24 hours
    from_date = add_days(now_datetime(), -1)

    # 1️ Fetch ALL SLA Breaches (no vertical filter)
    breaches = frappe.get_all(
        "SLA Breach Log",
        filters={
            "breached_on": [">=", from_date]
        },
        fields=[
            "name",
            "vertical",
            "doctype_name",
            "record_id",
            "breached_by",
            "stage",
            "hours_exceeded",
            "breached_on",
            "reporting_manager_email",
            "message"
        ],
        order_by="reporting_manager_email asc"
    )

    if not breaches:
        print("No SLA breaches found.")
        return 0

    print(f"Total breaches found: {len(breaches)}")

    # 2️ Group breaches by VALID manager email
    breaches_by_manager = {}
    skipped = 0

    for breach in breaches:
        mgr_email = breach.get("reporting_manager_email")

        # Skip missing email
        if not mgr_email:
            skipped += 1
            continue

        email = mgr_email.strip().lower()

        # Skip invalid email
        if not validate_email_address(email):
            skipped += 1
            continue

        breaches_by_manager.setdefault(email, []).append(breach)

    print(f"Skipped {skipped} breaches due to missing/invalid email")

    if not breaches_by_manager:
        print("No valid manager emails found. No emails sent.")
        return len(breaches)

    # 3️ Send consolidated email per manager
    sent_count = 0
    base_url = frappe.utils.get_url()

    for manager_email, manager_breaches in breaches_by_manager.items():
        try:
            print(f"Preparing email for: {manager_email} ({len(manager_breaches)} records)")

            subject = _("Daily SLA Breach Summary: {0} Records").format(len(manager_breaches))
            rows = []

            for b in manager_breaches:
                delay_days = b.get("hours_exceeded") or 0

                doctype_name = b.get("doctype_name") or "Lead"
                dt_slug = doctype_name.lower().replace(" ", "-")

                record_id = b.get("record_id") or "Unknown"
                record_url = f"{base_url}/app/{dt_slug}/{record_id}"

                rows.append(f"""
                <tr>
                    <td style="border:1px solid #ddd;padding:6px;">
                        <a href="{record_url}">{record_id}</a>
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;">
                        {b.get("vertical") or "-"}
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;">
                        {b.get("stage") or "-"}
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;color:red;">
                        {delay_days:.3f} Days
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;">
                        {b.get("breached_by") or "-"}
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;">
                        {b.get("message") or "-"}
                    </td>
                    <td style="border:1px solid #ddd;padding:6px;">
                        {get_datetime(b.get("breached_on")).strftime('%Y-%m-%d %I:%M %p')}
                    </td>
                </tr>
                """)

            email_html = f"""
            <div style="font-family:Arial,sans-serif;">
                <p>Hello,</p>
                <p>Please find below the SLA breach summary for the last 24 hours:</p>

                <table style="border-collapse:collapse;width:100%;font-size:11px;">
                    <thead>
                        <tr style="background:#f2f2f2;">
                            <th style="border:1px solid #ddd;padding:6px;">Record</th>
                            <th style="border:1px solid #ddd;padding:6px;">Vertical</th>
                            <th style="border:1px solid #ddd;padding:6px;">Stage</th>
                            <th style="border:1px solid #ddd;padding:6px;">Delay</th>
                            <th style="border:1px solid #ddd;padding:6px;">Owner</th>
                            <th style="border:1px solid #ddd;padding:6px;">Message</th>
                            <th style="border:1px solid #ddd;padding:6px;">Time</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>

                <p>Please take necessary action.</p>
                <hr>
                <small>Automated SLA Management System</small>
            </div>
            """

            frappe.sendmail(
                recipients=[manager_email],
                subject=subject,
                message=email_html,
                delayed=False
            )

            sent_count += 1
            print(f"Email queued for {manager_email}")

        except Exception as e:
            frappe.logger().error(f"SLA Summary failed for {manager_email}: {e}")

    frappe.db.commit()
    print(f"Summary sent to {sent_count} managers.")
    return len(breaches)
