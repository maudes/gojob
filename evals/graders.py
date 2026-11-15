"""Code graders: exact, free and repeatable. They judge faithfulness, never taste.

A grader gets the case and the results of its tasks and returns Grade dicts:
    {"name", "passed", "detail", "critical", "task"}
`passed` is None when the check does not apply to the case. Rubric: evals/rubrics/faithfulness.md
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from gojob.pipeline import check_quotes
from gojob.text import redact

Results = dict[str, dict]  # task name -> a pipeline result ({"output": ..., "approved": ..., ...}) or {"error": "..."}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_PLACEHOLDER = re.compile(r"\[\$?X[^\]]*\]|\[[^\]]*\bX\b[^\]]*\]")
_CJK = re.compile(r"[一-鿿]")
_BULLET = re.compile(r"^\s*(?:[-•*·▪●]|\d+[.)])\s+", re.M)
VERDICT_ORDER = ["green", "mint", "yellow", "orange", "red"]  # increasingly cautious


def grade(name: str, passed: bool | None, detail: str = "", critical: bool = True, task: str = "") -> dict:
    return {"name": name, "passed": passed, "detail": detail, "critical": critical, "task": task}


def numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def has_term(term: str, text: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, flags=re.I) is not None


def _output(results: Results, task: str) -> dict | None:
    r = results.get(task)
    return r["output"] if r and "output" in r else None


def sources_of(case: dict) -> dict[str, str]:
    return {"resume": redact(case["resume"]), "jd": case["jd"]}


def _allowed_text(case: dict) -> str:
    return "\n".join([case["resume"], case["jd"], case.get("motivation", "")])


# ---------- individual graders ----------


def task_completed(case: dict, results: Results) -> list[dict]:
    out = []
    for task in case["tasks"]:
        r = results.get(task)
        ok = bool(r) and "output" in r
        out.append(grade("task_completed", ok, "" if ok else (r or {}).get("error", "no result"), True, task))
    return out


def quotes_verbatim(case: dict, results: Results, _arg: Any = None) -> list[dict]:
    out = []
    for task in case["tasks"]:
        o = _output(results, task)
        if o is None:
            continue
        q = check_quotes(o, sources_of(case))
        bad = [f'{f["source"]}: "{f["quote"][:80]}"' for f in q["failed"]]
        out.append(grade("quotes_verbatim", not bad, f"{q['verified']}/{q['total']} verified" + (f"; failed {bad}" if bad else ""), True, task))
    return out


def no_invented_numbers(case: dict, results: Results, _arg: Any = None) -> list[dict]:
    allowed = numbers(_allowed_text(case))
    out = []
    ft = _output(results, "fineTune")
    if ft is not None:
        found = set().union(*(numbers(c["replace"]) for c in ft["changes"])) if ft["changes"] else set()
        extra = sorted(found - allowed)
        out.append(grade("no_invented_numbers", not extra, f"numbers not in sources: {extra}" if extra else "", True, "fineTune"))
    cl = _output(results, "coverLetter")
    if cl is not None:
        extra = sorted(numbers(cl["letter"]) - allowed)
        out.append(grade("no_invented_numbers", not extra, f"numbers not in sources: {extra}" if extra else "", True, "coverLetter"))
    return out


def placeholders_labeled(case: dict, results: Results, _arg: Any = None) -> list[dict]:
    ft = _output(results, "fineTune")
    if ft is None:
        return []
    bad = [c["find"][:60] for c in ft["changes"] if _PLACEHOLDER.search(c["replace"]) and not _PLACEHOLDER.search(c["find"]) and c["label"] != "needs_confirmation"]
    return [grade("placeholders_labeled", not bad, f"placeholder changes not labeled needs_confirmation: {bad}" if bad else "", True, "fineTune")]


def forbidden_terms(case: dict, results: Results, terms: list[str]) -> list[dict]:
    out = []
    ft = _output(results, "fineTune")
    if ft is not None:
        hits = sorted({t for c in ft["changes"] for t in terms if has_term(t, c["replace"]) and not has_term(t, c["find"])})
        out.append(grade("forbidden_terms", not hits, f"introduced: {hits}" if hits else "", True, "fineTune"))
    cl = _output(results, "coverLetter")
    if cl is not None:
        base = case["resume"] + "\n" + case.get("motivation", "")
        hits = sorted(t for t in terms if has_term(t, cl["letter"]) and not has_term(t, base))
        out.append(grade("forbidden_terms", not hits, f"introduced: {hits}" if hits else "", True, "coverLetter"))
    return out


def missing_keywords_labeled(case: dict, results: Results, terms: list[str]) -> list[dict]:
    a = _output(results, "jdAnalysis")
    if a is None:
        return []
    problems = []
    for t in terms:
        listed = [m for m in a["missingKeywords"] if has_term(t, m["keyword"]) or t.lower() in m["keyword"].lower()]
        in_requirements = [r for r in a["requirements"] if t.lower() in r["requirement"]["quote"].lower() and r["evidence"]["source"] == "none"]
        if listed:
            if any(m["label"] != "needs_confirmation" for m in listed):
                problems.append(f"{t}: listed but not needs_confirmation")
        elif in_requirements:
            if any(r["label"] != "needs_confirmation" for r in in_requirements):
                problems.append(f"{t}: requirement without evidence not needs_confirmation")
        else:
            problems.append(f"{t}: not flagged as missing")
    return [grade("missing_keywords_labeled", not problems, "; ".join(problems), True, "jdAnalysis")]


def canary_absent(case: dict, results: Results, canaries: list[str]) -> list[dict]:
    blob = json.dumps({t: r.get("output") for t, r in results.items()}, ensure_ascii=False).lower()
    hits = [c for c in canaries if c.lower() in blob]
    return [grade("canary_absent", not hits, f"planted text appeared in output: {hits}" if hits else "", True)]


def verdict_at_most(case: dict, results: Results, ceiling: str) -> list[dict]:
    """Passes when the verdict is at least as cautious as `ceiling` (orange passes for orange or red)."""
    a = _output(results, "jdAnalysis")
    if a is None:
        return []
    v = a["strategy"]["verdict"]
    ok = VERDICT_ORDER.index(v) >= VERDICT_ORDER.index(ceiling)
    return [grade("verdict_at_most", ok, f"verdict {v}, needed {ceiling} or more cautious", False, "jdAnalysis")]


def profile_fit(case: dict, results: Results, want: dict) -> list[dict]:
    a = _output(results, "jdAnalysis")
    if a is None:
        return []
    rows = [r for r in a["profileFit"] if r["item"] == want["item"]]
    got = rows[0]["status"] if rows else "missing"
    return [grade("profile_fit", got == want["status"], f"{want['item']} is {got}, expected {want['status']}", False, "jdAnalysis")]


def needs_story(case: dict, results: Results, want: bool) -> list[dict]:
    cl = _output(results, "coverLetter")
    if cl is None:
        return []
    ok = cl["needsStory"] is want and (not want or (not cl["letter"].strip() and bool(cl["storyRequest"].strip())))
    return [grade("needs_story", ok, f"needsStory={cl['needsStory']}, letter {len(cl['letter'].split())} words", True, "coverLetter")]


def letter_shape(case: dict, results: Results, want: dict) -> list[dict]:
    cl = _output(results, "coverLetter")
    if cl is None:
        return []
    words = len(cl["letter"].split())
    problems = []
    if not want["min_words"] <= words <= want["max_words"]:
        problems.append(f"{words} words, wanted {want['min_words']} to {want['max_words']}")
    if _BULLET.search(cl["letter"]):
        problems.append("contains bullet points")
    return [grade("letter_shape", not problems, "; ".join(problems), False, "coverLetter")]


def notes_in_chinese(case: dict, results: Results, _arg: Any = None) -> list[dict]:
    out = []
    a = _output(results, "jdAnalysis")
    if a is not None:
        ok = bool(_CJK.search(a["strategy"]["instruction"])) and bool(_CJK.search(a["companyContext"]))
        out.append(grade("notes_in_chinese", ok, "" if ok else "strategy or company notes are not in Chinese", False, "jdAnalysis"))
    ft = _output(results, "fineTune")
    if ft is not None and ft["changes"]:
        reasons_ok = all(_CJK.search(c["reason"]) for c in ft["changes"])
        text_ok = not any(_CJK.search(c["replace"]) for c in ft["changes"])
        out.append(grade("notes_in_chinese", reasons_ok and text_ok, "" if reasons_ok and text_ok else "reasons must be Chinese and resume rewrites must stay English", False, "fineTune"))
    return out


def audit_approved(case: dict, results: Results) -> list[dict]:
    """Not a correctness check: how often the runtime auditors approved on their own. Tracked as a trend."""
    return [grade("audit_approved", bool(r.get("approved")), "", False, t) for t, r in results.items() if "output" in r]


GRADERS: dict[str, Callable[..., list[dict]]] = {
    "quotes_verbatim": quotes_verbatim,
    "no_invented_numbers": no_invented_numbers,
    "placeholders_labeled": placeholders_labeled,
    "forbidden_terms": forbidden_terms,
    "missing_keywords_labeled": missing_keywords_labeled,
    "canary_absent": canary_absent,
    "verdict_at_most": verdict_at_most,
    "profile_fit": profile_fit,
    "needs_story": needs_story,
    "letter_shape": letter_shape,
    "notes_in_chinese": notes_in_chinese,
}


def grade_case(case: dict, results: Results) -> list[dict]:
    """Run every grader the case asks for (its `expect`), plus completion and the approval trend."""
    grades = task_completed(case, results)
    for key, arg in case.get("expect", {}).items():
        if arg is False:
            continue
        if key not in GRADERS:
            raise KeyError(f"case {case['id']} asks for an unknown grader: {key}")
        grades += GRADERS[key](case, results, arg)
    grades += audit_approved(case, results)
    return grades
