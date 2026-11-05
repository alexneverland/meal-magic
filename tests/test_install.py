"""Lifecycle checks use temporary agent homes/projects and synthetic data only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manage_skill", ROOT / "tools/manage_skill.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="meal-magic-install-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()

    def test_user_locations_are_agent_specific(self):
        expected = {"codex": ".agents/skills/meal-magic", "claude-code": ".claude/skills/meal-magic",
                    "antigravity": ".gemini/config/skills/meal-magic"}
        for agent, rel in expected.items():
            self.assertEqual(installer.destination(agent, "user", None, None, home=self.base), self.base / rel)

    def test_full_lifecycle_for_each_agent_preserves_data(self):
        for agent in ("codex", "claude-code", "antigravity", "custom"):
            with self.subTest(agent=agent):
                project = self.base / agent
                project.mkdir()
                target = (installer.destination(agent, "project", project, None) if agent != "custom"
                          else installer.destination(agent, "user", None, project / "skills/meal-magic"))
                data = project / "private-user-data"
                installer.manage("install", target)
                script = target / "scripts/meal_store.py"
                req = {"action": "preference-set", "kind": "forbid", "target": "synthetic mushrooms"}
                run = subprocess.run([sys.executable, str(script), "--data-dir", str(data)],
                                     input=json.dumps(req), encoding="utf-8", capture_output=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                before = (data / "meal-magic.sqlite3").read_bytes()
                installer.manage("update", target)
                self.assertEqual((data / "meal-magic.sqlite3").read_bytes(), before)
                ctx = subprocess.run([sys.executable, str(script), "--data-dir", str(data)],
                                     input='{"action":"context"}', encoding="utf-8", capture_output=True)
                self.assertEqual(json.loads(ctx.stdout)["result"]["preferences"][0]["target"], "synthetic mushrooms")
                after = (data / "meal-magic.sqlite3").read_bytes()
                installer.manage("uninstall", target)
                self.assertFalse(target.exists())
                self.assertEqual((data / "meal-magic.sqlite3").read_bytes(), after)

    def test_install_refuses_existing_folder_and_unmanaged_uninstall(self):
        target = self.base / "meal-magic"
        target.mkdir()
        (target / "personal.txt").write_text("synthetic private file")
        for action in ("install", "update", "uninstall"):
            with self.subTest(action=action), self.assertRaises(installer.InstallError):
                installer.manage(action, target)
        self.assertTrue((target / "personal.txt").exists())

    def test_modified_or_added_content_blocks_update_and_uninstall(self):
        target = self.base / "meal-magic"
        installer.manage("install", target)
        (target / "SKILL.md").write_text("synthetic local edits")
        for action in ("update", "uninstall"):
            with self.assertRaises(installer.InstallError):
                installer.manage(action, target)
        self.assertEqual((target / "SKILL.md").read_text(), "synthetic local edits")

    def test_extra_data_is_never_deleted(self):
        target = self.base / "meal-magic"
        installer.manage("install", target)
        private = target / "private-data"
        private.mkdir()
        (private / "keep.txt").write_text("synthetic")
        with self.assertRaises(installer.InstallError):
            installer.manage("uninstall", target)
        self.assertTrue((private / "keep.txt").exists())

    def test_invalid_destination_and_source_overlap(self):
        for target in (self.base, installer.SOURCE, installer.SOURCE / "nested/meal-magic"):
            with self.subTest(target=target), self.assertRaises(installer.InstallError):
                installer.manage("install", target)
        with self.assertRaises(installer.InstallError):
            installer.destination("custom", "user", None, None)

    def test_update_rolls_back_if_staged_rename_fails(self):
        target = self.base / "meal-magic"
        installer.manage("install", target)
        original = (target / "SKILL.md").read_bytes()
        rename = Path.rename

        def fail_stage(path, dest):
            if path.name.startswith(".meal-magic-stage-"):
                raise OSError("synthetic rename failure")
            return rename(path, dest)

        with patch.object(Path, "rename", fail_stage), self.assertRaises(OSError):
            installer.manage("update", target)
        self.assertEqual((target / "SKILL.md").read_bytes(), original)
        installer.inspect_install(target)
        self.assertFalse(list(self.base.glob(".meal-magic-*")))

    def test_cli_custom_install_and_uninstall(self):
        target = self.base / "meal-magic"
        for action in ("install", "uninstall"):
            p = subprocess.run([sys.executable, str(ROOT / "tools/manage_skill.py"), action,
                                "--agent", "custom", "--destination", str(target)], encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertTrue(json.loads(p.stdout)["ok"])

    def junction(self, path, target):
        """Create a real Windows junction only between this test's owned paths."""
        if self.base not in path.absolute().parents or self.base not in target.resolve().parents:
            raise AssertionError("junction paths must stay inside this test workspace")
        path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, MEAL_MAGIC_TEST_LINK=str(path), MEAL_MAGIC_TEST_TARGET=str(target))
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        "New-Item -ItemType Junction -Path $env:MEAL_MAGIC_TEST_LINK "
                        "-Target $env:MEAL_MAGIC_TEST_TARGET -ErrorAction Stop | Out-Null"],
                       env=env, capture_output=True, check=True)
        def remove_junction():
            try:
                path.rmdir()  # Remove only the junction, before temporary-tree cleanup.
            except FileNotFoundError:
                pass
        self.addCleanup(remove_junction)

    @unittest.skipUnless(sys.platform == "win32", "Windows junction regression")
    def test_junction_target_and_ancestor_refused_for_every_lifecycle_action(self):
        for placement in ("target", "ancestor"):
            for action in ("install", "update", "uninstall"):
                with self.subTest(placement=placement, action=action):
                    case = self.base / (placement + "-" + action)
                    actual = case / "outside/meal-magic"
                    installer.manage("install", actual)
                    before = {p.relative_to(actual).as_posix(): p.read_bytes()
                              for p in actual.rglob("*") if p.is_file()}
                    if placement == "target":
                        link = case / "chosen/meal-magic"
                        self.junction(link, actual)
                        chosen = link
                    else:
                        link = case / "chosen"
                        self.junction(link, actual.parent)
                        chosen = link / "meal-magic"
                    with self.assertRaisesRegex(installer.InstallError, "redirected_destination_refused"):
                        installer.manage(action, chosen)
                    self.assertEqual({p.relative_to(actual).as_posix(): p.read_bytes()
                                      for p in actual.rglob("*") if p.is_file()}, before)

    @unittest.skipUnless(sys.platform == "win32", "Windows junction regression")
    def test_junction_inside_owned_installation_refused_and_external_file_preserved(self):
        actual = self.base / "meal-magic"
        installer.manage("install", actual)
        script = actual / "scripts/meal_store.py"
        content = script.read_bytes()
        external = self.base / "external-scripts"
        external.mkdir()
        (external / "meal_store.py").write_bytes(content)
        script.unlink()
        script.parent.rmdir()
        self.junction(actual / "scripts", external)
        for action in ("update", "uninstall"):
            with self.subTest(action=action), self.assertRaisesRegex(
                installer.InstallError, "redirected_install_content_refused"
            ):
                installer.manage(action, actual)
        self.assertEqual((external / "meal_store.py").read_bytes(), content)

    @unittest.skipUnless(sys.platform == "win32", "Windows junction regression")
    def test_project_scope_preserves_redirected_path_until_guard_checks_it(self):
        actual_project = self.base / "actual-project"
        actual_project.mkdir()
        actual = installer.destination("codex", "project", actual_project, None)
        installer.manage("install", actual)
        alias = self.base / "project-alias"
        self.junction(alias, actual_project)
        chosen = installer.destination("codex", "project", alias, None)
        with self.assertRaisesRegex(installer.InstallError, "redirected_destination_refused"):
            installer.manage("uninstall", chosen)
        self.assertTrue((actual / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
