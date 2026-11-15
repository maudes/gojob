"""The HTTP interface. Same paths and JSON shapes the Next.js app used, so the browser code is unchanged."""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from . import coach as coach_mod
from . import config, files
from . import pipeline as pl
from . import prompts as P
from . import scout as scout_mod
from .claude import AgentError, has_credentials
from .docx_io import docx_to_pdf, docx_to_text, text_to_docx
from .extract import drive_download_url, file_to_text, html_to_text, is_safe_url
from .jobpage import read_job_page
from .meta import prompt_hash, stamp
from .schemas import ACTION_KINDS, COMPANY_STATUSES, TRACKER_STATUSES, WISH_DECISIONS, Profile
from .selftest import self_test
from .store import EMPTY_COACH, EMPTY_SCOUT, new_id, read_db, update_db
from .text import apply_to_text, redact

log = logging.getLogger("gojob")
app = FastAPI(title="Go Job", version=config.app_version(), docs_url="/api/docs", openapi_url="/api/openapi.json")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_UPLOAD = 8 * 1024 * 1024


# ---------- Errors: always {"error": "..."} like the first version ----------


def fail(error: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=error)


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _bad_request(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "Invalid request."}, status_code=400)


@app.exception_handler(AgentError)
async def _agent_error(_: Request, exc: AgentError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=502)


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"error": "Something went wrong on the server. Check the terminal for details."}, status_code=500)


def lang_of(body: dict) -> P.Lang:
    return "zh" if body.get("lang") == "zh" else "en"


def now_iso() -> str:
    return pl.now_iso()


def same_day(a: str | None, b: str) -> bool:
    return bool(a) and a[:10] == b[:10]


def need_profile(profile: dict) -> None:
    if not profile["savedAt"] or len(profile["resumeText"].strip()) < 200:
        raise fail("Save your profile with a resume first.")


# ---------- State ----------


@app.get("/api/state")
def state() -> dict:
    db = read_db()
    return {
        "profile": db["profile"],
        "health": db["health"],
        "analyses": db["analyses"],
        "tracker": db["tracker"],
        "coach": db["coach"],
        "scout": db["scout"],
        "config": {
            "live": has_credentials(),
            "mainModel": config.MAIN_MODEL,
            "reviewerModel": config.REVIEWER_MODEL,
            "tests": self_test(),
            "appVersion": config.app_version(),
            "promptHash": prompt_hash(),
        },
    }


# ---------- Profile, JD analysis ----------


def _point(g: dict) -> dict:
    return {"at": now_iso(), "average": g["average"], "scores": g["scores"]}


@app.post("/api/run")
def run(body: dict[str, Any] = Body(...)) -> dict:
    lang = lang_of(body)
    db = read_db()
    profile = db["profile"]
    # Eval rule 1: every assessment runs on the saved profile, nothing else.
    need_profile(profile)
    kind = body.get("kind")

    if kind == "health":
        if len(profile["targetJDs"]) < 3:
            raise fail("Add at least 3 target JDs first.")
        same = (db["health"] or {}).get("profileSavedAt") == profile["savedAt"]
        runs = db["healthRuns"] + 1 if same else 1
        health = pl.health_check(profile, lang, runs)

        def save_health(d: dict) -> None:
            d["health"] = health
            d["healthRuns"] = runs

        update_db(save_health)
        return {"health": health}

    if kind == "analyze":
        jd_text = str(body.get("jdText") or "").strip()
        if len(jd_text) < 300:
            raise fail("The job description is too short to analyse.")
        result = pl.analyze_jd(profile, profile["resumeText"], jd_text, lang, 1)
        record = {
            "id": new_id(),
            "jdUrl": body.get("jdUrl") or "",
            "jdText": jd_text,
            "createdAt": now_iso(),
            "tailoredText": None,
            "assessedText": profile["resumeText"],
            "history": [_point(result["gate"])],
            "networkTarget": "",
            **result,
            "actions": {},
        }
        update_db(lambda d: d["analyses"].insert(0, record))
        return {"record": record}

    rid = body.get("id")
    existing = next((a for a in db["analyses"] if a["id"] == rid), None)
    if not existing:
        raise fail("Analysis not found.", 404)

    def save(fn) -> dict:
        def apply(d: dict) -> dict | None:
            target = next((a for a in d["analyses"] if a["id"] == rid), None)
            if target is not None:
                fn(target)
            return target

        target = update_db(apply)
        if target is None:
            raise fail("Analysis not found.", 404)
        return target

    if kind == "reanalyze":
        resume = existing["tailoredText"] or profile["resumeText"]
        # A changed resume is a new assessment (never limited). The same resume is a retry (counted).
        changed = resume != existing["assessedText"]
        runs = 1 if changed else existing["analysis"]["runs"] + 1
        result = pl.analyze_jd(profile, resume, existing["jdText"], lang, runs, changed or len(existing["history"]) > 1)

        def apply_reanalysis(r: dict) -> None:
            r.update(result)
            r["assessedText"] = resume
            if changed:
                r["history"].append(_point(result["gate"]))
            else:
                r["history"][-1] = _point(result["gate"])

        return {"record": save(apply_reanalysis), "changed": changed}

    if kind == "setTarget":
        return {"record": save(lambda r: r.__setitem__("networkTarget", str(body.get("target") or "")[:200]))}

    action = body.get("action")
    if kind == "action" and action in ACTION_KINDS:
        output = pl.run_action(action, profile, existing, lang, str(body.get("input") or ""))
        return {"record": save(lambda r: r["actions"].__setitem__(action, output))}
    raise fail("Unknown request.")


