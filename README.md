# Meal Magic

A portable cooking skill that uses **your agent's model** to suggest meals,
remember food preferences and restrictions, keep an actual meal history, and
save recipes and favorites. One shared Python core works with Codex, Claude Code,
Antigravity, and custom agents that can load instructions and execute local tools.

**Version 0.6.1 — source preview, no tagged release yet.** Agent installation layouts
are documented; live model-session compatibility is not yet certified. See
[VERIFICATION.md](VERIFICATION.md) for exactly what was tested.

## Agent testing status

Our conversational acceptance tests will run in **Codex and Antigravity**, using
isolated synthetic household profiles. This is the agreed test plan, not a claim
that those conversations have already passed.

| Host | Live conversational testing | Evidence so far |
|---|---|---|
| Codex | Planned tests by the maintainers | Storage/lifecycle tests and installation-path checks; live skill discovery and conversations still pending |
| Antigravity | Planned tests by the maintainers | Storage/lifecycle tests and installation-path checks; live App/CLI/IDE conversations still pending |
| Claude Code | Not tested conversationally by the maintainers; community reports welcome | Documented installation and tested storage/lifecycle path; no verified live-model behavior |
| Custom agents | Each integration needs its own validation | Shared JSON CLI and explicit-directory installer tested; no blanket host compatibility claim |

