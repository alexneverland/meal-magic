"""Comprehensive tests for Meal Magic v0.7.0 features, migrations, and invariants."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/meal-magic/scripts"))
sys.path.insert(0, str(ROOT / "tools"))
import meal_store
import verify_scenarios


class V070Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meal-magic-v070-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.store = meal_store.Store(self.data)

    def call(self, action, **fields):
        return self.store.handle({"action": action, **fields})["result"]

    def test_recipe_update_remove_and_meal_history_preservation(self):
        member = self.call("member-set", label="Synthetic diner")
        rec = self.call(
            "recipe-save",
            request_key="r-save-1",
            name="Φακές σούπα",
            content="Υλικά: φακές, καρότο, κρεμμύδι, δάφνη.",
            tags=["όσπρια", "σούπα"],
            source="generated",
        )
        meal = self.call(
            "meal-log",
            request_key="m-log-1",
            kind="eaten",
            name="Φακές σούπα",
            occurred_on="2026-11-10",
            recipe_id=rec["id"],
            member_ids=[member["id"]],
        )
        self.assertEqual(meal["recipe_id"], rec["id"])

        # Partial update + idempotent retry + conflict
        updated = self.call(
            "recipe-update",
            id=rec["id"],
            request_key="r-upd-1",
            name="Φακές σούπα λεμονάτη",
            tags=["όσπρια", "λεμόνι"],
            favorite=True,
        )
        self.assertEqual(updated["name"], "Φακές σούπα λεμονάτη")
        self.assertTrue(updated["favorite"])
        self.assertEqual(
            self.call(
                "recipe-update",
                id=rec["id"],
                request_key="r-upd-1",
                name="Φακές σούπα λεμονάτη",
                tags=["όσπρια", "λεμόνι"],
                favorite=True,
            ),
            updated,
        )
        with self.assertRaisesRegex(meal_store.StoreError, "request_key_conflict"):
            self.call("recipe-update", id=rec["id"], request_key="r-upd-1", name="Different")
        with self.assertRaisesRegex(meal_store.StoreError, "recipe_update_requires_fields"):
            self.call("recipe-update", id=rec["id"], request_key="r-upd-empty")

        # Search reflects updated Greek text without accents
        found = self.call("recipe-search", query="φακες λεμονατη")
        self.assertEqual([r["id"] for r in found], [rec["id"]])

        # Delete requires confirm=True
        with self.assertRaisesRegex(meal_store.StoreError, "recipe_remove_requires_confirmation"):
            self.call("recipe-remove", id=rec["id"], request_key="r-del-no", confirm=False)

        removed = self.call("recipe-remove", id=rec["id"], request_key="r-del-1", confirm=True)
        self.assertEqual(removed, {"id": rec["id"], "removed": True, "unlinked_meals": 1})
        # Idempotent retry on recipe-remove
        self.assertEqual(
            self.call("recipe-remove", id=rec["id"], request_key="r-del-1", confirm=True),
            removed,
        )
        with self.assertRaisesRegex(meal_store.StoreError, "recipe_not_found"):
            self.call("recipe-get", id=rec["id"])

        # Meal survives with recipe_id=None, member_ids intact, and deleted_recipe snapshot
        meals = self.call("meal-list")
        self.assertEqual(len(meals), 1)
        self.assertIsNone(meals[0]["recipe_id"])
        self.assertEqual(meals[0]["member_ids"], [member["id"]])
        self.assertEqual(meals[0]["deleted_recipe"]["name"], "Φακές σούπα λεμονάτη")
        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_recipe_search_pagination_greek_and_ordering(self):
        ids = []
        for i in range(5):
            r = self.call(
                "recipe-save",
                request_key=f"sr-{i}",
                name=f"Κοτόπουλο {i}" if i % 2 == 0 else f"Chicken {i}",
                content="Λεμόνι και ρίγανη" if i % 2 == 0 else "Lemon and oregano",
                tags=["δείπνο"],
            )
            ids.append(r["id"])
        page1 = self.call("recipe-search", query="", limit=2, offset=0)
        page2 = self.call("recipe-search", query="", limit=2, offset=2)
        page3 = self.call("recipe-search", query="", limit=2, offset=4)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertEqual(len(page3), 1)
        seen = [r["id"] for r in page1 + page2 + page3]
        self.assertEqual(len(set(seen)), 5)
        gr = self.call("recipe-search", query="κοτοπουλο ριγανη")
        self.assertEqual(len(gr), 3)
        with self.assertRaisesRegex(meal_store.StoreError, "invalid_offset"):
            self.call("recipe-search", offset=-1)

    def test_meal_list_date_filters_pagination_and_idempotent_remove(self):
        member = self.call("member-set", label="Adult")
        dates = ["2026-10-25", "2026-11-01", "2026-11-05", "2026-11-10", "2026-11-12"]
        logged = []
        for idx, d in enumerate(dates):
            logged.append(
                self.call(
                    "meal-log",
                    request_key=f"ml-{idx}",
                    kind="eaten" if idx % 2 == 0 else "cooked",
                    name=f"Dish {idx}",
                    occurred_on=d,
                    member_ids=[member["id"]] if idx != 0 else [],
                )
            )
        ranged = self.call("meal-list", from_date="2026-11-01", to_date="2026-11-10")
        self.assertEqual([m["occurred_on"] for m in ranged], ["2026-11-10", "2026-11-05", "2026-11-01"])
        exact = self.call("meal-list", on="2026-11-05")
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["name"], "Dish 2")
        paged = self.call("meal-list", member_id=member["id"], limit=2, offset=2)
        self.assertEqual(len(paged), 2)

        with self.assertRaisesRegex(meal_store.StoreError, "invalid_date_range"):
            self.call("meal-list", from_date="2026-11-10", to_date="2026-11-01")
        with self.assertRaisesRegex(meal_store.StoreError, "invalid_date_filter"):
            self.call("meal-list", on="2026-11-05", from_date="2026-11-01")

        # Idempotent meal-remove with request_key
        rem = self.call("meal-remove", id=logged[0]["id"], request_key="mrem-1")
        self.assertEqual(rem, {"id": logged[0]["id"], "removed": True})
        self.assertEqual(self.call("meal-remove", id=logged[0]["id"], request_key="mrem-1"), rem)
        with self.assertRaisesRegex(meal_store.StoreError, "request_key_conflict"):
            self.call("meal-remove", id=logged[1]["id"], request_key="mrem-1")

    def test_meal_stats_accuracy_and_readonly(self):
        m1 = self.call("member-set", label="M1")
        rec = self.call("recipe-save", request_key="st-r1", name="Roast Chicken", content="Chicken and herbs.")
        self.call("meal-log", request_key="st-1", kind="cooked", name="Roast Chicken", occurred_on="2026-11-08", recipe_id=rec["id"])
        self.call("meal-log", request_key="st-2", kind="eaten", name="Roast Chicken", occurred_on="2026-11-09", recipe_id=rec["id"], member_ids=[m1["id"]])
        self.call("meal-log", request_key="st-3", kind="eaten", name="Roast Chicken", occurred_on="2026-11-11", recipe_id=rec["id"], member_ids=[m1["id"]])
        self.call("meal-log", request_key="st-4", kind="eaten", name="Lentil Soup", occurred_on="2026-11-12", member_ids=[m1["id"]])
        # Outside 7-day window ending 2026-11-13
        self.call("meal-log", request_key="st-5", kind="eaten", name="Old Pasta", occurred_on="2026-10-01", member_ids=[m1["id"]])

        # Delete recipe to verify deleted_recipe_names appears in stats
        self.call("recipe-remove", id=rec["id"], request_key="st-rdel", confirm=True)

        before = self.call("export")
        stats7 = self.call("meal-stats", days=7, on="2026-11-13")
        self.assertEqual(stats7["totals"], {
            "logged_events": 4,
            "cooked": 1,
            "eaten": 3,
            "distinct_dishes": 2,
            "distinct_cooked_dishes": 1,
            "distinct_eaten_dishes": 2,
        })
        self.assertEqual(stats7["variety"]["eaten_uniqueness_ratio"], 0.667)
        self.assertEqual(stats7["most_repeated_eaten"][0]["name"], "Roast Chicken")
        self.assertEqual(stats7["dishes"][0]["deleted_recipe_names"], ["Roast Chicken"])
        self.assertEqual(self.call("export"), before)

        # Member-scoped stats excludes cooked-only event without member_ids
        stats_m1 = self.call("meal-stats", days=7, on="2026-11-13", member_id=m1["id"])
        self.assertEqual(stats_m1["totals"]["cooked"], 0)
        self.assertEqual(stats_m1["totals"]["eaten"], 3)

    def test_selective_recipe_import_conflicts_and_rollback(self):
        r1 = self.call("recipe-save", request_key="ri-1", name="Salad", content="Tomatoes and cucumber.")
        # Dry run with duplicate ID + new recipe
        dry = self.call(
            "recipe-import",
            request_key="ri-dry",
            dry_run=True,
            on_conflict="skip",
            recipes=[r1, {"name": "Soup", "content": "Carrots and broth."}],
        )
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["skipped"], 1)
        self.assertEqual(dry["imported"], 1)
        self.assertEqual(len(self.call("recipe-search")), 1)

        # Fail on conflict by default, rolling back whole batch
        with self.assertRaisesRegex(meal_store.StoreError, "recipe_import_id_conflict"):
            self.call(
                "recipe-import",
                request_key="ri-fail",
                recipes=[{"name": "Temp", "content": "Temp"}, r1],
            )
        self.assertEqual(len(self.call("recipe-search")), 1)

        # Overwrite requires confirm_overwrite=True
        with self.assertRaisesRegex(meal_store.StoreError, "recipe_import_requires_confirmation"):
            self.call("recipe-import", request_key="ri-ow-no", on_conflict="overwrite", recipes=[r1])

        # new_id imports a copy with a fresh ID
        new_id_res = self.call(
            "recipe-import",
            request_key="ri-new",
            on_conflict="new_id",
            recipes=[{**r1, "content": "Tomatoes, cucumber, feta."}],
        )
        self.assertEqual(new_id_res["imported"], 1)
        self.assertEqual(len(new_id_res["renamed_ids"]), 1)
        self.assertEqual(len(self.call("recipe-search")), 2)

    def test_schema_seven_to_eight_migration_preserves_all_data(self):
        self.call("member-set", label="Tester")
        rec = self.call("recipe-save", request_key="mig-r1", name="Μουσακάς", content="Μελιτζάνες και κιμάς.")
        meal = self.call("meal-log", request_key="mig-m1", kind="eaten", name="Μουσακάς", occurred_on="2026-11-10", recipe_id=rec["id"])
        # Downgrade to schema 7 shape directly
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DROP TABLE recipe_requests")
            con.execute("ALTER TABLE recipes DROP COLUMN search_text")
            con.execute("ALTER TABLE meals DROP COLUMN recipe_snapshot")
            con.execute("PRAGMA user_version = 7")
            con.commit()
        found = self.call("recipe-search", query="μουσακας")
        self.assertEqual([r["id"] for r in found], [rec["id"]])
        self.call("recipe-remove", id=rec["id"], request_key="mig-del", confirm=True)
        meals = self.call("meal-list")
        self.assertEqual(meals[0]["id"], meal["id"])
        self.assertEqual(meals[0]["deleted_recipe"]["name"], "Μουσακάς")

    @unittest.skipUnless(os.name == "nt", "Windows shared-profile discovery")
    def test_windows_shared_profile_fast_path_and_invalidation(self):
        legacy_dir = Path(self.tmp.name) / "legacy"
        meal_store.Store(legacy_dir).handle({
            "action": "recipe-save",
            "request_key": "fp-1",
            "name": "Legacy Dish",
            "content": "Beans and rice.",
        })
        legacy_db = legacy_dir / "meal-magic.sqlite3"
        shared_dir = Path(self.tmp.name) / "shared" / ".meal-magic" / "data"
        with patch.object(meal_store, "windows_legacy_paths", return_value=[legacy_db]), \
             patch.object(meal_store, "default_data_dir", return_value=shared_dir):
            s = meal_store.Store()
            s.shared_windows = True
            s.handle({"action": "context"})
            origins = meal_store.read_origins(shared_dir / ".origins.json")
            self.assertIn("source_stats", origins)
            # Fast path should NOT call profile_snapshot on repeated reads
            with patch.object(meal_store, "profile_snapshot", side_effect=AssertionError("should use fast path")):
                ctx = s.handle({"action": "context"})
                self.assertEqual(ctx["ok"], True)
            # Modifying legacy DB must invalidate fast path and trigger conservative detection
            meal_store.Store(legacy_dir).handle({
                "action": "recipe-save",
                "request_key": "fp-2",
                "name": "Modified Legacy",
                "content": "Changed.",
            })
            with self.assertRaisesRegex(meal_store.StoreError, "legacy_profile_changed_after_adoption"):
                s.handle({"action": "context"})

    def test_scenario_harness_level1_passes(self):
        report = verify_scenarios.run_level1()
        self.assertEqual(report["failed"], 0, msg=json.dumps(report, indent=2))
        self.assertGreaterEqual(report["passed"], 7)

    def test_recipe_save_retry_after_recipe_remove_does_not_recreate(self):
        saved = self.call(
            "recipe-save",
            request_key="rs-once",
            name="Ephemeral Soup",
            content="Water and herbs.",
        )
        self.call("recipe-remove", id=saved["id"], request_key="rs-del", confirm=True)
        # Retrying the old save key must return the historical receipt, not recreate the recipe.
        replayed = self.call(
            "recipe-save",
            request_key="rs-once",
            name="Ephemeral Soup",
            content="Water and herbs.",
        )
        self.assertEqual(replayed["id"], saved["id"])
        self.assertEqual(self.call("recipe-search"), [])
        with self.assertRaisesRegex(meal_store.StoreError, "request_key_conflict"):
            self.call("recipe-save", request_key="rs-once", name="Different", content="Water and herbs.")

    def test_schema_seven_to_eight_rollback_preserves_original_database(self):
        member = self.call("member-set", label="Rollback tester")
        rec = self.call("recipe-save", request_key="rb-r1", name="Bean Stew", content="Beans and tomato.")
        meal = self.call(
            "meal-log",
            request_key="rb-m1",
            kind="eaten",
            name="Bean Stew",
            occurred_on="2026-11-10",
            recipe_id=rec["id"],
            member_ids=[member["id"]],
        )
        with closing(sqlite3.connect(self.store.path)) as con:
            con.execute("DROP TABLE recipe_requests")
            con.execute("ALTER TABLE recipes DROP COLUMN search_text")
            con.execute("ALTER TABLE meals DROP COLUMN recipe_snapshot")
            con.execute("PRAGMA user_version = 7")
            con.commit()

        # Inject a failure during v7->v8 migration after DDL changes have started.
        with patch.object(meal_store.Store, "_recipe_search_text", side_effect=RuntimeError("synthetic v8 failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic v8 failure"):
                self.call("context")

        with closing(sqlite3.connect(self.store.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recipe_requests'").fetchone())
            self.assertNotIn("search_text", {r[1] for r in con.execute("PRAGMA table_info(recipes)").fetchall()})
            self.assertNotIn("recipe_snapshot", {r[1] for r in con.execute("PRAGMA table_info(meals)").fetchall()})
            self.assertEqual(con.execute("SELECT count(*) FROM recipes").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM meals").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM meal_members").fetchone()[0], 1)

        # Next normal call upgrades cleanly to schema 8 and preserves everything.
        ctx = self.call("context")
        self.assertEqual(ctx["recent_meals"][0]["id"], meal["id"])
        self.assertEqual(ctx["recent_meals"][0]["member_ids"], [member["id"]])
        found = self.call("recipe-search", query="bean")
        self.assertEqual([r["id"] for r in found], [rec["id"]])

    @unittest.skipUnless(os.name == "nt", "Windows shared-profile discovery")
    def test_windows_wal_sidecar_change_invalidates_fast_path(self):
        legacy_dir = Path(self.tmp.name) / "legacy_wal"
        meal_store.Store(legacy_dir).handle({"action": "member-set", "label": "WAL Member"})
        legacy_db = legacy_dir / "meal-magic.sqlite3"
        shared_dir = Path(self.tmp.name) / "shared_wal" / ".meal-magic" / "data"
        with patch.object(meal_store, "windows_legacy_paths", return_value=[legacy_db]), \
             patch.object(meal_store, "default_data_dir", return_value=shared_dir):
            s = meal_store.Store()
            s.shared_windows = True
            s.handle({"action": "context"})
            # Simulate a WAL-mode write on the legacy DB while keeping the connection open so the WAL stays uncheckpointed.
            con = sqlite3.connect(legacy_db)
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA wal_autocheckpoint=0")
                con.execute("INSERT INTO preferences VALUES ('wal-p1','prefer','garlic','','2026-11-10',NULL)")
                con.commit()
                wal_path = legacy_db.with_name("meal-magic.sqlite3-wal")
                self.assertTrue(wal_path.exists() and wal_path.stat().st_size > 0)
                with self.assertRaisesRegex(meal_store.StoreError, "legacy_profile_changed_after_adoption"):
                    s.handle({"action": "context"})
            finally:
                con.close()

    def test_recipe_import_overwrite_and_idempotent_retry(self):
        rec = self.call("recipe-save", request_key="ow-1", name="Pasta", content="Old content.")
        meal = self.call("meal-log", request_key="ow-m1", kind="cooked", name="Pasta", occurred_on="2026-11-11", recipe_id=rec["id"])
        res = self.call(
            "recipe-import",
            request_key="ow-imp-1",
            on_conflict="overwrite",
            confirm_overwrite=True,
            recipes=[{**rec, "name": "Pasta v2", "content": "New content.", "tags": ["pasta"], "favorite": True}],
        )
        self.assertEqual(res["overwritten"], 1)
        self.assertEqual(res["imported"], 0)
        # Idempotent retry
        self.assertEqual(
            self.call(
                "recipe-import",
                request_key="ow-imp-1",
                on_conflict="overwrite",
                confirm_overwrite=True,
                recipes=[{**rec, "name": "Pasta v2", "content": "New content.", "tags": ["pasta"], "favorite": True}],
            ),
            res,
        )
        got = self.call("recipe-get", id=rec["id"])
        self.assertEqual(got["name"], "Pasta v2")
        self.assertTrue(got["favorite"])
        self.assertEqual(self.call("meal-list")[0]["recipe_id"], meal["recipe_id"])

        # Overwriting recipe A to "New Soup" and then importing recipe B with identical content
        # must report duplicate_matches accurately in both dry_run and actual import.
        batch = [
            {**rec, "name": "New Soup", "content": "Fresh broth.", "tags": []},
            {"name": "New Soup", "content": "Fresh broth.", "tags": []},
        ]
        dry_dup = self.call(
            "recipe-import",
            request_key="ow-dup-dry",
            dry_run=True,
            on_conflict="overwrite",
            confirm_overwrite=True,
            recipes=batch,
        )
        self.assertEqual(len(dry_dup["duplicate_matches"]), 1)
        self.assertEqual(dry_dup["duplicate_matches"][0]["existing_id"], rec["id"])
        real_dup = self.call(
            "recipe-import",
            request_key="ow-dup-real",
            on_conflict="overwrite",
            confirm_overwrite=True,
            recipes=batch,
        )
        self.assertEqual(real_dup["duplicate_matches"], dry_dup["duplicate_matches"])

    def test_recipe_import_empty_and_request_key_namespace(self):
        empty_res = self.call("recipe-import", request_key="shared-imp-k1", recipes=[])
        self.assertEqual(empty_res["imported"], 0)
        # Empty recipe-import must not mark the profile occupied or collide with full-profile import.
        snap = meal_store.Store(Path(self.tmp.name) / "src").handle({"action": "export"})["result"]
        imp_res = self.call("import", request_key="shared-imp-k1", data=snap)
        self.assertTrue(imp_res["imported"])
        # Reusing the same request_key for a subsequent recipe-import also stays isolated.
        rec_res = self.call(
            "recipe-import",
            request_key="shared-imp-k1",
            recipes=[{"name": "Isolated Soup", "content": "Water and herbs.", "tags": []}],
        )
        self.assertEqual(rec_res["imported"], 1)

    def test_read_origins_allows_negative_mtime_ns(self):
        origins_path = Path(self.tmp.name) / "origins_neg" / "origins.json"
        origins_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "profile_id": "a" * 32,
            "sources": {},
            "state": "ready",
            "database_identity": None,
            "selected_source": None,
            "source_stats": {
                "legacy": {
                    "dev": 1,
                    "ino": 2,
                    "size": 128,
                    "mtime_ns": -1000,
                    "wal_exists": False,
                    "wal_size": 0,
                    "wal_mtime_ns": -1,
                }
            },
        }
        meal_store.write_origins(origins_path, payload)
        self.assertEqual(meal_store.read_origins(origins_path), payload)

    def test_context_with_on_date_does_not_filter_recent_meals(self):
        logged = self.call("meal-log", request_key="ctx-m1", kind="eaten", name="Lentil Soup", occurred_on="2026-11-12")
        ctx = self.call("context", on="2026-11-13")
        self.assertEqual(ctx["date_context"]["on"], "2026-11-13")
        self.assertEqual([m["id"] for m in ctx["recent_meals"]], [logged["id"]])


if __name__ == "__main__":
    unittest.main()
