# JSON Import Implementation Plan

**Approved scope:** Restore only into an empty profile; no merging or overwriting existing household data. Work natively without subagents. Propose a PR to main; no merge authorization is implied for this new feature.

**Design:** Add `import` with `data` (the result object of export) and `request_key`. Accept current schema-6 and schema-7 snapshots; reject other versions explicitly. Validate a bounded structured snapshot, preserve public IDs, timestamps, plan revisions and member/recipe relationships, and insert everything in one transaction. Treat strings as data. Do not read arbitrary source paths or any personal files automatically.

**Compatibility:** Schema 7 adds an import receipt table. A matching key/snapshot replays the original success even after later changes; a changed snapshot conflicts. Imported recipes/meals get new internal request keys; original internal receipts are absent from export and cannot be restored. Rebuild receipts for active imported meals only. Preserve source public fields exactly; inconsistent restrictions or dangling links fail instead of guessing or silently repairing data.

**Empty destination:** No domain records, plan/meal/import receipts, changed locale or non-pending onboarding. Default locale/onboarding timestamps alone do not make a fresh profile nonempty. An existing initialized empty profile is allowed. No delete/reset/force flag.

**Limits:** 20 MiB canonical JSON, at most 10,000 records per domain, bounded strings using existing CLI limits. IDs are unique per domain; labels unique for members; referenced IDs must exist. Validate booleans/integers without coercion and reject unknown/missing fields, nonfinite values and malformed dates/timestamps.

## Tasks

- [x] Write synthetic tests for complete cross-domain round trip, Unicode/exact content, source schema 6/7, invalid fields/references/types, nonempty destinations, rollback, retries/concurrency, restart and extracted-package import.
- [x] Confirm tests fail before implementing. Add snapshot validation and schema-7/import transaction integration to the shared helper, preserving the existing installation file manifest.
- [x] Update shared skill, CLI reference, README, SECURITY and verification; source preview 0.6.0. Keep validation inside the existing helper and include the new tests in the package allowlist.
- [x] Run repository checks, full unittest suites on Python 3.12/3.14, whitespace checks, and build/inspect ZIP against source bytes/allowlist/CRC/checksum.
Delivery: review diff, stage named files, push feature branch, propose PR and inspect CI/reviews. Do not merge without a separate instruction.

## Review focus

No source text executes; failed imports leave no partial domain state or receipt. Retried imports must not overwrite later edits. Receipt-only/locale-only/onboarding-only destinations are not empty. Source allergen ownership is preserved, never inferred. Hidden source receipts cannot be restored from a public export.
