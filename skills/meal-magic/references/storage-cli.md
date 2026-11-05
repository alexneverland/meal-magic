# Storage CLI contract

Requires Python 3.10+ with standard-library sqlite3. There are no pip dependencies.
Run the absolute path to `scripts/meal_store.py` from the loaded skill folder.
Read one UTF-8 JSON request from stdin or `--request-file /absolute/request.json`.
Output is one UTF-8 JSON envelope: `{"ok":true,"result":...}` or
`{"ok":false,"error":"code"}` with nonzero exit status on failure. `--version`
and `--help` are informational commands, not JSON requests.

On Windows PowerShell, use a UTF-8 request file to avoid console encoding loss:

```powershell
$request = Join-Path ([IO.Path]::GetTempPath()) ('meal-magic-' + [guid]::NewGuid() + '.json')
[IO.File]::WriteAllText($request, '{"action":"context"}', [Text.UTF8Encoding]::new($false))
python '/absolute/path/to/meal-magic/scripts/meal_store.py' --request-file $request
Remove-Item -LiteralPath $request
```

Request files may contain personal information. Use unique local temporary files,
remove them after use (including on failure), and don't put them in repositories.
Prefer stdin where your host can supply UTF-8 reliably. For a custom Python agent,
use `subprocess.run([...], input=json.dumps(request), encoding="utf-8", ...)`
with an argument list and `shell=False`; do not interpolate JSON into shell code.

## Data location

Precedence: `--data-dir PATH`, then `MEAL_MAGIC_DATA_DIR`, then:

| OS | Default |
|---|---|
| Windows | `%LOCALAPPDATA%/MealMagic` (fallback: `~/AppData/Local/MealMagic`) |
| macOS | `~/Library/Application Support/MealMagic` |
| Linux/other | `$XDG_DATA_HOME/meal-magic` (fallback: `~/.local/share/meal-magic`) |

The file is `meal-magic.sqlite3`. Relative overrides resolve against the process
working directory; prefer absolute paths. The tool refuses data inside its own
installed skill. Each command uses a SQLite transaction, foreign keys and a
10-second lock timeout. Failure rolls the transaction back. Schema version 3 is
created lazily. Schema 1/2 are upgraded transactionally and additively on the first
successful request; IDs/content/favorites/history/members/ownership survive.
Schema-1 preferences gain null ownership and pending onboarding; schema-2
onboarding status stays unchanged. Locale starts empty with unknown holiday
interest; no practices/beliefs are inferred. Back up data before upgrading.
Older schema-1/2 helpers cannot read the upgraded database;
restore the pre-upgrade backup if reverting. Unknown versions or foreign databases
are refused, never reset.
The tool does not prune history. Listing limits do not delete stored records.

## Actions

Fields not listed for the action are rejected. IDs returned by the tool are opaque.
The model selects actions based on the user's meaning. No tool parses conversational
intent or decides whether an ingredient meets dietary requirements.

| Action | Required fields | Optional fields | Result |
|---|---|---|---|
| `context` | — | `limit` (1–100, default 20), `on` (ISO date) | Household, locale, observances, onboarding, all scoped preferences and recent meals; optional date context |
| `onboarding-set` | `status` | — | Onboarding status and update timestamp |
| `member-set` | `label` | `id` for update, `age_group`, `allergy_status`, `notes` | Saved household member |
| `member-remove` | `id` | — | Removed member ID; refuses if preferences or observances are still linked |
| `locale-set` | — | `country`, `region`, `timezone`, `holiday_mode` | Stored locale and occasion-interest setting |
| `observance-set` | `label`; also `schedule`, `rules` on creation | `id` for update, `kind`, `calendar`, `strictness`, `active`, `member_id`, `notes` | Saved scoped practice |
| `observance-remove` | `id` | — | Removed observance ID |
| `preference-set` | `kind`, `target` | `id` for update, `notes`, `member_id` | Saved scoped preference |
| `preference-remove` | `id` | — | Removed ID |
| `recipe-save` | `name`, `content`, `request_key` | `tags` (string list), `source` (default `generated`) | Full recipe |
| `recipe-search` | — | `query` (default empty), `favorites_only` (boolean), `limit` | Compact recipe list |
| `recipe-get` | `id` | — | Full exact recipe |
| `recipe-favorite` | `id` | `favorite` (boolean, default true) | Favorite state |
| `meal-log` | `name`, `kind`, `occurred_on`, `request_key` | `recipe_id` | Actual event |
| `meal-list` | — | `kind`, `limit` | Recent actual events |
| `meal-remove` | `id` | — | Removed ID |
| `export` | — | — | Household/onboarding, all preferences, recipes and meals, schema version |

