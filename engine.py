"""
Academic Decision Engine (Python Core)

This file contains ONLY the “brain” of the app.
It does math + logic. No menus, no UI, no printing inside the core functions.

Later:
• A CLI, website, or iOS app will CALL these functions
• That way, the logic can be reused anywhere
"""

# ----------------------------
# IMPORTS
# ----------------------------

# dataclass lets us create simple data objects without writing lots of code.
# Instead of writing __init__ manually, Python builds it for us.
from dataclasses import dataclass, asdict

# date and datetime help us work with real calendar dates (due dates, today, etc.)
from datetime import date, datetime, timedelta

# These are "type hints". They help describe what kind of data a function expects.
# They don't change how the program runs — they just help you (and future you) understand the code.
from typing import List, Dict, Tuple, Optional

# json lets us save and load data to files in a structured format.
import json

# ----------------------------
# DATA MODELS
# ----------------------------

# A dataclass is like a "blueprint" for a type of object.
# Assignment represents ONE assignment from a class.
@dataclass
class Assignment:
    name: str                  # Assignment title
    weight_percent: float      # How much it's worth in the class (0–100)
    due_date: date             # When it's due
    confidence: int            # How confident you feel (1–5)
    estimated_hours: float     # How many hours you think it will take


# DailyLog represents ONE day's mental energy inputs.
@dataclass
class DailyLog:
    sleep_hours: float
    class_hours: float
    study_hours: float
    workout_minutes: float
    social_hours: float
    stress_level: Optional[int] = None  # Optional means it can be None


# ----------------------------
# HELPERS
# ----------------------------

def parse_date(iso_yyyy_mm_dd: str) -> date:
    """
    Converts a string like '2026-02-11' into a date object.
    This makes it possible to do date math (like subtracting dates).
    """
    return datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d").date()


def days_until(due: date, today: date) -> int:
    """
    Returns number of days between today and due date.
    Positive = in the future
    Zero = due today
    Negative = overdue
    """
    return (due - today).days


def clamp(value: float, lo: float, hi: float) -> float:
    """
    Keeps a number within a range.
    Example: clamp(120, 0, 100) → 100
    """
    return max(lo, min(hi, value))

def calc_risk(a: Assignment, today: date) -> Dict[str, object]:
    """
    Calculates how academically "dangerous" an assignment is.

    INPUT:
      a = an Assignment object
      today = today's date

    PROCESS:
      1. Figure out how soon it is
      2. Convert confidence into "doubt"
      3. Combine weight, soonness, and doubt into a risk score

    OUTPUT:
      Dictionary with risk score + label
    """

    # How many days left until due
    dleft = days_until(a.due_date, today)

    # Convert time into urgency bucket
    if dleft <= 1:
        soon = 10
    elif dleft <= 3:
        soon = 8
    elif dleft <= 7:
        soon = 6
    elif dleft <= 14:
        soon = 4
    else:
        soon = 2

    # If confidence is high, doubt is low
    doubt = 6 - a.confidence

    # Combine everything into a single number
    weight_scaled = a.weight_percent / 10.0
    risk = (0.4 * soon) + (0.4 * weight_scaled) + (0.2 * doubt)

    # Turn number into label
    if risk < 3.5:
        label = "Low"
    elif risk < 5.5:
        label = "Medium"
    else:
        label = "High"

    return {
        "name": a.name,
        "days_left": dleft,
        "risk_score": round(risk, 2),
        "risk_label": label
    }

def rank_assignments(assignments: List[Assignment], today: date) -> List[Dict[str, object]]:
    """
    Returns assignments sorted from highest risk to lowest risk.
    """
    scored = [calc_risk(a, today) for a in assignments]
    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return scored

# ----------------------------
# 2) DEADLINE RUSH (URGENCY)
# ----------------------------

def urgency_zone(hours_per_day: float) -> str:
    """
    Turns required hours/day into a dramatic zone label.
    """
    if hours_per_day <= 1:
        return "Safe"
    if hours_per_day <= 2.5:
        return "Steady"
    if hours_per_day <= 4:
        return "Crunch Zone"
    return "Panic Zone"


