"""The HTTP interface the browser uses, end to end, in sample mode (no API key, no network)."""
from __future__ import annotations

import io

import httpx
import pytest
from fastapi.testclient import TestClient

from gojob import config, files
from gojob.docx_io import docx_to_text, text_to_docx
from gojob.main import app
from tests.conftest import RESUME

JD = (
    "Senior Product Manager, Connected Devices at Sample Home Co in Dublin. You will own the roadmap for our smart home device line, "
    "work with firmware, cloud and app teams, and run experiments to inform prioritisation. Requirements: five years of product "
    "management experience with connected hardware, strong stakeholder management, and a track record of shipping with partners. "
    "We offer a hybrid working model and an international team."
)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def profile_body():
    return {
        "resumeText": RESUME, "roles": ["Product Manager"], "domains": ["IoT"], "regions": ["Ireland"], "workModes": ["hybrid"],
        "targetJDs": [{"id": str(i), "title": f"JD {i}", "text": JD} for i in range(3)],
    }


@pytest.fixture
def saved(client, profile_body):
    res = client.put("/api/profile", json=profile_body)
    assert res.status_code == 200
    return res.json()["profile"]


def analyze(client) -> dict:
    res = client.post("/api/run", json={"kind": "analyze", "lang": "en", "jdUrl": "", "jdText": JD})
    assert res.status_code == 200, res.text
    return res.json()["record"]


# ---------- state & profile ----------


def test_state_reports_version_models_and_selftest(client):
    body = client.get("/api/state").json()
    assert body["config"]["live"] is False
    assert body["config"]["appVersion"] == config.app_version()
    assert all(t["pass"] for t in body["config"]["tests"])
    assert {"profile", "health", "analyses", "tracker", "coach", "scout"} <= set(body)


def test_profile_save_strips_contact_details_and_stamps_dates(client, profile_body):
    profile_body["resumeText"] = RESUME + "\nReach me: jane@mail.com or +353 87 123 4567"
    p = client.put("/api/profile", json=profile_body).json()["profile"]
    assert "@" not in p["resumeText"] and "[email]" in p["resumeText"] and "[phone]" in p["resumeText"]
    assert p["savedAt"] and p["resumeUpdatedAt"] and p["fullTimeOnly"] is True


def test_profile_rejects_too_many_roles(client, profile_body):
    profile_body["roles"] = ["a", "b", "c"]
    res = client.put("/api/profile", json=profile_body)
    assert res.status_code == 400 and res.json() == {"error": "Invalid profile."}


def test_runs_need_a_saved_profile(client):
    res = client.post("/api/run", json={"kind": "health", "lang": "en"})
    assert res.status_code == 400 and "Save your profile" in res.json()["error"]


# ---------- assessment flow ----------


def test_health_check_needs_three_target_jds(client, profile_body):
    profile_body["targetJDs"] = profile_body["targetJDs"][:2]
    client.put("/api/profile", json=profile_body)
    res = client.post("/api/run", json={"kind": "health", "lang": "en"})
    assert res.status_code == 400 and "3 target JDs" in res.json()["error"]


def test_health_check_runs_and_is_stored_and_stamped(client, saved):
    health = client.post("/api/run", json={"kind": "health", "lang": "en"}).json()["health"]
    assert health["gate"]["kind"] == "panel" and health["check"]["demo"] is True
    assert health["check"]["meta"]["appVersion"] == config.app_version()
    assert client.get("/api/state").json()["health"]["profileSavedAt"] == saved["savedAt"]


def test_analyze_creates_a_record_with_history(client, saved):
    record = analyze(client)
    assert record["analysis"]["output"]["meta"]["company"] and len(record["history"]) == 1
    assert record["analysis"]["meta"]["promptHash"]
    assert client.get("/api/state").json()["analyses"][0]["id"] == record["id"]


def test_short_jd_is_refused(client, saved):
    res = client.post("/api/run", json={"kind": "analyze", "lang": "en", "jdText": "too short"})
    assert res.status_code == 400


def test_actions_store_results_with_run_counts(client, saved):
    rec = analyze(client)
    for kind in ("fineTune", "interview", "networking", "onePager"):
        out = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": kind}).json()["record"]
        assert out["actions"][kind]["runs"] == 1 and out["actions"][kind]["meta"]["promptHash"]
    again = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "fineTune"}).json()["record"]
    assert again["actions"]["fineTune"]["runs"] == 2