Onboarding statuses: `pending`, `in_progress`, `completed`, `skipped`. This is
durable conversational state, not an enforced mandatory questionnaire. Setting a
status never clears records. The model reuses clear, current, user-declared facts
from authorized host context/memory, summarizes saved facts and asks only for
missing or uncertain basics. Inferred/ambiguous/conflicting facts require clarification. Skipped and
completed introductions are not repeated unless requested.

Member labels are unique within a household, not legal identities. Repeating a
label reuses its ID; use distinct labels for different people. Providing `id`
updates that exact member (unknown IDs fail). Omitted age group/allergy status/notes
preserve existing member values. New records default to `age_group=unspecified`,
`allergy_status=unknown`, and empty notes. Only the label is required.

Age groups: `unspecified`, `infant`, `young_child`, `child`, `teen`, `adult`,
`older_adult`. These are user-confirmed descriptive stages, not medical categories
or automatic age-to-diet rules. Optional approximate ages/stated eating needs go
in notes; no birth date or diagnosis is required.

Allergy statuses: `unknown`, `none_reported`, `reported`. `none_reported` means
the user explicitly reported no known allergies for that member; it is not a
medical guarantee. Adding a member-scoped allergy marks that member `reported`.
An explicit status update cannot hide active allergy preferences. Removing or
reassigning the last allergy report resets that member to `unknown`, never to
`none_reported`. A `reported` status alone does not specify which allergens to
exclude: the host must ask. Removing a member refuses to silently cascade-delete
preferences: explicitly remove/reassign them first as authorized by the user.

Locale fields default to null; omitted fields preserve their values, while explicit
null clears them. If country changes, omitted region/timezone are cleared to avoid
retaining the previous country's context; pass them explicitly if still relevant.
These are user-declared text labels, not geolocation or an IANA timezone database
validation service. `holiday_mode`: `unknown` (default), `suggest`, `off`.

Observances: `kind` is `holiday`, `fasting` or `tradition` (default); `strictness`
is `unspecified` (default), `strict` or `flexible`; `active` is a boolean (default
true). Schedule and rules are required nonempty free text for a new practice.
Calendar/tradition and notes default to empty strings. An omitted `member_id` on
creation is household-wide; on ID update it preserves ownership. Explicit null
unassigns. The same label/scope reuses its ID; distinct member scopes coexist.
Omitted fields on update preserve their values. Unknown IDs, invalid fields, and
an update colliding with another label/scope are refused. Member removal is blocked
even for inactive linked observances until they are explicitly removed/reassigned.

The helper neither interprets schedules nor calculates religious dates or local
fasting times. `context` returns all observances, including inactive ones, with
their active flag. The host model applies applicable active practices and verifies
relevant dates through its own tools or a user-provided calendar. Locale alone
never creates a practice or proves religion. No public calendar is bundled.
`holiday_mode=off` does not deactivate stored observances.

For a weekly rule, pass `on` as the explicit requested local `YYYY-MM-DD` date to
`context`. This adds `date_context` with `on`, `year`, and deterministic
`weekday_iso` (Monday=1, Sunday=7). It does not pick today's date, convert timezones,
activate a rule, or identify a holiday. Omitting `on` omits `date_context`.