def calc_urgency(a: Assignment, today: date, start_delay_days: int = 0) -> Dict[str, object]:
    dleft_after_delay = days_until(a.due_date, today) - start_delay_days

    # If it's due today, treat it as "1 day left" (today is your day to do it)
    effective_days = max(1, dleft_after_delay)

    # If it's overdue (negative), still mark it overdue
    if dleft_after_delay < 0:
        return {
            "name": a.name,
            "start_delay_days": start_delay_days,
            "days_left_after_delay": dleft_after_delay,
            "hours_per_day": None,
            "zone": "Overdue"
        }

    hours_day = a.estimated_hours / effective_days

    return {
        "name": a.name,
        "start_delay_days": start_delay_days,
        "days_left_after_delay": dleft_after_delay,
        "hours_per_day": round(hours_day, 2),
        "zone": urgency_zone(hours_day)
    }

def urgency_curve(a: Assignment, today: date, max_delay_days: int = 3) -> List[Dict[str, object]]:
    """
    Returns a list of urgency results for delays 0..max_delay_days.
    This creates the 'fake urgency curve' effect.
    """
    results = []
    for delay in range(0, max_delay_days + 1):
        results.append(calc_urgency(a, today, delay))
    return results

def stress_forecast(assignments: List[Assignment], today: date, window_days: int = 5) -> Dict[str, object]:
    high_risk = []
    for a in assignments:
        r = calc_risk(a, today)
        if 0 <= r["days_left"] <= window_days and r["risk_label"] == "High":
            high_risk.append(a.name)

    count = len(high_risk)
    word = "assignment" if count == 1 else "assignments"

    return {
        "window_days": window_days,
        "high_risk_count": count,
        "high_risk_names": high_risk,
        "message": f"You have {count} high-risk {word} in the next {window_days} days."
    }


def danger_score(a: Assignment, today: date) -> float:
    r = calc_risk(a, today)
    risk = float(r["risk_score"])

    u = calc_urgency(a, today, start_delay_days=0)
    hours_per_day = u["hours_per_day"]

    # urgency_scaled is 0..10 (5 hrs/day capped then *2)
    if hours_per_day is None:
        urgency_scaled = 10.0
    else:
        urgency_scaled = min(5.0, float(hours_per_day)) * 2.0

    # Weighted mix, then scale to a 0..10-ish "dashboard score"
    raw = (0.7 * risk) + (0.3 * urgency_scaled)
    score = raw  # already about 0..10; keep it
    return round(score, 2)



def rank_assignments_by_danger(assignments: List[Assignment], today: date) -> List[Dict[str, object]]:
    """
    Sorts assignments by a combined danger_score (risk + urgency).
    """
    results = []
    for a in assignments:
        r = calc_risk(a, today)
        u = calc_urgency(a, today, 0)
        results.append({
            "name": a.name,
            "risk_score": r["risk_score"],
            "risk_label": r["risk_label"],
            "hours_per_day": u["hours_per_day"],
            "zone": u["zone"],
            "danger_score": danger_score(a, today)
        })

    results.sort(key=lambda x: x["danger_score"], reverse=True)
    return results

def stress_forecast_by_danger(assignments: List[Assignment], today: date, window_days: int = 5) -> Dict[str, object]:
    danger_list = []

    for a in assignments:
        r = calc_risk(a, today)
        dleft = r["days_left"]

        if 0 <= dleft <= window_days:
            u = calc_urgency(a, today, 0)
            if u["zone"] in ("Crunch Zone", "Panic Zone"):
                danger_list.append(a.name)

    return {
        "window_days": window_days,
        "crunch_or_panic_count": len(danger_list),
        "names": danger_list,
        "message": f"You have {len(danger_list)} Crunch/Panic assignments in the next {window_days} days."
    }

def dashboard_summary(assignments: List[Assignment], today: date) -> Dict[str, object]:
    """
    Creates a UI-ready dashboard payload.
    Includes:
    - Stress forecast
    - Top 3 most dangerous assignments
    - Start-by dates
    - Clean dashboard headline strings with emojis
    """

    ranked = rank_assignments_by_danger(assignments, today)
    forecast = stress_forecast(assignments, today, window_days=5)
    by_name = {a.name: a for a in assignments}

    # Emojis
    zone_emoji = {
        "Safe": "🌿",
        "Steady": "🚶‍♂️",
        "Crunch Zone": "⏳",
        "Panic Zone": "🚨"
    }
    risk_emoji = {
        "Low": "✅",
        "Medium": "⚠️",
        "High": "🔥"
    }

    headlines: List[str] = []
    enriched_top: List[Dict[str, object]] = []

    for item in ranked[:3]:
        name = item["name"]
        a = by_name[name]

        sb = start_by_date(a, today)

        hp = item["hours_per_day"]
        hp_text = "N/A" if hp is None else f"{hp} hrs/day"

        z_em = zone_emoji.get(item["zone"], "")
        r_em = risk_emoji.get(item["risk_label"], "")

        headline = (
            f"{z_em} {r_em} {name} | "
            f"Danger {item['danger_score']} | "
            f"{item['risk_label']} ({item['risk_score']}) | "
            f"{item['zone']} ({hp_text}) | "
            f"Start-by: {sb['start_by_date']}"
        )