@app.delete("/api/run")
def delete_run(id: str = Query("")) -> dict:
    update_db(lambda d: d.__setitem__("analyses", [a for a in d["analyses"] if a["id"] != id]))
    files.remove_source(f"jd-{id}")
    return {"ok": True}


@app.post("/api/jd-fetch")
def jd_fetch(body: dict[str, Any] = Body(...)) -> dict:
    """Try to read a job page from its link. When nothing works the UI asks the user to paste the text."""
    page = read_job_page(str(body.get("url") or ""))
    return {"ok": True, **page} if page else {"ok": False}


# ---------- Profile ----------


def _scan(url: str) -> str:
    if not is_safe_url(url):
        return ""
    try:
        res = httpx.get(url, headers={"user-agent": "Mozilla/5.0 (compatible; profile-reader)"}, timeout=12, follow_redirects=True)
        return html_to_text(res.text)[:12000] if res.status_code < 400 else ""
    except httpx.HTTPError:
        return ""


@app.put("/api/profile")
def put_profile(body: dict[str, Any] = Body(...)) -> dict:
    try:
        parsed = Profile.model_validate({**Profile().dump(), **body, "fullTimeOnly": True})
    except ValidationError as err:
        raise fail("Invalid profile.") from err
    previous = read_db()["profile"]
    p = parsed.dump()
    promote = bool(body.get("promoteUpload"))

    # A newly uploaded file becomes the master copy only when the profile is saved.
    if promote and files.has_source("pending"):
        files.copy_source("pending", "master")
    elif not files.has_source("master") or (not promote and p["resumeText"] != previous["resumeText"]):
        # Resume was pasted or edited as text: the text itself is the source for downloads.
        files.save_source("master", "other", p["resumeText"])
        p["resumeFormat"] = "other"

    if p["websiteUrl"] and (p["websiteUrl"] != previous["websiteUrl"] or not previous["websiteText"]):
        website_text = _scan(p["websiteUrl"])
    else:
        website_text = previous["websiteText"] if p["websiteUrl"] else ""

    resume_text = redact(p["resumeText"])
    profile = {
        **p,
        # Contact details are stripped on the way in, so they are never shown or sent to a model.
        "resumeText": resume_text,
        "linkedinText": redact(p["linkedinText"]),
        "websiteText": redact(website_text),
        "resumeUpdatedAt": now_iso() if promote or resume_text != previous["resumeText"] or not previous["resumeUpdatedAt"] else previous["resumeUpdatedAt"],
        "savedAt": now_iso(),
    }
    update_db(lambda d: d.__setitem__("profile", profile))
    return {"profile": profile, "websiteScanned": bool(website_text)}


