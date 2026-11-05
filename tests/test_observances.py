"""Synthetic locale/practice persistence; no holiday calendars or model calls."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_store as base
import test_household as households

StoreError, SCRIPT, store_module = base.StoreError, base.SCRIPT, base.store_module


class ObservanceTests(unittest.TestCase):
    setUp = base.StoreTests.setUp
    call = base.StoreTests.call

    def member(self, label="Adult 1"):
        return self.call("member-set", label=label)

    def observance(self, **overrides):
        fields = {"label": "Synthetic weekly practice", "kind": "fasting",
                  "schedule": "Wednesdays and Fridays, as stated by this user",
                  "rules": "Use the user's explicitly permitted ingredients; no other rules inferred.",
                  "strictness": "strict"}
        fields.update(overrides)
        return self.call("observance-set", **fields)

    def test_empty_locale_and_country_do_not_infer_beliefs_or_practices(self):
        household = self.call("context")["household"]
        self.assertIsNone(household["locale"]["country"])
        self.assertEqual(household["locale"]["holiday_mode"], "unknown")
        self.assertEqual(household["observances"], [])
        self.call("locale-set", country="Greece", region="Synthetic region")
        context = self.call("context")
        self.assertEqual(context["household"]["observances"], [])
        self.assertEqual(context["preferences"], [])
        self.assertEqual(context["recent_meals"], [])
        self.assertEqual(self.call("recipe-search"), [])

    def test_locale_partial_updates_clear_and_persist_across_process(self):
        self.call("locale-set", country="Greece", region="Synthetic region", timezone="Europe/Athens")
        changed = self.call("locale-set", holiday_mode="suggest")
        self.assertEqual(changed["country"], "Greece")
        self.assertEqual(changed["timezone"], "Europe/Athens")
        unchanged = self.call("locale-set", country=" Greece ")
        self.assertEqual(unchanged["region"], "Synthetic region")
        self.assertEqual(unchanged["timezone"], "Europe/Athens")
        self.call("locale-set", region=None)
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input='{"action":"context"}', encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        locale = json.loads(p.stdout)["result"]["household"]["locale"]
        self.assertIsNone(locale["region"])
        self.assertEqual(locale["holiday_mode"], "suggest")

    def test_changed_country_does_not_keep_a_stale_region_or_timezone(self):
        self.call("locale-set", country="Country A", region="Region A", timezone="Zone A")
        locale = self.call("locale-set", country="Country B")
        self.assertIsNone(locale["region"])
        self.assertIsNone(locale["timezone"])
        locale = self.call("locale-set", country="Country C", region="Region C", timezone="Zone C")
        self.assertEqual(locale["region"], "Region C")
        self.assertEqual(locale["timezone"], "Zone C")

    def test_observance_keeps_custom_schedule_and_rules_without_calendar_inference(self):
        schedule = "Τετάρτη και Παρασκευή, εκτός από τις εξαιρέσεις που θα δηλώσω."
        rules = "Λαδερά με τους δικούς μου περιορισμούς, όχι γενίκευση σε άλαδα."
        item = self.observance(schedule=schedule, rules=rules, calendar="User's local calendar")
        fetched = self.call("context")["household"]["observances"][0]
        self.assertEqual(fetched["id"], item["id"])
        self.assertEqual(fetched["schedule"], schedule)
        self.assertEqual(fetched["rules"], rules)
        self.assertEqual(fetched["calendar"], "User's local calendar")
        self.assertNotIn("computed_dates", fetched)
        self.assertEqual(self.call("meal-list"), [])

    def test_requested_date_weekday_is_exact_without_inventing_an_observance(self):
        self.observance()
        thursday = self.call("context", on="2026-11-05")
        friday = self.call("context", on="2026-11-06")
        self.assertEqual(thursday["date_context"], {"on": "2026-11-05", "year": 2026, "weekday_iso": 4})
        self.assertEqual(friday["date_context"]["weekday_iso"], 5)
        self.assertEqual(len(friday["household"]["observances"]), 1)
        self.assertNotIn("date_context", self.call("context"))
        for invalid in ("2026-02-30", "Friday", "20261106"):
            with self.subTest(invalid=invalid), self.assertRaises(StoreError):
                self.call("context", on=invalid)

    def test_same_label_is_independent_for_members_and_household(self):
        adult, child = self.member(), self.member(label="Child 1")
        ids = set()
        for member_id in (None, adult["id"], child["id"]):
            first = self.observance(member_id=member_id)
            second = self.observance(member_id=member_id)
            self.assertEqual(first["id"], second["id"])
            ids.add(first["id"])
        self.assertEqual(len(ids), 3)

    def test_partial_update_preserves_rules_owner_and_inactive_state(self):
        adult = self.member()
        item = self.observance(member_id=adult["id"], calendar="Synthetic calendar", notes="User-specific exception")
        changed = self.call("observance-set", id=item["id"], label=item["label"], active=False)
        self.assertFalse(changed["active"])
        self.assertEqual(changed["member_id"], adult["id"])
        self.assertEqual(changed["rules"], item["rules"])
        retry = self.call("observance-set", label=item["label"], member_id=adult["id"])
        self.assertFalse(retry["active"])
        self.assertEqual(retry["calendar"], "Synthetic calendar")
        self.assertEqual(retry["notes"], "User-specific exception")

    def test_occasion_ideas_off_does_not_delete_or_disable_active_fast(self):
        item = self.observance()
        self.call("locale-set", holiday_mode="off")
        context = self.call("context")["household"]
        self.assertEqual(context["locale"]["holiday_mode"], "off")
        self.assertEqual(context["observances"][0]["id"], item["id"])
        self.assertTrue(context["observances"][0]["active"])

    def test_member_removal_requires_explicit_observance_removal_or_reassignment(self):
        adult = self.member()
        item = self.observance(member_id=adult["id"], active=False)
        with self.assertRaisesRegex(StoreError, "member_has_observances"):
            self.call("member-remove", id=adult["id"])
        self.call("observance-set", id=item["id"], label=item["label"], member_id=None)
        self.call("member-remove", id=adult["id"])
        self.assertIsNone(self.call("context")["household"]["observances"][0]["member_id"])
        self.call("observance-remove", id=item["id"])
        self.assertEqual(self.call("context")["household"]["observances"], [])

    def test_unknown_ids_invalid_fields_and_label_collision_refused(self):
        item = self.observance()
        other = self.observance(label="Another synthetic practice")
        bad = [
            {"action": "observance-set", "id": "missing", "label": "x"},
            {"action": "observance-set", "label": "x", "schedule": "weekly", "rules": "x", "member_id": "missing"},
            {"action": "observance-set", "label": "x", "schedule": "weekly", "rules": "x", "active": "false"},
            {"action": "observance-set", "label": "x", "schedule": "weekly", "rules": "x", "strictness": "guessed"},
            {"action": "observance-set", "label": "x", "schedule": "weekly", "rules": "x", "kind": "religion_guess"},
            {"action": "observance-set", "label": "x"},
            {"action": "observance-set", "label": other["label"], "id": item["id"]},
            {"action": "observance-remove", "id": "missing"},
            {"action": "locale-set", "country": ""},
            {"action": "locale-set", "holiday_mode": "assume_religion"},
        ]
        for req in bad:
            with self.subTest(req=req), self.assertRaises(StoreError):
                self.store.handle(req)
        self.assertEqual(len(self.call("context")["household"]["observances"]), 2)

    def seed_schema_two(self):
        households.HouseholdTests.seed_legacy(self)
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("CREATE TABLE members (id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE, "
                        "age_group TEXT NOT NULL, allergy_status TEXT NOT NULL, notes TEXT NOT NULL, updated_at TEXT NOT NULL)")
            con.execute("ALTER TABLE preferences ADD COLUMN member_id TEXT REFERENCES members(id)")
            con.execute("CREATE TABLE onboarding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), status TEXT NOT NULL, updated_at TEXT NOT NULL)")
            con.execute("INSERT INTO onboarding VALUES (1,'completed','2026-01-01')")
            con.execute("INSERT INTO members VALUES ('member-old','Adult 1','adult','reported','Synthetic member','2026-01-01')")
            con.execute("UPDATE preferences SET member_id='member-old'")
            con.execute("PRAGMA user_version = 2")
            con.commit()

    def test_schema_two_upgrade_preserves_members_ownership_and_completed_intake(self):
        self.seed_schema_two()
        context = self.call("context")
        self.assertEqual(context["household"]["onboarding"]["status"], "completed")
        self.assertEqual(context["preferences"][0]["member_id"], "member-old")
        self.assertEqual(context["household"]["members"][0]["id"], "member-old")
        self.assertEqual(context["household"]["observances"], [])
        self.assertIsNone(context["household"]["locale"]["country"])
        self.assertTrue(self.call("recipe-get", id="recipe-old")["favorite"])
        self.assertEqual(context["recent_meals"][0]["id"], "meal-old")
        self.assertEqual(self.call("export")["schema_version"], 3)

    def test_failed_schema_two_upgrade_rolls_back_without_losing_household(self):
        self.seed_schema_two()
        with patch.object(store_module, "now", side_effect=RuntimeError("synthetic locale migration failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic locale migration failure"):
                self.call("context")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT id FROM members").fetchone()[0], "member-old")
            self.assertFalse(con.execute("SELECT name FROM sqlite_master WHERE name='locale'").fetchone())
        self.assertEqual(self.call("context")["household"]["members"][0]["id"], "member-old")

    def test_export_contains_locale_and_scoped_observances(self):
        self.call("locale-set", country="Synthetic country", holiday_mode="suggest")
        item = self.observance()
        exported = self.call("export")
        self.assertEqual(exported["household"]["locale"]["country"], "Synthetic country")
        self.assertEqual(exported["household"]["observances"][0]["id"], item["id"])
        self.assertEqual(exported["recipes"], [])
        self.assertEqual(exported["meals"], [])

    def test_missing_locale_state_fails_without_resetting_observances(self):
        item = self.observance()
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DELETE FROM locale")
            con.commit()
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input='{"action":"context"}', encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["error"], "locale_state_missing")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT id FROM observances").fetchone()[0], item["id"])