def start_by_date(a: Assignment, today: date, crunch_threshold: float = 2.5) -> Dict[str, object]:
    """
    Finds the last day you can start working and still stay out of Crunch Zone.

    crunch_threshold = hours/day limit before things get intense.
    Default 2.5 hrs/day.
    """

    total_days_left = days_until(a.due_date, today)

    # If already due/overdue
    if total_days_left <= 0:
        return {
            "name": a.name,
            "start_by_days": 0,
            "start_by_date": today.isoformat(),
            "message": "Start immediately — already at deadline."
        }

    # Try each possible delay
    for delay in range(total_days_left + 1):
        dleft_after_delay = total_days_left - delay
        effective_days = max(1, dleft_after_delay)
        hours_per_day = a.estimated_hours / effective_days

        if hours_per_day > crunch_threshold:
            # The day BEFORE this delay was the last safe start
            safe_delay = max(0, delay - 1)
            start_date = today + timedelta(days=safe_delay)

            zone_if_wait = urgency_zone(hours_per_day)

            return {
                "name": a.name,
                "start_by_days": safe_delay,
                "start_by_date": start_date.isoformat(),
                "message": f"Start by {start_date.isoformat()} to avoid {zone_if_wait}."
            }

    # If never hits crunch, you’re safe until the end
    return {
        "name": a.name,
        "start_by_days": total_days_left,
        "start_by_date": a.due_date.isoformat(),
        "message": "You can pace this — no Crunch Zone risk."
    }

def assignment_to_dict(a: Assignment) -> Dict[str, object]:
    return {
        "name": a.name,
        "weight_percent": a.weight_percent,
        "due_date": a.due_date.isoformat(),   # convert date -> string
        "confidence": a.confidence,
        "estimated_hours": a.estimated_hours
    }


def assignment_from_dict(d: Dict[str, object]) -> Assignment:
    return Assignment(
        name=str(d["name"]),
        weight_percent=float(d["weight_percent"]),
        due_date=parse_date(str(d["due_date"])),
        confidence=int(d["confidence"]),
        estimated_hours=float(d["estimated_hours"])
    )


def save_assignments(path: str, assignments: List[Assignment]) -> None:
    data = [assignment_to_dict(a) for a in assignments]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_assignments(path: str) -> List[Assignment]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return [assignment_from_dict(item) for item in data]
    except FileNotFoundError:
        return []


def suggest_estimated_hours(assessment_type: str, confidence: int) -> float:
    """
    Returns a reasonable starting estimate (in hours) for math prep.
    assessment_type: 'quiz', 'test', 'midterm', 'final'
    confidence: 1..5 (1 = not confident, 5 = very confident)
    """
    base_by_type = {
        "quiz": 1.5,
        "test": 5.0,
        "midterm": 10.0,
        "final": 14.0
    }

    t = assessment_type.strip().lower()
    if t not in base_by_type:
        # default if user types something else
        t = "test"

    base = base_by_type[t]

    # Confidence adjustment:
    # 1 -> +4 hrs, 2 -> +2 hrs, 3 -> +0, 4 -> -1, 5 -> -2
    adjust = {1: 4.0, 2: 2.0, 3: 0.0, 4: -1.0, 5: -2.0}[confidence]

    return max(0.5, round(base + adjust, 1))

