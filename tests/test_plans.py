"""Plan persistence is separate from actual events; all data is synthetic."""
import concurrent.futures
from contextlib import closing
import copy
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_store as base

StoreError, SCRIPT, store_module = base.StoreError, base.SCRIPT, base.store_module


class PlanTests(unittest.TestCase):
    setUp = base.StoreTests.setUp
    call = base.StoreTests.call

    def plan_request(self, key="synthetic-plan-create"):
        return {"action": "plan-save", "request_key": key, "title": "Synthetic five dinners",
                "notes": "Budget-conscious estimate; no current prices available.",
                "meals": [{"on": f"2026-11-{day:02}", "slot": "dinner", "name": "Synthetic chickpea rice",
                           "servings": 4, "details": "25 minutes; 300 g dry rice, 480 g cooked chickpeas."}
                          for day in range(9, 14)],
                "shopping_list": [{"item": "rice", "quantity": "1.5 kg dry", "notes": "Total for five dinners"},
                                  {"item": "chickpeas", "quantity": "2.4 kg cooked/drained", "notes": ""}]}

    def save(self, req=None):
        return self.store.handle(req or self.plan_request())["result"]

    def update(self, saved, key="synthetic-update"):
        req = self.plan_request(key)
        req.update(id=saved["id"], expected_revision=saved["revision"])
        return req

    def test_create_get_list_and_export_never_record_actual_meals_or_recipes(self):
        plan = self.save()
        self.assertEqual(plan["revision"], 1)
        self.assertEqual(plan["start_on"], "2026-11-09")
        self.assertEqual(plan["end_on"], "2026-11-13")
        self.assertEqual(self.call("plan-get", id=plan["id"]), plan)
        listed = self.call("plan-list")
        self.assertEqual(listed[0]["id"], plan["id"])
        self.assertNotIn("shopping_list", listed[0])
        exported = self.call("export")
        self.assertEqual(exported["plans"], [plan])
        self.assertEqual(exported["meals"], [])
        self.assertEqual(exported["recipes"], [])

    def test_plan_survives_process_restart_and_greek_quantities(self):
        req = self.plan_request()
        req["shopping_list"][0] = {"item": "ρύζι", "quantity": "1,5 κιλά ωμό", "notes": "Συνθετικό"}
        saved = self.save(req)
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input=json.dumps({"action": "plan-get", "id": saved["id"]}),
                           encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["result"], saved)

    def test_specific_day_replacement_saves_full_revised_list_atomically(self):
        original = self.save()
        req = self.update(original)
        req["meals"][2].update(name="Synthetic lentils", details="30 minutes; 300 g dry lentils.")
        req["shopping_list"] = [{"item": "rice", "quantity": "1.2 kg dry"},
                                {"item": "lentils", "quantity": "300 g dry"},
                                {"item": "chickpeas", "quantity": "1.92 kg cooked/drained"}]
        updated = self.save(req)
        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["created_at"], original["created_at"])
        self.assertEqual(updated["meals"][0], original["meals"][0])
        self.assertEqual(updated["meals"][2]["name"], "Synthetic lentils")
        self.assertEqual(updated["shopping_list"][0]["quantity"], "1.2 kg dry")
        self.assertEqual(self.call("meal-list"), [])

    def test_retries_return_original_receipt_without_undoing_a_newer_revision(self):
        create_req = self.plan_request()
        original = self.save(create_req)
        update_req = self.update(original)
        updated = self.save(update_req)
        self.assertEqual(self.save(create_req), original)
        self.assertEqual(self.save(update_req), updated)
        self.assertEqual(self.call("plan-get", id=original["id"])["revision"], 2)
        conflict = copy.deepcopy(create_req)
        conflict["title"] = "Different request using the old key"
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.save(conflict)
        self.assertEqual(len(self.call("plan-list")), 1)

    def test_changed_json_types_conflict_but_object_key_order_does_not(self):
        create = self.plan_request()
        create["meals"][0]["servings"] = 1
        saved = self.save(create)
        self.assertEqual(self.save(dict(reversed(list(create.items())))), saved)
        for value in (True, 1.0):
            changed = copy.deepcopy(create)
            changed["meals"][0]["servings"] = value
            with self.subTest(value=value), self.assertRaisesRegex(StoreError, "request_key_conflict"):
                self.save(changed)
        update = self.update(saved)
        self.save(update)
        for value in (True, 1.0):
            changed = copy.deepcopy(update)
            changed["expected_revision"] = value
            with self.subTest(value=value), self.assertRaisesRegex(StoreError, "request_key_conflict"):
                self.save(changed)
        delete = {"action": "plan-remove", "id": saved["id"], "expected_revision": 2, "request_key": "typed-delete"}
        self.store.handle(delete)
        changed = {**delete, "expected_revision": 2.0}
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.store.handle(changed)

    def test_unknown_top_level_fields_take_precedence_over_receipt_checks(self):
        create = self.plan_request()
        saved = self.save(create)
        with self.assertRaisesRegex(StoreError, "^unknown_fields$"):
            self.save({**create, "unexpected": True})
        delete = {"action": "plan-remove", "id": saved["id"], "expected_revision": 1, "request_key": "extra-delete"}
        self.store.handle(delete)
        with self.assertRaisesRegex(StoreError, "^unknown_fields$"):
            self.store.handle({**delete, "unexpected": True})

    def test_paging_can_discover_every_plan_beyond_one_hundred(self):
        ids = set()
        for index in range(105):
            req = self.plan_request(key=f"page-{index}")
            req["title"] = f"Synthetic page {index}"
            ids.add(self.save(req)["id"])
        first = self.call("plan-list", limit=100)
        second = self.call("plan-list", limit=100, offset=100)
        self.assertEqual(len(first), 100)
        self.assertEqual(len(second), 5)
        self.assertEqual({p["id"] for p in first + second}, ids)
        self.assertFalse({p["id"] for p in first} & {p["id"] for p in second})
        self.assertEqual(self.call("plan-list", offset=105), [])
        filtered = self.call("plan-list", on="2026-11-10", limit=100, offset=100)
        self.assertEqual(filtered, second)
        self.assertNotIn("meals", second[0])

    def test_invalid_offsets_are_rejected(self):
        for offset in (-1, True, 1.0, "1", 2**63):
            with self.subTest(offset=offset), self.assertRaisesRegex(StoreError, "invalid_offset"):
                self.call("plan-list", offset=offset)

    def test_plan_listing_uses_index_without_temporary_order_sort(self):
        self.save()
        queries = []
        original_connect = self.store._connect
        def traced_connect():
            con = original_connect()
            con.set_trace_callback(queries.append)
            return con
        with patch.object(self.store, "_connect", side_effect=traced_connect):
            self.call("plan-list")
            self.call("plan-list", on="2026-11-10")
        listing_queries = [sql for sql in queries if sql.startswith("SELECT id,title,start_on")]
        self.assertEqual(len(listing_queries), 2)
        with closing(sqlite3.connect(self.store.path)) as con:
            for query in listing_queries:
                explain = " ".join(str(row[3]) for row in con.execute("EXPLAIN QUERY PLAN " + query))
                self.assertIn("plans_listing", explain)
                self.assertNotIn("USE TEMP B-TREE", explain)

    def test_existing_store_gains_missing_listing_index_without_data_loss(self):
        saved = self.save()
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DROP INDEX IF EXISTS plans_listing")
            con.commit()
        self.assertEqual(self.call("plan-get", id=saved["id"]), saved)
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertTrue(con.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='plans_listing'").fetchone())

    def test_stale_revision_and_missing_list_do_not_overwrite_plan(self):
        original = self.save()
        req = self.update(original)
        updated = self.save(req)
        stale = self.update(original, key="stale-writer")
        with self.assertRaisesRegex(StoreError, "plan_revision_conflict"):
            self.save(stale)
        invalid = self.update(updated, key="missing-list")
        del invalid["shopping_list"]
        with self.assertRaises(StoreError):
            self.save(invalid)
        self.assertEqual(self.call("plan-get", id=original["id"]), updated)

    def test_failed_receipt_rolls_back_both_plan_and_shopping_list(self):
        original = self.save()
        req = self.update(original)
        req["shopping_list"] = [{"item": "new item", "quantity": "5 whole"}]
        with patch.object(store_module.Store, "_record_plan_receipt", side_effect=sqlite3.OperationalError("synthetic failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.save(req)
        self.assertEqual(self.call("plan-get", id=original["id"]), original)
        self.assertEqual(self.save(req)["revision"], 2)

    def test_plan_notes_are_preserved_unless_explicitly_replaced(self):
        original = self.save()
        req = self.update(original)
        del req["notes"]
        updated = self.save(req)
        self.assertEqual(updated["notes"], original["notes"])
        req = self.update(updated, key="clear-notes")
        req["notes"] = ""
        self.assertEqual(self.save(req)["notes"], "")

    def test_invalid_nested_fields_dates_servings_and_duplicate_slots_rejected(self):
        mutations = [
            lambda r: r.update(meals=[]),
            lambda r: r["meals"][0].update(on="2026-02-30"),
            lambda r: r["meals"][0].update(servings=True),
            lambda r: r["meals"][0].update(servings=0),
            lambda r: r["meals"][0].update(details=""),
            lambda r: r["meals"][0].update(on="2026-09-01"),
            lambda r: r["meals"][0].update(invented="field"),
            lambda r: r["meals"].append(copy.deepcopy(r["meals"][0])),
            lambda r: r.update(shopping_list="buy rice"),
            lambda r: r["shopping_list"][0].update(quantity=1.5),
            lambda r: r["shopping_list"][0].update(item=""),
            lambda r: r["shopping_list"][0].update(invented="field"),
            lambda r: r.update(expected_revision=1),
            lambda r: r.update(notes=None),
            lambda r: r.update(id="missing", expected_revision=1),
        ]
        for mutate in mutations:
            req = self.plan_request()
            mutate(req)
            with self.subTest(req=req), self.assertRaises(StoreError):
                self.save(req)
        self.assertEqual(self.call("plan-list"), [])

    def test_unknown_plan_ids_and_invalid_revisions_do_not_create_records(self):
        for action in ("plan-get", "plan-remove"):
            with self.subTest(action=action), self.assertRaises(StoreError):
                self.call(action, **({"id": "unknown"} if action == "plan-get" else
                                    {"id": "unknown", "request_key": "remove-missing", "expected_revision": 1}))
        plan = self.save()
        for revision in (None, 0, True, "1"):
            req = self.update(plan, key="invalid-revision")
            req["expected_revision"] = revision
            with self.subTest(revision=revision), self.assertRaisesRegex(StoreError, "invalid_expected_revision"):
                self.save(req)

    def test_empty_shopping_list_is_explicit_and_quantities_are_not_interpreted(self):
        req = self.plan_request()
        req["shopping_list"] = []  # User explicitly already has everything needed.
        saved = self.save(req)
        self.assertEqual(saved["shopping_list"], [])
        req = self.update(saved)
        req["shopping_list"] = [{"item": "lemon", "quantity": "2 whole, plus zest to taste"}]
        self.assertEqual(self.save(req)["shopping_list"][0]["quantity"], "2 whole, plus zest to taste")

    def test_list_date_overlap_and_boundaries(self):
        plan = self.save()
        self.assertEqual(len(self.call("plan-list", on="2026-11-09")), 1)
        self.assertEqual(len(self.call("plan-list", on="2026-11-13")), 1)
        self.assertEqual(self.call("plan-list", on="2026-11-14"), [])
        self.assertEqual(self.call("plan-list", limit=1)[0]["id"], plan["id"])

    def test_delete_is_revision_checked_retryable_and_does_not_recreate_on_old_retry(self):
        req = self.plan_request()
        plan = self.save(req)
        with self.assertRaisesRegex(StoreError, "plan_revision_conflict"):
            self.call("plan-remove", id=plan["id"], expected_revision=2, request_key="bad-delete")
        deletion = {"action": "plan-remove", "id": plan["id"], "expected_revision": 1, "request_key": "delete-one"}
        one = self.store.handle(deletion)
        self.assertEqual(self.store.handle(deletion), one)
        self.assertEqual(self.save(req), plan)  # Historical receipt; no recreation.
        self.assertEqual(self.call("plan-list"), [])
        self.assertEqual(self.call("export")["plans"], [])
        with self.assertRaisesRegex(StoreError, "plan_not_found"):
            self.call("plan-get", id=plan["id"])

    def test_concurrent_updates_allow_only_one_writer_from_same_revision(self):
        plan = self.save()
        def writer(index):
            req = self.update(plan, key=f"writer-{index}")
            req["title"] = f"Synthetic writer {index}"
            p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                               input=json.dumps(req), encoding="utf-8", capture_output=True)
            return p.returncode, json.loads(p.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(writer, range(2)))
        self.assertEqual(sum(code == 0 for code, _ in outcomes), 1, outcomes)
        self.assertEqual([r["error"] for code, r in outcomes if code], ["plan_revision_conflict"])
        self.assertEqual(self.call("plan-get", id=plan["id"])["revision"], 2)

    def seed_schema_three(self):
        # Construct the previous schema by the existing synthetic v2 fixture + v3 DDL.
        import test_observances
        test_observances.ObservanceTests.seed_schema_two(self)
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("CREATE TABLE locale (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                        "country TEXT, region TEXT, timezone TEXT, holiday_mode TEXT NOT NULL, updated_at TEXT NOT NULL)")
            con.execute("INSERT INTO locale VALUES (1,'Synthetic country',NULL,NULL,'suggest','2026-01-01')")
            con.execute("CREATE TABLE observances (id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL, "
                        "schedule TEXT NOT NULL, rules TEXT NOT NULL, calendar TEXT NOT NULL, strictness TEXT NOT NULL, "
                        "active INTEGER NOT NULL, member_id TEXT REFERENCES members(id), notes TEXT NOT NULL, updated_at TEXT NOT NULL)")
            con.execute("INSERT INTO observances VALUES ('old-practice','Synthetic rule','fasting','Fridays',"
                        "'User-defined ingredients','','strict',1,'member-old','','2026-01-01')")
            con.execute("PRAGMA user_version = 3")
            con.commit()

    def test_schema_three_upgrade_preserves_every_existing_domain(self):
        self.seed_schema_three()
        exported = self.call("export")
        self.assertEqual(exported["schema_version"], 5)
        self.assertEqual(exported["plans"], [])
        self.assertEqual(exported["preferences"][0]["member_id"], "member-old")
        self.assertEqual(exported["recipes"][0]["content"], "Exact old content")
        self.assertTrue(exported["recipes"][0]["favorite"])
        self.assertEqual(exported["meals"][0]["id"], "meal-old")
        self.assertEqual(exported["household"]["observances"][0]["id"], "old-practice")
        self.assertEqual(exported["household"]["locale"]["country"], "Synthetic country")
        self.assertEqual(exported["household"]["onboarding"]["status"], "completed")

    def test_failed_plan_write_rolls_back_migration_and_receipt(self):
        self.seed_schema_three()
        with patch.object(store_module, "now", side_effect=RuntimeError("synthetic plan-write failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic plan-write failure"):
                self.save()
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertFalse(con.execute("SELECT name FROM sqlite_master WHERE name='plans'").fetchone())
            self.assertFalse(con.execute("SELECT name FROM sqlite_master WHERE name='plan_requests'").fetchone())
            self.assertEqual(con.execute("SELECT id FROM meals").fetchone()[0], "meal-old")
        self.assertEqual(self.call("plan-list"), [])
