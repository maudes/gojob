"""The subagent runner: same pipeline code, same results as the API path, answers come from files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gojob import cli, config, model_client, sample_data, subagent_runner, tasks
from gojob.schemas import Audit, AuditChecks, JDAnalysis, PanelScore, Profile

CASE = Path(__file__).resolve().parents[2] / "evals" / "cases" / "no-metrics.json"


def _audit(score: float = 97) -> Audit:
    return Audit(score=score, checks=AuditChecks(resume_quotes_verbatim=True, jd_quotes_verbatim=True, no_invented_facts=True, labels_correct=True, aligned_with_profile=True), issues=[])


def _panel() -> PanelScore:
    return PanelScore(score=84, verdict="Solid match.", strengths=[], gaps=[])


def scripted(schema):
    """The one answer every fake writer, scorer and auditor gives, whoever is asking."""
    if schema is Audit:
        return _audit()
    if schema is PanelScore:
        return _panel()
    if schema is JDAnalysis:
        return JDAnalysis.model_validate(sample_data.JD_ANALYSIS)
    raise AssertionError(schema)


@pytest.fixture
def profile() -> dict:
    case = json.loads(CASE.read_text("utf8"))
    return {**Profile().dump(), **case["profile"], "resumeText": case["resume"], "savedAt": "2026-01-01T00:00:00Z"}, case["jd"]


def _strip(result: dict) -> dict:
    """Everything but the clock and the stamp, which legitimately differ."""
    text = json.dumps(result, sort_keys=True, ensure_ascii=False)
    out = json.loads(text)

    def clean(node):
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in ("generatedAt", "meta")}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(out)


def _drive(run_dir: Path, run) -> tuple[dict, int]:
    """Replay `run` until it finishes, answering every pending request with the script. Returns (result, rounds)."""
    for rounds in range(1, 12):
        subagent_runner.start(run_dir)
        try:
            return run(), rounds
        except subagent_runner.NeedsAnswer:
            for req in subagent_runner.pending():
                schema = {"Audit": Audit, "PanelScore": PanelScore, "JDAnalysis": JDAnalysis}[req["schema"]]
                Path(req["answerFile"]).write_text(json.dumps(scripted(schema).dump()), "utf8")
    raise AssertionError("the run did not finish")


def test_subagent_answers_give_the_same_result_as_the_api_path(monkeypatch, tmp_path, profile):
    prof, jd = profile
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(model_client, "run_json", lambda *, schema, **_kw: scripted(schema))
    via_api = tasks.analyze_jd(prof, prof["resumeText"], jd, "en", 1)

    monkeypatch.undo()
    monkeypatch.setenv("GOJOB_RUNNER", "subagent")
    via_files, rounds = _drive(tmp_path / "run", lambda: tasks.analyze_jd(prof, prof["resumeText"], jd, "en", 1))

    assert rounds >= 3  # writer and scorers, then the auditors that need their output, then the repair the sample answer triggers
    assert _strip(via_files) == _strip(via_api)
    assert via_files["analysis"]["meta"]["runner"] == "subagent"


def test_first_round_asks_for_writer_and_three_scorers_on_the_capable_model(monkeypatch, tmp_path, profile):
    prof, jd = profile
    monkeypatch.setenv("GOJOB_RUNNER", "subagent")
    subagent_runner.start(tmp_path / "run")
    with pytest.raises(subagent_runner.NeedsAnswer):
        tasks.analyze_jd(prof, prof["resumeText"], jd, "en", 1)
    asked = subagent_runner.pending()
    assert sorted(r["schema"] for r in asked) == ["JDAnalysis", "PanelScore", "PanelScore", "PanelScore"]
    assert {r["agentModel"] for r in asked} == {"opus"}
    for r in asked:
        text = Path(r["promptFile"]).read_text("utf8")
        assert r["answerFile"] in text and "## SYSTEM" in text and "## USER" in text


def test_an_answered_request_is_not_asked_again(monkeypatch, tmp_path):
    monkeypatch.setenv("GOJOB_RUNNER", "subagent")
    subagent_runner.start(tmp_path)
    kw = dict(schema=Audit, model="claude-haiku-5-5", system="s", user="u", effort="low")
    with pytest.raises(subagent_runner.NeedsAnswer):
        subagent_runner.run_json(**kw)
    (req,) = subagent_runner.pending()
    assert req["agentModel"] == "haiku"
    Path(req["answerFile"]).write_text("```json\n" + json.dumps(_audit().dump()) + "\n```", "utf8")  # a fence is tolerated
    subagent_runner.start(tmp_path)
    assert subagent_runner.run_json(**kw).score == 97 and subagent_runner.pending() == []


def test_a_bad_answer_is_set_aside_and_asked_again_with_the_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("GOJOB_RUNNER", "subagent")
    kw = dict(schema=Audit, model="claude-haiku-5-5", system="s", user="u", effort="low")
    for attempt in range(1, 4):
        subagent_runner.start(tmp_path)
        with pytest.raises(subagent_runner.NeedsAnswer):
            subagent_runner.run_json(**kw)
        (req,) = subagent_runner.pending()
        assert req["attempts"] == attempt - 1 and (attempt == 1 or req["error"])
        Path(req["answerFile"]).write_text('{"score": "high"}', "utf8")
    subagent_runner.start(tmp_path)
    with pytest.raises(model_client.AgentError, match="failed validation 3 times"):
        subagent_runner.run_json(**kw)


def test_cli_first_round_lists_the_requests(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "MANUAL_DIR", tmp_path)
    assert cli.main(["analyze-jd", "--case", str(CASE), "--runner", "subagent", "--run", "t"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "pending" and out["waitingFor"] == 4 and len(out["requests"]) == 4
    assert all(Path(r["promptFile"]).exists() for r in out["requests"])


def test_cli_without_a_key_runs_in_sample_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert cli.main(["analyze-jd", "--case", str(CASE)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "done" and out["demo"] is True and out["runner"] == "api"