# ---------- Resume files ----------


@app.post("/api/upload")
async def upload(file: UploadFile | None = File(None), id: str | None = Query(None)) -> dict:
    """Resume upload. Without `id` it is the profile resume (pending until saved); with `id` it is the revised resume for one JD."""
    if file is None:
        raise fail("No file received.")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise fail("File is larger than 8 MB.")
    name = file.filename or ""
    try:
        is_docx = name.lower().endswith(".docx")
        text = docx_to_text(data) if is_docx else file_to_text(name, data)
    except Exception as err:  # noqa: BLE001
        raise fail(str(err) or "Could not read the file.", 422) from err
    if len(text) < 200:
        raise fail("Could not read enough text from this file (it may be a scanned image). Upload a .docx or paste the text.", 422)
    scope = f"jd-{id}" if id else "pending"
    files.save_source(scope, "docx" if is_docx else "other", data if is_docx else text)
    clean = redact(text)
    if id:

        def set_tailored(d: dict) -> dict | None:
            r = next((a for a in d["analyses"] if a["id"] == id), None)
            if r:
                r["tailoredText"] = clean
            return r

        record = update_db(set_tailored)
        if not record:
            raise fail("Analysis not found.", 404)
        return {"record": record}
    return {"text": clean, "fileName": name, "format": "docx" if is_docx else "other"}


@app.post("/api/resume-apply")
def resume_apply(body: dict[str, Any] = Body(...)) -> dict:
    """Write the accepted tracked changes into the resume text and into the stored file."""
    accepted = [
        {"find": c["find"], "replace": c["replace"]}
        for c in (body.get("accepted") or [])
        if isinstance(c, dict) and isinstance(c.get("find"), str) and isinstance(c.get("replace"), str) and c["find"]
    ]
    handled = {c["find"] for c in accepted} | set(body.get("rejected") or [])
    scope = body.get("scope")
    jd_scope = f"jd-{body.get('id')}"
    if scope == "jd" and accepted and not files.has_source(jd_scope):
        files.copy_source("master", jd_scope)
    missed_in_file = files.apply_to_source(jd_scope if scope == "jd" else "master", accepted) if accepted else []

    def apply(db: dict) -> dict | None:
        if scope == "profile":
            text, missed = apply_to_text(db["profile"]["resumeText"], accepted)
            db["profile"]["resumeText"] = text
            if accepted:
                db["profile"]["savedAt"] = db["profile"]["resumeUpdatedAt"] = now_iso()
            if db["health"]:
                changes = db["health"]["check"]["output"]["changes"]
                db["health"]["check"]["output"]["changes"] = [c for c in changes if c["find"] not in handled]
            return {"profile": db["profile"], "health": db["health"], "missedInText": missed}
        record = next((a for a in db["analyses"] if a["id"] == body.get("id")), None)
        if not record:
            return None
        text, missed = apply_to_text(record["tailoredText"] or db["profile"]["resumeText"], accepted)
        if accepted:
            record["tailoredText"] = text
        fine_tune = record["actions"].get("fineTune")
        if fine_tune:
            fine_tune["output"]["changes"] = [c for c in fine_tune["output"]["changes"] if c["find"] not in handled]
        return {"record": record, "missedInText": missed}

    result = update_db(apply)
    if result is None:
        raise fail("Analysis not found.", 404)
    return {**result, "missedInFile": missed_in_file}


