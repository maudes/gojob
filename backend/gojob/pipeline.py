"""The one path every AI output takes.

The capable writer produces it, five light auditors check it against the sources on a fixed
checklist, and a code-level check proves every quote exists word for word in its source.
If it fails, the flagged items go back to the writer once and all five audit again.
"""
from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

from . import demo
from . import prompts as P
from .claude import AgentError, has_credentials, run_json, run_with_search
from .config import MAIN_MODEL, PROMPTS_DIR, REVIEWER_MODEL
from .meta import stamp
from .schemas import Audit, CoverLetter, FineTune, HealthCheck, Interview, JDAnalysis, Networking, PanelScore
from .text import is_verbatim, redact

AUDITOR_COUNT = len(P.AUDIT_FOCUS)
#: Every auditor must score strictly above this.
AUDIT_PASS_ABOVE = 95

EMPTY_QUOTE_CHECK = {"total": 0, "verified": 0, "failed": []}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def round_half_up(x: float) -> int:
    """JavaScript's Math.round, which the first version used. Python's round() goes to even."""
    return math.floor(x + 0.5)


def clamp_score(x: float) -> int:
    return max(0, min(100, round_half_up(x)))


# ---------- Deterministic proof: every quote must exist in its source ----------


def check_quotes(output: Any, sources: dict[str, str]) -> dict:
    found: list[tuple[str, str]] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, str) and key in ("orderedBullets", "drop"):
                    found.append(("resume", item))
                else:
                    walk(item, key)
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("quote"), str) and node.get("source") in ("resume", "jd"):
            found.append((node["source"], node["quote"]))
        if isinstance(node.get("find"), str) and isinstance(node.get("replace"), str):
            found.append(("resume", node["find"]))
        for k, v in node.items():
            walk(v, k)

    walk(output)
    real = [(s, q) for s, q in found if q.strip()]
    failed = [{"source": s, "quote": q} for s, q in real if not is_verbatim(q, sources[s])]
    return {"total": len(real), "verified": len(real) - len(failed), "failed": failed}


# ---------- Five lightweight auditors ----------


def _dumps(obj: Any, **kw: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, **kw)


def run_audits(context: str, output: Any, lang: P.Lang, note: str = "") -> list[dict]:
    audit_note = f"<AUDIT_NOTE>\n{note}\n</AUDIT_NOTE>\n" if note else ""
    user = f"{context}\n{audit_note}<OUTPUT>\n{_dumps(output, indent=1)}\n</OUTPUT>"
    language = "Write issues in Taiwan Traditional Chinese." if lang == "zh" else "Write issues in English."

    def one(focus: str) -> dict:
        audit = run_json(
            schema=Audit, model=REVIEWER_MODEL, system=f"{P.audit_role(focus)}\n\n{language}", user=user, effort="low"
        )
        return {**audit.dump(), "score": clamp_score(audit.score)}

    with ThreadPoolExecutor(max_workers=AUDITOR_COUNT) as pool:
        return list(pool.map(one, P.AUDIT_FOCUS))


def is_approved(audits: list[dict], quote_check: dict) -> bool:
    """Approved only when all five auditors score above 95, tick every box, and every quote is verbatim."""
    return (
        len(audits) == AUDITOR_COUNT
        and all(a["score"] > AUDIT_PASS_ABOVE and all(a["checks"].values()) for a in audits)
        and not quote_check["failed"]
    )


def demo_audit() -> dict:
    return {"audits": demo.AUDITS, "quoteCheck": dict(EMPTY_QUOTE_CHECK), "approved": True, "demo": True}


def with_audit(
    *,
    produce: Callable[[str], Any],
    context: str,
    lang: P.Lang,
    check: Callable[[Any], dict] | None = None,
    note: str = "",
    repair: bool = True,
) -> dict:
    """Returns {output, audits, quoteCheck, approved, demo}."""
    check = check or (lambda _o: dict(EMPTY_QUOTE_CHECK))
    output = produce("")
    audits = run_audits(context, output, lang, note)
    quote_check = check(output)
    if repair and not is_approved(audits, quote_check):
        problems = [
            *[issue for a in audits for issue in a["issues"]],
            *[
                f'This text is attributed to the {f["source"]} but is not found there word for word: "{f["quote"]}"'
                for f in quote_check["failed"]
            ],
        ]
        if problems:
            unique = list(dict.fromkeys(problems))
            output = produce(
                f"\n<PREVIOUS_OUTPUT>\n{_dumps(output, separators=(',', ':'))}\n</PREVIOUS_OUTPUT>\n<REVIEW_ISSUES>\n"
                + "\n".join(f"- {p}" for p in unique)
                + "\n</REVIEW_ISSUES>\nProduce the output again. Keep everything the reviewers did not flag. Fix or remove each flagged item so that it is fully supported by the sources."
            )
            audits = run_audits(context, output, lang, note)
            quote_check = check(output)
    return {"output": output, "audits": audits, "quoteCheck": quote_check, "approved": is_approved(audits, quote_check), "demo": False}


