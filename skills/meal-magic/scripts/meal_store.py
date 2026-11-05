#!/usr/bin/env python3
"""Meal Magic's local JSON-in/JSON-out storage boundary (Python 3.10+)."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unicodedata
import uuid
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

VERSION = "0.6.2"
KINDS = ("prefer", "avoid", "forbid", "allergy", "diet")
AGE_GROUPS = ("unspecified", "infant", "young_child", "child", "teen", "adult", "older_adult")
ALLERGY_STATUSES = ("unknown", "none_reported", "reported")


class StoreError(Exception):
    """A safe, machine-readable storage or input failure."""


def default_data_dir() -> Path:
    """Resolve user data independently of the working or install directory."""
    override = os.environ.get("MEAL_MAGIC_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path.home() / ".meal-magic" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/MealMagic"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "meal-magic"


def checked_path(path: Path) -> Path:
    """Refuse links/reparse points; never follow discovery outside known locations."""
    path = Path(os.path.abspath(path.expanduser()))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise StoreError("redirected_profile_path")
    return path


def native_windows_path(path: Path) -> Path:
    """Address the local volume, including native AppData hidden by an MSIX overlay.

    This is a filesystem alias, not privilege escalation: normal Windows ACLs apply.
    No package names or host-specific storage implementation are required.
    """
    import ctypes
    from ctypes import wintypes
    path = checked_path(path)
    if str(path).startswith("\\\\"):
        return path
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeNameForVolumeMountPointW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    mount, volume = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(1024)
    if not kernel.GetVolumePathNameW(str(path), mount, len(mount)):
        raise StoreError("profile_volume_unavailable")
    if not kernel.GetVolumeNameForVolumeMountPointW(mount.value, volume, len(volume)):
        raise StoreError("profile_volume_unavailable")
    return checked_path(Path(volume.value) / path.relative_to(mount.value))


def windows_legacy_paths() -> list[Path]:
    """Only inspect exact MealMagic paths, never unrelated package contents."""
    user_local = Path.home() / "AppData" / "Local"
    roots = {native_windows_path(Path(os.environ.get("LOCALAPPDATA", user_local))),
             native_windows_path(user_local)}
    paths = []
    for local in sorted(roots):
        paths.append(local / "MealMagic" / "meal-magic.sqlite3")
        packages = checked_path(local / "Packages")
        if packages.exists():
            for package in sorted(packages.iterdir()):
                # Do not enter links, unrelated package content, backups or arbitrary directories.
                if package.is_symlink() or getattr(package.lstat(), "st_file_attributes", 0) & 0x400:
                    continue
                paths.append(package / "LocalCache" / "Local" / "MealMagic" / "meal-magic.sqlite3")
    return paths


def sqlite_uri(path: Path, mode: str = "ro") -> str:
    # Encode backslashes and '?' as well: Path.as_uri loses Windows volume-GUID prefixes.
    return "file:" + quote(str(path), safe="") + "?mode=" + mode


def physical_path(path: Path) -> str | None:
    """Report the file opened by the OS, not just a potentially virtualized spelling."""
    if not path.exists():
        return None
    if sys.platform != "win32":
        return str(path.resolve())
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                wintypes.DWORD, wintypes.DWORD]
    with path.open("rb") as source:
        buffer = ctypes.create_unicode_buffer(32768)
        size = kernel.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(source.fileno()), buffer, len(buffer), 0)
        if not size or size >= len(buffer):
            raise StoreError("profile_physical_path_unavailable")
        return buffer.value


def profile_snapshot(path: Path) -> tuple[sqlite3.Connection, bool, str]:
    """Consistent SQLite snapshot, including WAL and internal retry receipts."""
    memory = sqlite3.connect(":memory:")
    deadline = time.monotonic() + 10
    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() > deadline:
            raise StoreError("profile_busy_retry")
    try:
        with closing(sqlite3.connect(sqlite_uri(path), uri=True, timeout=10)) as source:
            source.backup(memory, pages=128, progress=progress, sleep=0.01)
        version = memory.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in memory.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {"preferences", "recipes", "meals"}
        if version >= 2:
            expected |= {"members", "onboarding"}
        if version >= 3:
            expected |= {"locale", "observances"}
        if version >= 4:
            expected |= {"plans", "plan_requests"}
        if version >= 5:
            expected |= {"meal_members"}
        if version >= 6:
            expected |= {"meal_requests"}
        if version >= 7:
            expected |= {"import_requests"}
        if version not in range(1, 8) or tables != expected:
            raise StoreError("unrecognized_legacy_profile")
        if memory.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise StoreError("invalid_legacy_profile")
        if memory.execute("PRAGMA foreign_key_check").fetchone():
            raise StoreError("invalid_legacy_profile")
        meaningful = any(memory.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone()
                         for table in tables - {"onboarding", "locale"})
        if "onboarding" in tables:
            rows = memory.execute("SELECT status FROM onboarding WHERE singleton=1").fetchall()
            if len(rows) != 1 or rows[0][0] not in ("pending", "in_progress", "completed", "skipped"):
                raise StoreError("invalid_legacy_profile")
            meaningful |= rows[0][0] in ("completed", "skipped")
        if "locale" in tables:
            rows = memory.execute("SELECT country,region,timezone,holiday_mode FROM locale WHERE singleton=1").fetchall()
            if len(rows) != 1:
                raise StoreError("invalid_legacy_profile")
            meaningful |= rows[0] != (None, None, None, "unknown")
        # Hash full logical state, including deleted-event/old-plan receipts; never log its text.
        fingerprint = hashlib.sha256("\n".join(sorted(memory.iterdump())).encode("utf-8")).hexdigest()
        return memory, bool(meaningful), fingerprint
    except Exception:
        memory.close()
        raise


@contextmanager
def profile_lock(directory: Path):
    """Serialize discovery, publication and writes across agents; OS releases on crash."""
    checked_path(directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = checked_path(directory / ".startup.lock")
    with lock_path.open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 10
        if os.name == "nt":
            import msvcrt
            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(lock, fcntl.LOCK_UN)
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise StoreError("profile_busy_retry") from None
                time.sleep(0.02)
        try:
            yield
        finally:
            release()


def discover_profiles(target: Path) -> list[Path]:
    found, identities = [], set()
    for path in windows_legacy_paths():
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        path = checked_path(path)
        info = path.stat()
        if not path.is_file():
            raise StoreError("invalid_legacy_profile")
        identity = (info.st_dev, info.st_ino)
        if identity not in identities:
            identities.add(identity)
            if not target.exists() or not os.path.samefile(path, target):
                found.append(path)
    return found


def read_origins(marker: Path) -> dict | None:
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        def hex_string(value, length):
            return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)
        identity = data.get("database_identity") if isinstance(data, dict) else None
        if (not isinstance(data, dict) or set(data) != {"schema", "profile_id", "sources", "state",
                                                      "database_identity", "selected_source"} or
                type(data["schema"]) is not int or data["schema"] != 1 or
                not hex_string(data["profile_id"], 32) or not isinstance(data["sources"], dict) or
                data["state"] not in ("publishing", "ready") or
                any(not isinstance(k, str) or not k or not hex_string(v, 64)
                    for k, v in data["sources"].items()) or
                (data["selected_source"] is not None and not isinstance(data["selected_source"], str)) or
                (identity is not None and (not isinstance(identity, list) or len(identity) != 2 or
                                          any(type(v) is not int or v < 0 for v in identity)))):
            raise ValueError
        return data
    except (ValueError, UnicodeError):
        raise StoreError("invalid_profile_origins") from None


def write_origins(marker: Path, data: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".origins-",
                                         suffix=".tmp", dir=marker.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, marker)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_shared_profile(target: Path, selected_database: str | None = None) -> None:
    """Adopt one unambiguous legacy profile without overwriting or removing sources."""
    target = checked_path(target)
    marker = checked_path(target.parent / ".origins.json")
    paths = discover_profiles(target)
    origins = read_origins(marker)
    # Stored paths are descriptive only. Never use this JSON to authorize reads
    # outside the exact legacy locations independently discovered above.
    snapshots, source_locks = [], []
    try:
        if origins is not None and origins["state"] == "ready" and not target.exists():
            raise StoreError("shared_profile_missing")
        if target.exists():
            con = sqlite3.connect(sqlite_uri(target, "rw"), uri=True, timeout=10)
            source_locks.append(con)
            con.execute("BEGIN IMMEDIATE")
            info = target.stat()
            if (origins is not None and origins.get("database_identity") is not None and
                    origins["database_identity"] != [info.st_dev, info.st_ino]):
                raise StoreError("shared_profile_identity_changed")
        # Reserve source writers while taking and publishing a committed snapshot.
        for path in sorted(paths, key=str):
            con = sqlite3.connect(sqlite_uri(path, "rw"), uri=True, timeout=10)
            source_locks.append(con)
            con.execute("BEGIN IMMEDIATE")
            snapshot, meaningful, fingerprint = profile_snapshot(path)
            snapshots.append((path, snapshot, meaningful, fingerprint))
        if origins is not None and target.exists():
            if selected_database is not None:
                chosen = origins.get("selected_source")
                if chosen is None or Path(chosen) != Path(selected_database):
                    raise StoreError("shared_profile_already_initialized")
            for path, snapshot, meaningful, fingerprint in snapshots:
                old = origins["sources"].get(str(path))
                if old is not None and old != fingerprint or old is None and meaningful:
                    raise StoreError("legacy_profile_changed_after_adoption")
            if origins["state"] == "publishing":
                origins["state"] = "ready"
                write_origins(marker, origins)
            return
        meaningful = [item for item in snapshots if item[2]]
        if selected_database is None and len({item[3] for item in meaningful}) > 1:
            raise StoreError("multiple_existing_profiles")
        selected = (meaningful or snapshots or [None])[0]
        if selected_database is not None:
            selected = next((item for item in snapshots if item[0] == Path(selected_database)), None)
            if selected is None:
                raise StoreError("profile_candidate_not_found")
            if target.exists():
                raise StoreError("shared_profile_already_initialized")
        if target.exists() and selected:
            current, occupied, fingerprint = profile_snapshot(target)
            current.close()
            if selected[2] and fingerprint != selected[3]:
                raise StoreError("multiple_existing_profiles")
        record = {"schema": 1, "profile_id": uuid.uuid4().hex,
                  "state": "ready" if target.exists() else "publishing",
                  "sources": {str(item[0]): item[3] for item in snapshots},
                  "selected_source": str(selected[0]) if selected else None,
                  "database_identity": None}
        if target.exists():
            info = target.stat()
            record["database_identity"] = [info.st_dev, info.st_ino]
        if origins is not None and not target.exists():
            # An interrupted initial publication may retry, but never silently replace a profile identity.
            record["profile_id"] = origins.get("profile_id", record["profile_id"])
        with tempfile.TemporaryDirectory(prefix=".meal-magic-adopt-", dir=target.parent) as temporary:
            stage_dir = Path(temporary)
            stage = stage_dir / "meal-magic.sqlite3"
            if not target.exists():
                if selected:
                    with closing(sqlite3.connect(stage)) as destination:
                        selected[1].backup(destination)
                # Migrate/validate only the staging copy; receipts stay in the complete DB.
                candidate = Store(stage_dir)
                candidate.handle({"action": "context"})
                candidate.handle({"action": "export"})
                with stage.open("r+b") as staged:
                    os.fsync(staged.fileno())
                info = stage.stat()
                record["database_identity"] = [info.st_dev, info.st_ino]
            write_origins(marker, record)
            if stage.exists():
                # Atomic no-replace publication also protects against explicit-path callers.
                os.link(stage, target)
                record["state"] = "ready"
                write_origins(marker, record)
    finally:
        for item in snapshots:
            item[1].close()
        for con in source_locks:
            con.rollback()
            con.close()


def normalized(value: str) -> str:
    """Normalize literal search text, never natural-language intent."""
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold())
                   if unicodedata.category(c) != "Mn")


def text_field(req: dict, key: str, *, limit: int = 2000) -> str:
    """Validate a required, nonempty string."""
    value = req.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise StoreError(f"invalid_{key}")
    return value.strip()


def boolean(req: dict, key: str, default: bool = False) -> bool:
    value = req.get(key, default)
    if type(value) is not bool:
        raise StoreError(f"invalid_{key}")
    return value


def limit_field(req: dict, default: int = 20) -> int:
    value = req.get("limit", default)
    if type(value) is not int or not 1 <= value <= 100:
        raise StoreError("invalid_limit")
    return value


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def date_field(req: dict, key: str) -> date:
    value = text_field(req, key, limit=10)
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
    except ValueError:
        raise StoreError(f"invalid_{key}") from None
    return parsed


def validate_snapshot(data: Any) -> dict:
    """Validate a public export as inert data without repairing or inferring facts."""
    def fields(value, names):
        if not isinstance(value, dict) or set(value) != set(names.split()):
            raise StoreError("invalid_import_fields")

    def string(value, maximum=2000, empty=False):
        if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
            raise StoreError("invalid_import_string")

    def stamp(value):
        string(value, 100)
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise StoreError("invalid_import_timestamp") from None

    def choice(value, allowed):
        if not isinstance(value, str) or value not in allowed:
            raise StoreError("invalid_import_enum")

    def reference(value, ids):
        if value is not None and (not isinstance(value, str) or value not in ids):
            raise StoreError("invalid_import_reference")

    fields(data, "schema_version household preferences recipes meals plans")
    if type(data["schema_version"]) is not int or data["schema_version"] not in (6, 7):
        raise StoreError("unsupported_import_schema")
    household = data["household"]
    fields(household, "onboarding members locale observances")
    collections = {key: data[key] for key in ("preferences", "recipes", "meals", "plans")}
    collections.update({key: household[key] for key in ("members", "observances")})
    ids = {}
    shapes = {
        "members": "id label age_group allergy_status notes updated_at",
        "observances": "id label kind schedule rules calendar strictness active member_id notes updated_at",
        "preferences": "id kind target notes updated_at member_id",
        "recipes": "id name content tags source created_at favorite",
        "meals": "id kind name occurred_on recipe_id created_at member_ids",
        "plans": "id title start_on end_on revision created_at updated_at meals shopping_list notes",
    }
    for domain, records in collections.items():
        if not isinstance(records, list) or len(records) > 10000:
            raise StoreError("invalid_import_records")
        ids[domain] = set()
        for record in records:
            fields(record, shapes[domain])
            string(record["id"], 200)
            if record["id"] != record["id"].strip():
                raise StoreError("invalid_import_id")
            if record["id"] in ids[domain]:
                raise StoreError("invalid_import_duplicate_id")
            ids[domain].add(record["id"])
            for key in ("created_at", "updated_at"):
                if key in record:
                    stamp(record[key])
    labels = set()
    for member in collections["members"]:
        string(member["label"], 200)
        if member["label"] in labels:
            raise StoreError("invalid_import_duplicate_label")
        labels.add(member["label"])
        choice(member["age_group"], AGE_GROUPS)
        choice(member["allergy_status"], ALLERGY_STATUSES)
        string(member["notes"], 4000, empty=True)
    members = {member["id"]: member for member in collections["members"]}
    for pref in collections["preferences"]:
        choice(pref["kind"], KINDS)
        string(pref["target"])
        string(pref["notes"], 4000, empty=True)
        reference(pref["member_id"], ids["members"])
        if pref["kind"] == "allergy" and pref["member_id"] is not None:
            if members[pref["member_id"]]["allergy_status"] != "reported":
                raise StoreError("invalid_import_allergy_status")
    for practice in collections["observances"]:
        string(practice["label"], 200)
        choice(practice["kind"], ("holiday", "fasting", "tradition"))
        choice(practice["strictness"], ("unspecified", "strict", "flexible"))
        if type(practice["active"]) is not bool:
            raise StoreError("invalid_import_boolean")
        reference(practice["member_id"], ids["members"])
        for key, maximum, empty in (("schedule", 4000, False), ("rules", 8000, False),
                                    ("calendar", 1000, True), ("notes", 4000, True)):
            string(practice[key], maximum, empty)
    fields(household["onboarding"], "status updated_at")
    choice(household["onboarding"]["status"], ("pending", "in_progress", "completed", "skipped"))
    stamp(household["onboarding"]["updated_at"])
    locale = household["locale"]
    fields(locale, "country region timezone holiday_mode updated_at")
    for key in ("country", "region", "timezone"):
        if locale[key] is not None:
            string(locale[key], 200)
    choice(locale["holiday_mode"], ("unknown", "suggest", "off"))
    stamp(locale["updated_at"])
    for recipe in collections["recipes"]:
        string(recipe["name"])
        string(recipe["content"], 100000)
        string(recipe["source"])
        if type(recipe["favorite"]) is not bool:
            raise StoreError("invalid_import_boolean")
        if not isinstance(recipe["tags"], list) or len(recipe["tags"]) > 50:
            raise StoreError("invalid_import_tags")
        for tag in recipe["tags"]:
            string(tag, 100)
    for meal in collections["meals"]:
        string(meal["name"])
        choice(meal["kind"], ("cooked", "eaten"))
        try:
            date_field(meal, "occurred_on")
        except StoreError:
            raise StoreError("invalid_import_date") from None
        reference(meal["recipe_id"], ids["recipes"])
        attendees = meal["member_ids"]
        if not isinstance(attendees, list) or len(attendees) > 100:
            raise StoreError("invalid_import_members")
        seen = set()
        for member in attendees:
            if not isinstance(member, str) or member not in ids["members"] or member in seen:
                raise StoreError("invalid_import_members")
            seen.add(member)
    for plan in collections["plans"]:
        string(plan["title"])
        if type(plan["revision"]) is not int or not 1 <= plan["revision"] < 2**63:
            raise StoreError("invalid_import_revision")
        try:
            # Reuse existing bounded plan validation; do not change imported text.
            Store._plan_document(plan)
            for meal in plan["meals"]:
                fields(meal, "on slot name servings details")
            for item in plan["shopping_list"]:
                fields(item, "item quantity notes")
            dates = [meal["on"] for meal in plan["meals"]]
            if plan["start_on"] != min(dates) or plan["end_on"] != max(dates):
                raise StoreError("invalid_plan_span")
        except StoreError:
            raise StoreError("invalid_import_plan") from None
    return data


SCHEMA = (
    "CREATE TABLE preferences (id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL, "
    "notes TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE recipes (id TEXT PRIMARY KEY, name TEXT NOT NULL, content TEXT NOT NULL, "
    "tags TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, "
    "request_key TEXT NOT NULL UNIQUE, request_payload TEXT NOT NULL)",
    "CREATE TABLE meals (id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('cooked','eaten')), "
    "name TEXT NOT NULL, occurred_on TEXT NOT NULL, recipe_id TEXT REFERENCES recipes(id), "
    "created_at TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, request_payload TEXT NOT NULL)",
    "CREATE INDEX meals_date ON meals(occurred_on DESC)",
)


class Store:
    """Single-user store shared by agents; each request is one transaction."""

    def __init__(self, data_dir: Path | str | None = None):
        self.shared_windows = (data_dir is None and not os.environ.get("MEAL_MAGIC_DATA_DIR")
                               and sys.platform == "win32")
        selected = Path(data_dir).expanduser() if data_dir else default_data_dir()
        self.data_dir = checked_path(selected) if self.shared_windows else selected.resolve()
        install = Path(__file__).resolve().parents[1]
        if self.data_dir == install or install in self.data_dir.parents:
            raise StoreError("data_directory_inside_skill")
        self.path = self.data_dir / "meal-magic.sqlite3"

    def _storage_info(self) -> dict:
        result = {"directory": str(self.data_dir), "database": str(self.path),
                  "physical_database": physical_path(self.path), "exists": self.path.is_file(),
                  "selection": "shared_windows_default" if self.shared_windows else "explicit_or_platform_default",
                  "profile_id": None, "legacy_candidates": []}
        if self.shared_windows:
            checked_path(self.data_dir)
            marker = checked_path(self.data_dir / ".origins.json")
            data = read_origins(marker)
            if data:
                result["profile_id"] = data["profile_id"]
            for path in discover_profiles(self.path):
                snapshot, meaningful, fingerprint = profile_snapshot(path)
                tables = {r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts = {table: snapshot.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
                          for table in ("members", "preferences", "recipes", "meals", "plans") if table in tables}
                snapshot.close()
                result["legacy_candidates"].append({"database": str(path),
                                                     "has_saved_state": meaningful, "counts": counts})
        return result

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("BEGIN IMMEDIATE")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise StoreError("unrecognized_database")
                for statement in SCHEMA:
                    con.execute(statement)
                version = 1
            if version == 1:
                # Additive, transactional migration. Preserve all v0.1 record IDs/content.
                con.execute("CREATE TABLE members (id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE, "
                            "age_group TEXT NOT NULL, allergy_status TEXT NOT NULL, notes TEXT NOT NULL, "
                            "updated_at TEXT NOT NULL)")
                con.execute("ALTER TABLE preferences ADD COLUMN member_id TEXT REFERENCES members(id)")
                con.execute("CREATE TABLE onboarding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                            "status TEXT NOT NULL, updated_at TEXT NOT NULL)")
                con.execute("INSERT INTO onboarding VALUES (1, 'pending', ?)", (now(),))
                con.execute("PRAGMA user_version = 2")
                version = 2
            if version == 2:
                con.execute("CREATE TABLE locale (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                            "country TEXT, region TEXT, timezone TEXT, holiday_mode TEXT NOT NULL, updated_at TEXT NOT NULL)")
                con.execute("INSERT INTO locale VALUES (1,NULL,NULL,NULL,'unknown',?)", (now(),))
                con.execute("CREATE TABLE observances (id TEXT PRIMARY KEY, label TEXT NOT NULL, "
                            "kind TEXT NOT NULL, schedule TEXT NOT NULL, rules TEXT NOT NULL, "
                            "calendar TEXT NOT NULL, strictness TEXT NOT NULL, active INTEGER NOT NULL, "
                            "member_id TEXT REFERENCES members(id), notes TEXT NOT NULL, updated_at TEXT NOT NULL)")
                con.execute("PRAGMA user_version = 3")
                version = 3
            if version == 3:
                con.execute("CREATE TABLE plans (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
                            "start_on TEXT NOT NULL, end_on TEXT NOT NULL, document TEXT NOT NULL, "
                            "revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
                # Receipts intentionally have no FK: retries after removal must not recreate a plan.
                con.execute("CREATE TABLE plan_requests (request_key TEXT PRIMARY KEY, "
                            "request_payload TEXT NOT NULL, response TEXT NOT NULL)")
                con.execute("PRAGMA user_version = 4")
                version = 4
            if version == 4:
                con.execute("CREATE TABLE meal_members (meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE, "
                            "member_id TEXT NOT NULL REFERENCES members(id), PRIMARY KEY(meal_id,member_id))")
                con.execute("CREATE INDEX meal_members_member ON meal_members(member_id,meal_id)")
                con.execute("PRAGMA user_version = 5")
                version = 5
            if version == 5:
                # No FK: an old log retry must not recreate a removed event or its links.
                con.execute("CREATE TABLE meal_requests (request_key TEXT PRIMARY KEY, "
                            "request_payload TEXT NOT NULL, response TEXT NOT NULL)")
                rows = list(con.execute("SELECT * FROM meals ORDER BY id"))
                for row, meal in zip(rows, self._meals(con, rows, all_members=True)):
                    payload = {key: meal[key] for key in ("kind", "name", "occurred_on", "recipe_id", "member_ids")}
                    self._record_meal_receipt(con, row["request_key"], payload, meal)
                con.execute("PRAGMA user_version = 6")
                version = 6
            if version == 6:
                con.execute("CREATE TABLE import_requests (request_key TEXT PRIMARY KEY, "
                            "snapshot_hash TEXT NOT NULL, response TEXT NOT NULL)")
                con.execute("PRAGMA user_version = 7")
            elif version != 7:
                raise StoreError("unsupported_schema_version")
            # Also add this index to schema-4 previews created before pagination.
            con.execute("CREATE INDEX IF NOT EXISTS plans_listing ON plans(start_on DESC,updated_at DESC,id)")
            return con
        except Exception:
            con.close()
            raise

    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        """Execute one explicit structured action; never infer conversational intent."""
        actions = {
            "storage-info": (None, set()),
            "profile-select": (None, {"database"}),
            "context": (self._context, {"limit", "on"}),
            "onboarding-set": (self._onboarding_set, {"status"}),
            "member-set": (self._member_set, {"id", "label", "age_group", "allergy_status", "notes"}),
            "member-remove": (self._member_remove, {"id"}),
            "locale-set": (self._locale_set, {"country", "region", "timezone", "holiday_mode"}),
            "observance-set": (self._observance_set, {"id", "label", "kind", "schedule", "rules",
                                                     "calendar", "strictness", "active", "member_id", "notes"}),
            "observance-remove": (self._observance_remove, {"id"}),
            "preference-set": (self._preference_set, {"id", "kind", "target", "notes", "member_id"}),
            "preference-remove": (self._remove_preference, {"id"}),
            "recipe-save": (self._recipe_save, {"name", "content", "tags", "source", "request_key"}),
            "recipe-search": (self._recipe_search, {"query", "favorites_only", "limit"}),
            "recipe-get": (self._recipe_get, {"id"}),
            "recipe-favorite": (self._recipe_favorite, {"id", "favorite"}),
            "meal-log": (self._meal_log, {"kind", "name", "occurred_on", "recipe_id", "request_key", "member_ids"}),
            "meal-list": (self._meal_list, {"limit", "kind", "member_id"}),
            "meal-remove": (self._remove_meal, {"id"}),
            "plan-save": (self._plan_save, {"id", "expected_revision", "request_key", "title",
                                            "meals", "shopping_list", "notes"}),
            "plan-get": (self._plan_get, {"id"}),
            "plan-list": (self._plan_list, {"on", "limit", "offset"}),
            "plan-remove": (self._plan_remove, {"id", "expected_revision", "request_key"}),
            "export": (self._export, set()),
            "import": (self._import, {"data", "request_key"}),
        }
        if not isinstance(req, dict) or not isinstance(req.get("action"), str):
            raise StoreError("request_must_have_action")
        action = req["action"]
        if action not in actions:
            raise StoreError("unknown_action")
        fn, allowed = actions[action]
        if set(req) - allowed - {"action"}:
            raise StoreError("unknown_fields")
        if action == "storage-info":
            return {"ok": True, "result": self._storage_info()}
        if action == "profile-select":
            if not self.shared_windows:
                raise StoreError("profile_selection_requires_windows_default")
            selected = text_field(req, "database", limit=32768)
            with profile_lock(self.data_dir):
                prepare_shared_profile(self.path, selected)
                return {"ok": True, "result": self._storage_info()}
        if self.shared_windows:
            checked_path(self.data_dir)
            with profile_lock(self.data_dir):
                prepare_shared_profile(self.path)
                return self._execute(fn, req)
        return self._execute(fn, req)

    def _execute(self, fn, req: dict) -> dict:
        con = self._connect()
        try:
            with con:
                result = fn(con, req)
            output = {"ok": True, "result": result}
            if req["action"] == "context":
                output["storage"] = self._storage_info()
            return output
        finally:
            con.close()

    @staticmethod
    def _recipe(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["tags"] = json.loads(result["tags"])
        result["favorite"] = bool(result["favorite"])
        result.pop("request_key", None)
        result.pop("request_payload", None)
        return result

    @staticmethod
    def _meal(row: sqlite3.Row, member_ids: list[str]) -> dict:
        result = dict(row)
        result.pop("request_key", None)
        result.pop("request_payload", None)
        result["member_ids"] = member_ids
        return result

    def _meals(self, con: sqlite3.Connection, rows: list[sqlite3.Row], *, all_members: bool = False) -> list[dict]:
        if not rows:
            return []
        members = {row["id"]: [] for row in rows}
        if all_members:
            links = con.execute("SELECT meal_id,member_id FROM meal_members ORDER BY meal_id,member_id")
        else:
            # Bounded callers return at most 100 meals; NULL padding never matches an ID.
            ids = list(members)
            links = con.execute(
                "SELECT meal_id,member_id FROM meal_members WHERE meal_id IN ("
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?) ORDER BY meal_id,member_id", ids + [None] * (100 - len(ids)))
        for link in links:
            members[link["meal_id"]].append(link["member_id"])
        return [self._meal(row, members[row["id"]]) for row in rows]

    @staticmethod
    def _record_meal_receipt(con: sqlite3.Connection, key: str, payload: dict, response: dict) -> dict:
        con.execute("INSERT INTO meal_requests VALUES (?,?,?)",
                    (key, json.dumps(payload, ensure_ascii=False), json.dumps(response, ensure_ascii=False)))
        return response

    def _context(self, con: sqlite3.Connection, req: dict) -> dict:
        result = {
            "household": self._household(con),
            "preferences": [dict(r) for r in con.execute("SELECT * FROM preferences ORDER BY id")],
            "recent_meals": self._meal_list(con, req),
        }
        if "on" in req:
            requested_date = date_field(req, "on")
            result["date_context"] = {"on": requested_date.isoformat(), "year": requested_date.year,
                                      "weekday_iso": requested_date.isoweekday()}
        return result

    @staticmethod
    def _household(con: sqlite3.Connection) -> dict:
        onboarding = con.execute("SELECT status,updated_at FROM onboarding WHERE singleton=1").fetchone()
        if not onboarding:
            raise StoreError("onboarding_state_missing")
        locale = con.execute("SELECT country,region,timezone,holiday_mode,updated_at FROM locale WHERE singleton=1").fetchone()
        if not locale:
            raise StoreError("locale_state_missing")
        observances = [dict(r) for r in con.execute("SELECT * FROM observances ORDER BY label,id")]
        for item in observances:
            item["active"] = bool(item["active"])
        return {
            "onboarding": dict(onboarding),
            "members": [dict(r) for r in con.execute("SELECT * FROM members ORDER BY label, id")],
            "locale": dict(locale),
            "observances": observances,
        }

    def _locale_set(self, con: sqlite3.Connection, req: dict) -> dict:
        previous = self._household(con)["locale"]
        values = {}
        requested_country = req.get("country", previous["country"])
        if isinstance(requested_country, str):
            requested_country = requested_country.strip()
        country_changed = requested_country != previous["country"]
        for key in ("country", "region", "timezone"):
            default = None if country_changed and key != "country" else previous[key]
            value = req.get(key, default)
            if value is not None:
                value = text_field({key: value}, key, limit=200)
            values[key] = value
        mode = req.get("holiday_mode", previous["holiday_mode"])
        if mode not in ("unknown", "suggest", "off"):
            raise StoreError("invalid_holiday_mode")
        con.execute("UPDATE locale SET country=?,region=?,timezone=?,holiday_mode=?,updated_at=? WHERE singleton=1",
                    (values["country"], values["region"], values["timezone"], mode, now()))
        return self._household(con)["locale"]

    def _observance_set(self, con: sqlite3.Connection, req: dict) -> dict:
        label = text_field(req, "label", limit=200)
        previous = None
        if "id" in req:
            ident = text_field(req, "id", limit=200)
            previous = con.execute("SELECT * FROM observances WHERE id=?", (ident,)).fetchone()
            if not previous:
                raise StoreError("observance_not_found")
        member_id = req.get("member_id", previous["member_id"] if previous else None)
        if member_id is not None and (not isinstance(member_id, str) or not con.execute(
            "SELECT id FROM members WHERE id=?", (member_id,)
        ).fetchone()):
            raise StoreError("member_not_found")
        if "id" not in req:
            previous = con.execute("SELECT * FROM observances WHERE label=? AND member_id IS ?",
                                   (label, member_id)).fetchone()
            ident = previous["id"] if previous else uuid.uuid4().hex
        elif con.execute("SELECT id FROM observances WHERE label=? AND member_id IS ? AND id<>?",
                         (label, member_id, ident)).fetchone():
            raise StoreError("observance_label_in_use")
        values = {}
        for key, default, maximum in (("kind", "tradition", 100), ("schedule", None, 4000),
                                      ("rules", None, 8000), ("calendar", "", 1000),
                                      ("strictness", "unspecified", 100), ("notes", "", 4000)):
            value = req.get(key, previous[key] if previous else default)
            if not isinstance(value, str) or len(value) > maximum or (key not in ("calendar", "notes") and not value.strip()):
                raise StoreError(f"invalid_{key}")
            values[key] = value.strip()
        if values["kind"] not in ("holiday", "fasting", "tradition"):
            raise StoreError("invalid_observance_kind")
        if values["strictness"] not in ("unspecified", "strict", "flexible"):
            raise StoreError("invalid_strictness")
        active = boolean(req, "active", bool(previous["active"]) if previous else True)
        con.execute("INSERT INTO observances VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "label=excluded.label,kind=excluded.kind,schedule=excluded.schedule,rules=excluded.rules,"
                    "calendar=excluded.calendar,strictness=excluded.strictness,active=excluded.active,"
                    "member_id=excluded.member_id,notes=excluded.notes,updated_at=excluded.updated_at",
                    (ident, label, values["kind"], values["schedule"], values["rules"], values["calendar"],
                     values["strictness"], active, member_id, values["notes"], now()))
        result = dict(con.execute("SELECT * FROM observances WHERE id=?", (ident,)).fetchone())
        result["active"] = bool(result["active"])
        return result

    def _observance_remove(self, con: sqlite3.Connection, req: dict) -> dict:
        return self._remove(con, "observances", req)

    def _onboarding_set(self, con: sqlite3.Connection, req: dict) -> dict:
        status = text_field(req, "status")
        if status not in ("pending", "in_progress", "completed", "skipped"):
            raise StoreError("invalid_onboarding_status")
        con.execute("UPDATE onboarding SET status=?,updated_at=? WHERE singleton=1", (status, now()))
        return self._household(con)["onboarding"]

    def _member_set(self, con: sqlite3.Connection, req: dict) -> dict:
        label = text_field(req, "label", limit=200)
        previous = None
        if "id" in req:
            ident = text_field(req, "id", limit=200)
            previous = con.execute("SELECT * FROM members WHERE id=?", (ident,)).fetchone()
            if not previous:
                raise StoreError("member_not_found")
        else:
            previous = con.execute("SELECT * FROM members WHERE label=?", (label,)).fetchone()
            ident = previous["id"] if previous else uuid.uuid4().hex
        age_group = req.get("age_group", previous["age_group"] if previous else "unspecified")
        allergy_status = req.get("allergy_status", previous["allergy_status"] if previous else "unknown")
        notes = req.get("notes", previous["notes"] if previous else "")
        if age_group not in AGE_GROUPS:
            raise StoreError("invalid_age_group")
        if allergy_status not in ALLERGY_STATUSES:
            raise StoreError("invalid_allergy_status")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise StoreError("invalid_notes")
        if allergy_status != "reported" and con.execute(
            "SELECT id FROM preferences WHERE member_id=? AND kind='allergy'", (ident,)
        ).fetchone():
            raise StoreError("member_has_allergy_preferences")
        if con.execute("SELECT id FROM members WHERE label=? AND id<>?", (label, ident)).fetchone():
            raise StoreError("member_label_in_use")
        con.execute("INSERT INTO members VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "label=excluded.label,age_group=excluded.age_group,allergy_status=excluded.allergy_status,"
                    "notes=excluded.notes,updated_at=excluded.updated_at",
                    (ident, label, age_group, allergy_status, notes.strip(), now()))
        return dict(con.execute("SELECT * FROM members WHERE id=?", (ident,)).fetchone())

    def _member_remove(self, con: sqlite3.Connection, req: dict) -> dict:
        ident = text_field(req, "id", limit=200)
        if con.execute("SELECT id FROM preferences WHERE member_id=?", (ident,)).fetchone():
            raise StoreError("member_has_preferences_remove_or_reassign_explicitly")
        if con.execute("SELECT id FROM observances WHERE member_id=?", (ident,)).fetchone():
            raise StoreError("member_has_observances_remove_or_reassign_explicitly")
        if con.execute("SELECT meal_id FROM meal_members WHERE member_id=?", (ident,)).fetchone():
            raise StoreError("member_has_meals_remove_events_explicitly")
        return self._remove(con, "members", req)

    @staticmethod
    def _refresh_allergy_status(con: sqlite3.Connection, member_id: str | None) -> None:
        if member_id is None:
            return
        if con.execute("SELECT id FROM preferences WHERE member_id=? AND kind='allergy'", (member_id,)).fetchone():
            con.execute("UPDATE members SET allergy_status='reported',updated_at=? WHERE id=?", (now(), member_id))
        else:
            # Removing the last report does not establish that there are no allergies.
            con.execute("UPDATE members SET allergy_status='unknown',updated_at=? "
                        "WHERE id=? AND allergy_status='reported'", (now(), member_id))

    def _preference_set(self, con: sqlite3.Connection, req: dict) -> dict:
        target = text_field(req, "target")
        kind = text_field(req, "kind")
        if kind not in KINDS:
            raise StoreError("invalid_preference_kind")
        previous = None
        if "id" in req:
            ident = text_field(req, "id", limit=200)
            previous = con.execute("SELECT * FROM preferences WHERE id=?", (ident,)).fetchone()
            if not previous:
                raise StoreError("preference_not_found")
        member_id = req.get("member_id", previous["member_id"] if previous else None)
        if member_id is not None and (not isinstance(member_id, str) or not con.execute(
            "SELECT id FROM members WHERE id=?", (member_id,)
        ).fetchone()):
            raise StoreError("member_not_found")
        if "id" not in req:
            # Repeating the same structured assertion is harmless. Meaning stays with the agent.
            previous = con.execute("SELECT * FROM preferences WHERE kind=? AND target=? AND member_id IS ?",
                                   (kind, target, member_id)).fetchone()
            ident = previous["id"] if previous else uuid.uuid4().hex
        notes = req.get("notes", previous["notes"] if previous else "")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise StoreError("invalid_notes")
        con.execute("INSERT INTO preferences (id,kind,target,notes,updated_at,member_id) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,target=excluded.target,"
                    "notes=excluded.notes,updated_at=excluded.updated_at,member_id=excluded.member_id",
                    (ident, kind, target, notes.strip(), now(), member_id))
        if kind == "allergy":
            self._refresh_allergy_status(con, member_id)
        if previous and previous["kind"] == "allergy":
            self._refresh_allergy_status(con, previous["member_id"])
        return dict(con.execute("SELECT * FROM preferences WHERE id=?", (ident,)).fetchone())

    def _remove_preference(self, con: sqlite3.Connection, req: dict) -> dict:
        ident = text_field(req, "id", limit=200)
        previous = con.execute("SELECT * FROM preferences WHERE id=?", (ident,)).fetchone()
        result = self._remove(con, "preferences", req)
        if previous["kind"] == "allergy":
            self._refresh_allergy_status(con, previous["member_id"])
        return result

    def _remove_meal(self, con: sqlite3.Connection, req: dict) -> dict:
        return self._remove(con, "meals", req)

    @staticmethod
    def _remove(con: sqlite3.Connection, table: str, req: dict) -> dict:
        ident = text_field(req, "id", limit=200)
        # Table is an internal constant, never caller-controlled.
        cursor = con.execute(f"DELETE FROM {table} WHERE id=?", (ident,))
        if not cursor.rowcount:
            raise StoreError("record_not_found")
        return {"id": ident, "removed": True}

    @staticmethod
    def _replayed(con: sqlite3.Connection, table: str, key: str, payload: dict) -> sqlite3.Row | None:
        previous = con.execute(f"SELECT * FROM {table} WHERE request_key=?", (key,)).fetchone()
        if previous and json.loads(previous["request_payload"]) != payload:
            raise StoreError("request_key_conflict")
        return previous

    def _recipe_save(self, con: sqlite3.Connection, req: dict) -> dict:
        key = text_field(req, "request_key", limit=200)
        text_field(req, "content", limit=100000)
        payload = {"name": text_field(req, "name"), "content": req["content"]}
        tags = req.get("tags", [])
        if not isinstance(tags, list) or len(tags) > 50 or any(
            not isinstance(t, str) or not t.strip() or len(t) > 100 for t in tags
        ):
            raise StoreError("invalid_tags")
        source = req.get("source", "generated")
        if not isinstance(source, str) or not source.strip() or len(source) > 2000:
            raise StoreError("invalid_source")
        payload.update(tags=[t.strip() for t in tags], source=source.strip())
        previous = self._replayed(con, "recipes", key, payload)
        if previous:
            return self._recipe(previous)
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO recipes VALUES (?,?,?,?,?,?,0,?,?)",
                    (ident, payload["name"], payload["content"], json.dumps(payload["tags"], ensure_ascii=False),
                     payload["source"], now(), key, json.dumps(payload, ensure_ascii=False)))
        return self._recipe_get(con, {"id": ident})

    def _recipe_search(self, con: sqlite3.Connection, req: dict) -> list[dict]:
        query = req.get("query", "")
        if not isinstance(query, str) or len(query) > 2000:
            raise StoreError("invalid_query")
        favorites = boolean(req, "favorites_only")
        limit = limit_field(req)
        terms = normalized(query).split()
        results = []
        for row in con.execute("SELECT * FROM recipes ORDER BY created_at DESC, id"):
            if favorites and not row["favorite"]:
                continue
            haystack = normalized(row["name"] + " " + row["content"] + " " + row["tags"])
            if all(term in haystack for term in terms):
                item = self._recipe(row)
                item.pop("content")
                results.append(item)
            if len(results) >= limit:
                break
        return results

    def _recipe_get(self, con: sqlite3.Connection, req: dict) -> dict:
        row = con.execute("SELECT * FROM recipes WHERE id=?", (text_field(req, "id", limit=200),)).fetchone()
        if not row:
            raise StoreError("recipe_not_found")
        return self._recipe(row)

    def _recipe_favorite(self, con: sqlite3.Connection, req: dict) -> dict:
        ident = text_field(req, "id", limit=200)
        favorite = boolean(req, "favorite", True)
        if not con.execute("UPDATE recipes SET favorite=? WHERE id=?", (favorite, ident)).rowcount:
            raise StoreError("recipe_not_found")
        return {"id": ident, "favorite": favorite}

    def _meal_log(self, con: sqlite3.Connection, req: dict) -> dict:
        key = text_field(req, "request_key", limit=200)
        kind = text_field(req, "kind")
        if kind not in ("cooked", "eaten"):
            raise StoreError("invalid_meal_kind")
        occurred_on = date_field(req, "occurred_on").isoformat()
        recipe_id = req.get("recipe_id")
        if recipe_id is not None and not isinstance(recipe_id, str):
            raise StoreError("recipe_not_found")
        member_ids = req.get("member_ids", [])
        if not isinstance(member_ids, list) or len(member_ids) > 100 or any(
            not isinstance(member, str) or not member.strip() or len(member) > 200 for member in member_ids
        ):
            raise StoreError("invalid_member_ids")
        member_ids = sorted(member.strip() for member in member_ids)
        if len(set(member_ids)) != len(member_ids):
            raise StoreError("invalid_member_ids")
        payload = {"kind": kind, "name": text_field(req, "name"), "occurred_on": occurred_on,
                   "recipe_id": recipe_id, "member_ids": member_ids}
        previous = self._replayed(con, "meal_requests", key, payload)
        if previous:
            return json.loads(previous["response"])
        if recipe_id is not None and not con.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
            raise StoreError("recipe_not_found")
        for member in member_ids:
            if not con.execute("SELECT id FROM members WHERE id=?", (member,)).fetchone():
                raise StoreError("member_not_found")
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO meals VALUES (?,?,?,?,?,?,?,?)",
                    (ident, kind, payload["name"], occurred_on, recipe_id, now(), key,
                     json.dumps(payload, ensure_ascii=False)))
        con.executemany("INSERT INTO meal_members(meal_id,member_id) VALUES (?,?)",
                        [(ident, member) for member in member_ids])
        meal = self._meals(con, [con.execute("SELECT * FROM meals WHERE id=?", (ident,)).fetchone()])[0]
        return self._record_meal_receipt(con, key, payload, meal)

    def _meal_list(self, con: sqlite3.Connection, req: dict) -> list[dict]:
        limit = limit_field(req)
        kind = req.get("kind")
        if kind is not None and kind not in ("cooked", "eaten"):
            raise StoreError("invalid_meal_kind")
        if "member_id" in req:
            member = text_field(req, "member_id", limit=200)
            if not con.execute("SELECT id FROM members WHERE id=?", (member,)).fetchone():
                raise StoreError("member_not_found")
            rows = con.execute(
                "SELECT m.* FROM meal_members mm JOIN meals m ON m.id=mm.meal_id "
                "WHERE mm.member_id=? AND (? IS NULL OR m.kind=?) "
                "ORDER BY m.occurred_on DESC,m.created_at DESC,m.id LIMIT ?", (member, kind, kind, limit))
        else:
            rows = con.execute(
                "SELECT * FROM meals WHERE (? IS NULL OR kind=?) ORDER BY occurred_on DESC,created_at DESC,id LIMIT ?",
                (kind, kind, limit))
        return self._meals(con, list(rows))

    @staticmethod
    def _plan(row: sqlite3.Row) -> dict:
        """Return a stored snapshot, never an actual meal event."""
        result = dict(row)
        result.update(json.loads(result.pop("document")))
        return result

    def _plan_get(self, con: sqlite3.Connection, req: dict) -> dict:
        row = con.execute("SELECT * FROM plans WHERE id=?", (text_field(req, "id", limit=200),)).fetchone()
        if not row:
            raise StoreError("plan_not_found")
        return self._plan(row)

    def _plan_list(self, con: sqlite3.Connection, req: dict) -> list[dict]:
        on = date_field(req, "on").isoformat() if "on" in req else None
        offset = req.get("offset", 0)
        if type(offset) is not int or not 0 <= offset < 2**63:
            raise StoreError("invalid_offset")
        limit = limit_field(req)
        if on is None:
            rows = con.execute("SELECT id,title,start_on,end_on,revision,created_at,updated_at FROM plans "
                               "ORDER BY start_on DESC,updated_at DESC,id LIMIT ? OFFSET ?", (limit, offset))
        else:
            rows = con.execute("SELECT id,title,start_on,end_on,revision,created_at,updated_at FROM plans "
                               "WHERE start_on<=? AND end_on>=? "
                               "ORDER BY start_on DESC,updated_at DESC,id LIMIT ? OFFSET ?", (on, on, limit, offset))
        return [dict(row) for row in rows]

    @staticmethod
    def _plan_revision(req: dict) -> int:
        revision = req.get("expected_revision")
        if type(revision) is not int or revision < 1:
            raise StoreError("invalid_expected_revision")
        return revision

    @staticmethod
    def _plan_receipt(con: sqlite3.Connection, key: str, req: dict) -> dict | None:
        """Replay the original response before any current-state/revision checks."""
        previous = con.execute("SELECT * FROM plan_requests WHERE request_key=?", (key,)).fetchone()
        if previous:
            stored = json.dumps(json.loads(previous["request_payload"]), sort_keys=True, allow_nan=False)
            incoming = json.dumps(req, sort_keys=True, allow_nan=False)
            if stored != incoming:
                raise StoreError("request_key_conflict")
            return json.loads(previous["response"])
        return None

    @staticmethod
    def _record_plan_receipt(con: sqlite3.Connection, key: str, req: dict, response: dict) -> dict:
        con.execute("INSERT INTO plan_requests VALUES (?,?,?)",
                    (key, json.dumps(req, ensure_ascii=False), json.dumps(response, ensure_ascii=False)))
        return response

    @staticmethod
    def _plan_document(req: dict) -> dict:
        """Validate structure only; the host computes ingredients and shopping totals."""
        meals = req.get("meals")
        shopping = req.get("shopping_list")
        if not isinstance(meals, list) or not 1 <= len(meals) <= 93:
            raise StoreError("invalid_plan_meals")
        if not isinstance(shopping, list) or len(shopping) > 300:
            raise StoreError("invalid_shopping_list")
        result = {"meals": [], "shopping_list": []}
        slots = set()
        for meal in meals:
            if not isinstance(meal, dict) or set(meal) - {"on", "slot", "name", "servings", "details"}:
                raise StoreError("invalid_plan_meal_fields")
            on = date_field(meal, "on").isoformat()
            slot = text_field(meal, "slot", limit=100)
            if (on, slot.casefold()) in slots:
                raise StoreError("duplicate_plan_slot")
            slots.add((on, slot.casefold()))
            servings = meal.get("servings")
            if type(servings) is not int or not 1 <= servings <= 100:
                raise StoreError("invalid_servings")
            details = text_field(meal, "details", limit=12000)
            result["meals"].append({"on": on, "slot": slot, "name": text_field(meal, "name"),
                                    "servings": servings, "details": details})
        dates = [date.fromisoformat(meal["on"]) for meal in result["meals"]]
        if (max(dates) - min(dates)).days > 30:
            raise StoreError("plan_span_exceeds_31_days")
        for item in shopping:
            if not isinstance(item, dict) or set(item) - {"item", "quantity", "notes"}:
                raise StoreError("invalid_shopping_item_fields")
            notes = item.get("notes", "")
            if not isinstance(notes, str) or len(notes) > 2000:
                raise StoreError("invalid_shopping_notes")
            result["shopping_list"].append({"item": text_field(item, "item"),
                                             "quantity": text_field(item, "quantity", limit=1000),
                                             "notes": notes})
        notes = req.get("notes", "")
        if not isinstance(notes, str) or len(notes) > 8000:
            raise StoreError("invalid_plan_notes")
        result["notes"] = notes
        return result

    def _plan_save(self, con: sqlite3.Connection, req: dict) -> dict:
        key = text_field(req, "request_key", limit=200)
        replay = self._plan_receipt(con, key, req)
        if replay is not None:
            return replay
        title = text_field(req, "title")
        current = self._plan_get(con, req) if "id" in req else None
        if current and self._plan_revision(req) != current["revision"]:
            raise StoreError("plan_revision_conflict")
        document = self._plan_document({**req, "notes": req.get("notes", current["notes"] if current else "")})
        dates = [meal["on"] for meal in document["meals"]]
        stamp = now()
        if current:
            ident = current["id"]
            con.execute("UPDATE plans SET title=?,start_on=?,end_on=?,document=?,revision=revision+1,"
                        "updated_at=? WHERE id=?", (title, min(dates), max(dates),
                        json.dumps(document, ensure_ascii=False), stamp, ident))
        else:
            if "expected_revision" in req:
                raise StoreError("revision_requires_plan_id")
            ident = uuid.uuid4().hex
            con.execute("INSERT INTO plans VALUES (?,?,?,?,?,1,?,?)", (ident, title, min(dates), max(dates),
                        json.dumps(document, ensure_ascii=False), stamp, stamp))
        return self._record_plan_receipt(con, key, req, self._plan_get(con, {"id": ident}))

    def _plan_remove(self, con: sqlite3.Connection, req: dict) -> dict:
        key = text_field(req, "request_key", limit=200)
        replay = self._plan_receipt(con, key, req)
        if replay is not None:
            return replay
        current = self._plan_get(con, req)
        if self._plan_revision(req) != current["revision"]:
            raise StoreError("plan_revision_conflict")
        result = self._remove(con, "plans", req)
        return self._record_plan_receipt(con, key, req, result)

    def _export(self, con: sqlite3.Connection, req: dict) -> dict:
        return {"schema_version": 7, "household": self._household(con),
                "plans": [self._plan(row) for row in con.execute("SELECT * FROM plans ORDER BY id")],
                "preferences": [dict(r) for r in con.execute("SELECT * FROM preferences ORDER BY id")],
                "recipes": [self._recipe(r) for r in con.execute("SELECT * FROM recipes ORDER BY id")],
                "meals": self._meals(con, list(con.execute("SELECT * FROM meals ORDER BY id")), all_members=True)}

    def _import(self, con: sqlite3.Connection, req: dict) -> dict:
        key = text_field(req, "request_key", limit=200)
        data = req.get("data")
        try:
            encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise StoreError("invalid_import_json") from None
        if len(encoded) > 20 * 1024 * 1024:
            raise StoreError("invalid_import_size")
        digest = hashlib.sha256(encoded).hexdigest()
        previous = con.execute("SELECT * FROM import_requests WHERE request_key=?", (key,)).fetchone()
        if previous:
            if previous["snapshot_hash"] != digest:
                raise StoreError("request_key_conflict")
            return json.loads(previous["response"])
        data = validate_snapshot(data)
        household = self._household(con)
        occupied = con.execute(
            "SELECT 1 FROM members UNION ALL SELECT 1 FROM preferences UNION ALL SELECT 1 FROM observances "
            "UNION ALL SELECT 1 FROM recipes UNION ALL SELECT 1 FROM meals UNION ALL SELECT 1 FROM plans "
            "UNION ALL SELECT 1 FROM plan_requests UNION ALL SELECT 1 FROM meal_requests "
            "UNION ALL SELECT 1 FROM import_requests LIMIT 1").fetchone()
        if (occupied or household["onboarding"]["status"] != "pending" or
                any(household["locale"][field] is not None for field in ("country", "region", "timezone")) or
                household["locale"]["holiday_mode"] != "unknown"):
            raise StoreError("import_requires_empty_profile")
        incoming = data["household"]
        for member in incoming["members"]:
            con.execute("INSERT INTO members VALUES (?,?,?,?,?,?)",
                        tuple(member[k] for k in ("id", "label", "age_group", "allergy_status", "notes", "updated_at")))
        for pref in data["preferences"]:
            con.execute("INSERT INTO preferences (id,kind,target,notes,updated_at,member_id) VALUES (?,?,?,?,?,?)",
                        tuple(pref[k] for k in ("id", "kind", "target", "notes", "updated_at", "member_id")))
        for practice in incoming["observances"]:
            con.execute("INSERT INTO observances VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        tuple(practice[k] for k in ("id", "label", "kind", "schedule", "rules", "calendar",
                                                   "strictness", "active", "member_id", "notes", "updated_at")))
        for recipe in data["recipes"]:
            payload = {k: recipe[k] for k in ("name", "content", "tags", "source")}
            con.execute("INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?,?)",
                        (recipe["id"], recipe["name"], recipe["content"], json.dumps(recipe["tags"], ensure_ascii=False),
                         recipe["source"], recipe["created_at"], recipe["favorite"], uuid.uuid4().hex,
                         json.dumps(payload, ensure_ascii=False)))
        for meal in data["meals"]:
            payload = {k: meal[k] for k in ("kind", "name", "occurred_on", "recipe_id", "member_ids")}
            payload["member_ids"] = sorted(payload["member_ids"])
            internal_key = uuid.uuid4().hex
            con.execute("INSERT INTO meals VALUES (?,?,?,?,?,?,?,?)",
                        (meal["id"], meal["kind"], meal["name"], meal["occurred_on"], meal["recipe_id"],
                         meal["created_at"], internal_key, json.dumps(payload, ensure_ascii=False)))
            con.executemany("INSERT INTO meal_members VALUES (?,?)", [(meal["id"], m) for m in meal["member_ids"]])
            self._record_meal_receipt(con, internal_key, payload, {**meal, "member_ids": payload["member_ids"]})
        for plan in data["plans"]:
            document = {k: plan[k] for k in ("meals", "shopping_list", "notes")}
            con.execute("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)",
                        (plan["id"], plan["title"], plan["start_on"], plan["end_on"], json.dumps(document, ensure_ascii=False),
                         plan["revision"], plan["created_at"], plan["updated_at"]))
        con.execute("UPDATE onboarding SET status=?,updated_at=? WHERE singleton=1",
                    (incoming["onboarding"]["status"], incoming["onboarding"]["updated_at"]))
        loc = incoming["locale"]
        con.execute("UPDATE locale SET country=?,region=?,timezone=?,holiday_mode=?,updated_at=? WHERE singleton=1",
                    tuple(loc[k] for k in ("country", "region", "timezone", "holiday_mode", "updated_at")))
        result = {"imported": True, "counts": {k: len(incoming[k] if k in incoming else data[k])
                                              for k in ("members", "preferences", "observances", "recipes", "meals", "plans")}}
        con.execute("INSERT INTO import_requests VALUES (?,?,?)", (key, digest, json.dumps(result)))
        return result


def main() -> int:
    """Read one UTF-8 JSON object, emit one JSON envelope, exit nonzero on error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Override persistent user data directory")
    parser.add_argument("--request-file", type=Path, help="Read UTF-8 JSON from this file instead of stdin")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = args.request_file.read_text(encoding="utf-8-sig") if args.request_file else sys.stdin.buffer.read().decode("utf-8-sig")
        req = json.loads(raw)
        output = Store(args.data_dir).handle(req)
        code = 0
    except (StoreError, OSError, sqlite3.Error, ValueError) as exc:
        error = str(exc) if isinstance(exc, StoreError) else "storage_or_input_error"
        output, code = {"ok": False, "error": error}, 1
    print(json.dumps(output, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