@app.get("/api/export")
def export(id: str | None = None, kind: str | None = None, format: str | None = None) -> Response:
    """Download the resume or cover letter as .docx or PDF."""
    db = read_db()
    record = next((a for a in db["analyses"] if a["id"] == id), None)
    company = re.sub(r"[^\w -]", "", ((record or {}).get("analysis", {}).get("output", {}).get("meta", {}).get("company") or ""), flags=re.A).strip()
    if kind == "letter":
        letter = ((record or {}).get("actions", {}).get("coverLetter") or {}).get("output", {}).get("letter")
        if not letter:
            raise fail("No cover letter yet.", 404)
        docx = text_to_docx(letter)
        name = f"Cover letter{f' - {company}' if company else ''}"
    else:
        jd_scope = f"jd-{record['id']}" if record else ""
        use_jd = bool(record) and files.has_source(jd_scope)
        docx = files.export_docx(jd_scope if use_jd else "master", (record or {}).get("tailoredText") or db["profile"]["resumeText"])
        name = f"Resume{f' - {company}' if company else ''}"
    if format == "pdf":
        pdf = docx_to_pdf(docx)
        if not pdf:
            raise fail(
                "PDF export needs LibreOffice on this computer (free: brew install --cask libreoffice). Until then, download the .docx and export it as PDF from Google Docs or Word.",
                501,
            )
        return Response(pdf, media_type="application/pdf", headers={"content-disposition": f'attachment; filename="{name}.pdf"'})
    return Response(docx, media_type=DOCX_MIME, headers={"content-disposition": f'attachment; filename="{name}.docx"'})


# ---------- Tracker ----------

TRACKER_FIELDS = ("company", "position", "location", "jobLink", "oneLine", "matchingScore", "applyDate", "networkTarget", "notes")


def _clean_row(data: dict) -> dict:
    out = {f: data[f] for f in TRACKER_FIELDS if isinstance(data.get(f), str)}
    if data.get("status") in TRACKER_STATUSES:
        out["status"] = data["status"]
    return out


@app.post("/api/tracker")
def tracker_add(body: dict[str, Any] = Body(...)) -> dict:
    row = {
        "id": new_id(), "company": "", "position": "", "location": "", "jobLink": "", "oneLine": "", "matchingScore": "",
        "applyDate": "", "networkTarget": "", "status": "Apply", "notes": "", **_clean_row(body),
    }

    def add(d: dict) -> list:
        d["tracker"].insert(0, row)
        return d["tracker"]

    return {"tracker": update_db(add), "row": row}


@app.patch("/api/tracker")
def tracker_edit(body: dict[str, Any] = Body(...)) -> dict:
    def edit(d: dict) -> list:
        row = next((r for r in d["tracker"] if r["id"] == body.get("id")), None)
        if row:
            row.update(_clean_row(body))
        return d["tracker"]

    return {"tracker": update_db(edit)}


@app.delete("/api/tracker")
def tracker_delete(id: str | None = None) -> dict:
    def delete(d: dict) -> list:
        d["tracker"] = [r for r in d["tracker"] if r["id"] != id]
        return d["tracker"]

    return {"tracker": update_db(delete)}


# ---------- Feedback ----------


@app.post("/api/feedback")
def feedback(body: dict[str, Any] = Body(...)) -> dict:
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise fail("Empty feedback.")
    entry = {"at": now_iso(), "feature": str(body.get("feature") or ""), "message": message.strip()[:4000]}
    update_db(lambda d: d["feedback"].append(entry))
    return {"ok": True}


# ---------- Scout ----------


def _s(v: Any, limit: int = 600) -> str:
    return v[:limit] if isinstance(v, str) else ""


def _strings(v: Any, limit: int) -> list[str]:
    return [x.strip()[:60] for x in v if isinstance(x, str) and x.strip()][:limit] if isinstance(v, list) else []


JOB_FIELDS = ("company", "title", "location", "url", "tier", "visa", "posted", "fit", "notes")
COMPANY_FIELDS = ("company", "careersUrl", "why", "roleType", "contact", "notes")