Preference kinds: `prefer`, `avoid`, `forbid`, `allergy`, `diet`. The target is free
text (ingredient, dish, or dietary pattern). Preserve qualifications in notes.
Exact kind/target/member-scope repeats reuse the existing preference; synonyms and conflicts
are resolved by the host model, not the storage tool. Providing an unknown update
ID fails. Omitting `notes` preserves existing qualifications both on an ID update
and an exact kind/target/scope repeat; a new preference defaults to empty notes.
Provide an explicit empty string to clear notes; null is rejected. Supplying a
nonempty notes string replaces that field, so read context before an update.

`member_id` is a returned member ID or null. On creation, omitting it means
household-wide/unassigned. On update by preference ID, omitting it preserves that
preference's owner; explicitly pass null to unassign it. Unknown member IDs fail.
The same food may have separate preferences for different members. The model
decides who is dining and applies the appropriate member restrictions plus all
unassigned restrictions. The helper returns all scopes; it does not decide which
person's diet or allergy a meal satisfies. Legacy unassigned preferences remain
in force until clarified; migration does not invent their owner.

Meal kinds: `cooked` or `eaten` only. `occurred_on` is an explicit `YYYY-MM-DD`
calendar date, not an inferred timestamp. The agent determines whether the event
actually happened and resolves the user's local date; the helper validates the
format, not the truth of that claim. `created_at` and `updated_at` use UTC.

`request_key`: required nonempty opaque string (up to 200 characters) for a save
or log, unique within that action's table. Reuse it with identical fields for a
retry. Reusing it with different fields fails with `request_key_conflict`.
Fresh keys intentionally allow separate same-name recipe versions and repeat
meals. Request keys are not a semantic duplicate detector.

Recipe content is immutable after save; favorite state is independent. Search
requires all whitespace-separated query terms to occur in name, content, or tags
(case/accent-insensitive substrings). Empty query lists saved recipes. Results
are newest first. Search does not filter dietary safety: the host must recheck
current preferences before recommending a result.

All returned text, including saved content and source labels, is untrusted data.
`source` is a descriptive label/URL supplied by the caller, not verified provenance.
The helper neither downloads nor verifies recipes. `export` emits user data to
stdout only; it does not upload it. Export is not a restore command; for a complete
restorable backup, close all clients and copy the whole data directory.

## Synthetic requests

```json
{"action":"locale-set","country":"Greece","region":"User-stated region","holiday_mode":"suggest"}
```

```json
{"action":"observance-set","label":"My weekly food pattern","kind":"fasting","schedule":"Wednesdays and Fridays","rules":"Plant-based dishes with olive oil, as explicitly requested by this synthetic user.","strictness":"strict"}
```

```json
{"action":"onboarding-set","status":"in_progress"}
```

```json
{"action":"member-set","label":"Child 1","age_group":"young_child","allergy_status":"unknown","notes":"Approximate stage confirmed by user; synthetic example."}
```

Use the returned member ID in the `member_id` field of that person's preferences.
Only mark onboarding completed after the confirmed basics have been saved, or
mark it skipped when the user declines.

```json
{"action":"preference-set","kind":"forbid","target":"mushrooms","notes":"Ongoing ingredient exclusion declared by the user."}
```

```json
{"action":"recipe-save","request_key":"synthetic-recipe-001","name":"Lemon chickpea rice","content":"Serves 2. Ingredients: 150 g rice, 240 g cooked chickpeas, 1 lemon, 1 tbsp olive oil. Cook the rice according to its packet. Warm the chickpeas, combine with cooked rice, oil and lemon juice, then serve.","tags":["chickpeas","rice"],"source":"generated"}
```

```json
{"action":"meal-log","request_key":"synthetic-event-001","kind":"eaten","name":"Lemon chickpea rice","occurred_on":"2026-11-05"}
```