Passing Python tests or CI does not verify how a host model follows the skill.
Claude Code users can try the documented integration and report reproducible
problems with synthetic examples through [issues](https://github.com/alexneverland/meal-magic/issues).
See [the acceptance scenarios](tests/agent-scenarios.md) and
[reporting guidance](CONTRIBUTING.md#reporting-agent-behavior).

## What it remembers

- Ongoing likes, dislikes, prohibited foods/ingredients, stated allergies, and
  dietary patterns, linked to the relevant household member when known. The model
  applies the diners' restrictions before suggesting or recommending food.
- Household members, including explicitly stated young-child/older-adult age
  groups, optional approximate age/needs notes, and first-use introduction status.
- User-stated country/region, interest in local food occasions, and declared
  holiday/fasting/tradition schedules and rules, per member or household-wide.
- Meals actually **cooked** and meals actually **eaten**, as separate events,
  with optional explicitly reported members and per-member history.
- Complete saved recipes, including multiple versions with the same name, and
  favorites identified by stable IDs.
- Saved multi-day meal plans and their consolidated shopping lists, kept together
  with revision checks and separately from actual meal history.

Suggestions remain conversation content; plans can be saved when requested.
Neither suggestions nor saved plans are actual meal history.
Saving, viewing, or favoriting a recipe never records it as cooked or eaten.
Recent actual meals help the model offer variety while allowing requested repeats
and leftovers. History is not automatically deleted.

The model understands the conversation, including ingredient meaning and dietary
constraints. The Python helper validates structured requests and stores data;
it does not classify intent with phrase lists, infer allergies, or verify that a
recipe is safe for a particular diet. Food restrictions also apply when recommending
old favorites; exact retrieval preserves the original and flags known conflicts.

## Requirements

- Python **3.10+**, including standard-library `sqlite3`. No `pip install` step.
- A working local agent with file access and permission to execute Python.
- Your existing agent account/model setup. This skill adds no model API key,
  subscription, AI service, MCP server, embeddings, or other application dependency.

The storage code makes no network calls. The model runs under the hosting agent's
existing terms, costs, and privacy settings. Data read by a cloud-backed agent may
be sent to that model provider. Local storage does not mean offline inference or
encrypted data. The single-user SQLite file uses normal OS file permissions.

## Get the source

Repository: [alexneverland/meal-magic](https://github.com/alexneverland/meal-magic).

Use `main` for the merged source:

```text
git clone https://github.com/alexneverland/meal-magic.git
cd meal-magic
python --version
python -m unittest discover -s tests -v
python tools/manage_skill.py install --agent codex
```

Choose `--agent claude-code` or `--agent antigravity` instead of `codex` as needed.
For an unmerged change, select its PR branch explicitly instead. A source preview
on `main` is not a tagged release or a claim of completed conversational testing.

To inspect an unmerged change, clone its PR branch explicitly in a separate checkout.
Back up an existing data directory before using this preview: its first successful
storage request upgrades the database to schema 7.

Alternatively, download a source ZIP using GitHub's **Code → Download ZIP** on
the chosen branch, extract it, and open a terminal beside this README and `tools/`.
Review the instructions and scripts before installation. The commands assume
`python` selects Python 3.10+; use `python3` instead on systems that require it.

For a checkout/source archive you already have, validate it before installation:

```text
python --version
python tools/check_repository.py
python -m unittest discover -s tests -v
```

To build a local review archive (without publishing anything):

```text
python tools/build_package.py
```

This writes `dist/meal-magic-0.6.1.zip` and a SHA-256 sidecar. Packaging uses an
explicit source-file allowlist, so databases, caches, personal settings, and
untracked files cannot enter the archive through directory scanning.

## Install

Choose an agent and scope. Commands below copy the same skill files into the
agent's documented discovery directory; they do not edit agent settings or install
Python. Installation is explicit and refuses to overwrite an existing folder.

### Personal installation

Run the command for the agent you use:

```text
python tools/manage_skill.py install --agent codex
python tools/manage_skill.py install --agent claude-code
python tools/manage_skill.py install --agent antigravity
```

| Agent | Personal destination | Project destination | Explicit use |
|---|---|---|---|
| Codex | `~/.agents/skills/meal-magic/` | `.agents/skills/meal-magic/` | `$meal-magic` |
| Claude Code | `~/.claude/skills/meal-magic/` | `.claude/skills/meal-magic/` | `/meal-magic` |
| Antigravity | `~/.gemini/config/skills/meal-magic/` | `.agents/skills/meal-magic/` | `/meal-magic` |

`~` means the OS user's home directory. These destinations describe local agents;
they do not configure hosted sessions, containers, remote machines, or Claude
Cowork. Agents running under another OS user may resolve a different home/data
directory. Do not install duplicate copies with the same name in several scopes
unless you understand the host's precedence rules.

### Project installation

Pass an existing project directory. Windows example:

```powershell
python tools/manage_skill.py install --agent codex --scope project --project 'C:\My Cooking Project'
```

macOS/Linux example:

```sh
python3 tools/manage_skill.py install --agent claude-code --scope project --project '/home/me/cooking'
```

Use `--agent antigravity` for Antigravity. Codex and Antigravity share the project
destination, so install once if they use the same project. All three personal
destinations are separate. A project-local installation still uses per-user data
outside the project by default; project scope does not create a separate profile.

### Confirm discovery

- **Codex:** look for `meal-magic` in the skill selector or invoke `$meal-magic`.
  Current documentation says changes are detected automatically; restart Codex
  if the skill does not appear.
- **Claude Code:** check the `/` command menu and invoke `/meal-magic`. Start a
  new session after installation for a conservative compatibility check. Current
  documentation also describes live reload and `/reload-skills` when a new
  top-level skills directory was created; availability depends on your version.
- **Antigravity:** check the project's Customizations list and invoke
  `/meal-magic`. In current Antigravity CLI documentation, `/skills` lists skills
  and `/skills reload` refreshes discovery; start a new conversation if necessary.

If discovery fails, compare your installed host version's documentation with these
paths. The locally available host versions have not all been tested in live
conversations with this skill. Do not fix discovery by changing unrelated settings.

Official sources checked **2026-11-05**:
[Codex skills](https://learn.chatgpt.com/docs/build-skills),
[Claude Code skills](https://code.claude.com/docs/en/skills),
[Antigravity skills](https://antigravity.google/docs/skills), and
[Antigravity discovery](https://antigravity.google/docs/customization-discovery/).

## Custom agents

Custom-agent support is an integration contract, not a claim that every agent
automatically discovers skills. The agent must:

1. Load `SKILL.md` as instructions when the cooking workflow is relevant.
2. Read its linked CLI reference and locate scripts relative to that SKILL.md.
3. Supply explicit structured JSON actions, inspect errors, and use returned IDs.
4. Run Python locally with access to the chosen data directory.

For an agent with a configurable skill directory, specify the **exact final
directory**, whose name must be `meal-magic`:

```powershell
python tools/manage_skill.py install --agent custom --destination 'C:\MyAgent\skills\meal-magic'
```

Register that directory using your own agent's documented mechanism. No registration
or configuration change happens automatically. An agent with local Python tools
can also call the CLI directly. Synthetic Python adapter example:

```python
import json
from pathlib import Path
import subprocess
import sys

skill_dir = Path("/absolute/path/to/meal-magic")  # Use your installed path.
request = {"action": "context"}
completed = subprocess.run(
    [sys.executable, str(skill_dir / "scripts/meal_store.py")],
    input=json.dumps(request, ensure_ascii=False),
    encoding="utf-8", capture_output=True, timeout=30, check=False,
)
response = json.loads(completed.stdout)
if completed.returncode != 0 or not response.get("ok"):
    raise RuntimeError(response.get("error", "meal_magic_failed"))
context = response["result"]
```

Keep `shell=False` (the default), pass arguments as a list, and never turn recipe
content into executable commands. A chat-only agent without local tool execution
cannot provide this skill's persistent storage functionality. A remote agent stores
data on its execution host, not automatically on the user's computer.

## Data, profiles, and backups

By default, all local agents running under the same OS user share one household profile:

| OS | User data directory |
|---|---|
| Windows | `%LOCALAPPDATA%\MealMagic` |
| macOS | `~/Library/Application Support/MealMagic` |
| Linux | `$XDG_DATA_HOME/meal-magic`, or `~/.local/share/meal-magic` |

The database is `meal-magic.sqlite3`. No personal histories, family records, or
real saved recipes are bundled. No external application is required or imported.

For a separate profile, set an absolute `MEAL_MAGIC_DATA_DIR` **in the environment
that runs the agent**, or pass `--data-dir` on each CLI call. Example for a
PowerShell terminal before launching your agent:

```powershell
$env:MEAL_MAGIC_DATA_DIR = 'C:\MyPrivateCookingData'
```

Changing this variable inside an unrelated terminal does not change an already
running desktop agent's environment. Ask your agent to pass `--data-dir` explicitly
if needed. The tool refuses storage inside its own installed skill directory.
Household members are separate records within this shared profile. Use separate
data directories for separate households. There are no per-member accounts or
multi-user access controls; anyone with access to the profile can read its records.

To make a complete backup, close all agents using the store and copy the entire
data directory to a private backup location. To restore, close those agents and
copy that saved directory back to the same data path (keep the current directory
as a backup first). Do not merge SQLite files. The `export` action returns a JSON
snapshot for inspection/portability. `import` restores its active public data only
into an empty profile; it does not restore source internal retry receipts. See
[JSON transfer](#json-transfer-into-an-empty-profile).

## JSON transfer into an empty profile

Use `import` to move active household data from a Meal Magic JSON export to a
new profile. This first version accepts schema-6/7 exports and refuses any target
with records, retained retry receipts, changed locale or non-pending onboarding.
It never overwrites or merges an existing household. An initialized untouched
profile is allowed; no delete/reset/force option is provided.

The import preserves public record IDs and links, member-scoped restrictions,
recipes and favorites, exact content/timestamps, actual meal membership and current
plan revisions. All validation/writes run atomically. Malformed or conflicting
data fails without partial restoration or silent repair. Imported text is data,
never instructions. Limits are 10,000 records per domain and 20 MiB canonical
UTF-8 JSON, with existing per-field bounds. See the [CLI contract](skills/meal-magic/references/storage-cli.md#json-import-into-an-empty-profile).

The request is a JSON object with `action: "import"`, a fresh `request_key`, and
`data` set to the successful export response's **result object**, not the full
response envelope. Pass it through stdin or a private UTF-8 `--request-file` and
explicitly target your chosen empty `--data-dir`. Never put backup files in Git
or interpolate their contents into shell commands. The host must read only the
specific export and destination you authorize.

Example preparation in Python, with paths explicitly selected by the user:

```python
import json
from pathlib import Path
import subprocess
import sys

export_file = Path("/private/backup/export-response.json")
helper = Path("/absolute/path/to/meal-magic/scripts/meal_store.py")
destination = Path("/private/new-empty-profile")
response = json.loads(export_file.read_text(encoding="utf-8-sig"))
if response.get("ok") is not True:
    raise ValueError("Source export did not succeed")
request = {"action": "import", "request_key": "restore-transfer-001", "data": response["result"]}
run = subprocess.run([sys.executable, str(helper), "--data-dir", str(destination)],
                     input=json.dumps(request, ensure_ascii=False), encoding="utf-8",
                     capture_output=True, check=False)
result = json.loads(run.stdout)
if run.returncode or not result.get("ok"):
    raise RuntimeError(result.get("error", "Import failed"))
print(result["result"])  # Success/counts only, not the private snapshot.
```

For uncertain retries, use the identical key/data: the original success is returned
without applying the snapshot again or undoing later edits. Changing the snapshot
with the same key conflicts. A new key against an imported profile is refused.

JSON export omits internal request keys and historical retry receipts. Import
creates new internal keys for active recipes/meals; deleted events, earlier plan
versions and original source retry keys cannot be recovered. Do not redeliver old
source requests to the destination. For a complete recovery including retry
history, use the closed-client whole-directory backup described above.

## Update

Obtain and review the new source version, open a terminal in its root, and run the
matching command. Use the same scope/project/destination as the original install:

For a Git checkout, `git pull --ff-only` updates the currently selected source
branch without creating a merge commit. Inspect the incoming changes before
running the installer. If you have local source edits, keep them safely rather
than using a reset/force overwrite. For a source ZIP, extract the new version into
a separate folder; don't extract it into the personal data directory.

```text
python tools/manage_skill.py update --agent codex
python tools/manage_skill.py update --agent claude-code
python tools/manage_skill.py update --agent antigravity
```

Project example:

```powershell
python tools/manage_skill.py update --agent codex --scope project --project 'C:\My Cooking Project'
```

Custom-agent example:

```powershell
python tools/manage_skill.py update --agent custom --destination 'C:\MyAgent\skills\meal-magic'
```

The manager verifies its ownership marker and file hashes, stages the new skill,
and rolls back if replacement fails. It refuses locally modified files, unknown
files/directories, symlinks/junctions, and unmanaged installations rather than
deleting them. Save any local edits/data outside the installation before resolving
such a refusal. Directly importing a helper may create `__pycache__` in its folder;
review and remove that generated cache if it blocks an update. There is no force
overwrite option. Prefer running the helper as a CLI. On Windows, reparse points
are checked without following them on every supported Python version, including
3.10/3.11; project paths retain their original spelling until this check runs.

The manager never opens the personal database. v0.6 uses schema version 7. On the
first successful storage request, the helper upgrades schema 1, 2, 3, 4, 5 or 6 transactionally.
Schema 1 gains household members, onboarding state and nullable preference
ownership; schema 2 gains locale and declared observances; schema 3 gains empty
plan storage and retry receipts; schema 4 gains an empty meal/member relation.
Schema 5 gains durable meal-log receipts backfilled from currently active events.
Schema 6 gains an import-receipt table for safe restoration retries.
Keys for events already deleted before this upgrade cannot be recovered.
Older meals remain unspecified and historical meal request keys remain retryable. Existing IDs/content,
favorites, history, members and ownership remain intact. Old unassigned
preferences stay unassigned. No family, age, location, belief or practice is
invented. A completed/skipped schema-2 introduction stays completed/skipped.

Back up the data directory before upgrading. The schema change rolls back if it
fails. Unknown schema versions/foreign databases are refused, never reset. Once
schema 7 is committed, older helpers (including v0.5/schema 6) cannot read it:
to roll back, stop all clients
and restore the matching pre-upgrade data backup, preserving newer data separately.

## First-use introduction and family meals

The introduction starts when Meal Magic is first used, not whenever the agent
starts or handles an unrelated task. It is optional and conversational:

1. The agent reads existing Meal Magic context. It saves relevant facts already
   explicitly stated by the user in its current conversation or authorized memory
   when their meaning, owner and currency are clear, and summarizes what it saved.
   It does not ask the same questions again. Inferred, stale, ambiguous or
   conflicting facts need clarification first; it does not copy memory wholesale.
2. It asks only for missing basics: who usually eats together and whether there
   are young children/older adults; allergies/prohibited ingredients and who they
   apply to; favorite/disliked foods and dietary patterns; and, optionally,
   country/region and the occasions/traditions the user wants taken into account.
3. It saves the confirmed answers, acknowledges them, and remembers that the
   introduction is complete. Partial answers and skipping are allowed. Interrupted
   introductions resume from stored facts; completed/skipped ones do not restart.

Names are optional: labels such as `Adult 1`, `Child 1`, and `Older adult 1` are
enough. Approximate age/stage can help with adaptations; dates of birth and medical
histories are not needed. Age alone never implies a diagnosis, allergy, swallowing
problem, need for pureed food, or prescribed diet. The agent asks about relevant
needs rather than inventing them. Unknown allergy information is distinguished
from a user's explicit report of no known allergies.

Example first message from the agent (synthetic):

> Before we get started, who do you usually cook for? Any young children or older
> adults? Are there allergies or ingredients anyone must avoid, and which foods
> does each person especially like or dislike? You can answer briefly or skip this.

The agent may also ask which country/region to use for local occasions and which
traditions/fasting routines, if any, the household follows. It asks up to four
short grouped questions, only for missing information, and may spread them across
turns. It does not require a religious identity or an exact home address.

For a shared meal, all members' restrictions and all unassigned restrictions
apply. If you specify who is eating, the agent uses those diners' preferences
while still considering shared-kitchen allergy concerns. One child's dislike is
not recorded as another adult's dislike. An unspecific older-adult label does not
cause automatic low-salt, soft-food, or other medical-diet assumptions.

The skill keeps the clearly established diners through follow-up questions instead
of asking who is eating every turn. With no established audience, it states a
shared-household assumption for suggestions. It asks when identity or conflicting
needs materially affect the dish. You can request one dish for a member with
explicitly stated needs and another for the rest of the household; the agent
labels the dishes and applies each audience's restrictions and stated shared-kitchen
precautions without inventing a diagnosis or medical diet.

A favorite food can be remembered without creating a saved recipe. The library's
favorite flag still refers to a particular complete saved recipe. Meal history
supports optional explicitly reported members: an unspecified family meal does
not assert that every member ate it. No personal facts are filled into this source
package; the shipped household starts empty.

Ingredients supplied for a recipe stay in the current conversation. There is no
persistent pantry, quantity or expiry tracking. Saved recipes and requested saved
plans remain separate features, not evidence of current stock.

## Holidays, local occasions, and fasting practices

Meal Magic keeps geographic context separate from personal practice:

- Country/region and optional timezone help the agent check the relevant local
  date/calendar. They are supplied by the user or already explicitly known to the
  host; language and location are never used to infer religious identity.
- `holiday_mode=suggest` opts into suitable local/upcoming occasion ideas;
  `off` disables unsolicited occasion ideas; `unknown` is the empty-profile default.
- A declared observance records the user's own label, schedule, food/meal-time
  rules, optional calendar/tradition, strictness and who follows it. It can be
  updated, disabled without deletion, or forgotten by ID.

For example, a user may request Christmas/New Year menus, follow a particular
Easter calendar, plan Ramadan meals, or choose a Wednesday/Friday food pattern.
The skill preserves the user's actual rules. It does not turn the word "fasting"
or "ladera" into assumed ingredient exclusions, oil rules, exemptions, or a
religious identity. It asks about details when they affect the meal. One adult's
practice is not automatically assigned to children or the rest of the household.
Allergies and explicit ingredient prohibitions still apply to festive meals.

For event dates, the host agent should verify the requested year, country/region
and calendar/tradition with its own browsing/calendar tools and an appropriate
official/local authority. Dates that depend on local announcements must be
distinguished from provisional dates. Exact daily fasting/meal times need the
relevant local timing source, not a guess from country alone. Sources should be
cited when used. Lookup queries use only the public date/location/tradition terms
needed; no household names or allergy profile should be sent in a search query.

**The Python helper is not a holiday database or religious calendar engine.** It
stores free-text schedules and rules; the model interprets them. An optional
explicit date on `context` supplies a deterministic ISO weekday for weekly rules,
without guessing the user's local date or activating any practice. There are no
hardcoded country calendars, fasting food lists, or built-in calendar network
calls. Existing host tools or dates supplied by the user provide verification.
If lookup is unavailable, the agent says the date/time is unverified and asks for
the calendar the user follows, or offers clearly conditional/ordinary options.
No extra API key or MCP service is required by the skill.

Newly stated ongoing practices can be remembered later, not only at onboarding.
Repeated meal choices may prompt a short question about a possible preference;
they do not silently become a belief, fast or permanent prohibition. There is no
background monitoring. Existing clear user-declared facts are saved with an
acknowledgment; uncertain patterns are confirmed first. Turning occasion ideas
off does not erase or disable an explicitly stored active fasting/dietary rule.

Synthetic examples:

```text
Use Greece and my stated local timezone for occasion ideas. Ask which Easter
calendar we follow rather than choosing one from the country.
```

```text
For Adult 1 only, remember this weekly rule: on Wednesdays and Fridays,
suggest plant-based dishes with olive oil. Treat it as strict unless I say otherwise.
```

```text
I want Ramadan dinner ideas according to our local community's calendar.
Ask me which community/calendar and which meal rules are relevant if you don't know.
```

## Uninstall

Keep the source manager, or use a newly extracted copy of this release. Run the
matching command with the same scope/project/destination:

```text
python tools/manage_skill.py uninstall --agent codex
python tools/manage_skill.py uninstall --agent claude-code
python tools/manage_skill.py uninstall --agent antigravity
```

Project/custom examples:

```powershell
python tools/manage_skill.py uninstall --agent codex --scope project --project 'C:\My Cooking Project'
python tools/manage_skill.py uninstall --agent custom --destination 'C:\MyAgent\skills\meal-magic'
```

Only that verified installation directory is removed. **Your preferences, meal
history, and recipes remain.** Other agent installations remain. Reinstalling
reconnects to the same data directory. Start a fresh conversation after uninstall
so the host no longer has previously loaded instructions in context.

Deleting personal data is a separate, deliberate operation: close all agents,
verify the chosen data directory and backups, then delete that directory using
your OS file manager if you intend to erase it. There is no automatic data purge.

## Usage examples

### Weekly plans and shopping lists

```text
Make a five-day dinner plan for four people, budget-conscious and varied.
We have 500 g dry rice and olive oil. Show quantities and a combined shopping list.
Save the plan so we can change it later.
```

The agent uses the current household restrictions/history and relevant dates,
asks about missing dates/diners when needed, and plans quantities for the stated
servings. The consolidated shopping list distinguishes dry/cooked/drained amounts
and subtracts only the stock you supplied. "Budget-conscious" is an estimate unless
prices are actually verified; the skill has no store pricing or ordering service.

```text
Show my saved five-day plan and its shopping list.
Replace Wednesday's dinner with lentils for two; keep the other days and save
the updated plan and revised shopping list.
```

Programs and lists are saved as one snapshot, with a stable plan ID and increasing
revision. Updating requires the current revision, so another agent's changes
cannot be silently overwritten. An outdated update is refused and must be
reapplied to the latest plan. The host recalculates the quantities/list; Python
validates and stores the supplied snapshot rather than understanding ingredients
or guaranteeing totals. An empty shopping list is possible if nothing else is needed.

Plan storage accepts 1–93 meals within 31 days; each meal has a date, slot, name,
integer servings and ingredient/preparation details. Plans are listed/retrieved
separately from actual meals. Saving or changing a plan does not record cooking,
eating, buying groceries or consuming pantry stock. Recipe-library entries are
not created just because a dish appears in a plan. There is no pantry inventory or
reminder system. Actual meal membership is recorded separately when reported.

The plan list supports paging through older plans with `limit`/`offset` and an
optional date-overlap filter; there is no need to export the full personal profile
to find records beyond the first 100. Paging is not a snapshot across concurrent
edits, so a host should reconcile plan IDs if the collection changes while paging.

```text
Forget that saved plan; keep my recipes and actual meal history.
```

Deletion removes the active plan with a revision check. Historical mutation receipts
remain in the local database to make retries safe; this is not complete erasure
of all old plan text. Export includes current plans but not those receipts. To
erase the entire profile, follow the separate data-directory deletion procedure.
JSON import transfers active plans into an empty profile; old plan versions are not restored. Plan contents are historical:
the agent must recheck current restrictions before recommending a saved plan.

### Recipes and actual meals

These are synthetic prompts, not bundled user preferences:

```text
We usually cook for two adults, a young child, and an older adult.
The child likes lentil soup. One adult is allergic to sesame.
The older adult avoids mushrooms; no other eating needs have been reported.
```

The agent clarifies which adult has the allergy and any uncertain pre-existing facts,
and links each preference to the appropriate member. It does not infer that the
other members have no allergies from the absence of allergy information.

```text
Remember that I prefer chickpeas, don't eat mushrooms, and am allergic to peanuts.
I have rice, chickpeas, lemon and olive oil. What can I make in 25 minutes?
```

The model remembers the ongoing preferences, applies the exclusions and allergy,
and proposes meals. The suggestions create no actual meal events.

```text
Give me the full lemon chickpea rice recipe for two, and save it.
Make that saved recipe a favorite.
Show the exact recipe I saved, not a newly generated version.
```

```text
Let's cook it tomorrow.
```

This is a plan. It does not enter the actual meal history.

```text
I cooked the lemon chickpea rice today, but haven't eaten it yet.
```

Only a cooked event is recorded. Later:

```text
I ate the leftover chickpea rice today. Suggest something different for dinner.
```

An eaten event is recorded and history informs variety. Leftovers are valid
additional events, not suppressed by similar meal names.

```text
No rice tonight, but keep my usual preferences.
Forget my mushroom dislike; I now enjoy mushrooms.
```

The first request is temporary. For the second, the agent reads remembered context;
if mushrooms were stored as a prohibition instead of a dislike, it clarifies the
change before replacing that restriction. Stated allergies are never inferred
or silently removed.

### Personal meal history

Synthetic example with two previously identified household members:

```text
For Adult 1, use their stated eating requirements and make a separate dinner.
For Child 1, suggest another dish using their own preferences.
```

This is still a suggestion. Only a later actual report records history:

```text
Adult 1 ate the separate rice dish today; Child 1 ate the pasta today.
What has Adult 1 actually eaten recently? Suggest something different.
```

The host records separate dishes with their explicitly reported diners, then uses
`meal-list` with the person's `member_id` and `kind=eaten` for personal variety.
It does not infer eating from a cooked event or a planned audience. Members on a
`cooked` event are explicitly reported recipients, not cooks or proof of eating.
Unspecified and pre-upgrade events return `member_ids: []`, meaning unknown, and
are excluded from personal history. Membership is optional, so an otherwise clear
actual event can still be saved without asking for a full attendance list.

Member removal refuses linked actual meals rather than erasing history. Event
removal deletes only that event and its membership links. If a user requests a
membership correction, removing the incorrect event and recording a replacement
are separate transactions; an interrupted replacement must be reported and retried.

Meal-log receipts retain the original request/response and member IDs after removal,
so retrying an old key returns its original receipt without recreating a deleted
meal. Use current listings to establish whether an event is active. Removal clears
the active event and links, not all retained text. JSON export excludes internal
meal receipts, just as it excludes plan receipts. Complete erasure requires the
separate, deliberate whole-data-directory removal described above.

## Testing and limits

```text
python -m unittest discover -s tests -v
python tools/check_repository.py
```

Tests use standard-library `unittest`, temporary directories, fake agent homes,
and synthetic data. They do not install into your real agent directories, call
models, use Android devices, or read application/user databases. See
[VERIFICATION.md](VERIFICATION.md) for results and
[tests/agent-scenarios.md](tests/agent-scenarios.md) for live conversational checks.

Storage tests cannot prove that every host/model correctly interprets ambiguous
conversation or reliably activates the skill. Allergen/dietary reasoning depends
on that model and the user's information; the helper is not a dietary safety
classifier. v0.6 excludes shopping service integrations, inventory tracking, nutrition
tracking, source scraping, and MCP services. JSON import does not merge profiles.

## Layout

```text
skills/meal-magic/       Portable installed skill and standard-library helper
tools/manage_skill.py   Explicit install/update/uninstall utility
tests/                  Isolated executable tests and live-agent scenarios
```

The short `SKILL.md` keeps the shared rules and a required-reading map. Detailed
workflows live in `references/household.md`, `occasions.md`, `recipes-plans.md` and
`meal-history.md`; `storage-cli.md` remains the structured tool contract. All hosts
install the same files. The installer accepts the original verified five-file
manifest when updating/uninstalling an older installation, but still refuses local
edits, extra files, redirected paths and incomplete/unknown manifests. No schema
or storage behavior changes accompany this instruction reorganization.


This is a standalone package: the hosting agent provides the model and local
Python provides storage. Examples and tests are synthetic. Licensed under
[MIT](LICENSE).

## Contributing, reporting problems, and review

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the branch/PR workflow and CI commands,
and [SECURITY.md](SECURITY.md) for privacy boundaries and vulnerability reporting.
Use [issues](https://github.com/alexneverland/meal-magic/issues) with synthetic
reproductions; never attach your profile/database or credentials.

Changes to `main` go through PRs and the required CI gate. Codex review can be
requested with `@codex review` in a PR comment when the repository is connected
and code review is enabled in Codex. The request is not itself a completed review.
The [official Codex review guide](https://learn.chatgpt.com/docs/third-party/github)
explains setup. Root [AGENTS.md](AGENTS.md) supplies focused project review rules.
