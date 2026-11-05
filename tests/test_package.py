"""Exercise the actual distributable independently of the source checkout."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_package", ROOT / "tools/build_package.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackageTests(unittest.TestCase):
    def test_review_zip_has_only_public_files_and_can_install(self):
        with tempfile.TemporaryDirectory(prefix="meal-magic-package-test-") as temp:
            base = Path(temp).resolve()
            archive = builder.build(base / "dist")
            with zipfile.ZipFile(archive) as bundle:
                version = (ROOT / "skills/meal-magic/VERSION").read_text().strip()
                expected = {f"meal-magic-{version}/" + rel for rel in builder.PUBLIC_FILES}
                self.assertEqual(set(bundle.namelist()), expected)
                self.assertIsNone(bundle.testzip())
                bundle.extractall(base / "extracted")  # Entries above are the exact trusted allowlist.
            extracted = base / f"extracted/meal-magic-{version}"
            self.assertTrue((extracted / "tests/test_meal_members.py").is_file())
            installed = base / "custom-agent/meal-magic"
            p = subprocess.run([sys.executable, str(extracted / "tools/manage_skill.py"), "install",
                                "--agent", "custom", "--destination", str(installed)],
                               encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertTrue((installed / "LICENSE").is_file())
            for name in ("household", "occasions", "recipes-plans", "meal-history"):
                rel = f"references/{name}.md"
                self.assertEqual((installed / rel).read_bytes(), (extracted / "skills/meal-magic" / rel).read_bytes())
            p = subprocess.run([sys.executable, str(installed / "scripts/meal_store.py"),
                                "--data-dir", str(base / "synthetic-profile")], input='{"action":"context"}',
                               encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)["result"]
            self.assertEqual(result["preferences"], [])
            self.assertEqual(result["recent_meals"], [])
            self.assertEqual(result["household"]["onboarding"]["status"], "pending")
            request = {"action": "plan-save", "request_key": "package-plan", "title": "Synthetic dinner",
                       "meals": [{"on": "2026-11-09", "slot": "dinner", "name": "Synthetic rice",
                                  "servings": 2, "details": "150 g dry rice; cook according to packet."}],
                       "shopping_list": [{"item": "rice", "quantity": "150 g dry"}]}
            def invoke(req):
                run = subprocess.run([sys.executable, str(installed / "scripts/meal_store.py"),
                                      "--data-dir", str(base / "synthetic-profile")], input=json.dumps(req),
                                     encoding="utf-8", capture_output=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                return json.loads(run.stdout)["result"]
            saved = invoke(request)
            update = subprocess.run([sys.executable, str(extracted / "tools/manage_skill.py"), "update",
                                     "--agent", "custom", "--destination", str(installed)],
                                    encoding="utf-8", capture_output=True)
            self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
            self.assertEqual(invoke({"action": "plan-get", "id": saved["id"]}), saved)
            self.assertEqual(invoke({"action": "meal-list"}), [])
            member = invoke({"action": "member-set", "label": "Synthetic diner"})
            meal = invoke({"action": "meal-log", "request_key": "package-meal", "name": "Synthetic rice",
                           "kind": "eaten", "occurred_on": "2026-11-05", "member_ids": [member["id"]]})
            update = subprocess.run([sys.executable, str(extracted / "tools/manage_skill.py"), "update",
                                     "--agent", "custom", "--destination", str(installed)],
                                    encoding="utf-8", capture_output=True)
            self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
            self.assertEqual(invoke({"action": "meal-list", "member_id": member["id"]}), [meal])
            exported = invoke({"action": "export"})
            restored = subprocess.run([sys.executable, str(installed / "scripts/meal_store.py"),
                                       "--data-dir", str(base / "restored-synthetic-profile")],
                                      input=json.dumps({"action": "import", "request_key": "package-import", "data": exported}),
                                      encoding="utf-8", capture_output=True)
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            queried = subprocess.run([sys.executable, str(installed / "scripts/meal_store.py"),
                                      "--data-dir", str(base / "restored-synthetic-profile")],
                                     input='{"action":"export"}', encoding="utf-8", capture_output=True)
            self.assertEqual(queried.returncode, 0, queried.stdout + queried.stderr)
            self.assertEqual(json.loads(queried.stdout)["result"], exported)


if __name__ == "__main__":
    unittest.main()
