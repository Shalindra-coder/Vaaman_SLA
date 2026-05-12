#!/bin/bash

# SLA Management Test Runner
# This script runs all test cases for the SLA Management app

echo "=========================================="
echo "SLA Management Test Suite"
echo "=========================================="
echo ""

SITE_NAME="${1:-vidhi}"

echo "Site: $SITE_NAME"
echo ""

# Function to run a test case
run_test() {
    local test_name=$1
    local command=$2
    
    echo "Running: $test_name"
    echo "Command: $command"
    echo "---"
    
    if bench --site "$SITE_NAME" execute "$command"; then
        echo "✅ PASSED: $test_name"
    else
        echo "❌ FAILED: $test_name"
    fi
    echo ""
}

# Test 1: Create SLA Rule
echo "Test 1: Creating SLA Rule..."
bench --site "$SITE_NAME" console << 'EOF'
import frappe
frappe.init(site='vidhi')
frappe.connect()

sla_rule = frappe.get_doc({
    "doctype": "SLA Rule",
    "vertical": "Permanent Staffing",
    "applies_to": "Lead",
    "stage_field": "status",
    "stage_value": "New",
    "max_hours_allowed": 24,
    "active": 1
})
sla_rule.insert()
print(f"✅ SLA Rule created: {sla_rule.name}")
frappe.db.commit()
EOF

echo ""

# Test 2: Test Stage Change Timestamp
echo "Test 2: Testing Stage Change Timestamp..."
bench --site "$SITE_NAME" console << 'EOF'
import frappe
frappe.init(site='vidhi')
frappe.connect()

lead = frappe.get_doc({
    "doctype": "Lead",
    "lead_name": "Test Lead for Timestamp",
    "status": "New",
    "vertical": "Permanent Staffing",
    "naming_series": "CRM-LEAD-.YYYY.-"
})
lead.set_new_name()
lead.insert()

if lead.last_stage_change_on:
    print(f"✅ Timestamp auto-populated: {lead.last_stage_change_on}")
else:
    print("❌ Timestamp not populated")
frappe.db.commit()
EOF

echo ""

# Test 3: Test SLA Breach Detection
echo "Test 3: Testing SLA Breach Detection..."
bench --site "$SITE_NAME" console << 'EOF'
import frappe
frappe.init(site='vidhi')
frappe.connect()
from frappe.utils import add_to_date, now_datetime

# Create lead with breach condition
lead = frappe.get_doc({
    "doctype": "Lead",
    "lead_name": "Test Breach Lead",
    "status": "New",
    "vertical": "Permanent Staffing",
    "naming_series": "CRM-LEAD-.YYYY.-"
})
lead.set_new_name()
lead.insert()

# Set breach time
breach_time = add_to_date(now_datetime(), hours=-30)
frappe.db.set_value("Lead", lead.name, "last_stage_change_on", breach_time)
frappe.db.commit()

print(f"✅ Lead created with breach condition: {lead.name}")
EOF

# Run SLA Checker
echo "Running SLA Checker..."
bench --site "$SITE_NAME" execute sla_management.scripts.sla_checker.sla_checker

echo ""

# Check for breach log
echo "Test 4: Checking SLA Breach Log..."
bench --site "$SITE_NAME" console << 'EOF'
import frappe
frappe.init(site='vidhi')
frappe.connect()

breach_logs = frappe.get_all("SLA Breach Log", limit=5)
if breach_logs:
    print(f"✅ Found {len(breach_logs)} breach log(s)")
    for log in breach_logs:
        print(f"  - {log.name}")
else:
    print("⚠️  No breach logs found")
EOF

echo ""

# Test 5: Daily Summary
echo "Test 5: Testing Daily Summary..."
bench --site "$SITE_NAME" execute sla_management.scripts.sla_daily_summary.sla_daily_summary

echo ""
echo "=========================================="
echo "Test Suite Complete"
echo "=========================================="