@app.post("/api/scout")
def scout(body: dict[str, Any] = Body(...)) -> dict:
    lang = lang_of(body)
    db = read_db()
    profile = db["profile"]
    kind = body.get("kind")

    if kind == "run":
        # Eval rule 1: the scan runs on the saved profile, nothing else.
        need_profile(profile)
        base = scout_mod.default_settings(profile)
        given = body.get("settings") or {}
        regions, languages = _strings(given.get("regions"), 8), _strings(given.get("languages"), 4)
        settings = {"regions": regions or base["regions"], "languages": languages or base["languages"], "notes": _s(given.get("notes"), 500)}
        report_before = db["scout"]["report"]
        runs = (report_before or {}).get("runs", 0) + 1 if same_day((report_before or {}).get("at"), now_iso()) else 1
        report = scout_mod.run_scout(profile, settings, db["scout"]["history"], lang, runs)

        def save_run(d: dict) -> dict:
            d["scout"]["settings"] = settings
            d["scout"]["report"] = report
            if not report["demo"]:
                entry = {"at": report["at"], "headline": report["output"]["headline"], "regions": [{"region": r["region"], "heat": r["heat"]} for r in report["output"]["regions"]]}
                d["scout"]["history"] = [entry, *[h for h in d["scout"]["history"] if not same_day(h["at"], report["at"])]][:30]
            return d["scout"]

        return {"scout": update_db(save_run)}

    if kind == "saveJob":
        given = body.get("job") or {}
        job = {"id": new_id(), "company": "", "title": "", "location": "", "url": "", "tier": "", "visa": "", "posted": "", "fit": "", "decision": "Deciding", "notes": "", "savedAt": now_iso(), "lastChecked": None, "open": None}
        for f in JOB_FIELDS:
            job[f] = _s(given.get(f))

        def save_job(d: dict) -> dict:
            if not job["url"] or not any(j["url"] == job["url"] for j in d["scout"]["wishlist"]):
                d["scout"]["wishlist"].insert(0, job)
            return d["scout"]

        return {"scout": update_db(save_job)}

    if kind == "saveCompany":
        given = body.get("company") or {}
        row = {"id": new_id(), "company": "", "careersUrl": "", "why": "", "roleType": "", "contact": "", "status": "Watching", "notes": "", "addedAt": now_iso(), "lastChecked": None, "openings": [], "openingsNote": ""}
        for f in COMPANY_FIELDS:
            row[f] = _s(given.get(f))

        def save_company(d: dict) -> dict:
            name = row["company"].strip().lower()
            if not name or not any(c["company"].strip().lower() == name for c in d["scout"]["companies"]):
                d["scout"]["companies"].insert(0, row)
            return d["scout"]

        return {"scout": update_db(save_company)}

    if kind == "checkJob":
        job = next((j for j in db["scout"]["wishlist"] if j["id"] == body.get("id")), None)
        if not job:
            raise fail("That job is no longer in the wish list.", 404)
        page = read_job_page(job["url"]) if job["url"] else None

        def mark(d: dict) -> dict:
            row = next((j for j in d["scout"]["wishlist"] if j["id"] == body.get("id")), None)
            if row:
                row.update({"lastChecked": now_iso(), "open": "open" if page else "unconfirmed"})
            return d["scout"]

        return {"scout": update_db(mark)}

    if kind in ("checkCompany", "people"):
        need_profile(profile)
        company = next((c for c in db["scout"]["companies"] if c["id"] == body.get("id")), None)
        if not company:
            raise fail("That company is no longer in the list.", 404)
        if not company["company"].strip():
            raise fail("Give the company a name first.")
        if kind == "checkCompany":
            result = scout_mod.check_company(profile, company, lang)

            def save_openings(d: dict) -> dict:
                row = next((c for c in d["scout"]["companies"] if c["id"] == body.get("id")), None)
                if row:
                    row.update({"openings": result["openings"], "openingsNote": result["note"], "openingsAudit": result["audit"], "lastChecked": now_iso()})
                return d["scout"]

            return {"scout": update_db(save_openings)}
        where = {"company": company["company"], "title": company["roleType"] or " / ".join(profile["roles"]), "location": ", ".join(profile["regions"])}
        people = pl.find_people(P.profile_block(profile), where, lang, ((company.get("people") or {}).get("runs") or 0) + 1)

        def save_people(d: dict) -> dict:
            row = next((c for c in d["scout"]["companies"] if c["id"] == body.get("id")), None)
            if row:
                row["people"] = people
            return d["scout"]

        return {"scout": update_db(save_people)}
    raise fail("Unknown request.")


