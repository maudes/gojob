"""Pure logic: redaction, quote proof, gates, applying changes, docx editing, stamps, data upgrades."""
from __future__ import annotations

import json

import pytest

from gojob import config, store
from gojob.docx_io import apply_changes_to_docx, docx_to_text, text_to_docx
from gojob.extract import drive_download_url, google_resume_url, html_to_text, is_safe_url
from gojob.version_stamp import prompt_hash, skill_hashes, stamp
from gojob.audit import check_quotes, is_approved
from gojob.scoring import gate, round_half_up
from gojob.scout import keep_linked
from gojob.selftest import self_test
from gojob.text_tools import apply_to_text, editable_lines, is_layout_line, is_verbatim, keep_editable, redact


def test_every_runtime_selftest_passes():
    failed = [t["name"] for t in self_test() if not t["pass"]]
    assert failed == []


# ---------- redact / verbatim ----------


def test_redact_removes_contacts_but_keeps_year_ranges():
    out = redact("Jane · jane@mail.com · +353 87 123 4567 · 2019 - 2023")
    assert "[email]" in out and "[phone]" in out and "2019 - 2023" in out


@pytest.mark.parametrize(
    "quote,source,expected",
    [
        ("•  Led   Matter integration", "- Led Matter integration across teams", True),
        ("Led Matter integrations", "Led Matter integration across teams", False),
        ("", "anything", True),  # nothing quoted means nothing to prove
        ("“smart” quotes", '"smart" quotes here', True),
    ],
)
def test_is_verbatim(quote, source, expected):
    assert is_verbatim(quote, source) is expected


def test_check_quotes_walks_evidence_changes_and_bullet_orders():
    output = {
        "requirements": [{"requirement": {"source": "jd", "quote": "five years"}, "evidence": {"source": "resume", "quote": "invented"}}],
        "changes": [{"find": "Owned roadmap", "replace": "Owned the roadmap"}],
        "bulletOrder": [{"orderedBullets": ["Owned roadmap", "made up"], "drop": []}],
    }
    result = check_quotes(output, {"resume": "Owned roadmap", "jd": "five years of PM"})
    assert result["total"] == 5
    assert sorted(f["quote"] for f in result["failed"]) == ["invented", "made up"]


# ---------- gates ----------


def test_gate_needs_average_and_minimum():
    assert gate([80, 80, 80], 80, 70)["green"]
    assert not gate([95, 95, 69], 80, 70)["green"]
    assert not gate([79, 80, 80], 80, 70)["green"]


def test_gate_rounds_like_the_first_version():
    assert gate([71, 72, 72], 80, 70)["average"] == 71.7
    assert round_half_up(2.5) == 3 and round_half_up(0.5) == 1  # Python's round() would give 2 and 0


def _audit(score, ok=True):
    checks = dict.fromkeys(("resumeQuotesVerbatim", "jdQuotesVerbatim", "noInventedFacts", "labelsCorrect", "alignedWithProfile"), True)
    checks["noInventedFacts"] = ok
    return {"score": score, "checks": checks, "issues": []}


CLEAN = {"total": 1, "verified": 1, "failed": []}


def test_approval_rules():
    assert is_approved([_audit(96)] * 5, CLEAN)
    assert not is_approved([_audit(96)] * 4 + [_audit(95)], CLEAN)  # must be strictly above 95
    assert not is_approved([_audit(99)] * 4, CLEAN)  # all five auditors must report
    assert not is_approved([_audit(99)] * 4 + [_audit(99, ok=False)], CLEAN)  # every box ticked
    assert not is_approved([_audit(99)] * 5, {"total": 1, "verified": 0, "failed": [{"source": "resume", "quote": "x"}]})


# ---------- applying changes ----------


def test_apply_to_text_reports_what_it_could_not_place():
    text, missed = apply_to_text("A\nOwned roadmap\nB", [{"find": "Owned roadmap", "replace": "Owned the roadmap"}, {"find": "gone", "replace": "x"}])
    assert text == "A\nOwned the roadmap\nB" and missed == ["gone"]


def test_docx_is_edited_in_place_and_keeps_other_lines():
    docx = text_to_docx("Jane Doe\nEXPERIENCE\n- Owned the connectivity roadmap\n- Built middleware")
    edited, missed = apply_changes_to_docx(docx, [{"find": "Owned the connectivity roadmap", "replace": "Owned the connectivity roadmap for [X] products"}])
    text = docx_to_text(edited)
    assert not missed and "for [X] products" in text and "Built middleware" in text


