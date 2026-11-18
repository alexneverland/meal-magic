# What should we cook after a week of family dinners?

[Watch the 32-second Codex demo](https://youtu.be/1LTPwSZk2UI).

Two adults and two children share dinner. Child 1 has a recorded tree-nut allergy.
They start with a seven-day plan. On Wednesday, they make a tomato and egg skillet
instead of the planned cod. On Sunday, they eat Saturday's leftovers.

## Run the demo

From the repository root, with Python 3.10 or newer:

```sh
python -B docs/demos/family-week.py
```

The script calls the v0.7.0 storage CLI using a fresh temporary directory for
every run. It creates the four fictional members, registers the allergy for
Child 1, saves the dinner plan, and checks that saving the plan leaves actual
history empty. It then records the family's explicit cooking and eating reports
as separate events. The temporary profile is cleaned up when the script exits.

## What the CLI returned

The saved plan comes from `plan-get`, the actual dinners from two date-filtered
`meal-list` reads, and the event totals from `meal-stats`. The script formats
those results for display.

**November 9–15, 2026 · 6 cooking events · 7 eating events**

| Day | Planned | Cooked | Eaten |
| --- | --- | --- | --- |
| Mon 9 | Lemon roast chicken and potatoes | Lemon roast chicken and potatoes | Lemon roast chicken and potatoes |
| Tue 10 | Spinach and feta pasta | Spinach and feta pasta | Spinach and feta pasta |
| Wed 11 | Baked cod and green beans | Tomato and egg skillet with toast | Tomato and egg skillet with toast |
| Thu 12 | Turkey and vegetable tacos | Turkey and vegetable tacos | Turkey and vegetable tacos |
| Fri 13 | Mushroom and pea risotto | Mushroom and pea risotto | Mushroom and pea risotto |
| Sat 14 | Ginger chicken and rice bowls | Ginger chicken and rice bowls | Ginger chicken and rice bowls |
| Sun 15 | Leftover ginger chicken and rice bowls | No cooking event | Leftover ginger chicken and rice bowls |

## Ask for the next dinner

> For Monday, November 16, 2026, suggest one dinner for all four of us. We have
> chickpeas, canned tomatoes, carrots, and plain yogurt. Use our stored
> restrictions and dinners we actually ate November 9–15. Summarize Wednesday's
> plan versus what we ate, explain how the history shaped your suggestion, and
> leave the demo records as they are.

**Illustrative host response**

> Wednesday's plan called for baked cod. You actually ate a tomato and egg skillet
> with toast. After ginger chicken and rice bowls on Saturday and leftovers on
> Sunday, I'd make **tomato-braised chickpeas and carrots with plain yogurt**.
> Simmer the chickpeas and sliced carrots in the tomatoes until tender, then
> serve with a spoonful of yogurt. It uses what you have and gives you a
> different main ingredient from the weekend's chicken. Keep Child 1's tree-nut
> restriction in mind when choosing packaged ingredients and preparing the meal.

The Python helper stores and retrieves records. The host model suggests dinner
and explains its reasoning, so the exact answer can vary. The fixture records a
reported allergy. Ingredient labels and cross-contact require human checks.

In a recorded Codex Desktop run, Codex listed all seven dinners, explained the
Wednesday change and Sunday's leftovers, and suggested chickpea, tomato and
carrot stew with plain yogurt. It referenced the two recent chicken dinners and
Child 1's recorded tree-nut allergy. The recording uses the synthetic fixture.

## Record the demo

1. Run `python -B docs/demos/family-week.py --keep-profile`. Copy the printed
   **Demo profile** path. Each run creates a new synthetic profile in the system
   temp directory and leaves it available for recording.
2. Open a new agent chat in the repo. Ask it to load
   `skills/meal-magic/SKILL.md` from the checkout and to use the printed demo
   directory as the explicit `--data-dir` for **every** Meal Magic call. Then
   paste the next-dinner prompt above. Use the same date range shown in the
   fixture even if recording on a different day.
3. Capture the fixture output or the agent's actual response once it finishes.
   Check that it distinguishes Wednesday's plan from the meal eaten, uses the
   stored allergy and cites the actual weekend dinners. Crop the recording to
   the relevant window and keep local paths and other chats out of frame.

| Time | Show | Caption |
| --- | --- | --- |
| 0–5 s | Four members and Child 1's stored allergy | Four people, one dinner to plan |
| 5–15 s | Seven-day table and Wednesday's row | Planned cod. Ate a tomato and egg skillet. |
| 15–20 s | Sunday's row | Leftovers count as eaten |
| 20–35 s | Next-dinner prompt and the agent's actual reply | A dinner suggestion based on what the family actually ate |

For a static version, use the CLI table and the explicitly labeled illustrative
answer above. The checked-in PNGs and GIFs cover earlier scenarios.
