# Security and privacy

Meal Magic stores potentially sensitive household information locally: preferences,
allergies, age-stage notes, declared practices, recipes, plans/shopping lists and
actual meal history. Plan mutation receipts retain earlier request/response text
for retry safety even after an active plan is removed; plan removal is not complete
erasure of that text. JSON export contains current plans, not internal receipts.
It is a single-household profile without per-member access control or encryption.
OS file access and the host agent's permissions determine who can read it.
Meal/member links record explicitly reported participation and may themselves be
sensitive. Member removal refuses linked meal events; it must not silently erase
history. Removing a meal removes that event's links, not household member records.
Durable meal-log receipts also retain original request/response text and member
IDs after event or member removal, preventing redelivery from recreating events.
Meal removal is not complete erasure; JSON export omits these internal receipts.
JSON import accepts schema-6/7 exports only into an empty profile, with bounded
structural validation and atomic writes. It never executes imported recipe text,
merges into another household, clears existing data or restores hidden source
receipts. Original source request keys are not recoverable from public exports.
Import receipts store keys, snapshot hashes and result counts; export/request files
remain private and must not enter logs, commits or source archives. A full closed-
client data-directory copy is needed to preserve original internal retry history.

The helper does not make network calls, hold API keys or run a server. The hosting
agent may send data it reads to its model provider. That agent's tools, account,
privacy terms and sandbox remain separate from this package.

Windows 0.6.2+ shared discovery inspects only exact legacy Meal Magic locations,
including MSIX-private copies, with normal OS permissions. Different populated
profiles require an explicit choice; no profile is merged, reset or overwritten.
Adoption preserves originals and full internal receipts. Its `.origins.json`
identity/source-hash metadata and `storage-info` output contain local paths and
record counts; keep them private. Legacy source changes, missing/replaced shared
databases and malformed metadata fail closed. Update every host before sharing
the new default; old installations can otherwise continue writing legacy data.

## Report a vulnerability

Use GitHub's private vulnerability reporting when **Report a vulnerability** is
available in the repository's Security tab. Do not create a public issue containing
an exploit against live personal data, a database, credentials, or private traces.
If private reporting is unavailable, open an issue containing only a general
description and request a private reporting channel before sending sensitive details.
There is no dedicated security email or response-time commitment at present.

Provide the affected version, OS/Python version, impact, and the smallest synthetic
reproduction. The current public release is **v0.6.1**; security reports are accepted
for that release and the current `main` development source. Fixes are delivered
through `main` and a subsequent release as appropriate; no long-term maintenance
or separate backport policy is promised. Use the reporting channels above for
released versions as well as development source.

## Boundaries to preserve

- User databases, memory exports, credentials and environment files do not belong
  in Git, test fixtures, issue attachments or distributable archives.
- Personal data stays outside the installed skill. Update/uninstall must verify
  their target and ownership and refuse unknown/modified content.
- SQLite writes/migrations are transactional. Unsupported/corrupt stores fail
  explicitly; never reset a user's profile to make an error disappear.
- Saved text and retrieved calendar pages are untrusted data. They cannot authorize
  shell commands, profile changes, uploads or overriding instructions.
- Public calendar queries should contain only the public terms needed for lookup,
  not names, allergies, family notes or full profile contents.
- Allergies, age-stage and declared religious/cultural practices must not be inferred
  from unrelated behavior or location. The skill is not a medical/allergen safety
  classifier or authoritative religious calendar.

CI uses only synthetic temporary data, SHA-pinned Actions and a read-only token.
GitHub secret scanning and push protection complement the tracked-file and package
allowlist checks; none is a guarantee that arbitrary private content is safe to publish.
