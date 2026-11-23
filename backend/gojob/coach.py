"""Step 5, interview coach: one practice question at a time, feedback, weekly report."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from . import context_blocks as P
from .model_client import has_credentials, run_json
from .config import MAIN_MODEL
from .version_stamp import stamp
from .audit import demo_audit, with_audit
from .scoring import clamp_score
from .schemas import CoachFeedback, CoachQuestion, CoachReport
from .text_tools import is_verbatim, redact

CATEGORIES = ["self_intro", "behavioral", "general", "story", "jd", "product"]
#: Roughly what fits when spoken at a calm pace.
TARGET_WORDS = {"30s": (55, 90), "2min": (230, 320)}
DAY = 86400.0

DEMO_QUESTIONS = {
    "self_intro": "Tell me about yourself and why you are looking at product roles now.",
    "behavioral": "What is a weakness you are actively working on, and what have you changed because of it?",
    "general": "What kind of team do you do your best work in?",
    "story": "Pick one project from your resume. What was the hardest decision you made on it?",
    "jd": "Which requirement in this job description are you least sure you meet, and how would you close that gap?",
    "product": "Choose a feature you use every day. How would you decide whether to improve it or remove it?",
}


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def pick_category(items: list[dict], has_jd: bool, now: float | None = None) -> str:
    """Pick the next category: the least practised in the last 14 days, with categories
    that scored low counted as less practised so they come back more often."""
    now = _now() if now is None else now
    recent = [i for i in items if now - _ts(i["at"]) < 14 * DAY]
    last = items[0]["category"] if items else None
    best, best_weight = "self_intro", float("inf")
    for c in CATEGORIES:
        if c == "jd" and not has_jd:
            continue
        mine = [i for i in recent if i["category"] == c]
        avg = sum(i["feedback"]["score"] for i in mine) / len(mine) if mine else 100
        weight = len(mine) - (1.5 if avg < 70 else 0) + (0.5 if c == last else 0)
        if weight < best_weight:
            best, best_weight = c, weight
    return best


def top_weaknesses(items: list[dict], now: float | None = None) -> list[tuple[str, int]]:
    """The weaknesses that showed up most in the last 14 days."""
    now = _now() if now is None else now
    counts: Counter[str] = Counter()
    for i in items:
        if now - _ts(i["at"]) > 14 * DAY:
            continue
        counts.update(i["feedback"]["weaknesses"])
    # most_common keeps first-seen order among ties, like the sort in the first version
    return counts.most_common(3)


def _from_module_two(records: list[dict], asked: set[str]) -> dict | None:
    for r in records:
        interview = r["actions"].get("interview")
        q = next((x for x in interview["output"]["questions"] if x["question"] not in asked), None) if interview else None
        if q:
            return {
                "category": "jd",
                "source": f"{r['analysis']['output']['meta']['company'] or 'JD'} · {q['interviewer']}",
                "question": q["question"],
                "storyHint": " · ".join(q["keyElements"]),
                "why": q["why"],
                "demo": interview.get("demo", False),
            }
    return None


def next_question(*, profile: dict, coach: dict, records: list[dict], category: str, lang: P.Lang) -> dict:
    category = pick_category(coach["items"], len(records) > 0) if category == "auto" else category
    asked = {i["question"] for i in coach["items"]}

    # JD practice starts with the questions already prepared for that job in module 2.
    if category == "jd":
        ready = _from_module_two(records, asked)
        if ready:
            return ready
    jd = records[0] if records else None
    if category == "jd" and jd:
        source = jd["analysis"]["output"]["meta"]["company"] or "JD"
    elif category == "story" and coach["storyBank"]["text"]:
        source = "Story bank"
    else:
        source = ""

    if not has_credentials():
        return {
            "category": category,
            "source": source,
            "question": DEMO_QUESTIONS[category],
            "storyHint": "Sample question. Add an API key for questions built from your story bank and JDs.",
            "why": "",
            "demo": True,
            "audit": demo_audit(),
            "meta": stamp(),
        }

    weak = ", ".join(f"{w} ({n}x)" for w, n in top_weaknesses(coach["items"])) or "none recorded"
    recent = "\n".join(f"- {i['question']}" for i in coach["items"][:30]) or "(none)"
    jd_part = f"\n<JD>\n{jd['jdText']}\n</JD>" if category == "jd" and jd else ""
    context = (
        f"Category: {P.skill(f"coach-question#category-{category}")}\nRecurring weaknesses (last 14 days): {weak}\n\n<RECENT_QUESTIONS>\n{recent}\n</RECENT_QUESTIONS>\n"
        f"{P.profile_block(profile)}\n<STORY_BANK>\n{redact(coach['storyBank']['text']) or '(not provided)'}\n</STORY_BANK>{jd_part}"
    )

    def produce(extra: str) -> dict:
        return run_json(
            schema=CoachQuestion,
            model=MAIN_MODEL,
            effort="low",
            system=f"{P.coach_rules(lang)}\n\n{P.skill('coach-question')}",
            user=context + extra,
        ).dump()

    result = with_audit(produce=produce, context=context, lang=lang, note=P.skill("interview-coach#audit-note") + " " + P.skill("coach-question#audit-note"))
    out = result.pop("output")
    return {"category": category, "source": source, **out, "demo": False, "audit": result, "meta": stamp()}


def give_feedback(*, profile: dict, coach: dict, prompt: dict, mode: str, answer: str, seconds: float, jd_text: str, lang: P.Lang) -> tuple[dict, dict]:
    count = len(answer.split())
    lo, hi = TARGET_WORDS[mode]
    if not has_credentials():
        long, short = count > hi, count < lo
        feedback = {
            "score": 62 if long or short else 78,
            "headline": "Sample feedback. Add an API key for real coaching on your answer.",
            "content": [{"element": e, "present": e != "impact", "note": "Sample note."} for e in ("situation", "challenge", "decision", "impact", "relevance")],
            "english": [],
            "delivery": f"{count} words. Target for the {'30-second' if mode == '30s' else '2-minute'} version is {lo} to {hi}.",
            "tighter": "",
            "weaknesses": [*(["too_long"] if long else []), *(["too_short"] if short else []), "no_impact"],
            "confirm": [],
        }
        return feedback, demo_audit()

    time_line = f"\nTime taken: {seconds:g} seconds" if seconds else ""
    jd_part = f"\n<JD>\n{jd_text}\n</JD>" if jd_text else ""
    context = (
        f"Question ({prompt['category']}): {prompt['question']}\nVersion: {'30 seconds' if mode == '30s' else '2 minutes'}\nWord count: {count}{time_line}\n\n"
        f"<ANSWER>\n{redact(answer)}\n</ANSWER>\n{P.profile_block(profile)}\n<STORY_BANK>\n{redact(coach['storyBank']['text']) or '(not provided)'}\n</STORY_BANK>{jd_part}"
    )

    def produce(extra: str) -> dict:
        return run_json(
            schema=CoachFeedback,
            model=MAIN_MODEL,
            effort="medium",
            system=f"{P.coach_rules(lang)}\n\n{P.coach_feedback_task(lo, hi)}",
            user=context + extra,
        ).dump()

    redacted_answer = redact(answer)

    def check(out: dict) -> dict:
        # Code-level proof: every English correction must quote the candidate's own words.
        quotes = [e["original"] for e in out["english"] if e["original"].strip()]
        failed = [{"source": "answer", "quote": q} for q in quotes if not is_verbatim(q, redacted_answer)]
        return {"total": len(quotes), "verified": len(quotes) - len(failed), "failed": failed}

    result = with_audit(produce=produce, context=context, lang=lang, note=P.skill("interview-coach#audit-note"), check=check)
    out = result.pop("output")
    return {**out, "score": clamp_score(out["score"])}, result


def weekly_report(coach: dict, lang: P.Lang, now: float | None = None) -> dict:
    now = _now() if now is None else now
    week = [i for i in coach["items"] if now - _ts(i["at"]) < 7 * DAY]
    counts = dict(Counter(i["category"] for i in week))
    base = {"at": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "counts": counts, "total": len(week)}
    if not has_credentials() or not week:
        return {
            **base,
            "demo": True,
            "audit": demo_audit(),
            "meta": stamp(),
            "output": {
                "strengths": ["Sample: add an API key for a written review of your week."] if week else [],
                "weakAreas": [f"{w} ({n}x)" for w, n in top_weaknesses(coach["items"], now)],
                "prepare": [],
                "delivery30": "",
                "delivery2min": "",
            },
        }
    log = "\n\n".join(
        f"[{i['at'][:10]}] {i['category']} · {i['mode']} · score {i['feedback']['score']} · {len(i['answer'].split())} words · "
        f"weaknesses: {', '.join(i['feedback']['weaknesses']) or 'none'}\nQ: {i['question']}\nCoach: {i['feedback']['headline']}"
        for i in week
    )
    context = f"<LOG>\n{log}\n</LOG>"

    def produce(extra: str) -> dict:
        return run_json(
            schema=CoachReport,
            model=MAIN_MODEL,
            effort="medium",
            system=f"{P.coach_rules(lang)}\n\n{P.skill('coach-report')}",
            user=context + extra,
        ).dump()

    result = with_audit(produce=produce, context=context, lang=lang, note=P.skill("coach-report#audit-note"))
    output = result.pop("output")
    return {**base, "demo": False, "output": output, "audit": result, "meta": stamp()}


def session_log(items: list[dict]) -> str:
    """A Markdown log of practice sessions, for the user's own records."""
    by_day: dict[str, list[dict]] = {}
    for i in items:
        by_day.setdefault(i["at"][:10], []).append(i)
    days = []
    for day, lst in by_day.items():
        entries = [
            f"## {i['category']} · {i['mode']} · score {i['feedback']['score']}\n\n**Q:** {i['question']}\n\n**Answer:** {i['answer']}\n\n"
            f"**Coach:** {i['feedback']['headline']}\n\n**Weaknesses:** {', '.join(i['feedback']['weaknesses']) or 'none'}"
            for i in lst
        ]
        days.append("\n\n".join([f"# Interview practice {day}", *entries]))
    return "\n\n---\n\n".join(days)