def test_docx_edit_handles_xml_special_characters_and_misses():
    docx = text_to_docx("Jane Doe\nEXPERIENCE\n- Grew revenue by 10% in R&D")
    edited, missed = apply_changes_to_docx(docx, [{"find": "R&D", "replace": "R&D <core>"}, {"find": "does not exist", "replace": "x"}])
    assert "R&D <core>" in docx_to_text(edited) and missed == ["does not exist"]


# ---------- links and pages ----------


def test_keep_linked_drops_unusable_urls():
    kept, dropped = keep_linked([{"url": "https://jobs.example.com/1"}, {"url": ""}, {"url": "see careers page"}, {"url": "http://localhost/x"}])
    assert len(kept) == 1 and dropped == 3


@pytest.mark.parametrize("url", ["http://127.0.0.1/a", "http://192.168.1.4/", "http://[::1]/", "http://printer.local/", "ftp://x.com/a", "javascript:alert(1)"])
def test_unsafe_urls_are_refused(url):
    assert is_safe_url(url) is None


def test_drive_links_become_download_links():
    assert drive_download_url("https://docs.google.com/document/d/" + "a" * 25 + "/edit").endswith("/export?format=txt")
    assert "format=csv&gid=7" in drive_download_url("https://docs.google.com/spreadsheets/d/" + "b" * 25 + "/edit#gid=7")
    assert drive_download_url("http://localhost/x") is None


def test_html_prefers_json_ld_job_posting():
    page = '<script type="application/ld+json">{"@type":"JobPosting","title":"PM","description":"<p>Own the roadmap</p>","hiringOrganization":{"name":"Acme"}}</script><p>noise</p>'
    assert html_to_text(page).startswith("PM\nAcme") and "Own the roadmap" in html_to_text(page)


# ---------- stamp, prompt hash, data versions ----------


def test_stamp_names_release_prompts_and_models():
    s = stamp()
    assert s["appVersion"] == config.app_version()
    assert len(s["promptHash"]) == 10 and s["promptHash"] == prompt_hash()
    assert set(s["models"]) == {"main", "reviewer"}


def test_prompt_hash_changes_when_a_skill_file_changes(tmp_path, monkeypatch):
    monkeypatch.setattr("gojob.version_stamp.SKILLS_DIR", tmp_path)
    (tmp_path / "demo.md").write_text("v1")
    before = prompt_hash()
    (tmp_path / "demo.md").write_text("version 2")  # no restart and no cache to clear
    assert prompt_hash() != before


def test_old_database_is_upgraded_and_backed_up(isolated):
    old = {"profile": {"resumeText": "x"}, "tracker": [{"id": "a"}]}
    config.DB_FILE.write_text(json.dumps(old))
    db = store.read_db()
    assert db["schemaVersion"] == config.SCHEMA_VERSION and db["tracker"] == [{"id": "a"}]
    assert db["profile"]["roles"] == []  # missing fields are filled in
    assert (isolated / "db.v0.bak.json").exists()
    store.update_db(lambda d: None)
    assert json.loads(config.DB_FILE.read_text())["schemaVersion"] == config.SCHEMA_VERSION


def test_database_from_a_newer_app_is_refused(isolated):
    config.DB_FILE.write_text(json.dumps({"schemaVersion": config.SCHEMA_VERSION + 1}))
    with pytest.raises(RuntimeError, match="newer Go Job"):
        store.read_db()


def test_damaged_database_is_kept_aside_not_overwritten(isolated):
    config.DB_FILE.write_text("{not json")
    assert store.read_db()["tracker"] == []
    assert list(isolated.glob("db.corrupt-*.json"))


def test_wire_names_match_what_the_browser_and_prompts_use():
    """to_camel gets acronyms wrong ("targetJds"); every model field must match the names in lib/schemas.ts."""
    import inspect
    import re

    from gojob import schemas as S

    ts = (config.ROOT / "lib" / "schemas.ts").read_text("utf8")
    known = set(re.findall(r"\b([A-Za-z0-9_]+)\??\s*:", ts))
    bad = [
        f"{name}.{field}"
        for name, cls in inspect.getmembers(S, inspect.isclass)
        if issubclass(cls, S.Model) and cls is not S.Model
        for field, info in cls.model_fields.items()
        if (info.alias or field) not in known
    ]
    assert bad == []


# ---------- layout lock: wording changes never land on structure lines ----------

RESUME = """Alex Example
Product Manager · IoT Ecosystems · Partner Integrations
Cork → Berlin · [email] · LinkedIn · Portfolio
SUMMARY
Platform PM with 6+ years aligning connected hardware platforms with partner ecosystems and certification programs.
EXPERIENCE
Northlight Devices Cork, Ireland
Product Manager, Platform Delivery Nov 2025 – Present
Own client-facing delivery for retail programs and the platform roadmap, establishing a stakeholder layer with five milestones.
Scoped PKI engineering effort for OEM partners, including an industry certification, 2022–2023, and a cross-team defect review process.
2024 Q2 Excellence Award · 2022 Annual Excellence Award — Northlight Devices Business Unit
EDUCATION
Example University Cork, Ireland B.A. in Journalism, Minor in Political Science
SKILLS
Technical: Python · SQL · Git · REST APIs · LLM APIs · Matter · Thread
"""


