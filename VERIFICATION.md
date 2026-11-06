# Verification — 2026-11-05

Version: **0.6.2**; release preparation authorized by the project owner.
Work was performed without subagents.
Review/merge state is recorded in the corresponding pull request. Release assets
and the published tag identify the released commit.

## Executed

- Current Windows release candidate: Python **3.14.10** and **3.12.10** each completed
  **159 unittest tests: 158 passed, 1 conditional MSIX probe skipped**, no failures.
  Repository validation and `git diff --check` passed. The 0.6.2 ZIP has the exact
  33-file allowlist, matching source bytes, passing CRCs and a matching SHA-256
  sidecar. The published tag/release page identifies the final release commit.
- Windows profile-discovery update: 39 new synthetic tests cover native/MSIX
  candidate discovery, populated-vs-empty selection, explicit conflict choice,
  duplicate physical/logical sources, receipts, WAL, schema-1 copy-only upgrades,
  staging/publication failure, concurrent subprocess startup, source drift,
  malformed origins, missing/replaced shared DBs, inaccessible candidates, and
  explicit/environment overrides. Source files and installed user skills were
  not used as test fixtures. The new default is outside AppData.
  One conditional OS probe runs only when newly created AppData files are actually
  redirected by the current process; otherwise it is explicitly skipped. Native
  volume/discovery coverage runs separately on Windows without that prerequisite.
  The 39-test discovery suite also passed on Windows/Python 3.11 (38 passed, the
  same conditional probe skipped). A CI-found Python 3.10 pathlib namespace-parent
  incompatibility is covered by a regression that ignores only synthetic device
  namespace ancestors, retaining checks on every real directory below the volume.
- The owner-authorized pre-upgrade check found that a volume-GUID spelling still
  opened the MSIX-private file on this Windows installation. The final resolver
  therefore uses physical handle paths for source identity and refuses initial
  automatic adoption when the native legacy view is hidden, requesting one explicit
  source choice instead. It does not claim that a volume alias bypasses MSIX.
- Owner-authorized Codex upgrade: the known household was explicitly selected,
  adopted into the outside-AppData shared directory, and reopened with the installed
  0.6.2 helper. The complete public export matched a pre-upgrade SQLite backup and
  the original source file hash was unchanged. Private backups were made before
  and after adoption. No household details or private paths are included here.
  This is authorized actual use, separate from synthetic development tests.
- On 2026-11-06, the owner shared successful Antigravity uninstall/reinstall output
  for v0.6.2 and the subsequent context response. Without a data-directory override,
  it used the shared Windows default, returned the same physical database path and
  profile ID recorded by Codex, and retrieved existing household/preferences with
  onboarding completed. No JSON import or new household registration was needed.
  The uninstall report also stated that the legacy database hash was unchanged.
  These are owner-reported actual-use results, not independently captured
  Antigravity process traces. Personal member details, IDs, hashes and machine paths
  from the supplied output are deliberately excluded. Broader Antigravity meal
  conversations and live cross-host writes are not established by this read check.
- An additional extracted-package integration installs the real manager/helper
  for Codex and Antigravity under one temporary synthetic Windows user home,
  adopts a synthetic legacy profile, writes through one host and reads through
  the other, and verifies the same shared identity and unchanged legacy source.
  This is CLI/storage integration, not two live model sessions.
- The current 33-file ZIP includes the new discovery tests. Earlier
  0.6.1 evidence below remains scoped to that version; it does not certify the
  upgraded live-agent discovery flow. Development tests used only synthetic data;
  the owner-authorized actual Codex upgrade and owner-reported Antigravity clean
  reinstall/shared-profile acceptance are recorded separately above.

- Windows, Python **3.14.10**: **119/119 unittest tests passed** for the integrated import/reference update.
- Windows, Python **3.12.10**: **119/119 unittest tests passed** for the integrated import/reference update.
- Five new installer tests verify workflow reference installation, legacy manifest
  update/uninstall, protection of local edits/unknown files and refusal of partial
  manifests. The package verifies installed reference bytes. Workflow relocation
  preserves the original detailed instructions; complete live reference-routing
  comparison scenarios remain untested.
