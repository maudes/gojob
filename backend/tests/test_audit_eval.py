"""The auditor eval must itself be trustworthy: its faults are real, its correct answers are correct,
and its scoring says the right thing about a perfect, a blind and a trigger-happy auditor."""
from __future__ import annotations

import json
import sys

import pytest

from gojob import audit, config
from gojob.schemas import CoverLetter, FineTune, JDAnalysis
from gojob.text_tools import redact

sys.path.insert(0, str(config.ROOT))
from evals import audit_run as A  # noqa: E402
from evals.common import skills_changed  # noqa: E402

CASES = {c["id"]: c for c in A.load_cases()}
CHECKS = {"resumeQuotesVerbatim", "jdQuotesVerbatim", "noInventedFacts", "labelsCorrect", "alignedWithProfile"}
QUOTE_CHECKS = {"resumeQuotesVerbatim", "jdQuotesVerbatim"}
SCHEMA = {"fineTune": FineTune, "jdAnalysis": JDAnalysis, "coverLetter": CoverLetter}


def sources(case: dict) -> dict:
    return {"resume": redact(case["resume"]), "jd": case["jd"]}


# ---------- the fixtures are sound ----------


def test_cases_cover_the_three_tasks_and_every_check():
    assert {c["task"] for c in CASES.values()} == set(SCHEMA)
    assert CHECKS <= {chk for c in CASES.values() for f in c["faults"] for chk in f["expectChecks"]}
    assert sum(len(c["faults"]) for c in CASES.values()) >= 15


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_the_correct_answer_is_valid_and_every_quote_in_it_is_word_for_word(case_id):
    case = CASES[case_id]
    SCHEMA[case["task"]].model_validate(case["clean"])
    check = audit.check_quotes(case["clean"], sources(case))
    assert check["failed"] == [] and check["total"] > 0


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_every_fault_is_real_and_changes_only_what_it_says(case_id):
    case = CASES[case_id]
    corpus = " ".join([case["resume"], case["jd"], case.get("motivation", ""), "Visa sponsorship required: No"]).lower()
    clean_json = json.dumps(case["clean"], ensure_ascii=False)
    seen = set()
    for fault in case["faults"]:
        assert fault["id"] not in seen
        seen.add(fault["id"])
        assert fault["expectChecks"] and set(fault["expectChecks"]) <= CHECKS
        faulty = A.apply_ops(case["clean"], fault["ops"])
        assert faulty != case["clean"], f"{fault['id']} changes nothing"
        SCHEMA[case["task"]].model_validate(faulty)  # the fault is content, never a broken structure
        text = json.dumps(faulty, ensure_ascii=False)
        for planted in fault["introduces"]:
            assert planted.lower() not in corpus, f"{fault['id']}: {planted!r} is already in the sources, so it is not invented"
            assert planted in text and planted not in clean_json, f"{fault['id']}: {planted!r} is not what the fault adds"
        # A quote fault must really break a quote; every other fault must leave the quotes intact, so each
        # fault tests one thing and the code-level quote proof is not what catches it.
        broken = bool(audit.check_quotes(faulty, sources(case))["failed"])
        assert broken == bool(set(fault["expectChecks"]) & QUOTE_CHECKS), f"{fault['id']}: breaks a quote only when it says so"


def test_a_fault_edit_that_does_not_apply_is_an_error_not_a_silent_no_op():
    with pytest.raises(ValueError, match="does not apply"):
        A.apply_ops({"letter": "abc"}, [{"path": "letter", "replace": ["zzz", "y"]}])
    assert A.apply_ops({"a": [{"b": 1}]}, [{"path": "a.0.b", "set": 2}]) == {"a": [{"b": 2}]}


def test_auditors_get_the_sources_the_app_gives_them():
    ctx = A.context_for(CASES["cover-letter-gridly"])
    assert "<PROFILE>" in ctx and "<RESUME>" in ctx and "<JD>" in ctx and "<MOTIVATION" in ctx and "Visa sponsorship required: No" in ctx
    assert "@" not in ctx and "<MOTIVATION" not in A.context_for(CASES["fine-tune-thermostat"])


# ---------- the scoring says the right thing about three kinds of auditor ----------


def fake_audits(flag: bool, expected: tuple[str, ...] = ()) -> list[dict]:
    checks = {c: True for c in CHECKS}
    if flag:
        checks.update({c: False for c in (expected or ("noInventedFacts",))})
    return [{"score": 60 if flag else 99, "checks": dict(checks), "issues": ["x"] if flag else []} for _ in range(5)]