def test_cover_letter_asks_for_a_story_until_given_one(client, saved):
    rec = analyze(client)
    first = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "coverLetter", "input": ""}).json()["record"]
    assert first["actions"]["coverLetter"]["output"]["needsStory"] is True
    story = "I want to join because partner certification decides how fast device teams can ship, and I have lived that problem."
    second = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "coverLetter", "input": story}).json()["record"]
    assert story in second["actions"]["coverLetter"]["output"]["letter"]


def test_unknown_requests_and_ids_get_clear_errors(client, saved):
    assert client.post("/api/run", json={"kind": "nope", "lang": "en", "id": "x"}).status_code == 404
    rec = analyze(client)
    assert client.post("/api/run", json={"kind": "action", "id": rec["id"], "action": "hack"}).status_code == 400


def test_reanalyze_counts_a_retry_but_a_changed_resume_starts_over(client, saved):
    rec = analyze(client)
    retry = client.post("/api/run", json={"kind": "reanalyze", "lang": "en", "id": rec["id"]}).json()
    assert retry["changed"] is False and retry["record"]["analysis"]["runs"] == 2 and len(retry["record"]["history"]) == 1


def test_delete_analysis(client, saved):
    rec = analyze(client)
    assert client.delete("/api/run", params={"id": rec["id"]}).json() == {"ok": True}
    assert client.get("/api/state").json()["analyses"] == []


# ---------- tracked changes & files ----------


def test_accepted_changes_reach_the_text_and_the_download(client, saved):
    rec = analyze(client)
    ft = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "fineTune"}).json()["record"]["actions"]["fineTune"]["output"]["changes"]
    assert ft, "sample mode builds changes from the user's own resume lines"
    res = client.post("/api/resume-apply", json={"scope": "jd", "id": rec["id"], "accepted": ft[:1], "rejected": [c["find"] for c in ft[1:]]})
    assert res.status_code == 200
    body = res.json()
    assert ft[0]["replace"] in body["record"]["tailoredText"] and body["missedInText"] == [] and body["missedInFile"] == []
    assert body["record"]["actions"]["fineTune"]["output"]["changes"] == []
    docx = client.get("/api/export", params={"id": rec["id"], "kind": "resume", "format": "docx"})
    assert docx.status_code == 200 and "wordprocessingml" in docx.headers["content-type"]


def test_upload_docx_becomes_pending_then_master_on_save(client, profile_body):
    data = text_to_docx(RESUME)
    up = client.post("/api/upload", files={"file": ("cv.docx", data, "application/octet-stream")})
    assert up.status_code == 200 and up.json()["format"] == "docx" and "Sample Candidate" in up.json()["text"]
    client.put("/api/profile", json={**profile_body, "promoteUpload": True, "resumeFormat": "docx"})
    assert (config.FILES_DIR / "master.docx").exists()


class _Reply:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content, self.status_code = content, status_code


DOC_LINK = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/edit"


def test_google_doc_link_is_fetched_as_word_and_keeps_the_layout(client, resume, monkeypatch):
    asked = []

    def fake_get(url, **_kw):
        asked.append(url)
        return _Reply(text_to_docx(resume + "\nPersonal: alex@example.com"))

    monkeypatch.setattr("gojob.main.httpx.get", fake_get)
    got = client.post("/api/resume-link", json={"link": DOC_LINK})
    assert got.status_code == 200
    body = got.json()
    assert asked == ["https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/export?format=docx"]
    assert body["format"] == "docx" and "Matter integration" in body["text"] and "alex@example.com" not in body["text"]
    assert files.has_source("pending")  # the Word file is kept, so a revised resume is edited in place


def test_a_link_that_is_not_shared_gets_a_clear_message(client, monkeypatch):
    monkeypatch.setattr("gojob.main.httpx.get", lambda *_a, **_k: _Reply(b"<html><title>Sign in</title></html>", 200))
    res = client.post("/api/resume-link", json={"link": DOC_LINK})
    assert res.status_code == 422 and "Anyone with the link" in res.json()["error"]


