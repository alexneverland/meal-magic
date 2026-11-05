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
            base = Path(temp)
            archive = builder.build(base / "dist")
            with zipfile.ZipFile(archive) as bundle:
                version = (ROOT / "skills/meal-magic/VERSION").read_text().strip()
                expected = {f"meal-magic-{version}/" + rel for rel in builder.PUBLIC_FILES}
                self.assertEqual(set(bundle.namelist()), expected)
                self.assertIsNone(bundle.testzip())
                bundle.extractall(base / "extracted")  # Entries above are the exact trusted allowlist.
            extracted = base / f"extracted/meal-magic-{version}"
            installed = base / "custom-agent/meal-magic"
            p = subprocess.run([sys.executable, str(extracted / "tools/manage_skill.py"), "install",
                                "--agent", "custom", "--destination", str(installed)],
                               encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertTrue((installed / "LICENSE").is_file())
            p = subprocess.run([sys.executable, str(installed / "scripts/meal_store.py"),
                                "--data-dir", str(base / "synthetic-profile")], input='{"action":"context"}',
                               encoding="utf-8", capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)["result"]
            self.assertEqual(result["preferences"], [])
            self.assertEqual(result["recent_meals"], [])
            self.assertEqual(result["household"]["onboarding"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
