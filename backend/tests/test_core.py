"""Pure logic: redaction, quote proof, gates, applying changes, docx editing, stamps, data upgrades."""
from __future__ import annotations

import json

import pytest

from gojob import config, store
from gojob.docx_io import apply_changes_to_docx, docx_to_text, text_to_docx
from gojob.extract import drive_download_url, html_to_text, is_safe_url
from gojob.meta import prompt_hash, stamp
from gojob.pipeline import check_quotes, gate, is_approved, round_half_up
from gojob.scout import keep_linked
from gojob.selftest import self_test
from gojob.text import apply_to_text, is_verbatim, redact


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


def test_prompt_hash_changes_when_a_prompt_file_changes(tmp_path, monkeypatch):
    (tmp_path / "one-pager.md").write_text("v1")
    monkeypatch.setattr("gojob.meta.PROMPTS_DIR", tmp_path)
    prompt_hash.cache_clear()
    before = prompt_hash()
    (tmp_path / "one-pager.md").write_text("v2")
    prompt_hash.cache_clear()
    assert prompt_hash() != before
    prompt_hash.cache_clear()


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
