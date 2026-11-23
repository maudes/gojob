"""Scores and gates: the apply rule, the tuning ceiling, score rounding. No model calls.
Used by tasks.py, api.py and coach.py."""
from __future__ import annotations

import hashlib
import math

# Every score threshold of the app is here, except the auditors' pass mark (audit.py).
# The browser gets them from thresholds() (GET /api/state, config.thresholds) and shows them; it holds no numbers of its own.

#: Profile health check gate: the average must reach 80 and no reviewer may score below 70.
HEALTH_NEED_AVERAGE = 80
HEALTH_NEED_MIN = 70
#: JD match gate (apply): same bar by default, kept separate so the two can be tuned on their own.
JD_NEED_AVERAGE = 80
JD_NEED_MIN = 70
#: A JD below the apply bar is "tune" from this average up, and "risky" below it.
JD_TUNE_FROM = 60
#: After a resume change, the average must rise by at least this much, or the tuning has stopped paying off.
CEILING_MIN_GAIN = 1.0

CEILING_MESSAGE = (
    "Tuning has reached its ceiling for this JD. What is left needs real experience, not rewording. "
    "Add that experience to the resume and upload it, or choose another job."
)


def thresholds() -> dict:
    """What the browser needs to word and judge the gates. Sent with the app state."""
    return {
        "health": {"average": HEALTH_NEED_AVERAGE, "min": HEALTH_NEED_MIN},
        "jd": {"average": JD_NEED_AVERAGE, "min": JD_NEED_MIN, "tuneFrom": JD_TUNE_FROM},
    }


def round_half_up(x: float) -> int:
    """JavaScript's Math.round, which the first version used. Python's round() goes to even."""
    return math.floor(x + 0.5)


def clamp_score(x: float) -> int:
    return max(0, min(100, round_half_up(x)))


def gate(scores: list[float], need_average: float, need_min: float) -> dict:
    average = round_half_up(sum(scores) / len(scores) * 10) / 10
    low = min(scores)
    return {
        "kind": "panel",
        "scores": scores,
        "average": average,
        "min": low,
        "needAverage": need_average,
        "needMin": need_min,
        "green": average >= need_average and low >= need_min,
    }


def text_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def mark_fine_tune(output: dict, resume: str) -> dict:
    """Record which resume this fine-tune was written for and how many of its changes rest on evidence."""
    changes = (output.get("output") or {}).get("changes") or []
    output["basedOn"] = text_key(resume)
    output["evidenceBacked"] = sum(1 for c in changes if c.get("label") in ("confirmed", "inference"))
    return output


def fit_ceiling(record: dict, profile_resume: str) -> dict | None:
    """Has honest tuning run out for this JD? Tuning may only reword what the resume already shows,
    so once nothing evidence-backed is left (or the score stops rising), more passes can only reword.

    Returns None while tuning can still help, or when the resume changed since the last assessment
    (new input, so nothing is known yet).
    """
    resume = record.get("tailoredText") or profile_resume
    if resume != record.get("assessedText") or record["gate"]["green"]:
        return None
    fine_tune = (record.get("actions") or {}).get("fineTune")
    if fine_tune and fine_tune.get("basedOn") == text_key(resume) and fine_tune.get("evidenceBacked", 1) == 0:
        return {"reason": "no_evidence_left"}
    history = record.get("history") or []
    if len(history) >= 2:
        gain = round(history[-1]["average"] - history[-2]["average"], 1)
        if gain < CEILING_MIN_GAIN:
            return {"reason": "score_plateau", "gain": gain}
    return None
