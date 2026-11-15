"""LLM judge for usefulness (rubrics/usefulness.md). Opinion, not proof: calibrate it before trusting it.

The judge is only as good as its agreement with a person, so `calibrate.py` compares it with
your own labels. Set EVAL_JUDGE_MODEL to grade with a different (ideally stronger) model than
the writer; by default it uses the writer model.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from gojob.claude import run_json
from gojob.config import MAIN_MODEL

RUBRIC = Path(__file__).with_name("rubrics") / "usefulness.md"


class JudgeScore(BaseModel):
    score: int = Field(description="1 to 5 as defined in the rubric")
    reasons: list[str]


def judge_model() -> str:
    return os.environ.get("EVAL_JUDGE_MODEL") or MAIN_MODEL


def judge(case: dict, task: str, output: dict) -> dict:
    user = (
        f"<TASK>{task}</TASK>\n<RESUME>\n{case['resume']}\n</RESUME>\n<JD>\n{case['jd']}\n</JD>\n"
        + (f"<MOTIVATION>\n{case['motivation']}\n</MOTIVATION>\n" if case.get("motivation") else "")
        + f"<OUTPUT>\n{json.dumps(output, ensure_ascii=False, indent=1)}\n</OUTPUT>"
    )
    result = run_json(schema=JudgeScore, model=judge_model(), system=RUBRIC.read_text("utf8"), user=user, effort="medium")
    return {"score": max(1, min(5, result.score)), "reasons": result.reasons, "model": judge_model()}
