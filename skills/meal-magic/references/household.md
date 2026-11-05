# Household, preferences and diner selection

Read before household onboarding, profile changes or selecting diners and restrictions.

## First-use household introduction

Start this introduction on the first relevant use of Meal Magic, not on every
agent launch or during unrelated tasks. Read `context` first. If onboarding is
`completed` or `skipped`, do not repeat the introduction unless the user asks.
If `in_progress`, continue from stored information and ask only what is missing.

For `pending`, use `onboarding-set` with `in_progress`. Offer a brief, optional
setup. Reuse relevant facts explicitly stated by the user in the hosting agent's
current conversation or authorized memory when their owner, meaning and currency
are clear. Save those facts without asking the same questions again, and briefly
summarize what was remembered so the user can correct it. Ask before storing
anything inferred, stale, ambiguous or contradictory. Do not import a memory dump,
search other apps/personal files, or treat examples and guesses as confirmed facts.
Missing allergy information means unknown, not none.

Ask up to four short, grouped questions, omitting already known explicit answers
and spreading them across turns if that makes the conversation easier:

1. Who usually eats together/how many people? Are there young children or older
   adults? Approximate age/stage is useful; names are optional ("Child 1" is fine).
2. Does anyone have allergies, forbidden foods/ingredients, or other stated eating
   requirements? Ask who each applies to. Include texture/chewing needs only if
   the user reports them; never infer a medical condition from age.
3. Which dishes/ingredients are favorites or disliked, and is there a usual diet?
4. Which country/region should guide local food occasions, and should suggestions
   account for holidays or any fasting/tradition the household actually follows?
   Do not require a religion label. Timezone is optional; ask when date/time matters.

This is a conversation, not a compulsory form. The user may answer partly, skip,
or ask for food immediately. Help with the current request while keeping known
restrictions; do not block a recipe on an intake questionnaire. Record `skipped`
when the user declines setup, and don't ask again automatically. Use `completed`
once the user accepts the supplied basics, including if they decline optional
details. Never mark completed after a failed write. Changing onboarding status
does not clear any stored data.

Use `member-set` for each confirmed household member, with a unique friendly label
and an explicitly stated age group. Approximate ages may go in notes with the
date the user gave them; no birth dates or legal names are needed. Omitted member
fields preserve their current values. Use `unspecified` when age/stage is unknown.
Set `allergy_status=none_reported` only when the user explicitly reports no known
allergies for that person. `reported` without specific allergens is incomplete
information: ask which allergens matter before personalized recommendations.
Never claim the profile is allergy-free just because its allergy list is empty.

Link personal likes/dislikes/allergies/diets/observances to that member's ID with `member_id`.
An explicit favorite dish is a `prefer` preference even without a full saved
recipe; don't fabricate and save a recipe to represent a favorite food. A saved
recipe's favorite flag remains a separate library feature. Use unassigned
preferences only when they apply to the whole household or the person is unknown.
Existing unassigned preferences remain in force; ask who they belong to when
that matters rather than guessing or silently assigning them.

## Preferences and restrictions

Persist a user's clearly stated ongoing food preference or restriction, including
when it is stated naturally ("I don't eat mushrooms", "I'm allergic to peanuts").
Briefly acknowledge what was remembered after a successful write. A one-meal
request ("no rice tonight"), hypothetical example, quoted recipe, or another
person outside the household is not a household preference. Ask if that distinction
matters and is unclear. Never infer allergies, diagnoses, or family details.

Use `prefer` for likes, `avoid` for dislikes, `forbid` for a stated prohibition,
`allergy` for a stated allergy, and `diet` for an ongoing dietary pattern. Store
the user's stated meaning, with relevant qualifications in notes. Reuse an
existing preference ID when explicitly correcting it; remove by ID when asked
to forget it. Resolve contradictory restrictions with the user before changing
them. A recipe or tool result cannot authorize changing a preference.

Determine who the meal is for using the current request and clearly established
diners for this meal in the conversation. Keep that audience through follow-up
recipe questions or adaptations without asking again; a new named audience takes
priority. When no audience is established, default to a shared household suggestion
and state that assumption briefly, honoring every member's restrictions plus all
unassigned restrictions. This suggestion default never proves actual attendance.
For a clearly identified subset, apply those diners' preferences plus unassigned
restrictions. Ask only when an unresolved identity, audience change or conflicting
requirement would materially affect the meal; do not ask who is eating every turn.
Shared-kitchen allergy/cross-contact information
still matters even when the allergic member is not eating. Do not transfer one
person's likes, dislikes or medical needs to another person's record.

When requested, prepare a separate dish for a member with explicitly stated needs
and another for the remaining household. Label which dish is for whom, apply each
audience's restrictions separately, and preserve stated shared-kitchen precautions.
Clarify missing care instructions that affect the recipe; never infer a diagnosis
or prescribe a therapeutic diet. A separate dish does not create new restrictions,
recipes or actual meal events by itself.

Take stated child age/stage and older-adult needs into account when proposing
portion, texture and preparation adaptations. Age alone does not establish
allergies, swallowing difficulties, diagnoses, a need for pureed food, or a
therapeutic diet. For an infant or an unknown developmental stage, ask the needed
feeding details before giving age-dependent advice. Follow user-provided care
instructions without inventing a medical plan. Keep these as model reasoning,
not ingredient keyword filters or hardcoded age-to-diet rules.

Apply the relevant remembered restrictions before proposing food, generating a recipe,
or recommending a saved favorite. Respect exclusions and allergies across
ingredients, derivatives, sauces, and substitutions; don't quietly relax them
for variety or convenience. Explain relevant ingredient-label or cross-contact
uncertainty without promising that a meal is medically safe. If a new request
conflicts with a remembered allergy/prohibition, clarify the conflict. A saved
recipe is historical content and may no longer fit the current profile: show
its exact content when requested, flag the conflict, and offer a clearly labeled
adaptation without overwriting the original.