def input_assignment() -> Assignment:
    """
    Prompts the user for assignment info and returns an Assignment object.
    Includes:
    - Input validation
    - Optional study-hours suggestion for quizzes/tests/midterms/finals
    """

    name = input("Assignment name: ").strip()

    # Weight %
    while True:
        try:
            weight_percent = float(input("Weight % (0-100): ").strip())
            if 0 <= weight_percent <= 100:
                break
            print("Please enter a number between 0 and 100.")
        except ValueError:
            print("Please enter a valid number (example: 15).")

    # Due date
    while True:
        try:
            due_date_str = input("Due date (YYYY-MM-DD): ").strip()
            due_date = parse_date(due_date_str)
            break
        except ValueError:
            print("Invalid format. Example: 2026-02-18")

    # Confidence 1–5
    while True:
        try:
            confidence = int(input("Confidence (1-5): ").strip())
            if 1 <= confidence <= 5:
                break
            print("Please enter an integer from 1 to 5.")
        except ValueError:
            print("Please enter a whole number (1-5).")

    # Ask if user wants suggested hours
    while True:
        use_suggest = input("Suggest study hours? (y/n): ").strip().lower()
        if use_suggest in ("y", "n"):
            break
        print("Type y or n.")

    if use_suggest == "y":
        # Ask type of assessment
        while True:
            assessment_type = input("Type (quiz/test/midterm/final): ").strip().lower()
            if assessment_type in ("quiz", "test", "midterm", "final"):
                break
            print("Please choose: quiz, test, midterm, or final.")

        # Suggest hours based on type + confidence
        suggested = suggest_estimated_hours(assessment_type, confidence)
        print(f"Suggested estimated hours: {suggested}")

        # Let user accept or override
        while True:
            entry = input("Estimated hours (press Enter to accept suggestion): ").strip()
            if entry == "":
                estimated_hours = suggested
                break
            try:
                estimated_hours = float(entry)
                if estimated_hours >= 0:
                    break
                print("Hours can't be negative.")
            except ValueError:
                print("Please enter a valid number (example: 3.5).")
    else:
        # Manual entry
        while True:
            try:
                estimated_hours = float(input("Estimated hours: ").strip())
                if estimated_hours >= 0:
                    break
                print("Hours can't be negative.")
            except ValueError:
                print("Please enter a valid number (example: 3.5).")

    return Assignment(
        name=name,
        weight_percent=weight_percent,
        due_date=due_date,
        confidence=confidence,
        estimated_hours=estimated_hours
    )

def edit_assignment(assignments: List[Assignment]) -> None:
    """
    Lets the user pick an assignment and edit its fields.
    Modifies the list in place.
    """
    if not assignments:
        print("No assignments to edit.")
        return

    print("\nAssignments:")
    for i, a in enumerate(assignments, start=1):
        print(f"{i}) {a.name} (weight {a.weight_percent}%, due {a.due_date.isoformat()})")

    try:
        idx = int(input("Enter number to edit: ").strip())
        if not (1 <= idx <= len(assignments)):
            print("Invalid number.")
            return
    except ValueError:
        print("Please enter a valid integer.")
        return

    a = assignments[idx - 1]
    print("\nPress Enter to keep the current value.")

    new_name = input(f"Name [{a.name}]: ").strip()
    if new_name:
        a.name = new_name

    new_weight = input(f"Weight % [{a.weight_percent}]: ").strip()
    if new_weight:
        try:
            w = float(new_weight)
            if 0 <= w <= 100:
                a.weight_percent = w
            else:
                print("Weight must be 0–100. Keeping old value.")
        except ValueError:
            print("Invalid weight. Keeping old value.")

    new_due = input(f"Due date YYYY-MM-DD [{a.due_date.isoformat()}]: ").strip()
    if new_due:
        try:
            a.due_date = parse_date(new_due)
        except ValueError:
            print("Invalid date format. Keeping old value.")

    new_conf = input(f"Confidence 1-5 [{a.confidence}]: ").strip()
    if new_conf:
        try:
            c = int(new_conf)
            if 1 <= c <= 5:
                a.confidence = c
            else:
                print("Confidence must be 1–5. Keeping old value.")
        except ValueError:
            print("Invalid confidence. Keeping old value.")

    new_hours = input(f"Estimated hours [{a.estimated_hours}]: ").strip()
    if new_hours:
        try:
            h = float(new_hours)
            if h >= 0:
                a.estimated_hours = h
            else:
                print("Hours can't be negative. Keeping old value.")
        except ValueError:
            print("Invalid hours. Keeping old value.")

    print(f"Updated: {a.name}")


