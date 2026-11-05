"""Actual meal membership, retry and migration tests with synthetic data only."""
from contextlib import closing
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_store import Store, StoreError, SCRIPT, store_module


class MealMemberTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meal-magic-members-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.store = Store(self.data)
        self.one = self.call("member-set", label="Synthetic adult")
        self.two = self.call("member-set", label="Synthetic child")

    def call(self, action, **fields):
        return self.store.handle({"action": action, **fields})["result"]

    def log(self, key="meal-one", **fields):
        request = {"kind": "eaten", "name": "Synthetic soup", "occurred_on": "2026-11-05",
                   "request_key": key}
        request.update(fields)
        return self.call("meal-log", **request)

    def legacy_profile(self):
        """Downgrade only this synthetic fixture to the actual schema-4 layout."""
        meal = self.log()
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DROP TABLE IF EXISTS import_requests")
            con.execute("DROP TABLE IF EXISTS meal_requests")
            con.execute("DROP TABLE IF EXISTS meal_members")
            payload = json.loads(con.execute("SELECT request_payload FROM meals").fetchone()[0])
            payload.pop("member_ids", None)
            con.execute("UPDATE meals SET request_payload=?", (json.dumps(payload),))
            con.execute("PRAGMA user_version=4")
            con.commit()
        meal.pop("member_ids", None)
        return meal

    def test_separate_dishes_and_cooked_eaten_members_are_independent(self):
        one = self.log(member_ids=[self.one["id"]], name="Synthetic special dish")
        two = self.log("family", member_ids=[self.two["id"]], name="Synthetic family dish")
        cooked = self.log("cooked", kind="cooked", member_ids=[self.one["id"], self.two["id"]])
        self.assertEqual(one["member_ids"], [self.one["id"]])
        self.assertEqual(two["member_ids"], [self.two["id"]])
        self.assertEqual(cooked["member_ids"], sorted([self.one["id"], self.two["id"]]))
        self.assertEqual([m["id"] for m in self.call("meal-list", kind="eaten", member_id=self.one["id"])],
                         [one["id"]])
        exported = self.call("export")
        self.assertEqual(exported["recipes"], [])
        self.assertEqual(exported["plans"], [])
        self.assertEqual(exported["preferences"], [])
        self.assertEqual(len(exported["meals"]), 3)
        self.assertEqual({meal["id"]: meal["member_ids"] for meal in exported["meals"]},
                         {one["id"]: [self.one["id"]], two["id"]: [self.two["id"]],
                          cooked["id"]: sorted([self.one["id"], self.two["id"]])})
        self.assertEqual({meal["id"]: meal["member_ids"] for meal in self.call("context")["recent_meals"]},
                         {meal["id"]: meal["member_ids"] for meal in exported["meals"]})

    def test_unspecified_membership_never_assigns_the_whole_household(self):
        unknown = self.log()
        self.assertEqual(unknown["member_ids"], [])
        self.assertEqual(self.call("meal-list", member_id=self.one["id"]), [])
        self.assertEqual(self.call("context")["recent_meals"], [unknown])
        self.assertEqual(self.log(member_ids=[]), unknown)

    def test_member_filter_precedes_limit_and_keeps_older_personal_history(self):
        older = self.log(member_ids=[self.one["id"]], occurred_on="2026-11-01")
        self.log("other", member_ids=[self.two["id"]])
        self.log("unknown")
        self.assertEqual(self.call("meal-list", member_id=self.one["id"], limit=1), [older])
        self.assertEqual(self.call("meal-list", member_id=self.one["id"], kind="cooked"), [])

    def test_member_order_does_not_change_retry_but_changed_membership_conflicts(self):
        ids = [self.one["id"], self.two["id"]]
        saved = self.log(member_ids=ids)
        self.assertEqual(self.log(member_ids=list(reversed(ids))), saved)
        for members in ([self.one["id"]], [], [self.two["id"]]):
            with self.subTest(members=members), self.assertRaisesRegex(StoreError, "request_key_conflict"):
                self.log(member_ids=members)
        self.assertEqual(self.call("meal-list"), [saved])

    def test_deleted_event_retry_returns_receipt_without_recreating_membership(self):
        saved = self.log(member_ids=[self.one["id"]])
        self.call("meal-remove", id=saved["id"])
        self.call("member-remove", id=self.one["id"])
        self.assertEqual(self.log(member_ids=[self.one["id"]]), saved)
        self.assertEqual(self.call("meal-list"), [])
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.log(member_ids=[self.one["id"]], name="Changed synthetic soup")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_members").fetchone()[0], 0)

    def test_schema_five_preview_backfills_durable_receipts_before_deletion(self):
        saved = self.log(member_ids=[self.one["id"]])
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DROP TABLE IF EXISTS import_requests")
            con.execute("DROP TABLE IF EXISTS meal_requests")
            con.execute("PRAGMA user_version=5")
            con.commit()
        self.call("meal-remove", id=saved["id"])
        self.assertEqual(self.log(member_ids=[self.one["id"]]), saved)
        self.assertEqual(self.call("meal-list", member_id=self.one["id"]), [])
        self.assertEqual(self.call("export")["schema_version"], 7)

    def test_receipt_failure_rolls_back_meal_and_member_links(self):
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON meal_requests "
                        "BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
            con.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.log(member_ids=[self.one["id"]])
        self.assertEqual(self.call("meal-list"), [])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_members").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_requests").fetchone()[0], 0)
            con.execute("DROP TRIGGER fail_receipt")
            con.commit()
        saved = self.log(member_ids=[self.one["id"]])
        self.assertEqual(self.call("meal-list"), [saved])

    def test_export_loads_memberships_in_one_query_for_large_history(self):
        for index in range(120):
            self.log(str(index), member_ids=[self.one["id"]] if index % 2 else [])
        statements = []
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            con.set_trace_callback(statements.append)
            return con
        with patch.object(store_module.sqlite3, "connect", side_effect=connect):
            result = self.call("export")
        self.assertEqual(len(result["meals"]), 120)
        self.assertEqual(sum(meal["member_ids"] == [self.one["id"]] for meal in result["meals"]), 60)
        listed = self.call("meal-list", limit=100)
        self.assertEqual(len(listed), 100)
        self.assertEqual(sum(meal["member_ids"] == [self.one["id"]] for meal in listed), 50)
        membership_reads = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")
                            and "meal_members" in sql]
        self.assertEqual(len(membership_reads), 1)

    def test_receipt_backfill_failure_preserves_schema_five_preview(self):
        saved = self.log(member_ids=[self.one["id"]])
        real_connect = sqlite3.connect
        with closing(real_connect(self.store.path)) as con:
            con.execute("DROP TABLE IF EXISTS import_requests")
            con.execute("DROP TABLE IF EXISTS meal_requests")
            con.execute("PRAGMA user_version=5")
            con.commit()
        def connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            con.set_authorizer(lambda action, name, *unused: sqlite3.SQLITE_DENY
                               if action == sqlite3.SQLITE_INSERT and name == "meal_requests" else sqlite3.SQLITE_OK)
            return con
        with patch.object(store_module.sqlite3, "connect", side_effect=connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.call("context")
        with closing(real_connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='meal_requests'").fetchone())
        self.assertEqual(self.call("meal-list"), [saved])

    def test_invalid_and_unknown_members_fail_without_partial_events(self):
        invalid = [None, "all", {}, True, [None], [True], [1], [""], [" "], ["x" * 201],
                   [self.one["id"], self.one["id"]], [self.one["id"], " " + self.one["id"] + " "],
                   [str(i) for i in range(101)]]
        for index, members in enumerate(invalid):
            with self.subTest(members=members), self.assertRaisesRegex(StoreError, "invalid_member_ids"):
                self.log(str(index), member_ids=members)
        with self.assertRaisesRegex(StoreError, "member_not_found"):
            self.log(member_ids=[self.one["id"], "missing"])
        self.assertEqual(self.call("meal-list"), [])

    def test_invalid_member_filters_do_not_silently_return_household_history(self):
        self.log()
        for member in (None, True, [], "", " ", "x" * 201):
            with self.subTest(member=member), self.assertRaisesRegex(StoreError, "invalid_member_id"):
                self.call("meal-list", member_id=member)
        with self.assertRaisesRegex(StoreError, "member_not_found"):
            self.call("meal-list", member_id="missing")

    def test_membership_persists_across_cli_process_restart(self):
        saved = self.log(member_ids=[self.one["id"]])
        request = {"action": "meal-list", "member_id": self.one["id"]}
        run = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                             input=json.dumps(request), encoding="utf-8", capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["result"], [saved])

    def test_concurrent_member_event_retries_create_one_event_and_one_link(self):
        request = {"action": "meal-log", "request_key": "parallel-member-event", "kind": "eaten",
                   "name": "Synthetic soup", "occurred_on": "2026-11-05", "member_ids": [self.one["id"]]}
        def invoke(_):
            run = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                                 input=json.dumps(request), encoding="utf-8", capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            return json.loads(run.stdout)["result"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(invoke, range(4)))
        self.assertEqual(len({meal["id"] for meal in results}), 1)
        self.assertEqual(self.call("meal-list", member_id=self.one["id"]), [results[0]])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_members").fetchone()[0], 1)

    def test_one_hundred_members_are_accepted_without_truncation(self):
        members = [self.one["id"], self.two["id"]]
        for index in range(98):
            members.append(self.call("member-set", label=f"Synthetic diner {index}")["id"])
        self.assertEqual(self.log(member_ids=members)["member_ids"], sorted(members))

    def test_linked_member_removal_refuses_and_event_removal_preserves_other_history(self):
        saved = self.log(member_ids=[self.one["id"], self.two["id"]])
        other = self.log("other", member_ids=[self.two["id"]])
        with self.assertRaisesRegex(StoreError, "member_has_meals"):
            self.call("member-remove", id=self.one["id"])
        self.call("meal-remove", id=saved["id"])
        self.call("member-remove", id=self.one["id"])
        self.assertEqual(self.call("meal-list"), [other])
        self.assertEqual(self.call("context")["household"]["members"], [self.two])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_members").fetchone()[0], 1)
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_relation_write_failure_rolls_back_event_and_all_links(self):
        self.call("context")
        fail_after_first = max(self.one["id"], self.two["id"])
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("CREATE TRIGGER fail_member BEFORE INSERT ON meal_members "
                        "WHEN NEW.member_id = '" + fail_after_first + "' "
                        "BEGIN SELECT RAISE(ABORT,'synthetic link failure'); END")
            con.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.log(member_ids=[self.one["id"], self.two["id"]])
        self.assertEqual(self.call("meal-list"), [])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meal_members").fetchone()[0], 0)
            con.execute("DROP TRIGGER fail_member")
            con.commit()
        self.assertEqual(len(self.log(member_ids=[self.one["id"], self.two["id"]])["member_ids"]), 2)

    def test_schema_four_upgrade_preserves_other_domains_and_legacy_retry(self):
        recipe = self.call("recipe-save", request_key="recipe", name="Synthetic rice", content="Exact text.")
        pref = self.call("preference-set", kind="avoid", target="synthetic mushrooms", member_id=self.one["id"])
        self.call("locale-set", country="Synthetic country", holiday_mode="off")
        self.call("onboarding-set", status="completed")
        self.call("observance-set", label="Synthetic practice", schedule="Fridays", rules="User supplied rule",
                  member_id=self.one["id"])
        plan = self.call("plan-save", request_key="plan", title="Synthetic plan",
                         meals=[{"on": "2026-11-06", "slot": "dinner", "name": "Synthetic rice",
                                 "servings": 1, "details": "Synthetic steps"}], shopping_list=[])
        before = self.call("export")
        legacy = self.legacy_profile()
        result = self.call("export")
        self.assertEqual(result["schema_version"], 7)
        self.assertEqual(result["recipes"], [recipe])
        self.assertEqual(result["preferences"], [pref])
        self.assertEqual(result["plans"], [plan])
        self.assertEqual(result["household"], before["household"])
        self.assertEqual(self.call("plan-save", request_key="plan", title="Synthetic plan",
                                  meals=plan["meals"], shopping_list=[]), plan)
        self.assertEqual(result["meals"], [{**legacy, "member_ids": []}])
        self.assertEqual(self.log(), {**legacy, "member_ids": []})
        self.assertEqual(self.log(member_ids=[]), {**legacy, "member_ids": []})
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.log(member_ids=[self.one["id"]])
        self.assertEqual(self.call("meal-list", member_id=self.one["id"]), [])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertNotIn("member_ids", json.loads(con.execute("SELECT request_payload FROM meals").fetchone()[0]))
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 7)

    def test_failed_write_rolls_back_schema_four_migration(self):
        legacy = self.legacy_profile()
        with self.assertRaises(StoreError):
            self.log("bad", member_ids=["missing"])
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='meal_members'").fetchone())
            self.assertEqual(con.execute("SELECT id FROM meals").fetchone()[0], legacy["id"])
        self.assertEqual(self.log()["id"], legacy["id"])

    def test_failed_schema_five_index_creation_rolls_back_new_relation(self):
        legacy = self.legacy_profile()
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            con.set_authorizer(lambda action, name, *unused:
                               sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_INDEX
                               and name == "meal_members_member" else sqlite3.SQLITE_OK)
            return con
        with patch.object(store_module.sqlite3, "connect", side_effect=connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.call("context")
        with closing(real_connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='meal_members'").fetchone())
            self.assertEqual(con.execute("SELECT id FROM meals").fetchone()[0], legacy["id"])
        self.assertEqual(self.log()["id"], legacy["id"])


if __name__ == "__main__":
    unittest.main()
