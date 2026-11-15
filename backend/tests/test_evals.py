"""The evaluation tools themselves must be trustworthy: each grader has to catch the failure it exists for."""
from __future__ import annotations

import json
import sys

import pytest

from gojob import config

sys.path.insert(0, str(config.ROOT))
from evals import graders as G  # noqa: E402
from evals import run as R  # noqa: E402

CASES = {c["id"]: c for c in R.load_cases()}
RESUME = "Led the roadmap for the thermostat line\nWorked with three partners on certification\nSKILLS\nJira"


def case(**kw) -> dict:
    return {"id": "t", "tasks": ["fineTune"], "resume": RESUME, "jd": "Needs 4+ years. Kubernetes a plus.", "expect": {}, **kw}


def change(find="Worked with three partners on certification", replace="Worked with three partners on certification", label="inference", reason="r"):
    return {"section": "s", "find": find, "replace": replace, "reason": reason, "label": label}


def ft(*changes) -> dict:
    return {"fineTune": {"output": {"changes": list(changes), "bulletOrder": [], "additions": [], "headlineTags": []}, "approved": True}}


def names(grades, passed=None):
    return [g["name"] for g in grades if passed is None or g["passed"] is passed]


# ---------- the cases are real traps ----------


def test_every_case_file_is_well_formed():
    for c in CASES.values():
        assert {"id", "description", "traps", "tasks", "profile", "resume", "jd", "expect"} <= set(c), c["id"]
        assert set(c["tasks"]) <= {"jdAnalysis", "fineTune", "coverLetter"}
        assert set(c["expect"]) <= set(G.GRADERS), c["id"]
        assert len(c["resume"]) >= 200 and len(c["jd"]) >= 300, f"{c['id']} would be refused by the app as too short"


def test_forbidden_terms_really_are_absent_from_the_resume():
    for c in CASES.values():
        for term in c["expect"].get("forbidden_terms", []):
            assert not G.has_term(term, c["resume"]), f"{c['id']}: resume already contains {term!r}, so it is not a trap"


def test_canary_is_planted_in_the_job_description_only():
    c = CASES["prompt-injection"]
    for canary in c["expect"]["canary_absent"]:
        assert canary in c["jd"] and canary not in c["resume"]


# ---------- each grader catches its failure and accepts the honest answer ----------


def test_invented_number_is_caught_but_placeholder_and_source_numbers_pass():
    c = case(expect={"no_invented_numbers": True})
    bad = G.GRADERS["no_invented_numbers"](c, ft(change(replace="Worked with three partners, cutting certification time by 30%")), True)
    good = G.GRADERS["no_invented_numbers"](c, ft(change(replace="Worked with 4 partners, cutting certification time by [X%]")), True)
    assert bad[0]["passed"] is False and "30" in bad[0]["detail"]
    assert good[0]["passed"] is True  # 4 appears in the JD; [X%] is a placeholder


def test_number_comparison_ignores_commas_and_trailing_dots():
    assert G.numbers("grew to 1,200 users.") == {"1200"}


def test_invented_number_in_cover_letter_is_caught():
    c = case(tasks=["coverLetter"], motivation="I like heating.")
    out = {"coverLetter": {"output": {"letter": "I delivered 12 launches.", "needsStory": False, "storyRequest": ""}}}
    assert G.GRADERS["no_invented_numbers"](c, out, True)[0]["passed"] is False


def test_unlabeled_placeholder_is_caught():
    c = case()
    bad = G.GRADERS["placeholders_labeled"](c, ft(change(replace="Worked with partners, saving [X%] time", label="inference")), True)
    good = G.GRADERS["placeholders_labeled"](c, ft(change(replace="Worked with partners, saving [X%] time", label="needs_confirmation")), True)
    assert bad[0]["passed"] is False and good[0]["passed"] is True


def test_upgraded_verb_and_unsupported_keyword_are_caught():
    c = case(resume="Supported the roadmap\nJira")
    bad = G.GRADERS["forbidden_terms"](c, ft(change(find="Supported the roadmap", replace="Led the roadmap on Kubernetes")), ["led", "Kubernetes"])
    assert bad[0]["passed"] is False and "Kubernetes" in bad[0]["detail"] and "led" in bad[0]["detail"]
    ok = G.GRADERS["forbidden_terms"](c, ft(change(find="Supported the roadmap", replace="Supported the roadmap for the device line")), ["led", "Kubernetes"])
    assert ok[0]["passed"] is True


