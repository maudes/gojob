"""Thresholds live in scoring.py: the health check and JD match use them, and the browser takes them from the state."""
from __future__ import annotations

import json
import re
from pathlib import Path

from gojob import scoring, tasks
from gojob.schemas import Profile

ROOT = Path(__file__).resolve().parents[2]
CASE = json.loads((ROOT / "evals" / "cases" / "no-metrics.json").read_text("utf8"))


def test_health_check_gate_follows_the_constants(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(tasks, "HEALTH_NEED_AVERAGE", 91)
    monkeypatch.setattr(tasks, "HEALTH_NEED_MIN", 66)
    profile = {**Profile().dump(), "resumeText": CASE["resume"], "savedAt": "2026-01-01T00:00:00Z"}
    gate = tasks.health_check(profile, "en", 1)["gate"]
    assert (gate["needAverage"], gate["needMin"]) == (91, 66)


def test_jd_analysis_gate_follows_the_constants(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(tasks, "JD_NEED_AVERAGE", 77)
    monkeypatch.setattr(tasks, "JD_NEED_MIN", 55)
    profile = {**Profile().dump(), "resumeText": CASE["resume"], "savedAt": "2026-01-01T00:00:00Z"}
    gate = tasks.analyze_jd(profile, CASE["resume"], CASE["jd"], "en", 1)["gate"]
    assert (gate["needAverage"], gate["needMin"]) == (77, 55)


def test_the_state_sends_every_threshold_the_browser_uses():
    t = scoring.thresholds()
    assert t["health"] == {"average": scoring.HEALTH_NEED_AVERAGE, "min": scoring.HEALTH_NEED_MIN}
    assert t["jd"] == {"average": scoring.JD_NEED_AVERAGE, "min": scoring.JD_NEED_MIN, "tuneFrom": scoring.JD_TUNE_FROM}


def test_the_browser_holds_no_gate_numbers_of_its_own():
    """The screens take the thresholds from the backend. A literal 80 / 70 / 60 next to a comparison or the word
    'average' means somebody typed a gate number back into the browser code."""
    files = [ROOT / "lib" / "text.ts", ROOT / "components" / "zh.ts", *sorted((ROOT / "components").glob("*.tsx"))]
    pattern = re.compile(r"(?:>=|≥|average)\s*\d{2}\b|\d{2}\s+or more|below\s+\d{2}\b|reviewer\s*(?:<|≥|>=)?\s*\d{2}\b")
    hits = [f"{f.name}: {m[0]}" for f in files for m in pattern.finditer(f.read_text("utf8"))]
    assert not hits, hits


def test_every_translated_gate_sentence_keeps_the_same_placeholders():
    zh = (ROOT / "components" / "zh.ts").read_text("utf8")
    pairs = re.findall(r'^\s*"([^"\n]*\{\w+\}[^"\n]*)":\s*"([^"\n]*)",', zh, flags=re.M)
    assert pairs, "no placeholder sentences found; update this test"
    for en, translated in pairs:
        assert sorted(re.findall(r"\{(\w+)\}", en)) == sorted(re.findall(r"\{(\w+)\}", translated)), en
