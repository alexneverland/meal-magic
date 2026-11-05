# Verification — 2026-11-05

Version: **0.3.0**, initial source preview proposed through a PR. Work was
performed without subagents. No tagged release or agent-directory installation
is implied by the source repository. The implementation remains under review
until the initial PR is explicitly merged.

## Executed

- Windows, Python **3.14.10**: **55/55 unittest tests passed**.
- Windows, Python **3.12.10**: **55/55 unittest tests passed**.
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
- The package test built a ZIP from the explicit public-file allowlist, checked its
  exact entries and CRCs, extracted it, installed from the extracted manager, and
  ran that installed helper against an empty synthetic profile. The installed
  skill includes its MIT license. No caches or databases were packaged.
- Repository validation checks required public files, local Markdown links, runtime
  imports against the standard library, and forbidden tracked paths in Git checkouts.
  It is a hygiene check, not an exhaustive security or secret-content audit.
- GitHub CI is configured for Windows/Linux/macOS with Python 3.10/3.14 and a stable
  `Required checks` gate. CI results belong to the specific commit/PR check runs;
  configuration alone does not establish a pass on those platforms.
- The app's project listing confirmed **Meal Magic**, path **C:\Meal Magic**.

## Per-agent evidence

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
