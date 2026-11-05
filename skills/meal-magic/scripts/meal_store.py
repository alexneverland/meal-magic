#!/usr/bin/env python3
"""Meal Magic's local JSON-in/JSON-out storage boundary (Python 3.10+)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import unicodedata
import uuid
from datetime import date, datetime, timezone
from typing import Any

VERSION = "0.4.0"
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
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "MealMagic"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/MealMagic"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "meal-magic"


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
        self.data_dir = Path(data_dir).expanduser().resolve() if data_dir else default_data_dir().resolve()
        install = Path(__file__).resolve().parents[1]
        if self.data_dir == install or install in self.data_dir.parents:
            raise StoreError("data_directory_inside_skill")
        self.path = self.data_dir / "meal-magic.sqlite3"

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
            elif version != 4:
                raise StoreError("unsupported_schema_version")
            return con
        except Exception:
            con.close()
            raise

    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        """Execute one explicit structured action; never infer conversational intent."""
        actions = {
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
            "meal-log": (self._meal_log, {"kind", "name", "occurred_on", "recipe_id", "request_key"}),
            "meal-list": (self._meal_list, {"limit", "kind"}),
            "meal-remove": (self._remove_meal, {"id"}),
            "plan-save": (self._plan_save, {"id", "expected_revision", "request_key", "title",
                                            "meals", "shopping_list", "notes"}),
            "plan-get": (self._plan_get, {"id"}),
            "plan-list": (self._plan_list, {"on", "limit"}),
            "plan-remove": (self._plan_remove, {"id", "expected_revision", "request_key"}),
            "export": (self._export, set()),
        }
        if not isinstance(req, dict) or not isinstance(req.get("action"), str):
            raise StoreError("request_must_have_action")
        action = req["action"]
        if action not in actions:
            raise StoreError("unknown_action")
        fn, allowed = actions[action]
        if set(req) - allowed - {"action"}:
            raise StoreError("unknown_fields")
        con = self._connect()
        try:
            with con:
                result = fn(con, req)
            return {"ok": True, "result": result}
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
    def _meal(row: sqlite3.Row) -> dict:
        result = dict(row)
        result.pop("request_key", None)
        result.pop("request_payload", None)
        return result

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
        if recipe_id is not None:
            if not isinstance(recipe_id, str) or not con.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
                raise StoreError("recipe_not_found")
        payload = {"kind": kind, "name": text_field(req, "name"), "occurred_on": occurred_on, "recipe_id": recipe_id}
        previous = self._replayed(con, "meals", key, payload)
        if previous:
            return self._meal(previous)
        ident = uuid.uuid4().hex
        con.execute("INSERT INTO meals VALUES (?,?,?,?,?,?,?,?)",
                    (ident, kind, payload["name"], occurred_on, recipe_id, now(), key,
                     json.dumps(payload, ensure_ascii=False)))
        return self._meal(con.execute("SELECT * FROM meals WHERE id=?", (ident,)).fetchone())

    def _meal_list(self, con: sqlite3.Connection, req: dict) -> list[dict]:
        limit = limit_field(req)
        kind = req.get("kind")
        if kind is not None and kind not in ("cooked", "eaten"):
            raise StoreError("invalid_meal_kind")
        return [self._meal(r) for r in con.execute(
            "SELECT * FROM meals WHERE (? IS NULL OR kind=?) ORDER BY occurred_on DESC, created_at DESC, id LIMIT ?",
            (kind, kind, limit))]

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
        rows = con.execute("SELECT id,title,start_on,end_on,revision,created_at,updated_at FROM plans "
                           "WHERE (? IS NULL OR (start_on<=? AND end_on>=?)) "
                           "ORDER BY start_on DESC,updated_at DESC,id LIMIT ?", (on, on, on, limit_field(req)))
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
            if json.loads(previous["request_payload"]) != req:
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
        return {"schema_version": 4, "household": self._household(con),
                "plans": [self._plan(row) for row in con.execute("SELECT * FROM plans ORDER BY id")],
                "preferences": [dict(r) for r in con.execute("SELECT * FROM preferences ORDER BY id")],
                "recipes": [self._recipe(r) for r in con.execute("SELECT * FROM recipes ORDER BY id")],
                "meals": [self._meal(r) for r in con.execute("SELECT * FROM meals ORDER BY id")]}


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