def _stamped(result: dict, runs: int) -> dict:
    return {**result, "runs": runs, "generatedAt": now_iso(), "meta": stamp()}


def reviewed(*, schema: type[BaseModel], role: str, context: str, sources: dict, lang: P.Lang, runs: int) -> dict:
    result = with_audit(
        produce=lambda extra: run_json(schema=schema, model=MAIN_MODEL, system=P.system(role, lang), user=context + extra, effort="high").dump(),
        context=context,
        lang=lang,
        check=lambda output: check_quotes(output, sources),
    )
    return _stamped(result, runs)


def demo_reviewed(output: Any, runs: int) -> dict:
    return _stamped({"output": output, "audits": demo.AUDITS, "quoteCheck": dict(EMPTY_QUOTE_CHECK), "approved": True, "demo": True}, runs)


# ---------- Three scoring reviewers ----------

PANEL_NOTE = (
    "The OUTPUT is three reviewers' scores with their verdicts, strengths and gaps. Judge whether each verdict, strength and gap is supported by the sources "
    "and whether every proof quote is word for word. A score is an opinion: flag it only when its own verdict contradicts the evidence it cites."
)


def run_panel(context: str, target: str, lang: P.Lang, sources: dict) -> tuple[list[dict], dict]:
    """The three scoring reviewers, whose own output is then audited like everything else."""

    def produce(extra: str) -> list[dict]:
        def one(lens: dict) -> dict:
            score = run_json(schema=PanelScore, model=MAIN_MODEL, system=P.system(P.panel_role(lens["lens"], target), lang), user=context + extra, effort="medium")
            return {**score.dump(), "score": clamp_score(score.score), "reviewer": lens["id"]}

        with ThreadPoolExecutor(max_workers=len(P.PANEL_LENSES)) as pool:
            return list(pool.map(one, P.PANEL_LENSES))

    result = with_audit(produce=produce, context=context, lang=lang, check=lambda o: check_quotes(o, sources), note=PANEL_NOTE)
    panel = result.pop("output")
    return panel, result


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


# ---------- Public entry points ----------


def health_check(profile: dict, lang: P.Lang, runs: int) -> dict:
    if not has_credentials():
        return {
            "check": demo_reviewed(demo.health(profile["resumeText"]), runs),
            "panel": demo.panel([72, 84, 78]),
            "panelAudit": demo_audit(),
            "gate": gate([72, 84, 78], 80, 70),
            "profileSavedAt": profile["savedAt"],
        }
    context = f"{P.profile_block(profile)}\n{P.target_jds_block(profile)}"
    sources = {"resume": redact(profile["resumeText"]), "jd": "\n".join(j["text"] for j in profile["targetJDs"])}
    with ThreadPoolExecutor(max_workers=2) as pool:
        check_f = pool.submit(reviewed, schema=HealthCheck, role=P.HEALTH_ROLE, context=context, sources=sources, lang=lang, runs=runs)
        panel_f = pool.submit(run_panel, context, "profile", lang, sources)
        check, (panel, panel_audit) = check_f.result(), panel_f.result()
    return {"check": check, "panel": panel, "panelAudit": panel_audit, "gate": gate([p["score"] for p in panel], 80, 70), "profileSavedAt": profile["savedAt"]}


def analyze_jd(profile: dict, resume_text: str, jd_text: str, lang: P.Lang, runs: int, improved: bool = False) -> dict:
    """Matching assessment for one JD. `resume_text` is the tailored version when there is one."""
    if not has_credentials():
        scores = [82, 85, 82] if improved else [68, 76, 71]
        return {"analysis": demo_reviewed(demo.JD_ANALYSIS, runs), "panel": demo.panel(scores), "panelAudit": demo_audit(), "gate": gate(scores, 80, 60)}
    context = f"{P.profile_block(profile, resume_text)}\n{P.jd_block(jd_text)}"
    sources = {"resume": redact(resume_text), "jd": jd_text}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a_f = pool.submit(reviewed, schema=JDAnalysis, role=P.JD_ROLE, context=context, sources=sources, lang=lang, runs=runs)
        p_f = pool.submit(run_panel, context, "jd", lang, sources)
        analysis, (panel, panel_audit) = a_f.result(), p_f.result()
    return {"analysis": analysis, "panel": panel, "panelAudit": panel_audit, "gate": gate([p["score"] for p in panel], 80, 60)}


def parse_loose_json(text: str, what: str = "networking agent") -> Any:
    start, end = text.find("{"), text.rfind("}")
    try:
        if start < 0 or end <= start:
            raise ValueError
        return json.loads(text[start : end + 1])
    except ValueError as err:
        raise AgentError(f"The {what} did not return a usable list. Retry.") from err


