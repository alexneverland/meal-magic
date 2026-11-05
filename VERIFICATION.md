# Verification — 2026-11-05

Version: **0.5.1**, source preview proposed through pull requests. Work was
performed without subagents. No tagged release or agent-directory installation
is implied by the source repository. Review/merge state is recorded in the
corresponding pull request, not inferred from this report.

## Executed

- Windows, Python **3.14.10**: **105/105 unittest tests passed** for the instruction/reference reorganization.
- Windows, Python **3.12.10**: **105/105 unittest tests passed** for the instruction/reference reorganization.
- Five new installer tests cover the workflow-reference files in installations,
  upgrade/uninstall from the original five-file manifest, protection of modified
  and unknown legacy files, and refusal of partial reference manifests. The package
  test verifies the extracted installed reference bytes match the source package.
  The original workflow sections were compared verbatim after relocation, allowing
  only relative-link adjustments. Main SKILL.md shrank from 3,054 to 793 words
  (317 to 89 lines); the change is instruction organization, not schema behavior.
- Prior v0.5 member-history/review baseline: **100/100 tests passed** on Windows
  with Python 3.12.10 and 3.14.10. Those tests remain in the current suite.
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
  one query rather than one per event. Final schema version is 6. Receipts retain
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
- Repository validation checks required public files, local Markdown links, runtime
  imports against the standard library, and forbidden tracked paths in Git checkouts.
  It is a hygiene check, not an exhaustive security or secret-content audit.
- The 0.5.1 source ZIP was built and inspected against the exact 31-file public
  allowlist, with passing CRC verification and a matching SHA-256 sidecar. Generated
  archives and caches are not committed. `git diff --check` passed.
- GitHub CI is configured for Windows/Linux/macOS with Python 3.10/3.14 and a stable
  `Required checks` gate. CI results belong to the specific commit/PR check runs;
  configuration alone does not establish a pass on those platforms.
- The app's project listing confirmed **Meal Magic**, path **C:\Meal Magic**.

## Per-agent evidence

### Agreed conversational test scope

The project owner will perform the live acceptance scenarios in **Codex and
Antigravity**, with isolated synthetic profiles. Those conversations are still
pending; this section records responsibility and scope, not completed results.

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
| Codex | `codex-cli 0.166.0-alpha.6` | Version command; documented path mapping; install/update/uninstall and installed helper in a temporary synthetic project. The current Codex chat authored and ran the tests. | Fresh-session automatic discovery, explicit invocation, and conversational behavior after installation. |
| Claude Code | `2.1.159` | Version command; documented path mapping; install/update/uninstall and installed helper in a temporary synthetic project. | Live model session, automatic discovery, slash-command invocation, and conversational behavior. Current official docs may describe features newer than this local version. |
| Antigravity CLI | `1.0.8` | Version command; documented path mapping; install/update/uninstall and installed helper in a temporary synthetic project. | Live CLI/App/IDE invocation, automatic discovery, and conversational behavior. |
| Custom agents | No specific host | Explicit-directory installation and execution of the shared JSON CLI in a temporary destination. | Host registration, model behavior, tool permissions, or compatibility with any arbitrary custom agent. |

No external model sessions were launched. No global agent installation or agent
configuration was changed. Installation-layout tests are not evidence that each
model follows the instructions. [Agent scenarios](tests/agent-scenarios.md) specify
the live checks still needed before claiming tested conversational compatibility.
No live-agent sessions were launched for the planning update. New conversational
plan/shopping-list scenarios are provided for the owner, not recorded as passed.
No live-agent sessions were launched for the member-history update either.
Audience continuity, separate dishes, temporary ingredients and correct assignment
from actual conversational reports have additional manual acceptance scenarios;
their presence is not evidence that a host model passed them. There is no pantry
storage, quantity/expiry tracking, medical inference or automatic meal attendance.
No live-agent reference-routing evaluation was performed for the instruction
reorganization. Source-section preservation and installer/link/package tests do
not prove unchanged host-model behavior; fresh-session comparison scenarios remain
for the owner in Codex and Antigravity.

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
