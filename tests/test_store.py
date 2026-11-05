"""Behavioral persistence tests: temporary synthetic data only, no model calls."""
import concurrent.futures
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/meal-magic/scripts/meal_store.py"
spec = importlib.util.spec_from_file_location("meal_store", SCRIPT)
store_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store_module)
Store, StoreError = store_module.Store, store_module.StoreError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meal-magic-test-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name).resolve() / "data"
        self.store = Store(self.data)

    def call(self, action, **fields):
        return self.store.handle({"action": action, **fields})["result"]

    def save(self, key="recipe-one", name="Synthetic lentil soup", content="Lentils, water, lemon. Simmer until tender."):
        return self.call("recipe-save", name=name, content=content, request_key=key)

    def log(self, key="event-one", **overrides):
        req = {"name": "Synthetic soup", "kind": "cooked", "occurred_on": "2026-11-04", "request_key": key}
        req.update(overrides)
        return self.call("meal-log", **req)

    def test_empty_context(self):
        context = self.call("context")
        self.assertEqual(context["preferences"], [])
        self.assertEqual(context["recent_meals"], [])
        self.assertEqual(context["household"]["members"], [])
        self.assertEqual(context["household"]["onboarding"]["status"], "pending")

    def test_preferences_survive_new_process_and_can_be_corrected_and_forgotten(self):
        pref = self.call("preference-set", kind="forbid", target="μανιτάρια", notes="Synthetic exclusion")
        self.call("preference-set", kind="prefer", target="chickpeas")
        self.call("preference-set", kind="allergy", target="peanuts")
        self.call("preference-set", kind="diet", target="vegetarian")
        run = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                             input=json.dumps({"action": "context"}), encoding="utf-8", capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(json.loads(run.stdout)["result"]["preferences"]), 4)
        changed = self.call("preference-set", id=pref["id"], kind="avoid", target="μανιτάρια", notes="Corrected by user")
        self.assertEqual(changed["id"], pref["id"])
        self.call("preference-remove", id=pref["id"])
        self.assertEqual(len(self.call("context")["preferences"]), 3)

    def test_repeated_structured_preference_is_idempotent(self):
        one = self.call("preference-set", kind="prefer", target="rice")
        two = self.call("preference-set", kind="prefer", target="rice")
        self.assertEqual(one["id"], two["id"])
        self.assertEqual(len(self.call("context")["preferences"]), 1)

    def test_recipe_versions_and_exact_unicode_retrieval(self):
        content = "\nΣυνθετική συνταγή\nΥλικά: ρύζι και λεμόνι.\n1. Βράσε το ρύζι.\n"
        one = self.save(content=content)
        two = self.save(key="recipe-two", content="Another version")
        self.assertNotEqual(one["id"], two["id"])
        self.assertEqual(self.call("recipe-get", id=one["id"])["content"], content)

    def test_search_content_tags_accents_case_and_favorites(self):
        one = self.call("recipe-save", name="Συνθετικό ρύζι", content="Λεμόνι και ρεβίθια.", tags=["quick"], request_key="r")
        self.save()
        self.assertEqual(self.call("recipe-search", query="ΡΥΖΙ λεμονι quick")[0]["id"], one["id"])
        self.assertEqual(self.call("recipe-search", favorites_only=True), [])
        self.call("recipe-favorite", id=one["id"])
        self.assertEqual(len(self.call("recipe-search", favorites_only=True)), 1)
        self.call("recipe-favorite", id=one["id"], favorite=False)
        self.assertEqual(self.call("recipe-search", favorites_only=True), [])

    def test_recipe_operations_and_preferences_do_not_log_meals(self):
        recipe = self.save()
        self.call("recipe-get", id=recipe["id"])
        self.call("recipe-favorite", id=recipe["id"])
        self.call("recipe-search", query="lentil")
        self.call("preference-set", kind="avoid", target="mushrooms")
        self.assertEqual(self.call("meal-list"), [])

    def test_save_retry_and_changed_payload_conflict(self):
        one, two = self.save(), self.save()
        self.assertEqual(one["id"], two["id"])
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.save(content="Changed on retry")
        self.assertEqual(len(self.call("recipe-search")), 1)

    def test_cooked_eaten_repeat_meals_and_retry_are_separate(self):
        cooked = self.log()
        self.assertEqual(self.log()["id"], cooked["id"])
        eaten = self.log(key="event-two", kind="eaten")
        repeat = self.log(key="event-three", kind="eaten")
        self.assertNotEqual(eaten["id"], repeat["id"])
        self.assertEqual(len(self.call("meal-list")), 3)
        self.assertEqual(len(self.call("meal-list", kind="cooked")), 1)
        self.assertEqual(len(self.call("meal-list", kind="eaten")), 2)
        self.call("meal-remove", id=repeat["id"])
        self.assertEqual(len(self.call("meal-list")), 2)

    def test_log_retry_changed_payload_fails(self):
        self.log()
        with self.assertRaisesRegex(StoreError, "request_key_conflict"):
            self.log(kind="eaten")
        self.assertEqual(len(self.call("meal-list")), 1)

    def test_recipe_link_integrity(self):
        with self.assertRaisesRegex(StoreError, "recipe_not_found"):
            self.log(recipe_id="missing")
        self.assertEqual(self.call("meal-list"), [])
        recipe = self.save()
        self.assertEqual(self.log(recipe_id=recipe["id"])["recipe_id"], recipe["id"])

    def test_plans_and_suggestions_rejected_as_actual_events(self):
        for kind in ("planned", "suggested", "favorite"):
            with self.subTest(kind=kind), self.assertRaisesRegex(StoreError, "invalid_meal_kind"):
                self.log(kind=kind)
        self.assertEqual(self.call("meal-list"), [])

    def test_invalid_fields_dates_booleans_and_missing_ids_fail(self):
        bad = [
            {"action": "recipe-favorite", "id": "x", "favorite": "false"},
            {"action": "context", "limit": True},
            {"action": "context", "limit": 101},
            {"action": "context", "unknown": "silently ignored?"},
            {"action": "preference-set", "kind": "maybe", "target": "rice"},
            {"action": "preference-set", "kind": "avoid", "target": "rice", "id": "missing"},
            {"action": "recipe-save", "name": "x", "content": "x", "request_key": "x", "tags": "wrong"},
            {"action": "recipe-get", "id": "missing"},
            {"action": "meal-remove", "id": "missing"},
            {"action": "guess-intent", "text": "I ate rice"},
        ]
        for req in bad:
            with self.subTest(req=req), self.assertRaises(StoreError):
                self.store.handle(req)
        for value in ("2026-02-30", "yesterday", "20261104", "2026-11-04T12:00"):
            with self.subTest(value=value), self.assertRaisesRegex(StoreError, "invalid_occurred_on"):
                self.log(occurred_on=value)

    def test_history_not_pruned_and_sorted_by_occurrence(self):
        for i in range(35):
            self.log(key=f"meal-{i}", occurred_on="2026-10-01")
        self.log(key="newer", occurred_on="2026-11-01")
        self.assertEqual(len(self.call("meal-list")), 20)
        self.assertEqual(self.call("meal-list")[0]["occurred_on"], "2026-11-01")
        self.assertEqual(len(self.call("export")["meals"]), 36)

    def test_corrupt_database_is_not_overwritten(self):
        self.data.mkdir()
        self.store.path.write_bytes(b"synthetic invalid SQLite")
        before = self.store.path.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            self.call("context")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_unknown_schema_and_foreign_database_refused(self):
        self.call("context")
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("PRAGMA user_version = 99")
        with self.assertRaisesRegex(StoreError, "unsupported_schema_version"):
            self.call("context")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 99)
        other = Store(Path(self.tmp.name) / "foreign")
        other.data_dir.mkdir()
        with closing(sqlite3.connect(other.path)) as con:
            con.execute("CREATE TABLE unrelated (value TEXT)")
        with self.assertRaisesRegex(StoreError, "unrecognized_database"):
            other.handle({"action": "context"})

    def test_concurrent_processes_and_retry_do_not_lose_writes(self):
        def run(i):
            req = {"action": "meal-log", "name": "Synthetic rice", "kind": "eaten",
                   "occurred_on": "2026-11-04", "request_key": f"parallel-{i % 4}"}
            p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                               input=json.dumps(req), encoding="utf-8", capture_output=True)
            return p.returncode, p.stdout
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, range(8)))
        self.assertTrue(all(code == 0 for code, _ in results), results)
        self.assertEqual(len(self.call("meal-list")), 4)

    def test_data_directory_precedence_and_install_separation(self):
        with patch.dict(os.environ, {"MEAL_MAGIC_DATA_DIR": str(self.data)}):
            self.assertEqual(Store().data_dir, self.data)
            explicit = Path(self.tmp.name).resolve() / "other"
            self.assertEqual(Store(explicit).data_dir, explicit)
        with self.assertRaisesRegex(StoreError, "data_directory_inside_skill"):
            Store(SCRIPT.parents[1] / "private-data")

    def test_cli_unicode_file_errors_and_nonzero_exit(self):
        request = Path(self.tmp.name) / "request.json"
        request.write_text(json.dumps({"action": "preference-set", "kind": "prefer", "target": "ρεβίθια"}, ensure_ascii=False), encoding="utf-8-sig")
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data), "--request-file", str(request)],
                           encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["result"]["target"], "ρεβίθια")
        for raw in ("{", "[]", '{"action":"missing"}'):
            p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                               input=raw, encoding="utf-8", capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(json.loads(p.stdout)["ok"])
        self.assertFalse((SCRIPT.parents[1] / "meal-magic.sqlite3").exists())

    def test_read_failure_has_explicit_cli_error(self):
        self.data.write_text("not a directory", encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.data)],
                           input='{"action":"context"}', encoding="utf-8", capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(json.loads(p.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