def run_with(monkeypatch, auditor, repeats=2):
    monkeypatch.setattr(A, "audit_once", auditor)
    results = A.evaluate(list(CASES.values()), repeats, workers=2)
    return results, A.summarise(results)


def perfect(context, output, lang):
    for case in CASES.values():
        for v in A.variants(case):
            if v["output"] == output:
                return fake_audits(v["kind"] == "fault", tuple(v["fault"]["expectChecks"]) if v["fault"] else ())
    raise AssertionError("unknown answer")


def test_a_perfect_auditor_passes(monkeypatch):
    results, s = run_with(monkeypatch, perfect)
    assert s["recall"] == 1.0 and s["falseAlarm"] == 0.0 and s["missed"] == [] and s["ok"] is True
    assert all(f["expectedHits"] == 5 * f["runs"] for f in s["byFault"].values())
    assert len(results) == sum(1 + len(c["faults"]) for c in CASES.values())


def test_a_blind_auditor_that_approves_everything_fails_on_recall(monkeypatch):
    _, s = run_with(monkeypatch, lambda *_: fake_audits(False))
    assert s["recall"] == 0.0 and s["falseAlarm"] == 0.0 and s["ok"] is False
    assert len(s["missed"]) == sum(len(c["faults"]) for c in CASES.values())


def test_a_trigger_happy_auditor_fails_on_false_alarms(monkeypatch):
    _, s = run_with(monkeypatch, lambda *_: fake_audits(True))
    assert s["recall"] == 1.0 and s["falseAlarm"] == 1.0 and s["ok"] is False


def test_an_auditor_that_only_checks_one_kind_of_answer_shows_it_per_task(monkeypatch):
    def partial(context, output, lang):
        return perfect(context, output, lang) if "Cloudwise" not in json.dumps(output) else fake_audits(False)

    _, s = run_with(monkeypatch, partial)
    assert s["byTask"]["jdAnalysis"]["faultBlocked"] == 0 and s["byTask"]["fineTune"]["faultBlocked"] == s["byTask"]["fineTune"]["faultRuns"]
    assert 0 < s["recall"] < A.MIN_RECALL and s["ok"] is False


def test_one_miss_in_a_repeat_is_reported_even_when_most_runs_catch_it(monkeypatch):
    missed = []

    def flaky(context, output, lang):
        audits = perfect(context, output, lang)
        if audits[0]["score"] < 95 and not missed:  # the first faulty answer slips through once
            missed.append(1)
            return fake_audits(False)
        return audits

    _, s = run_with(monkeypatch, flaky, repeats=3)
    assert len(s["missed"]) == 1 and s["recall"] > A.MIN_RECALL


# ---------- command line and comparing two runs ----------


def test_the_command_needs_a_key_and_a_yes(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["audit_run.py", "--yes"])
    assert A.main() == 2 and "ANTHROPIC_API_KEY" in capsys.readouterr().out  # conftest removes the key
    monkeypatch.setattr(A, "has_credentials", lambda: True)
    monkeypatch.setattr(sys, "argv", ["audit_run.py", "--cases", "fine-tune-thermostat"])
    assert A.main() == 2 and "model calls" in capsys.readouterr().out  # the estimate, no calls made
    monkeypatch.setattr(sys, "argv", ["audit_run.py", "--list"])
    assert A.main() == 0


def test_comparing_runs_marks_what_got_worse_and_names_the_changed_skill(tmp_path, capsys):
    def run(recall_blocked: int, audit_hash: str) -> dict:
        key = "fine-tune-thermostat/invented-metric"
        return {"meta": {"appVersion": "1", "promptHash": audit_hash, "git": "x", "skills": {"auditor": audit_hash, "scout": "same"}},
                "summary": {"recall": recall_blocked / 3, "falseAlarm": 0.0, "byFault": {key: {"blocked": recall_blocked, "runs": 3, "expectedHits": 0, "task": "fineTune"}}}}

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(run(3, "aaaaaa")))
    b.write_text(json.dumps(run(1, "bbbbbb")))
    assert A.compare(str(a), str(b)) == 1
    out = capsys.readouterr().out
    assert "skills changed: auditor" in out and "WORSE" in out
    assert A.compare(str(a), str(a)) == 0


def test_skills_changed_handles_old_runs_without_fingerprints():
    assert skills_changed({"skills": {"a": "1", "b": "2"}}, {"skills": {"a": "1", "b": "3", "c": "4"}}) == ["b", "c"]
    assert skills_changed({}, {"skills": {"a": "1"}}) is None