def test_resume_link_refuses_other_sites_and_survives_network_errors(client, monkeypatch):
    assert client.post("/api/resume-link", json={"link": "https://example.com/cv.docx"}).status_code == 400
    assert client.post("/api/resume-link", json={"link": ""}).status_code == 400

    def down(*_a, **_k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("gojob.main.httpx.get", down)
    assert client.post("/api/resume-link", json={"link": DOC_LINK}).status_code == 502


def test_upload_rejects_big_empty_and_unreadable_files(client):
    assert client.post("/api/upload", files={"file": ("a.txt", b"x" * (8 * 1024 * 1024 + 1))}).status_code == 400
    assert client.post("/api/upload", files={"file": ("a.txt", b"too little")}).status_code == 422
    assert client.post("/api/upload", files={"file": ("a.exe", b"x" * 500)}).status_code == 422


def test_resume_download_without_any_saved_resume_still_builds_a_file(client, saved):
    res = client.get("/api/export", params={"kind": "resume"})
    assert res.status_code == 200 and "Sample Candidate" in docx_to_text(res.content)


def test_pdf_export_explains_when_libreoffice_is_missing(client, saved, monkeypatch):
    monkeypatch.setattr("gojob.main.docx_to_pdf", lambda _d: None)
    res = client.get("/api/export", params={"kind": "resume", "format": "pdf"})
    assert res.status_code == 501 and "LibreOffice" in res.json()["error"]


# ---------- tracker ----------


def test_tracker_add_edit_delete(client):
    row = client.post("/api/tracker", json={"company": "Acme", "position": "PM", "bogus": "ignored", "status": "HR"}).json()["row"]
    assert row["company"] == "Acme" and row["status"] == "HR" and "bogus" not in row
    rows = client.patch("/api/tracker", json={"id": row["id"], "notes": "called", "status": "not-a-status"}).json()["tracker"]
    assert rows[0]["notes"] == "called" and rows[0]["status"] == "HR"
    assert client.delete("/api/tracker", params={"id": row["id"]}).json()["tracker"] == []


# ---------- scout ----------


def test_scout_scan_wishlist_and_companies(client, saved):
    scan = client.post("/api/scout", json={"kind": "run", "lang": "en", "settings": {"regions": ["Ireland", "UK"], "languages": ["English"], "notes": ""}}).json()["scout"]
    assert scan["report"]["demo"] and len(scan["report"]["output"]["regions"]) == 2 and scan["report"]["meta"]["appVersion"]
    assert scan["history"] == []  # sample scans are not kept as market history

    assert scan["report"]["output"]["direction"][0]["proof"]["source"] == "resume"  # the search direction is read from the resume
    before = {j["url"] for j in scan["report"]["output"]["jobs"]}
    fresh = client.post("/api/scout", json={"kind": "refresh", "lang": "en", "part": "jobs"}).json()["scout"]["report"]
    assert fresh["output"]["jobs"] and not before & {j["url"] for j in fresh["output"]["jobs"]} and before <= set(fresh["shown"]["jobs"])
    assert fresh["output"]["companies"] == scan["report"]["output"]["companies"]  # the other part is untouched
    again_c = client.post("/api/scout", json={"kind": "refresh", "lang": "en", "part": "companies"}).json()["scout"]["report"]
    assert again_c["output"]["companies"][0]["company"] != scan["report"]["output"]["companies"][0]["company"]
    assert client.post("/api/scout", json={"kind": "refresh", "lang": "en", "part": "markets"}).status_code == 400

    job = scan["report"]["output"]["jobs"][0]
    saved_job = client.post("/api/scout", json={"kind": "saveJob", "job": job}).json()["scout"]["wishlist"]
    assert len(saved_job) == 1
    assert len(client.post("/api/scout", json={"kind": "saveJob", "job": job}).json()["scout"]["wishlist"]) == 1  # same link is not saved twice
    jid = saved_job[0]["id"]
    edited = client.patch("/api/scout", json={"list": "jobs", "id": jid, "decision": "Applied", "notes": "sent"}).json()["scout"]["wishlist"][0]
    assert edited["decision"] == "Applied" and edited["notes"] == "sent"

    comps = client.post("/api/scout", json={"kind": "saveCompany", "company": {"company": "Acme", "careersUrl": "https://acme.test/careers"}}).json()["scout"]["companies"]
    cid = comps[0]["id"]
    checked = client.post("/api/scout", json={"kind": "checkCompany", "lang": "en", "id": cid}).json()["scout"]["companies"][0]
    assert checked["openings"][0]["isNew"] is True
    again = client.post("/api/scout", json={"kind": "checkCompany", "lang": "en", "id": cid}).json()["scout"]["companies"][0]
    assert again["openings"][0]["isNew"] is False
    people = client.post("/api/scout", json={"kind": "people", "lang": "en", "id": cid}).json()["scout"]["companies"][0]["people"]
    assert people["output"]["targets"]

    assert client.delete("/api/scout", params={"list": "jobs", "id": jid}).json()["scout"]["wishlist"] == []
    assert client.delete("/api/scout", params={"list": "companies", "id": cid}).json()["scout"]["companies"] == []


def test_scout_needs_a_saved_profile(client):
    assert client.post("/api/scout", json={"kind": "run", "lang": "en"}).status_code == 400


# ---------- coach ----------


def test_coach_question_answer_report_and_log(client, saved):
    prompt = client.post("/api/coach", json={"kind": "next", "lang": "en", "category": "self_intro", "jdIds": []}).json()["prompt"]
    assert prompt["question"] and prompt["meta"]["promptHash"]
    short = client.post("/api/coach", json={"kind": "feedback", "lang": "en", "prompt": prompt, "mode": "30s", "answer": "too short", "seconds": 5, "jdIds": []})
    assert short.status_code == 400
    answer = "I started as a firmware engineer and moved into product because I wanted to decide what we build, not only how. " * 3
    out = client.post("/api/coach", json={"kind": "feedback", "lang": "en", "prompt": prompt, "mode": "30s", "answer": answer, "seconds": 40, "jdIds": []}).json()
    assert out["item"]["feedback"]["score"] and out["item"]["meta"]["appVersion"] and len(out["coach"]["items"]) == 1
    report = client.post("/api/coach", json={"kind": "report", "lang": "en"}).json()["coach"]["report"]
    assert report["total"] == 1
    log = client.get("/api/coach")
    assert log.status_code == 200 and "Interview practice" in log.text and "markdown" in log.headers["content-type"]
    assert client.delete("/api/coach", params={"id": out["item"]["id"]}).json()["coach"]["items"] == []


def test_jd_practice_needs_a_ticked_job(client, saved):
    res = client.post("/api/coach", json={"kind": "next", "lang": "en", "category": "jd", "jdIds": []})
    assert res.status_code == 400


def test_story_bank_from_pasted_text_and_file(client, saved):
    stories = "Story one: I led the certification push for our lighting range and cut the schedule by working with the lab early. " * 3
    bank = client.post("/api/coach/bank", json={"text": stories}).json()["coach"]["storyBank"]
    assert bank["name"] == "Pasted text" and bank["updatedAt"]
    up = client.post("/api/coach/bank", files={"file": ("stories.txt", stories.encode(), "text/plain")}).json()["coach"]["storyBank"]
    assert up["name"] == "stories.txt"
    assert client.post("/api/coach/bank", json={"text": "short"}).status_code == 422
    assert client.post("/api/coach/bank", json={"link": "http://localhost/x"}).status_code == 400


# ---------- saved data & feedback ----------


def test_feedback_and_data_management(client, saved):
    assert client.post("/api/feedback", json={"feature": "scout", "message": "  nice  "}).json() == {"ok": True}
    assert client.post("/api/feedback", json={"message": "   "}).status_code == 400
    analyze(client)
    usage = client.get("/api/data").json()
    assert usage["counts"]["analyses"] == 1 and usage["counts"]["feedback"] == 1 and usage["bytes"] > 0
    cleared = client.delete("/api/data", params={"what": "analyses"}).json()
    assert cleared["analyses"] == [] and cleared["counts"]["analyses"] == 0 and cleared["counts"]["feedback"] == 1


def test_data_file_is_stamped_with_its_version(client, saved):
    import json

    assert json.loads(config.DB_FILE.read_text())["schemaVersion"] == config.SCHEMA_VERSION


def test_errors_are_json_with_an_error_key(client):
    res = client.put("/api/profile", content=b"not json", headers={"content-type": "application/json"})
    assert res.status_code == 400 and "error" in res.json()
    assert client.get("/api/does-not-exist").status_code == 404


def test_upload_io_roundtrip_helper():
    # sanity check that the helper used above really produces a readable Word file
    assert "Sample Candidate" in docx_to_text(text_to_docx(RESUME)) and io.BytesIO(b"").read() == b""


def test_fine_tune_is_refused_once_tuning_has_hit_its_ceiling(client, saved):
    rec = analyze(client)
    first = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "fineTune"}).json()["record"]
    assert first["ceiling"] is None
    from gojob import pipeline as pl
    from gojob.store import update_db

    def stall(d: dict) -> None:
        r = d["analyses"][0]
        ft = r["actions"]["fineTune"]
        ft["evidenceBacked"] = 0  # nothing the resume supports is left
        ft["basedOn"] = pl.text_key(r["tailoredText"] or d["profile"]["resumeText"])

    update_db(stall)
    state = client.get("/api/state").json()
    assert state["analyses"][0]["ceiling"] == {"reason": "no_evidence_left"}
    blocked = client.post("/api/run", json={"kind": "action", "lang": "en", "id": rec["id"], "action": "fineTune"})
    assert blocked.status_code == 409 and "ceiling" in blocked.json()["error"]