from datetime import timedelta  # put this with your other datetime imports if not already there


def workload_projection(assignments: List[Assignment], today: date, days: int = 7) -> List[Dict[str, object]]:
    """
    Projects workload for the next `days` days.

    Simple model (good enough for v1):
    - For each assignment, assume you start today and spread work evenly across remaining days.
    - daily_hours_for_assignment = estimated_hours / max(1, days_left)

    Output: list of day entries with total hours + per-assignment breakdown.
    """
    projection: List[Dict[str, object]] = []

    for i in range(days):
        day = today + timedelta(days=i)
        total = 0.0
        breakdown: List[Dict[str, object]] = []

        for a in assignments:
            dleft = days_until(a.due_date, day)

            # If overdue relative to that day, skip (or you can choose to treat as "do ASAP")
            if dleft < 0:
                continue

            # If due today, put all remaining hours today (effective_days = 1)
            effective_days = max(1, dleft)

            daily_hours = a.estimated_hours / effective_days

            # Only count it if the assignment is still pending on that day
            # (if day is after due date, it won't be included because dleft < 0)
            total += daily_hours
            breakdown.append({
                "name": a.name,
                "daily_hours": round(daily_hours, 2),
                "due_date": a.due_date.isoformat()
            })

        projection.append({
            "date": day.isoformat(),
            "total_hours": round(total, 2),
            "breakdown": breakdown
        })

    return projection


def hours_next_days(assignments: List[Assignment], today: date, window_days: int = 3) -> Dict[str, object]:
    """
    Returns total projected hours required over the next `window_days` days.
    """
    proj = workload_projection(assignments, today, days=window_days)
    total = round(sum(day["total_hours"] for day in proj), 2)
    return {
        "window_days": window_days,
        "total_hours": total,
        "days": proj
    }


def workload_text_bars(assignments: List[Assignment], today: date, days: int = 7, blocks_per_hour: int = 2) -> List[str]:
    """
    Returns text lines like:
      2026-02-11 | 3.5h | ███████
    blocks_per_hour controls bar length.
    """
    proj = workload_projection(assignments, today, days=days)
    lines: List[str] = []

    for day in proj:
        h = float(day["total_hours"])
        blocks = int(round(h * blocks_per_hour))
        bar = "█" * blocks if blocks > 0 else ""
        lines.append(f"{day['date']} | {h}h | {bar}")

    return lines

def expected_score_from_confidence(confidence: int) -> float:
    """
    Map confidence (1–5) to expected score (0–100).
    Tune later based on your real outcomes.
    """
    mapping = {
        1: 65.0,
        2: 75.0,
        3: 83.0,
        4: 90.0,
        5: 96.0
    }
    return float(mapping.get(confidence, 83.0))


def projected_grade_after_assignment(current_grade: float, weight_percent: float, assignment_score: float) -> float:
    """
    Simple weighted-grade model:
      new = current*(1-w) + score*w
    where w = weight_percent/100
    """
    w = clamp(weight_percent / 100.0, 0.0, 1.0)
    current_grade = clamp(current_grade, 0.0, 100.0)
    assignment_score = clamp(assignment_score, 0.0, 100.0)
    return round(current_grade * (1 - w) + assignment_score * w, 2)


def gpa_impact_estimate(a: Assignment, current_grade: float, predicted_score: float = None) -> Dict[str, object]:
    """
    Estimates potential grade change from this assignment.

    - predicted_score defaults from confidence if not provided
    - flags 'drop_risk' when weight is big + confidence low
    """
    if predicted_score is None:
        predicted_score = expected_score_from_confidence(a.confidence)

    new_grade = projected_grade_after_assignment(current_grade, a.weight_percent, predicted_score)
    delta = round(new_grade - current_grade, 2)

    # "Drop risk" heuristic (resume-worthy logic):
    # big weight OR due soon + low confidence => warning
    weight_flag = a.weight_percent >= 20
    confidence_flag = a.confidence <= 2
    drop_risk = weight_flag and confidence_flag

    # Severity label by magnitude of delta
    mag = abs(delta)
    if mag < 0.5:
        severity = "Tiny"
    elif mag < 1.5:
        severity = "Noticeable"
    else:
        severity = "Big"

    return {
        "name": a.name,
        "current_grade": round(current_grade, 2),
        "weight_percent": a.weight_percent,
        "predicted_score": round(predicted_score, 2),
        "projected_grade": new_grade,
        "delta_points": delta,  # negative = drop
        "severity": severity,
        "drop_risk": drop_risk,
        "message": (
            f"Potential grade change: {delta} points."
            + (" ⚠️ High weight + low confidence." if drop_risk else "")
        )
    }

