"""Run a fictional dinner week through the Meal Magic CLI (Python 3.10+)."""

import argparse
from contextlib import nullcontext
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory, mkdtemp


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "skills/meal-magic/scripts/meal_store.py"
START = date(2026, 11, 9)
DINNERS = (
    "Lemon roast chicken and potatoes",
    "Spinach and feta pasta",
    "Baked cod and green beans",
    "Turkey and vegetable tacos",
    "Mushroom and pea risotto",
    "Ginger chicken and rice bowls",
    "Leftover ginger chicken and rice bowls",
)
WEDNESDAY_ACTUAL = "Tomato and egg skillet with toast"
NEXT_DINNER_PROMPT = (
    "For Monday, November 16, 2026, suggest one dinner for all four of us. "
    "We have chickpeas, canned tomatoes, carrots, and plain yogurt. "
    "Use our stored restrictions and dinners we actually ate November 9–15. "
    "Summarize Wednesday's plan versus what we ate, explain how the history "
    "shaped your suggestion, and leave the demo records as they are."
)


def run_demo(profile):
    command = [sys.executable, "-B", str(HELPER), "--data-dir", str(Path(profile).resolve())]

    def call(action, **fields):
        request = {"action": action, **fields}
        process = subprocess.run(
            command, input=json.dumps(request), capture_output=True, encoding="utf-8"
        )
        if process.returncode:
            raise RuntimeError(f"{action} failed: {process.stdout or process.stderr}")
        envelope = json.loads(process.stdout)
        if not envelope["ok"]:
            raise RuntimeError(f"{action} failed: {envelope['error']}")
        return envelope["result"]

    members = [
        call("member-set", label=label, age_group=age)
        for label, age in (
            ("Adult 1", "adult"), ("Adult 2", "adult"),
            ("Child 1", "child"), ("Child 2", "teen"),
        )
    ]
    call("preference-set", kind="allergy", target="tree nuts", member_id=members[2]["id"])
    call("onboarding-set", status="completed")
    planned = [
        {
            "on": (START + timedelta(days=index)).isoformat(),
            "slot": "dinner",
            "name": dish,
            "servings": 4,
            "details": "Serve four. On Saturday prepare four extra portions for Sunday."
            if index == 5 else "Family dinner for four.",
        }
        for index, dish in enumerate(DINNERS)
    ]
    saved_plan = call(
        "plan-save", request_key="family-week-plan", title="Fictional family dinner plan",
        meals=planned, shopping_list=[], notes="All planned ingredients were on hand.",
    )
    dates = {"from_date": planned[0]["on"], "to_date": planned[-1]["on"]}
    if call("meal-list", **dates):
        raise RuntimeError("A saved plan should leave actual history empty.")
    for index, dinner in enumerate(planned):
        dish = WEDNESDAY_ACTUAL if index == 2 else dinner["name"]
        for kind in (("eaten",) if index == 6 else ("cooked", "eaten")):
            call(
                "meal-log", request_key=f"family-week-{kind}-{index}", kind=kind,
                name=dish, occurred_on=dinner["on"], member_ids=[m["id"] for m in members],
            )

    context = call("context", on="2026-11-16")
    restrictions = [p for p in context["preferences"] if p["kind"] == "allergy"]
    saved_plan = call("plan-get", id=saved_plan["id"])
    cooked = call("meal-list", kind="cooked", **dates)
    eaten = call("meal-list", kind="eaten", **dates)
    stats = call("meal-stats", **dates)["totals"]
    if len(restrictions) != 1 or restrictions[0]["member_id"] != members[2]["id"]:
        raise RuntimeError("Expected one allergy linked to Child 1.")
    if (stats["cooked"], stats["eaten"]) != (6, 7) or (len(cooked), len(eaten)) != (6, 7):
        raise RuntimeError("Expected six cooking events and seven eating events.")
    cooked_by_day = {meal["occurred_on"]: meal["name"] for meal in cooked}
    eaten_by_day = {meal["occurred_on"]: meal["name"] for meal in eaten}
    if eaten_by_day[planned[2]["on"]] != WEDNESDAY_ACTUAL or saved_plan["meals"] != planned:
        raise RuntimeError("Expected the Wednesday swap alongside the unchanged plan.")

    print("# A week of dinners with Meal Magic")
    print("\nHousehold: " + ", ".join(member["label"] for member in context["household"]["members"]))
    print(f"Saved allergy: Child 1, {restrictions[0]['target']}")
    print(f"\n{stats['cooked']} cooking events and {stats['eaten']} eating events, November 9–15, 2026.")
    print("\n| Date | Planned | Cooked | Eaten |")
    print("| --- | --- | --- | --- |")
    for dinner in saved_plan["meals"]:
        day = dinner["on"]
        print(f"| {day} | {dinner['name']} | {cooked_by_day.get(day, 'No cooking event')} | {eaten_by_day[day]} |")
    print("\nNext dinner prompt (for an AI host with the demo profile):\n")
    print(NEXT_DINNER_PROMPT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-profile", action="store_true", help="Keep a new temp profile for recording.")
    args = parser.parse_args()
    profile_context = (
        nullcontext(mkdtemp(prefix="meal-magic-family-demo-"))
        if args.keep_profile else TemporaryDirectory(prefix="meal-magic-family-demo-")
    )
    with profile_context as profile:
        run_demo(profile)
        if args.keep_profile:
            print(f"\nDemo profile: {profile}")


if __name__ == "__main__":
    main()