- Fourteen new import tests verify complete cross-domain round trips preserving
  public IDs, exact Unicode/recipe content, favorites, member ownership, timestamps
  and plan revisions; schema-6 compatibility; type/date/field/reference validation;
  duplicate labels/IDs; nonfinite values, invalid Unicode and size/record limits;
  refusal of records, metadata or receipts in destination profiles; rollback on
  last-write failure and failed schema-6 migration; and concurrent subprocess
  retries that do not overwrite later edits. Imported internal keys are new and
  ordinary plan updates/event removal continue working. Text containing malicious
  instructions remains exact recipe data; no model execution is implied.
  The documented 10,000-record boundary is exercised by importing and exporting
  10,000 synthetic preferences without truncation.
- Prior v0.5 member-history/review baseline: **100/100 tests passed** on Windows
  with Python 3.12.10/3.14.10. The current suite includes those tests.
- Nineteen new synthetic membership tests cover separate dishes, independent
  cooked/eaten membership, unspecified attendance, per-member filtering before
  limits, reordered/conflicting retries, malformed/unknown IDs, the 100-member
  boundary, subprocess restarts and concurrent retries, linked-member deletion
  refusal, event-link removal, and atomic rollback on a failed relation write.
  Schema-4 migration preserves recipes, restrictions, members, locale, observances,
  onboarding, plans and their mutation receipts. Old meal request keys remain
  retryable without rewriting historical payloads or inventing participants.
  Failed writes and a denied migration index creation roll back to schema 4.
  Review regressions verify that deleted events never return on old retries,
  including after member removal; schema-5 previews backfill durable receipts;
  denied backfill/receipt writes roll back; a 120-event export loads membership in
  one query rather than one per event. This feature introduced schema 6. Receipts retain
  original meal text/member IDs after active removal and are excluded from export.
- Prior v0.4 planning/review baseline: **81/81 tests passed** on Windows with
  Python 3.12.10 and 3.14.10. The current suite includes those tests.
- Prior v0.3 Windows, Python **3.11.9**: **11/11 installer tests passed**, including actual
  junction target/ancestor/content and project-alias regressions. The new regressions
  first reproduced failures against the previous implementation on Python 3.11.
  The fix uses `lstat`/Windows reparse attributes, not Python-3.12-only APIs.
- The bundled Codex `skill-creator` `quick_validate.py` reported **Skill is valid!**
  for the actual `skills/meal-magic` directory.
- Storage was exercised through direct calls and real subprocess CLI calls with
  isolated temporary data, including UTF-8/BOM request files and Greek text.
- Tests verified persistent preferences, correction/removal, exact recipe content
  (including boundary newlines), independent same-name versions, favorites, search
  by content/tags/case/accents, cooked/eaten separation, repeat meals, idempotent
  retries, conflicting retries, unknown inputs/IDs, calendar-date validation,
  unpruned history, corrupt/foreign/unsupported database refusal, explicit CLI
  failures, and concurrent writes from eight processes.
  Preference qualifications survive omitted notes on exact repeats and ownership
  updates; clearing requires an explicit empty string, and invalid null rolls back.
- Twenty-one plan tests verify separate plan storage, exact process-restart retrieval,
  per-day replacement with a full revised shopping list, revision conflicts,
  simultaneous writers, historical receipt replay after updates/deletion, explicit
  removal, malformed nested payloads, notes preservation, date overlap listing,
  migration from schema 3 preserving existing domains, and transactional rollback
  on receipt failure or a failed write during migration. Quantities are text and
  were not interpreted/summed by Python; ingredient totals remain host-model work.
  Review regressions check JSON-type-sensitive retries (including booleans vs
  integers/floats), unknown-field error precedence, complete paging over 105 plans,
  invalid offsets, and the actual traced listing queries' indexed execution without
  temporary ordering sorts. Existing schema-4 previews gain the listing index
  without changing plan data.
