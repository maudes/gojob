"""What each button does: health check, JD match, fine-tune, cover letter, interview prep, networking, one-pager.
Each one builds its context, calls the model through the audit loop, and returns a stamped result. Used by api.py."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel

from . import context_blocks as P
from . import model_client, sample_data
from .audit import EMPTY_QUOTE_CHECK, check_quotes, demo_audit, with_audit
from .config import MAIN_MODEL
from .model_client import AgentError, has_credentials
from .schemas import CoverLetter, FineTune, HealthCheck, Interview, JDAnalysis, Networking, PanelScore
from .scoring import HEALTH_NEED_AVERAGE, HEALTH_NEED_MIN, JD_NEED_AVERAGE, JD_NEED_MIN, clamp_score, gate
from .store import new_id, now_iso
from .text_tools import keep_editable, redact
from .version_stamp import stamp


def _stamped(result: dict, runs: int) -> dict:
    return {**result, "runs": runs, "generatedAt": now_iso(), "meta": stamp()}


def reviewed(*, schema: type[BaseModel], role: str, context: str, sources: dict, lang: P.Lang, runs: int) -> dict:
    def produce(extra: str) -> dict:
        output = model_client.run_json(schema=schema, model=MAIN_MODEL, system=P.system(role, lang), user=context + extra, effort="high").dump()
        if isinstance(output.get("changes"), list):
            # Layout lock: a tracked change never lands on the name, contact, section title, employer, title, date or school lines.
            output["changes"], _ = keep_editable(output["changes"], sources["resume"])
        return output

    result = with_audit(
        produce=produce,
        context=context,
        lang=lang,
        check=lambda output: check_quotes(output, sources),
    )
    return _stamped(result, runs)


def demo_reviewed(output: Any, runs: int) -> dict:
    return _stamped({"output": output, "audits": sample_data.AUDITS, "quoteCheck": dict(EMPTY_QUOTE_CHECK), "approved": True, "demo": True}, runs)


# ---------- Three scoring reviewers ----------

PANEL_NOTE = (
    "The OUTPUT is three reviewers' scores with their verdicts, strengths and gaps. Judge whether each verdict, strength and gap is supported by the sources "
    "and whether every proof quote is word for word. A score is an opinion: flag it only when its own verdict contradicts the evidence it cites."
)


def run_panel(context: str, target: str, lang: P.Lang, sources: dict) -> tuple[list[dict], dict]:
    """The three scoring reviewers, whose own output is then audited like everything else."""

    def produce(extra: str) -> list[dict]:
        def one(reviewer: str) -> dict:
            score = model_client.run_json(schema=PanelScore, model=MAIN_MODEL, system=P.system(P.panel_role(reviewer, target), lang), user=context + extra, effort="medium")
            return {**score.dump(), "score": clamp_score(score.score), "reviewer": reviewer}

        with ThreadPoolExecutor(max_workers=len(P.PANEL_LENSES)) as pool:
            return list(pool.map(one, P.PANEL_LENSES))

    result = with_audit(produce=produce, context=context, lang=lang, check=lambda o: check_quotes(o, sources), note=PANEL_NOTE)
    panel = result.pop("output")
    return panel, result


# ---------- Public entry points ----------


def health_check(profile: dict, lang: P.Lang, runs: int) -> dict:
    if not has_credentials():
        return {
            "check": demo_reviewed(sample_data.health(profile["resumeText"]), runs),
            "panel": sample_data.panel([72, 84, 78]),
            "panelAudit": demo_audit(),
            "gate": gate([72, 84, 78], HEALTH_NEED_AVERAGE, HEALTH_NEED_MIN),
            "profileSavedAt": profile["savedAt"],
        }
    context = f"{P.profile_block(profile)}\n{P.target_jds_block(profile)}"
    sources = {"resume": redact(profile["resumeText"]), "jd": "\n".join(j["text"] for j in profile["targetJDs"])}
    with ThreadPoolExecutor(max_workers=2) as pool:
        check_f = pool.submit(reviewed, schema=HealthCheck, role=P.skill("health-check"), context=context, sources=sources, lang=lang, runs=runs)
        panel_f = pool.submit(run_panel, context, "profile", lang, sources)
        check, (panel, panel_audit) = check_f.result(), panel_f.result()
    return {"check": check, "panel": panel, "panelAudit": panel_audit, "gate": gate([p["score"] for p in panel], HEALTH_NEED_AVERAGE, HEALTH_NEED_MIN), "profileSavedAt": profile["savedAt"]}


def analyze_jd(profile: dict, resume_text: str, jd_text: str, lang: P.Lang, runs: int, improved: bool = False) -> dict:
    """Matching assessment for one JD. `resume_text` is the tailored version when there is one."""
    if not has_credentials():
        scores = [82, 85, 82] if improved else [68, 76, 71]
        return {"analysis": demo_reviewed(sample_data.JD_ANALYSIS, runs), "panel": sample_data.panel(scores), "panelAudit": demo_audit(), "gate": gate(scores, JD_NEED_AVERAGE, JD_NEED_MIN)}
    context = f"{P.profile_block(profile, resume_text)}\n{P.jd_block(jd_text)}"
    sources = {"resume": redact(resume_text), "jd": jd_text}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a_f = pool.submit(reviewed, schema=JDAnalysis, role=P.skill("jd-match"), context=context, sources=sources, lang=lang, runs=runs)
        p_f = pool.submit(run_panel, context, "jd", lang, sources)
        analysis, (panel, panel_audit) = a_f.result(), p_f.result()
    return {"analysis": analysis, "panel": panel, "panelAudit": panel_audit, "gate": gate([p["score"] for p in panel], JD_NEED_AVERAGE, JD_NEED_MIN)}


def history_point(g: dict) -> dict:
    return {"at": now_iso(), "average": g["average"], "scores": g["scores"]}


def new_record(profile: dict, jd_text: str, jd_url: str, lang: P.Lang) -> dict:
    """A new saved JD assessment: the match analysis on the saved resume, plus the bookkeeping fields."""
    result = analyze_jd(profile, profile["resumeText"], jd_text, lang, 1)
    return {
        "id": new_id(),
        "jdUrl": jd_url,
        "jdText": jd_text,
        "createdAt": now_iso(),
        "tailoredText": None,
        "assessedText": profile["resumeText"],
        "history": [history_point(result["gate"])],
        "networkTarget": "",
        **result,
        "actions": {},
    }


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
        return demo_reviewed(sample_data.NETWORKING, runs)
    text = model_client.run_with_search(
        system=P.system(P.skill("networking"), lang),
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
            return {"html": sample_data.ONE_PAGER_HTML, "runs": runs, "demo": True, "generatedAt": now_iso(), "audit": demo_audit(), "meta": stamp()}
        if kind == "fineTune":
            return demo_reviewed(sample_data.fine_tune(resume_text), runs)
        if kind == "coverLetter":
            return demo_reviewed(sample_data.cover_letter(input_text), runs)
        return demo_reviewed(getattr(sample_data, kind.upper()), runs)

    context = f"{P.profile_block(profile, resume_text)}\n{P.jd_block(record['jdText'])}"
    sources = {"resume": redact(resume_text), "jd": record["jdText"]}
    base = {"sources": sources, "lang": lang, "runs": runs}

    if kind == "fineTune":
        return reviewed(**base, context=context, schema=FineTune, role=P.skill("fine-tune"))
    if kind == "interview":
        return reviewed(**base, context=context, schema=Interview, role=P.skill("interview-prep"))
    if kind == "coverLetter":
        motivation = f'<MOTIVATION note="written by the candidate, treat as confirmed">\n{redact(input_text) or "(nothing provided)"}\n</MOTIVATION>'
        return reviewed(**base, schema=CoverLetter, role=P.skill("cover-letter"), context=f"{context}\n{motivation}")
    if kind == "networking":
        return find_people(context, {"company": meta["company"], "title": meta["title"], "location": meta["location"]}, lang, runs)
    if kind == "onePager":
        return _one_pager(profile, record, meta, resume_text, context, lang, runs, input_text)
    raise AgentError("Unknown request.")


def _one_pager(profile: dict, record: dict, meta: dict, resume_text: str, context: str, lang: P.Lang, runs: int, input_text: str) -> dict:
    background = "\n".join(
        [
            f"Target roles: {', '.join(profile['roles'])}",
            f"Domains: {', '.join(profile['domains'])}",
            f"Resume:\n{redact(resume_text)}",
        ]
    )
    prompt = P.skill(
        "one-pager#template",
        company=meta["company"] or "(see JD)",
        title=meta["title"] or (profile["roles"][0] if profile["roles"] else ""),
        department=meta["location"] or ", ".join(profile["regions"]),
        round=input_text.strip() or "Not yet",
        background=background,
    )
    html = model_client.run_with_search(
        system=P.skill("one-pager") + (" " + P.skill("one-pager#english") if lang == "en" else ""),
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
