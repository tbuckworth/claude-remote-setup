#!/usr/bin/env python3
"""SM-2 spaced repetition priority queue for paper review.

Reads database.json, outputs JSON array of papers due for review,
sorted by priority (highest first).

Usage: uv run --python 3.12 scripts/sr_priority.py <database.json>
"""

import json
import sys
from datetime import date, datetime
from statistics import mean


def parse_date(s):
    """Parse ISO date string to date object."""
    if not s:
        return None
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def compute_weak_levels(by_level):
    """Return list of Bloom's levels where score < 60%."""
    weak = []
    for level, (asked, correct) in by_level.items():
        if asked > 0 and correct / asked < 0.6:
            weak.append(level)
    return weak


def compute_priority(paper, today):
    """Compute SR priority score for a paper.

    Returns (priority, metadata_dict) or None if not due.
    """
    next_review = parse_date(paper.get("next_review"))
    if not next_review or next_review > today:
        return None

    # Quality urgency: worse recent scores -> higher priority
    quality_history = paper.get("quality_history", [])
    if quality_history:
        avg_quality = mean(quality_history[-3:])  # last 3 reviews
    else:
        # Estimate from quiz results
        quiz = paper.get("quiz_results")
        if quiz and quiz["total_asked"] > 0:
            pct = quiz["total_correct"] / quiz["total_asked"] * 100
            avg_quality = score_to_quality(pct)
        else:
            avg_quality = 3.0
    quality_urgency = (5 - avg_quality) / 5

    # Overdue urgency
    days_overdue = (today - next_review).days
    overdue_urgency = min(days_overdue / 30, 1.0)

    # Recency factor: the last desktop review, or the last flashcard review on the phone's Learn tab
    # (`phone_reviews`, folded in nightly by tools/fold_phone_state.py in the data repo), whichever is later
    review_dates = paper.get("review_dates", [])
    reviewed = [d for d in (parse_date(review_dates[-1]) if review_dates else None,
                            parse_date((paper.get("phone_reviews") or {}).get("last_review"))) if d]
    days_since = (today - max(reviewed)).days if reviewed else 90
    recency_factor = min(days_since / 90, 1.0)

    priority = 0.4 * quality_urgency + 0.35 * overdue_urgency + 0.25 * recency_factor

    # Compute weak levels
    quiz = paper.get("quiz_results")
    weak_levels = compute_weak_levels(quiz["by_level"]) if quiz and "by_level" in quiz else []

    return priority, {
        "id": paper["id"],
        "title": paper["title"],
        "priority": round(priority, 4),
        "days_overdue": days_overdue,
        "days_since_review": days_since,
        "last_score": f"{quiz['total_correct']}/{quiz['total_asked']}" if quiz else None,
        "avg_quality": round(avg_quality, 1),
        "easiness_factor": paper.get("easiness_factor", 2.5),
        "weak_levels": weak_levels,
        "review_file": paper.get("review_file"),
    }


def score_to_quality(pct):
    """Map quiz percentage to SM-2 quality (0-5)."""
    if pct >= 90:
        return 5
    elif pct >= 70:
        return 4
    elif pct >= 50:
        return 3
    elif pct >= 30:
        return 2
    elif pct >= 10:
        return 1
    else:
        return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: sr_priority.py <database.json>", file=sys.stderr)
        sys.exit(1)

    db_path = sys.argv[1]
    with open(db_path) as f:
        db = json.load(f)

    today = date.today()
    due = []

    for paper in db.get("papers", []):
        if paper.get("status") != "reviewed":
            continue
        result = compute_priority(paper, today)
        if result is not None:
            priority, meta = result
            due.append(meta)

    due.sort(key=lambda x: x["priority"], reverse=True)
    print(json.dumps(due, indent=2))


if __name__ == "__main__":
    main()
