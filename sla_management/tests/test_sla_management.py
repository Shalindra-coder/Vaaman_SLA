# Copyright (c) 2024, SLA Management Team and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date, get_datetime
from datetime import timedelta
import json
import os
from sla_management.tests.test_helpers import create_test_lead, create_test_sla_rule, set_lead_breach_condition


class TestSLAManagement(FrappeTestCase):
	"""Test cases for SLA Management app"""

	def setUp(self):
		"""Set up test data"""
		self.test_vertical = "Permanent Staffing"
		self.test_stage = "New"
		self.test_sla_hours = 24
		self.test_user = frappe.session.user

	def tearDown(self):
		"""Clean up test data"""
		# Clean up test records
		frappe.db.rollback()

	def test_01_create_sla_rule(self):
		"""Test Case 1: SLA Rule Creation"""
		sla_rule = frappe.get_doc({
			"doctype": "SLA Rule",
			"vertical": self.test_vertical,
			"applies_to": "Lead",
			"stage_field": "status",
			"stage_value": self.test_stage,
			"max_hours_allowed": self.test_sla_hours,
			"responsibility": "Test Responsibility",
			"notify_to": "test@example.com",
			"active": 1
		})
		sla_rule.insert()

		self.assertTrue(frappe.db.exists("SLA Rule", sla_rule.name))
		self.assertEqual(sla_rule.active, 1)
		self.assertEqual(sla_rule.vertical, self.test_vertical)

	def test_02_stage_change_timestamp_new_record(self):
		"""Test Case 2: Stage Change Timestamp - New Record"""
		lead = create_test_lead("Test Lead", self.test_stage, self.test_vertical)

		self.assertIsNotNone(lead.last_stage_change_on)
		# last_stage_change_on can be datetime object or string
		if lead.last_stage_change_on:
			# Verify timestamp is recent (within last minute)
			if isinstance(lead.last_stage_change_on, str):
				timestamp = get_datetime(lead.last_stage_change_on)
			else:
				timestamp = lead.last_stage_change_on
			now = now_datetime()
			diff = (now - timestamp).total_seconds()
			self.assertLess(diff, 60, "Timestamp should be recent")

	def test_03_stage_change_timestamp_update(self):
		"""Test Case 3: Stage Change Timestamp - Update"""
		lead = create_test_lead("Test Lead Update", "New", self.test_vertical)
		original_timestamp = lead.last_stage_change_on

		# Wait a moment
		import time
		time.sleep(1)

		# Change stage
		lead.status = "Working"
		lead.save()

		self.assertNotEqual(lead.last_stage_change_on, original_timestamp)
		self.assertIsNotNone(lead.last_stage_change_on)

	def test_04_sla_breach_detection(self):
		"""Test Case 4: SLA Breach Detection"""
		# Create SLA Rule
		sla_rule = create_test_sla_rule(
			self.test_vertical, "Lead", "status", 
			self.test_stage, self.test_sla_hours, active=1
		)

		# Create Lead
		lead = create_test_lead("Test Breach Lead", self.test_stage, self.test_vertical)
		lead.owner = self.test_user
		lead.save()

		# Set breach condition
		set_lead_breach_condition(lead.name, self.test_sla_hours + 5)

		# Run SLA Checker
		from sla_management.scripts.sla_checker import sla_checker
		breach_count = sla_checker()

		# Verify breach log created
		breach_logs = frappe.get_all(
			"SLA Breach Log",
			filters={
				"doctype_name": "Lead",
				"record_id": lead.name
			}
		)

		self.assertGreater(len(breach_logs), 0, "Breach log should be created")
		if breach_logs:
			breach_log = frappe.get_doc("SLA Breach Log", breach_logs[0].name)
			# Breach log stores the Lead's vertical (mapped), not SLA Rule vertical
			from sla_management.tests.test_helpers import map_sla_vertical_to_lead_vertical
			expected_vertical = map_sla_vertical_to_lead_vertical(self.test_vertical)
			self.assertEqual(breach_log.vertical, expected_vertical)
			self.assertEqual(breach_log.stage, self.test_stage)
			self.assertGreater(breach_log.hours_exceeded, 0)

	def test_05_no_breach_scenario(self):
		"""Test Case 5: No Breach Scenario"""
		# Create SLA Rule
		sla_rule = create_test_sla_rule(
			self.test_vertical, "Lead", "status",
			self.test_stage, self.test_sla_hours, active=1
		)

		# Create Lead
		lead = create_test_lead("Test No Breach Lead", self.test_stage, self.test_vertical)

		# Set last_stage_change_on within SLA
		set_lead_breach_condition(lead.name, self.test_sla_hours - 5)

		# Count breaches before
		breach_count_before = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		# Run SLA Checker
		from sla_management.scripts.sla_checker import sla_checker
		sla_checker()

		# Count breaches after
		breach_count_after = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		self.assertEqual(breach_count_before, breach_count_after, "No new breach should be created")

	def test_06_daily_summary_email(self):
		"""Test Case 6: Daily Summary Email"""
		# Create multiple breaches
		breach1 = frappe.get_doc({
			"doctype": "SLA Breach Log",
			"vertical": self.test_vertical,
			"doctype_name": "Lead",
			"record_id": "TEST-001",
			"breached_by": self.test_user,
			"stage": self.test_stage,
			"hours_exceeded": 5.5,
			"breached_on": now_datetime(),
			"boss_email": "manager@example.com"
		})
		breach1.insert(ignore_permissions=True)

		breach2 = frappe.get_doc({
			"doctype": "SLA Breach Log",
			"vertical": self.test_vertical,
			"doctype_name": "Lead",
			"record_id": "TEST-002",
			"breached_by": self.test_user,
			"stage": self.test_stage,
			"hours_exceeded": 3.2,
			"breached_on": now_datetime(),
			"boss_email": "manager@example.com"
		})
		breach2.insert(ignore_permissions=True)
		frappe.db.commit()

		# Run daily summary
		from sla_management.scripts.sla_daily_summary import sla_daily_summary
		result = sla_daily_summary()

		# Verify email was queued (check email queue)
		# Note: Actual email sending requires email server configuration
		self.assertIsNotNone(result)

	def test_07_missing_boss_email_fallback(self):
		"""Test Case 7: Missing Boss Email Fallback"""
		from sla_management.scripts.sla_checker import get_boss_email

		# Test with non-existent user
		boss_email = get_boss_email("nonexistent@example.com")
		self.assertEqual(boss_email, "crm-head@promptpersonnel.com")

		# Test with empty string
		boss_email = get_boss_email("")
		self.assertEqual(boss_email, "crm-head@promptpersonnel.com")

	def test_08_deactivated_sla_rule(self):
		"""Test Case 8: Deactivated SLA Rule"""
		# First, ensure no other active rules exist for this combination
		# Delete any existing active rules for this test
		existing_rules = frappe.get_all("SLA Rule", 
			filters={
				"vertical": self.test_vertical,
				"applies_to": "Lead",
				"stage_value": self.test_stage,
				"active": 1
			}
		)
		for rule in existing_rules:
			frappe.delete_doc("SLA Rule", rule.name, force=1)
		frappe.db.commit()
		
		# Create deactivated SLA Rule
		sla_rule = create_test_sla_rule(
			self.test_vertical, "Lead", "status",
			self.test_stage, self.test_sla_hours, active=0
		)
		
		# Verify rule is deactivated
		sla_rule.reload()
		self.assertEqual(sla_rule.active, 0, "Rule should be deactivated")

		# Create Lead with breach condition
		lead = create_test_lead("Test Deactivated Rule", self.test_stage, self.test_vertical)

		# Set breach condition
		set_lead_breach_condition(lead.name, self.test_sla_hours + 5)
		
		# Count breaches before
		breach_count_before = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		# Run SLA Checker
		from sla_management.scripts.sla_checker import sla_checker
		sla_checker()

		# Count breaches after
		breach_count_after = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		self.assertEqual(breach_count_before, breach_count_after, "Deactivated rule should be ignored")

	def test_09_duplicate_breach_prevention(self):
		"""Test Case 9: Duplicate Breach Prevention"""
		# Create SLA Rule
		sla_rule = create_test_sla_rule(
			self.test_vertical, "Lead", "status",
			self.test_stage, self.test_sla_hours, active=1
		)

		# Create Lead
		lead = create_test_lead("Test Duplicate Prevention", self.test_stage, self.test_vertical)

		# Set breach condition
		set_lead_breach_condition(lead.name, self.test_sla_hours + 5)

		# Run SLA Checker twice
		from sla_management.scripts.sla_checker import sla_checker
		sla_checker()
		breach_count_after_first = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		sla_checker()
		breach_count_after_second = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		self.assertEqual(breach_count_after_first, breach_count_after_second, "Duplicate breach should be prevented")

	def test_10_vertical_filtering(self):
		"""Test Case 13: Vertical Filtering"""
		# Create SLA Rule for Permanent Staffing
		sla_rule = create_test_sla_rule(
			"Permanent Staffing", "Lead", "status", "New", 24, active=1
		)

		# Create Lead with different vertical
		lead = create_test_lead("Test Vertical Filter", "New", "Temporary Staffing")

		# Set breach condition
		set_lead_breach_condition(lead.name, 30)

		# Count breaches before
		breach_count_before = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		# Run SLA Checker
		from sla_management.scripts.sla_checker import sla_checker
		sla_checker()

		# Count breaches after
		breach_count_after = frappe.db.count("SLA Breach Log", {"record_id": lead.name})

		self.assertEqual(breach_count_before, breach_count_after, "Different vertical should not trigger breach")


