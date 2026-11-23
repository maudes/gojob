"""The audit loop: write, audit five times, check quotes, repair once. The model is replaced by a fake."""
from __future__ import annotations

import pytest

from gojob import audit, model_client, scoring, tasks
from gojob.schemas import Audit, AuditChecks, HealthCheck


def audit_result(score: float, ok: bool = True, issues: list[str] | None = None) -> Audit:
    return Audit(
        score=score,
        checks=AuditChecks(resume_quotes_verbatim=ok, jd_quotes_verbatim=True, no_invented_facts=True, labels_correct=True, aligned_with_profile=True),
        issues=issues or [],
    )


class FakeModel:
    """Stands in for run_json. Auditors answer from a queue; the writer is a separate callable."""

    def __init__(self, audit_scores: list[float], issue: str = "made up number"):
        self.audit_scores = list(audit_scores)
        self.issue = issue
        self.audit_calls = 0

    def __call__(self, *, schema, **_kw):
        assert schema is Audit
        score = self.audit_scores[self.audit_calls % len(self.audit_scores)] if len(self.audit_scores) == 5 else self.audit_scores.pop(0)
        self.audit_calls += 1
        return audit_result(score, issues=[self.issue] if score <= audit.AUDIT_PASS_ABOVE else [])


def test_clean_output_passes_first_time_without_repair(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", FakeModel([97] * 5))
    produced: list[str] = []
    result = audit.with_audit(produce=lambda extra: produced.append(extra) or {"ok": 1}, context="ctx", lang="en")
    assert result["approved"] and produced == [""] and len(result["audits"]) == 5


def test_failed_audit_sends_issues_back_to_the_writer_once(monkeypatch):
    # first round: one auditor objects; second round: everyone is happy
    monkeypatch.setattr(model_client, "run_json", FakeModel([97, 97, 97, 97, 80] + [98] * 5))
    produced: list[str] = []

    def produce(extra: str):
        produced.append(extra)
        return {"v": len(produced)}

    result = audit.with_audit(produce=produce, context="ctx", lang="en")
    assert len(produced) == 2
    assert "<REVIEW_ISSUES>" in produced[1] and "made up number" in produced[1] and '"v":1' in produced[1]
    assert result["output"] == {"v": 2} and result["approved"]


def test_repair_happens_only_once_even_if_it_still_fails(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", FakeModel([80] * 5))
    produced: list[str] = []
    result = audit.with_audit(produce=lambda e: produced.append(e) or {}, context="ctx", lang="en")
    assert len(produced) == 2 and not result["approved"]


def test_repair_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", FakeModel([80] * 5))
    produced: list[str] = []
    result = audit.with_audit(produce=lambda e: produced.append(e) or {}, context="ctx", lang="en", repair=False)
    assert len(produced) == 1 and not result["approved"]


def test_a_quote_not_in_the_source_blocks_approval_even_when_auditors_agree(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", FakeModel([99] * 5))
    out = {"keywords": [{"proof": {"source": "resume", "quote": "Led a team of 50"}}]}
    result = audit.with_audit(produce=lambda e: out, context="ctx", lang="en", check=lambda o: audit.check_quotes(o, {"resume": "Led a small team", "jd": ""}))
    assert not result["approved"]
    assert result["quoteCheck"]["failed"] == [{"source": "resume", "quote": "Led a team of 50"}]


def test_repair_prompt_names_the_unverified_quote(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", FakeModel([99] * 5))
    seen: list[str] = []
    audit.with_audit(
        produce=lambda e: seen.append(e) or {"proof": {"source": "jd", "quote": "invented"}},
        context="ctx",
        lang="en",
        check=lambda o: audit.check_quotes(o, {"resume": "", "jd": "real text"}),
    )
    assert len(seen) == 2 and 'not found there word for word: "invented"' in seen[1]


def test_results_carry_the_stamp_run_count_and_time(monkeypatch):
    monkeypatch.setattr(model_client, "run_json", lambda **kw: audit_result(98) if kw["schema"] is Audit else _health())
    result = tasks.reviewed(schema=HealthCheck, role="role", context="c", sources={"resume": "", "jd": ""}, lang="en", runs=3)
    assert result["runs"] == 3 and result["generatedAt"].endswith("Z")
    assert set(result["meta"]) == {"appVersion", "promptHash", "skills", "models", "runner"}


def _health() -> HealthCheck:
    return HealthCheck.model_validate(
        {
            "roleConflict": {"conflict": False, "reason": "r"},
            "positioning": {"statement": "s", "closeToTruth": "t", "closeToTarget": "g"},
            "keywords": [],
            "changes": [],
        }
    )


def test_demo_results_are_stamped_too():
    result = tasks.demo_reviewed({"x": 1}, 2)
    assert result["demo"] and result["meta"]["appVersion"] and result["runs"] == 2


@pytest.mark.parametrize("text", ["no json here", '{"broken": ', ""])
def test_unusable_agent_text_becomes_a_friendly_error(text):
    from gojob.model_client import AgentError

    with pytest.raises(AgentError, match="did not return a usable list"):
        tasks.parse_loose_json(text)


# ---------- Tuning ceiling ----------


def record(*, green=False, tailored="R1", assessed="R1", history=(70.0,), fine_tune=None) -> dict:
    return {
        "tailoredText": tailored,
        "assessedText": assessed,
        "gate": {"green": green},
        "history": [{"average": a} for a in history],
        "actions": {"fineTune": fine_tune} if fine_tune else {},
    }


def tune(resume: str, labels: list[str]) -> dict:
    out = {"output": {"changes": [{"label": x} for x in labels]}}
    return scoring.mark_fine_tune(out, resume)


@pytest.mark.parametrize("avg, low", [(scoring.HEALTH_NEED_AVERAGE, scoring.HEALTH_NEED_MIN), (scoring.JD_NEED_AVERAGE, scoring.JD_NEED_MIN)])
def test_a_gate_needs_the_average_and_no_reviewer_below_the_minimum(avg, low):
    assert scoring.gate([avg, avg, avg], avg, low)["green"]
    assert not scoring.gate([100, 100, low - 1], avg, low)["green"]
    assert not scoring.gate([avg - 1, avg, avg], avg, low)["green"]


def test_ceiling_when_the_fine_tune_found_nothing_the_resume_supports():
    r = record(fine_tune=tune("R1", ["needs_confirmation", "needs_confirmation"]))
    assert scoring.fit_ceiling(r, "R1") == {"reason": "no_evidence_left"}
    assert scoring.fit_ceiling(record(fine_tune=tune("R1", [])), "R1") == {"reason": "no_evidence_left"}


def test_no_ceiling_while_evidence_backed_changes_exist_even_if_the_user_rejected_them():
    ft = tune("R1", ["confirmed", "needs_confirmation"])
    ft["output"]["changes"] = []  # the user accepted or rejected everything
    assert scoring.fit_ceiling(record(fine_tune=ft), "R1") is None


def test_ceiling_when_a_resume_change_barely_moved_the_score():
    stalled = scoring.fit_ceiling(record(history=(71.0, 71.6), tailored="R2", assessed="R2"), "R1")
    assert stalled == {"reason": "score_plateau", "gain": 0.6}
    assert scoring.fit_ceiling(record(history=(71.0, 69.0), tailored="R2", assessed="R2"), "R1")["gain"] == -2.0
    assert scoring.fit_ceiling(record(history=(71.0, 74.0), tailored="R2", assessed="R2"), "R1") is None


def test_no_ceiling_when_green_or_when_the_resume_changed_since_the_assessment():
    assert scoring.fit_ceiling(record(green=True, fine_tune=tune("R1", [])), "R1") is None
    assert scoring.fit_ceiling(record(tailored="R2", assessed="R1", fine_tune=tune("R1", [])), "R1") is None


def test_a_fine_tune_written_for_an_older_resume_does_not_set_the_ceiling():
    assert scoring.fit_ceiling(record(tailored="R2", assessed="R2", fine_tune=tune("R1", [])), "R1") is None
