#!/usr/bin/env python3
"""Check portable-skill layout, local Markdown links and tracked-file hygiene."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys

from build_package import PUBLIC_FILES, ROOT


def forbidden_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in {"__pycache__", ".venv", "venv", "dist", "MealMagic", ".meal-magic-data", ".meal-magic"} for part in parts):
        return True
    name = Path(path).name.lower()
    return (name in {".env", ".origins.json"} or name.startswith(".env.") or
            name.startswith(("credentials.", "secrets.")) or
            any(name.endswith(ext) or ext + "-" in name for ext in (".db", ".sqlite", ".sqlite3")) or
            name.endswith((".pyc", ".pyo")))


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for rel in PUBLIC_FILES:
        path = root / rel
        if not path.is_file() or path.is_symlink() or forbidden_path(rel):
            errors.append(f"Missing, redirected or forbidden public file: {rel}")
            continue
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                target = target.strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (path.parent / target).is_file():
                    errors.append(f"Broken local Markdown link in {rel}: {target}")
    skill = root / "skills/meal-magic/SKILL.md"
    if skill.is_file():
        text = skill.read_text(encoding="utf-8")
        blocks = text.split("---", 2)
        if len(blocks) < 3 or blocks[0].strip() or "name: meal-magic" not in blocks[1].splitlines() or not any(
            line.startswith("description: ") and line.removeprefix("description: ").strip() for line in blocks[1].splitlines()
        ):
            errors.append("Skill manifest must start with name and nonempty description frontmatter")
    for path in (root / "skills/meal-magic/scripts").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                if name.split(".")[0] not in sys.stdlib_module_names:
                    errors.append(f"Non-standard-library runtime import in {path.name}: {name}")
    if (root / ".git").exists():
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                                 encoding="utf-8", capture_output=True, check=True).stdout.split("\0")
        errors.extend(f"Forbidden tracked file: {rel}" for rel in tracked if rel and forbidden_path(rel))
    return errors


if __name__ == "__main__":
    failures = check()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print("Repository checks passed (layout, local links, stdlib imports, tracked paths where available).")