def find_people(context: str, where: dict, lang: P.Lang, runs: int) -> dict:
    """Search the web for people at one company and draft two first-contact messages each."""
    if not has_credentials():
        return demo_reviewed(demo.NETWORKING, runs)
    text = run_with_search(
        system=P.system(P.NETWORKING_ROLE, lang),
        user=f"{context}\nCompany: {where['company']}\nRole: {where['title']}\nLocation: {where['location']}",
        max_searches=8,
        max_tokens=16000,
    )
    try:
        parsed = Networking.model_validate(parse_loose_json(text))
    except ValueError as err:
        raise AgentError("The networking agent did not return a usable list. Retry.") from err
    data = parsed.dump()
    result = with_audit(
        produce=lambda _extra: data,
        context=context,
        lang=lang,
        repair=False,
        note="Names, titles and profileUrl values come from web search and are outside the sources; do not flag them. Judge what the messages say about the candidate and the JD, and whether each message keeps the outreach rules (75 words or fewer, one question mark, no job opening, no referral request).",
    )
    return _stamped(result, runs)


def run_action(kind: str, profile: dict, record: dict, lang: P.Lang, input_text: str) -> dict:
    runs = ((record["actions"].get(kind) or {}).get("runs") or 0) + 1
    meta = record["analysis"]["output"]["meta"]
    resume_text = record.get("tailoredText") or profile["resumeText"]

    if not has_credentials():
        if kind == "onePager":
            return {"html": demo.ONE_PAGER_HTML, "runs": runs, "demo": True, "generatedAt": now_iso(), "audit": demo_audit(), "meta": stamp()}
        if kind == "fineTune":
            return demo_reviewed(demo.fine_tune(resume_text), runs)
        if kind == "coverLetter":
            return demo_reviewed(demo.cover_letter(input_text), runs)
        return demo_reviewed(getattr(demo, kind.upper()), runs)

    context = f"{P.profile_block(profile, resume_text)}\n{P.jd_block(record['jdText'])}"
    sources = {"resume": redact(resume_text), "jd": record["jdText"]}
    base = {"sources": sources, "lang": lang, "runs": runs}

    if kind == "fineTune":
        return reviewed(**base, context=context, schema=FineTune, role=P.FINE_TUNE_ROLE)
    if kind == "interview":
        return reviewed(**base, context=context, schema=Interview, role=P.INTERVIEW_ROLE)
    if kind == "coverLetter":
        motivation = f'<MOTIVATION note="written by the candidate, treat as confirmed">\n{redact(input_text) or "(nothing provided)"}\n</MOTIVATION>'
        return reviewed(**base, schema=CoverLetter, role=P.COVER_LETTER_ROLE, context=f"{context}\n{motivation}")
    if kind == "networking":
        return find_people(context, {"company": meta["company"], "title": meta["title"], "location": meta["location"]}, lang, runs)
    if kind == "onePager":
        return _one_pager(profile, record, meta, resume_text, context, lang, runs, input_text)
    raise AgentError("Unknown request.")


def _one_pager(profile: dict, record: dict, meta: dict, resume_text: str, context: str, lang: P.Lang, runs: int, input_text: str) -> dict:
    template = (PROMPTS_DIR / "one-pager.md").read_text("utf8")
    background = "\n".join(
        [
            f"Target roles: {', '.join(profile['roles'])}",
            f"Domains: {', '.join(profile['domains'])}",
            f"Resume:\n{redact(resume_text)}",
        ]
    )
    prompt = (
        template.replace("{{company}}", meta["company"] or "(see JD)")
        .replace("{{title}}", meta["title"] or (profile["roles"][0] if profile["roles"] else ""))
        .replace("{{department}}", meta["location"] or ", ".join(profile["regions"]))
        .replace("{{round}}", input_text.strip() or "Not yet")
        .replace("{{background}}", background)
    )
    html = run_with_search(
        system=P.ONE_PAGER_SYSTEM + (P.ONE_PAGER_ENGLISH if lang == "en" else ""),
        user=f"{prompt}\n\n{P.jd_block(record['jdText'])}",
        max_searches=15,
        max_tokens=64000,
    )
    cleaned = re.sub(r"```\s*$", "", re.sub(r"^.*?(?=<!DOCTYPE|<html)", "", html, count=1, flags=re.I | re.S))
    final_html = cleaned or html
    # Auditors read the report as text and judge only what it says about the candidate.
    as_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[\s\S]*?</\1>", " ", final_html, flags=re.I)))
    audit = with_audit(
        produce=lambda _extra: as_text,
        context=context,
        lang=lang,
        repair=False,
        note="The OUTPUT is a company research report built from web sources. Company facts, figures and citations are outside the sources; do not flag them. Flag only statements about the candidate (background, experience, skills, results) that RESUME and PROFILE do not support.",
    )
    audit.pop("output")
    return {"html": final_html, "runs": runs, "demo": False, "generatedAt": now_iso(), "audit": audit, "meta": stamp()}