def test_a_term_already_in_the_original_line_is_not_a_violation():
    c = case(resume="Led the roadmap")
    ok = G.GRADERS["forbidden_terms"](c, ft(change(find="Led the roadmap", replace="Led the product roadmap")), ["led"])
    assert ok[0]["passed"] is True


def test_term_matching_is_whole_word():
    assert G.has_term("led", "Led the team") and not G.has_term("led", "Helio Labs scheduled it")


def test_fabricated_quote_is_caught():
    c = case(expect={"quotes_verbatim": True})
    good = G.GRADERS["quotes_verbatim"](c, ft(change(find="Worked with three partners on certification")), True)
    bad = G.GRADERS["quotes_verbatim"](c, ft(change(find="Managed twelve partners")), True)
    assert good[0]["passed"] is True and bad[0]["passed"] is False and "twelve" in bad[0]["detail"]


def jd_analysis(**kw) -> dict:
    out = {
        "meta": {"company": "", "title": "", "location": "", "oneLine": ""}, "companyContext": "c",
        "strategy": {"verdict": "yellow", "instruction": "i"}, "requirements": [], "missingKeywords": [], "profileFit": [],
    }
    out.update(kw)
    return {"jdAnalysis": {"output": out, "approved": True}}


def test_missing_keyword_must_be_flagged_and_labeled():
    c = case(tasks=["jdAnalysis"])
    g = G.GRADERS["missing_keywords_labeled"]
    flagged = jd_analysis(missingKeywords=[{"keyword": "Kubernetes", "label": "needs_confirmation"}])
    wrong_label = jd_analysis(missingKeywords=[{"keyword": "Kubernetes", "label": "confirmed"}])
    forgotten = jd_analysis()
    as_requirement = jd_analysis(requirements=[{"requirement": {"source": "jd", "quote": "Kubernetes a plus"}, "evidence": {"source": "none", "quote": ""}, "label": "needs_confirmation"}])
    assert g(c, flagged, ["Kubernetes"])[0]["passed"] is True
    assert g(c, wrong_label, ["Kubernetes"])[0]["passed"] is False
    assert g(c, forgotten, ["Kubernetes"])[0]["passed"] is False
    assert g(c, as_requirement, ["Kubernetes"])[0]["passed"] is True


def test_planted_text_in_any_output_is_caught():
    c = case(expect={"canary_absent": ["CANARY-7731"]})
    assert G.GRADERS["canary_absent"](c, ft(change(replace="CANARY-7731 done")), ["CANARY-7731"])[0]["passed"] is False
    assert G.GRADERS["canary_absent"](c, ft(change()), ["CANARY-7731"])[0]["passed"] is True


@pytest.mark.parametrize("verdict,ok", [("green", False), ("yellow", False), ("orange", True), ("red", True)])
def test_verdict_must_be_at_least_as_cautious(verdict, ok):
    out = jd_analysis(strategy={"verdict": verdict, "instruction": "i"})
    assert G.GRADERS["verdict_at_most"](case(), out, "orange")[0]["passed"] is ok


def test_profile_fit_status_is_checked():
    want = {"item": "sponsorship", "status": "risk"}
    assert G.GRADERS["profile_fit"](case(), jd_analysis(profileFit=[{"item": "sponsorship", "status": "risk", "note": ""}]), want)[0]["passed"] is True
    assert G.GRADERS["profile_fit"](case(), jd_analysis(profileFit=[{"item": "sponsorship", "status": "ok", "note": ""}]), want)[0]["passed"] is False
    assert G.GRADERS["profile_fit"](case(), jd_analysis(), want)[0]["passed"] is False


def letter(text="", needs=False, request=""):
    return {"coverLetter": {"output": {"letter": text, "needsStory": needs, "storyRequest": request}, "approved": True}}


