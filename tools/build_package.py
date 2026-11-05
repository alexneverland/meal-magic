#!/usr/bin/env python3
"""Build a review ZIP from an explicit public-file allowlist, never user data."""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = (
    "README.md", "LICENSE", "VERIFICATION.md", "SECURITY.md", "CONTRIBUTING.md", "AGENTS.md",
    ".gitignore", ".gitattributes", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/dependabot.yml", ".github/workflows/ci.yml",
    "skills/meal-magic/SKILL.md", "skills/meal-magic/VERSION", "skills/meal-magic/LICENSE",
    "skills/meal-magic/scripts/meal_store.py", "skills/meal-magic/references/storage-cli.md",
    "tools/manage_skill.py", "tools/build_package.py", "tools/check_repository.py",
    "tests/test_store.py", "tests/test_household.py", "tests/test_observances.py",
    "tests/test_install.py", "tests/test_package.py", "tests/test_plans.py", "tests/agent-scenarios.md",
)


def build(output_dir: Path, root: Path = ROOT) -> Path:
    """Package known source files only; output must not replace any source file."""
    output_dir = output_dir.resolve()
    version = (root / "skills/meal-magic/VERSION").read_text(encoding="utf-8").strip()
    if not version or any(c not in "0123456789." for c in version):
        raise ValueError("invalid_package_version")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"meal-magic-{version}.zip"
    for rel in PUBLIC_FILES:
        source = root / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing_or_redirected_public_file: {rel}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for rel in PUBLIC_FILES:
            bundle.write(root / rel, arcname=f"meal-magic-{version}/{rel}")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return archive


if __name__ == "__main__":
    print(build(ROOT / "dist"))
