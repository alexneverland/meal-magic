# Suggestions, recipes, meal plans and shopping lists

Read before suggesting or generating recipes, using the recipe library, or planning/editing menus.

## Suggestions and recipes

Use available ingredients, current preferences, practical time/serving constraints,
and actual recent meals to offer a few useful options. Distinguish ingredients
already available from any extras needed. Use history for variety, not a rigid
ban on repeats; leftovers and requested repeats are valid. Ingredients supplied for
a recipe are temporary conversation context, not a persistent inventory. Do not
save an ingredient list as preferences, notes or a plan merely to remember stock.
There is no pantry storage, quantity tracking or expiry tracking in this version.
Don't infer pantry stock from old meals. Generate a full recipe when requested, with quantities,
servings, clear steps, and useful cooking times. Don't claim verified nutrition
or external authorship without evidence.

Suggestions stay in conversation unless the user asks to keep a plan. Saved plans
are separate from actual meal events. Save a complete named recipe only when the user asks to keep it (or has
explicitly requested ongoing autosave). Search saved recipes before claiming
they are absent. The tool's search is literal, accent-insensitive matching in
name/content/tags; choose useful search terms yourself. Retry with simpler terms
or list recipes with an empty query. Pick by ID; ask when multiple versions make
the user's intended choice unclear. Fetch the exact saved content rather than
regenerating it and calling it the original. New adaptations get new recipe IDs.

## Meal plans and shopping lists

When asked for a weekly/multi-day plan, read the planning contract in
[references/storage-cli.md](storage-cli.md#meal-plans-and-shopping-lists).
Use current profile/history, the requested dates, servings, budget/time constraints
and applicable practices for each date. Ask only for material missing details or
state reasonable assumptions. Prepare quantities per meal and a consolidated
shopping list; reconcile equivalent ingredients/units with the model, distinguish
dry/cooked/drained amounts, and keep incompatible units separate. Subtract only
stock the user actually supplied for this request. Do not invent pantry inventory
or assert a precise budget without verified prices.

If the user asks to save/remember the plan (or has authorized ongoing plan saving),
use `plan-save`. Otherwise show a conversational draft. Do not save separate recipe
records just because a dish appears in a plan. `plan-list` discovers saved plans;
use `offset` with the same filters/limit to read older pages instead of exporting
the full private profile. Continue until a short/empty page, rechecking IDs if
another agent edits the collection while paging.
Fetch by ID before retrieval/editing, and clarify ambiguous choices. Before
recommending an old plan, recheck current restrictions; saved content is historical,
not automatically suitable for changed preferences or another date.

For a change to one day/meal/serving count, fetch the current plan, preserve the
other entries, revise the affected quantities and recompute the complete shopping
list. Save both together using the fetched `revision` as `expected_revision`.
Use a new request key for each intended mutation and the identical key/payload
when retrying an uncertain call. On a revision conflict, reload and reapply only
the requested change; do not overwrite intervening edits. A successful retry may
return an older receipt: `plan-get` establishes current state. Delete a plan only
when the user asks, using `plan-remove` with its current revision and request key.

Plans and shopping lists never prove cooking, eating, purchasing or pantry changes.
Only a later explicit actual-meal report uses `meal-log`. The helper validates and
stores a plan/list snapshot; it does not calculate ingredient totals, verify dietary
safety, order groceries, or schedule reminders.
