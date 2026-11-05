"""Shared startup/adoption regressions; all profiles and installs are disposable."""
import concurrent.futures
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch, PropertyMock

from test_store import SCRIPT, Store, StoreError, store_module as module


class SharedProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meal-magic-discovery-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.target = self.base / "shared" / "data"
        self.native = self.base / "native" / "meal-magic.sqlite3"
        self.private = self.base / "private" / "meal-magic.sqlite3"
        self.paths = [self.native, self.private]
        self.addCleanup(patch.stopall)
        patch.object(module, "windows_legacy_paths", lambda: self.paths).start()
        patch.object(module, "legacy_view_redirected", return_value=False).start()

    def shared(self):
        store = Store(self.target)
        store.shared_windows = True  # Exercise Windows policy with synthetic adapters on every OS.
        return store

    def call(self, action="context", **fields):
        return self.shared().handle({"action": action, **fields})

    def seed(self, path, label=None):
        store = Store(path.parent)
        store.handle({"action": "context"})
        if label:
            store.handle({"action": "member-set", "label": label})
        return store

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_storage_info_is_read_only_before_first_use(self):
        self.seed(self.private, "Synthetic person")
        before = self.digest(self.private)
        info = self.call("storage-info")["result"]
        self.assertFalse(info["exists"])
        self.assertTrue(info["legacy_candidates"][0]["has_saved_state"])
        self.assertFalse(self.target.exists())
        self.assertEqual(self.digest(self.private), before)

    def test_adopts_populated_private_profile_over_empty_native_shell(self):
        empty = self.seed(self.native)
        empty.handle({"action": "onboarding-set", "status": "in_progress"})
        source = self.seed(self.private, "Synthetic household")
        source.handle({"action": "preference-set", "kind": "prefer", "target": "Synthetic rice"})
        before = {p: self.digest(p) for p in self.paths}
        reply = self.call()
        self.assertEqual(reply["result"], source.handle({"action": "context"})["result"])
        self.assertTrue(reply["storage"]["profile_id"])
        self.assertEqual(before, {p: self.digest(p) for p in self.paths})
        self.assertEqual(self.call()["storage"]["profile_id"], reply["storage"]["profile_id"])

    def test_two_meaningful_profiles_refuse_without_creating_database(self):
        self.seed(self.native, "Native synthetic member")
        self.seed(self.private, "Private synthetic member")
        before = {p: self.digest(p) for p in self.paths}
        with self.assertRaisesRegex(StoreError, "multiple_existing_profiles"):
            self.call()
        self.assertFalse((self.target / "meal-magic.sqlite3").exists())
        self.assertFalse((self.target / ".origins.json").exists())
        self.assertEqual(before, {p: self.digest(p) for p in self.paths})

    def test_identical_copies_do_not_create_false_conflict(self):
        self.seed(self.native, "Same synthetic member")
        self.private.parent.mkdir()
        self.private.write_bytes(self.native.read_bytes())
        self.assertEqual(len(self.call()["result"]["household"]["members"]), 1)

    def test_explicit_conflict_choice_is_remembered_without_overwriting_other_profiles(self):
        self.seed(self.native, "Native synthetic member")
        self.seed(self.private, "Selected synthetic member")
        before = {p: self.digest(p) for p in self.paths}
        reply = self.call("profile-select", database=str(self.private))
        self.assertTrue(reply["result"]["profile_id"])
        self.assertEqual(self.call()["result"]["household"]["members"][0]["label"], "Selected synthetic member")
        self.assertEqual(self.call("profile-select", database=str(self.private)), reply)
        with self.assertRaisesRegex(StoreError, "shared_profile_already_initialized"):
            self.call("profile-select", database=str(self.native))
        self.assertEqual(before, {p: self.digest(p) for p in self.paths})

    def test_incomplete_virtualized_view_requires_explicit_source_choice(self):
        self.seed(self.private, "Known synthetic member")
        with patch.object(module, "legacy_view_redirected", return_value=True):
            with self.assertRaisesRegex(StoreError, "profile_discovery_incomplete_choose_source"):
                self.call()
            self.assertFalse((self.target / "meal-magic.sqlite3").exists())
            info = self.call("storage-info")["result"]
            self.assertTrue(info["legacy_view_redirected"])
            self.assertEqual(info["legacy_candidates"][0]["counts"]["members"], 1)
            self.call("profile-select", database=str(self.private))
            self.assertEqual(len(self.call()["result"]["household"]["members"]), 1)

    @unittest.skipUnless(os.name == "nt", "Windows handle path aliases")
    def test_physical_source_identity_survives_different_host_aliases(self):
        self.seed(self.native, "Synthetic member")
        actual = module.physical_path(self.native)
        self.paths = [Path(actual)]
        first = self.call()
        self.paths = [self.native]
        self.assertEqual(self.call()["storage"]["profile_id"], first["storage"]["profile_id"])

    @unittest.skipUnless(os.name == "nt", "Windows virtualized source handles")
    def test_native_host_can_reopen_profile_selected_from_a_virtualized_alias(self):
        self.seed(self.native)
        self.seed(self.private, "Synthetic chosen household")
        self.paths = [self.native]
        original_handle_path = module.physical_path
        def virtualized_handle(path):
            return str(self.private) if path == self.native else original_handle_path(path)
        with patch.object(module, "physical_path", side_effect=virtualized_handle), \
                patch.object(module, "legacy_view_redirected", return_value=True):
            self.call("profile-select", database=str(self.private))
            first = self.call()
        # An unpackaged host sees the true empty native shell plus the same private source.
        self.paths = [self.native, self.private]
        second = self.call()
        self.assertEqual(first["storage"]["profile_id"], second["storage"]["profile_id"])
        self.assertEqual(second["result"]["household"]["members"][0]["label"], "Synthetic chosen household")

    def test_conflict_selection_cannot_read_an_arbitrary_path(self):
        self.seed(self.native, "Synthetic member")
        with self.assertRaisesRegex(StoreError, "profile_candidate_not_found"):
            self.call("profile-select", database=str(self.base / "unrelated.sqlite3"))
        self.assertFalse((self.target / "meal-magic.sqlite3").exists())

    def test_schema_one_is_upgraded_only_in_the_adopted_copy(self):
        self.native.parent.mkdir()
        with closing(sqlite3.connect(self.native)) as con:
            for statement in module.SCHEMA:
                con.execute(statement)
            con.execute("INSERT INTO preferences VALUES ('synthetic-old','prefer','Synthetic rice','','2026-11-05')")
            con.execute("PRAGMA user_version=1")
            con.commit()
        before = self.digest(self.native)
        self.assertEqual(self.call()["result"]["preferences"][0]["id"], "synthetic-old")
        self.assertEqual(self.digest(self.native), before)
        with closing(sqlite3.connect(self.target / "meal-magic.sqlite3")) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 7)

    def test_scan_failure_does_not_initialize_a_new_database(self):
        with patch.object(module, "windows_legacy_paths", side_effect=PermissionError("synthetic denied directory")):
            with self.assertRaises(PermissionError):
                self.call()
        self.assertFalse((self.target / "meal-magic.sqlite3").exists())

    def test_changed_shared_file_identity_is_not_silently_accepted(self):
        self.seed(self.native, "Synthetic member")
        self.call()
        target = self.target / "meal-magic.sqlite3"
        replacement = self.target / "replacement.sqlite3"
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
        with self.assertRaisesRegex(StoreError, "shared_profile_identity_changed"):
            self.call()

    def test_different_working_directories_share_the_windows_default(self):
        with patch.object(module.sys, "platform", "win32"), patch.object(Path, "home", return_value=self.base):
            with patch.dict(os.environ, {"MEAL_MAGIC_DATA_DIR": ""}):
                expected = self.base / ".meal-magic" / "data"
                self.assertEqual(module.default_data_dir(), expected)
                # Resolve against the OS user home, never the checkout or host install.
                with patch.object(module.os, "getcwd", return_value=str(self.base / "another-checkout")):
                    self.assertEqual(module.default_data_dir(), expected)

    def test_duplicate_physical_paths_are_deduplicated(self):
        self.seed(self.native, "Synthetic member")
        self.paths = [self.native, self.native]
        self.assertEqual(len(self.call("storage-info")["result"]["legacy_candidates"]), 1)
        self.assertEqual(len(self.call()["result"]["household"]["members"]), 1)

    @unittest.skipUnless(os.name == "nt", "Windows paths are case insensitive")
    def test_agent_path_casing_changes_do_not_look_like_a_new_profile(self):
        self.seed(self.native, "Synthetic member")
        first = self.call()
        self.paths = [Path(str(self.native).swapcase())]
        second = self.call()
        self.assertEqual(first["storage"]["profile_id"], second["storage"]["profile_id"])

    def test_retained_receipts_count_as_meaningful(self):
        source = self.seed(self.native)
        meal = source.handle({"action": "meal-log", "name": "Synthetic dinner", "kind": "eaten",
                              "occurred_on": "2026-11-05", "request_key": "retained"})["result"]
        source.handle({"action": "meal-remove", "id": meal["id"]})
        self.seed(self.private, "Other synthetic member")
        with self.assertRaisesRegex(StoreError, "multiple_existing_profiles"):
            self.call()

    def test_full_database_adoption_preserves_deleted_event_retry(self):
        source = self.seed(self.private, "Synthetic member")
        req = {"action": "meal-log", "name": "Synthetic dinner", "kind": "eaten",
               "occurred_on": "2026-11-05", "request_key": "original-key"}
        meal = source.handle(req)["result"]
        source.handle({"action": "meal-remove", "id": meal["id"]})
        self.call()
        self.assertEqual(self.shared().handle(req)["result"], meal)
        self.assertEqual(self.call("meal-list")["result"], [])

    def test_locale_and_completed_onboarding_are_not_empty(self):
        for action in ({"action": "locale-set", "country": "Synthetic country"},
                       {"action": "onboarding-set", "status": "completed"}):
            with self.subTest(action=action):
                source = self.seed(self.native)
                source.handle(action)
                self.seed(self.private, "Another synthetic member")
                with self.assertRaisesRegex(StoreError, "multiple_existing_profiles"):
                    self.call()

    def test_corrupt_foreign_and_future_schema_never_create_new_profile(self):
        self.native.parent.mkdir()
        for kind in ("corrupt", "foreign", "future"):
            with self.subTest(kind=kind):
                self.native.unlink(missing_ok=True)
                if kind == "corrupt":
                    self.native.write_bytes(b"not a SQLite database")
                else:
                    with closing(sqlite3.connect(self.native)) as con:
                        con.execute("CREATE TABLE foreign_table(value)")
                        con.execute("PRAGMA user_version=" + ("99" if kind == "future" else "7"))
                        con.commit()
                before = self.digest(self.native)
                with self.assertRaises((StoreError, sqlite3.Error)):
                    self.call()
                self.assertEqual(self.digest(self.native), before)
                self.assertFalse((self.target / "meal-magic.sqlite3").exists())

    def test_source_changed_by_old_agent_after_adoption_is_reported(self):
        old = self.seed(self.private, "Synthetic member")
        self.call()
        old.handle({"action": "preference-set", "kind": "avoid", "target": "Synthetic ingredient"})
        canonical = self.target / "meal-magic.sqlite3"
        before = self.digest(canonical)
        with self.assertRaisesRegex(StoreError, "legacy_profile_changed_after_adoption"):
            self.call()
        self.assertEqual(self.digest(canonical), before)
        self.assertTrue(self.call("storage-info")["result"]["exists"])

    def test_new_populated_old_location_after_fresh_start_is_not_ignored(self):
        self.call()
        self.seed(self.native, "Late old-agent member")
        with self.assertRaisesRegex(StoreError, "legacy_profile_changed_after_adoption"):
            self.call()

    def test_existing_shared_database_is_never_overwritten(self):
        self.seed(self.target / "meal-magic.sqlite3", "Shared synthetic member")
        self.seed(self.private, "Different old member")
        before = self.digest(self.target / "meal-magic.sqlite3")
        with self.assertRaisesRegex(StoreError, "multiple_existing_profiles"):
            self.call()
        self.assertEqual(self.digest(self.target / "meal-magic.sqlite3"), before)

    def test_failed_publication_can_retry_without_losing_sources(self):
        self.seed(self.private, "Synthetic member")
        before = self.digest(self.private)
        with patch.object(module.os, "link", side_effect=OSError("simulated publication failure")):
            with self.assertRaises(OSError):
                self.call()
        self.assertFalse((self.target / "meal-magic.sqlite3").exists())
        self.assertEqual(self.digest(self.private), before)
        self.assertEqual(len(self.call()["result"]["household"]["members"]), 1)

    def test_missing_previously_ready_database_is_never_recreated_from_stale_sources(self):
        self.seed(self.private, "Synthetic member")
        self.call()
        self.call("preference-set", kind="prefer", target="New shared-only preference")
        target = self.target / "meal-magic.sqlite3"
        target.rename(self.target / "owner-moved-database.sqlite3")
        with self.assertRaisesRegex(StoreError, "shared_profile_missing"):
            self.call()
        self.assertFalse(target.exists())

    def test_staging_failure_does_not_publish_or_change_legacy_database(self):
        self.seed(self.private, "Synthetic member")
        before = self.digest(self.private)
        original = Store._connect
        def fail_staging(store):
            if store.data_dir.name.startswith(".meal-magic-adopt-"):
                raise sqlite3.OperationalError("simulated migration failure")
            return original(store)
        with patch.object(Store, "_connect", fail_staging):
            with self.assertRaises(sqlite3.Error):
                self.call()
        self.assertFalse((self.target / "meal-magic.sqlite3").exists())
        self.assertFalse((self.target / ".origins.json").exists())
        self.assertEqual(self.digest(self.private), before)

    def test_malformed_origin_metadata_is_not_repaired_or_overwritten(self):
        self.call()
        marker = self.target / ".origins.json"
        marker.write_text('[]')
        for action in ("context", "storage-info"):
            with self.assertRaisesRegex(StoreError, "invalid_profile_origins"):
                self.call(action)
        self.assertEqual(marker.read_text(), '[]')

    def test_interrupted_ready_marker_is_recovered_before_any_requested_write(self):
        self.seed(self.private, "Synthetic member")
        real_write = module.write_origins
        def fail_ready(marker, data):
            if data["state"] == "ready":
                raise OSError("simulated interruption after publication")
            real_write(marker, data)
        with patch.object(module, "write_origins", side_effect=fail_ready):
            with self.assertRaises(OSError):
                self.call("preference-set", kind="prefer", target="Must not be written yet")
        marker = self.target / ".origins.json"
        self.assertEqual(json.loads(marker.read_text())["state"], "publishing")
        reply = self.call()
        self.assertEqual(reply["result"]["preferences"], [])
        self.assertEqual(json.loads(marker.read_text())["state"], "ready")

    def test_source_links_are_refused_without_touching_their_targets(self):
        self.seed(self.private, "Synthetic member")
        self.native.parent.mkdir()
        try:
            self.native.symlink_to(self.private)
        except OSError:
            self.skipTest("Host does not allow creating a symlink")
        before = self.digest(self.private)
        with self.assertRaisesRegex(StoreError, "redirected_profile_path"):
            self.call()
        self.assertEqual(self.digest(self.private), before)

    def test_origin_links_are_refused(self):
        self.target.mkdir(parents=True)
        external = self.base / "synthetic-external.json"
        external.write_text('{}')
        try:
            (self.target / ".origins.json").symlink_to(external)
        except OSError:
            self.skipTest("Host does not allow creating a symlink")
        with self.assertRaisesRegex(StoreError, "redirected_profile_path"):
            self.call()
        self.assertEqual(external.read_text(), '{}')

    def test_process_exit_releases_startup_lock_without_manual_cleanup(self):
        program = """
import importlib.util,os,pathlib,sys
s=importlib.util.spec_from_file_location('fixture_store',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with m.profile_lock(pathlib.Path(sys.argv[2])): os._exit(0)
"""
        run = subprocess.run([sys.executable, "-c", program, str(SCRIPT), str(self.target)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.call()["result"]["household"]["members"], [])

    def test_external_target_creation_race_is_never_accepted_as_adopted_data(self):
        self.seed(self.private, "Synthetic member")
        def competing_writer(source, target):
            target.write_bytes(b"unexpected external file")
            raise FileExistsError("simulated competing explicit-path caller")
        with patch.object(module.os, "link", side_effect=competing_writer):
            with self.assertRaises(FileExistsError):
                self.call()
        with self.assertRaises((StoreError, sqlite3.Error)):
            self.call()
        self.assertEqual((self.target / "meal-magic.sqlite3").read_bytes(), b"unexpected external file")

    def test_marker_cannot_authorize_arbitrary_source_reads(self):
        self.call()
        marker = self.target / ".origins.json"
        record = json.loads(marker.read_text())
        record["sources"][str(self.base / "unrelated-private.sqlite3")] = "0" * 64
        marker.write_text(json.dumps(record))
        self.assertEqual(self.call()["result"]["household"]["members"], [])
        self.assertFalse((self.base / "unrelated-private.sqlite3").exists())

    def test_explicit_directory_and_environment_override_do_not_scan_legacy_profiles(self):
        with patch.object(module, "windows_legacy_paths", side_effect=AssertionError("unexpected discovery")):
            Store(self.target).handle({"action": "context"})
            with patch.dict(os.environ, {"MEAL_MAGIC_DATA_DIR": str(self.base / "override")}):
                self.assertFalse(Store().shared_windows)
                Store().handle({"action": "context"})

    def test_invalid_action_does_not_create_startup_directory(self):
        with self.assertRaisesRegex(StoreError, "unknown_fields"):
            self.call("context", unknown=True)
        self.assertFalse(self.target.exists())

    def test_wal_committed_rows_are_preserved(self):
        source = self.seed(self.private)
        with closing(sqlite3.connect(self.private)) as wal:
            wal.execute("PRAGMA journal_mode=WAL")
            wal.execute("BEGIN")
            wal.execute("SELECT * FROM members").fetchall()
            source.handle({"action": "member-set", "label": "Committed WAL synthetic member"})
            self.assertTrue(Path(str(self.private) + "-wal").exists())
            self.assertEqual(self.call()["result"]["household"]["members"][0]["label"],
                             "Committed WAL synthetic member")

    def test_parallel_process_startup_adopts_once_and_keeps_all_writes(self):
        self.seed(self.private, "Original synthetic member")
        program = """
import importlib.util,json,pathlib,sys
s=importlib.util.spec_from_file_location('fixture_store',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.windows_legacy_paths=lambda:[pathlib.Path(sys.argv[3])]
m.legacy_view_redirected=lambda:False
store=m.Store(pathlib.Path(sys.argv[2]));store.shared_windows=True
print(json.dumps(store.handle({'action':'member-set','label':sys.argv[4]})))
"""
        def run(index):
            return subprocess.run([sys.executable, "-c", program, str(SCRIPT), str(self.target),
                                   str(self.private), "Synthetic parallel " + str(index)],
                                  capture_output=True, text=True, encoding="utf-8")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(4)))
        self.assertTrue(all(r.returncode == 0 for r in results), [(r.stdout, r.stderr) for r in results])
        self.assertEqual(len(self.call()["result"]["household"]["members"]), 5)

    @unittest.skipUnless(os.name == "nt", "Windows native-volume and MSIX path adapter")
    def test_volume_namespace_is_not_treated_as_a_filesystem_ancestor_on_python_310(self):
        native = module.native_windows_path(self.base)
        legacy_parents = (*native.parents, Path("\\\\?\\"))
        with patch.object(type(native), "parents", new_callable=PropertyMock, return_value=legacy_parents):
            self.assertEqual(module.checked_path(native), native)

    @unittest.skipUnless(os.name == "nt", "Windows native-volume and MSIX path adapter")
    def test_windows_native_discovery_only_visits_exact_meal_magic_paths(self):
        local = self.base / "synthetic-local-appdata"
        expected = local / "Packages" / "Synthetic.Package" / "LocalCache" / "Local" / "MealMagic"
        self.seed(expected / "meal-magic.sqlite3", "Synthetic packaged member")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), patch.object(Path, "home", return_value=self.base / "synthetic-home"):
            # Undo only the fixture adapter, never use the real user's AppData.
            from importlib.util import module_from_spec, spec_from_file_location
            spec = spec_from_file_location("native_fixture", SCRIPT)
            real = module_from_spec(spec)
            spec.loader.exec_module(real)
            candidates = real.windows_legacy_paths()
            existing = [p for p in candidates if p.exists()]
            self.assertEqual(len(existing), 1)
            self.assertTrue(os.path.samefile(existing[0], expected / "meal-magic.sqlite3"))
            snapshot, meaningful, fingerprint = real.profile_snapshot(existing[0])
            snapshot.close()
            self.assertTrue(meaningful)

    @unittest.skipUnless(os.name == "nt", "Requires Windows MSIX AppData redirection")
    def test_actual_msix_overlay_cannot_hide_a_second_synthetic_profile(self):
        # Create only uniquely named disposable fixtures, never a real MealMagic directory.
        local = Path(os.environ["LOCALAPPDATA"])
        with tempfile.NamedTemporaryFile(prefix="meal-magic-msix-location-", dir=local,
                                         delete=False) as marker:
            marker_path = Path(marker.name)
        fixture_name = "meal-magic-msix-fixture-" + uuid.uuid4().hex + ".sqlite3"
        native = private = None
        try:
            native_parent = module.native_windows_path(local)
            private_parent = Path(module.physical_path(marker_path)).parent
            if os.path.samefile(native_parent, private_parent):
                self.skipTest("This process has no MSIX AppData overlay")
            self.seed(self.native, "Synthetic native fixture")
            self.seed(self.private, "Synthetic private fixture")
            native = native_parent / fixture_name
            private = private_parent / fixture_name
            native.write_bytes(self.native.read_bytes())
            if private.exists() and os.path.samefile(native, private):
                # The volume alias is itself redirected: one physical fixture, not
                # two profiles. Do not overwrite it with the second fixture payload.
                self.paths = [native, private]
                with patch.object(module, "legacy_view_redirected", return_value=True):
                    with self.assertRaisesRegex(StoreError, "profile_discovery_incomplete_choose_source"):
                        self.call()
                    info = self.call("storage-info")["result"]
                    self.assertEqual(len(info["legacy_candidates"]), 1)
                    self.call("profile-select", database=info["legacy_candidates"][0]["database"])
                    self.assertEqual(self.call()["result"]["household"]["members"][0]["label"],
                                     "Synthetic native fixture")
                return
            # A distinct name avoids creating a new shadow that would hide the
            # first fixture after its physical path was checked.
            private = private_parent / ("private-" + fixture_name)
            private.write_bytes(self.private.read_bytes())
            self.assertFalse(os.path.samefile(native, private))
            self.assertNotEqual(module.profile_key(Path(module.physical_path(native))),
                                module.profile_key(Path(module.physical_path(private))))
            self.assertNotEqual(self.digest(native), self.digest(private))
            self.paths = [native, private]
            with self.assertRaisesRegex(StoreError, "multiple_existing_profiles"):
                self.call()
            self.assertFalse((self.target / "meal-magic.sqlite3").exists())
        finally:
            for fixture in (native, private):
                if fixture is not None:
                    if fixture.name not in (fixture_name, "private-" + fixture_name):
                        raise AssertionError("Unexpected synthetic cleanup target")
                    fixture.unlink(missing_ok=True)
            marker_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