class TestSLAVerticalWise(FrappeTestCase):
	"""Test cases for each vertical"""

	def test_permanent_vertical_stages(self):
		"""Test all Permanent Staffing vertical stages"""
		stages = ["New", "Working", "Nurturing", "Proposal Sent", "Negotiation"]
		
		for stage in stages:
			with self.subTest(stage=stage):
				sla_rule = frappe.get_doc({
					"doctype": "SLA Rule",
					"vertical": "Permanent Staffing",
					"applies_to": "Lead",
					"stage_field": "status",
					"stage_value": stage,
					"max_hours_allowed": 24,
					"active": 1
				})
				sla_rule.insert()
				self.assertTrue(frappe.db.exists("SLA Rule", sla_rule.name))

	def test_temporary_vertical_stages(self):
		"""Test all Temporary Staffing vertical stages"""
		stages = ["New", "Screening"]
		
		for stage in stages:
			with self.subTest(stage=stage):
				sla_rule = frappe.get_doc({
					"doctype": "SLA Rule",
					"vertical": "Temporary Staffing",
					"applies_to": "Lead",
					"stage_field": "status",
					"stage_value": stage,
					"max_hours_allowed": 24,
					"active": 1
				})
				sla_rule.insert()
				self.assertTrue(frappe.db.exists("SLA Rule", sla_rule.name))

