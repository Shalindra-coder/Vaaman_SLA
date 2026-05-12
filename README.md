# SLA Management App

SLA Tracker & Escalation System for ERPNext (Lead + Opportunity)

## Overview

This Frappe custom app implements SLA monitoring, notifications, and escalation workflows for **Lead** and **Opportunity** doctypes based on vertical and stage combinations.

## Features

1. **Track time in stage** - Automatically tracks how long a Lead/Opportunity remains in a given stage
2. **SLA Rule Management** - Define SLA rules per Vertical + Stage combination
3. **Real-time Notifications** - In-app notifications when SLA breaches occur
4. **Daily Email Summaries** - Consolidated email reports to reporting managers
5. **Escalation Logic** - Automatic escalation based on hierarchy
6. **SLA Breach Logging** - Complete audit trail of all SLA breaches

## Installation

```bash
# Create the app (already done)
cd /path/to/frappe-bench
bench new-app sla_management

# Install on your site
bench --site yoursite install-app sla_management

# Migrate
bench --site yoursite migrate
```

## Setup

### 1. Configure SLA Rules

Navigate to **SLA Rule** doctype and create rules for each Vertical + Stage combination:

- **Vertical**: Permanent / Temporary / LLC / L&D / Franchise
- **Applies To**: Lead or Opportunity
- **Stage Field**: "status" (for Lead) or "stage" (for Opportunity)
- **Stage Value**: e.g., "New", "Proposal Sent", etc.
- **Max Hours Allowed**: SLA threshold in hours
- **Notify To**: Email addresses to notify on breach
- **Escalate To**: Optional escalation email

### 2. Configure Reporting Hierarchy

Navigate to **CRM Reporting Hierarchy** and populate the hierarchy:

- User Email
- Reporting Manager Email
- Department, Designation, Role

### 3. Custom Fields

The app automatically adds custom fields to Lead and Opportunity:
- `vertical` (Select)
- `last_stage_change_on` (Datetime, hidden, read-only)

## Scheduled Jobs

### Hourly SLA Checker

Runs every hour to:
- Check all active Leads and Opportunities against SLA rules
- Send in-app notifications on breach
- Create SLA Breach Log entries

**Manual trigger:**
```bash
bench --site yoursite execute sla_management.scripts.sla_checker.sla_checker
```

### Daily Email Summary

Runs daily at 7 AM to:
- Fetch all SLA breaches in the last 24 hours
- Group by reporting manager
- Send consolidated email summaries

**Manual trigger:**
```bash
bench --site yoursite execute sla_management.scripts.sla_daily_summary.sla_daily_summary
```

## Testing

### Test Cases

1. **New Lead Creation**
   - Create a Lead with status "New"
   - Verify `last_stage_change_on` auto-populates

2. **Lead Status Change**
   - Change status → "Working"
   - Verify `last_stage_change_on` updates

3. **SLA Rule Match**
   - Create SLA rule for Permanent + New = 24 hrs
   - Verify records tracked correctly

4. **SLA Breach**
   - Wait > 24 hrs or modify `last_stage_change_on` manually
   - Run hourly SLA checker
   - Verify notification created + breach log inserted

5. **Daily Summary**
   - Simulate multiple breaches
   - Run `sla_daily_summary()`
   - Verify one consolidated email per boss

6. **Hierarchy Fallback**
   - Boss email missing
   - Verify defaults to crm-head@promptpersonnel.com

7. **Client Warning**
   - Open Lead with breached SLA
   - Verify red warning banner appears

## Structure

```
sla_management/
├── sla_management/
│   ├── __init__.py
│   ├── hooks.py
│   ├── doctype/
│   │   ├── sla_rule/
│   │   ├── sla_breach_log/
│   │   └── crm_reporting_hierarchy/
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── sla_checker.py
│   │   └── sla_daily_summary.py
│   └── public/
│       └── js/
│           ├── lead_sla_warning.js
│           └── opportunity_sla_warning.js
├── pyproject.toml
└── README.md
```

## License

MIT



