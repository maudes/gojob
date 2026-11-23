"""Run the evaluation set against the real pipeline and write a result file.

    npm run eval -- --list                      show the cases
    npm run eval -- --demo                      wiring check with sample output (free, proves nothing about quality)
    npm run eval -- --yes                       real run of every case (costs API money)
    npm run eval -- --yes --judge --cases keyword-trap,no-metrics
    npm run eval -- --compare runs/A.json runs/B.json

Exit code: 0 = every critical check passed, 1 = at least one failed, 2 = not run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from evals import graders  # noqa: E402
from evals.common import print_skill_changes  # noqa: E402
from gojob import tasks  # noqa: E402
from gojob.store import now_iso  # noqa: E402
from gojob.model_client import has_credentials  # noqa: E402
from gojob.version_stamp import stamp  # noqa: E402
from gojob.schemas import Profile  # noqa: E402
from gojob.text_tools import redact  # noqa: E402

CASES_DIR = Path(__file__).with_name("cases")
RUNS_DIR = Path(__file__).with_name("runs")


def load_cases(ids: list[str] | None = None) -> list[dict]:
    cases = [json.loads(p.read_text("utf8")) for p in sorted(CASES_DIR.glob("*.json"))]
    if ids:
        unknown = set(ids) - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in ids]
    return cases


def profile_for(case: dict) -> dict:
    return {**Profile().dump(), **case["profile"], "resumeText": redact(case["resume"]), "savedAt": now_iso()}


def _trim(result: dict, seconds: float) -> dict:
    """Keep what is needed to regrade or relabel later, not the whole record."""
    return {
        "output": result["output"],
        "approved": result["approved"],
        "quoteCheck": result["quoteCheck"],
        "auditScores": [a["score"] for a in result["audits"]],
        "demo": result["demo"],
        "seconds": round(seconds, 1),
    }


def run_case(case: dict) -> dict:
    """Run each task of the case the way the app runs it, and return {task: trimmed result | {error}}."""
    profile = profile_for(case)
    lang = case.get("lang", "en")
    results: dict[str, dict] = {}
    analysis = {"output": {"meta": {"company": "", "title": "", "location": "", "oneLine": ""}}}
    for task in case["tasks"]:
        started = time.perf_counter()
        try:
            if task == "jdAnalysis":
                res = tasks.analyze_jd(profile, profile["resumeText"], case["jd"], lang, 1)
                analysis = res["analysis"]
                results[task] = _trim(analysis, time.perf_counter() - started)
            else:
                record = {"actions": {}, "analysis": analysis, "jdText": case["jd"], "tailoredText": None}
                res = tasks.run_action(task, profile, record, lang, case.get("motivation", ""))
                results[task] = _trim(res, time.perf_counter() - started)
        except Exception as err:  # noqa: BLE001 - a failing task is a result, not a crash
            results[task] = {"error": f"{type(err).__name__}: {err}"}
    return results


def git_state() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("+uncommitted" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "no-git"


def summarise(cases: dict[str, dict]) -> dict:
    by_check: dict[str, dict] = {}
    judge_scores: dict[str, list[int]] = {}
    seconds: list[float] = []
    critical_failures: list[str] = []
    for cid, c in cases.items():
        for g in c["grades"]:
            if g["passed"] is None:
                continue
            row = by_check.setdefault(g["name"], {"passed": 0, "total": 0, "critical": g["critical"]})
            row["total"] += 1
            row["passed"] += bool(g["passed"])
            if g["critical"] and not g["passed"]:
                critical_failures.append(f"{cid}/{g['task'] or '-'}: {g['name']}: {g['detail']}")
        for task, j in c.get("judge", {}).items():
            judge_scores.setdefault(task, []).append(j["score"])
        seconds += [r["seconds"] for r in c["results"].values() if "seconds" in r]
    return {
        "ok": not critical_failures,
        "criticalFailures": critical_failures,
        "checks": by_check,
        "judgeMean": {t: round(sum(v) / len(v), 2) for t, v in judge_scores.items()},
        "meanSecondsPerTask": round(sum(seconds) / len(seconds), 1) if seconds else None,
    }


def estimate(cases: list[dict], judge: bool) -> str:
    opus = haiku = 0
    for c in cases:
        for t in c["tasks"]:
            opus += 4 if t == "jdAnalysis" else 1
            haiku += 10 if t == "jdAnalysis" else 5
        opus += len(c["tasks"]) if judge else 0
    return f"about {opus} writer-class and {haiku} auditor-class model calls, up to twice that when auditors ask for a repair"


def print_report(run: dict) -> None:
    s = run["summary"]
    print(f"\nGo Job eval · v{run['meta']['appVersion']} · prompts {run['meta']['promptHash']} · {run['meta']['mode']} · {run['meta']['git']}")
    print(f"{'check':28} {'pass':>9}  critical")
    for name, r in sorted(s["checks"].items()):
        flag = "yes" if r["critical"] else ""
        print(f"{name:28} {r['passed']:>4}/{r['total']:<4}  {flag}")
    if s["judgeMean"]:
        print("usefulness (1-5):", ", ".join(f"{t} {m}" for t, m in s["judgeMean"].items()))
    if s["meanSecondsPerTask"] is not None:
        print(f"mean time per task: {s['meanSecondsPerTask']}s")
    if s["criticalFailures"]:
        print("\nCRITICAL FAILURES")
        for f in s["criticalFailures"]:
            print(" -", f)
    print("\nRESULT:", "PASS" if s["ok"] else "FAIL", "(demo output: this says nothing about answer quality)" if run["meta"]["mode"] == "demo" else "")


def compare(a_path: str, b_path: str) -> int:
    a, b = (json.loads(Path(p).read_text("utf8")) for p in (a_path, b_path))
    print(f"A: v{a['meta']['appVersion']} prompts {a['meta']['promptHash']} {a['meta']['git']}   B: v{b['meta']['appVersion']} prompts {b['meta']['promptHash']} {b['meta']['git']}")
    print_skill_changes(a["meta"], b["meta"])
    print(f"{'check':28} {'A':>8} {'B':>8}  change")
    regressions = 0
    for name in sorted(set(a["summary"]["checks"]) | set(b["summary"]["checks"])):
        ra, rb = a["summary"]["checks"].get(name), b["summary"]["checks"].get(name)
        pa = ra["passed"] / ra["total"] if ra else None
        pb = rb["passed"] / rb["total"] if rb else None
        note = ""
        if pa is not None and pb is not None and pb < pa:
            note = "REGRESSION"
            regressions += 1
        fmt = lambda p: "-" if p is None else f"{p:.0%}"  # noqa: E731
        print(f"{name:28} {fmt(pa):>8} {fmt(pb):>8}  {note}")
    for t in sorted(set(a["summary"]["judgeMean"]) | set(b["summary"]["judgeMean"])):
        print(f"usefulness {t:18} {a['summary']['judgeMean'].get(t, '-'):>8} {b['summary']['judgeMean'].get(t, '-'):>8}")
    return 1 if regressions else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--demo", action="store_true", help="use the app's sample output; checks wiring only")
    ap.add_argument("--yes", action="store_true", help="confirm that a live run may spend API money")
    ap.add_argument("--judge", action="store_true", help="also score usefulness with the LLM judge")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--save", action="store_true", help="save the result file even in demo mode")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    args = ap.parse_args()

    if args.compare:
        return compare(*args.compare)
    cases = load_cases(args.cases.split(",") if args.cases else None)
    if args.list:
        for c in cases:
            print(f"{c['id']:30} {','.join(c['tasks']):28} {c['description']}")
        return 0

    live = has_credentials()
    if not live and not args.demo:
        print("No ANTHROPIC_API_KEY found, so every answer would be sample output. Add a key to .env.local, or pass --demo for a wiring check.")
        return 2
    if live and args.demo:
        print("--demo is for runs without a key; remove the key or drop --demo.")
        return 2
    if live and not args.yes:
        print(f"{len(cases)} cases. This run makes {estimate(cases, args.judge)}.\nRe-run with --yes to start.")
        return 2

    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        all_results = list(pool.map(run_case, cases))

    out_cases: dict[str, dict] = {}
    for case, results in zip(cases, all_results):
        entry = {"description": case["description"], "traps": case["traps"], "results": results, "grades": graders.grade_case(case, results)}
        if args.judge and live:
            from evals.judge import judge as run_judge

            entry["judge"] = {}
            for task, r in results.items():
                if "output" in r:
                    try:
                        entry["judge"][task] = run_judge(case, task, r["output"])
                    except Exception as err:  # noqa: BLE001
                        entry["judge"][task] = {"score": 1, "reasons": [f"judge failed: {err}"], "model": "-"}
        out_cases[case["id"]] = entry

    run = {
        "meta": {**stamp(), "startedAt": started.isoformat(timespec="seconds"), "mode": "live" if live else "demo", "git": git_state(), "caseCount": len(cases)},
        "cases": out_cases,
    }
    run["summary"] = summarise(out_cases)
    print_report(run)
    if live or args.save:
        RUNS_DIR.mkdir(exist_ok=True)
        name = f"{started.strftime('%Y%m%dT%H%M%S')}_v{run['meta']['appVersion']}_p{run['meta']['promptHash']}_{run['meta']['mode']}.json"
        (RUNS_DIR / name).write_text(json.dumps(run, indent=1, ensure_ascii=False), "utf8")
        print("saved", RUNS_DIR.relative_to(ROOT) / name)
    return 0 if run["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
