"""Step 2, headhunter scan: web search for openings, then link, quote and audit checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import context_blocks as P
from .model_client import AgentError, has_credentials, run_with_search
from .extract import is_safe_url
from .jobpage import read_job_page
from .version_stamp import stamp
from .audit import check_quotes, demo_audit, with_audit
from .store import now_iso
from .tasks import parse_loose_json
from .schemas import CompanyOpenings, ScoutReport
from .text_tools import redact

MAX_JOBS = 8
MAX_COMPANIES = 5

AUDIT_NOTE = (
    "The OUTPUT is a job-market scan built from web search. Companies, postings, links, dates, visa notes and market signals come from the web and are outside the sources; "
    "do not flag them. Flag only: a statement about the candidate (experience, skills, results, level) that RESUME and PROFILE do not support; a resume proof quote that is not "
    "word for word; a wrong confirmed / inference / needs_confirmation label on a candidate statement; and an item that breaks PROFILE (a role family, work type or sponsorship "
    "need the profile rules out)."
)


def default_settings(profile: dict) -> dict:
    return {"regions": profile["regions"] or ["Global remote"], "languages": ["English"], "notes": ""}


def keep_linked(items: list[dict]) -> tuple[list[dict], int]:
    """Keep only real web addresses, so a made-up or empty link never reaches the table."""
    kept = [i for i in items if is_safe_url(i["url"].strip()) is not None]
    return kept, len(items) - len(kept)


def verify_links(urls: list[str]) -> dict[str, str]:
    """Open each link from this computer. "verified" means it read like an open job posting."""
    unique = list(dict.fromkeys(urls))

    def check(u: str) -> str:
        try:
            return "verified" if read_job_page(u) else "unverified"
        except Exception:  # noqa: BLE001 - a failing link is simply unverified
            return "unverified"

    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        return dict(zip(unique, pool.map(check, unique)))


def _demo_report(profile: dict, settings: dict) -> dict:
    role = (profile["roles"] or ["Product Manager"])[0]
    domain = (profile["domains"] or ["your domain"])[0]
    line = next((ln.strip() for ln in profile["resumeText"].split("\n") if len(ln.strip()) > 40), "")
    proof = {"source": "resume", "quote": redact(line)} if line else {"source": "none", "quote": ""}
    heats = ["steady", "warming", "unknown"]
    first_region = settings["regions"][0] if settings["regions"] else "Remote"
    return {
        "headline": "Sample result. A real scan searches each region for openings and market signals that fit your profile.",
        "direction": [
            {"theme": f"Sample: {domain}", "searchFor": f"Sample: {role} roles close to the work this resume line shows.", "proof": proof},
        ],
        "regions": [
            {
                "region": r,
                "heat": heats[i % 3],
                "summary": "Sample text. A real scan summarises hiring activity, funding and layoffs for this region, with a source link.",
                "label": "inference",
                "sourceUrl": "",
            }
            for i, r in enumerate(settings["regions"])
        ],
        "jobs": [
            {"tier": "A", "company": "Sample Devices Co", "title": f"Senior {role}", "location": f"{first_region} · Hybrid", "visa": "offered", "visaNote": "Sample: posting states relocation support.", "posted": "unverified", "url": "https://example.com/jobs/sample-1", "fit": f"Sample: direct match with your {domain} background.", "proof": proof, "label": "inference"},
            {"tier": "B", "company": "Sample Networks Ltd", "title": f"{role}, Platform", "location": "Remote", "visa": "not_mentioned", "visaNote": "Sample: visa not mentioned, confirm with the recruiter.", "posted": "unverified", "url": "https://example.com/jobs/sample-2", "fit": "Sample: adjacent industry where the same platform skills transfer.", "proof": proof, "label": "inference"},
            {"tier": "C", "company": "Sample AI Labs", "title": f"{role}, Developer Platform", "location": "Remote", "visa": "needs_confirmation", "visaNote": "Sample: hiring location unclear.", "posted": "unverified", "url": "https://example.com/jobs/sample-3", "fit": "Sample: your experience is a lever in a different field.", "proof": proof, "label": "needs_confirmation"},
        ],
        "companies": [
            {"company": "Sample Home Robotics", "url": "https://example.com/careers", "signal": "Sample: recent funding round and a new product line.", "signalUrl": "", "why": f"Sample: building in {domain} with no matching opening yet.", "roleType": role, "approach": "Sample: reach a product lead with a question about their roadmap, not a job request.", "proof": proof, "label": "inference"},
        ],
        "weekly": "",
        "priorities": ["Sample: save one job to your wish list and analyse it in step 3."],
        "unreachable": [],
    }


def run_scout(profile: dict, settings: dict, history: list[dict], lang: P.Lang, runs: int) -> dict:
    at = now_iso()
    if not has_credentials():
        output = _demo_report(profile, settings)
        return {**demo_audit(), "output": output, "links": {j["url"]: "sample" for j in output["jobs"]}, "dropped": 0, "at": at, "runs": runs, "meta": stamp()}
    week_ago = datetime.now(timezone.utc).timestamp() - 7 * 86400
    previous = "\n".join(
        f"{h['at'][:10]}: {h['headline']} | {', '.join(f'{r['region']}={r['heat']}' for r in h['regions'])}"
        for h in history
        if datetime.fromisoformat(h["at"].replace("Z", "+00:00")).timestamp() >= week_ago
    )
    context = f"{P.profile_block(profile)}\n{P.scout_settings_block(settings, previous)}"
    text = run_with_search(system=P.system(P.skill("scout"), lang), user=context, max_searches=min(30, 8 + len(settings["regions"]) * 4), max_tokens=24000)
    try:
        parsed = ScoutReport.model_validate(parse_loose_json(text, "headhunter agent")).dump()
    except ValueError as err:
        raise AgentError("The headhunter agent did not return a usable list. Retry.") from err
    jobs, dropped = keep_linked(parsed["jobs"])
    output = {**parsed, "jobs": jobs[:MAX_JOBS], "companies": parsed["companies"][:MAX_COMPANIES]}
    sources = {"resume": redact(profile["resumeText"]), "jd": ""}
    with ThreadPoolExecutor(max_workers=2) as pool:
        audit_f = pool.submit(with_audit, produce=lambda _e: output, context=context, lang=lang, repair=False, note=AUDIT_NOTE, check=lambda o: check_quotes(o, sources))
        links_f = pool.submit(verify_links, [j["url"] for j in output["jobs"]])
        audit, links = audit_f.result(), links_f.result()
    audit.pop("output")
    return {**audit, "output": output, "links": links, "dropped": dropped, "at": at, "runs": runs, "meta": stamp()}


def _audit_and_links(output: dict, context: str, profile: dict, lang: P.Lang, urls: list[str]) -> tuple[dict, dict[str, str]]:
    sources = {"resume": redact(profile["resumeText"]), "jd": ""}
    with ThreadPoolExecutor(max_workers=2) as pool:
        audit_f = pool.submit(with_audit, produce=lambda _e: output, context=context, lang=lang, repair=False, note=AUDIT_NOTE, check=lambda o: check_quotes(o, sources))
        links_f = pool.submit(verify_links, urls)
        audit, links = audit_f.result(), links_f.result()
    audit.pop("output")
    return audit, links


def refresh_part(profile: dict, settings: dict, report: dict, part: str, lang: P.Lang) -> dict:
    """Replace only the openings or only the companies with items not shown before in this scan."""
    old = report["output"]
    shown = dict(report.get("shown") or {"jobs": [], "companies": []})
    current = [j["url"] for j in old["jobs"]] if part == "jobs" else [c["company"] for c in old["companies"]]
    shown[part] = list(dict.fromkeys([*shown.get(part, []), *current]))
    refreshes = report.get("refreshes", 0) + 1

    if not has_credentials():
        fresh = _demo_report(profile, settings)
        if part == "jobs":
            items = [{**j, "company": f"{j['company']} ({refreshes + 1})", "url": f"{j['url']}-r{refreshes}"} for j in fresh["jobs"]]
            links = {j["url"]: "sample" for j in items}
        else:
            items = [{**c, "company": f"{c['company']} ({refreshes + 1})"} for c in fresh["companies"]]
            links = report["links"]
        return {**report, "output": {**old, part: items}, "links": links, "shown": shown, "refreshes": refreshes}

    context = f"{P.profile_block(profile)}\n{P.scout_settings_block(settings, '')}"
    user = f"{context}\n{P.scout_refresh_block(part, old.get('direction') or [], shown[part])}"
    text = run_with_search(system=P.system(P.skill("scout"), lang), user=user, max_searches=12, max_tokens=12000)
    try:
        parsed = ScoutReport.model_validate(parse_loose_json(text, "headhunter agent")).dump()
    except ValueError as err:
        raise AgentError("The headhunter agent did not return a usable list. Retry.") from err
    dropped = report.get("dropped", 0)
    if part == "jobs":
        kept, dropped = keep_linked(parsed["jobs"])
        seen = set(shown["jobs"])
        items = [j for j in kept if j["url"] not in seen][:MAX_JOBS]
    else:
        seen = {c.strip().lower() for c in shown["companies"]}
        items = [c for c in parsed["companies"] if c["company"].strip().lower() not in seen][:MAX_COMPANIES]
    output = {**old, part: items}
    audit, links = _audit_and_links(output, context, profile, lang, [j["url"] for j in output["jobs"]])
    return {**report, **audit, "output": output, "links": links, "dropped": dropped, "shown": shown, "refreshes": refreshes, "meta": stamp()}


def check_company(profile: dict, company: dict, lang: P.Lang) -> dict:
    """Re-check one target company. Openings not seen before are marked new."""
    now = now_iso()
    if not has_credentials():
        sample = "https://example.com/jobs/sample-watch"
        seen = any(o["url"] == sample for o in company["openings"])
        return {
            "openings": [
                {
                    "title": f"Sample: {(profile['roles'] or ['Product Manager'])[0]}",
                    "location": "Remote",
                    "url": sample,
                    "fit": "Sample opening. A real check searches this company's careers page.",
                    "firstSeen": company["openings"][0]["firstSeen"] if seen else now,
                    "isNew": not seen,
                    "link": "sample",
                }
            ],
            "note": "Sample result. Add an API key to search this company's current openings.",
            "audit": demo_audit(),
        }
    context = f"{P.profile_block(profile)}\n<COMPANY>\nName: {company['company']}\nCareers page: {company['careersUrl'] or '(not given, search for it)'}\n</COMPANY>"
    text = run_with_search(system=P.system(P.skill("company-watch"), lang), user=context, max_searches=6, max_tokens=8000)
    try:
        parsed = CompanyOpenings.model_validate(parse_loose_json(text, "headhunter agent")).dump()
    except ValueError as err:
        raise AgentError("The headhunter agent did not return a usable list. Retry.") from err
    kept, _ = keep_linked(parsed["openings"])
    output = {**parsed, "openings": kept[:6]}
    sources = {"resume": redact(profile["resumeText"]), "jd": ""}
    with ThreadPoolExecutor(max_workers=2) as pool:
        audit_f = pool.submit(with_audit, produce=lambda _e: output, context=context, lang=lang, repair=False, note=AUDIT_NOTE, check=lambda o: check_quotes(o, sources))
        links_f = pool.submit(verify_links, [o["url"] for o in output["openings"]])
        audited, links = audit_f.result(), links_f.result()
    audited.pop("output")
    before = {o["url"]: o["firstSeen"] for o in company["openings"]}
    return {
        "openings": [
            {
                "title": o["title"],
                "location": o["location"],
                "url": o["url"],
                "fit": o["fit"],
                "firstSeen": before.get(o["url"], now),
                "isNew": o["url"] not in before,
                "link": links.get(o["url"], "unverified"),
            }
            for o in output["openings"]
        ],
        "note": output["note"],
        "audit": audited,
    }