# ----------------------------
#Main Function
# ----------------------------

if __name__ == "__main__":
    DATA_FILE = "assignments.json"

    # Load saved assignments
    all_assignments = load_assignments(DATA_FILE)
    print(f"(Loaded {len(all_assignments)} assignments from {DATA_FILE})")

    while True:
        # Update today's date each loop (so it stays accurate if program stays open)
        today = date.today()

        print("\n===== StudentOS Menu =====")
        print("1) Add assignment")
        print("2) Edit assignment")
        print("3) Remove assignment")
        print("4) Show dashboard")
        print("5) List assignments (sorted by danger)")
        print("6) Save & quit")

        choice = input("Choose an option (1-6): ").strip()

        # ---------------- ADD ----------------
        if choice == "1":
            new_a = input_assignment()
            all_assignments.append(new_a)
            save_assignments(DATA_FILE, all_assignments)
            print(f"Saved. Added: {new_a.name}")

        # ---------------- EDIT ----------------
        elif choice == "2":
            edit_assignment(all_assignments)
            save_assignments(DATA_FILE, all_assignments)
            print("Saved edits.")

        # ---------------- REMOVE ----------------
        elif choice == "3":
            if not all_assignments:
                print("No assignments to remove.")
                continue

            print("\nAssignments:")
            for i, a in enumerate(all_assignments, start=1):
                print(f"{i}) {a.name} (due {a.due_date.isoformat()})")

            try:
                idx = int(input("Enter number to remove: ").strip())
                if 1 <= idx <= len(all_assignments):
                    removed = all_assignments.pop(idx - 1)
                    save_assignments(DATA_FILE, all_assignments)
                    print(f"Removed: {removed.name}")
                else:
                    print("Invalid number.")
            except ValueError:
                print("Please enter a valid integer.")

        # ---------------- DASHBOARD ----------------
        elif choice == "4":
            if not all_assignments:
                print("No assignments yet. Add one first.")
                continue

            print("\n=== DASHBOARD SUMMARY ===")
            summary = dashboard_summary(all_assignments, today)

            for line in summary["headlines"]:
                print(line)

            print(summary["stress_forecast"]["message"])

        # ---------------- LIST SORTED BY DANGER ----------------
        elif choice == "5":
            if not all_assignments:
                print("No assignments yet.")
                continue

            print("\n=== ALL ASSIGNMENTS (Sorted by Danger) ===")

            ranked = rank_assignments_by_danger(all_assignments, today)
            by_name = {a.name: a for a in all_assignments}

            # Urgency zone emojis
            zone_emoji = {
                "Safe": "🌿",
                "Steady": "🚶‍♂️",
                "Crunch Zone": "⏳",
                "Panic Zone": "🚨"
            }

            # Risk level emojis
            risk_emoji = {
                "Low": "✅",
                "Medium": "⚠️",
                "High": "🔥"
            }

            for item in ranked:
                a = by_name[item["name"]]
                dleft = days_until(a.due_date, today)

                if dleft > 0:
                    day_word = "day" if dleft == 1 else "days"
                    dleft_text = f"{dleft} {day_word} left"
                elif dleft == 0:
                    dleft_text = "Due today"
                else:
                    day_word = "day" if abs(dleft) == 1 else "days"
                    dleft_text = f"{abs(dleft)} {day_word} overdue"

                z_em = zone_emoji.get(item["zone"], "")
                r_em = risk_emoji.get(item["risk_label"], "")

                print(
                    f"{z_em} {r_em} {item['name']} | "
                    f"{dleft_text} | "
                    f"Danger {item['danger_score']} | "
                    f"{item['risk_label']} ({item['risk_score']}) | "
                    f"{item['zone']} ({item['hours_per_day']} hrs/day)"
                )

        # ---------------- QUIT ----------------
        elif choice == "6":
            save_assignments(DATA_FILE, all_assignments)
            print(f"Saved to {DATA_FILE}. Goodbye.")
            break

        else:
            print("Please choose a number from 1 to 6.")

