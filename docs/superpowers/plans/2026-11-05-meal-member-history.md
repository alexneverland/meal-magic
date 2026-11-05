# Meal Member History Implementation Plan

> Execute natively in this session, without subagents, as required by AGENTS.md and the owner.

**Goal:** Record explicitly reported members on actual meal events and retrieve each member's history.

**Architecture:** Add a schema-5 meal/member relation with foreign keys. Keep the shared standard-library JSON CLI and host-model reasoning. Ingredients remain conversational only; no pantry, quantities or expiry storage is added.

**Tech Stack:** Python 3.10+, SQLite, unittest.

**Spec:** Owner's approved conversation scope: continue with known diners without repetitive questions; clarify material ambiguity; support separate dishes for one member and the rest of the household using explicitly stated needs. Never infer actual attendance from a suggestion or from the default household audience.

## Global Constraints

- Use only temporary synthetic data, no real profiles or agent installations.
- Eaten-event members mean actual diners; cooked-event members mean explicitly reported recipients, not cooks or proof of eating.
- Optional `member_ids` defaults to an empty list meaning unspecified. Existing events stay unspecified.
- Member IDs form an unordered set (canonical sorted output); duplicate, malformed, over-100 and unknown IDs fail atomically.
- Preserve schema-4 retry payloads, IDs and existing data; deletion of a linked member refuses rather than cascading history.
- `meal-list` accepts optional `member_id`, filters before limiting, and excludes unspecified events from personal history.
- Keep plan storage, restrictions, installation safety and pantry behavior unchanged.

## Review Focus

- Legacy request keys replay after migration without conflicts or duplicate events.
- Reordered member IDs replay, changed membership conflicts.
- Invalid membership and failed relation writes roll back the event and any migration.
- Removing an event removes only its membership links; removing a linked member refuses.
- A member filter does not include another person's or unspecified history and applies before pagination limits.

## Task 1: Storage and regression tests

**Files:** `skills/meal-magic/scripts/meal_store.py`, `tests/test_meal_members.py`; schema expectations in household/observance/plan tests.

- [x] Add tests for scoped events, filtering, retries, restart persistence, migration preservation/rollback, member removal and failed relation writes.
- [x] Run `python -m unittest discover -s tests -p test_meal_members.py -v` and confirm missing-feature failures.
- [x] Add schema-5 migration, membership validation/serialization, atomic meal logging, compatible replay and member filtering/deletion protection.
- [x] Run focused and full unittest suites; preserve old schema fixture coverage.

## Task 2: Skill, documentation and distribution

**Files:** skill instructions and CLI reference, README, SECURITY, VERIFICATION, agent scenarios, VERSION, package builder/test.

- [x] Describe audience continuity, separate dishes, explicit attendance, member history and temporary ingredients.
- [x] Update source preview to 0.5.0 and schema migration/rollback documentation.
- [x] Extend extracted-package smoke test to retrieve member-scoped history after update.
- [x] Run repository checks, full tests, whitespace checks and source ZIP build/CRC/allowlist inspection.
Delivery: review the full diff, stage only named files, commit/push the branch and propose a PR to main. Do not merge or publish a release.
