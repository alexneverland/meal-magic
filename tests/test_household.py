"""Synthetic household/onboarding persistence and schema-upgrade behavior."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_store as base

StoreError, SCRIPT, store_module = base.StoreError, base.SCRIPT, base.store_module


class HouseholdTests(unittest.TestCase):
    setUp = base.StoreTests.setUp
    call = base.StoreTests.call
    save = base.StoreTests.save
    log = base.StoreTests.log

    def member(self, label="Child 1", **fields):
        return self.call("member-set", label=label, **fields)

    def test_onboarding_persists_across_processes_and_does_not_create_meals(self):
        self.call("onboarding-set", status="in_progress")
        child = self.member(age_group="young_child", notes="Approximate age stated by user; synthetic.")
        self.call("preference-set", kind="prefer", target="chickpea rice", member_id=child["id"])
        self.call("onboarding-set", status="completed")
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input='{"action":"context"}', encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        context = json.loads(p.stdout)["result"]
        self.assertEqual(context["household"]["onboarding"]["status"], "completed")
        self.assertEqual(context["household"]["members"][0]["id"], child["id"])
        self.assertEqual(context["recent_meals"], [])
        self.assertEqual(self.call("recipe-search"), [])

    def test_skip_and_restart_do_not_clear_supplied_profile(self):
        child = self.member(age_group="young_child")
        self.call("preference-set", kind="forbid", target="mushrooms", member_id=child["id"])
        for status in ("skipped", "pending", "in_progress", "completed"):
            self.call("onboarding-set", status=status)
            context = self.call("context")
            self.assertEqual(len(context["household"]["members"]), 1)
            self.assertEqual(len(context["preferences"]), 1)

    def test_child_older_adult_and_unknown_do_not_invent_allergies(self):
        self.member(age_group="young_child")
        self.member(label="Older adult 1", age_group="older_adult")
        self.member(label="Guest")
        ctx = self.call("context")
        self.assertEqual({m["age_group"] for m in ctx["household"]["members"]},
                         {"young_child", "older_adult", "unspecified"})
        self.assertTrue(all(m["allergy_status"] == "unknown" for m in ctx["household"]["members"]))
        self.assertEqual(ctx["preferences"], [])

    def test_member_fields_preserved_on_partial_update_and_labels_unique(self):
        child = self.member(age_group="young_child", allergy_status="none_reported", notes="Synthetic age note")
        retry = self.member()
        self.assertEqual(retry["id"], child["id"])
        self.assertEqual(retry["allergy_status"], "none_reported")
        renamed = self.member(label="Young diner", id=child["id"])
        self.assertEqual(renamed["age_group"], "young_child")
        self.assertEqual(renamed["notes"], "Synthetic age note")
        other = self.member(label="Other")
        with self.assertRaisesRegex(StoreError, "member_label_in_use"):
            self.member(label="Other", id=child["id"])
        self.assertNotEqual(other["id"], child["id"])

    def test_same_preference_is_independent_per_member_and_household(self):
        child = self.member()
        elder = self.member(label="Older adult 1", age_group="older_adult")
        ids = []
        for scope in (None, child["id"], elder["id"]):
            first = self.call("preference-set", kind="prefer", target="rice", member_id=scope)
            again = self.call("preference-set", kind="prefer", target="rice", member_id=scope)
            self.assertEqual(first["id"], again["id"])
            ids.append(first["id"])
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(len(self.call("context")["preferences"]), 3)

    def test_allergy_report_overrides_none_reported_and_cannot_be_hidden(self):
        child = self.member(allergy_status="none_reported")
        allergy = self.call("preference-set", kind="allergy", target="sesame", member_id=child["id"])
        self.assertEqual(self.call("context")["household"]["members"][0]["allergy_status"], "reported")
        with self.assertRaisesRegex(StoreError, "member_has_allergy_preferences"):
            self.member(id=child["id"], allergy_status="none_reported")
        updated = self.call("preference-set", id=allergy["id"], kind="allergy", target="sesame", notes="Confirmed synthetic update")
        self.assertEqual(updated["member_id"], child["id"])
        self.call("preference-remove", id=allergy["id"])
        self.assertEqual(self.call("context")["household"]["members"][0]["allergy_status"], "unknown")

    def test_reassigning_an_allergy_refreshes_both_members(self):
        child, adult = self.member(), self.member(label="Adult 1")
        allergy = self.call("preference-set", kind="allergy", target="peanuts", member_id=child["id"])
        self.call("preference-set", id=allergy["id"], kind="allergy", target="peanuts", member_id=adult["id"])
        members = {m["id"]: m for m in self.call("context")["household"]["members"]}
        self.assertEqual(members[child["id"]]["allergy_status"], "unknown")
        self.assertEqual(members[adult["id"]]["allergy_status"], "reported")

    def test_member_removal_cannot_silently_delete_restrictions(self):
        child = self.member()
        pref = self.call("preference-set", kind="forbid", target="mushrooms", member_id=child["id"])
        with self.assertRaisesRegex(StoreError, "member_has_preferences"):
            self.call("member-remove", id=child["id"])
        self.assertEqual(self.call("context")["preferences"][0]["id"], pref["id"])
        self.call("preference-remove", id=pref["id"])
        self.call("member-remove", id=child["id"])
        self.assertEqual(self.call("context")["household"]["members"], [])

    def test_unknown_member_and_invalid_structured_values_fail(self):
        bad = [
            {"action": "member-set", "label": "Child", "age_group": "guessed"},
            {"action": "member-set", "label": "Child", "allergy_status": "probably_none"},
            {"action": "member-set", "label": "Child", "id": "missing"},
            {"action": "onboarding-set", "status": "automatically_inferred"},
            {"action": "preference-set", "kind": "allergy", "target": "nuts", "member_id": "missing"},
            {"action": "member-remove", "id": "missing"},
        ]
        for req in bad:
            with self.subTest(req=req), self.assertRaises(StoreError):
                self.store.handle(req)
        self.assertEqual(self.call("context")["household"]["members"], [])

    def seed_legacy(self):
        self.data.mkdir()
        with closing(sqlite3.connect(self.store.path)) as con:
            for sql in store_module.SCHEMA:
                con.execute(sql)
            con.execute("INSERT INTO preferences VALUES ('pref-old','allergy','synthetic sesame','legacy note','2026-01-01')")
            con.execute("INSERT INTO recipes VALUES ('recipe-old','Synthetic rice','Exact old content', '[]',"
                        "'generated','2026-01-01',1,'old-save',?)",
                        (json.dumps({"name": "Synthetic rice", "content": "Exact old content", "tags": [], "source": "generated"}),))
            con.execute("INSERT INTO meals VALUES ('meal-old','eaten','Synthetic rice','2026-01-01',"
                        "'recipe-old','2026-01-01','old-log','{}')")
            con.execute("PRAGMA user_version = 1")
            con.commit()

    def test_legacy_upgrade_preserves_ids_recipes_favorites_and_history(self):
        self.seed_legacy()
        ctx = self.call("context")
        self.assertEqual(ctx["preferences"][0]["id"], "pref-old")
        self.assertIsNone(ctx["preferences"][0]["member_id"])
        self.assertEqual(ctx["household"]["onboarding"]["status"], "pending")
        self.assertEqual(ctx["household"]["members"], [])
        recipe = self.call("recipe-get", id="recipe-old")
        self.assertEqual(recipe["content"], "Exact old content")
        self.assertTrue(recipe["favorite"])
        self.assertEqual(ctx["recent_meals"][0]["id"], "meal-old")
        exported = self.call("export")
        self.assertEqual(exported["schema_version"], 4)
        self.assertEqual(len(exported["preferences"]), 1)
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_failed_upgrade_rolls_back_entire_schema_change(self):
        self.seed_legacy()
        with patch.object(store_module, "now", side_effect=RuntimeError("synthetic migration failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic migration failure"):
                self.call("context")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT id FROM preferences").fetchone()[0], "pref-old")
            self.assertNotIn("member_id", [r[1] for r in con.execute("PRAGMA table_info(preferences)")])
            self.assertFalse(con.execute("SELECT name FROM sqlite_master WHERE name='members'").fetchone())
        self.assertEqual(self.call("context")["preferences"][0]["id"], "pref-old")

    def test_export_contains_household_without_creating_a_recipe_for_favorite_food(self):
        child = self.member(age_group="young_child")
        self.call("preference-set", kind="prefer", target="synthetic favorite pasta", member_id=child["id"])
        export = self.call("export")
        self.assertEqual(export["household"]["members"][0]["id"], child["id"])
        self.assertEqual(export["recipes"], [])
        self.assertEqual(export["meals"], [])

    def test_missing_onboarding_record_fails_without_resetting_members(self):
        member = self.member()
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DELETE FROM onboarding")
            con.commit()
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input='{"action":"context"}', encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["error"], "onboarding_state_missing")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT id FROM members").fetchone()[0], member["id"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM onboarding").fetchone()[0], 0)