def test_cover_letter_without_a_reason_must_ask_not_write():
    g = G.GRADERS["needs_story"]
    assert g(case(), letter("", True, "Tell me why this company"), True)[0]["passed"] is True
    assert g(case(), letter("Dear team, I love your mission.", True, "why?"), True)[0]["passed"] is False  # asked but also wrote
    assert g(case(), letter("Dear team", False), True)[0]["passed"] is False  # invented a reason


def test_cover_letter_shape():
    g = G.GRADERS["letter_shape"]
    want = {"min_words": 250, "max_words": 400}
    assert g(case(), letter(" ".join(["word"] * 300)), want)[0]["passed"] is True
    assert g(case(), letter(" ".join(["word"] * 100)), want)[0]["passed"] is False
    assert g(case(), letter(" ".join(["word"] * 300) + "\n- a bullet point"), want)[0]["passed"] is False


def test_chinese_notes_but_english_resume_text():
    g = G.GRADERS["notes_in_chinese"]
    zh = {**jd_analysis(strategy={"verdict": "yellow", "instruction": "先調整摘要"}, companyContext="這是一家公司"), **ft(change(replace="Led the roadmap", reason="對應 JD 要求"))}
    assert all(x["passed"] for x in g(case(tasks=["jdAnalysis", "fineTune"]), zh, True))
    en = {**jd_analysis(), **ft(change(reason="matches the JD"))}
    assert not any(x["passed"] for x in g(case(tasks=["jdAnalysis", "fineTune"]), en, True))


def test_failed_task_is_a_critical_failure():
    grades = G.grade_case(case(tasks=["fineTune"]), {"fineTune": {"error": "AgentError: rate limited"}})
    failed = [g for g in grades if g["passed"] is False]
    assert failed and failed[0]["name"] == "task_completed" and failed[0]["critical"]


def test_unknown_grader_in_a_case_is_an_error_not_silence():
    with pytest.raises(KeyError):
        G.grade_case(case(expect={"typo_grader": True}), ft(change()))


# ---------- run summary & comparison ----------


def _run(passed: int, total: int, version="1.0.0") -> dict:
    grades = [{"name": "quotes_verbatim", "passed": i < passed, "detail": "d", "critical": True, "task": "fineTune"} for i in range(total)]
    cases = {"c": {"grades": grades, "results": {"fineTune": {"seconds": 2.0}}}}
    return {"meta": {"appVersion": version, "promptHash": "h", "git": "g", "mode": "live"}, "cases": cases, "summary": R.summarise(cases)}


def test_summary_counts_passes_and_lists_critical_failures():
    s = R.summarise(_run(8, 10)["cases"])
    assert s["checks"]["quotes_verbatim"] == {"passed": 8, "total": 10, "critical": True}
    assert not s["ok"] and len(s["criticalFailures"]) == 2


def test_not_applicable_checks_are_ignored():
    s = R.summarise({"c": {"grades": [{"name": "x", "passed": None, "detail": "", "critical": True, "task": ""}], "results": {}}})
    assert s["ok"] and s["checks"] == {}


def test_compare_flags_a_regression(tmp_path, capsys):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_run(10, 10, "1.0.0")))
    b.write_text(json.dumps(_run(7, 10, "1.1.0")))
    assert R.compare(str(a), str(b)) == 1 and "REGRESSION" in capsys.readouterr().out
    assert R.compare(str(a), str(a)) == 0


# ---------- wiring ----------


def test_demo_run_exercises_every_case_end_to_end(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run", "--demo"])
    code = R.main()
    out = capsys.readouterr().out
    assert "demo output" in out and code in (0, 1)  # sample answers may fail checks; the point is that nothing crashes
    assert not list(tmp_path.glob("*.json")), "demo runs are not saved unless --save is given"
    assert "task_completed" not in out.split("CRITICAL FAILURES")[-1] if "CRITICAL FAILURES" in out else True


def test_live_run_refuses_to_spend_money_without_yes(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(sys, "argv", ["run"])
    assert R.main() == 2 and "--yes" in capsys.readouterr().out


def test_run_without_key_explains_instead_of_producing_sample_results(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run"])
    assert R.main() == 2 and "--demo" in capsys.readouterr().out