- Household tests verified persistent members/stages, independent per-member
  preferences, partial member updates, nonrepeating onboarding state storage,
  skipping/restarting without data loss, explicit unknown-vs-none-reported allergy
  state, allergy reassignment/removal, and refusal to silently delete member
  restrictions. They verified schema-1 migration without loss of IDs/content,
  favorites/history and full rollback on a simulated migration failure. They do
  not prove the model asks the introduction questions correctly. A missing
  onboarding record fails explicitly without resetting other household records.
- Locale/observance tests verified empty/unknown defaults, country changes clearing
  stale region/timezone, persistent explicit locale, custom free-text schedules
  and rules, independent member scopes, idempotent saves, partial updates,
  disabling/removing/reassigning practices, preserving active rules when occasion
  ideas are off, explicit errors, schema-2 migration preserving the household and
  completed onboarding, and rollback on a simulated schema-2 migration failure.
  Explicit date context was checked for exact ISO weekdays and invalid calendar
  dates, without inferring active observances or choosing the user's local date.
  They do not verify that a model applies a religious calendar correctly.
- Installer tests copied and executed the actual skill in temporary destinations
  for Codex, Claude Code, Antigravity, and a custom agent. They verified lifecycle
  operations, documented path mapping, unchanged external personal data, refusal
  of modified/unmanaged/extra content, and rollback after a simulated update error.
  Three additional Windows-only tests create real junctions between owned temporary
  paths and verify rejection without changing external synthetic installations.
  Those cases are skipped on Linux/macOS, where Windows junctions do not exist.
- The package test built a ZIP from the explicit public-file allowlist, checked its
  exact entries and CRCs, extracted it, installed from the extracted manager, and
  ran that installed helper against an empty synthetic profile. The installed
  skill includes its MIT license. No caches or databases were packaged.
  The planning update also saves a plan through the extracted installed helper,
  updates that installation and retrieves the unchanged plan from external data.
  The member-history update includes the new test module in the ZIP, records a
  member-scoped eaten event through the extracted installed helper, updates that
  temporary installation, and retrieves the same event by member after restart.
  The JSON import update exports that extracted-package synthetic profile, restores
  it into a different empty temporary directory with the installed helper, and
  verifies the complete export matches after another subprocess restart.
- Repository validation checks required public files, local Markdown links, runtime
  imports against the standard library, and forbidden tracked paths in Git checkouts.
  It is a hygiene check, not an exhaustive security or secret-content audit.
- The 0.6.1 source ZIP was built and inspected against the exact 32-file public
  allowlist, with passing CRC verification and a matching SHA-256 sidecar. Generated
  archives and caches are not committed. `git diff --check` passed.
- GitHub CI is configured for Windows/Linux/macOS with Python 3.10/3.14 and a stable
  `Required checks` gate. CI results belong to the specific commit/PR check runs;
  configuration alone does not establish a pass on those platforms.
- The app's project listing confirmed **Meal Magic**, path **C:\Meal Magic**.

## Per-agent evidence

### Owner-authorized actual use and remaining test scope

On 2026-11-05, the owner explicitly requested installation for actual use, followed
by a cooking conversation. This was separate from development testing; no real
profile was used by the automated test suite. The requested v0.6.1 installation
used the owner's Codex personal skill directory.
All nine installed files matched the source, and the installed CLI executed.
Explicit invocation loaded the skill; the live conversation read the required
references, initialized context, saved user-declared household/preferences and
reused them before generating a quick recipe from supplied ingredients. The owner
confirmed successful testing. In subsequent owner-shared conversational transcripts,
the agent scoped a temporary food dislike to one household member without calling
it an allergy, tailored shared-meal suggestions, and kept a proposed future meal
out of cooked/eaten history (reported empty by the agent). The owner separately
confirmed successful removal of the temporary test preference. These are
owner-reported conversational observations, not independent inspection of the
SQLite rows or coverage of all manual acceptance scenarios. Personal details from that session are intentionally
excluded from this report, repository and release assets.