@app.patch("/api/scout")
def scout_edit(body: dict[str, Any] = Body(...)) -> dict:
    """Inline edits to a wish list job or a target company."""

    def edit(d: dict) -> dict:
        if body.get("list") == "jobs":
            row = next((j for j in d["scout"]["wishlist"] if j["id"] == body.get("id")), None)
            if row:
                for f in JOB_FIELDS:
                    if isinstance(body.get(f), str):
                        row[f] = _s(body[f])
                if body.get("decision") in WISH_DECISIONS:
                    row["decision"] = body["decision"]
        else:
            row = next((c for c in d["scout"]["companies"] if c["id"] == body.get("id")), None)
            if row:
                for f in COMPANY_FIELDS:
                    if isinstance(body.get(f), str):
                        row[f] = _s(body[f])
                if body.get("status") in COMPANY_STATUSES:
                    row["status"] = body["status"]
        return d["scout"]

    return {"scout": update_db(edit)}


@app.delete("/api/scout")
def scout_delete(id: str | None = None, list: str | None = None) -> dict:  # noqa: A002 - query name is part of the API
    def delete(d: dict) -> dict:
        if list == "jobs":
            d["scout"]["wishlist"] = [j for j in d["scout"]["wishlist"] if j["id"] != id]
        else:
            d["scout"]["companies"] = [c for c in d["scout"]["companies"] if c["id"] != id]
        return d["scout"]

    return {"scout": update_db(delete)}


# ---------- Interview coach ----------


@app.post("/api/coach")
def coach(body: dict[str, Any] = Body(...)) -> dict:
    lang = lang_of(body)
    db = read_db()
    if not db["profile"]["savedAt"]:
        raise fail("Save your profile with a resume first.")
    jd_ids = body.get("jdIds") or []
    records = [a for a in db["analyses"] if a["id"] in jd_ids] if "jdIds" in body else []
    kind = body.get("kind")

    if kind == "next":
        if body.get("category") == "jd" and not records:
            raise fail("Tick at least one job to practise JD questions.")
        prompt = coach_mod.next_question(profile=db["profile"], coach=db["coach"], records=records, category=body.get("category") or "auto", lang=lang)
        return {"prompt": prompt}

    if kind == "feedback":
        answer = str(body.get("answer") or "").strip()
        if len(answer.split()) < 8:
            raise fail("The answer is too short to coach. Say a little more.")
        prompt = body["prompt"]
        seconds = body.get("seconds") or 0
        seconds = float(seconds) if isinstance(seconds, (int, float)) else 0
        fb, audit = coach_mod.give_feedback(
            profile=db["profile"], coach=db["coach"], prompt=prompt, mode=body["mode"], answer=answer, seconds=seconds,
            jd_text=records[0]["jdText"] if prompt.get("category") == "jd" and records else "", lang=lang,
        )
        item = {**prompt, "id": new_id(), "at": now_iso(), "mode": body["mode"], "answer": answer, "seconds": seconds, "feedback": fb, "feedbackAudit": audit, "meta": stamp()}

        def add(d: dict) -> dict:
            d["coach"]["items"].insert(0, item)
            return d["coach"]

        return {"coach": update_db(add), "item": item}

    if kind == "report":
        report = coach_mod.weekly_report(db["coach"], lang)

        def save(d: dict) -> dict:
            d["coach"]["report"] = report
            return d["coach"]

        return {"coach": update_db(save)}
    raise fail("Unknown request.")


@app.get("/api/coach")
def coach_log() -> Response:
    """Download the practice log as Markdown."""
    return Response(
        coach_mod.session_log(read_db()["coach"]["items"]),
        media_type="text/markdown; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="interview-practice-log.md"'},
    )


@app.delete("/api/coach")
def coach_delete(id: str | None = None) -> dict:
    def delete(d: dict) -> dict:
        d["coach"]["items"] = [i for i in d["coach"]["items"] if i["id"] != id]
        return d["coach"]

    return {"coach": update_db(delete)}


MAX_BANK = 120000


def _bank_text(name: str, data: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".docx"):
        return docx_to_text(data)
    if lower.endswith((".csv", ".tsv")):
        return data.decode("utf8", errors="replace").strip()
    return file_to_text(name, data)


