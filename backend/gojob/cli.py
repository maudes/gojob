"""Command line: run one JD assessment without the browser, by API or by Claude Code subagents.
  uv run python -m gojob.cli analyze-jd --jd-file JD.txt [--runner subagent --run NAME] [--save]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config, subagent_runner, tasks
from .model_client import AgentError
from .schemas import Profile
from .store import now_iso, read_db, update_db
from .text_tools import redact


def _profile(args: argparse.Namespace) -> tuple[dict, str, str]:
    """(profile, jd text, language). A --case is a synthetic eval case; otherwise the saved profile is used."""
    if args.case:
        case = json.loads(Path(args.case).read_text("utf8"))
        profile = {**Profile().dump(), **case["profile"], "resumeText": redact(case["resume"]), "savedAt": now_iso()}
        return profile, case["jd"], args.lang or case.get("lang", "en")
    profile = read_db()["profile"]
    if args.resume_file:
        profile = {**profile, "resumeText": Path(args.resume_file).read_text("utf8")}
    if len(profile["resumeText"].strip()) < 200:
        sys.exit("Save a profile with a resume first (or pass --resume-file).")
    jd = Path(args.jd_file).read_text("utf8").strip() if args.jd_file else ""
    if len(jd) < 300:
        sys.exit("Give a job description of at least 300 characters with --jd-file (or use --case).")
    return profile, jd, args.lang or "en"


def analyze_jd(args: argparse.Namespace) -> dict:
    profile, jd, lang = _profile(args)
    run_dir = config.MANUAL_DIR / args.run
    if config.runner() == "subagent":
        subagent_runner.start(run_dir)
    try:
        record = tasks.new_record(profile, jd, args.jd_url or "", lang)
    except subagent_runner.NeedsAnswer:
        waiting = subagent_runner.pending()
        return {"status": "pending", "run": str(run_dir), "waitingFor": len(waiting), "requests": waiting}
    out = {
        "status": "done",
        "runner": config.runner(),
        "approved": record["analysis"]["approved"] and record["panelAudit"]["approved"],
        "gate": record["gate"],
        "auditScores": [a["score"] for a in record["analysis"]["audits"]],
        "panelAuditScores": [a["score"] for a in record["panelAudit"]["audits"]],
        "quoteCheck": record["analysis"]["quoteCheck"],
        "demo": record["analysis"]["demo"],
    }
    if config.runner() == "subagent":
        result_file = run_dir / "result.json"
        result_file.write_text(json.dumps(record, ensure_ascii=False, indent=1), "utf8")
        out["resultFile"] = str(result_file)
    if args.save:
        update_db(lambda d: d["analyses"].insert(0, record))
        out["savedId"] = record["id"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gojob", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze-jd", help="assess one job description against the saved resume")
    a.add_argument("--jd-file", help="text file with the job description")
    a.add_argument("--jd-url", help="where the job was posted (only stored)")
    a.add_argument("--resume-file", help="use this resume text instead of the saved one")
    a.add_argument("--case", help="use an evaluation case (evals/cases/*.json: resume, JD and profile) instead of your data")
    a.add_argument("--lang", choices=["en", "zh"])
    a.add_argument("--runner", choices=["api", "subagent"], default="api", help="who answers the model calls (default: api)")
    a.add_argument("--run", default="run", help="subagent runner: folder name under data/manual/ holding requests and answers")
    a.add_argument("--save", action="store_true", help="save the finished assessment into data/db.json, like the app does")
    args = parser.parse_args(argv)
    os.environ["GOJOB_RUNNER"] = args.runner
    try:
        print(json.dumps(analyze_jd(args), ensure_ascii=False, indent=1))
    except AgentError as err:
        print(json.dumps({"status": "error", "error": str(err)}, ensure_ascii=False, indent=1))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
