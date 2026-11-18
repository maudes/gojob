"""Test the five fidelity auditors: do they catch mistakes that were planted on purpose?

The auditors are the safety net of every answer, and nothing else checks them. Each case in evals/audit/
holds a correct answer and a list of faults (an altered quote, an invented number, a wrong label, ...),
each written as a small edit of the correct answer. This runs the five auditors on the correct answer and on
every faulty version, the way the app runs them, and reports:

  recall       how many faulty answers were blocked (at least one auditor flagged them)
  false alarm  how many correct answers were wrongly blocked (each one costs a repair round and an annoyed user)

    npm run eval:audit -- --list
    npm run eval:audit -- --yes                       real run, all cases, 3 repeats (spends API money)
    npm run eval:audit -- --yes --cases fine-tune-thermostat --repeats 5
    npm run eval:audit -- --compare runs/A.json runs/B.json

Exit code: 0 = recall and false-alarm limits met, 1 = not met, 2 = not run.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from evals.common import print_skill_changes  # noqa: E402
from evals.run import git_state  # noqa: E402
from gojob import pipeline as pl  # noqa: E402
from gojob import prompts as P  # noqa: E402
from gojob.claude import has_credentials  # noqa: E402
from gojob.meta import stamp  # noqa: E402
from gojob.schemas import Profile  # noqa: E402
from gojob.text import redact  # noqa: E402

AUDIT_DIR = Path(__file__).with_name("audit")
RUNS_DIR = Path(__file__).with_name("runs")

# Starting limits, to be tuned after the first real run. Blocking needs only one of the five auditors to
# object, so the bar for catching a fault is deliberately high.
MIN_RECALL = 0.90
MAX_FALSE_ALARM = 0.34


def load_cases(ids: list[str] | None = None) -> list[dict]:
    cases = [json.loads(p.read_text("utf8")) for p in sorted(AUDIT_DIR.glob("*.json"))]
    if ids:
        unknown = set(ids) - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in ids]
    return cases


def apply_ops(output: dict, ops: list[dict]) -> dict:
    """A faulty copy of a correct answer. An op is {"path": "changes.0.label", "set": value} or
    {"path": "letter", "replace": [old, new]} (a text substitution inside a string field)."""
    out = copy.deepcopy(output)
    for op in ops:
        *parents, last = [int(k) if k.isdigit() else k for k in op["path"].split(".")]
        node = out
        for key in parents:
            node = node[key]
        if "set" in op:
            node[last] = op["set"]
        else:
            old, new = op["replace"]
            if old not in node[last]:
                raise ValueError(f"fault edit does not apply: {old!r} is not in {op['path']}")
            node[last] = node[last].replace(old, new, 1)
    return out


def variants(case: dict) -> list[dict]:
    """The correct answer first, then one faulty answer per fault."""
    out = [{"key": f"{case['id']}/clean", "kind": "clean", "output": case["clean"], "fault": None}]
    for f in case["faults"]:
        out.append({"key": f"{case['id']}/{f['id']}", "kind": "fault", "output": apply_ops(case["clean"], f["ops"]), "fault": f})
    return out


def context_for(case: dict) -> str:
    """What the auditors receive as sources, built the way the app builds it for this task."""
    profile = {**Profile().dump(), **case["profile"], "resumeText": redact(case["resume"]), "savedAt": pl.now_iso()}
    context = f"{P.profile_block(profile, profile['resumeText'])}\n{P.jd_block(case['jd'])}"
    if case["task"] == "coverLetter":
        context += f'\n<MOTIVATION note="written by the candidate, treat as confirmed">\n{redact(case.get("motivation", ""))}\n</MOTIVATION>'
    return context


def audit_once(context: str, output: dict, lang: str) -> list[dict]:
    """One run of the five auditors, exactly as in the app. Tests replace this."""
    return pl.run_audits(context, output, lang)


def judge(case: dict, variant: dict, context: str) -> dict:
    started = time.perf_counter()
    audits = audit_once(context, variant["output"], case.get("lang", "en"))
    expected = set(variant["fault"]["expectChecks"]) if variant["fault"] else set()
    failed = [[name for name, ok in a["checks"].items() if not ok] for a in audits]
    return {
        "scores": [a["score"] for a in audits],
        "failedChecks": failed,
        "issues": [i for a in audits for i in a["issues"]],
        "blocked": not pl.is_approved(audits, {"failed": []}),  # quote proof is a separate code check, so only the auditors are judged here
        "expectedHits": sum(1 for f in failed if expected & set(f)),
        "seconds": round(time.perf_counter() - started, 1),
    }


def evaluate(cases: list[dict], repeats: int, workers: int = 3) -> dict[str, dict]:
    """Run the five auditors `repeats` times on every correct and faulty answer."""
    contexts = {c["id"]: context_for(c) for c in cases}
    work = [(c, v) for c in cases for v in variants(c) for _ in range(repeats)]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        done = list(pool.map(lambda w: judge(w[0], w[1], contexts[w[0]["id"]]), work))
    results: dict[str, dict] = {}
    for (c, v), outcome in zip(work, done):
        results.setdefault(v["key"], {"kind": v["kind"], "task": c["task"], "runs": []})["runs"].append(outcome)
    return results


def summarise(results: dict[str, dict]) -> dict:
    """results: variant key -> {"kind", "task", "runs": [judge() ...]}"""
    faulty = [r for v in results.values() if v["kind"] == "fault" for r in v["runs"]]
    clean = [r for v in results.values() if v["kind"] == "clean" for r in v["runs"]]
    rate = lambda rows, f: round(sum(1 for r in rows if f(r)) / len(rows), 3) if rows else None  # noqa: E731
    by_fault = {
        k: {"blocked": sum(r["blocked"] for r in v["runs"]), "runs": len(v["runs"]), "expectedHits": sum(r["expectedHits"] for r in v["runs"]), "task": v["task"]}
        for k, v in results.items()
        if v["kind"] == "fault"
    }
    by_task: dict[str, dict] = {}
    for k, v in results.items():
        t = by_task.setdefault(v["task"], {"faultRuns": 0, "faultBlocked": 0, "cleanRuns": 0, "cleanBlocked": 0})
        side = "fault" if v["kind"] == "fault" else "clean"
        t[f"{side}Runs"] += len(v["runs"])
        t[f"{side}Blocked"] += sum(r["blocked"] for r in v["runs"])
    mean = lambda rows: round(sum(s for r in rows for s in r["scores"]) / max(1, sum(len(r["scores"]) for r in rows)), 1) if rows else None  # noqa: E731
    recall, false_alarm = rate(faulty, lambda r: r["blocked"]), rate(clean, lambda r: r["blocked"])
    return {
        "recall": recall,
        "falseAlarm": false_alarm,
        "meanScoreFaulty": mean(faulty),
        "meanScoreClean": mean(clean),
        "byFault": by_fault,
        "byTask": by_task,
        "missed": sorted(k for k, v in by_fault.items() if v["blocked"] < v["runs"]),
        "ok": recall is not None and recall >= MIN_RECALL and (false_alarm is None or false_alarm <= MAX_FALSE_ALARM),
    }


def print_report(run: dict) -> None:
    s, m = run["summary"], run["meta"]
    print(f"\nGo Job auditor eval · v{m['appVersion']} · audit skill {m['skills'].get('audit', '?')} · prompts {m['promptHash']} · {m['git']} · {m['repeats']} repeat(s)")
    print(f"{'planted fault':58} {'blocked':>9} {'by right check':>15}")
    for key, f in sorted(s["byFault"].items()):
        flag = "  <-- MISSED" if f["blocked"] < f["runs"] else ""
        print(f"{key:58} {f['blocked']:>4}/{f['runs']:<4} {f['expectedHits']:>8}/{f['runs'] * 5:<5}{flag}")
    pct = lambda x: "-" if x is None else f"{x:.0%}"  # noqa: E731
    print(f"\nrecall (faulty answers blocked): {pct(s['recall'])}   needs {MIN_RECALL:.0%}")
    print(f"false alarm (correct answers blocked): {pct(s['falseAlarm'])}   allowed {MAX_FALSE_ALARM:.0%}")
    print(f"mean auditor score: correct {s['meanScoreClean']}, faulty {s['meanScoreFaulty']}   (the app needs every score above {pl.AUDIT_PASS_ABOVE})")
    for task, t in sorted(s["byTask"].items()):
        print(f"  {task:12} faulty blocked {t['faultBlocked']}/{t['faultRuns']}   correct blocked {t['cleanBlocked']}/{t['cleanRuns']}")
    if s["missed"]:
        print("\nMissed at least once (these are the cases to learn from):")
        for k in s["missed"]:
            print(" -", k)
    print("\nRESULT:", "PASS" if s["ok"] else "FAIL")


def compare(a_path: str, b_path: str) -> int:
    a, b = (json.loads(Path(p).read_text("utf8")) for p in (a_path, b_path))
    print(f"A: v{a['meta']['appVersion']} audit {a['meta']['skills'].get('audit', '?')} {a['meta']['git']}   B: v{b['meta']['appVersion']} audit {b['meta']['skills'].get('audit', '?')} {b['meta']['git']}")
    print_skill_changes(a["meta"], b["meta"])
    pct = lambda x: "-" if x is None else f"{x:.0%}"  # noqa: E731
    worse = 0
    for label, key, higher_is_better in (("recall", "recall", True), ("false alarm", "falseAlarm", False)):
        va, vb = a["summary"][key], b["summary"][key]
        bad = va is not None and vb is not None and (vb < va if higher_is_better else vb > va)
        worse += bad
        print(f"{label:12} {pct(va):>6} -> {pct(vb):>6}  {'WORSE' if bad else ''}")
    for k in sorted(set(a["summary"]["byFault"]) | set(b["summary"]["byFault"])):
        fa, fb = a["summary"]["byFault"].get(k), b["summary"]["byFault"].get(k)
        ra = fa["blocked"] / fa["runs"] if fa else None
        rb = fb["blocked"] / fb["runs"] if fb else None
        bad = ra is not None and rb is not None and rb < ra
        worse += bad
        print(f"  {k:56} {pct(ra):>6} -> {pct(rb):>6}  {'WORSE' if bad else ''}")
    return 1 if worse else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--yes", action="store_true", help="confirm that a live run may spend API money")
    ap.add_argument("--repeats", type=int, default=3, help="runs per answer; auditors are not perfectly repeatable (default 3)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    args = ap.parse_args()

    if args.compare:
        return compare(*args.compare)
    cases = load_cases(args.cases.split(",") if args.cases else None)
    if args.list:
        for c in cases:
            print(f"{c['id']:28} {c['task']:12} {len(c['faults'])} faults: {', '.join(f['id'] for f in c['faults'])}")
        return 0
    if not has_credentials():
        print("No ANTHROPIC_API_KEY found. The auditors are model calls, so there is nothing to measure without a key. Add one to .env.local.")
        return 2
    jobs = [(c, v) for c in cases for v in variants(c)]
    calls = len(jobs) * args.repeats * 5
    if not args.yes:
        print(f"{len(cases)} cases, {len(jobs)} answers x {args.repeats} repeats: {calls} auditor-class model calls (up to twice that if a call is retried).\nRe-run with --yes to start.")
        return 2

    started = datetime.now(timezone.utc)
    results = evaluate(cases, args.repeats, args.workers)

    run = {"meta": {**stamp(), "startedAt": started.isoformat(timespec="seconds"), "mode": "live", "git": git_state(), "repeats": args.repeats}, "thresholds": {"minRecall": MIN_RECALL, "maxFalseAlarm": MAX_FALSE_ALARM}, "variants": results}
    run["summary"] = summarise(results)
    print_report(run)
    RUNS_DIR.mkdir(exist_ok=True)
    name = f"audit_{started.strftime('%Y%m%dT%H%M%S')}_v{run['meta']['appVersion']}_a{run['meta']['skills'].get('audit', 'x')}.json"
    (RUNS_DIR / name).write_text(json.dumps(run, indent=1, ensure_ascii=False), "utf8")
    print("saved", RUNS_DIR.relative_to(ROOT) / name)
    return 0 if run["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