def _store_bank(text: str, name: str) -> dict:
    if len(text.strip()) < 80:
        raise fail("Not enough text was found. Paste your stories instead.", 422)
    if len(text) > MAX_BANK:
        raise fail("The story bank is longer than 120,000 characters. Keep the stories you practise with and remove the rest.", 422)

    def save(d: dict) -> dict:
        d["coach"]["storyBank"] = {"text": redact(text), "name": name, "updatedAt": now_iso()}
        return d["coach"]

    return {"coach": update_db(save)}


@app.post("/api/coach/bank")
async def coach_bank(request: Request) -> dict:
    """Story bank: an uploaded file, a Google Docs / Sheets / Drive link, or pasted text."""
    try:
        if "multipart/form-data" in request.headers.get("content-type", ""):
            upload_file = (await request.form()).get("file")
            if upload_file is None or isinstance(upload_file, str):
                raise fail("No file received.")
            data = await upload_file.read()
            if len(data) > MAX_UPLOAD:
                raise fail("File is larger than 8 MB.")
            return _store_bank(_bank_text(upload_file.filename or "", data), upload_file.filename or "")
        body = await request.json()
        if isinstance(body.get("text"), str):
            return _store_bank(body["text"], "Pasted text")
        target = drive_download_url(str(body.get("link") or ""))
        if not target:
            raise fail("That link is not valid.")
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            res = await client.get(target)
        ctype = res.headers.get("content-type", "")
        # A private Google file answers with its sign-in page instead of the content.
        if res.status_code >= 400 or "text/html" in ctype:
            raise fail('This link could not be read. In Google Drive set sharing to "Anyone with the link", or download the file and upload it here.', 422)
        if "csv" in ctype:
            name = "Google Sheet.csv"
        elif "pdf" in ctype:
            name = "Drive file.pdf"
        elif "wordprocessingml" in ctype:
            name = "Drive file.docx"
        else:
            name = "Google Doc.txt"
        return _store_bank(_bank_text(name, res.content), re.sub(r"\.\w+$", "", name))
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        raise fail(str(err) or "Could not read the story bank.", 422) from err


# ---------- Saved data ----------


def _usage() -> dict:
    db = read_db()
    size = config.DB_FILE.stat().st_size if config.DB_FILE.exists() else 0
    if config.FILES_DIR.exists():
        size += sum(f.stat().st_size for f in config.FILES_DIR.iterdir() if f.is_file())
    return {
        "bytes": size,
        "counts": {
            "analyses": len(db["analyses"]),
            "tracker": len(db["tracker"]),
            "coach": len(db["coach"]["items"]),
            "storyBank": 1 if db["coach"]["storyBank"]["text"] else 0,
            "feedback": len(db["feedback"]),
            "wishlist": len(db["scout"]["wishlist"]),
            "companies": len(db["scout"]["companies"]),
            "scans": len(db["scout"]["history"]) + (1 if db["scout"]["report"] else 0),
        },
    }


@app.get("/api/data")
def data_usage() -> dict:
    return _usage()


@app.delete("/api/data")
def data_clear(what: str | None = None) -> dict:
    """Manual clean-up of one kind of saved data. Nothing is removed automatically."""

    def clear(db: dict) -> list[str]:
        removed = [a["id"] for a in db["analyses"]] if what == "analyses" else []
        if what == "analyses":
            db["analyses"] = []
        elif what == "tracker":
            db["tracker"] = []
        elif what == "coach":
            db["coach"] = {**db["coach"], "items": [], "report": None}
        elif what == "storyBank":
            db["coach"]["storyBank"] = dict(EMPTY_COACH["storyBank"])
        elif what == "feedback":
            db["feedback"] = []
        elif what == "wishlist":
            db["scout"]["wishlist"] = []
        elif what == "companies":
            db["scout"]["companies"] = []
        elif what == "scans":
            db["scout"] = {**db["scout"], "report": None, "history": list(EMPTY_SCOUT["history"])}
        return removed

    for rid in update_db(clear):
        files.remove_source(f"jd-{rid}")
    db = read_db()
    return {**_usage(), "analyses": db["analyses"], "tracker": db["tracker"], "coach": db["coach"], "scout": db["scout"]}