def test_structure_lines_are_locked_and_wording_lines_are_not():
    lines = [ln for ln in RESUME.split("\n") if ln.strip()]
    locked = {ln for i, ln in enumerate(lines) if is_layout_line(ln, i == 0, i == 1)}
    assert {"Alex Example", "SUMMARY", "EXPERIENCE", "EDUCATION", "Northlight Devices Cork, Ireland"} <= locked
    assert any("Nov 2025 – Present" in ln for ln in locked) and any("Example University" in ln for ln in locked) and any("Excellence Award" in ln for ln in locked)
    assert any("[email]" in ln for ln in locked)
    free = set(lines) - locked
    assert any(ln.startswith("Platform PM with") for ln in free) and any(ln.startswith("Own client-facing") for ln in free)
    assert any(ln.startswith("Technical:") for ln in free) and any(ln.startswith("Product Manager · IoT") for ln in free)  # skills and the headline may be reworded


def test_a_date_range_inside_a_long_bullet_does_not_lock_the_bullet():
    bullet = next(ln for ln in RESUME.split("\n") if "industry certification" in ln)
    assert not is_layout_line(bullet)


def test_keep_editable_drops_only_changes_on_structure_lines():
    changes = [
        {"find": "Product Manager, Platform Delivery Nov 2025", "replace": "x"},
        {"find": "Northlight Devices", "replace": "x"},
        {"find": "Own client-facing delivery", "replace": "Led client-facing delivery"},
        {"find": "Not in the resume at all", "replace": "y"},  # unplaceable text is left for the quote check to flag
    ]
    kept, dropped = keep_editable(changes, RESUME)
    assert dropped == 2 and [c["replace"] for c in kept] == ["Led client-facing delivery", "y"]


def test_sample_changes_never_pick_a_structure_line():
    from gojob.sample_data import health

    for change in health(RESUME)["changes"]:
        line = next(ln for ln in RESUME.split("\n") if change["find"] in ln)
        assert line in editable_lines(RESUME)
    sample_header_first = "Sample Lighting Co · Product Manager · 2021 - 2024\n" + RESUME
    assert all(not c["find"].startswith("Sample Lighting") for c in health(sample_header_first)["changes"])


def test_google_resume_link_becomes_a_word_download():
    doc = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/edit?tab=t.0"
    assert google_resume_url(doc) == "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/export?format=docx"
    assert google_resume_url("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/view").startswith("https://drive.google.com/uc?export=download&id=")
    for other in ("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG/edit", "https://example.com/a.docx", "http://localhost/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEFG", ""):
        assert google_resume_url(other) is None


def test_each_skill_has_its_own_fingerprint_that_follows_what_it_includes(tmp_path, monkeypatch):
    monkeypatch.setattr("gojob.version_stamp.SKILLS_DIR", tmp_path)
    monkeypatch.setattr("gojob.skill_loader.SKILLS_DIR", tmp_path)

    def write(name: str, body: str) -> None:
        (tmp_path / f"{name}.md").write_text(f"---\nname: {name}\ndescription: a test skill for fingerprints\n---\n\n{body}")

    write("shared", "## part: x\n\nrule x\n\n## part: y\n\nrule y\n")
    write("a", "Task A.\n\n{{include:shared#x}}")
    write("b", "Task B.")
    base = skill_hashes()
    assert set(base) == {"shared", "a", "b"} and all(len(h) == 6 for h in base.values())

    write("shared", "## part: x\n\nrule x\n\n## part: y\n\nrule y changed\n")  # a part that `a` does not include
    after_y = skill_hashes()
    assert after_y["a"] == base["a"] and after_y["b"] == base["b"] and after_y["shared"] != base["shared"]

    write("shared", "## part: x\n\nrule x changed\n\n## part: y\n\nrule y changed\n")  # the part `a` includes
    after_x = skill_hashes()
    assert after_x["a"] != base["a"] and after_x["shared"] != after_y["shared"] and after_x["b"] == base["b"]

    write("b", "Task B, reworded.")
    assert skill_hashes()["b"] != after_x["b"] and skill_hashes()["a"] == after_x["a"]


def test_real_skills_have_fingerprints_and_the_stamp_carries_them():
    hashes = skill_hashes()
    assert {"auditor", "health-check", "shared-rules", "scout"} <= set(hashes)
    assert stamp()["skills"] == hashes