This owner-authorized actual-use acceptance check is evidence for basic Codex use,
not a synthetic development test or completion of the full acceptance suite
or a controlled before/after reference-routing comparison. The exact desktop/model
version for that live session was not captured. Fresh-chat automatic skill
invocation, broader Antigravity meal conversations and remaining manual scenarios
are still pending; Antigravity default-profile retrieval after a clean reinstall
is now covered by the owner-reported v0.6.2 evidence above.
Automated development tests continue to use only synthetic temporary profiles.

**Claude Code remains conversationally untested by the maintainers.** Its
installation instructions and shared storage/lifecycle tools are provided, and
Claude Code users are welcome to submit synthetic reproductions and compatibility
reports. Community reports must identify the tested host/model/version and are
not automatically treated as independently verified maintainer results.

Custom-agent support remains an integration contract requiring validation in
each host. There is no claim that all agents discover or follow this skill.

### Observed evidence

| Host | Local version observed | Actually tested | Not tested |
|---|---|---|---|
| Codex | Earlier CLI observation: `codex-cli 0.166.0-alpha.6`; live desktop/model version not captured | Synthetic storage/lifecycle checks; owner-confirmed cooking/profile smoke test; owner-authorized v0.6.2 shared-storage upgrade with complete public-export/backup comparison and unchanged original source hash. | Fresh-session automatic skill invocation and the complete conversational acceptance suite. |
| Claude Code | `2.1.159` | Version command; documented path mapping; install/update/uninstall and installed helper in a temporary synthetic project. | Live model session, automatic discovery, slash-command invocation, and conversational behavior. Current official docs may describe features newer than this local version. |
| Antigravity | Earlier CLI observation: `1.0.8`; actual-use host/model version not captured | Synthetic storage/lifecycle checks; owner-reported clean v0.6.2 uninstall/reinstall and default-profile retrieval matched Codex physical path/profile ID and recovered existing household/preferences with completed onboarding. | Automatic skill invocation, broader meal conversations, live cross-host writes, and independently captured Antigravity process traces. |
| Custom agents | No specific host | Explicit-directory installation and execution of the shared JSON CLI in a temporary destination. | Host registration, model behavior, tool permissions, or compatibility with any arbitrary custom agent. |

The owner explicitly authorized the personal Codex installation and live use
described above; no agent configuration was changed. Installation-layout tests
alone are not evidence that each model follows the instructions.
[Agent scenarios](tests/agent-scenarios.md) specify the broader live checks.
No live-agent sessions were launched for the planning update. New conversational
plan/shopping-list scenarios are provided for the owner, not recorded as passed.
No live-agent sessions were launched for the member-history update either.
Audience continuity, separate dishes, temporary ingredients and correct assignment
from actual conversational reports have additional manual acceptance scenarios;
their presence is not evidence that a host model passed them. There is no pantry
storage, quantity/expiry tracking, medical inference or automatic meal attendance.
No live-agent JSON import conversation was executed. Added manual scenarios cover
authorized source/destination selection, refusal to overwrite, receipt replay and
the distinction between active-data transfer and whole-directory backup.

The local baseline above used Windows/Python 3.12 and 3.14. Other local Python
versions and macOS/Linux were not executed locally. The code targets Python
3.10+; check the specific commit's GitHub CI results for the configured
Windows/Linux/macOS and Python 3.10/3.14 matrix. A configured job is not a passing
job. All storage/lifecycle tests use synthetic temporary records, never personal data.

No live holiday-date or local fasting-time lookup was performed. The package has
no bundled holiday database or date engine for religious calendars. The skill
instructs the host to use available browsing/calendar tools or user-provided dates,
cite sources and disclose uncertainty. Real source choice, calendar interpretation,
weekday matching and host-memory reuse remain live-agent evaluation items.

## Documentation sources

Official pages were opened and checked on 2026-11-05:

- [Codex / Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code / Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [Antigravity / Agent skills](https://antigravity.google/docs/skills)
- [Antigravity / Customization discovery](https://antigravity.google/docs/customization-discovery/)

The package is standalone. No external application's code, configuration,
database or personal records is required, imported or bundled.

The Codex smoke test exercised loading workflow references during normal use.
Source preservation and link/installer/package checks do not prove unchanged model
behavior; controlled fresh-session comparison scenarios remain for Codex and
Antigravity.
